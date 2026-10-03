"""Task 3: HPO phenotypes, information content and phenotype similarity for the slice.

Run:  python3 pipeline/biology/hpo.py
Needs: data/raw/downloads/phenotype.hpoa, data/raw/downloads/hp.obo
       (download from https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/)
       data/raw/biology/diseases.json (fetch_diseases.py)
Out:  data/raw/biology/hpo_fragment.json  ({nodes, edges} in docs/SCHEMA.md shape)
      data/raw/biology/hpo_stats.json     (full per-disease profiles, similarity matrix, background)

Method
(a) Profile entities per gene-defined umbrella disease = every OMIM entity with an OMIM causal
    edge (Monarch) + every Orphanet entity whose Orphadata association is "Disease-causing" AND
    which is gene-specific (exactly one associated gene). Multi-gene clinical groups (e.g. GEFS+,
    Doose syndrome, presynaptic CMS groups) and contiguous-deletion / modifier links are excluded.
(b) IC(t) = -ln(n_diseases annotated to t or a descendant / n_total_diseases), computed over ALL
    diseases in phenotype.hpoa (aspect P only, NOT-qualified rows excluded, is_a propagation).
(c) Phenotype nodes + has_phenotype edges citing the hpoa `reference` column.
(d) Disease similarity = Resnik best-match-average (BMA) over direct annotations.
    An edge is emitted when the pair's BMA is >= the 95th percentile of BOTH diseases'
    background distributions AND >= the 99th percentile for at least one of them (background =
    BMA against a fixed random sample of 3000 non-slice diseases, seed 20261003).
"""
from __future__ import annotations

import math
import random
import re
from collections import defaultdict

from common import DOWNLOADS, RAW, TODAY, edge_id, read_json, write_json

HPOA = DOWNLOADS / "phenotype.hpoa"
OBO = DOWNLOADS / "hp.obo"
PHENO_ROOT = "HP:0000118"  # Phenotypic abnormality
DISTINCTIVE_IC = 4.0       # annotated (incl. descendants) in <= ~1.8% of diseases
BROAD_IC = 2.0             # annotated in >= ~13.5% of diseases
TOP_K = 12                 # most-informative terms kept per disease
MAX_PER_DISEASE = 20
BACKGROUND_N = 3000
PCTL = 0.95        # both diseases: pair must be in the top 5% of their background
PCTL_STRICT = 0.99 # and in the top 1% for at least one of the two diseases
FREQ_LABELS = {
    "HP:0040280": "Obligate (100%)", "HP:0040281": "Very frequent (80-99%)",
    "HP:0040282": "Frequent (30-79%)", "HP:0040283": "Occasional (5-29%)",
    "HP:0040284": "Very rare (1-4%)", "HP:0040285": "Excluded (0%)",
}


def parse_obo():
    terms, cur = {}, None
    alt = {}
    for line in OBO.read_text().splitlines():
        if line == "[Term]":
            cur = {"parents": [], "obsolete": False}
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = None
            continue
        if cur is None or not line:
            if cur is not None and not line and "id" in cur:
                terms[cur["id"]] = cur
                cur = None
            continue
        k, _, v = line.partition(": ")
        if k == "id":
            cur["id"] = v
        elif k == "name":
            cur["name"] = v
        elif k == "is_a":
            cur["parents"].append(v.split(" ! ")[0].strip())
        elif k == "alt_id":
            alt[v] = None  # filled after id known
            cur.setdefault("alt", []).append(v)
        elif k == "is_obsolete" and v == "true":
            cur["obsolete"] = True
        elif k == "replaced_by":
            cur["replaced_by"] = v
    if cur and "id" in cur:
        terms[cur["id"]] = cur
    alt_map = {}
    for tid, t in terms.items():
        for a in t.get("alt", []):
            alt_map[a] = tid
        if t["obsolete"] and t.get("replaced_by"):
            alt_map[tid] = t["replaced_by"]
    version = None
    for line in OBO.read_text().splitlines()[:20]:
        if line.startswith("data-version:"):
            version = line.split(": ", 1)[1]
    return terms, alt_map, version


def ancestors_fn(terms):
    cache = {}

    def anc(t):
        if t in cache:
            return cache[t]
        out = {t}
        for p in terms.get(t, {}).get("parents", []):
            out |= anc(p)
        cache[t] = frozenset(out)
        return cache[t]
    return anc


