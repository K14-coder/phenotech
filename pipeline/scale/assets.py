"""Multi-disease registries / data platforms at scale -> data/derived/scale/assets.json

  asset:simons-searchlight   Simons Searchlight 'Genetic Disorders We Study' gene list (registry + natural history
                             study + biorepository). One gene symbol per list line -> every universe disease of that gene.
  asset:cords-registry       CoRDS (Sanford Research) 'Represented Diseases' list.
  asset:iamrare-<slug>       each registry listed on NORD IAMRARE 'Find a Study' (disease label -> registry name/link).
  asset:citizen-health       Citizen Health 'Our advocacy partners' disease/gene list (medical-record natural history).
Matching rules (recorded per link):
  list_item_exact_name    the whole list item equals (token-normalised) a disease name/synonym in the universe
  list_item_name_phrase   a disease name/synonym appears as a whole phrase inside the list item (IAMRARE labels only)
  list_item_gene          the list item is, or contains as a case-sensitive token, a causal gene symbol
                          (credited to every universe disease of that gene, with `gene`)
Quotes are the verbatim list lines from the stored pages (data/raw/scale/pages/).
"""
from __future__ import annotations

import html as _h
import re
from pathlib import Path

from build_trials import ONCO, SYMBOL_STOP, build_name_index, find_names, gene_hits, hpo_labels
from common import GLOBAL_INDEX, OUT, deinvert, get_html, get_page, norm_text, norm_ws, read_json, slugify, today, write_json

SIMONS = "https://www.simonssearchlight.org/research/what-we-study/"
CORDS = "https://research.sanfordhealth.org/rare-disease-registry/represented-diseases"
IAMRARE = "https://iamrare.org/find-a-study/"
CITIZEN = "https://www.citizen.health/communities"


