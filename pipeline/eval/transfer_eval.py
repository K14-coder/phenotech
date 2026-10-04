"""Accuracy evaluation for the atlas graph: connectivity + a therapy-transfer benchmark.

Run:  python3 pipeline/eval/transfer_eval.py          (stdlib only, ~10 s, no network, no OpenAI)
Reads: data/graph.json, data/curated/{biology,family_*}.json (family of each disease),
       data/build/report.md, docs/agent-reports/openai-extraction.md (agreement numbers, parsed),
       data/derived/global/{index.json,mechanism/*.json} (G2P / ClinGen mechanism classes)
Writes: data/derived/eval.json

Question: how well is the graph connected, and how accurately can it say how progress on one
disease could help another?

Benchmark: leave-one-out over every known therapy -> disease link (developed_for; study -tests->
therapy + study -studies-> disease as context and in the extended set). For a held-out pair the
developed_for edge and every study edge linking that therapy class to that disease are hidden, then
all 45 diseases minus the class's other known diseases are scored (filtered ranking) and the rank of
the held-out disease recorded. Ties are scored at their expectation (random tie-break), so a scorer
that cannot separate candidates earns exactly the random baseline. 95% intervals: bootstrap that
resamples therapy classes (cases of one therapy are correlated), 2,000 draws, fixed seed.
"""
from __future__ import annotations

import json
import os
import math
import pathlib
import random
import re
import statistics
import sys
from collections import Counter, defaultdict, deque

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from transfer_score import EQUIVALENCE, RECOMMENDED, ROOT, TransferIndex, load_graph  # noqa: E402

OUT = ROOT / "data" / "derived" / "eval.json"
B = 2000
SEED = 20261004
KS = (1, 3, 5)
GENERIC = {"mech:loss-of-function", "mech:haploinsufficiency", "mech:gain-of-function", "mech:dominant-negative"}
FAMILY_FILE = {"biology": "SNAREopathies (+SLC6A1)", "family_dee": "DEE", "family_lysosomal": "Lysosomal",
               "family_rasopathy": "RASopathies"}
SCORERS = [  # (key, label for the table, letter in the brief)
    ("random", "Random", "a"),
    ("phenotype", "Phenotype similarity (IC-weighted)", "b"),
    ("mechanism", "Mechanism match, IDF-weighted, incl. processes", "c"),
    ("pheno+mech", "Phenotype + mechanism", "d"),
    ("mech+cluster", "Mechanism + shared curated cluster", "e"),
    ("combined", "Phenotype + mechanism + cluster", "f"),
    ("mech-similarity", "Mechanism-profile similarity to known diseases", "extra"),
    ("same-family", "Baseline: same curated family as the known diseases", "base"),
    ("mech+cluster-leaky", "(e) incl. therapy-informed clusters (LEAKY)", "leak"),
    ("naive-driven_by", "Naive rule: target is a driven_by mechanism", "base"),
    ("hypotheses-rule", "Current pipeline/derive/hypotheses.py chain rule", "base"),
    ("hypotheses-rule-no-cluster", "Current rule without its cluster chain", "base"),
]
EPS = 1e-9


def r3(x):
    return None if x is None else round(x, 3)


# ====================================================================== connectivity
def families(nodes):
    fam = {}
    for f, label in FAMILY_FILE.items():
        d = json.loads((ROOT / "data" / "curated" / f"{f}.json").read_text())
        for n in d.get("nodes", []):
            if n["type"] == "disease":
                fam.setdefault(n["id"], label)
    return {d: fam.get(d, "unassigned") for d in nodes if nodes[d]["type"] == "disease"}


def components(node_ids, edges):
    parent = {n: n for n in node_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in edges:
        a, b = find(e["source"]), find(e["target"])
        if a != b:
            parent[a] = b
    comp = Counter(find(n) for n in node_ids)
    return comp, find


def bfs_lengths(diseases, adj):
    out = []
    dl = set(diseases)
    for i, s in enumerate(diseases):
        dist = {s: 0}
        q = deque([s])
        while q:
            x = q.popleft()
            for y in adj[x]:
                if y not in dist:
                    dist[y] = dist[x] + 1
                    q.append(y)
        for t in diseases[i + 1:]:
            out.append(dist.get(t))
    return out


def path_stats(diseases, edges, keep_node_types=None):
    adj = defaultdict(set)
    for e in edges:
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])
    ls = bfs_lengths(diseases, adj)
    conn = [x for x in ls if x is not None]
    return {"pairs": len(ls), "connected_pairs": len(conn), "share_connected": r3(len(conn) / len(ls)),
            "median_hops": statistics.median(conn) if conn else None,
            "mean_hops": r3(statistics.mean(conn)) if conn else None, "max_hops": max(conn) if conn else None,
            "hops_histogram": dict(sorted(Counter(conn).items()))}