def parse_hpoa(alt_map, terms):
    rows = []
    version = None
    with HPOA.open() as fh:
        for line in fh:
            if line.startswith("#"):
                if line.startswith("#version:"):
                    version = line.split(":", 1)[1].strip()
                continue
            if line.startswith("database_id"):
                continue
            f = line.rstrip("\n").split("\t")
            r = dict(zip(["database_id", "disease_name", "qualifier", "hpo_id", "reference", "evidence",
                          "onset", "frequency", "sex", "modifier", "aspect", "biocuration"], f))
            hid = alt_map.get(r["hpo_id"], r["hpo_id"])
            if hid not in terms or terms[hid]["obsolete"]:
                continue
            r["hpo_id"] = hid
            rows.append(r)
    return rows, version


def main() -> None:
    terms, alt_map, obo_version = parse_obo()
    anc = ancestors_fn(terms)
    rows, hpoa_version = parse_hpoa(alt_map, terms)
    print(f"hp.obo {obo_version}: {len(terms)} terms; phenotype.hpoa {hpoa_version}: {len(rows)} rows")

    # ---- (b) information content over ALL diseases (aspect P, positive annotations)
    direct = defaultdict(set)
    names = {}
    for r in rows:
        if r["aspect"] != "P" or r["qualifier"] == "NOT":
            continue
        direct[r["database_id"]].add(r["hpo_id"])
        names[r["database_id"]] = r["disease_name"]
    propagated = {d: frozenset().union(*(anc(t) for t in ts)) for d, ts in direct.items()}
    n_total = len(direct)
    counts = defaultdict(int)
    for d, ps in propagated.items():
        for t in ps:
            counts[t] += 1
    ic = {t: -math.log(c / n_total) for t, c in counts.items()}
    print(f"IC computed over {n_total} diseases")

    # ---- (a) slice profile entities
    dis = read_json(RAW / "diseases.json")
    profiles = {}
    for sym, d in dis.items():
        if not d["include"]:
            continue
        ents = []
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                if m["primary_knowledge_source"] == "infores:omim" and (m.get("original_object") or "").startswith("OMIM:"):
                    ents.append(m["original_object"])
        for code, a in d.get("orphanet_associations", {}).items():
            if a.get("causal") and a.get("n_genes_associated") == 1:
                ents.append(f"ORPHA:{code}")
        ents = sorted(set(ents))
        present = [e for e in ents if e in direct]
        missing = [e for e in ents if e not in direct]
        profiles[sym] = {"entities": ents, "annotated_entities": present, "missing_in_hpoa": missing}
        print(f"  {sym}: profile entities {ents} (no HPO annotations: {missing})")

    # per-umbrella term table (direct, positive, aspect P)
    slice_terms = {}
    for sym, p in profiles.items():
        tt = {}
        for r in rows:
            if r["database_id"] not in p["annotated_entities"]:
                continue
            if r["aspect"] != "P" or r["qualifier"] == "NOT":
                continue
            t = tt.setdefault(r["hpo_id"], {"refs": set(), "freq": set(), "evidence": set(),
                                             "entities": set()})
            for ref in r["reference"].split(";"):
                if ref.strip():
                    t["refs"].add(ref.strip())
            if r["frequency"]:
                t["freq"].add(r["frequency"])
            t["evidence"].add(r["evidence"])
            t["entities"].add(r["database_id"])
        slice_terms[sym] = tt
        print(f"  {sym}: {len(tt)} direct phenotype terms")

    syms = [s for s in profiles if slice_terms[s]]

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
        if detail:
            return s, list(zip(ta, ab)), list(zip(tb, ba))
        return s

    sl_direct = {s: sorted(slice_terms[s]) for s in syms}
    sl_prop = {s: frozenset().union(*(anc(t) for t in sl_direct[s])) for s in syms}

    slice_entity_ids = {e for p in profiles.values() for e in p["entities"]}
    bg_pool = sorted(d for d in direct if d not in slice_entity_ids)
    rng = random.Random(20261003)
    bg = rng.sample(bg_pool, min(BACKGROUND_N, len(bg_pool)))
    background = {}
    for s in syms:
        vals = sorted(bma(sl_direct[s], sl_prop[s], sorted(direct[d]), propagated[d]) for d in bg)
        background[s] = {"p50": vals[len(vals) // 2], "p90": vals[int(0.90 * len(vals))],
                         "p95": vals[int(PCTL * len(vals))], "p99": vals[int(0.99 * len(vals))],
                         "values": vals}
        print(f"  background {s}: p50={background[s]['p50']:.2f} p95={background[s]['p95']:.2f} "
              f"p99={background[s]['p99']:.2f}")

    def pct_rank(s, v):
        vals = background[s]["values"]
        lo = sum(1 for x in vals if x < v)
        return lo / len(vals)

    pairs = []
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            s, ab, ba = bma(sl_direct[a], sl_prop[a], sl_direct[b], sl_prop[b], detail=True)
            # weighted IC-Jaccard over propagated sets (secondary metric)
            inter = sl_prop[a] & sl_prop[b]
            union = sl_prop[a] | sl_prop[b]
            jac = sum(ic.get(t, 0) for t in inter) / max(1e-9, sum(ic.get(t, 0) for t in union))
            exact_shared = sorted(set(sl_direct[a]) & set(sl_direct[b]), key=lambda t: -ic.get(t, 0))
            pairs.append({"a": a, "b": b, "bma": s, "ic_jaccard": jac,
                          "pct_a": pct_rank(a, s), "pct_b": pct_rank(b, s),
                          "exact_shared": exact_shared,
                          "best_matches_ab": [(t, c) for t, (c, _) in ab],
                          "best_matches_ba": [(t, c) for t, (c, _) in ba]})
    pairs.sort(key=lambda p: -p["bma"])

    def is_edge(p):
        return min(p["pct_a"], p["pct_b"]) >= PCTL and max(p["pct_a"], p["pct_b"]) >= PCTL_STRICT

    # ---- phenotype selection for readability
    selected = {}
    shared_any = defaultdict(set)
    for p in pairs:
        if is_edge(p):
            for t in p["exact_shared"][:8]:
                shared_any[p["a"]].add(t)
                shared_any[p["b"]].add(t)
    for s in syms:
        tt = slice_terms[s]
        # drop terms that are ancestors of another kept term only if they are broad duplicates
        by_ic = sorted(tt, key=lambda t: -ic.get(t, 0))
        top = []
        for t in by_ic:
            if len(top) >= TOP_K:
                break
            # avoid near-duplicate parent/child pairs among the top terms
            if any(t in anc(u) or u in anc(t) for u in top):
                continue
            top.append(t)
        keep = list(dict.fromkeys(top + sorted(shared_any[s], key=lambda t: -ic.get(t, 0))))
        # always keep the classic broad hallmark terms when directly annotated, so BROAD vs
        # DISTINCTIVE contrast is visible (seizure / ID / developmental delay / hypotonia)
        for hall in ["HP:0001250", "HP:0001249", "HP:0001263", "HP:0001252"]:
            if hall in tt and hall not in keep:
                keep.append(hall)
        selected[s] = keep[:MAX_PER_DISEASE]

    # ---- emit nodes / edges
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
        if pid not in nodes:
            nodes[pid] = {
                "id": pid, "type": "phenotype", "label": terms[t]["name"],
                "xrefs": {"HPO": t},
                "attrs": {"ic": round(ic.get(t, 0.0), 3), "n_diseases": counts.get(t, 0),
                          "n_total_diseases": n_total,
                          "specificity": ("distinctive" if ic.get(t, 0) >= DISTINCTIVE_IC else
                                          "broad" if ic.get(t, 0) < BROAD_IC else "intermediate")},
                "sources": [{"source": "HPO", "ref": t, "url": hpo_url + t, "title": terms[t]["name"],
                             "kind": "database", "study_type": "database_record",
                             "extracted_by": "database", "retrieved": TODAY}],
            }
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
            has_pmid = any(r.startswith("PMID:") for r in refs)
            freq = sorted(info["freq"])
            attrs = {"hpo_evidence_codes": sorted(info["evidence"]),
                     "entities": sorted(info["entities"]), "ic": round(ic.get(t, 0.0), 3)}
            if freq:
                attrs["frequency"] = freq if len(freq) > 1 else freq[0]
                lab = [FREQ_LABELS.get(f, f) for f in freq]
                attrs["frequency_label"] = lab if len(lab) > 1 else lab[0]
            spec = nodes[pid]["attrs"]["specificity"]
            edges.append({
                "id": edge_id(f"disease:{s}", "has_phenotype", pid),
                "source": f"disease:{s}", "target": pid, "type": "has_phenotype",
                "label": "has phenotype",
                "explanation": (f"HPO annotates {terms[t]['name']} to {', '.join(sorted(info['entities']))} "
                                f"({s}-related disorders). This feature is {spec} "
                                f"(IC {ic.get(t, 0):.2f}; seen in {counts.get(t, 0)} of {n_total} annotated diseases)."),
                "evidence_level": "curated", "status": "supported",
                "confidence": 0.9 if has_pmid else 0.8,
                "evidence": ev, "attrs": attrs,
            })

    sim_edges = []
    for p in pairs:
        if not is_edge(p):
            continue
        a, b = p["a"], p["b"]
        # shared phenotype concepts: exact shared terms plus informative MICA terms from best matches
        mica = defaultdict(float)
        for t, c in p["best_matches_ab"] + p["best_matches_ba"]:
            if c:
                mica[c] = ic.get(c, 0.0)
        exact = p["exact_shared"]
        distinctive = [t for t in exact if ic.get(t, 0) >= DISTINCTIVE_IC]
        broad = [t for t in exact if ic.get(t, 0) < BROAD_IC]
        inter = [t for t in exact if BROAD_IC <= ic.get(t, 0) < DISTINCTIVE_IC]
        mica_distinct = [c for c in sorted(mica, key=lambda c: -mica[c])
                         if mica[c] >= DISTINCTIVE_IC and c not in exact][:4]
        for t in distinctive[:6] + broad[:4] + inter[:4]:
            ensure_pheno(t)

        def fmt(ts):
            return ", ".join(f"{terms[t]['name']} (IC {ic.get(t, 0):.1f})" for t in ts) or "none"
        expl = (f"{a}- and {b}-related disorders have more similar HPO phenotype profiles than "
                f"{int(min(p['pct_a'], p['pct_b']) * 100)}-{int(max(p['pct_a'], p['pct_b']) * 100)}% of "
                f"background disease comparisons (Resnik BMA {p['bma']:.2f}). "
                f"Shared DISTINCTIVE (high-IC) features: {fmt(distinctive[:6])}. "
                f"Shared BROAD (low-IC) features: {fmt(broad[:4])}.")
        if mica_distinct:
            expl += f" Related distinctive features (common ancestor of best matches): {fmt(mica_distinct)}."
        conf = 0.3 + 0.19 * min(1.0, (min(p["pct_a"], p["pct_b"]) - PCTL) / (1 - PCTL))
        sim_edges.append({
            "id": edge_id(f"disease:{a}", "similar_phenotype", f"disease:{b}"),
            "source": f"disease:{a}", "target": f"disease:{b}", "type": "similar_phenotype",
            "label": "similar symptom profile",
            "explanation": expl,
            "evidence_level": "inferred", "status": "supported", "confidence": round(conf, 2),
            "evidence": [{"source": "Atlas", "ref": "pipeline/biology/hpo.py",
                          "url": "https://github.com/obophenotype/human-phenotype-ontology/releases",
                          "title": f"Resnik best-match-average over phenotype.hpoa {hpoa_version} / hp.obo "
                                   f"{obo_version}; IC over {n_total} diseases",
                          "kind": "computed", "extracted_by": "computed", "retrieved": TODAY}],
            "attrs": {"resnik_bma": round(p["bma"], 3), "ic_weighted_jaccard": round(p["ic_jaccard"], 3),
                      "background_percentile": {a: round(p["pct_a"], 4), b: round(p["pct_b"], 4)},
                      "shared_distinctive": distinctive, "shared_intermediate": inter,
                      "shared_broad": broad, "related_distinctive_mica": mica_distinct,
                      "method": "Resnik BMA; edge if >= 95th percentile of both diseases' background and >= 99th for one"},
        })

    frag = {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges + sim_edges}
    write_json(RAW / "hpo_fragment.json", frag)
    stats = {
        "hpoa_version": hpoa_version, "hpo_version": obo_version, "n_total_diseases": n_total,
        "thresholds": {"distinctive_ic": DISTINCTIVE_IC, "broad_ic": BROAD_IC, "percentile": PCTL,
                       "top_k": TOP_K, "max_per_disease": MAX_PER_DISEASE, "background_n": BACKGROUND_N},
        "profiles": profiles,
        "terms_per_disease": {s: len(slice_terms[s]) for s in syms},
        "selected_per_disease": {s: len(selected[s]) for s in syms},
        "background": {s: {k: v for k, v in background[s].items() if k != "values"} for s in syms},
        "pairs": [{k: v for k, v in p.items() if not k.startswith("best_matches")} for p in pairs],
    }
    write_json(RAW / "hpo_stats.json", stats)
    print(f"phenotype nodes={len(nodes)} has_phenotype={len(edges)} similar_phenotype={len(sim_edges)}")
    for p in pairs[:20]:
        flag = "EDGE" if is_edge(p) else "    "
        print(f"  {flag} {p['a']:7s}-{p['b']:7s} BMA={p['bma']:.2f} pct=({p['pct_a']:.3f},{p['pct_b']:.3f}) "
              f"jac={p['ic_jaccard']:.2f} shared={len(p['exact_shared'])}")


if __name__ == "__main__":
    main()
