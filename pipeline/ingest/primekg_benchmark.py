"""Build the PrimeKG therapy-transfer benchmark over the rare diseases of our global index (stdlib only).

Input : data/raw/downloads/primekg/kg_drug_disease.csv   (from pipeline/ingest/primekg_fetch.py)
        data/derived/global/index.json                    (11,456 rare diseases, MONDO-keyed)
        data/raw/downloads/mondo-base.obo                 (for the subtype fallback)
Output: data/derived/ingest/primekg_benchmark.json

MONDO mapping
-------------
PrimeKG disease nodes are MONDO terms: `y_source == "MONDO"` with `y_id` the bare MONDO number
("5044" -> MONDO:0005044), or `y_source == "MONDO_grouped"` with `y_id` an underscore-joined list of
MONDO numbers that PrimeKG merged into one node because their names were near-identical
("1200_1134_15512" -> MONDO:0001200, MONDO:0001134, MONDO:0015512).
A PrimeKG node is mapped to the index rows whose id is one of its MONDO ids (exact match). If none
matches, it is mapped to index rows that are direct MONDO `is_a` children of one of its MONDO ids,
when there are 1-8 of them (`via: "child"`): PrimeKG often annotates the parent ("Gaucher disease")
while our index holds the subtypes. The benchmark unit is the PrimeKG node, with features pooled over
its mapped index rows.

Eligible disease nodes: mapped to >= 1 index row that has a gene (gsrc 1 = OMIM Mendelian, or 2 =
Orphanet), i.e. monogenic / rare. Benchmark drugs: DrugBank drugs with `indication` edges to >= 2
eligible nodes. Candidate pool: every eligible node that is an indication of any benchmark drug.
Contraindication and off-label edges to eligible nodes are kept for the "should rank low" check and
for filtering.

    python3 pipeline/ingest/primekg_benchmark.py              # primary: indication edges are positives
    python3 pipeline/ingest/primekg_benchmark.py --offlabel   # extended: indication + off-label use
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
KG = ROOT / "data/raw/downloads/primekg/kg_drug_disease.csv"
INDEX = ROOT / "data/derived/global/index.json"
MONDO_OBO = ROOT / "data/raw/downloads/mondo-base.obo"
OUT = ROOT / "data/derived/ingest/primekg_benchmark.json"
MAX_CHILDREN = 0   # child fallback disabled: it chained generic parents ("dermatitis", "injury") into unrelated units


def mondo_children():
    kids = defaultdict(set)
    cur = None
    obsolete = False
    with open(MONDO_OBO, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line == "[Term]":
                cur, obsolete = None, False
            elif line.startswith("id: MONDO:"):
                cur = line[4:]
            elif line.startswith("is_obsolete: true"):
                obsolete = True
            elif line.startswith("is_a: MONDO:") and cur and not obsolete:
                kids[line[6:19]].add(cur)
    return kids


def node_mondo(src, nid):
    parts = nid.split("_") if src == "MONDO_grouped" else [nid]
    return ["MONDO:%07d" % int(p) for p in parts if p.isdigit()]


def main():
    idx = json.load(open(INDEX))
    f = idx["f"]
    rows = {r[f.index("id")]: r for r in idx["rows"]}
    gene_of = {k: [g for g in r[f.index("genes")].split(",") if g] for k, r in rows.items()}
    kids = mondo_children()

    nodes = {}                     # primekg node key -> info
    edges = defaultdict(lambda: defaultdict(set))   # relation -> drug -> node keys
    drug_name = {}
    with open(KG) as fh:
        for r in csv.DictReader(fh):
            key = f"{r['y_source']}:{r['y_id']}"
            if key not in nodes:
                mids = node_mondo(r["y_source"], r["y_id"])
                hit = [m for m in mids if m in rows]
                via = "exact"
                if not hit:
                    ch = sorted({c for m in mids for c in kids.get(m, ()) if c in rows})
                    if 1 <= len(ch) <= MAX_CHILDREN:
                        hit, via = ch, "child"
                genes = sorted({g for m in hit for g in gene_of[m]})
                nodes[key] = {"name": r["y_name"], "mondo": mids, "index_ids": hit, "via": via if hit else None,
                              "genes": genes}
            edges[r["relation"]][r["x_id"]].add(key)
            drug_name[r["x_id"]] = r["x_name"]

    # merge PrimeKG nodes that map to overlapping index rows (e.g. "gastric cancer" and "gastric
    # neoplasm"; "CINCA syndrome" and "cryopyrin-associated periodic syndrome") into one unit, so a
    # disease can never be its own transfer target under two names.
    parent = {k: k for k in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    first = {}
    for k in sorted(nodes):
        for m in nodes[k]["index_ids"]:
            if m in first:
                parent[find(k)] = find(first[m])
            else:
                first[m] = k
    comp = defaultdict(list)
    for k in nodes:
        comp[find(k)].append(k)
    unit_of, units = {}, {}
    for members in comp.values():
        members.sort()
        u = members[0]
        for k in members:
            unit_of[k] = u
        units[u] = {"name": " | ".join(dict.fromkeys(nodes[k]["name"] for k in members)),
                    "primekg_nodes": members,
                    "mondo": sorted({m for k in members for m in nodes[k]["mondo"]}),
                    "index_ids": sorted({m for k in members for m in nodes[k]["index_ids"]}),
                    "via": "exact" if any(nodes[k]["via"] == "exact" for k in members) else
                           ("child" if any(nodes[k]["via"] for k in members) else None),
                    "genes": sorted({g for k in members for g in nodes[k]["genes"]})}
    merged = len(nodes) - len(units)
    for rel in edges:
        edges[rel] = defaultdict(set, {d: {unit_of[k] for k in s} for d, s in edges[rel].items()})
    raw_nodes = nodes
    nodes = units
    eligible = {k for k, v in nodes.items() if v["index_ids"] and v["genes"]}
    offlabel_pos = "--offlabel" in sys.argv
    ind = {d: sorted(s & eligible) for d, s in edges["indication"].items()}
    if offlabel_pos:
        for d, s in edges["off-label use"].items():
            ind[d] = sorted(set(ind.get(d, [])) | (s & eligible))
        edges["off-label use"] = defaultdict(set)
    bench_drugs = sorted(d for d, s in ind.items() if len(s) >= 2)
    pool = sorted({n for d in bench_drugs for n in ind[d]})
    poolset = set(pool)
    out = {
        "source": "PrimeKG kg.csv (Chandak, Huang & Zitnik, Sci Data 2023), Harvard Dataverse doi:10.7910/DVN/IXA7BM v2 (2022-05-02), file 6180620",
        "licence": "PrimeKG code MIT (github.com/mims-harvard/PrimeKG); Dataverse dataset CC0 1.0. Drug-disease edges derive from DrugCentral and DrugBank-curated indications (see PrimeKG paper)",
        "mapping": "PrimeKG MONDO / MONDO_grouped node -> index rows by exact MONDO id; else direct is_a children in the index (1-8). Nodes sharing an index row are merged into one unit. Eligible = mapped to >=1 index row with a gene.",
        "counts": {
            "primekg_disease_nodes_with_drug_edges": len(raw_nodes),
            "units_after_merging_overlapping_nodes": len(nodes), "nodes_merged": merged,
            "mapped_nodes": sum(1 for v in nodes.values() if v["index_ids"]),
            "mapped_exact": sum(1 for v in nodes.values() if v["via"] == "exact"),
            "mapped_child": sum(1 for v in nodes.values() if v["via"] == "child"),
            "eligible_nodes": len(eligible),
            "drugs_with_any_eligible_indication": sum(1 for s in ind.values() if s),
            "benchmark_drugs": len(bench_drugs),
            "candidate_pool": len(pool),
            "cases": sum(len(ind[d]) for d in bench_drugs),
            "contraindication_pairs_in_pool": sum(len(edges["contraindication"].get(d, set()) & poolset) for d in bench_drugs),
            "offlabel_pairs_in_pool": sum(len(edges["off-label use"].get(d, set()) & poolset) for d in bench_drugs),
        },
        "pool": pool,
        "nodes": {k: nodes[k] for k in sorted(eligible)},
        "drugs": {d: {"name": drug_name[d], "indication": ind[d],
                      "contraindication": sorted(edges["contraindication"].get(d, set()) & poolset),
                      "offlabel": sorted(edges["off-label use"].get(d, set()) & poolset)} for d in bench_drugs},
    }
    out["positives"] = "indication + off-label use" if offlabel_pos else "indication"
    out_path = OUT.with_name("primekg_benchmark_offlabel.json") if offlabel_pos else OUT
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(json.dumps(out["counts"], indent=1))


if __name__ == "__main__":
    main()
