"""HPO phenotypes, information content and phenotype similarity for the lysosomal family.

Same method as pipeline/biology/hpo.py (whose parsing code is reused), extended with a
CROSS-FAMILY comparison against the SNAREopathy profiles recorded in data/raw/biology/hpo_stats.json.

(a) Profile entities per gene-defined umbrella = every OMIM entity with an OMIM `causes` edge (Monarch)
    + every Orphanet entity that is "Disease-causing" AND gene-specific (exactly one associated gene).
    Susceptibility links (GBA1 -> Parkinson disease / Lewy body dementia, `contributes_to`) are excluded.
(b) IC(t) = -ln(n diseases annotated to t or a descendant / n diseases), over ALL diseases in
    phenotype.hpoa (aspect P, NOT rows dropped, is_a propagation).
(c) Per disease keep the 12 most informative non-redundant terms + terms shared with similarity
    partners + lysosomal hallmark terms when directly annotated; cap 20.
(d) Resnik best-match-average; edge if >= 95th percentile of BOTH diseases' backgrounds and >= 99th for
    one (background = 3000 random non-family diseases, seed 20261003, as in the biology layer).
Run:  python3 pipeline/families/lysosomal/hpo.py
Out:  data/raw/families/lysosomal/hpo_fragment.json, hpo_stats.json
"""
from __future__ import annotations

import importlib.util
import math
import random
from collections import defaultdict

from lyso_common import GRAPH, RAW, ROOT, TODAY, edge_id, read_json, write_json

_spec = importlib.util.spec_from_file_location("bio_hpo", ROOT / "pipeline" / "biology" / "hpo.py")
# biology/hpo.py imports `common` from its own directory; make that importable for the reuse
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "pipeline" / "biology"))
bio_hpo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bio_hpo)  # type: ignore[union-attr]
sys.path.pop(0)

parse_obo, parse_hpoa, ancestors_fn = bio_hpo.parse_obo, bio_hpo.parse_hpoa, bio_hpo.ancestors_fn
DISTINCTIVE_IC, BROAD_IC = bio_hpo.DISTINCTIVE_IC, bio_hpo.BROAD_IC
FREQ_LABELS = bio_hpo.FREQ_LABELS
TOP_K, MAX_PER_DISEASE, BACKGROUND_N = 12, 20, 3000
PCTL, PCTL_STRICT = 0.95, 0.99
# lysosomal hallmarks kept when directly annotated, so broad-vs-distinctive contrast stays visible
HALLMARKS = ["HP:0001433", "HP:0001744", "HP:0001250", "HP:0002376", "HP:0001249", "HP:0001263",
             "HP:0001252", "HP:0002240"]


