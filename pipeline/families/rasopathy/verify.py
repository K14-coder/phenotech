"""Independent verification of data/curated/family_rasopathy.json.

1. Every quote is re-checked as a normalised SUBSTRING of the locally stored source (nothing is
   trusted from curation.py):
     PubMed   -> data/raw/families/rasopathy/pubmed/<PMID>.json (title + abstract)
     CT.gov   -> clinicaltrials/<NCT>.json (all protocolSection text)
     Website  -> web/<id>.txt via web/_manifest.json URL, or fda/<drug>.label.json for DailyMed URLs
     GO       -> quickgo/terms*.json definitions;  UniProt -> uniprot/<SYMBOL>.json FUNCTION text
   `verified` is set true/false accordingly (--write stores it).
2. Every edge endpoint and cluster member must exist in this fragment or in data/graph.json.
3. Schema checks (and, when data/graph.json exists, that every endpoint is in fragment or graph): deterministic edge ids, legal relation types, evidence present (unless hypothesis),
   confidence in [0, 1], quote present on PubMed/Website evidence, url on every evidence item.
Exit code 1 on any failure.
Run:  python3 pipeline/families/rasopathy/verify.py [--write]
"""
from __future__ import annotations

import sys
from collections import Counter

from ras_common import GRAPH, OUT_FRAGMENT, RAW, existing_node_types, norm, read_json, write_json

WRITE = "--write" in sys.argv
LEGAL = {"causes": ("gene", "disease"), "variant_in": ("variant_group", "gene"), "has_effect": ("variant_group", "mechanism"),
         "participates_in": ("gene", "mechanism"), "driven_by": ("disease", "mechanism"), "has_phenotype": ("disease", "phenotype"),
         "shares_mechanism": ("disease", "disease"), "similar_phenotype": ("disease", "disease"),
         "serves": ("patient_org", "disease"), "maintains": (("patient_org", "researcher"), "asset"), "covers": ("asset", "disease"),
         "studies": ("study", "disease"), "tests": ("study", "therapy"), "targets": ("therapy", "mechanism"),
         "developed_for": ("therapy", "disease"), "works_on": ("researcher", ("gene", "disease", "mechanism"))}
_cache = {}


def _flat(o):
    if isinstance(o, str):
        return [o]
    if isinstance(o, dict):
        return [x for v in o.values() for x in _flat(v)]
    if isinstance(o, list):
        return [x for v in o for x in _flat(v)]
    return []


def stored_text(ev):
    ref, src, url = ev.get("ref", ""), ev.get("source"), ev.get("url", "")
    key = (src, ref, url)
    if key in _cache:
        return _cache[key]
    txt = None
    if src == "PubMed" and ref.startswith("PMID:"):
        p = RAW / "pubmed" / f"{ref[5:]}.json"
        if p.exists():
            r = read_json(p)
            txt = r["title"] + " " + r["abstract"]
    elif src == "ClinicalTrials.gov":
        p = RAW / "clinicaltrials" / f"{ref}.json"
        if p.exists():
            txt = " ".join(_flat(read_json(p)["protocolSection"]))
    elif src == "Website":
        if "dailymed.nlm.nih.gov" in url:
            for p in (RAW / "fda").glob("*.label.json"):
                res = read_json(p)["results"][0]
                if res["set_id"] in url:
                    txt = " ".join(res.get("indications_and_usage", []))
        else:
            man = read_json(RAW / "web" / "_manifest.json")
            sid = next((k for k, m in man.items() if m["url"] == url and m.get("status") == 200), None)
            if sid:
                txt = (RAW / "web" / f"{sid}.txt").read_text()
    elif src == "GO":
        txt = " ".join((r.get("definition") or {}).get("text", "") for p in (RAW / "quickgo").glob("terms*.json")
                       for r in read_json(p)["results"])
    elif src == "UniProt":
        txt = " ".join(t.get("value", "") for p in (RAW / "uniprot").glob("*.json") for res in read_json(p).get("results", [])
                       for c in res.get("comments", []) for t in c.get("texts", []) or [])
    _cache[key] = norm(txt) if txt else None
    return _cache[key]


