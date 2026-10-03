"""HPO phenotypes, information content (IC) and phenotype similarity for the RASopathy family.
Same method as pipeline/biology/hpo.py (whose parsers are reused):
  IC(t) = -ln(n diseases annotated to t or a descendant / n diseases) over ALL of phenotype.hpoa
  (aspect P, NOT rows dropped, obsolete/alt ids remapped, is_a propagation).
Profile entities per gene-defined umbrella = the GERMLINE Mendelian entities listed in
ras_subtypes.GERMLINE_OMIM (all taken from Monarch OMIM causal edges; somatic cancers and
mosaic/somatic entities are excluded) + gene-specific Orphanet entities (1 associated gene,
"Disease-causing germline").
Similarity: Resnik best-match-average with a per-disease background of 3,000 random non-slice
diseases (seed 20261003); an edge needs >= 99.9th percentile for both (the family is homogeneous).

Run:  python3 pipeline/families/rasopathy/hpo.py
Out:  data/raw/families/rasopathy/hpo_fragment.json, hpo_stats.json
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from ras_common import FAMILY, GENES, RAW, TODAY, edge_id, existing_graph_ids, load_bio, read_json, write_json
from ras_subtypes import GERMLINE_OMIM, orpha_gene_specific

H = load_bio("hpo")
DISTINCTIVE_IC, BROAD_IC = H.DISTINCTIVE_IC, H.BROAD_IC
# The RASopathies are phenotypically homogeneous by design (62 of 66 pairs pass the biology layer's
# 95th/99th-percentile rule), so this family requires the top 0.1% of BOTH background distributions.
TOP_K, MAX_PER_DISEASE, BACKGROUND_N, PCTL, PCTL_STRICT = 12, 20, 3000, 0.999, 0.999
# broad RASopathy hallmarks kept when directly annotated, so broad vs distinctive contrast stays visible
HALLMARKS = ["HP:0004322", "HP:0001639", "HP:0001642", "HP:0001249", "HP:0000957", "HP:0000465"]


def main():
    terms, alt_map, obo_version = H.parse_obo()
    anc = H.ancestors_fn(terms)
    rows, hpoa_version = H.parse_hpoa(alt_map, terms)
    direct, names = defaultdict(set), {}
    for r in rows:
        if r["aspect"] == "P" and r["qualifier"] != "NOT":
            direct[r["database_id"]].add(r["hpo_id"])
            names[r["database_id"]] = r["disease_name"]
    propagated = {d: frozenset().union(*(anc(t) for t in ts)) for d, ts in direct.items()}
    n_total = len(direct)
    counts = defaultdict(int)
    for ps in propagated.values():
        for t in ps:
            counts[t] += 1
    ic = {t: -math.log(c / n_total) for t, c in counts.items()}
    print(f"hp.obo {obo_version}; phenotype.hpoa {hpoa_version}; IC over {n_total} diseases")

    dis = read_json(RAW / "diseases.json")
    profiles = {}
    for sym in GENES:
        ents = [f"OMIM:{m}" for m in GERMLINE_OMIM[sym]] + [f"ORPHA:{c}" for c in orpha_gene_specific(dis[sym])]
        ents = sorted(set(ents))
        profiles[sym] = {"entities": ents, "annotated_entities": [e for e in ents if e in direct],
                         "missing_in_hpoa": [e for e in ents if e not in direct]}
        print(f"  {sym}: {profiles[sym]['annotated_entities']} (no HPO: {profiles[sym]['missing_in_hpoa']})")

    slice_terms = {}
    for sym, p in profiles.items():
        tt = {}
        for r in rows:
            if r["database_id"] not in p["annotated_entities"] or r["aspect"] != "P" or r["qualifier"] == "NOT":
                continue
            t = tt.setdefault(r["hpo_id"], {"refs": set(), "freq": set(), "evidence": set(), "entities": set()})
            t["refs"].update(x.strip() for x in r["reference"].split(";") if x.strip())
            if r["frequency"]:
                t["freq"].add(r["frequency"])
            t["evidence"].add(r["evidence"])
            t["entities"].add(r["database_id"])
        slice_terms[sym] = tt
    syms = [s for s in GENES if slice_terms[s]]

    anc_sorted = {}

    def best_match(t, other):
        if t not in anc_sorted:
            anc_sorted[t] = sorted(anc(t), key=lambda x: -ic.get(x, 0.0))
        for c in anc_sorted[t]:
            if c in other:
                return c, ic.get(c, 0.0)
        return None, 0.0

    def bma(ta, pa, tb, pb, detail=False):
        ab = [best_match(t, pb) for t in ta]
        ba = [best_match(t, pa) for t in tb]
        s = 0.5 * (sum(x[1] for x in ab) / len(ab) + sum(x[1] for x in ba) / len(ba))
        return (s, ab, ba) if detail else s

    sl_direct = {s: sorted(slice_terms[s]) for s in syms}
    sl_prop = {s: frozenset().union(*(anc(t) for t in sl_direct[s])) for s in syms}
    slice_ents = {e for p in profiles.values() for e in p["entities"]}
    bg = random.Random(20261003).sample(sorted(d for d in direct if d not in slice_ents), BACKGROUND_N)
    background = {}
    for s in syms:
        vals = sorted(bma(sl_direct[s], sl_prop[s], sorted(direct[d]), propagated[d]) for d in bg)
        background[s] = {"p50": vals[len(vals) // 2], "p95": vals[int(PCTL * len(vals))],
                         "p99": vals[int(PCTL_STRICT * len(vals))], "values": vals}

    def pct(s, v):
        vals = background[s]["values"]
        return sum(1 for x in vals if x < v) / len(vals)

    pairs = []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            s, ab, ba = bma(sl_direct[a], sl_prop[a], sl_direct[b], sl_prop[b], detail=True)
            inter, union = sl_prop[a] & sl_prop[b], sl_prop[a] | sl_prop[b]
            jac = sum(ic.get(t, 0) for t in inter) / max(1e-9, sum(ic.get(t, 0) for t in union))
            pairs.append({"a": a, "b": b, "bma": s, "ic_jaccard": jac, "pct_a": pct(a, s), "pct_b": pct(b, s),
                          "exact_shared": sorted(set(sl_direct[a]) & set(sl_direct[b]), key=lambda t: -ic.get(t, 0)),
                          "mica": sorted({c for _, (c, _) in zip(sl_direct[a], ab) if c} |
                                         {c for _, (c, _) in zip(sl_direct[b], ba) if c},
                                         key=lambda c: -ic.get(c, 0))})
    pairs.sort(key=lambda p: -p["bma"])

    def is_edge(p):
        return min(p["pct_a"], p["pct_b"]) >= PCTL and max(p["pct_a"], p["pct_b"]) >= PCTL_STRICT

    shared_any = defaultdict(set)
    for p in pairs:
        if is_edge(p):
            for t in p["exact_shared"][:4]:
                shared_any[p["a"]].add(t)
                shared_any[p["b"]].add(t)
    selected = {}
    for s in syms:
        top = []
        for t in sorted(slice_terms[s], key=lambda t: -ic.get(t, 0)):
            if len(top) >= TOP_K:
                break
            if any(t in anc(u) or u in anc(t) for u in top):
                continue
            top.append(t)
        keep = list(dict.fromkeys(top + sorted(shared_any[s], key=lambda t: -ic.get(t, 0))))
        for hall in HALLMARKS:
            if hall in slice_terms[s] and hall not in keep:
                keep.append(hall)
        selected[s] = keep[:MAX_PER_DISEASE]

    existing = existing_graph_ids()
    nodes, edges = {}, []

    def ref_url(ref):
        if ref.startswith("PMID:"):
            return f"https://pubmed.ncbi.nlm.nih.gov/{ref.split(':')[1]}/"
        if ref.startswith("OMIM:"):
            return f"https://omim.org/entry/{ref.split(':')[1]}"
        if ref.startswith("ORPHA:"):
            return f"https://www.orpha.net/en/disease/detail/{ref.split(':')[1]}"
        return "https://hpo.jax.org/"

    def spec(t):
        v = ic.get(t, 0)
        return "distinctive" if v >= DISTINCTIVE_IC else "broad" if v < BROAD_IC else "intermediate"

    def ensure_pheno(t):
        pid = f"phenotype:{t}"
        if pid not in existing and pid not in nodes:   # reuse existing phenotype nodes, never duplicate
            nodes[pid] = {"id": pid, "type": "phenotype", "label": terms[t]["name"], "xrefs": {"HPO": t},
                          "attrs": {"ic": round(ic.get(t, 0.0), 3), "n_diseases": counts.get(t, 0),
                                    "n_total_diseases": n_total, "specificity": spec(t)},
                          "sources": [{"source": "HPO", "ref": t, "url": f"https://hpo.jax.org/browse/term/{t}",
                                       "title": terms[t]["name"], "kind": "database",
                                       "study_type": "database_record", "extracted_by": "database",
                                       "retrieved": TODAY}]}
        return pid

    for s in syms:
        for t in selected[s]:
            info = slice_terms[s][t]
            pid = ensure_pheno(t)
            refs = sorted(info["refs"], key=lambda r: (not r.startswith("PMID:"), r))
            ev = [{"source": "HPO", "ref": r, "url": ref_url(r),
                   "title": f"phenotype.hpoa ({hpoa_version}) annotation: {terms[t]['name']} ({t}) in "
                            f"{', '.join(sorted(info['entities']))}",
                   "kind": "database", "study_type": "database_record", "extracted_by": "database",
                   "retrieved": TODAY} for r in refs[:3]]
            freq = sorted(info["freq"])
            attrs = {"hpo_evidence_codes": sorted(info["evidence"]), "entities": sorted(info["entities"]),
                     "ic": round(ic.get(t, 0.0), 3), "specificity": spec(t)}
            if freq:
                lab = [H.FREQ_LABELS.get(f, f) for f in freq]
                attrs["frequency"] = freq if len(freq) > 1 else freq[0]
                attrs["frequency_label"] = lab if len(lab) > 1 else lab[0]
            edges.append({"id": edge_id(f"disease:{s}", "has_phenotype", pid), "source": f"disease:{s}",
                          "target": pid, "type": "has_phenotype", "label": "has phenotype",
                          "explanation": (f"HPO annotates {terms[t]['name']} to {', '.join(sorted(info['entities']))} "
                                          f"({s}-related disorders). This feature is {spec(t)} (IC {ic.get(t, 0):.2f}; "
                                          f"seen in {counts.get(t, 0)} of {n_total} annotated diseases)."),
                          "evidence_level": "curated", "status": "supported",
                          "confidence": 0.9 if any(r.startswith("PMID:") for r in refs) else 0.8,
                          "evidence": ev, "attrs": attrs})

    sim = []
    for p in pairs:
        if not is_edge(p):
            continue
        a, b = p["a"], p["b"]
        ex = p["exact_shared"]
        distinctive = [t for t in ex if ic.get(t, 0) >= DISTINCTIVE_IC]
        broad = [t for t in ex if ic.get(t, 0) < BROAD_IC]
        inter = [t for t in ex if BROAD_IC <= ic.get(t, 0) < DISTINCTIVE_IC]

        def fmt(ts):
            return ", ".join(f"{terms[t]['name']} (IC {ic.get(t, 0):.1f})" for t in ts) or "none"
        lo, hi = sorted([p["pct_a"], p["pct_b"]])
        sim.append({"id": edge_id(f"disease:{a}", "similar_phenotype", f"disease:{b}"),
                    "source": f"disease:{a}", "target": f"disease:{b}", "type": "similar_phenotype",
                    "label": "similar symptom profile",
                    "explanation": (f"{a}- and {b}-related disorders have more similar HPO phenotype profiles than "
                                    f"{int(lo * 100)}-{int(hi * 100)}% of background disease comparisons (Resnik BMA "
                                    f"{p['bma']:.2f}). Shared DISTINCTIVE features: {fmt(distinctive[:6])}. "
                                    f"Shared BROAD features: {fmt(broad[:4])}."),
                    "evidence_level": "inferred", "status": "supported",
                    "confidence": round(0.3 + 0.19 * min(1.0, (lo - PCTL) / (1 - PCTL)), 2),
                    "evidence": [{"source": "Atlas", "ref": "pipeline/families/rasopathy/hpo.py",
                                  "url": "https://github.com/obophenotype/human-phenotype-ontology/releases",
                                  "title": f"Resnik best-match-average over phenotype.hpoa {hpoa_version} / hp.obo "
                                           f"{obo_version}; IC over {n_total} diseases",
                                  "kind": "computed", "extracted_by": "computed", "retrieved": TODAY}],
                    "attrs": {"resnik_bma": round(p["bma"], 3), "ic_weighted_jaccard": round(p["ic_jaccard"], 3),
                              "background_percentile": {a: round(p["pct_a"], 4), b: round(p["pct_b"], 4)},
                              "shared_distinctive": distinctive, "shared_intermediate": inter, "shared_broad": broad,
                              "method": "Resnik BMA; edge if >= 99.9th percentile of both diseases' backgrounds (family-specific, stricter than the biology layer)",
                              "family": FAMILY}})
    write_json(RAW / "hpo_fragment.json", {"nodes": sorted(nodes.values(), key=lambda n: n["id"]),
                                           "edges": edges + sim})
    write_json(RAW / "hpo_stats.json", {
        "hpoa_version": hpoa_version, "hpo_version": obo_version, "n_total_diseases": n_total,
        "profiles": profiles, "terms_per_disease": {s: len(slice_terms[s]) for s in syms},
        "selected_per_disease": {s: len(selected[s]) for s in syms},
        "background": {s: {k: v for k, v in background[s].items() if k != "values"} for s in syms},
        "pairs": [{k: v for k, v in p.items() if k != "mica"} for p in pairs]})
    print(f"new phenotype nodes={len(nodes)} has_phenotype={len(edges)} similar_phenotype={len(sim)}")
    for s in syms:
        print(f"  {s}: {len(slice_terms[s])} terms, kept {len(selected[s])}")
    for p in pairs[:25]:
        print(f"  {'EDGE' if is_edge(p) else '    '} {p['a']:7s}-{p['b']:7s} BMA={p['bma']:.2f} "
              f"pct=({p['pct_a']:.3f},{p['pct_b']:.3f}) shared={len(p['exact_shared'])}")


if __name__ == "__main__":
    main()