def main():
    universe = read_json(OUT / "universe.json")
    ds, gene_d = universe["diseases"], universe["genes"]
    idx = read_json(GLOBAL_INDEX, None)
    moo = {}
    if idx:
        F = {k: i for i, k in enumerate(idx["f"])}
        moo = {r[F["id"]]: bool(r[F["orpha"]]) for r in idx["rows"]}
    rare = {did: did.startswith("ORPHA:") or moo.get(d.get("mondo"), False) for did, d in ds.items()}
    index, by_first, _ = build_name_index(universe, rare, hpo_labels())
    words = set(w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines())
    genes_ok = {g for g in gene_d if len(g) >= 3 and g.lower() not in words and g not in SYMBOL_STOP}

    def match_item(item: str, url: str, quote: str, phrase=False, exact_gene_ok=True):
        links = []
        hit_ids = set()
        for v in [item] + deinvert(item) + [p.strip() for p in re.split(r"[/()]", item) if len(p.strip()) > 3]:
            for did in index.get(norm_text(v), ()):
                if did not in hit_ids:
                    hit_ids.add(did)
                    links.append({"id": did, "name": ds[did]["name"], "evidence": {"url": url, "quote": quote,
                                  "rule": "list_item_exact_name"}})
        if phrase:
            for k in find_names(norm_text(item), index, by_first, original=item):
                for did in index[k]:
                    if did not in hit_ids:
                        hit_ids.add(did)
                        links.append({"id": did, "name": ds[did]["name"], "evidence": {"url": url, "quote": quote,
                                      "rule": "list_item_name_phrase", "matched": k}})
        gs = set()
        s = item.strip()
        if exact_gene_ok and s in gene_d:          # a bare symbol line ("STXBP1") is unambiguous on a gene list
            gs.add(s)
        gs |= gene_hits(item, genes_ok)
        for g in sorted(gs):
            ids = [x for x in gene_d[g] if not ("somatic" in ds[x]["name"].lower() or ONCO.search(ds[x]["name"])
                                                or len(ds[x]["genes"]) >= 10)]
            if not ids:
                continue
            links.append({"gene": g, "ids": ids, "names": [ds[x]["name"] for x in ids][:6],
                          "evidence": {"url": url, "quote": quote, "rule": "list_item_gene"}})
        return links

    assets = []

    # -- Simons Searchlight
    t = get_page(SIMONS)["text"]
    body = t[t.find("Genetic Disorders We Study"):]
    start = body.find("A - C\nACTB") if "A - C\nACTB" in body else body.find("Copy Number Variants (CNVs)")
    end = body.find("\nSearchlight\nAbout")
    lines = [l.strip() for l in body[start:end].split("\n") if l.strip()]
    sym = [l for l in lines if re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,14}", l) and not re.fullmatch(r"[A-Z] - [A-Z]", l)]
    links = []
    for s in sym:
        if s in gene_d:
            links += match_item(s, SIMONS, s, exact_gene_ok=True)
    assets.append({"id": "asset:simons-searchlight", "name": "Simons Searchlight (registry, natural history study & biorepository)",
                   "kind": "registry", "also_kind": ["natural_history_study", "biobank"], "url": SIMONS,
                   "list_context_quote": "The genetic disorders we study are listed below.",
                   "items_on_list": len(sym), "items_in_universe": len({l["gene"] for l in links}),
                   "not_in_universe": sorted(s for s in sym if s not in gene_d), "diseases": links})

    # -- CoRDS
    t = get_page(CORDS)["text"]
    a, b = t.find("\n11q22"), t.rfind("\nZ")
    lines = [l.strip() for l in t.split("\n")]
    s_i = next((i for i, l in enumerate(lines) if re.match(r"^\d+q|^1p36|^A$", l)), 0)
    items = []
    for l in lines[s_i:]:
        if l in ("Print", "Back to top") or l.startswith("©"):
            break
        if len(l) > 1 and not re.fullmatch(r"[A-Z#]", l):
            items.append(l)
    links = []
    for it in items:
        links += match_item(it, CORDS, it, exact_gene_ok=False)
    assets.append({"id": "asset:cords-registry", "name": "CoRDS - Coordination of Rare Diseases at Sanford (registry)",
                   "kind": "registry", "url": CORDS, "items_on_list": len(items), "diseases": links})

    # -- IAMRARE registries
    h = get_html(IAMRARE) or ""
    groups = []
    for block in h.split('<div class="disease-term-group"')[1:]:
        m = re.search(r'<h2 class="term-group-title">([^<]*)</h2>', block)
        if not m:
            continue
        label = norm_ws(_h.unescape(m.group(1)))
        for h4 in re.findall(r'<h4 class="term-study-title">(.*?)</h4>', block, re.S):
            a = re.search(r'<a href="([^"]+)"', h4)
            reg = norm_ws(_h.unescape(re.sub("<[^>]+>", "", h4)))
            groups.append((label, a.group(1) if a else IAMRARE, reg))
    for label, href, reg in groups:
        quote = f"{label} {reg}"
        lk = match_item(label, IAMRARE, quote, phrase=True, exact_gene_ok=True)
        lk2 = [x for x in match_item(reg, IAMRARE, quote, phrase=True, exact_gene_ok=False)
               if (x.get("id") or x.get("gene")) not in {y.get("id") or y.get("gene") for y in lk}]
        assets.append({"id": "asset:iamrare-" + slugify(reg, 50), "name": reg, "kind": "registry",
                       "program": "NORD IAMRARE", "url": href.strip(), "listed_at": IAMRARE, "disease_label": label,
                       "diseases": lk + lk2})

    # -- Citizen Health partner list
    t = get_page(CITIZEN)["text"]
    seg = t[t.find("Our partners focus on"):t.find("\nAbout\nAdvocacy\nNews\nFAQ")]
    items = sorted(set(l.strip() for l in seg.split("\n")[1:] if l.strip()))
    links = []
    for it in items:
        links += match_item(it, CITIZEN, it, phrase=False, exact_gene_ok=True)
    assets.append({"id": "asset:citizen-health", "name": "Citizen Health (medical-record-based natural history platform)",
                   "kind": "data_platform", "url": CITIZEN,
                   "list_context_quote": "Our partners focus on 100+ rare diseases and conditions including...",
                   "items_on_list": len(items), "diseases": links})

    # summary + per-disease lookup
    by_disease = {}
    for a in assets:
        a["extracted_by"] = "automated"
        for l in a["diseases"]:
            for did in ([l["id"]] if "id" in l else l["ids"]):
                by_disease.setdefault(did, [])
                if a["id"] not in by_disease[did]:
                    by_disease[did].append(a["id"])
    assets = [a for a in assets if a["diseases"]] + [a for a in assets if not a["diseases"]]
    meta = {"generated": today(), "extracted_by": "automated", "rules": __doc__.strip(),
            "counts": {"assets": len(assets), "assets_with_disease_links": sum(1 for a in assets if a["diseases"]),
                       "diseases_with_asset": len(by_disease),
                       "per_asset": {a["id"]: len(a["diseases"]) for a in assets if a["diseases"]}}}
    write_json(OUT / "assets.json", {"meta": meta, "assets": assets, "by_disease": by_disease})
    print({k: v for k, v in meta["counts"].items() if k != "per_asset"})
    for k, v in list(meta["counts"]["per_asset"].items())[:12]:
        print("  ", k, v)


if __name__ == "__main__":
    main()