def connectivity(g, idx, fam):
    nodes = idx.nodes
    E = g["edges"]
    non_hyp = [e for e in E if e["evidence_level"] != "hypothesis"]
    comp, find = components(list(nodes), non_hyp)
    giant_root, giant = comp.most_common(1)[0]
    diseases = idx.diseases
    giant_dis = sum(1 for d in diseases if find(d) == giant_root)
    outside = sorted(Counter(nodes[n]["type"] for n in nodes if find(n) != giant_root).items())

    # evidence-backed disease -> mechanism (no inferred, no hypothesis edges)
    eb_levels = {"hypothesis", "inferred"}
    ebe = [e for e in E if e["evidence_level"] not in eb_levels]
    by = defaultdict(list)
    for e in ebe:
        by[e["type"]].append(e)
    gene_of = {e["target"]: e["source"] for e in by["causes"]}
    vg_gene = defaultdict(set)
    for e in by["variant_in"]:
        vg_gene[e["target"]].add(e["source"])
    eff = defaultdict(set)
    for e in by["has_effect"]:
        eff[e["source"]].add(e["target"])
    part = defaultdict(set)
    for e in by["participates_in"]:
        part[e["source"]].add(e["target"])
    dm = defaultdict(set)
    for e in by["driven_by"]:
        dm[e["source"]].add(e["target"])
    for d in diseases:
        gn = gene_of.get(d)
        if gn:
            dm[d] |= part.get(gn, set())
            for vg in vg_gene.get(gn, ()):
                dm[d] |= eff.get(vg, set())
    mech_dis = defaultdict(set)
    for d in diseases:
        for m in dm[d]:
            mech_dis[m].add(d)

    def linked(d, specific=False, cross=False):
        for m in dm[d]:
            if specific and m in GENERIC:
                continue
            for o in mech_dis[m]:
                if o != d and (not cross or fam[o] != fam[d]):
                    return True
        return False
    n = len(diseases)
    shares = {
        "any_mechanism": sum(linked(d) for d in diseases),
        "specific_mechanism": sum(linked(d, True) for d in diseases),
        "specific_mechanism_cross_family": sum(linked(d, True, True) for d in diseases),
        "any_mechanism_cross_family": sum(linked(d, False, True) for d in diseases),
    }
    pair_any = sum(1 for i, a in enumerate(diseases) for b in diseases[i + 1:] if dm[a] & dm[b])
    pair_spec = sum(1 for i, a in enumerate(diseases) for b in diseases[i + 1:] if (dm[a] & dm[b]) - GENERIC)
    pair_gen = sum(1 for i, a in enumerate(diseases) for b in diseases[i + 1:] if dm[a] & dm[b] & GENERIC)

    bridges = []
    for m, ds in sorted(mech_dis.items()):
        fs = sorted({fam[d] for d in ds})
        if len(fs) > 1:
            bridges.append({"mechanism": m, "label": nodes[m]["label"], "generic": m in GENERIC,
                            "n_diseases": len(ds), "families": fs,
                            "diseases": sorted(x.split(":")[1] for x in ds)})

    # disease-disease computed links
    dd = [e for e in E if e["type"] in ("shares_mechanism", "similar_phenotype")]
    dd_pairs = {tuple(sorted((e["source"], e["target"]))) for e in dd}
    dd_cross = sorted(p for p in dd_pairs if fam[p[0]] != fam[p[1]])
    has_nb = {x for p in dd_pairs for x in p}
    cross_edges = [{"pair": [a.split(":")[1], b.split(":")[1]], "families": [fam[a], fam[b]],
                    "types": sorted(e["type"] for e in dd if tuple(sorted((e["source"], e["target"]))) == (a, b))}
                   for a, b in dd_cross]

    # therapies spanning families (known = developed_for or study)
    tclass_cross = []
    for c, kd in idx.known.items():
        fs = sorted({fam[d] for d in kd})
        if len(fs) > 1:
            tclass_cross.append({"therapy": c, "families": fs, "diseases": sorted(d.split(":")[1] for d in kd)})

    bio_types = {"causes", "variant_in", "has_effect", "participates_in", "driven_by", "has_phenotype"}
    bio = [e for e in ebe if e["type"] in bio_types]
    mech_only = [e for e in bio if e["type"] != "has_phenotype"]
    paths = {
        "full_graph_no_hypotheses": path_stats(diseases, non_hyp),
        "biology_evidence_backed": path_stats(diseases, bio),
        "mechanism_only_evidence_backed": path_stats(diseases, mech_only),
        "specific_mechanism_only_evidence_backed": path_stats(
            diseases, [e for e in mech_only if e["target"] not in GENERIC]),
        "disease_disease_links_only": path_stats(diseases, dd),
    }

    lvl = Counter(e["evidence_level"] for e in E)
    ce = [e for e in E if e.get("counter_evidence")]
    ce_by = Counter(e["type"] for e in ce)
    tot_by = Counter(e["type"] for e in E)
    return {
        "nodes": len(nodes), "edges": len(E),
        "components": {"n": len(comp), "giant_nodes": giant, "giant_share": r3(giant / len(nodes)),
                       "diseases_in_giant": giant_dis, "diseases": n,
                       "outside_giant_by_type": dict(outside),
                       "note": "union-find over all edges except the 5 hypothesis edges, direction ignored"},
        "mechanism_links": {
            "rule": "disease -> mechanism via driven_by, or gene participates_in, or variant_group has_effect, using "
                    "only edges whose evidence_level is not inferred or hypothesis; two diseases are linked when they "
                    "reach the same mechanism node; 'specific' excludes loss-of-function, haploinsufficiency, "
                    "gain-of-function and dominant-negative",
            "diseases": n, **shares,
            **{f"share_{k}": r3(v / n) for k, v in shares.items()},
            "disease_pairs": n * (n - 1) // 2, "pairs_sharing_any_mechanism": pair_any,
            "pairs_sharing_specific_mechanism": pair_spec, "pairs_sharing_a_generic_effect": pair_gen,
            "share_pairs_generic": r3(pair_gen / (n * (n - 1) / 2)),
        },
        "mechanism_specificity": sorted(
            [{"mechanism": m, "n_diseases": idx.mech_df[m], "idf": r3(idx.idf[m])} for m in idx.mech_df],
            key=lambda x: (-x["n_diseases"], x["mechanism"])),
        "path_lengths": paths,
        "cross_family": {
            "disease_disease_pairs": len(dd_pairs), "diseases_with_a_disease_neighbour": len(has_nb),
            "cross_family_pairs": len(dd_cross), "cross_family_links": cross_edges,
            "bridging_mechanisms": bridges,
            "bridging_specific_mechanisms": [b["mechanism"] for b in bridges if not b["generic"]],
            "therapies_spanning_families": tclass_cross,
        },
        "edges_by_evidence_level": dict(lvl.most_common()),
        "counter_evidence": {"edges_with_counter_evidence": len(ce), "share": r3(len(ce) / len(E)),
                             "contested_edges": sum(1 for e in E if e["status"] == "contested"),
                             "by_type": {t: f"{ce_by[t]}/{tot_by[t]}" for t in sorted(ce_by, key=lambda t: -ce_by[t])}},
    }


