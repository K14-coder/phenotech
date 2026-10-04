"""Multi-feature therapy-transfer scorer: single features, nested-CV tuned combinations, ablation.

Run:  python3 pipeline/eval/build_features.py && python3 pipeline/eval/feature_eval.py   (numpy; ~1 min; offline)
Reads data/graph.json + data/derived/features/atlas_features.json. Writes data/derived/eval_features.json.

Benchmark = the 56 developed_for leave-one-out cases of transfer_eval.py (same hiding, filtered ranking,
expected-value ties, class-level bootstrap). Each feature is a per-query max-normalised similarity
(see transfer_score.FEATURE_DOC); a combination is sum_f w_f * feature_f.

Tuning without leakage (nested, grouped by therapy class):
  outer loop: hold out ALL cases of one therapy class (38 folds);
  inner: choose weights on the remaining classes only, then score the held-out class's cases.
Two pre-declared tuners, both coarse because n is small:
  grid   : every w in {0, 1} for each feature (a feature-subset search), objective = mean reciprocal rank
           on the training classes; ties -> fewer features. 2^12 = 4,096 settings.
  logit  : conditional-logit ranking model (softmax over each case's candidates), weights constrained >= 0,
           L2 penalty lambda = 1 per feature, projected gradient descent.
Plus untuned references: equal weight on all features; the old best (symptoms + mechanism_target).
"""
from __future__ import annotations

import itertools
import json
import math
import pathlib
import random
import statistics
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from transfer_eval import B, KS, SEED, build_cases, families, r3, tie_metrics  # noqa: E402
from transfer_score import (ALL_FEATURES, CONTEXT_FEATURES, FEATURE_DOC, ROOT, MultiFeatureIndex,  # noqa: E402
                            load_graph)

OUT = ROOT / "data" / "derived" / "eval_features.json"
EPS = 1e-9
# shared_gene is constant 0 here (one causal gene per disease, no two diseases share one): kept in the
# single-feature table for completeness, excluded from tuning.
TUNE = [f for f in ALL_FEATURES if f != "shared_gene"]
OLD_BEST = {"symptoms": 1.0, "mechanism_target": 1.0}
LAMBDA = 1.0


# ---------------------------------------------------------------- data
def case_tensors(idx, cases):
    """Per case: candidate list, index of the held-out disease, matrix (n_cand x F) of normalised features."""
    out = []
    for c in cases:
        cands = [d for d in idx.diseases if d not in set(c["context"])]
        fm = idx.feature_matrix(c["cls"], c["context"], cands, ALL_FEATURES)
        X = np.array([[fm[f][d] for f in ALL_FEATURES] for d in cands])
        out.append({"cands": cands, "y": cands.index(c["held_out"]), "X": X, "cls": c["cls"]})
    return out


def metrics_from_scores(s, y):
    s = np.round(s, 9)
    sc = {i: float(v) for i, v in enumerate(s)}
    return tie_metrics(sc, y)


# ---------------------------------------------------------------- vectorised reciprocal rank for many weight vectors
H = np.concatenate([[0.0], np.cumsum(1.0 / np.arange(1, 200))])


def rr_matrix(T, W):
    """T: list of case tensors, W: (K x F) weights -> RR (n_cases x K), expected value under random tie-break."""
    out = np.zeros((len(T), W.shape[0]))
    for i, t in enumerate(T):
        S = np.round(t["X"] @ W.T, 9)             # n_cand x K
        st = S[t["y"]]                              # K
        g = (S > st + EPS).sum(0)
        tie = (np.abs(S - st) <= EPS).sum(0)
        out[i] = (H[g + tie] - H[g]) / tie
    return out


def fidx(feats):
    return [ALL_FEATURES.index(f) for f in feats]


def grid_weights(feats):
    """All {0,1} subsets over `feats` (excluding the empty one), as K x len(ALL_FEATURES)."""
    cols = fidx(feats)
    rows = []
    for bits in itertools.product((0.0, 1.0), repeat=len(feats)):
        if not any(bits):
            continue
        w = np.zeros(len(ALL_FEATURES))
        w[cols] = bits
        rows.append(w)
    return np.array(rows)


