"""(2c) One Bright Data Google search per disease still WITHOUT a patient org (max 300 diseases, deduplicated by
MONDO concept), prioritised by trial activity and gene prominence:
    score = 3*ln(1+name-matched trials) + 1.5*ln(1+gene-matched trials) + 1*(Orphanet entity)
            + 0.5*ln(1+#diseases of its gene in the trial pool) + 0.3*ln(1+#HPO annotations)
Query: "<GENE> foundation" when the disease has one causal gene and its name is a numbered subtype or > 6 words
       (families of numbered OMIM subtypes organise by gene); otherwise "<disease name> patient foundation".
Accept a result only if
  - its domain is not a news site, social network, hospital, university, journal, government/health-info portal,
    encyclopedia, testing lab, pharma/biotech or a rare-disease directory, AND
  - the fetched page (direct fetch first, Bright Data unlocker fallback) mentions the disease name/synonym
    (token-normalised phrase) or the gene symbol (case-sensitive token)  -> rule serp_page_mentions_name|gene, AND
  - the page self-describes as an organisation (foundation/association/non-profit/charity/support group/donate...).
The quote is the verbatim page sentence that contains the match. Output: data/derived/scale/_serp_orgs.json
"""
from __future__ import annotations

import concurrent.futures as cf
import socket

socket.setdefaulttimeout(20)
import html as _h
import json
import math
import re
import sys
from pathlib import Path

from build_trials import SYMBOL_STOP, build_name_index, find_names, hpo_labels
from common import (GLOBAL_INDEX, OUT, RAW, BudgetExceeded, bd_live_count, bd_search, domain_of, get_html,
                    get_page, norm_text, read_json, slugify, today, write_json)

MAX_DISEASES = 300
BAD_DOMAIN = re.compile(
    r"(facebook|instagram|twitter|(^|\.)x\.com|linkedin|youtube|tiktok|reddit|pinterest|medium\.com|substack|"
    r"prnewswire|businesswire|globenewswire|news|nytimes|cnn\.|bbc\.|theguardian|forbes|statnews|fierce|biospace|"
    r"healthline|webmd|verywell|everydayhealth|gofundme|change\.org|wikipedia|wikiwand|fandom|quora|amazon\.|"
    r"\.edu$|\.edu\.|\.ac\.|universit|hospital|clinic|childrens|chop\.|stjude|hopkins|nhs\.uk|\.gov$|\.gov\.|"
    r"ncbi|pubmed|medlineplus|orpha\.net|omim|malacards|genecards|uniprot|rarediseases\.org|globalgenes|"
    r"eurordis|geneticalliance|clinicaltrials|nature\.com|sciencedirect|springer|wiley|frontiersin|mdpi|cell\.com|"
    r"plos|bmj|thelancet|jamanetwork|nejm|karger|tandfonline|sagepub|oup\.com|biorxiv|medrxiv|researchgate|"
    r"semanticscholar|europepmc|cochrane|medscape|uptodate|dovepress|hindawi|ahajournals|journal|"
    r"invitae|genedx|blueprintgenetics|preventiongenetics|ambrygen|23andme|centogene|fulgent|labcorp|questdiag|"
    r"pharma|therapeutics|simonssearchlight|rare-x|citizen\.health|ojrd|scielo|ijpediatrics|msdmanuals|"
    r"merckmanuals|britannica|dictionary|disorders\.eyes|dermnet|radiopaedia|patient\.info|nord\.|"
    r"rarediseasesnetwork|rarechromo|contactfamilies|genome\.gov|ghr\.|geneticsandmedicine|kidshealth|"
    r"mayoclinic|clevelandclinic|cedars|mountsinai|massgeneral|stanford|ucsf|yale|harvard|medicine|diagnostic|"
    r"genetic|health|ern-|\.ern|gastro|acmg|ashg|aan\.com|academy|college|cancer\.gov|peacehealth|lpl|"
    r"thinkgenetic|rarediseases\.info|disease-?info|sciencedaily|ivami|orphan|drugs?\.com|rxlist|lab)", re.I)