# ====================================================================== benchmark
def tie_metrics(scores, target):
    s = scores[target]
    g = sum(1 for v in scores.values() if v > s + EPS)
    t = sum(1 for v in scores.values() if abs(v - s) <= EPS)
    rank = g + (t + 1) / 2
    rr = sum(1.0 / r for r in range(g + 1, g + t + 1)) / t
    rec = {k: min(max((k - g) / t, 0.0), 1.0) for k in KS}
    return {"rank": rank, "rr": rr, **{f"r@{k}": rec[k] for k in KS}, "n_cand": len(scores), "tied": t}


def build_cases(idx, include_study_only=False):
    cases = []
    for cls in sorted(idx.known):
        kd = idx.known[cls]
        if not (len(kd) >= 2 or idx.targets.get(cls)):
            continue
        for d in sorted(kd):
            dev = any(p.startswith("developed_for:") for p in kd[d])
            if not dev and not include_study_only:
                continue
            context = set(kd) - {d}
            cases.append({"cls": cls, "held_out": d, "context": sorted(context),
                          "source": "developed_for" if dev else "study_only",
                          "hidden": sorted(kd[d])})
    return cases


def run(idx, cases, scorers):
    rows = {s: [] for s in scorers}
    for c in cases:
        cands = [d for d in idx.diseases if d not in set(c["context"])]
        for s in scorers:
            sc = idx.score(s, c["cls"], c["context"], cands)
            sc = {d: round(v, 9) for d, v in sc.items()}
            rows[s].append(tie_metrics(sc, c["held_out"]))
    return rows