def nested_grid(T, feats):
    W = grid_weights(feats)
    RR = rr_matrix(T, W)
    nfeat = (W > 0).sum(1)
    classes = sorted({t["cls"] for t in T})
    chosen = {}
    for k in classes:
        tr = np.array([t["cls"] != k for t in T])
        obj = RR[tr].mean(0) - 1e-6 * nfeat          # ties -> fewer features
        chosen[k] = W[int(np.argmax(obj))]
    full = W[int(np.argmax(RR.mean(0) - 1e-6 * nfeat))]
    return chosen, full


def fit_logit(T, feats, lam=LAMBDA, iters=600, lr=0.5):
    cols = fidx(feats)
    w = np.full(len(cols), 1.0)
    Xs = [t["X"][:, cols] for t in T]
    ys = [t["y"] for t in T]
    n = len(T)
    for _ in range(iters):
        grad = -lam * w
        for X, y in zip(Xs, ys):
            z = X @ w
            p = np.exp(z - z.max())
            p /= p.sum()
            grad += X[y] - p @ X
        w = np.maximum(w + lr * grad / n, 0.0)
    full = np.zeros(len(ALL_FEATURES))
    full[cols] = w
    return full


def anchored_weights(feats, extra_w=0.5, max_extra=2):
    """Old best (symptoms + mechanism_target, weight 1) plus at most `max_extra` other features at weight
    `extra_w`: 1 + 11 + 55 = 67 settings. Added AFTER the first run (disclosed): a smaller, conservative search."""
    others = [f for f in feats if f not in OLD_BEST]
    rows = []
    for k in range(max_extra + 1):
        for combo in itertools.combinations(others, k):
            w = np.zeros(len(ALL_FEATURES))
            w[fidx(OLD_BEST)] = 1.0
            w[fidx(combo)] = extra_w
            rows.append(w)
    return np.array(rows)


def nested_anchored(T, feats):
    W = anchored_weights(feats)
    RR = rr_matrix(T, W)
    nfeat = (W > 0).sum(1)
    chosen = {}
    for k in sorted({t["cls"] for t in T}):
        tr = np.array([t["cls"] != k for t in T])
        chosen[k] = W[int(np.argmax(RR[tr].mean(0) - 1e-6 * nfeat))]
    return chosen, W[int(np.argmax(RR.mean(0) - 1e-6 * nfeat))]


def nested_logit(T, feats):
    classes = sorted({t["cls"] for t in T})
    chosen = {k: fit_logit([t for t in T if t["cls"] != k], feats) for k in classes}
    return chosen, fit_logit(T, feats)


def outer_metrics(T, chosen):
    return [metrics_from_scores(t["X"] @ chosen[t["cls"]], t["y"]) for t in T]


def fixed_metrics(T, w):
    return [metrics_from_scores(t["X"] @ w, t["y"]) for t in T]


# ---------------------------------------------------------------- aggregation + bootstrap over classes
def agg(ms):
    return {"n": len(ms), **{f"recall@{k}": statistics.mean(m[f"r@{k}"] for m in ms) for k in KS},
            "mrr": statistics.mean(m["rr"] for m in ms), "median_rank": statistics.median(m["rank"] for m in ms)}


def boot_all(T, rows, ref):
    groups = defaultdict(list)
    for i, t in enumerate(T):
        groups[t["cls"]].append(i)
    keys = sorted(groups)
    rng = random.Random(SEED)
    draws = {s: defaultdict(list) for s in rows}
    diffs = {s: [] for s in rows}
    for _ in range(B):
        ii = [i for k in (rng.choice(keys) for _ in keys) for i in groups[k]]
        ra = agg([rows[ref][i] for i in ii])
        for s in rows:
            a = agg([rows[s][i] for i in ii])
            for m in ("recall@1", "recall@3", "recall@5", "mrr"):
                draws[s][m].append(a[m])
            diffs[s].append(a["mrr"] - ra["mrr"])

    def ci(v):
        v = sorted(v)
        return [r3(v[int(0.025 * len(v))]), r3(v[min(len(v) - 1, int(0.975 * len(v)))])]
    out = {}
    for s in rows:
        p = agg(rows[s])
        out[s] = {**{m: r3(p[m]) for m in p}, "ci95": {m: ci(draws[s][m]) for m in draws[s]},
                  f"mrr_diff_vs_{ref}_ci95": ci(diffs[s]),
                  f"p_mrr_better_than_{ref}": r3(sum(1 for x in diffs[s] if x > 0) / B)}
    return out