def main():
    frag = read_json(OUT_FRAGMENT)
    # endpoints may live in this fragment or in the other fragments that build_graph.py merges into
    # data/graph.json; after a build, data/graph.json itself is checked too (see bottom)
    graph_nodes = existing_node_types()
    types = dict(graph_nodes)
    types.update({n["id"]: n["type"] for n in frag["nodes"]})
    fails, by_src = [], Counter()
    checked = ok = 0

    def visit(ev, where):
        nonlocal checked, ok
        if not ev.get("url"):
            fails.append(f"{where}: evidence without url ({ev.get('ref')})")
        q = ev.get("quote")
        if not q:
            if ev.get("source") in ("PubMed", "Website"):
                fails.append(f"{where}: {ev['source']} evidence without quote ({ev.get('ref')})")
            return
        checked += 1
        txt = stored_text(ev)
        good = bool(txt) and norm(q) in txt
        ev["verified"] = good
        if good:
            ok += 1
            by_src[ev["source"]] += 1
        else:
            fails.append(f"{where}: quote NOT verified [{ev.get('source')} {ev.get('ref')}]: {q[:100]!r}")

    for n in frag["nodes"]:
        for e in n.get("sources", []):
            visit(e, n["id"])
    for e in frag["edges"]:
        if e["id"] != f"{e['source']}|{e['type']}|{e['target']}":
            fails.append(f"non-deterministic edge id {e['id']}")
        for end in ("source", "target"):
            if e[end] not in types:
                fails.append(f"dangling {end} {e[end]} in {e['id']}")
        if e["type"] in LEGAL and e["source"] in types and e["target"] in types:
            s_ok, t_ok = LEGAL[e["type"]]
            s_ok = s_ok if isinstance(s_ok, tuple) else (s_ok,)
            t_ok = t_ok if isinstance(t_ok, tuple) else (t_ok,)
            if types[e["source"]] not in s_ok or types[e["target"]] not in t_ok:
                fails.append(f"illegal {e['type']}: {types[e['source']]} -> {types[e['target']]} ({e['id']})")
        elif e["type"] not in LEGAL:
            fails.append(f"unknown edge type {e['type']}")
        if not e.get("evidence") and e.get("evidence_level") != "hypothesis":
            fails.append(f"edge without evidence {e['id']}")
        if not 0 <= e.get("confidence", -1) <= 1:
            fails.append(f"confidence out of range {e['id']}")
        for ev in e.get("evidence", []):
            visit(ev, e["id"])
        for ev in e.get("counter_evidence", []):
            visit(ev, e["id"] + " (counter)")
    eids = {e["id"] for e in frag["edges"]}
    for c in frag["clusters"]:
        for m in c["members"]:
            if m not in types:
                fails.append(f"cluster {c['id']} member missing: {m}")
        for x in c["edge_ids"]:
            if x not in eids:
                fails.append(f"cluster {c['id']} edge missing: {x}")
    dup = [i for i, k in Counter(n["id"] for n in frag["nodes"]).items() if k > 1]
    reused = [n["id"] for n in frag["nodes"] if n["id"] in graph_nodes]
    print(f"nodes {len(frag['nodes'])} (re-emitted existing ids: {len(reused)}; duplicates: {len(dup)}), "
          f"edges {len(frag['edges'])}, clusters {len(frag['clusters'])}, gaps {len(frag['gaps'])}")
    print(f"quotes checked {checked}, verified {ok}, failed {checked - ok}; by source {dict(by_src)}")
    endpoints_external = sorted({x for e in frag["edges"] for x in (e["source"], e["target"])
                                 if x not in {n['id'] for n in frag['nodes']}})
    print(f"edge endpoints reused from data/graph.json: {len(endpoints_external)} -> {endpoints_external[:12]}...")
    if GRAPH.exists():
        gids = {n["id"] for n in read_json(GRAPH)["nodes"]}
        mine_in_graph = sum(1 for n in frag["nodes"] if n["id"] in gids)
        miss = sorted({x for e in frag["edges"] for x in (e["source"], e["target"])} - gids - {n["id"] for n in frag["nodes"]})
        print(f"data/graph.json: {mine_in_graph}/{len(frag['nodes'])} fragment nodes present; endpoints missing from "
              f"fragment+graph: {len(miss)}")
        fails += [f"endpoint missing from fragment and graph.json: {x}" for x in miss]
    for f in fails[:60]:
        print("  FAIL", f)
    print(f"problems: {len(fails)}")
    if WRITE:
        write_json(OUT_FRAGMENT, frag)
        print(f"wrote verified flags into {OUT_FRAGMENT}")
    sys.exit(1 if fails or dup or reused else 0)


if __name__ == "__main__":
    main()