def agg(ms):
    if not ms:
        return {}
    return {"n": len(ms), **{f"recall@{k}": statistics.mean(m[f"r@{k}"] for m in ms) for k in KS},
            "mrr": statistics.mean(m["rr"] for m in ms), "median_rank": statistics.median(m["rank"] for m in ms),
            "mean_candidates": statistics.mean(m["n_cand"] for m in ms)}


def boot(cases, rows, scorers, ref="hypotheses-rule"):
    groups = defaultdict(list)
    for i, c in enumerate(cases):
        groups[c["cls"]].append(i)
    keys = sorted(groups)
    rng = random.Random(SEED)
    draws = {s: defaultdict(list) for s in scorers}
    diffs = {s: defaultdict(list) for s in scorers}
    for _ in range(B):
        idxs = [i for k in (rng.choice(keys) for _ in keys) for i in groups[k]]
        ref_a = agg([rows[ref][i] for i in idxs])
        for s in scorers:
            a = agg([rows[s][i] for i in idxs])
            for m in ("recall@1", "recall@3", "recall@5", "mrr", "median_rank"):
                draws[s][m].append(a[m])
                diffs[s][m].append(a[m] - ref_a[m])

    def ci(v):
        v = sorted(v)
        return [r3(v[int(0.025 * len(v))]), r3(v[min(len(v) - 1, int(0.975 * len(v)))])]
    out = {}
    for s in scorers:
        point = agg(rows[s])
        out[s] = {"n": point["n"], "n_therapy_classes": len(keys),
                  **{m: r3(point[m]) for m in ("recall@1", "recall@3", "recall@5", "mrr", "median_rank",
                                                 "mean_candidates")},
                  "ci95": {m: ci(draws[s][m]) for m in draws[s]},
                  f"diff_vs_{ref}_ci95": {m: ci(diffs[s][m]) for m in ("recall@1", "recall@5", "mrr")},
                  f"p_better_than_{ref}_mrr": r3(sum(1 for x in diffs[s]["mrr"] if x > 0) / B)}
    return out


def benchmark(idx, scorers):
    main = build_cases(idx)
    ext = build_cases(idx, include_study_only=True)
    rows_main = run(idx, main, scorers)
    rows_ext = run(idx, ext, scorers)
    subsets = {
        "all_developed_for": (main, rows_main),
        "transfer_context_nonempty": None, "rediscovery_context_empty": None,
        "extended_incl_study_only": (ext, rows_ext),
    }
    for name, pred in (("transfer_context_nonempty", lambda c: bool(c["context"])),
                       ("rediscovery_context_empty", lambda c: not c["context"])):
        ii = [i for i, c in enumerate(main) if pred(c)]
        subsets[name] = ([main[i] for i in ii], {s: [rows_main[s][i] for i in ii] for s in scorers})
    results = {name: boot(cs, rw, scorers) for name, (cs, rw) in subsets.items()}
    per_case = []
    for i, c in enumerate(main):
        per_case.append({"therapy": c["cls"], "held_out": c["held_out"].split(":")[1],
                         "context": [x.split(":")[1] for x in c["context"]],
                         "ranks": {s: rows_main[s][i]["rank"] for s in scorers}})
    return main, ext, results, per_case


# ====================================================================== known-collaboration checks
def case_check(idx, cls, scorers, seed=None, drop_targets=()):
    saved = set(idx.targets.get(cls, set()))
    if drop_targets:
        idx.targets[cls] = saved - set(drop_targets)
    try:
        out = _case_check(idx, cls, scorers, seed)
    finally:
        idx.targets[cls] = saved
    if drop_targets:
        out["ablation_dropped_targets"] = list(drop_targets)
    return out