def main() -> None:
    terms, alt_map, obo_version = parse_obo()
    anc = ancestors_fn(terms)
    rows, hpoa_version = parse_hpoa(alt_map, terms)
    direct = defaultdict(set)
    for r in rows:
        if r["aspect"] == "P" and r["qualifier"] != "NOT":
            direct[r["database_id"]].add(r["hpo_id"])
    propagated = {d: frozenset().union(*(anc(t) for t in ts)) for d, ts in direct.items()}
    n_total = len(direct)
    counts = defaultdict(int)
    for ps in propagated.values():
        for t in ps:
            counts[t] += 1
    ic = {t: -math.log(c / n_total) for t, c in counts.items()}
    print(f"hp.obo {obo_version}; phenotype.hpoa {hpoa_version}; IC over {n_total} diseases")

    # ---- (a) family profiles
    dis = read_json(RAW / "diseases.json")
    profiles = {}
    for sym, d in dis.items():
        ents = []
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                oo = m.get("original_object") or ""
                if m["primary_knowledge_source"] == "infores:omim" and m["predicate"] == "biolink:causes" \
                        and oo.startswith("OMIM:"):
                    ents.append(oo)
        for code, a in d.get("orphanet_associations", {}).items():
            if a.get("causal") and a.get("n_genes_associated") == 1:
                ents.append(f"ORPHA:{code}")
        ents = sorted(set(ents))
        profiles[sym] = {"entities": ents, "annotated_entities": [e for e in ents if e in direct],
                         "missing_in_hpoa": [e for e in ents if e not in direct], "family": "lysosomal"}
    # SNAREopathy profiles exactly as the biology layer defined them (read-only)
    snare = read_json(ROOT / "data" / "raw" / "biology" / "hpo_stats.json")["profiles"]
    for sym, p in snare.items():
        profiles[sym] = {"entities": p["entities"], "annotated_entities": p["annotated_entities"],
                         "missing_in_hpoa": p["missing_in_hpoa"], "family": "snareopathy"}

    slice_terms = {}
    for sym, p in profiles.items():
        tt = {}
        for r in rows:
            if r["database_id"] not in p["annotated_entities"] or r["aspect"] != "P" or r["qualifier"] == "NOT":
                continue
            t = tt.setdefault(r["hpo_id"], {"refs": set(), "freq": set(), "evidence": set(), "entities": set()})
            for ref in r["reference"].split(";"):
                if ref.strip():
                    t["refs"].add(ref.strip())
            if r["frequency"]:
                t["freq"].add(r["frequency"])
            t["evidence"].add(r["evidence"])
            t["entities"].add(r["database_id"])
        slice_terms[sym] = tt
    fam = [s for s in profiles if profiles[s]["family"] == "lysosomal" and slice_terms[s]]
    other = [s for s in profiles if profiles[s]["family"] == "snareopathy" and slice_terms[s]]
    for s in fam:
        print(f"  {s}: entities {profiles[s]['annotated_entities']} -> {len(slice_terms[s])} direct terms")

    # ---- (d) Resnik BMA
    anc_sorted = {}

    def anc_by_ic(t):
        if t not in anc_sorted:
            anc_sorted[t] = sorted(anc(t), key=lambda x: -ic.get(x, 0.0))
        return anc_sorted[t]

    def best_match(t, other_prop):
        for c in anc_by_ic(t):
            if c in other_prop:
                return c, ic.get(c, 0.0)
        return None, 0.0

    def bma(ta, pa, tb, pb, detail=False):
        ab = [best_match(t, pb) for t in ta]
        ba = [best_match(t, pa) for t in tb]
        s = 0.5 * (sum(x[1] for x in ab) / len(ab) + sum(x[1] for x in ba) / len(ba))
        return (s, list(zip(ta, ab)), list(zip(tb, ba))) if detail else s

    allsyms = fam + other
    sl_direct = {s: sorted(slice_terms[s]) for s in allsyms}
    sl_prop = {s: frozenset().union(*(anc(t) for t in sl_direct[s])) for s in allsyms}
    fam_entities = {e for s in fam for e in profiles[s]["entities"]}
    snare_entities = {e for s in other for e in profiles[s]["entities"]}
    background = {}
    for group, excl in ((fam, fam_entities), (other, snare_entities)):
        pool = sorted(d for d in direct if d not in excl)
        bg = random.Random(20261003).sample(pool, min(BACKGROUND_N, len(pool)))
        for s in group:
            vals = sorted(bma(sl_direct[s], sl_prop[s], sorted(direct[d]), propagated[d]) for d in bg)
            background[s] = {"p50": vals[len(vals) // 2], "p95": vals[int(PCTL * len(vals))],
                             "p99": vals[int(0.99 * len(vals))], "values": vals}

    def pct_rank(s, v):
        vals = background[s]["values"]
        return sum(1 for x in vals if x < v) / len(vals)

    pairs = []
    cand = [(a, b) for i, a in enumerate(fam) for b in fam[i + 1:]] + [(a, b) for a in fam for b in other]
    for a, b in cand:
        s, ab, ba = bma(sl_direct[a], sl_prop[a], sl_direct[b], sl_prop[b], detail=True)
        inter, union = sl_prop[a] & sl_prop[b], sl_prop[a] | sl_prop[b]
        jac = sum(ic.get(t, 0) for t in inter) / max(1e-9, sum(ic.get(t, 0) for t in union))
        exact_shared = sorted(set(sl_direct[a]) & set(sl_direct[b]), key=lambda t: -ic.get(t, 0))
        pairs.append({"a": a, "b": b, "cross_family": b in other, "bma": s, "ic_jaccard": jac,
                      "pct_a": pct_rank(a, s), "pct_b": pct_rank(b, s), "exact_shared": exact_shared,
                      "best_matches_ab": [(t, c) for t, (c, _) in ab],
                      "best_matches_ba": [(t, c) for t, (c, _) in ba]})
    pairs.sort(key=lambda p: -p["bma"])

    def is_edge(p):
        return min(p["pct_a"], p["pct_b"]) >= PCTL and max(p["pct_a"], p["pct_b"]) >= PCTL_STRICT

    # ---- (c) selection (family diseases only; SNARE has_phenotype edges belong to the biology layer)
    shared_any = defaultdict(set)
    for p in pairs:
        if is_edge(p):
            for t in p["exact_shared"][:8]:
                shared_any[p["a"]].add(t)
    selected = {}
    for s in fam:
        tt = slice_terms[s]
        top = []
        for t in sorted(tt, key=lambda t: -ic.get(t, 0)):
            if len(top) >= TOP_K:
                break
            if any(t in anc(u) or u in anc(t) for u in top):
                continue
            top.append(t)
        keep = list(dict.fromkeys(top + sorted(shared_any[s], key=lambda t: -ic.get(t, 0))))
        for hall in HALLMARKS:
            if hall in tt and hall not in keep:
                keep.append(hall)
        selected[s] = keep[:MAX_PER_DISEASE]

    # ---- emit
    existing = {n["id"] for n in read_json(GRAPH)["nodes"]} if GRAPH.exists() else set()
    nodes, edges = {}, []
    hpo_url = "https://hpo.jax.org/browse/term/"

    def ref_url(ref):
        if ref.startswith("PMID:"):
            return f"https://pubmed.ncbi.nlm.nih.gov/{ref.split(':')[1]}/"
        if ref.startswith("OMIM:"):
            return f"https://omim.org/entry/{ref.split(':')[1]}"
        if ref.startswith("ORPHA:"):
            return f"https://www.orpha.net/en/disease/detail/{ref.split(':')[1]}"
        return "https://hpo.jax.org/"

    def ensure_pheno(t):
        pid = f"phenotype:{t}"
        if pid not in nodes and pid not in existing:
            nodes[pid] = {"id": pid, "type": "phenotype", "label": terms[t]["name"], "xrefs": {"HPO": t},
                          "attrs": {"ic": round(ic.get(t, 0.0), 3), "n_diseases": counts.get(t, 0),
                                    "n_total_diseases": n_total,
                                    "specificity": ("distinctive" if ic.get(t, 0) >= DISTINCTIVE_IC else
                                                    "broad" if ic.get(t, 0) < BROAD_IC else "intermediate")},
                          "sources": [{"source": "HPO", "ref": t, "url": hpo_url + t, "title": terms[t]["name"],
                                       "kind": "database", "study_type": "database_record",
                                       "extracted_by": "database", "retrieved": TODAY}]}
        return pid

    for s in fam:
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
                     "ic": round(ic.get(t, 0.0), 3)}
            if freq:
                attrs["frequency"] = freq if len(freq) > 1 else freq[0]
                lab = [FREQ_LABELS.get(f, f) for f in freq]
                attrs["frequency_label"] = lab if len(lab) > 1 else lab[0]
            spec = ("distinctive" if ic.get(t, 0) >= DISTINCTIVE_IC else "broad" if ic.get(t, 0) < BROAD_IC
                    else "intermediate")
            edges.append({"id": edge_id(f"disease:{s}", "has_phenotype", pid), "source": f"disease:{s}",
                          "target": pid, "type": "has_phenotype", "label": "has phenotype",
                          "explanation": (f"HPO annotates {terms[t]['name']} to {', '.join(sorted(info['entities']))} "
                                          f"({s}-related disorders). This feature is {spec} (IC {ic.get(t, 0):.2f}; "
                                          f"seen in {counts.get(t, 0)} of {n_total} annotated diseases)."),
                          "evidence_level": "curated", "status": "supported",
                          "confidence": 0.9 if any(r.startswith("PMID:") for r in refs) else 0.8,
                          "evidence": ev, "attrs": attrs})

    sim_edges = []
    for p in pairs:
        if not is_edge(p):
            continue
        a, b = p["a"], p["b"]
        mica = {}
        for t, c in p["best_matches_ab"] + p["best_matches_ba"]:
            if c:
                mica[c] = ic.get(c, 0.0)
        exact = p["exact_shared"]
        distinctive = [t for t in exact if ic.get(t, 0) >= DISTINCTIVE_IC]
        broad = [t for t in exact if ic.get(t, 0) < BROAD_IC]
        inter = [t for t in exact if BROAD_IC <= ic.get(t, 0) < DISTINCTIVE_IC]
        mica_distinct = [c for c in sorted(mica, key=lambda c: -mica[c]) if mica[c] >= DISTINCTIVE_IC
                         and c not in exact][:4]

        def fmt(ts):
            return ", ".join(f"{terms[t]['name']} (IC {ic.get(t, 0):.1f})" for t in ts) or "none"
        lo, hi = sorted((p["pct_a"], p["pct_b"]))
        expl = (f"{a}- and {b}-related disorders have more similar HPO phenotype profiles than "
                f"{int(lo * 100)}-{int(hi * 100)}% of background disease comparisons (Resnik BMA {p['bma']:.2f}). "
                f"Shared DISTINCTIVE (high-IC) features: {fmt(distinctive[:6])}. "
                f"Shared BROAD (low-IC) features: {fmt(broad[:4])}.")
        if mica_distinct:
            expl += f" Related distinctive features (common ancestor of best matches): {fmt(mica_distinct)}."
        if p["cross_family"]:
            expl += (f" This pair crosses disease families: {a} is a lysosomal storage disorder, {b} a "
                     f"SNAREopathy, so the overlap is in symptoms, not in cause.")
        conf = 0.3 + 0.19 * min(1.0, (lo - PCTL) / (1 - PCTL))
        sim_edges.append({"id": edge_id(f"disease:{a}", "similar_phenotype", f"disease:{b}"),
                          "source": f"disease:{a}", "target": f"disease:{b}", "type": "similar_phenotype",
                          "label": "similar symptom profile" + (" (cross-family)" if p["cross_family"] else ""),
                          "explanation": expl, "evidence_level": "inferred", "status": "supported",
                          "confidence": round(conf, 2),
                          "evidence": [{"source": "Atlas", "ref": "pipeline/families/lysosomal/hpo.py",
                                        "url": "https://github.com/obophenotype/human-phenotype-ontology/releases",
                                        "title": f"Resnik best-match-average over phenotype.hpoa {hpoa_version} / hp.obo "
                                                 f"{obo_version}; IC over {n_total} diseases",
                                        "kind": "computed", "extracted_by": "computed", "retrieved": TODAY}],
                          "attrs": {"resnik_bma": round(p["bma"], 3), "ic_weighted_jaccard": round(p["ic_jaccard"], 3),
                                    "background_percentile": {a: round(p["pct_a"], 4), b: round(p["pct_b"], 4)},
                                    "shared_distinctive": distinctive, "shared_intermediate": inter,
                                    "shared_broad": broad, "related_distinctive_mica": mica_distinct,
                                    "cross_family": p["cross_family"],
                                    "method": "Resnik BMA; edge if >= 95th percentile of both diseases' background "
                                              "and >= 99th for one"}})
        for t in distinctive[:6] + broad[:4] + inter[:4]:
            ensure_pheno(t)
    write_json(RAW / "hpo_fragment.json", {"nodes": sorted(nodes.values(), key=lambda n: n["id"]),
                                           "edges": edges + sim_edges})
    write_json(RAW / "hpo_stats.json", {
        "hpoa_version": hpoa_version, "hpo_version": obo_version, "n_total_diseases": n_total,
        "profiles": profiles, "terms_per_disease": {s: len(slice_terms[s]) for s in fam},
        "selected_per_disease": {s: len(selected[s]) for s in fam},
        "background": {s: {k: v for k, v in background[s].items() if k != "values"} for s in allsyms},
        "pairs": [{k: v for k, v in p.items() if not k.startswith("best_matches")} for p in pairs]})
    print(f"phenotype nodes (new)={len(nodes)} has_phenotype={len(edges)} similar_phenotype={len(sim_edges)}")
    print("selected per disease:", {s: len(selected[s]) for s in fam})
    for p in pairs[:40]:
        flag = "EDGE" if is_edge(p) else "    "
        print(f"  {flag} {'X' if p['cross_family'] else ' '} {p['a']:6s}-{p['b']:7s} BMA={p['bma']:.2f} "
              f"pct=({p['pct_a']:.3f},{p['pct_b']:.3f}) shared={len(p['exact_shared'])}")
    xe = [p for p in pairs if p["cross_family"] and is_edge(p)]
    print(f"cross-family edges: {[(p['a'], p['b'], round(p['bma'], 2)) for p in xe]}")
    best_x = sorted([p for p in pairs if p["cross_family"]], key=lambda p: -min(p["pct_a"], p["pct_b"]))[:8]
    for p in best_x:
        print(f"  best cross: {p['a']}-{p['b']} BMA={p['bma']:.2f} pct=({p['pct_a']:.3f},{p['pct_b']:.3f})")


if __name__ == "__main__":
    main()
