"""Product 4: nearest phenotype neighbours OUTSIDE the slice -> data/derived/beyond_slice.json

Run:  python3 pipeline/derive/beyond_slice.py
In:   data/raw/downloads/{phenotype.hpoa, hp.obo, genes_to_disease.txt}
      data/raw/biology/hpo_stats.json (the biology layer's profile entities per umbrella disease)
Method (same as pipeline/biology/hpo.py, whose parsers are imported, not copied):
  IC(t) = -ln(n diseases annotated to t or a descendant / N), aspect P, NOT rows dropped, over ALL
  diseases in phenotype.hpoa. Umbrella profile = union of direct annotations of its OMIM/ORPHA
  entities. Similarity = Resnik best-match-average (BMA) against EVERY disease in phenotype.hpoa.
  Percentile = share of all non-slice HPO diseases scoring lower. Excluded as "inside the slice":
  every slice profile entity and every disease whose genes_to_disease.txt genes include a slice gene.
  Shared terms = the most informative common ancestors (MICA) of the best matches, ranked by IC.
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict

from dcommon import BIO_RAW, DERIVED, DOWNLOADS, ROOT, SLICE_GENES, TODAY, read_json, write_json

sys.path.append(str(ROOT / "pipeline" / "biology"))
import hpo  # noqa: E402  (biology layer: parse_obo, ancestors_fn, parse_hpoa, IC thresholds)

TOP_N = 8
MIN_TERMS = 5
LABEL = "phenotype similarity only; mechanism not assessed"


def main():
    terms, alt_map, obo_version = hpo.parse_obo()
    anc = hpo.ancestors_fn(terms)
    rows, hpoa_version = hpo.parse_hpoa(alt_map, terms)
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

    genes_of = defaultdict(set)
    for line in (DOWNLOADS / "genes_to_disease.txt").read_text().splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 4:
            genes_of[f[3]].add(f[1])
    profiles = read_json(BIO_RAW / "hpo_stats.json")["profiles"]
    slice_entities = {e for p in profiles.values() for e in p["entities"]}
    slice_set = set(SLICE_GENES)
    excluded = {d for d in direct if d in slice_entities or genes_of.get(d, set()) & slice_set}
    # Resnik BMA over-rewards very small profiles (one rare term matched inside a large profile), and
    # QTL / susceptibility loci are not rare-disease entities: both are left out of the comparison.
    pool = sorted(d for d in direct if d not in excluded and len(direct[d]) >= MIN_TERMS
                  and not re.search(r"\bQTL|susceptibility", names.get(d, ""), re.I))

    anc_sorted = {}

    def anc_by_ic(t):
        if t not in anc_sorted:
            anc_sorted[t] = sorted(anc(t), key=lambda x: -ic.get(x, 0.0))
        return anc_sorted[t]

    def best(t, other_prop):
        for c in anc_by_ic(t):
            if c in other_prop:
                return c
        return None

    def bma(ta, pa, tb, pb):
        s1 = sum(ic.get(best(t, pb), 0.0) if best(t, pb) else 0.0 for t in ta) / len(ta)
        s2 = sum(ic.get(best(t, pa), 0.0) if best(t, pa) else 0.0 for t in tb) / len(tb)
        return 0.5 * (s1 + s2)

    def spec(v):
        return "distinctive" if v >= hpo.DISTINCTIVE_IC else ("broad" if v < hpo.BROAD_IC else "intermediate")

    out = {}
    for sym in SLICE_GENES:
        ents = profiles.get(sym, {}).get("annotated_entities", [])
        if not ents:
            out[f"disease:{sym}"] = {"profile_entities": [], "neighbors": [],
                                     "note": "No HPO-annotated OMIM/Orphanet entity for this gene "
                                             "(see gap:stx1a-mendelian-validity), so no profile to compare."}
            continue
        ta = sorted(set().union(*(direct[e] for e in ents)))
        pa = frozenset().union(*(anc(t) for t in ta))
        scores = {d: bma(ta, pa, sorted(direct[d]), propagated[d]) for d in pool}
        ranked = sorted(scores.values())
        n = len(ranked)

        def pct(v):
            lo, hi = 0, n
            while lo < hi:
                mid = (lo + hi) // 2
                if ranked[mid] < v:
                    lo = mid + 1
                else:
                    hi = mid
            return lo / n
        top = sorted(pool, key=lambda d: (-scores[d], d))[:TOP_N]
        neigh = []
        for d in top:
            tb = sorted(direct[d])
            mica = {}
            for t in ta:
                c = best(t, propagated[d])
                if c:
                    mica[c] = ic.get(c, 0.0)
            for t in tb:
                c = best(t, pa)
                if c:
                    mica[c] = ic.get(c, 0.0)
            shared = sorted(mica, key=lambda c: (-mica[c], c))
            distinctive = [c for c in shared if mica[c] >= hpo.DISTINCTIVE_IC][:3]
            if len(distinctive) < 3:
                distinctive += [c for c in shared if c not in distinctive][:3 - len(distinctive)]
            neigh.append({
                "id": d, "name": names[d], "genes": sorted(genes_of.get(d, [])),
                "score": round(scores[d], 3), "percentile": round(pct(scores[d]), 4),
                "top_shared_terms": [{"hpo": c, "name": terms[c]["name"], "ic": round(mica[c], 2),
                                      "specificity": spec(mica[c])} for c in distinctive],
            })
        out[f"disease:{sym}"] = {
            "profile_entities": ents, "n_profile_terms": len(ta),
            "background": {"p50": round(ranked[n // 2], 3), "p99": round(ranked[int(0.99 * n)], 3),
                           "max": round(ranked[-1], 3)},
            "neighbors": neigh,
        }
        print(f"[beyond] {sym}: {len(ta)} terms; top: " +
              "; ".join(f"{x['name'][:40]} ({','.join(x['genes'][:2])}) {x['score']}" for x in neigh[:3]))
    data = {
        "label": LABEL,
        "meta": {"generated": TODAY, "hpoa_version": hpoa_version, "hpo_version": obo_version,
                 "n_hpo_diseases": n_total, "n_compared": len(pool), "n_excluded_as_slice": len(excluded),
                 "method": "Resnik best-match-average over direct annotations; IC over all phenotype.hpoa "
                           "diseases (aspect P, NOT rows dropped, is_a propagation); percentile = share of "
                           "all compared non-slice diseases scoring lower; shared terms = most informative "
                           "common ancestors of the best matches (distinctive = IC >= 4.0).",
                 "excluded_rule": "slice profile entities, and any disease whose genes_to_disease.txt genes "
                                  "include a slice gene (e.g. multi-gene CMS or GEFS+ groupings); diseases with "
                                  f"fewer than {MIN_TERMS} direct phenotype terms (Resnik BMA over-rewards tiny "
                                  "profiles); QTL and susceptibility loci",
                 "code": "pipeline/derive/beyond_slice.py (imports pipeline/biology/hpo.py parsers)"},
        "diseases": out,
    }
    size = write_json(DERIVED / "beyond_slice.json", data)
    print(f"[beyond] wrote beyond_slice.json ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