def sub(rows, ii):
    return {s: [v[i] for i in ii] for s, v in rows.items()}


def wdict(w):
    return {f: r3(float(w[i])) for i, f in enumerate(ALL_FEATURES) if w[i] > 0}


# ---------------------------------------------------------------- known-collaboration checks
def collab(idx, cls, weights_named, seed=None):
    kd = idx.known_diseases(cls)
    res = {"therapy": cls, "known": sorted(d.split(":")[1] for d in kd), "leave_one_out": []}

    def rank_of(weights, ctx, target):
        cands = [x for x in idx.diseases if x not in ctx]
        sc = {k: round(v, 9) for k, v in idx.score_weighted(weights, cls, ctx, cands).items()}
        return tie_metrics(sc, target)["rank"], cands, sc
    for d in sorted(kd):
        ctx = kd - {d}
        row = {"held_out": d.split(":")[1], "ranks": {}}
        for name, w in weights_named.items():
            row["ranks"][name], cands, sc = rank_of(w, ctx, d)
        row["n_candidates"] = len(cands)
        res["leave_one_out"].append(row)
    if seed:
        ctx = {seed}
        out = {"seed": seed.split(":")[1]}
        for name, w in weights_named.items():
            cands = [x for x in idx.diseases if x not in ctx]
            sc = idx.score_weighted(w, cls, ctx, cands)
            ranked = sorted(cands, key=lambda x: (-round(sc[x], 9), x))
            pos = {x: i + 1 for i, x in enumerate(ranked)}
            out[name] = {"ranks_of_other_known": {x.split(":")[1]: pos[x] for x in sorted(kd - ctx)},
                         "top5": [x.split(":")[1] for x in ranked[:5]]}
        res["seed_only"] = out
    return res


def lysosomal_ordering(idx, fam):
    """Within-family ordering for miglustat: for each held-out lysosomal known disease, its rank among the
    lysosomal candidates only, per single feature."""
    cls = "therapy:miglustat"
    kd = idx.known_diseases(cls)
    lys = [d for d in idx.diseases if fam.get(d) == "Lysosomal"]
    out = {}
    for f in ALL_FEATURES:
        rs = []
        for d in sorted(kd):
            ctx = kd - {d}
            cands = [x for x in lys if x not in ctx]
            sc = {k: round(v, 9) for k, v in idx.score_weighted({f: 1.0}, cls, ctx, cands).items()}
            rs.append((d.split(":")[1], tie_metrics(sc, d)["rank"], len(cands)))
        out[f] = {"ranks_within_lysosomal": {a: b for a, b, _ in rs}, "n_lysosomal_candidates": rs[0][2],
                  "mean_rank": r3(statistics.mean(b for _a, b, _c in rs))}
    return out


