"""Direction-aware therapy matching: does "drug lowers function + disease has too much" (or the reverse) help?

    uv run -q --with pyarrow --with pandas python3 pipeline/ingest/direction_build.py   # data/derived/direction/
    uv run -q --with numpy --with scipy python3 pipeline/eval/direction_eval.py         # ~30 s, offline, no OpenAI

Output: data/derived/eval_direction.json

Compatibility c(drug, disease) in {-1, 0, +1}:
  * direct: a drug target (ChEMBL action with a known direction) is a causal gene of the disease that has a
    direction call. decrease + GoF or increase + LoF -> +1 (match); the opposite -> -1 (mismatch); both or
    neither -> 0 (neutral).
  * pathway (variant "direct+pathway"): when there is no direct hit, a drug target that shares a small
    lowest-level Reactome pathway (<= 60 genes) with a directed disease gene gives +-0.5 by the same rule.
Score = base + bonus * max(c, 0) - penalty * max(-c, 0), base = the production scorer
phenotype/max + 0.5 genes/max + 0.5 pathway_full/max (docs/agent-reports/ingest.md section 5).
Control: an UNDIRECTED target bonus (any drug target is a disease gene, direction ignored), so a gain from
"target = disease gene" is not mistaken for a gain from direction.

(a) PrimeKG indications, nested 5-fold CV over drug groups for (variant, bonus, penalty); bootstrap over
    drug groups. (b) PrimeKG contraindications: percentile shift (context = all indications).
(c) Atlas: sodium-channel cases from data/curated/family_dee.json and the 56-case eval.md benchmark.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "eval"))
import primekg_eval as pe  # noqa: E402

DIRD = ROOT / "data/derived/direction"
RAW = ROOT / "data/raw/downloads"
OUT = ROOT / "data/derived/eval_direction.json"
GRID = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0)
PATH_MAX_GENES = 60


def load_direction(fallback=False):
    gd = json.load(open(DIRD / "gene_direction.json"))
    dd = json.load(open(DIRD / "drug_direction.json"))
    by_dis = gd["by_disease"]
    gene_fb = {}
    if fallback:   # gene-level call, only when every MONDO entry of the gene agrees
        tmp = defaultdict(set)
        for m, gs in by_dis.items():
            for g, r in gs.items():
                tmp[g].add(r["direction"])
        gene_fb = {g: next(iter(s)) for g, s in tmp.items() if len(s) == 1 and next(iter(s)) in ("LoF", "GoF")}
    return gd, dd, by_dis, gene_fb


def small_pathways():
    sym2ncbi = {}
    for line in open(RAW / "genes_to_disease.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if p[0].startswith("NCBIGene:"):
            sym2ncbi.setdefault(p[1], p[0].split(":")[1])
    pw = defaultdict(set)
    for line in open(RAW / "NCBI2Reactome.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 6 and p[5] == "Homo sapiens":
            pw[p[1]].add(p[0])
    ncbi2sym = {v: k for k, v in sym2ncbi.items()}
    gene_pw = defaultdict(set)
    for pid, gs in pw.items():
        if len(gs) <= PATH_MAX_GENES:
            for n in gs:
                if n in ncbi2sym:
                    gene_pw[ncbi2sym[n]].add(pid)
    return gene_pw


def sign(drug_dir, dis_dir):
    if drug_dir == "decrease":
        return 1 if dis_dir == "GoF" else -1
    return 1 if dis_dir == "LoF" else -1


def compat(actions, dis_genes_dir, gene_pw, use_path):
    """actions: [(direction, set(targets))]; dis_genes_dir: {gene: 'LoF'|'GoF'}. Returns c, basis."""
    pos = neg = 0
    basis = []
    for dr, tg in actions:
        for g, gd in dis_genes_dir.items():
            if g in tg:
                s = sign(dr, gd)
                pos += s > 0
                neg += s < 0
                basis.append((g, gd, dr, "direct"))
    if pos or neg:
        return (1.0 if pos and not neg else -1.0 if neg and not pos else 0.0), basis
    if not use_path:
        return 0.0, basis
    for dr, tg in actions:
        tp = set().union(*[gene_pw.get(t, set()) for t in tg]) if tg else set()
        for g, gd in dis_genes_dir.items():
            if gene_pw.get(g, set()) & tp:
                s = sign(dr, gd)
                pos += s > 0
                neg += s < 0
                basis.append((g, gd, dr, "pathway"))
    return (0.5 if pos and not neg else -0.5 if neg and not pos else 0.0), basis


def node_dirs(bench, by_dis, gene_fb):
    out = {}
    for k in bench["pool"]:
        n = bench["nodes"][k]
        acc = defaultdict(lambda: [0.0, 0.0])
        for m in n["index_ids"]:
            for g, r in by_dis.get(m, {}).items():
                if r["direction"] in ("LoF", "GoF", "mixed"):
                    acc[g][0] += r["lof"]
                    acc[g][1] += r["gof"]
        d = {}
        for g, (lo, go) in acc.items():
            if go >= 2 * lo and go > 0:
                d[g] = "GoF"
            elif lo >= 2 * go and lo > 0:
                d[g] = "LoF"
        for g in n["genes"]:
            if g not in d and g not in acc and g in gene_fb:
                d[g] = gene_fb[g]
        out[k] = {g: v for g, v in d.items() if g in set(n["genes"]) or True}
    return out


def drug_actions(dd, db):
    v = dd["drugbank"].get(db)
    if not v:
        return [], set()
    acts = [(a["direction"], set(a["targets"])) for a in v["actions"] if a["direction"] and a["targets"]]
    alltg = set().union(*[set(a["targets"]) for a in v["actions"]]) if v["actions"] else set()
    return acts, alltg


def boot_ci(v, groups_idx, draws):
    gs = np.array([v[ix].sum() for ix in groups_idx])
    gc = np.array([len(ix) for ix in groups_idx])
    bs = (draws @ gs) / np.maximum(draws @ gc, 1)
    return [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)], bs


# ====================================================================== (a) + (b) PrimeKG
def primekg(fallback=False):
    t0 = time.time()
    bench = json.load(open(pe.ING / "primekg_benchmark.json"))
    sims, cover = pe.build_similarities(bench)
    X, tgt, mask, meta = pe.build_cases(bench, sims)
    C, N, F = X.shape
    fi = {f: i for i, f in enumerate(pe.FEATURES)}
    wbase = np.zeros(F, np.float32)
    wbase[fi["phenotype"]], wbase[fi["genes"]], wbase[fi["pathway_full"]] = 1, 0.5, 0.5
    base = X @ wbase

    gd, dd, by_dis, gene_fb = load_direction(fallback)
    gene_pw = small_pathways()
    pool = bench["pool"]
    pos_of = {k: i for i, k in enumerate(pool)}
    ndir = node_dirs(bench, by_dis, gene_fb)
    drugs = sorted(bench["drugs"])
    D = len(drugs)
    Cd = np.zeros((D, N), np.float32)      # direct
    Cp = np.zeros((D, N), np.float32)      # direct + pathway
    U = np.zeros((D, N), np.float32)       # undirected: any target is a disease gene
    Up = np.zeros((D, N), np.float32)      # undirected incl. small pathway
    drug_has_dir = np.zeros(D, bool)
    for a, db in enumerate(drugs):
        acts, alltg = drug_actions(dd, db)
        drug_has_dir[a] = bool(acts)
        tpw = set().union(*[gene_pw.get(t, set()) for t in alltg]) if alltg else set()
        for j, k in enumerate(pool):
            gs = set(bench["nodes"][k]["genes"])
            if alltg & gs:
                U[a, j] = 1
                Up[a, j] = 1
            elif tpw and any(gene_pw.get(g, set()) & tpw for g in gs):
                Up[a, j] = 0.5
            if acts and ndir[k]:
                Cd[a, j], _ = compat(acts, ndir[k], gene_pw, False)
                Cp[a, j], _ = compat(acts, ndir[k], gene_pw, True)
    didx = {d: i for i, d in enumerate(drugs)}
    case_drug = np.array([didx[m[0]] for m in meta])
    comp = {"direct": Cd[case_drug], "direct+pathway": Cp[case_drug]}
    undirected = {"direct": U[case_drug], "direct+pathway": Up[case_drug]}

    grp_of = pe.drug_groups(bench["drugs"])
    gnames = sorted(set(grp_of.values()))
    gidx = {g: i for i, g in enumerate(gnames)}
    case_group = np.array([gidx[grp_of[m[0]]] for m in meta])
    groups_idx = [np.where(case_group == i)[0] for i in range(len(gnames))]
    rng = np.random.default_rng(pe.SEED)
    draws = rng.multinomial(len(gnames), np.ones(len(gnames)) / len(gnames), size=pe.N_BOOT).astype(np.float64)
    K = 5
    perm = np.random.default_rng(pe.SEED + 1).permutation(len(gnames))
    fold_of_group = np.empty(len(gnames), int)
    fold_of_group[perm] = np.arange(len(gnames)) % K
    fold = fold_of_group[case_group]

    def per_case(scores):
        gt, eq = pe.rank_stats(scores, tgt, mask)
        return pe.metrics_from(gt, eq)

    # candidate settings
    settings = [("base", None, 0.0, 0.0)]
    for var in comp:
        for b in GRID:
            for p in GRID:
                if b or p:
                    settings.append(("dir", var, b, p))
    und_settings = [("base", None, 0.0, 0.0)] + [("und", var, b, 0.0) for var in undirected for b in GRID if b]
    cache = {}

    def run_setting(s):
        if s in cache:
            return cache[s]
        kind, var, b, p = s
        if kind == "base":
            sc = base
        elif kind == "dir":
            c = comp[var]
            sc = base + b * np.maximum(c, 0) - p * np.maximum(-c, 0)
        else:
            sc = base + b * undirected[var]
        cache[s] = per_case(sc)
        return cache[s]

    def nested(cands):
        rr = np.zeros(C)
        r = {k: np.zeros(C) for k in pe.KS}
        chosen = []
        for k in range(K):
            tr, te = fold != k, fold == k
            best = max(cands, key=lambda s: (run_setting(s)["rr"][tr].mean(), -(s[2] + s[3])))
            chosen.append(best)
            m = run_setting(best)
            rr[te] = m["rr"][te]
            for kk in pe.KS:
                r[kk][te] = m[f"r@{kk}"][te]
        return {"rr": rr, **{f"r@{kk}": r[kk] for kk in pe.KS}}, chosen

    res = {}
    per = {}

    def report(name, m):
        per[name] = m["rr"]
        out = {}
        for key in ["rr"] + [f"r@{k}" for k in pe.KS]:
            out[key] = round(float(m[key].mean()), 4)
            out[key + "_ci"], _ = boot_ci(m[key], groups_idx, draws)
        res[name] = out

    report("base (phen + 0.5 genes + 0.5 pathway)", run_setting(settings[0]))
    m_dir, ch_dir = nested(settings)
    report("nested direction-aware", m_dir)
    m_und, ch_und = nested(und_settings)
    report("nested undirected target bonus (control)", m_und)
    m_dir_only, ch_do = nested([s for s in settings if s[0] == "base" or s[1] == "direct"])
    report("nested direction-aware, direct only", m_dir_only)
    for s in [("dir", "direct", 0.5, 0.5), ("dir", "direct+pathway", 0.5, 0.5), ("dir", "direct", 1.0, 1.0),
              ("dir", "direct", 0.0, 1.0), ("dir", "direct", 1.0, 0.0), ("und", "direct", 0.5, 0.0)]:
        report(f"fixed {s[0]} {s[1]} bonus {s[2]} penalty {s[3]}", run_setting(s))
    best_in = max(settings, key=lambda s: run_setting(s)["rr"].mean())
    report(f"in-sample best {best_in} (optimistic)", run_setting(best_in))

    paired = {}
    b0 = per["base (phen + 0.5 genes + 0.5 pathway)"]
    for n, v in per.items():
        if n.startswith("base"):
            continue
        ci, bs = boot_ci(v - b0, groups_idx, draws)
        paired[n] = {"diff": round(float((v - b0).mean()), 4), "ci": ci, "p_better": round(float((bs > 0).mean()), 3)}
    ci, bs = boot_ci(per["nested direction-aware"] - per["nested undirected target bonus (control)"], groups_idx, draws)
    paired["nested direction-aware minus undirected control"] = {
        "diff": round(float((per["nested direction-aware"] - per["nested undirected target bonus (control)"]).mean()), 4),
        "ci": ci, "p_better": round(float((bs > 0).mean()), 3)}

    # coverage + sign agreement
    pool_dir = sum(1 for k in pool if ndir[k])
    held_c = comp["direct"][np.arange(C), tgt]
    held_cp = comp["direct+pathway"][np.arange(C), tgt]
    allc = comp["direct"][mask]
    cov = {"benchmark_drugs": D, "drugs_with_directed_chembl_action": int(drug_has_dir.sum()),
           "drugs_in_chembl_moa_at_all": int(sum(1 for d in drugs if d in dd["drugbank"])),
           "pool_diseases": N, "pool_diseases_with_directed_gene": pool_dir,
           "cases": C,
           "cases_heldout_direct_nonzero": int((held_c != 0).sum()),
           "cases_heldout_direct_match": int((held_c > 0).sum()), "cases_heldout_direct_mismatch": int((held_c < 0).sum()),
           "cases_heldout_path_nonzero": int((held_cp != 0).sum()),
           "cases_heldout_path_match": int((held_cp > 0).sum()), "cases_heldout_path_mismatch": int((held_cp < 0).sum()),
           "candidate_pairs_direct_nonzero_frac": round(float((allc != 0).mean()), 4),
           "candidate_pairs_direct_match_frac": round(float((allc > 0).mean()), 4),
           "candidate_pairs_direct_mismatch_frac": round(float((allc < 0).mean()), 4),
           "cases_heldout_undirected_target_hit": int((undirected["direct"][np.arange(C), tgt] > 0).sum())}

    # (b) contraindications
    contra_rows = []
    for d, v in sorted(bench["drugs"].items()):
        ctr = [pos_of[k] for k in v["contraindication"] if k not in v["indication"]]
        if not ctr:
            continue
        ind = [pos_of[k] for k in v["indication"]]
        m = np.ones(N, bool)
        m[ind] = False
        m[[pos_of[k] for k in v["offlabel"]]] = False
        S = np.stack([sims[f] for f in pe.FEATURES])
        sc = S[:, ind, :].max(axis=1)
        mx = np.where(m[None, :], sc, 0).max(axis=1)
        sc = np.where(mx[:, None] > 0, sc / np.where(mx > 0, mx, 1)[:, None], 0).T
        a = didx[d]
        for c in ctr:
            contra_rows.append((d, c, sc @ wbase, m, Cd[a], Cp[a], U[a]))

    def pct(s, m, c):
        cand = s[m]
        gt = (cand > s[c]).sum()
        eq = (cand == s[c]).sum() - (1 if m[c] else 0)
        return (gt + eq / 2) / max(1, m.sum() - 1)

    def contra_eval(var, b, p, und=0.0):
        rows = []
        for d, c, bs_, m, cd, cp, u in contra_rows:
            cc = cd if var == "direct" else cp
            s1 = bs_ + b * np.maximum(cc, 0) - p * np.maximum(-cc, 0) + und * u
            rows.append((d, c, pct(bs_, m, c), pct(s1, m, c), float(cc[c])))
        return rows

    cgrp = lambda d: gidx[grp_of[d]]
    contra = {}
    refit = max(settings, key=lambda s: run_setting(s)["rr"].mean())
    for name, (var, b, p, und) in {
        "fixed direct bonus 0.5 penalty 0.5": ("direct", 0.5, 0.5, 0),
        "fixed direct+pathway bonus 0.5 penalty 0.5": ("direct+pathway", 0.5, 0.5, 0),
        "fixed direct bonus 1 penalty 1": ("direct", 1.0, 1.0, 0),
        f"refit {refit}": (refit[1] or "direct", refit[2], refit[3], 0),
        "undirected target bonus 0.5 (control)": ("direct", 0, 0, 0.5),
    }.items():
        rows = contra_eval(var, b, p, und)
        before = np.array([r[2] for r in rows])
        after = np.array([r[3] for r in rows])
        shift = after - before
        gi = np.array([cgrp(r[0]) for r in rows])
        gix = [np.where(gi == i)[0] for i in range(len(gnames))]
        gix = [ix for ix in gix if len(ix)]
        dr = rng.multinomial(len(gix), np.ones(len(gix)) / len(gix), size=pe.N_BOOT).astype(np.float64)
        ci, _ = boot_ci(shift, gix, dr)
        nz = np.array([r[4] != 0 for r in rows])
        contra[name] = {"n_pairs": len(rows), "mean_percentile_before": round(float(before.mean()), 4),
                        "mean_percentile_after": round(float(after.mean()), 4),
                        "mean_shift_toward_bottom": round(float(shift.mean()), 4), "shift_ci": ci,
                        "pairs_with_direction_signal": int(nz.sum()),
                        "pairs_mismatch": int(sum(1 for r in rows if r[4] < 0)),
                        "pairs_match": int(sum(1 for r in rows if r[4] > 0)),
                        "shift_on_signal_pairs": round(float(shift[nz].mean()), 4) if nz.any() else None,
                        "before_on_signal_pairs": round(float(before[nz].mean()), 4) if nz.any() else None,
                        "after_on_signal_pairs": round(float(after[nz].mean()), 4) if nz.any() else None}
    # sign agreement among labelled pairs: indications vs contraindications vs all other candidate pairs
    ind_pairs = [(didx[d], pos_of[k]) for d, v in bench["drugs"].items() for k in v["indication"]]
    con_pairs = [(didx[r[0]], r[1]) for r in contra_rows]
    def sign_tab(pairs, M):
        v = np.array([M[a, j] for a, j in pairs])
        return {"n": len(v), "nonzero": int((v != 0).sum()), "match": int((v > 0).sum()), "mismatch": int((v < 0).sum())}
    sign_agreement = {var: {"indications": sign_tab(ind_pairs, M), "contraindications": sign_tab(con_pairs, M),
                            "all_drug_x_pool_pairs": {"n": int(M.size), "nonzero": int((M != 0).sum()),
                                                      "match": int((M > 0).sum()), "mismatch": int((M < 0).sum())}}
                      for var, M in (("direct", Cd), ("direct+pathway", Cp))}
    # examples of mismatch on contraindications and mismatch on indications
    names = {k: bench["nodes"][k]["name"] for k in pool}
    ex_con = []
    for d, c, b_, a_, cc in contra_eval("direct", 0.5, 0.5):
        if cc != 0 and len(ex_con) < 25:
            acts, _ = drug_actions(dd, d)
            _, basis = compat(acts, ndir[pool[c]], gene_pw, False)
            ex_con.append({"drug": bench["drugs"][d]["name"], "disease": names[pool[c]], "c": cc,
                           "basis": sorted({f"{g} {gd} / drug {dr}" for g, gd, dr, _k in basis})[:4],
                           "pct_before": round(b_, 3), "pct_after": round(a_, 3)})
    ex_ind_mis = []
    for i in np.where(held_c < 0)[0][:25]:
        d = meta[i][0]
        acts, _ = drug_actions(dd, d)
        _, basis = compat(acts, ndir[pool[tgt[i]]], gene_pw, False)
        ex_ind_mis.append({"drug": bench["drugs"][d]["name"], "disease": names[pool[tgt[i]]],
                           "basis": sorted({f"{g} {gd} / drug {dr}" for g, gd, dr, _k in basis})[:4]})
    ex_ind_match = []
    for i in np.where(held_c > 0)[0][:25]:
        d = meta[i][0]
        acts, _ = drug_actions(dd, d)
        _, basis = compat(acts, ndir[pool[tgt[i]]], gene_pw, False)
        ex_ind_match.append({"drug": bench["drugs"][d]["name"], "disease": names[pool[tgt[i]]],
                             "basis": sorted({f"{g} {gd} / drug {dr}" for g, gd, dr, _k in basis})[:4]})
    print(f"primekg done {time.time()-t0:.0f}s", flush=True)
    return {"results": res, "paired_vs_base": paired, "coverage": cov,
            "nested_choices_direction": [list(map(str, s)) for s in ch_dir],
            "nested_choices_undirected": [list(map(str, s)) for s in ch_und],
            "contraindications": contra, "sign_agreement": sign_agreement,
            "examples": {"contraindication_pairs_with_signal": ex_con, "indications_scored_mismatch": ex_ind_mis,
                         "indications_scored_match": ex_ind_match}}


# ====================================================================== (c) atlas
def atlas():
    import transfer_eval as te
    from transfer_score import TransferIndex, load_graph, DirectionIndex
    g = load_graph()
    fam = te.families({n["id"]: n for n in g["nodes"]})
    idx = DirectionIndex(g, family=fam)
    cases = te.build_cases(idx)
    out = {"n_cases": len(cases)}
    # coverage
    dirs = {d: idx.disease_direction(d) for d in idx.diseases}
    out["coverage"] = {"diseases": len(idx.diseases),
                       "diseases_by_direction": {k: sum(1 for v in dirs.values() if v == k) for k in ("LoF", "GoF", "mixed", None)},
                       "therapy_classes_with_direction": sum(1 for c in idx.members if idx.class_direction(c)[0]),
                       "therapy_classes": len(idx.members),
                       "cases_heldout_nonzero": 0, "cases_heldout_match": 0, "cases_heldout_mismatch": 0}
    for c in cases:
        v = idx.s_direction(c["cls"], c["context"], c["held_out"])
        out["coverage"]["cases_heldout_nonzero"] += v != 0
        out["coverage"]["cases_heldout_match"] += v > 0
        out["coverage"]["cases_heldout_mismatch"] += v < 0
    res = {}
    for name, (b, p) in {"pheno+mech (production, eval.md d)": (0, 0), "pheno+mech+direction 0.5/0.5": (0.5, 0.5),
                         "pheno+mech+direction 1/1": (1.0, 1.0), "pheno+mech+direction 0.25/0.25": (0.25, 0.25),
                         "pheno+mech+direction penalty only 0.5": (0, 0.5)}.items():
        ms = []
        for c in cases:
            cands = [d for d in idx.diseases if d not in set(c["context"])]
            sc = idx.score_direction(c["cls"], c["context"], cands, bonus=b, penalty=p)
            ms.append(te.tie_metrics({d: round(v, 9) for d, v in sc.items()}, c["held_out"]))
        res[name] = {k: round(v, 4) for k, v in te.agg(ms).items()}
    # leakage control: the same bonus for "therapy target gene == candidate's gene", direction ignored
    def und_targets(cls):
        tg = set()
        for t in idx.members.get(cls, [cls]):
            v = idx.ther_dir.get(t)
            if v:
                tg |= set(v["targets"])
        return tg
    for b in (0.5,):
        ms = []
        for c in cases:
            cands = [d for d in idx.diseases if d not in set(c["context"])]
            base = TransferIndex.score(idx, "pheno+mech", c["cls"], c["context"], cands)
            tg = und_targets(c["cls"])
            sc = {d: base[d] + (b if idx.gene_of.get(d) in tg else 0) for d in cands}
            ms.append(te.tie_metrics({d: round(v, 9) for d, v in sc.items()}, c["held_out"]))
        res[f"pheno+mech+UNDIRECTED target-gene bonus {b} (leakage control)"] = {k: round(v, 4) for k, v in te.agg(ms).items()}
    # where do the curated targets come from? share of held-out diseases whose gene is a listed target
    out["coverage"]["cases_heldout_gene_is_listed_target"] = sum(
        1 for c in cases if idx.gene_of.get(c["held_out"]) in und_targets(c["cls"]))
    out["benchmark"] = res
    # sodium channel and other contested pairs (counter_evidence)
    dee = json.load(open(ROOT / "data/curated/family_dee.json"))
    gdir = json.load(open(DIRD / "gene_direction.json"))
    vgd = gdir["atlas_variant_groups"]
    rows = []
    for e in dee["edges"]:
        if e["type"] != "developed_for" or not e.get("counter_evidence"):
            continue
        t, d = e["source"], e["target"]
        cls = idx.class_of.get(t, t)
        dr, tg = idx.class_direction(cls)
        gene = idx.gene_of.get(d)
        sub = []
        for vg, v in vgd.items():
            if v["gene"] == gene and dr and gene in tg:
                for s in v["sides"]:
                    sub.append({"variant_group": vg, "side": s["side"], "level": s["level"],
                                "compat": sign(dr, s["side"])})
        rows.append({"therapy": t, "disease": d, "drug_direction": dr, "drug_targets": sorted(tg),
                     "gene_level_direction": idx.disease_direction(d),
                     "gene_level_compat": idx.s_direction(cls, [], d),
                     "subtype_compat": sorted({(s["variant_group"].split(":")[-1], s["side"], s["compat"]) for s in sub}),
                     "explanation": e.get("explanation"),
                     "counter_evidence": [c.get("ref") for c in e["counter_evidence"]][:3]})
    out["contested_pairs"] = rows
    # automated (MONDO-level) direction for the sodium-channel subtypes, and ChEMBL sodium-channel blockers
    by_dis = gdir["by_disease"]
    index = json.load(open(ROOT / "data/derived/global/index.json"))
    names = {r[0]: r[1] for r in index["rows"]}
    sub = []
    for m, gs in by_dis.items():
        for gname in ("SCN1A", "SCN2A", "SCN8A"):
            if gname in gs:
                r = gs[gname]
                sub.append({"mondo": m, "name": names.get(m), "gene": gname, "direction": r["direction"],
                            "lof": r["lof"], "gof": r["gof"],
                            "basis": [f"{b['source']}: {b.get('label') or ''}"[:80] for b in r["basis"]][:4]})
    out["automated_sodium_channel_disease_directions"] = sorted(sub, key=lambda x: (x["gene"], x["mondo"]))
    dd = json.load(open(DIRD / "drug_direction.json"))
    out["chembl_sodium_channel_blockers"] = {v["name"]: sorted({(a["action_type"], ",".join(a["targets"][:6])) for a in v["actions"]})
                                             for v in dd["drugbank"].values()
                                             if v["name"] in ("PHENYTOIN", "CARBAMAZEPINE", "LAMOTRIGINE", "OXCARBAZEPINE",
                                                              "LACOSAMIDE", "RUFINAMIDE", "ZONISAMIDE", "TOPIRAMATE")}
    return out


def main():
    t0 = time.time()
    a = primekg(fallback=False)
    a_fb = primekg(fallback=True)
    c = atlas()
    out = {"generated": time.strftime("%Y-%m-%d"), "script": "pipeline/eval/direction_eval.py",
           "inputs": ["data/derived/direction/gene_direction.json", "data/derived/direction/drug_direction.json",
                      "data/derived/ingest/primekg_benchmark.json", "data/graph.json", "data/curated/family_dee.json"],
           "grid": GRID, "pathway_max_genes": PATH_MAX_GENES,
           "primekg": a, "primekg_gene_fallback_sensitivity": {k: a_fb[k] for k in ("results", "paired_vs_base", "coverage", "contraindications", "sign_agreement")},
           "atlas": c, "runtime_s": round(time.time() - t0, 1)}
    OUT.write_text(json.dumps(out, indent=1, default=str))
    for tag, x in (("PRIMARY", a), ("FALLBACK", a_fb)):
        print("=====", tag)
        print(json.dumps(x["coverage"]))
        for n, r in x["results"].items():
            print(f"{n:70s} MRR {r['rr']:.3f} {r['rr_ci']} R@1 {r['r@1']:.3f} R@5 {r['r@5']:.3f} {r['r@5_ci']} R@10 {r['r@10']:.3f}")
        for n, r in x["paired_vs_base"].items():
            print(f"   d {n:70s} {r}")
        print(json.dumps(x["contraindications"], indent=0))
        print(json.dumps(x["sign_agreement"]))
    print("choices", a["nested_choices_direction"], a["nested_choices_undirected"])
    print(json.dumps(c["coverage"]), json.dumps(c["benchmark"], indent=0))
    for r in c["contested_pairs"]:
        print(r["therapy"], r["disease"], r["drug_direction"], r["gene_level_direction"], r["gene_level_compat"], r["subtype_compat"])
    print(f"done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