def _case_check(idx, cls, scorers, seed=None):
    kd = idx.known_diseases(cls)
    out = {"therapy": cls, "known": sorted(d.split(":")[1] for d in kd), "leave_one_out": []}
    for d in sorted(kd):
        ctx = kd - {d}
        cands = [x for x in idx.diseases if x not in ctx]
        r = {}
        for s in scorers:
            sc = {k: round(v, 9) for k, v in idx.score(s, cls, ctx, cands).items()}
            r[s] = tie_metrics(sc, d)["rank"]
        top = idx.rank_candidates(cls, known=ctx, top=3)
        src = "developed_for" if any(p.startswith("developed_for:") for p in idx.known[cls][d]) else "study_only"
        out["leave_one_out"].append({"held_out": d.split(":")[1], "source": src, "n_candidates": len(cands),
                                     "rank": r, "recommended_top3": [t[0].split(":")[1] for t in top],
                                     "why": idx.explain(cls, ctx, d)})
    if seed:
        ctx = {seed}
        ranked = idx.rank_candidates(cls, known=ctx)
        pos = {d: i + 1 for i, (d, _s, _e) in enumerate(ranked)}
        out["seed_only"] = {"seed": seed.split(":")[1], "n_candidates": len(ranked),
                            "ranks_of_other_known": {d.split(":")[1]: pos[d] for d in sorted(kd - ctx)},
                            "top5": [d.split(":")[1] for d, _s, _e in ranked[:5]]}
    ranked = idx.rank_candidates(cls, top=5)
    out["prospective_top5_given_all_known"] = [
        {"disease": d.split(":")[1], "score": s, "mechanisms": [m["mechanism"] for m in e["mechanisms"]],
         "clusters": e["clusters"], "nearest_known": (e["nearest_known_by_phenotype"] or ":").split(":")[1]}
        for d, s, e in ranked]
    return out


# ====================================================================== agreement metrics
def djb2(s):
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def external_mechanism_agreement(idx):
    """Atlas driven_by effect classes vs G2P / ClinGen dosage classes in data/derived/global/mechanism."""
    mdir = ROOT / "data" / "derived" / "global" / "mechanism"
    if not mdir.exists():
        return {"available": False}
    shards = {}
    rows = []
    for d in idx.diseases:
        n = idx.nodes[d]
        gene = d.split(":")[1]
        ids = set()
        x = (n.get("xrefs") or {}).get("MONDO")
        ids |= set([x] if isinstance(x, str) else (x or []))
        for st in (n.get("attrs") or {}).get("subtypes") or []:
            if st.get("MONDO"):
                ids |= set([st["MONDO"]] if isinstance(st["MONDO"], str) else st["MONDO"])
        ext = set()
        srcs = set()
        for mid in ids:
            b = djb2(mid) % 64
            if b not in shards:
                shards[b] = json.loads((mdir / f"{b}.json").read_text())
            rec = shards[b]["d"].get(mid) or {}
            for m in rec.get("mechanisms", []):
                if m.get("class") and m.get("gene") == gene:
                    ext.add(m["class"])
                    srcs.add(m["source"])
        atlas = {m for m in idx.driven[d] if m in GENERIC}
        # lenient: also effects reached through variant groups (vg -has_effect->), any non-hypothesis level
        atlas_all = {m for m, chs in idx.chains[d].items()
                     if idx.nodes[m].get("attrs", {}).get("kind") == "effect"
                     and any(k in ("driven_by", "variant_group") for k, _ in chs)}
        rows.append({"disease": gene, "external": sorted(ext), "atlas": sorted(atlas),
                     "atlas_incl_variant_groups": sorted(atlas_all), "sources": sorted(srcs)})
    lof = {"mech:loss-of-function", "mech:haploinsufficiency", "mech:lysosomal-enzyme-deficiency"}

    def lenient(s):
        return {"mech:loss-of-function" if m in lof else m for m in s}
    withext = [r for r in rows if r["external"]]
    strict = [r for r in withext if set(r["external"]) & set(r["atlas"])]
    len_ok = [r for r in withext if lenient(r["external"]) & lenient(r["atlas_incl_variant_groups"])]
    missed = [r for r in withext if not lenient(r["external"]) & lenient(r["atlas_incl_variant_groups"])]
    return {"available": True,
            "rule": "for each atlas disease, the G2P / ClinGen-dosage mechanism classes recorded for its MONDO ids "
                    "(same gene only) vs the atlas: 'strict' = exact class on a driven_by edge; 'lenient' = also "
                    "effects reached via variant groups, with haploinsufficiency and lysosomal enzyme deficiency "
                    "counted as loss of function",
            "diseases_with_external_class": len(withext), "diseases": len(rows),
            "agree_strict": len(strict), "agree_lenient": len(len_ok),
            "share_agree_strict": r3(len(strict) / len(withext)) if withext else None,
            "share_agree_lenient": r3(len(len_ok) / len(withext)) if withext else None,
            "disagree_lenient": [{"disease": r["disease"], "external": r["external"],
                                  "atlas": r["atlas_incl_variant_groups"]} for r in missed]}


