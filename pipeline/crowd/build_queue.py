#!/usr/bin/env python3
"""Seed list for the crowd research queue (stdlib only, about 5 s).

    python3 pipeline/crowd/build_queue.py

Reads committed files only:
  data/derived/global/index.json            the 11,456-disease index (MONDO rows, genes, synonyms)
  data/graph.json                           the 45 deep diseases (their genes are excluded)
  data/derived/scale/{trials,orgs,assets,universe}.json   trials / patient groups / registries at scale
  data/derived/population/prevalence.json   MONDO ids with an Orphanet prevalence record
  data/derived/global/dismech_index.json    MONDO ids with a DisMech pathograph
  data/derived/global/mechanism/<b>.json    curated mechanism classes, mechanism cluster, mechanism neighbours

Writes web/app/api/queue/_data/seed.json, which the queue server imports (bundled with the route, so it
works on Vercel without filesystem reads). Rows are in priority order: the first row is researched first.

Who is in the queue: monogenic rows (gene source OMIM/mim2gene or Orphanet, 1-5 genes) that are not one
of the 45 deep diseases and none of whose genes is a deep-disease gene. Non-disease rows (blood groups,
susceptibility, QTL, somatic, "[...]"/"{...}" OMIM phenotypes) are left out.

Usefulness score (weights below, recorded in the output's meta):
  + trials matched by disease name (3) or only by gene (1)
  + at least one patient organisation (2), at least one registry / data platform (1)
  + an Orphanet prevalence record (2)
  + NO DisMech pathograph (1.5): the mechanism gap is largest there; diseases WITH one still rank by
    the other signals, and their packet says so (the volunteer cross-checks rather than starts from zero)
  + listed as a mechanism neighbour of a deep disease (3), or in the same mechanism cluster (1)
  + up to 1 for phenotype annotation depth (n HPO terms / 50, capped)
Ties break on name.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G = ROOT / "data" / "derived" / "global"
S = ROOT / "data" / "derived" / "scale"
OUT = ROOT / "web" / "app" / "api" / "queue" / "_data" / "seed.json"

W = {
    "trials_by_name": 3.0,
    "trials_by_gene": 1.0,
    "orgs": 2.0,
    "registry": 1.0,
    "prevalence": 2.0,
    "no_dismech": 1.5,
    "mechanism_neighbour_of_deep": 3.0,
    "same_cluster_as_deep": 1.0,
    "hpo_depth_max": 1.0,
}

# Row layout of seed.json (also in its "f" header; web/lib/server/queue.ts reads it by position).
FIELDS = ["id", "name", "syn", "genes", "omim", "orpha", "n", "mech", "cluster", "dismech", "trials", "orgs", "regs", "prev", "nb", "score"]

NON_DISEASE = re.compile(
    r"blood group|susceptibility|\bqtl\b|quantitative trait|somatic|protection against|resistance to|"
    r"modifier of|^\[|^\{|^#|polymorphism|variation in|non-disease",
    re.I,
)


def load(p: Path):
    with p.open() as f:
        return json.load(f)


def djb2(s: str) -> int:
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def main() -> None:
    idx = load(G / "index.json")
    f = {k: i for i, k in enumerate(idx["f"])}
    graph = load(ROOT / "data" / "graph.json")
    deep_nodes = [n for n in graph["nodes"] if n["type"] == "disease"]
    deep_genes = {n["id"].split(":", 1)[1] for n in deep_nodes}
    deep_mondo: dict[str, str] = {}
    for n in deep_nodes:
        for m in (n.get("xrefs") or {}).get("MONDO", []) or []:
            deep_mondo[m] = n["id"]
    for r in idx["rows"]:
        if r[f["atlas"]]:
            deep_mondo.setdefault(r[f["id"]], r[f["atlas"]])

    # --- scale layer, keyed by MONDO (several native ids can share one MONDO concept) ---
    trials = load(S / "trials.json")["diseases"]
    universe = load(S / "universe.json")["diseases"]
    native_to_mondo = {k: v.get("mondo") for k, v in universe.items() if v.get("mondo")}
    for k, v in trials.items():
        if v.get("mondo"):
            native_to_mondo.setdefault(k, v["mondo"])
    t_name: dict[str, int] = defaultdict(int)
    t_gene: dict[str, int] = defaultdict(int)
    t_active: dict[str, int] = defaultdict(int)
    for k, v in trials.items():
        m = native_to_mondo.get(k)
        if not m:
            continue
        t_name[m] += v["by_name"]["n"]
        t_gene[m] = max(t_gene[m], v["by_gene"]["n"])
        t_active[m] += v["by_name"].get("active", 0)
    orgs_by: dict[str, set] = defaultdict(set)
    for k, ids in load(S / "orgs.json")["by_disease"].items():
        m = native_to_mondo.get(k)
        if m:
            orgs_by[m].update(ids)
    regs_by: dict[str, set] = defaultdict(set)
    for k, ids in load(S / "assets.json")["by_disease"].items():
        m = native_to_mondo.get(k)
        if m:
            regs_by[m].update(ids)

    prevalence = set(load(ROOT / "data" / "derived" / "population" / "prevalence.json").get("mondo", {}).keys())
    dismech = {r[0] for r in load(G / "dismech_index.json")["rows"]}

    # --- mechanism layer: classes, cluster, neighbours of deep diseases ---
    mech: dict[str, dict] = {}
    for b in range(64):
        p = G / "mechanism" / f"{b}.json"
        if p.exists():
            mech.update(load(p)["d"])
    clusters = {c["id"]: c for c in load(G / "clusters.json")["clusters"]}
    nb_of_deep: dict[str, set] = defaultdict(set)
    deep_clusters: dict[str, set] = defaultdict(set)
    for m, deep in deep_mondo.items():
        e = mech.get(m) or {}
        for nb in e.get("mechanism_neighbours", []) or []:
            nb_of_deep[nb["id"]].add(deep)
        if e.get("cluster_id"):
            deep_clusters[e["cluster_id"]].add(deep)

    rows = []
    whys: dict[str, list] = {}
    used_clusters: set = set()
    skipped = defaultdict(int)
    for r in idx["rows"]:
        rid, name, genes_s, gsrc = r[f["id"]], r[f["name"]], r[f["genes"]], r[f["gsrc"]]
        genes = [g for g in genes_s.split(",") if g]
        if r[f["atlas"]] or rid in deep_mondo:
            skipped["deep"] += 1
            continue
        if gsrc not in (1, 2) or not genes:
            skipped["no_gene"] += 1
            continue
        if len(genes) > 5:
            skipped["over_5_genes"] += 1
            continue
        if any(g in deep_genes for g in genes):
            skipped["deep_gene"] += 1
            continue
        if NON_DISEASE.search(name):
            skipped["non_disease"] += 1
            continue
        e = mech.get(rid) or {}
        classes = sorted({x["class"].split(":", 1)[1] for x in e.get("mechanisms", []) or [] if x.get("class")})
        cid = e.get("cluster_id")
        nbs = sorted(nb_of_deep.get(rid, ()))
        same_cluster = sorted(deep_clusters.get(cid, ())) if cid else []
        tn, tg, ta = t_name.get(rid, 0), t_gene.get(rid, 0), t_active.get(rid, 0)
        no, nr = len(orgs_by.get(rid, ())), len(regs_by.get(rid, ()))
        has_prev = rid in prevalence
        has_dm = rid in dismech
        n_hpo = r[f["n"]]
        score = 0.0
        why = []
        if tn:
            score += W["trials_by_name"]
            why.append(f"{tn} trial{'s' if tn != 1 else ''} name the disease")
        elif tg:
            score += W["trials_by_gene"]
            why.append(f"trials mention {genes[0]}")
        if no:
            score += W["orgs"]
            why.append(f"{no} patient group{'s' if no != 1 else ''}")
        if nr:
            score += W["registry"]
            why.append("registry")
        if has_prev:
            score += W["prevalence"]
            why.append("prevalence known")
        if not has_dm:
            score += W["no_dismech"]
            why.append("no curated mechanism chain yet")
        if nbs:
            score += W["mechanism_neighbour_of_deep"]
            why.append("mechanism neighbour of " + ", ".join(nbs[:3]))
        elif same_cluster:
            score += W["same_cluster_as_deep"]
            why.append("same mechanism family as " + ", ".join(same_cluster[:2]))
        score += min(n_hpo, 50) / 50 * W["hpo_depth_max"]
        if cid:
            used_clusters.add(cid)
        rows.append([
            rid, name, r[f["syn"]], genes,
            [x for x in r[f["omim"]].split(",") if x],
            [x for x in r[f["orpha"]].split(",") if x],
            n_hpo, classes, cid or None, 1 if has_dm else 0,
            [tn, tg, ta], no, nr, 1 if has_prev else 0, nbs[:5], round(score, 2),
        ])
        whys[rid] = why

    rows.sort(key=lambda x: (-x[15], x[1].lower()))
    out = {
        "f": FIELDS,
        "clusters": {c: clusters[c]["label"] for c in sorted(used_clusters) if c in clusters},
        "meta": {
            "generated": date.today().isoformat(),
            "built_by": "pipeline/crowd/build_queue.py",
            "n": len(rows),
            "weights": W,
            "skipped": dict(skipped),
            "deep_genes": sorted(deep_genes),
        },
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"[crowd] {len(rows)} diseases in the queue seed -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"[crowd] skipped: {dict(skipped)}")
    for x in rows[:10]:
        print(f"  {x[15]:5.2f}  {x[0]:16} {x[1][:60]:60} {', '.join(whys[x[0]][:3])}")


if __name__ == "__main__":
    main()
