"""Patient organisations at scale -> data/derived/scale/orgs.json

Sources (each evidence item carries source, url, verbatim quote and the matching rule):
  a) trials      sponsors/collaborators of class OTHER whose name matches
                 foundation|association|alliance|society|network|coalition|connect|trust|federation|support,
                 minus universities/hospitals/companies/professional & funding bodies (build_trials.py), linked to
                 the trial's matched diseases. Evidence = the CT.gov record; quote = the sponsor name as registered.
  b) directories Global Genes Global Advocacy Alliance, NORD ODB, EURORDIS members, Genetic Alliance UK
                 (directories.py: rules dir_disease_field_name / dir_text_name / dir_text_gene)
  c) serp        one Bright Data Google search for diseases still without an org (serp_orgs.py)
Dedup: same website domain (ignoring social/hosting domains) or same normalised name. Existing ids from
data/graph.json are reused when the domain or normalised name matches.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

from build_trials import ONCO, SYMBOL_STOP, build_name_index, find_names, gene_hits, hpo_labels
from common import (GLOBAL_INDEX, GRAPH, OUT, RAW as ROOT_RAW, deinvert, domain_of, norm_text, read_json, slugify, today,
                    write_json)
from directories import all_records, snippet

GENERIC_HOSTS = {"facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "youtube.com",
                 "sites.google.com", "google.com", "wixsite.com", "blogspot.com", "wordpress.com", "groups.io",
                 "linktr.ee", "rarediseases.org", "globalgenes.org", "eurordis.org", "geneticalliance.org.uk",
                 "clinicaltrials.gov", "bit.ly", "gofundme.com", "squarespace.com", "weebly.com"}
RULE_RANK = {"dir_disease_field_name": 0, "dir_text_name": 1, "serp_page_mentions_name": 2,
             "dir_text_gene": 3, "serp_page_mentions_gene": 3}


def org_key_name(name: str) -> str:
    n = norm_text(name)
    n = re.sub(r"\b(the|inc|incorporated|e v|ev|ltd|limited|uk|usa|us|ngo|nfp|asbl|vzw|org|corp)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def norm_domain(url: str | None) -> str | None:
    """Dedup key from a website: the domain for a root URL, domain + first path segment otherwise (several
    member orgs can be hosted on one umbrella domain, e.g. alliance-maladies-rares.org/amis-de-adnp)."""
    if not url:
        return None
    full = url if "://" in url else "http://" + url
    d = domain_of(full)
    if not d or any(d == g or d.endswith("." + g) for g in GENERIC_HOSTS):
        return None
    import urllib.parse as _u
    seg = [x for x in _u.urlparse(full).path.split("/") if x and x.lower() not in ("en", "index.html", "home")]
    return d + ("/" + seg[0].lower() if seg else "")


def main():
    universe = read_json(OUT / "universe.json")
    ds = universe["diseases"]
    gene_diseases = universe["genes"]
    idx = read_json(GLOBAL_INDEX, None)
    mondo_has_orpha = {}
    if idx:
        F = {k: i for i, k in enumerate(idx["f"])}
        mondo_has_orpha = {r[F["id"]]: bool(r[F["orpha"]]) for r in idx["rows"]}
    rare = {did: did.startswith("ORPHA:") or mondo_has_orpha.get(d.get("mondo"), False) for did, d in ds.items()}
    hpo = hpo_labels()
    index, by_first, _ = build_name_index(universe, rare, hpo)
    words = set(w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines())
    genes = {g for g in gene_diseases if len(g) >= 3 and g.lower() not in words and g not in SYMBOL_STOP
             and not g.startswith("HLA-")}

    # ---------------------------------------------------------------- candidates
    cands = []   # {name, website, sources:set, records:[...], links: {did: [evidence]}}

    def add_link(c, did, ev):
        if did not in ds:
            return
        c["links"].setdefault(did, [])
        if ev not in c["links"][did]:
            c["links"][did].append(ev)

    NOT_PATIENT_ORG = re.compile(r"\bNIH\b|National Institutes? of|Section on|Department of|Universit|Hospital|"
                                 r"\bClinic\b|Medical Cent|School of|\bLab(oratory)?\b|rhinolog|surgeon|physician|"
                                 r"academy of|college of|movement disorders? society|heart association|thoracic|otolaryng|"
                                 r"dermatolog|ophthalmolog|patholog|radiolog|anesthes|nurses|pharmacist|neurolog(y|ical) (society|association)|"
                                 r"society (of|for) (clinical|pediatric|paediatric|medical|human genetics)|endocrine society|"
                                 r"american association of|american society of|european society", re.I)
    for r in all_records():
        if NOT_PATIENT_ORG.search(r["name"]):
            continue
        c = {"name": r["name"], "website": r.get("website"), "country": r.get("country"),
             "sources": {r["source"]}, "records": [{"source": r["source"], "url": r["evidence_url"],
                                                    "record": r.get("record_url"), "profile": r.get("profile_url"),
                                                    "quote": r["quote"][:400]}],
             "nord_member": r.get("nord_member"), "links": {}}
        base = {"source": r["source"], "url": r.get("profile_url") if r["source"] == "nord" else r["evidence_url"],
                "directory_page": r["evidence_url"]}
        # (1) structured disease field (EURORDIS 'Disease:', NORD 'Related Rare Diseases:')
        for entry in r.get("focus_list", []):
            for v in [entry] + deinvert(entry):
                k = norm_text(v)
                for did in index.get(k, ()):
                    add_link(c, did, {**base, "url": r["evidence_url"], "quote": r["quote"][:400],
                                      "rule": "dir_disease_field_name", "matched": entry})
        # (2) disease name inside org name or mission text
        texts = [("name", r["name"])] + ([("focus", r["focus"])] if r["source"] == "globalgenes" and r["focus"] else [])
        for field, text in texts:
            for k in find_names(norm_text(text), index, by_first, original=text):
                q = text if field == "name" else (snippet(text, k) or text[:300])
                for did in index[k]:
                    add_link(c, did, {**base, "url": r["evidence_url"], "quote": q, "rule": "dir_text_name",
                                      "matched": k})
            for g in gene_hits(text, genes):
                q = text if field == "name" else next((s for s in re.split(r"(?<=[.!?;])\s+", text) if g in s), text[:300])
                m_after = re.search(re.escape(g) + r"[\s\-]*(duplication|deletion|dup|del)\b", text, re.I)
                for did in gene_diseases[g]:
                    dn = ds[did]["name"].lower()
                    if "somatic" in dn or len(ds[did]["genes"]) >= 10 or ONCO.search(dn):
                        continue   # never credit a gene org to somatic or many-gene umbrella entities
                    if m_after and m_after.group(1).lower()[:3] not in dn:
                        continue   # 'MECP2 Duplication Foundation' -> only duplication entities
                    add_link(c, did, {**base, "url": r["evidence_url"], "quote": q[:300], "rule": "dir_text_gene",
                                      "matched": g})
        cands.append(c)

    trial_orgs = read_json(OUT / "_trial_orgs.json", {"orgs": {}})["orgs"]
    for key, o in trial_orgs.items():
        c = {"name": o["name"], "website": None, "country": None, "sources": {"clinicaltrials.gov"},
             "records": [], "links": {}}
        for did, evs in o["diseases"].items():
            for ev in evs:
                add_link(c, did, {"source": "clinicaltrials.gov", **ev})
        cands.append(c)

    serp = read_json(OUT / "_serp_orgs.json", {"orgs": []})["orgs"]
    SERP_BAD = re.compile(r"jacc|ahajournals|nemours|ludwig|cancerresearch|research\.org$|institute|kidshealth", re.I)
    for o in serp:
        if SERP_BAD.search(domain_of(o["url"])):
            continue   # post-filter added after the final spot-check (journal / hospital / research-institute hits)
        c = {"name": o["name"], "website": o["url"], "country": None, "sources": {"serp"}, "records": [],
             "links": {}}
        for did, ev in o["diseases"].items():
            add_link(c, did, {"source": "serp", **ev})
        cands.append(c)

    # ---------------------------------------------------------------- verbatim check of directory quotes
    from common import get_html as _gh, html_to_text as _h2t, norm_ws as _nw
    import json as _json
    page_text = {}

    def stored_text(src, url):
        key = (src, url)
        if key not in page_text:
            if src == "eurordis":
                raw = _json.loads((ROOT_RAW / "directories" / "eurordis_members.json").read_text())["html"]
                page_text[key] = _nw(_h2t(raw)).lower()
            elif src == "globalgenes":
                txt = []
                for p in sorted((ROOT_RAW / "directories" / "globalgenes").glob("page_*.json")):
                    for r in _json.loads(p.read_text())["records"]:
                        txt.append(_nw(_h2t(r.get("title") or "")) + " " + _nw(_h2t(r.get("content") or "")))
                page_text[key] = " ".join(txt).lower()
            else:
                page_text[key] = _nw(_h2t(_gh(url) or "")).lower()
        return page_text[key]

    n_unverified = 0
    for c in cands:
        for did in list(c["links"]):
            kept = []
            for e in c["links"][did]:
                if e["source"] in ("eurordis", "nord", "globalgenes", "geneticalliance_uk"):
                    q = _nw(e["quote"]).lower().rstrip(" .")
                    if q and q in stored_text(e["source"], e.get("directory_page") or e["url"]):
                        e["verified"] = True
                    else:
                        n_unverified += 1
                        continue
                kept.append(e)
            if kept:
                c["links"][did] = kept
            else:
                del c["links"][did]

    # ---------------------------------------------------------------- dedupe
    graph = read_json(GRAPH, {"nodes": []})
    existing = [n for n in graph.get("nodes", []) if n.get("type") == "patient_org"]
    ex_by_dom = {norm_domain((n.get("attrs") or {}).get("url")): n["id"] for n in existing}
    ex_by_dom.pop(None, None)
    ex_by_name = {org_key_name(n["label"]): n["id"] for n in existing}

    groups, by_dom, by_name = [], {}, {}
    for c in cands:
        dom, nk = norm_domain(c["website"]), org_key_name(c["name"])
        gi = by_dom.get(dom) if dom else None
        if gi is None:
            gi = by_name.get(nk)
        if gi is None:
            gi = len(groups)
            groups.append([])
        groups[gi].append(c)
        if dom:
            by_dom.setdefault(dom, gi)
        by_name.setdefault(nk, gi)

    GENERIC_TOK = set("""disease diseases syndrome syndromes disorder disorders deficiency type foundation research
    association society network alliance trust support group national international american european of for the and
    in with to a an families family parents children kids cure fund federation coalition connect inc uk usa canada
    australia rare related autosomal dominant recessive x linked familial hereditary congenital infantile juvenile
    adult onset early late progressive primary 1 2 3 4 5 6 7 8 9 10""".split())
    DIRECTORY_SRC = {"eurordis", "nord", "globalgenes", "geneticalliance_uk"}

    def disease_tokens(did):
        d = ds[did]
        toks = set()
        for n in [d["name"]] + d.get("synonyms", []):
            toks |= {t for t in norm_text(n).split() if len(t) >= 4 and t not in GENERIC_TOK}
        return toks | {g.lower() for g in d["genes"]}

    orgs, used_ids, by_disease = [], set(), collections.defaultdict(list)
    dropped_trial_links = 0
    for g in groups:
        in_directory = bool(set().union(*(c["sources"] for c in g)) & DIRECTORY_SRC)
        name_toks = set()
        for c in g:
            name_toks |= {t for t in norm_text(c["name"]).split() if len(t) >= 3 and t not in GENERIC_TOK}
        links = {}
        for c in g:
            for did, evs in c["links"].items():
                for e in evs:
                    if e["source"] == "clinicaltrials.gov":
                        dtok = disease_tokens(did)
                        # (1) the org's own name must say something about this disease (or its gene)
                        if not (name_toks & dtok):
                            dropped_trial_links += 1
                            continue
                        # (2) gene-via links: the trial's conditions/title must share a phenotype word with this disease
                        if e["rule"].count(":") >= 2:
                            ctoks = {t for x in (e.get("conditions") or []) + [e.get("context") or ""]
                                     for t in norm_text(x).split() if len(t) >= 4 and t not in GENERIC_TOK}
                            if not (ctoks & (dtok - {g.lower() for g in ds[did]["genes"]})):
                                dropped_trial_links += 1
                                continue
                    if e not in links.get(did, []):
                        links.setdefault(did, []).append(e)
        if not links:
            continue
        # name/website: prefer directory records over trial/serp strings
        ORGW = re.compile(r"foundation|association|alliance|society|network|coalition|connect|trust|federation|support|"
                          r"group|cure|fund|families|parents|charity|project|research|vereniging|verein|asociaci|associa|"
                          r"stichting|fondation|fundaci|e\.v|onlus|asbl|uk|international|org", re.I)
        g_sorted = sorted(g, key=lambda c: (0 if ORGW.search(c["name"]) else 1,
                                            0 if c["sources"] & {"eurordis", "nord", "globalgenes", "geneticalliance_uk"} else 1,
                                            0 if c["website"] else 1))
        name = g_sorted[0]["name"]
        website = next((c["website"] for c in g_sorted if c["website"]), None)
        dom = norm_domain(website)
        oid = ex_by_dom.get(dom) if dom else None
        oid = oid or ex_by_name.get(org_key_name(name))
        reused = bool(oid)
        if not oid:
            base = "org:" + (slugify(name, 50) or "unnamed")
            oid = base if base not in used_ids else f"{base}--{slugify(dom or str(len(used_ids)), 30)}"
        used_ids.add(oid)
        sources = sorted(set().union(*(c["sources"] for c in g)))
        records = [r for c in g for r in c["records"]][:6]
        prof = next((r["profile"] for r in records if r.get("profile")), None)
        diseases = []
        for did, evs in links.items():
            evs = sorted(evs, key=lambda e: RULE_RANK.get(e["rule"], 2 if e["rule"].startswith("trial") else 4))
            best = evs[0]
            diseases.append({"id": did, "name": ds[did]["name"], "mondo": ds[did].get("mondo"),
                             "evidence": {k: best[k] for k in ("source", "url", "quote", "rule", "verified") if k in best}
                             | ({"matched": best["matched"]} if best.get("matched") else {})
                             | ({"context": best["context"]} if best.get("context") else {}),
                             "also": [{k: e[k] for k in ("source", "url", "quote", "rule") if k in e} for e in evs[1:3]],
                             "n_evidence": len(evs)})
            by_disease[did].append(oid)
        diseases.sort(key=lambda x: x["id"])
        orgs.append({"id": oid, "name": name, "url": website or prof or (records[0]["url"] if records else None),
                     "website": website, "directory_profile": prof, "country": next((c["country"] for c in g if c["country"]), None),
                     "nord_member": any(c.get("nord_member") for c in g) or None,
                     "sources": sources, "directory_records": records, "reused_graph_id": reused,
                     "extracted_by": "automated", "diseases": diseases})

    # merge entries that resolved to the same id (two groups matching one existing graph org)
    merged = {}
    for o in orgs:
        if o["id"] not in merged:
            merged[o["id"]] = o
            continue
        m = merged[o["id"]]
        m["sources"] = sorted(set(m["sources"]) | set(o["sources"]))
        m["directory_records"] = (m["directory_records"] + o["directory_records"])[:6]
        have_ids = {d["id"] for d in m["diseases"]}
        m["diseases"] = sorted(m["diseases"] + [d for d in o["diseases"] if d["id"] not in have_ids], key=lambda x: x["id"])
        m["website"] = m["website"] or o["website"]
        m["url"] = m["url"] or o["url"]
    orgs = list(merged.values())
    by_disease = collections.defaultdict(list)
    for o in orgs:
        if not o["url"]:
            o["url"] = o["diseases"][0]["evidence"]["url"]   # trial-only org: link its CT.gov record
        for d in o["diseases"]:
            by_disease[d["id"]].append(o["id"])

    # summary
    per_src = collections.Counter()
    dis_src = collections.defaultdict(set)
    for o in orgs:
        for d in o["diseases"]:
            for e in [d["evidence"]] + d["also"]:
                per_src[e["source"]] += 1
                dis_src[e["source"]].add(d["id"])
    meta = {"generated": today(), "extracted_by": "automated", "rules": __doc__.strip(),
            "counts": {"orgs": len(orgs), "diseases_with_org": len(by_disease),
                       "org_disease_links": sum(len(o["diseases"]) for o in orgs),
                       "evidence_items_by_source": dict(per_src),
                       "diseases_by_source": {k: len(v) for k, v in dis_src.items()},
                       "reused_graph_ids": sum(1 for o in orgs if o["reused_graph_id"]),
                       "trial_links_dropped_by_relevance_rule": dropped_trial_links,
                       "directory_quotes_dropped_unverified": n_unverified}}
    write_json(OUT / "orgs.json", {"meta": meta, "orgs": orgs,
                                    "by_disease": {k: sorted(set(v)) for k, v in sorted(by_disease.items())}})
    print(meta["counts"])


if __name__ == "__main__":
    main()