def claude_cross_check(rep, grab):
    """Same numbers for the independent Claude reading (READER=claude), when it has been run."""
    path = ROOT / "docs" / "agent-reports" / "claude-extraction.md"
    if not path.exists():
        return {}
    cl = path.read_text()
    agree, both = grab(r"\*\*Agreement\*\* on \(edge, PMID\) pairs both extractors cite \| \*\*(\d+)/(\d+)", cl)
    refound, curated = grab(r"Curated \(edge, PMID\) pairs for these abstracts re-found independently \| (\d+)/(\d+)", cl)
    abstracts, = grab(r"Abstracts processed \| \*\*(\d+)\*\*", cl)
    by_type = {}
    for m in re.finditer(r"^\| `(\w+)` \| (\d+) \| (\d+) \| (\d+) \|", cl, re.M):
        t, n, a, dis = m.group(1), *map(int, m.groups()[1:])
        if n:
            by_type[t] = {"pairs": n, "agree": a, "share": r3(a / n)}
    reread, = grab(r"Claude cross-check: (\d+) cited sources re-read", rep)
    disagree_rep, = grab(r"Cited sources where the Claude reading disagrees with the curators: (\d+)", rep)
    return {"claude_cross_check": {
        "agree": agree, "pairs_both_cite": both, "share": r3(agree / both) if both else None,
        "curated_pairs_refound": refound, "curated_pairs": curated, "share_refound": r3(refound / curated) if curated else None,
        "abstracts": abstracts, "by_edge_type": by_type,
        "sources_reread_in_build": reread, "sources_disagreeing_in_build": disagree_rep,
        "scope": "DEE, lysosomal, RASopathy and cross-family abstracts cited by the graph; Claude agent reading, "
                 "blind to the curated graph, same instructions and schema as the OpenAI reader; abstracts only",
        "sources": ["docs/agent-reports/claude-extraction.md", "data/build/report.md"]}}


def agreement(idx):
    rep = (ROOT / "data" / "build" / "report.md").read_text()
    oa = (ROOT / "docs" / "agent-reports" / "openai-extraction.md").read_text()

    def grab(pat, text, cast=int):
        m = re.search(pat, text)
        if not m:
            raise SystemExit(f"agreement: pattern not found: {pat}")
        return [cast(x) for x in m.groups()]
    agree, both = grab(r"\*\*Agreement\*\* on \(edge, PMID\) pairs both extractors cite \| \*\*(\d+)/(\d+)", oa)
    refound, curated = grab(r"Curated \(edge, PMID\) pairs for these abstracts re-found independently \| (\d+)/(\d+)", oa)
    abstracts, = grab(r"Abstracts processed \| \*\*(\d+)\*\*", oa)
    by_type = {}
    for m in re.finditer(r"^\| `(\w+)` \| (\d+) \| (\d+) \| (\d+) \|", oa, re.M):
        t, n, a, dis = m.group(1), *map(int, m.groups()[1:])
        if n:
            by_type[t] = {"pairs": n, "agree": a, "share": r3(a / n)}
    reread, = grab(r"OpenAI cross-check: (\d+) cited sources re-read", rep)
    disagree_rep, = grab(r"Cited sources where the OpenAI reading disagrees with the curators: (\d+)", rep)
    q_ok, q_tot = grab(r"quotes string-verified against the stored source: \*\*(\d+)/(\d+)\*\*", rep)
    return {
        "openai_cross_check": {
            "agree": agree, "pairs_both_cite": both, "share": r3(agree / both),
            "curated_pairs_refound": refound, "curated_pairs": curated, "share_refound": r3(refound / curated),
            "abstracts": abstracts, "by_edge_type": by_type,
            "sources_reread_in_build": reread, "sources_disagreeing_in_build": disagree_rep,
            "scope": "SNARE slice only (biology 62/62 abstracts + community 16); model gpt-6-astra; one model, abstracts only",
            "sources": ["docs/agent-reports/openai-extraction.md", "data/build/report.md"]},
        **claude_cross_check(rep, grab),
        "quote_verification": {"verified": q_ok, "with_quote": q_tot, "source": "data/build/report.md"},
        "dismech": {
            "atlas_umbrellas_linked_by_mondo": 32, "atlas_umbrellas": 45, "mondo_links": 72,
            "deep_compared": ["STXBP1", "SCN1A (Dravet)", "SNAP25"],
            "primary_mechanism_class_agrees": "3/3",
            "disagreements": ["PMID:25381298: atlas files it on vg:SNAP25:missense -> loss-of-function "
                              "(OpenAI-extracted, unverified); DisMech reads it as dominant-negative",
                              "Dravet gene scope: DisMech lists STXBP1 among Dravet genes; the atlas has no STXBP1-Dravet link"],
            "note": "qualitative, 3 diseases; not a rate",
            "source": "docs/agent-reports/dismech.md"},
        "g2p_clingen_mechanism_class": external_mechanism_agreement(idx),
    }