# ---------------------------------------------------------------- main
def main():
    g = load_graph()
    fam = families({n["id"]: n for n in g["nodes"]})
    idx = MultiFeatureIndex(g, family=fam)
    cases = build_cases(idx)
    T = case_tensors(idx, cases)
    n = len(T)
    transfer_ii = [i for i, c in enumerate(cases) if c["context"]]
    redisc_ii = [i for i, c in enumerate(cases) if not c["context"]]

    rows, weights_report = {}, {}
    for f in ALL_FEATURES:
        w = np.zeros(len(ALL_FEATURES))
        w[ALL_FEATURES.index(f)] = 1.0
        rows["feat:" + f] = fixed_metrics(T, w)
    w_old = np.zeros(len(ALL_FEATURES))
    w_old[fidx(OLD_BEST)] = 1.0
    rows["old_best(symptoms+mechanism_target)"] = fixed_metrics(T, w_old)
    w_eq = np.zeros(len(ALL_FEATURES))
    w_eq[fidx(TUNE)] = 1.0
    rows["equal_weight_all(untuned)"] = fixed_metrics(T, w_eq)

    chosen_g, full_g = nested_grid(T, TUNE)
    rows["nested_grid"] = outer_metrics(T, chosen_g)
    chosen_l, full_l = nested_logit(T, TUNE)
    rows["nested_logit"] = outer_metrics(T, chosen_l)
    chosen_a, full_a = nested_anchored(T, TUNE)
    rows["nested_anchored(post-hoc tuner)"] = outer_metrics(T, chosen_a)
    rows["anchored_refit_in_sample(optimistic)"] = fixed_metrics(T, full_a)
    # in-sample (optimistic) scores of the refitted weights, reported only to show the optimism gap
    rows["grid_refit_in_sample(optimistic)"] = fixed_metrics(T, full_g)
    rows["logit_refit_in_sample(optimistic)"] = fixed_metrics(T, full_l)

    def stability(chosen):
        cnt = defaultdict(int)
        for w in chosen.values():
            for f in wdict(w):
                cnt[f] += 1
        return {f: f"{v}/{len(chosen)}" for f, v in sorted(cnt.items(), key=lambda x: -x[1])}
    weights_report = {
        "grid_refit_all_cases": wdict(full_g), "logit_refit_all_cases": wdict(full_l),
        "grid_feature_selected_in_outer_folds": stability(chosen_g),
        "anchored_refit_all_cases": wdict(full_a),
        "anchored_feature_selected_in_outer_folds": stability(chosen_a),
        "logit_mean_weight_over_outer_folds": {f: r3(statistics.mean(float(w[i]) for w in chosen_l.values()))
                                               for i, f in enumerate(ALL_FEATURES) if f in TUNE},
    }

    ref = "old_best(symptoms+mechanism_target)"
    results = {"all_developed_for": boot_all(T, rows, ref),
               "transfer_context_nonempty": boot_all([T[i] for i in transfer_ii], sub(rows, transfer_ii), ref),
               "rediscovery_context_empty": boot_all([T[i] for i in redisc_ii], sub(rows, redisc_ii), ref)}

    # ablation: drop one feature, re-run the whole nested procedure (both tuners) without it
    ablation = {}
    for f in TUNE:
        fs = [x for x in TUNE if x != f]
        cg, _ = nested_grid(T, fs)
        cl, _ = nested_logit(T, fs)
        ag, al = agg(outer_metrics(T, cg)), agg(outer_metrics(T, cl))
        ca, _ = nested_anchored(T, fs) if f not in OLD_BEST else (None, None)
        ablation[f] = {"nested_anchored": {k: r3(v) for k, v in agg(outer_metrics(T, ca)).items()} if ca else None,
                       "nested_grid": {k: r3(v) for k, v in ag.items()},
                       "nested_logit": {k: r3(v) for k, v in al.items()}}
    # add-one to the old best (fixed weight 1, untuned) -- descriptive
    add_one = {}
    for f in TUNE:
        if f in OLD_BEST:
            continue
        w = w_old.copy()
        w[ALL_FEATURES.index(f)] = 1.0
        add_one[f] = {k: r3(v) for k, v in agg(fixed_metrics(T, w)).items()}

    # final scorer: the procedure with the best HONEST (nested / untuned) MRR; refit weights on all cases
    ra = results["all_developed_for"]
    cand_final = {"old_best(symptoms+mechanism_target)": w_old, "nested_grid": full_g, "nested_logit": full_l,
                  "nested_anchored(post-hoc tuner)": full_a}
    final_name = max(cand_final, key=lambda k: (ra[k]["mrr"], k == "old_best(symptoms+mechanism_target)"))
    final = cand_final[final_name]
    named = {"old_best": OLD_BEST, "grid_refit": wdict(full_g), "logit_refit": wdict(full_l),
             "anchored_refit": wdict(full_a),
             "symptoms": {"symptoms": 1.0}, "mechanism_target": {"mechanism_target": 1.0},
             "reactome": {"reactome": 1.0}, "tissue": {"tissue": 1.0}, "compartment": {"compartment": 1.0},
             "phenotype_systems": {"phenotype_systems": 1.0}, "molecular_consequence": {"molecular_consequence": 1.0}}
    checks = {
        "4-phenylbutyrate (STXBP1 <-> SLC6A1)": collab(idx, "therapy:4-phenylbutyrate", named),
        "MEK inhibitors across RASopathies": collab(idx, "class:mek-inhibitors", named, seed="disease:NF1"),
        "miglustat across lysosomal diseases": collab(idx, "therapy:miglustat", named, seed="disease:GBA1"),
        "miglustat within-lysosomal ordering by single feature": lysosomal_ordering(idx, fam),
    }
    per_case = [{"therapy": c["cls"], "held_out": c["held_out"].split(":")[1],
                 "context": [x.split(":")[1] for x in c["context"]],
                 "ranks": {s: rows[s][i]["rank"] for s in ("old_best(symptoms+mechanism_target)", "nested_grid",
                                                           "nested_logit", "nested_anchored(post-hoc tuner)")}} for i, c in enumerate(cases)]
    out = {
        "generated_by": "pipeline/eval/feature_eval.py",
        "features": {f: FEATURE_DOC[f] for f in ALL_FEATURES},
        "feature_coverage": idx.fx and json.loads((ROOT / "data/derived/features/atlas_features.json").read_text())["meta"]["coverage"],
        "design": {"cases": n, "therapy_classes": len({t['cls'] for t in T}), "transfer_cases": len(transfer_ii),
                   "outer_cv": "leave-one-therapy-class-out (all cases of a class held out together)",
                   "grid": "w in {0,1} per feature (%d features, %d settings), objective inner MRR, ties -> fewer "
                           "features" % (len(TUNE), 2 ** len(TUNE) - 1),
                   "logit": f"conditional logit, w >= 0, L2 lambda={LAMBDA}, projected gradient",
                   "excluded_from_tuning": ["shared_gene (constant 0: no two atlas diseases share a causal gene)"],
                   "ci": f"95% bootstrap over therapy classes, {B} draws, seed {SEED}",
                   "normalisation": "each feature divided by its max over the query's candidates"},
        "results": results,
        "weights": weights_report,
        "final_procedure": final_name,
        "final_weights_refit_all_cases": wdict(final),
        "ablation_drop_one_nested": ablation,
        "add_one_to_old_best_untuned": add_one,
        "known_collaboration_checks": checks,
        "per_case_ranks": per_case,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":"), default=float))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    for name in ("all_developed_for", "transfer_context_nonempty"):
        print(f"\n## {name}")
        for s, x in results[name].items():
            c = x["ci95"]
            print(f"{s:42s} R@1 {x['recall@1']:.2f} R@3 {x['recall@3']:.2f} R@5 {x['recall@5']:.2f} "
                  f"[{c['recall@5'][0]:.2f}-{c['recall@5'][1]:.2f}] MRR {x['mrr']:.3f} [{c['mrr'][0]:.2f}-{c['mrr'][1]:.2f}]"
                  f" P>old {x[f'p_mrr_better_than_{ref}']}")
    print("\nweights", json.dumps(weights_report, indent=1))
    print("\nablation (MRR grid / logit)")
    for f, a in ablation.items():
        an = a["nested_anchored"]["mrr"] if a["nested_anchored"] else float("nan")
        print(f"  -{f:24s} anchored {an:.3f} grid {a['nested_grid']['mrr']:.3f} / logit {a['nested_logit']['mrr']:.3f}   R@5 "
              f"{a['nested_grid']['recall@5']:.2f} / {a['nested_logit']['recall@5']:.2f}")
    print("\nadd one to old best", {f: (a["mrr"], a["recall@5"]) for f, a in add_one.items()})


if __name__ == "__main__":
    main()