ORG_WORDS = re.compile(r"\b(foundation|association|alliance|society|network|coalition|connect|trust|federation|"
                       r"support group|families|parents|charity|cure|fund|e\.v\.|community|project|organi[sz]ation)\b", re.I)
SELF_ORG = re.compile(r"(non-?profit|501\s?\(c\)\s?\(?3\)?|registered charity|charity (no|number)|patient (advocacy )?"
                      r"organi[sz]ation|advocacy (group|organi[sz]ation)|support group|our mission|donate|"
                      r"foundation|association|e\.\s?v\.|vzw|asbl|onlus|stichting|verein)", re.I)


def page_title(html: str) -> str | None:
    m = re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', html, re.I) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:site_name"', html, re.I)
    if m:
        return _h.unescape(m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return _h.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None


def org_name(serp_title: str, html: str | None, domain: str = "") -> str:
    """og:site_name, else the title segment that names an organisation, else the domain (never a page title)."""
    m = re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', html or "", re.I)
    if m:
        return _h.unescape(m.group(1)).strip()[:120]
    t = page_title(html or "") or serp_title or ""
    parts = [p.strip() for p in re.split(r"\s[|\-–—:]\s", t) if p.strip()]
    for p in parts[::-1]:
        if ORG_WORDS.search(p):
            return p[:120]
    return domain


def find_quote(text: str, terms_norm: list[str], gene: str | None):
    for line in text.split("\n"):
        for s in re.split(r"(?<=[.!?])\s+", line):
            ns = f" {norm_text(s)} "
            for k in terms_norm:
                if f" {k} " in ns and len(s) <= 400:
                    return s.strip(), "serp_page_mentions_name", k
            if gene and re.search(r"(?<![A-Za-z0-9])" + re.escape(gene) + r"(?![A-Za-z0-9])", s) and len(s) <= 400:
                return s.strip(), "serp_page_mentions_gene", gene
    return None


def main():
    universe = read_json(OUT / "universe.json")
    ds = universe["diseases"]
    trials = read_json(OUT / "trials.json")["diseases"]
    orgs = read_json(OUT / "orgs.json")
    # diseases that have an org from trials/directories (SERP-sourced links are ignored so that a re-run
    # re-evaluates the same diseases from cache instead of moving on to new ones)
    have = {d["id"] for o in orgs["orgs"] for d in o["diseases"]
            if any(e["source"] != "serp" for e in [d["evidence"]] + d["also"])}
    concept = {did: (d.get("mondo") or did) for did, d in ds.items()}
    concepts_with_org = {concept[d] for d in have}
    idx = read_json(GLOBAL_INDEX, None)
    mondo_has_orpha = {}
    if idx:
        F = {k: i for i, k in enumerate(idx["f"])}
        mondo_has_orpha = {r[F["id"]]: bool(r[F["orpha"]]) for r in idx["rows"]}
    rare = {did: did.startswith("ORPHA:") or mondo_has_orpha.get(d.get("mondo"), False) for did, d in ds.items()}
    index, by_first, _ = build_name_index(universe, rare, hpo_labels())
    terms_of = {}
    for k, dids in index.items():
        for did in dids:
            terms_of.setdefault(did, []).append(k)
    words = set(w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines())
    gene_trial_dis = {g: sum(1 for d in v if d in trials) for g, v in universe["genes"].items()}

    cand = {}
    for did, d in ds.items():
        c = concept[did]
        if did in have or c in concepts_with_org:
            continue
        t = trials.get(did, {})
        nn, ng = t.get("by_name", {}).get("n", 0), t.get("by_gene", {}).get("n", 0)
        gp = max((gene_trial_dis.get(g, 0) for g in d["genes"]), default=0)
        score = 3 * math.log1p(nn) + 1.5 * math.log1p(ng) + (1 if rare[did] else 0) + 0.5 * math.log1p(gp) \
            + 0.3 * math.log1p(d.get("n_hpo", 0))
        if c not in cand or score > cand[c][0]:
            cand[c] = (score, did)
    ranked = sorted(cand.values(), reverse=True)[:MAX_DISEASES]
    print(f"diseases without org: {len(cand)} concepts; searching {len(ranked)}; BD used {bd_live_count()}")

    def work(item):
        score, did = item
        d = ds[did]
        gene = d["genes"][0] if len(d["genes"]) == 1 else None
        usable_gene = gene if gene and len(gene) >= 3 and gene.lower() not in words and gene not in SYMBOL_STOP else None
        numbered = bool(re.search(r"\d", d["name"])) or len(d["name"].split()) > 6
        q = f"{usable_gene} foundation" if (usable_gene and numbered) else f"{d['name']} patient foundation"
        rec = {"disease": did, "name": d["name"], "score": round(score, 2), "query": q, "accepted": None, "tried": []}
        try:
            results = bd_search(q, num=10)
        except BudgetExceeded:
            rec["error"] = "budget"
            return rec
        except Exception as e:
            rec["error"] = str(e)[:100]
            return rec
        terms = sorted(terms_of.get(did, []), key=len, reverse=True)
        n_fetch = 0
        for r in results:
            link = r.get("link") or ""
            dom = domain_of(link)
            if not dom or BAD_DOMAIN.search(dom):
                continue
            title = r.get("title") or ""
            if not (ORG_WORDS.search(title) or ORG_WORDS.search(dom.replace("-", " ")) or dom.endswith(".org")
                    or (usable_gene and usable_gene.lower() in dom)):
                continue
            if n_fetch >= 2:
                break
            n_fetch += 1
            try:
                page = get_page(link)
            except BudgetExceeded:
                break
            text = page.get("text") or ""
            hit = find_quote(text, terms, usable_gene) if text else None
            selforg = bool(SELF_ORG.search(text[:20000])) if text else False
            rec["tried"].append({"url": link, "via": page.get("via"), "hit": bool(hit), "self_org": selforg})
            ttl = (page_title(get_html(link) or "") or title).lower()
            if re.search(r"journal|pdq|health professional|clinical (features|review|study)|case report|"
                         r"\bpubmed\b|abstract|proceedings|guideline|task force|recommendation", ttl + " " + title.lower()):
                hit = None   # article / guideline pages are not organisations
            if hit and hit[1] == "serp_page_mentions_gene":
                from build_trials import gene_hits as _gh
                if not _gh(hit[0], {usable_gene}, strict=True, all_texts=[text[:5000]]):
                    hit = None   # symbol without a gene context ('HADH Administration', 'LPL')
            if hit and selforg:
                quote, rule, matched = hit
                rec["accepted"] = {"name": org_name(title, get_html(link), dom), "url": link, "domain": dom,
                                   "evidence": {"url": link, "quote": quote, "rule": rule, "matched": matched,
                                                "query": q, "serp_rank": r.get("rank"), "retrieved": page.get("retrieved")}}
                break
        return rec

    out_dir = RAW / "serp_orgs"
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for rec in ex.map(work, ranked):
            recs.append(rec)
            if len(recs) % 25 == 0:
                print(f"  {len(recs)}/{len(ranked)} done, accepted {sum(1 for r in recs if r['accepted'])}, "
                      f"BD used {bd_live_count()}", flush=True)
    write_json(out_dir / "log.json", {"generated": today(), "records": recs}, indent=1)
    # group accepted by domain
    orgs_out = {}
    for r in recs:
        a = r["accepted"]
        if not a:
            continue
        o = orgs_out.setdefault(a["domain"], {"name": a["name"], "url": a["url"], "diseases": {}})
        o["diseases"][r["disease"]] = a["evidence"]
    write_json(OUT / "_serp_orgs.json", {"generated": today(), "orgs": list(orgs_out.values())})
    print(f"accepted: {sum(1 for r in recs if r['accepted'])}/{len(recs)}; BD used {bd_live_count()}")


if __name__ == "__main__":
    main()
