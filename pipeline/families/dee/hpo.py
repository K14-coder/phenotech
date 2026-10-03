"""DEE family, step 4: HPO phenotypes, information content and phenotype similarity, INCLUDING
cross-family pairs with the 11 SNAREopathy diseases already in the atlas.

Method = pipeline/biology/hpo.py unchanged (the parsing / IC / BMA helpers are imported from it):
  * IC(t) = -ln(n diseases annotated to t or a descendant / N), over ALL diseases in
    phenotype.hpoa (aspect P, NOT rows dropped, obsolete/alt ids remapped, is_a propagation).
  * Profile entities per gene umbrella = OMIM entities with an OMIM causal edge (Monarch) +
    Orphanet entities that are "Disease-causing" AND gene-specific (exactly one gene).
    SNAREopathy profiles are read from data/raw/biology/hpo_stats.json (same rule).
  * Resnik best-match-average; an edge is emitted when the pair is >= 99th percentile of BOTH
    diseases' background distributions (BMA vs a fixed random sample of 3000 diseases outside
    both families, seed 20261003). This is stricter than the SNAREopathy layer's 95th/99th rule
    because both families are epilepsy-dense (that rule would flag 72 of 155 pairs here).
  * Only DEE-DEE and DEE-SNARE pairs are emitted here (SNARE-SNARE pairs already exist).

Run:  python3 pipeline/families/dee/hpo.py
Out:  data/raw/families/dee/hpo_fragment.json, data/raw/families/dee/hpo_stats.json
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from dee_common import BIO_RAW, GENES, RAW, SNARE_GENES, TODAY, edge_id, existing_graph, read_json, write_json

import hpo as bio_hpo  # noqa: E402  (pipeline/biology/hpo.py: parse_obo, ancestors_fn, parse_hpoa, constants)

DISTINCTIVE_IC, BROAD_IC = bio_hpo.DISTINCTIVE_IC, bio_hpo.BROAD_IC
TOP_K, MAX_PER_DISEASE, BACKGROUND_N = bio_hpo.TOP_K, bio_hpo.MAX_PER_DISEASE, bio_hpo.BACKGROUND_N
PCTL, PCTL_STRICT, FREQ_LABELS = bio_hpo.PCTL, bio_hpo.PCTL_STRICT, bio_hpo.FREQ_LABELS
PCTL_BOTH = 0.99
HALLMARKS = ["HP:0001250", "HP:0001249", "HP:0001263", "HP:0001252"]


def dee_profiles():
    dis = read_json(RAW / "diseases.json")
    prof = {}
    for sym in GENES:
        d = dis[sym]
        ents = []
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                if m["primary_knowledge_source"] == "infores:omim" and (m.get("original_object") or "").startswith("OMIM:"):
                    ents.append(m["original_object"])
        for code, a in d.get("orphanet_associations", {}).items():
            if a.get("causal") and a.get("n_genes_associated") == 1:
                ents.append(f"ORPHA:{code}")
        prof[sym] = sorted(set(ents))
    return prof


def main():
    terms, alt_map, obo_version = bio_hpo.parse_obo()
    anc = bio_hpo.ancestors_fn(terms)
    rows, hpoa_version = bio_hpo.parse_hpoa(alt_map, terms)
    direct, names = defaultdict(set), {}
    for r in rows:
        if r["aspect"] != "P" or r["qualifier"] == "NOT":
            continue
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

    bio_stats = read_json(BIO_RAW / "hpo_stats.json")
    profiles = {s: {"entities": e} for s, e in dee_profiles().items()}
    for s in SNARE_GENES:
        profiles[s] = {"entities": bio_stats["profiles"][s]["entities"]}
    for s, p in profiles.items():
        p["annotated_entities"] = [e for e in p["entities"] if e in direct]
        p["missing_in_hpoa"] = [e for e in p["entities"] if e not in direct]

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
    for s in GENES:
        print(f"  {s}: entities {profiles[s]['annotated_entities']} -> {len(slice_terms[s])} direct terms "
              f"(no HPO annotations: {profiles[s]['missing_in_hpoa']})")
    syms = [s for s in profiles if slice_terms[s]]
    dee = [s for s in GENES if s in syms]
    snare = [s for s in SNARE_GENES if s in syms]

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

    sl_direct = {s: sorted(slice_terms[s]) for s in syms}
    sl_prop = {s: frozenset().union(*(anc(t) for t in sl_direct[s])) for s in syms}
    slice_entity_ids = {e for p in profiles.values() for e in p["entities"]}
    bg_pool = sorted(d for d in direct if d not in slice_entity_ids)
    bg = random.Random(20261003).sample(bg_pool, min(BACKGROUND_N, len(bg_pool)))
    background = {}
    for s in syms:
        vals = sorted(bma(sl_direct[s], sl_prop[s], sorted(direct[d]), propagated[d]) for d in bg)
        background[s] = {"p50": vals[len(vals) // 2], "p95": vals[int(PCTL * len(vals))],
                         "p99": vals[int(0.99 * len(vals))], "values": vals}

    def pct_rank(s, v):
        vals = background[s]["values"]
        return sum(1 for x in vals if x < v) / len(vals)

    pairs = []
    cand = [(a, b) for i, a in enumerate(dee) for b in dee[i + 1:]] + [(a, b) for a in dee for b in snare]
    for a, b in cand:
        s, ab, ba = bma(sl_direct[a], sl_prop[a], sl_direct[b], sl_prop[b], detail=True)
        inter, union = sl_prop[a] & sl_prop[b], sl_prop[a] | sl_prop[b]
        jac = sum(ic.get(t, 0) for t in inter) / max(1e-9, sum(ic.get(t, 0) for t in union))
        pairs.append({"a": a, "b": b, "cross_family": b in SNARE_GENES, "bma": s, "ic_jaccard": jac,
                      "pct_a": pct_rank(a, s), "pct_b": pct_rank(b, s),
                      "exact_shared": sorted(set(sl_direct[a]) & set(sl_direct[b]), key=lambda t: -ic.get(t, 0)),
                      "best_matches": [(t, c) for t, (c, _) in ab] + [(t, c) for t, (c, _) in ba]})
    pairs.sort(key=lambda p: -p["bma"])

    def is_edge(p):
        # STRICTER than the SNAREopathy layer (>=95th for both and >=99th for one): both families
        # are epilepsy-dense, so against a random rare-disease background that rule flags 72 of 155
        # pairs. Requiring >= the 99th percentile for BOTH diseases keeps 34 (20 cross-family).
        return min(p["pct_a"], p["pct_b"]) >= PCTL_BOTH

    # ---- phenotype selection (DEE diseases only; SNARE phenotypes are already in the graph)
    shared_any = defaultdict(set)
    for p in pairs:
        if is_edge(p):
            for t in p["exact_shared"][:8]:
                shared_any[p["a"]].add(t)
                if p["b"] in GENES:
                    shared_any[p["b"]].add(t)
    selected = {}
    for s in dee:
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

    existing = existing_graph()
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

    def spec(t):
        v = ic.get(t, 0)
        return "distinctive" if v >= DISTINCTIVE_IC else "broad" if v < BROAD_IC else "intermediate"

    for s in dee:
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
            edges.append({"id": edge_id(f"disease:{s}", "has_phenotype", pid), "source": f"disease:{s}",
                          "target": pid, "type": "has_phenotype", "label": "has phenotype",
                          "explanation": (f"HPO annotates {terms[t]['name']} to {', '.join(sorted(info['entities']))} "
                                          f"({s}-related disorders). This feature is {spec(t)} (IC {ic.get(t, 0):.2f}; "
                                          f"seen in {counts.get(t, 0)} of {n_total} annotated diseases)."),
                          "evidence_level": "curated", "status": "supported",
                          "confidence": 0.9 if any(r.startswith("PMID:") for r in refs) else 0.8,
                          "evidence": ev, "attrs": attrs})

    def fmt(ts):
        return ", ".join(f"{terms[t]['name']} (IC {ic.get(t, 0):.1f})" for t in ts) or "none"

    for p in pairs:
        if not is_edge(p):
            continue
        a, b = p["a"], p["b"]
        exact = p["exact_shared"]
        distinctive = [t for t in exact if ic.get(t, 0) >= DISTINCTIVE_IC]
        broad = [t for t in exact if ic.get(t, 0) < BROAD_IC]
        inter = [t for t in exact if BROAD_IC <= ic.get(t, 0) < DISTINCTIVE_IC]
        mica = {c: ic.get(c, 0.0) for _, c in p["best_matches"] if c}
        mica_distinct = [c for c in sorted(mica, key=lambda c: -mica[c]) if mica[c] >= DISTINCTIVE_IC and c not in exact][:4]
        for t in distinctive[:6] + broad[:4] + inter[:4]:
            ensure_pheno(t)
        expl = (f"{a}- and {b}-related disorders have more similar HPO phenotype profiles than "
                f"{int(min(p['pct_a'], p['pct_b']) * 100)}-{int(max(p['pct_a'], p['pct_b']) * 100)}% of background "
                f"disease comparisons (Resnik BMA {p['bma']:.2f}). Shared DISTINCTIVE (high-IC) features: "
                f"{fmt(distinctive[:6])}. Shared BROAD (low-IC) features: {fmt(broad[:4])}.")
        if mica_distinct:
            expl += f" Related distinctive features (common ancestor of best matches): {fmt(mica_distinct)}."
        conf = 0.3 + 0.19 * min(1.0, (min(p["pct_a"], p["pct_b"]) - PCTL) / (1 - PCTL))
        edges.append({"id": edge_id(f"disease:{a}", "similar_phenotype", f"disease:{b}"),
                      "source": f"disease:{a}", "target": f"disease:{b}", "type": "similar_phenotype",
                      "label": "similar symptom profile", "explanation": expl,
                      "evidence_level": "inferred", "status": "supported", "confidence": round(conf, 2),
                      "evidence": [{"source": "Atlas", "ref": "pipeline/families/dee/hpo.py",
                                    "url": "https://github.com/obophenotype/human-phenotype-ontology/releases",
                                    "title": f"Resnik best-match-average over phenotype.hpoa {hpoa_version} / hp.obo "
                                             f"{obo_version}; IC over {n_total} diseases",
                                    "kind": "computed", "extracted_by": "computed", "retrieved": TODAY}],
                      "attrs": {"resnik_bma": round(p["bma"], 3), "ic_weighted_jaccard": round(p["ic_jaccard"], 3),
                                "background_percentile": {a: round(p["pct_a"], 4), b: round(p["pct_b"], 4)},
                                "shared_distinctive": distinctive, "shared_intermediate": inter, "shared_broad": broad,
                                "related_distinctive_mica": mica_distinct, "cross_family": p["cross_family"],
                                "method": "Resnik BMA; edge if >= 99th percentile of BOTH diseases' background distributions"}})

    write_json(RAW / "hpo_fragment.json", {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges})
    write_json(RAW / "hpo_stats.json", {
        "hpoa_version": hpoa_version, "hpo_version": obo_version, "n_total_diseases": n_total,
        "profiles": profiles, "terms_per_disease": {s: len(slice_terms[s]) for s in syms},
        "selected_per_disease": {s: len(selected[s]) for s in dee},
        "background": {s: {k: v for k, v in background[s].items() if k != "values"} for s in syms},
        "pairs": [{k: v for k, v in p.items() if k != "best_matches"} for p in pairs]})
    n_sim = sum(1 for e in edges if e["type"] == "similar_phenotype")
    n_x = sum(1 for e in edges if e["type"] == "similar_phenotype" and e["attrs"]["cross_family"])
    print(f"new phenotype nodes={len(nodes)} has_phenotype={len(edges) - n_sim} similar_phenotype={n_sim} "
          f"(cross-family {n_x}); selected per disease={ {s: len(selected[s]) for s in dee} }")
    for p in pairs[:30]:
        print(f"  {'EDGE' if is_edge(p) else '    '} {'X' if p['cross_family'] else ' '} {p['a']:8s}-{p['b']:8s} "
              f"BMA={p['bma']:.2f} pct=({p['pct_a']:.3f},{p['pct_b']:.3f}) shared={len(p['exact_shared'])}")


if __name__ == "__main__":
    main()
