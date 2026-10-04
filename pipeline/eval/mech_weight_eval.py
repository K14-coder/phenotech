"""Mechanism weighting search for the therapy-transfer benchmark, with nested cross-validation.

Run:  python3 pipeline/eval/mech_weight_eval.py        (stdlib only, ~1 min, offline)
Writes data/derived/eval_mech_weights.json.

Benchmark = the 56 developed_for leave-one-out cases of transfer_eval.py (same cases, same filtered ranking,
same expected-value ties). The site's scorer is pheno+mech:
    score(d) = w_pheno * phenotype(d)/max + (1 - w_pheno) * mechanism(d)/max
    mechanism(d) = sum over the therapy's target mechanisms m of chain_w(d, m) * idf(m)^alpha * generic(m)
Knobs searched (current default in brackets):
    chain weight of variant_group chains   {0, 0.4, 0.8, 1.0}   [0.8]   (driven_by fixed at 1.0)
    chain weight of pathway chains          {0, 0.35, 0.7, 1.0}  [0.7]
    generic-class multiplier (LoF, HI, GoF, DN)  {0, 0.25, 0.5, 1}  [1]
    IDF exponent alpha                      {0, 0.5, 1, 2}       [1]
    phenotype weight w_pheno                {0, 0.25, 0.5, 0.75} [0.5]
A chain weight of 0 removes that chain kind, and IDF is recomputed from the diseases that still reach m.

Honest estimate: nested CV grouped by therapy class (outer: hold out all cases of one class; inner: pick the
setting with the best MRR on the other classes, ties -> closest to the default). In-sample best settings are
reported too, but they are optimistic by construction (KNOWLEDGE.md: non-nested tuning inflated MRR by
about 0.03-0.05).
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from transfer_eval import build_cases, families, tie_metrics  # noqa: E402
from transfer_score import ROOT, TransferIndex, load_graph  # noqa: E402

OUT = ROOT / "data" / "derived" / "eval_mech_weights.json"
GENERIC = {"mech:loss-of-function", "mech:haploinsufficiency", "mech:gain-of-function", "mech:dominant-negative"}
GRID = {
    "variant_group": [0.0, 0.4, 0.8, 1.0],
    "pathway": [0.0, 0.35, 0.7, 1.0],
    "generic": [0.0, 0.25, 0.5, 1.0],
    "alpha": [0.0, 0.5, 1.0, 2.0],
    "w_pheno": [0.0, 0.25, 0.5, 0.75],
}
DEFAULT = {"variant_group": 0.8, "pathway": 0.7, "generic": 1.0, "alpha": 1.0, "w_pheno": 0.5}
B = 1000
SEED = 7


def setting_key(s):
    return tuple(s[k] for k in GRID)


def distance(s):
    return sum(abs(GRID[k].index(s[k]) - GRID[k].index(DEFAULT[k])) for k in GRID)


class Scorer:
    def __init__(self, idx, cases):
        self.idx = idx
        self.cases = cases
        N = len(idx.diseases)
        self.N = N
        # kinds of chain per (disease, mechanism)
        self.kinds = {d: {m: {k for k, _ in chs} for m, chs in idx.chains[d].items()} for d in idx.diseases}
        # phenotype component per case (fixed)
        self.ph = []
        self.cands = []
        for c in cases:
            cands = [d for d in idx.diseases if d not in set(c["context"])]
            self.cands.append(cands)
            self.ph.append({d: idx.s_phenotype(c["cls"], set(c["context"]), d) for d in cands})

    def metrics(self, s):
        cw = {"driven_by": 1.0, "variant_group": s["variant_group"], "pathway": s["pathway"]}
        prof = {}
        df = defaultdict(int)
        for d, ms in self.kinds.items():
            p = {}
            for m, ks in ms.items():
                w = max(cw[k] for k in ks)
                if w > 0:
                    p[m] = w
                    df[m] += 1
            prof[d] = p
        idf = {m: math.log((self.N + 1) / (n + 1)) ** s["alpha"] if s["alpha"] else 1.0 for m, n in df.items()}
        out = []
        for c, cands, ph in zip(self.cases, self.cands, self.ph):
            tg = self.idx.targets.get(c["cls"], ())
            me = {d: sum(prof[d].get(m, 0.0) * idf.get(m, 0.0) * (s["generic"] if m in GENERIC else 1.0) for m in tg)
                  for d in cands}
            mp, mm = max(ph.values(), default=0.0), max(me.values(), default=0.0)
            w = s["w_pheno"]
            sc = {d: round(w * (ph[d] / mp if mp else 0.0) + (1 - w) * (me[d] / mm if mm else 0.0), 9) for d in cands}
            out.append(tie_metrics(sc, c["held_out"]))
        return out


def summary(ms):
    return {"n": len(ms), "recall@1": statistics.mean(m["r@1"] for m in ms), "recall@5": statistics.mean(m["r@5"] for m in ms),
            "mrr": statistics.mean(m["rr"] for m in ms)}


def r3(x):
    return round(x, 3)


def main():
    g = load_graph()
    idx = TransferIndex(g, family=families({n["id"]: n for n in g["nodes"]}))
    cases = build_cases(idx)
    S = Scorer(idx, cases)
    settings = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    per = {setting_key(s): S.metrics(s) for s in settings}
    base = summary(per[setting_key(DEFAULT)])
    print(f"default {DEFAULT}: n={base['n']} R@5={base['recall@5']:.3f} MRR={base['mrr']:.3f}")

    # one knob at a time from the default
    sweeps = {}
    for k, vals in GRID.items():
        sweeps[k] = []
        for v in vals:
            s = {**DEFAULT, k: v}
            m = summary(per[setting_key(s)])
            sweeps[k].append({"value": v, "recall@5": r3(m["recall@5"]), "mrr": r3(m["mrr"])})
            print(f"  {k:14s}={v:<5} R@5={m['recall@5']:.3f} MRR={m['mrr']:.3f}")

    # in-sample ranking (optimistic)
    ranked = sorted(settings, key=lambda s: (-summary(per[setting_key(s)])["mrr"], distance(s)))
    top = [{"setting": s, **{k: r3(v) for k, v in summary(per[setting_key(s)]).items() if k != "n"}} for s in ranked[:10]]

    # nested CV grouped by therapy class
    groups = defaultdict(list)
    for i, c in enumerate(cases):
        groups[c["cls"]].append(i)
    nested_rows = [None] * len(cases)
    chosen = []
    for cls, held in groups.items():
        train = [i for i in range(len(cases)) if i not in set(held)]
        best = min(settings, key=lambda s: (-statistics.mean(per[setting_key(s)][i]["rr"] for i in train), distance(s)))
        chosen.append(best)
        for i in held:
            nested_rows[i] = per[setting_key(best)][i]
    nested = summary(nested_rows)
    print(f"nested CV: R@5={nested['recall@5']:.3f} MRR={nested['mrr']:.3f} (default {base['recall@5']:.3f} / {base['mrr']:.3f})")

    # class-level bootstrap of nested - default
    rng = random.Random(SEED)
    keys = sorted(groups)
    d_mrr, d_r5 = [], []
    for _ in range(B):
        ii = [i for k in (rng.choice(keys) for _ in keys) for i in groups[k]]
        d_mrr.append(statistics.mean(nested_rows[i]["rr"] - per[setting_key(DEFAULT)][i]["rr"] for i in ii))
        d_r5.append(statistics.mean(nested_rows[i]["r@5"] - per[setting_key(DEFAULT)][i]["r@5"] for i in ii))
    ci = lambda v: [r3(sorted(v)[int(0.025 * B)]), r3(sorted(v)[int(0.975 * B)])]
    stab = {k: dict(sorted(((str(v), sum(1 for s in chosen if s[k] == v)) for v in GRID[k]), key=lambda x: -x[1])) for k in GRID}

    # extra checks: finer phenotype weight; evidence-level down-weighting of mechanism chains
    fine = {}
    for w in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7):
        m = summary(S.metrics({**DEFAULT, "w_pheno": w}))
        fine[str(w)] = {"recall@5": r3(m["recall@5"]), "mrr": r3(m["mrr"])}
    E = {e["id"]: e for e in g["edges"]}
    level = {}
    for name, lv in (("off", {}), ("observational 0.8, inferred 0.5", {"observational": 0.8, "inferred": 0.5}),
                     ("observational 0.5, inferred 0.25", {"observational": 0.5, "inferred": 0.25})):
        ms = []
        cwd = {"driven_by": 1.0, "variant_group": DEFAULT["variant_group"], "pathway": DEFAULT["pathway"]}
        for c, cands, ph in zip(S.cases, S.cands, S.ph):
            tg = idx.targets.get(c["cls"], ())
            me = {}
            for d in cands:
                tot = 0.0
                for m in tg:
                    best = max((cwd[k] * min(lv.get(E[x]["evidence_level"], 1.0) for x in eids) for k, eids in idx.chains[d].get(m, ())), default=0.0)
                    tot += best * idx.idf.get(m, 0.0)
                me[d] = tot
            mp, mm = max(ph.values()), max(me.values())
            sc = {d: round(0.5 * (ph[d] / mp if mp else 0) + 0.5 * (me[d] / mm if mm else 0), 9) for d in cands}
            ms.append(tie_metrics(sc, c["held_out"]))
        m = summary(ms)
        level[name] = {"recall@5": r3(m["recall@5"]), "mrr": r3(m["mrr"])}
    ntg = defaultdict(int)
    for c in cases:
        ntg[len(idx.targets.get(c["cls"], ()))] += 1
    best_mrr = max(statistics.mean(m["rr"] for m in v) for v in per.values())
    ties = sum(1 for v in per.values() if abs(statistics.mean(m["rr"] for m in v) - best_mrr) < 1e-9)
    print("fine w_pheno", json.dumps(fine)); print("evidence-level", json.dumps(level)); print("cases by number of target mechanisms", dict(ntg), "settings tying best", ties)

    out = {
        "generated_by": "pipeline/eval/mech_weight_eval.py",
        "cases_by_number_of_target_mechanisms": dict(ntg), "settings_tying_best_mrr": ties,
        "w_pheno_fine": fine, "evidence_level_weighting": level,
        "cases": len(cases), "settings": len(settings), "grid": GRID, "default": DEFAULT,
        "default_result": {k: r3(v) for k, v in base.items()},
        "one_knob_sweeps": sweeps,
        "in_sample_top10_optimistic": top,
        "nested_cv": {**{k: r3(v) for k, v in nested.items()}, "outer_folds": len(groups),
                      "delta_vs_default_mrr": r3(nested["mrr"] - base["mrr"]), "delta_mrr_95ci": ci(d_mrr),
                      "delta_vs_default_recall@5": r3(nested["recall@5"] - base["recall@5"]), "delta_recall@5_95ci": ci(d_r5),
                      "chosen_values_over_folds": stab},
    }
    OUT.write_text(json.dumps(out, indent=1))
    print("in-sample best:", json.dumps(top[0]))
    print("delta MRR 95% CI", ci(d_mrr), "delta R@5 95% CI", ci(d_r5))
    print("chosen over folds:", json.dumps(stab))


if __name__ == "__main__":
    main()