# ====================================================================== main
def table(res, scorers):
    lines = ["| scorer | n | R@1 | R@3 | R@5 | MRR | median rank |", "|---|---|---|---|---|---|---|"]
    for s in scorers:
        x = res[s]
        c = x["ci95"]
        f = lambda m: f"{x[m]:.2f} [{c[m][0]:.2f}-{c[m][1]:.2f}]"
        lines.append(f"| {s} | {x['n']} | {f('recall@1')} | {f('recall@3')} | {f('recall@5')} | {f('mrr')} | "
                     f"{x['median_rank']:g} [{c['median_rank'][0]:g}-{c['median_rank'][1]:g}] |")
    return "\n".join(lines)


def main():
    g = load_graph()
    fam = families({n["id"]: n for n in g["nodes"]})
    # published benchmark: curated + AI-reviewed links (labelled); EVAL_CURATED_ONLY=1 for curated links only
    curated_only = os.environ.get("EVAL_CURATED_ONLY") == "1"
    idx = TransferIndex(g, family=fam, include_ai_reviewed=not curated_only)
    scorers = [s for s, _l, _x in SCORERS]
    conn = connectivity(g, idx, fam)
    main_cases, ext_cases, results, per_case = benchmark(idx, scorers)

    # node-level sensitivity: no therapy equivalence classes
    idx_node = TransferIndex(g, classes={}, family=fam, include_ai_reviewed=not curated_only)
    # the same benchmark on curated links only, shown next to the published figure
    idx_cur = TransferIndex(g, family=fam, include_ai_reviewed=False)
    cur_main, _ce, res_cur, _pc = benchmark(idx_cur, [RECOMMENDED, "random", "hypotheses-rule"])
    _m, _e, res_node, _p = benchmark(idx_node, scorers)

    # combination-weight sensitivity (post hoc; NOT used to pick the method)
    sens = {}
    for a in (0.25, 0.5, 0.75):
        ms = []
        for c in main_cases:
            cands = [d for d in idx.diseases if d not in set(c["context"])]
            ph = idx.score("phenotype", c["cls"], c["context"], cands)
            mc = idx.score("mech+cluster", c["cls"], c["context"], cands)
            mp, mm = max(ph.values()), max(mc.values())
            sc = {d: round(a * (ph[d] / mp if mp else 0) + (1 - a) * (mc[d] / mm if mm else 0), 9) for d in cands}
            ms.append(tie_metrics(sc, c["held_out"]))
        x = agg(ms)
        sens[f"phenotype_weight_{a}"] = {k: r3(v) for k, v in x.items()}

    checks = {
        "4-phenylbutyrate (STXBP1 <-> SLC6A1)": case_check(idx, "therapy:4-phenylbutyrate", scorers),
        "4-phenylbutyrate, ablation: without its SLC6A1-specific target (GABA reuptake)": case_check(
            idx, "therapy:4-phenylbutyrate", scorers, drop_targets=["mech:gaba-reuptake"]),
        "MEK inhibitors across RASopathies": case_check(idx, "class:mek-inhibitors", scorers, seed="disease:NF1"),
        "miglustat across lysosomal diseases": case_check(idx, "therapy:miglustat", scorers, seed="disease:GBA1"),
    }

    labels = {s: {"label": l, "brief_letter": x} for s, l, x in SCORERS}

    # candidate-set size of the rules (how many diseases tie at the top / score > 0) and naive recovery
    cand_sizes = {}
    for s in ("naive-driven_by", "hypotheses-rule", RECOMMENDED):
        pos, top_ties, rec = [], [], 0
        for c in main_cases:
            cands = [d for d in idx.diseases if d not in set(c["context"])]
            sc = idx.score(s, c["cls"], c["context"], cands)
            pos.append(sum(1 for v in sc.values() if v > EPS))
            mx = max(sc.values())
            top_ties.append(sum(1 for v in sc.values() if abs(v - mx) <= EPS) if mx > EPS else len(sc))
            rec += sc[c["held_out"]] > EPS
        cand_sizes[s] = {"held_out_scored_above_zero": rec, "n": len(main_cases),
                         "diseases_scored_above_zero_median": statistics.median(pos), "max": max(pos),
                         "tied_at_top_median": statistics.median(top_ties), "tied_at_top_max": max(top_ties)}

    by_family = {}
    for s in (RECOMMENDED, "hypotheses-rule", "same-family", "phenotype", "mechanism"):
        grp = defaultdict(list)
        for i, c in enumerate(main_cases):
            m = run(idx, [c], [s])[s][0]
            grp[fam[c["held_out"]]].append(m)
        by_family[s] = {f: {"n": len(v), "mrr": r3(statistics.mean(x["rr"] for x in v)),
                            "recall@5": r3(statistics.mean(x["r@5"] for x in v))} for f, v in sorted(grp.items())}
    out = {
        "generated_by": "pipeline/eval/transfer_eval.py",
        "graph": {"version": g["meta"].get("version"), "generated_at": g["meta"].get("generated_at"),
                  "nodes": len(g["nodes"]), "edges": len(g["edges"])},
        "question": "How well is the graph connected, and how accurately can it identify how progress on one "
                    "disease could help another?",
        "connectivity": conn,
        "transfer_benchmark": {
            "design": {
                "unit": "therapy class x disease; classes: " + "; ".join(f"{k} = {', '.join(v)}" for k, v in EQUIVALENCE.items()),
                "positives": "developed_for edges (test cases); study -tests-> therapy + study -studies-> disease pairs "
                             "are context and, in the extended set, test cases too",
                "inclusion": "therapy class linked to >= 2 diseases or with >= 1 targets edge",
                "hidden_per_case": "the held-out developed_for edge(s) of the whole class and every study edge linking "
                                   "the class to the held-out disease",
                "candidates": "all 45 diseases minus the class's other known diseases (filtered ranking)",
                "ties": "expected value under random tie-break (rank = better + (tied+1)/2)",
                "ci": f"95% percentile bootstrap over therapy classes, {B} draws, seed {SEED}",
                "weights_fixed_before_running": "chain weights 1.0/0.8/0.7; IDF ln((N+1)/(df+1)); combination = "
                                                "phenotype/max + (mechanism+cluster)/max, equal weight",
                "n_cases_main": len(main_cases), "n_cases_extended": len(ext_cases),
                "n_therapy_classes": len({c["cls"] for c in main_cases}),
                "n_cases_with_context": sum(1 for c in main_cases if c["context"]),
            },
            "scorers": labels,
            "results": results,
            "node_level_sensitivity": {s: {k: res_node["all_developed_for"][s][k]
                                           for k in ("n", "recall@1", "recall@5", "mrr", "median_rank")}
                                       for s in scorers},
            "combination_weight_sensitivity_post_hoc": sens,
            "recommended_scorer": RECOMMENDED,
            "links": {"includes_ai_reviewed": idx.include_ai_reviewed, "ai_reviewed_links": idx.n_ai_reviewed,
                      "note": "AI-reviewed = proposed by an independent Claude reading and accepted by an AI review, not "
                              "by a human expert (data/curated/claude_reviewed.json)"},
            "curated_only": {"n_cases": len(cur_main),
                             **{s: {k: (r3(v) if isinstance(v, (int, float)) else v) for k, v in res_cur["all_developed_for"][s].items()} for s in (RECOMMENDED, "random")}},
            "candidate_set_sizes": cand_sizes,
            "by_family_of_held_out": by_family,
            "per_case_ranks": per_case,
        },
        "known_collaboration_checks": checks,
        "agreement": agreement(idx),
    }
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    for name in ("all_developed_for", "transfer_context_nonempty", "rediscovery_context_empty",
                 "extended_incl_study_only"):
        print(f"\n## {name}\n" + table(results[name], scorers))
    print("\n## node-level (no classes), all_developed_for\n" + table(res_node["all_developed_for"], scorers))
    print("\nsensitivity", json.dumps(sens))


if __name__ == "__main__":
    main()
