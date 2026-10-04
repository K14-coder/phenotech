"""PrimeKG therapy-transfer benchmark: which disease factors help, measured on ~2,100 external cases.

    uv run --with numpy --with scipy python3 pipeline/eval/primekg_eval.py              # ~10 s, offline, no OpenAI
    uv run --with numpy --with scipy python3 pipeline/eval/primekg_eval.py --offlabel  # indication + off-label positives

Inputs : data/derived/ingest/primekg_benchmark.json (pipeline/ingest/primekg_benchmark.py)
         data/derived/ingest/{constraint,alphamissense_gene,clinvar_gene_spectrum}.json
         data/derived/global/{index.json, mechanism/*.json}, data/raw/downloads/global_entries.json (HPO)
         data/derived/features/{gene_families,gene_tissue}.json, data/derived/mechsim.json (TM-align)
         data/raw/downloads/{NCBI2Reactome,ReactomePathways,ReactomePathwaysRelation,genes_to_disease}.txt
Output : data/derived/ingest/primekg_eval.json

Protocol (mirrors docs/agent-reports/eval.md sections 2 and 5)
  * Case = one (drug, indicated disease) pair; the pair is hidden, the drug's other indicated diseases
    are the context, and every pool disease except the context and the drug's off-label diseases is
    ranked (filtered ranking). Feature score of a candidate = max similarity to a context disease,
    normalised by its maximum over the candidates of that case.
  * Ties are scored at their expected value (random tie-break), so an uninformative feature scores
    exactly at random.
  * Drugs with near-identical indication lists (Jaccard >= 0.5, single linkage; e.g. the eight systemic
    corticosteroids) form one "drug group". Bootstrap (2,000 draws) and cross-validation folds are over
    drug groups, so correlated drugs never sit on both sides of a split.
  * Combinations: nested CV (5 outer folds over drug groups). Inside each outer fold, weights are chosen
    on the training groups only: `grid` = every {0,1} subset of the features (exhaustive, objective mean
    reciprocal rank, ties to fewer features); `logit` = conditional-logit ranking model (softmax over a
    case's candidates), weights >= 0, L2 penalty. Untuned references: equal weights, phenotype alone.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
from collections import Counter, defaultdict

import numpy as np
from scipy.optimize import minimize

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "eval"))
from build_features import load_reactome  # noqa: E402

ING = ROOT / "data/derived/ingest"
GLOB = ROOT / "data/derived/global"
FEAT = ROOT / "data/derived/features"
RAW = ROOT / "data/raw/downloads"
OUT = ING / "primekg_eval.json"
SEED = 20261004
N_BOOT = 2000
KS = (1, 3, 5, 10)

FEATURES = ["phenotype", "genes", "mechanism", "constraint", "pathway_mid", "pathway_full", "gene_family",
            "protein_domain", "tissue", "mutation_spectrum", "alphamissense", "structure_tm"]
FEATURE_DOC = {
    "phenotype": "symptoms: HPO IC-weighted cosine over ancestor-propagated annotations (phenotype.hpoa, as in the global index)",
    "genes": "genes involved: Jaccard of the causal gene sets",
    "mechanism": "mechanism class: IDF-weighted cosine of G2P / ClinGen classes (global/mechanism) + gnomAD constraint tokens (LoF-intolerant pLI>=0.9 or LOEUF<0.6; LoF-tolerant LOEUF>1; missense-constrained Z>=3.09)",
    "constraint": "gnomAD v4.1 continuous: 1 - mean |diff| of [pLI, 1-min(LOEUF,1.5)/1.5, clip(misZ/6, -1, 1)] (most constrained gene of the disease)",
    "pathway_mid": "signalling pathway: Reactome mid-level (depth-3) pathways of the disease, from global/mechanism; IDF-weighted cosine",
    "pathway_full": "signalling pathway: Reactome lowest-level + all ancestors of the genes (NCBI2Reactome); IDF-weighted cosine",
    "gene_family": "protein family: PANTHER + InterPro Family entries (features/gene_families.json); IDF-weighted cosine",
    "protein_domain": "protein structure/domains: InterPro Domain/Repeat/Homologous superfamily + Pfam; IDF-weighted cosine",
    "tissue": "tissue: HPA tissue-enriched nTPM (features/gene_tissue.json), cosine of log1p(nTPM)",
    "mutation_spectrum": "mutation type: full-ClinVar P/LP consequence spectrum (clinvar_gene_spectrum.json), 1 - Jensen-Shannon divergence",
    "alphamissense": "molecular consequence / structure: 1 - |diff| of AlphaMissense gene mean pathogenicity",
    "structure_tm": "protein structure: AlphaFold TM-align score between the disease genes (data/derived/mechsim.json, 220 genes)",
}


# ------------------------------------------------------------------ similarity helpers
def cosine_matrix(vecs):
    """vecs: list of dict token->weight. Returns NxN cosine (0 where a vector is empty)."""
    vocab = {}
    for v in vecs:
        for t in v:
            vocab.setdefault(t, len(vocab))
    if not vocab:
        return np.zeros((len(vecs), len(vecs)), dtype=np.float32), np.zeros(len(vecs), bool)
    M = np.zeros((len(vecs), len(vocab)), dtype=np.float32)
    for i, v in enumerate(vecs):
        for t, w in v.items():
            M[i, vocab[t]] = w
    nrm = np.linalg.norm(M, axis=1)
    has = nrm > 0
    M[has] /= nrm[has, None]
    return M @ M.T, has


def idf_vecs(token_sets, df, n):
    return [{t: math.log((n + 1) / (df.get(t, 0) + 1)) for t in s} for s in token_sets]


def scalar_sim(vals, fn):
    v = np.array([np.nan if x is None else x for x in vals], dtype=np.float64)
    has = ~np.isnan(v)
    S = np.zeros((len(v), len(v)), dtype=np.float32)
    idx = np.where(has)[0]
    S[np.ix_(idx, idx)] = fn(v[idx][:, None], v[idx][None, :])
    return S, has


# ------------------------------------------------------------------ build per-node features
def build_similarities(bench):
    pool = bench["pool"]
    nodes = bench["nodes"]
    N = len(pool)
    sims, cover = {}, {}

    # phenotype -----------------------------------------------------
    ge = json.load(open(RAW / "global_entries.json"))
    ic, anc = ge["ic"], ge["ancestors"]
    vecs = []
    for k in pool:
        terms = set()
        for m in nodes[k]["index_ids"]:
            e = ge["entries"].get(m)
            if e:
                for t in e["direct"]:
                    terms |= set(anc.get(t, [t]))
        vecs.append({t: ic[t] for t in terms if ic.get(t, 0) > 0})
    sims["phenotype"], cover["phenotype"] = cosine_matrix(vecs)

    genes = [set(nodes[k]["genes"]) for k in pool]

    # genes -----------------------------------------------------------
    S = np.zeros((N, N), dtype=np.float32)
    for i in range(N):
        for j in range(i + 1, N):
            if genes[i] & genes[j]:
                S[i, j] = S[j, i] = len(genes[i] & genes[j]) / len(genes[i] | genes[j])
    sims["genes"], cover["genes"] = S, np.array([bool(g) for g in genes])

    # mechanism shards ---------------------------------------------
    mech = {}
    for b in range(64):
        d = json.load(open(GLOB / "mechanism" / f"{b}.json"))
        mech.update(d["d"])
    con = json.load(open(ING / "constraint.json"))["genes"]

    def con_tokens(g):
        c = con.get(g)
        if not c:
            return set()
        pli, loeuf, misz = c[0], c[1], c[2]
        t = set()
        if (pli is not None and pli >= 0.9) or (loeuf is not None and loeuf < 0.6):
            t.add("con:lof_intolerant")
        elif loeuf is not None and loeuf > 1.0:
            t.add("con:lof_tolerant")
        if misz is not None and misz >= 3.09:
            t.add("con:missense_constrained")
        return t

    mech_sets = []
    for k, gs in zip(pool, genes):
        s = set()
        for m in nodes[k]["index_ids"]:
            for r in mech.get(m, {}).get("mechanisms", []):
                if r.get("class"):
                    s.add(r["class"])
        for g in gs:
            s |= con_tokens(g)
        mech_sets.append(s)
    # df over every index disease (classes) / every gene (constraint), approximated over the pool
    df = Counter(t for s in mech_sets for t in s)
    sims["mechanism"], cover["mechanism"] = cosine_matrix(idf_vecs(mech_sets, df, N))

    def con_vec(gs):
        best = None
        for g in gs:
            c = con.get(g)
            if not c or c[1] is None:
                continue
            if best is None or c[1] < best[1]:
                best = c
        if best is None:
            return None
        pli = best[0] if best[0] is not None else 0.0
        misz = best[2] if best[2] is not None else 0.0
        return (pli, 1 - min(best[1], 1.5) / 1.5, max(-1.0, min(1.0, misz / 6)))

    cv = [con_vec(gs) for gs in genes]
    has = np.array([c is not None for c in cv])
    A = np.array([c if c else (0, 0, 0) for c in cv], dtype=np.float32)
    S = 1 - np.abs(A[:, None, :] - A[None, :, :]).mean(axis=2) / np.array([1, 1, 2]).mean()
    S = np.clip(S, 0, 1)
    S[~has] = 0
    S[:, ~has] = 0
    sims["constraint"], cover["constraint"] = S.astype(np.float32), has

    # pathway (mid-level, from the mechanism shards) ----------------
    pw_all = [set(v.get("pathways", [])) for v in mech.values()]
    dfp = Counter(t for s in pw_all for t in s)
    pw = []
    for k in pool:
        s = set()
        for m in nodes[k]["index_ids"]:
            s |= set(mech.get(m, {}).get("pathways", []))
        pw.append(s)
    sims["pathway_mid"], cover["pathway_mid"] = cosine_matrix(idf_vecs(pw, dfp, len(pw_all)))

    # pathway (full Reactome via NCBI gene ids) ---------------------
    gene_paths, _ = load_reactome()
    sym2ncbi = {}
    for line in open(RAW / "genes_to_disease.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if p[0].startswith("NCBIGene:"):
            sym2ncbi.setdefault(p[1], p[0].split(":")[1])
    dff = Counter(t for s in gene_paths.values() for t in s)
    ng = len(gene_paths)
    toks = [set().union(*[gene_paths.get(sym2ncbi.get(g, ""), set()) for g in gs]) if gs else set() for gs in genes]
    sims["pathway_full"], cover["pathway_full"] = cosine_matrix(idf_vecs(toks, dff, ng))

    # protein family / domain ---------------------------------------
    gf = json.load(open(FEAT / "gene_families.json"))["genes"]
    fam_df, dom_df = Counter(), Counter()
    for v in gf.values():
        fam_df.update(set(v[2]) | set(v[3]))
        dom_df.update(set(v[4]) | set(v[5]))
    fams = [set().union(*[set(gf[g][2]) | set(gf[g][3]) for g in gs if g in gf]) if gs else set() for gs in genes]
    doms = [set().union(*[set(gf[g][4]) | set(gf[g][5]) for g in gs if g in gf]) if gs else set() for gs in genes]
    sims["gene_family"], cover["gene_family"] = cosine_matrix(idf_vecs(fams, fam_df, len(gf)))
    sims["protein_domain"], cover["protein_domain"] = cosine_matrix(idf_vecs(doms, dom_df, len(gf)))

    # tissue ----------------------------------------------------------
    gt = json.load(open(FEAT / "gene_tissue.json"))["genes"]
    tv = []
    for gs in genes:
        v = defaultdict(float)
        for g in gs:
            for t, x in (gt.get(g, [None, {}])[1] or {}).items():
                v[t] += math.log1p(x)
        tv.append(dict(v))
    sims["tissue"], cover["tissue"] = cosine_matrix(tv)

    # mutation spectrum ---------------------------------------------
    spec = json.load(open(ING / "clinvar_gene_spectrum.json"))
    keys = spec["keys"]
    P = np.zeros((N, len(keys)))
    for i, gs in enumerate(genes):
        for g in gs:
            c = spec["genes"].get(g, {}).get("c", {})
            for j, kk in enumerate(keys):
                P[i, j] += c.get(kk, 0)
    has = P.sum(1) > 0
    P[has] /= P[has].sum(1, keepdims=True)
    M = 0.5 * (P[:, None, :] + P[None, :, :])

    def kl(a, b):
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(a > 0, a * np.log2(np.where(b > 0, a / b, 1)), 0)
        return r.sum(-1)
    JS = 0.5 * kl(P[:, None, :], M) + 0.5 * kl(P[None, :, :], M)
    S = (1 - JS).astype(np.float32)
    S[~has] = 0
    S[:, ~has] = 0
    sims["mutation_spectrum"], cover["mutation_spectrum"] = S, has

    # AlphaMissense ---------------------------------------------------
    am = json.load(open(ING / "alphamissense_gene.json"))["genes"]
    vals = []
    for gs in genes:
        x = [am[g][0] for g in gs if g in am]
        vals.append(float(np.mean(x)) if x else None)
    sims["alphamissense"], cover["alphamissense"] = scalar_sim(vals, lambda a, b: 1 - np.abs(a - b))

    # AlphaFold TM-align (mechsim) -----------------------------------
    ms = json.load(open(ROOT / "data/derived/mechsim.json"))
    pf = ms["pair_fields"]
    ti, tj, tt = pf.index("i"), pf.index("j"), pf.index("tm_score")
    ent_genes = [set(p.get("genes") or [p.get("gene")]) for p in ms["profiles"]]
    tm = {}
    for r in ms["pairs"]:
        if r[tt] is None:
            continue
        for a in ent_genes[r[ti]]:
            for b in ent_genes[r[tj]]:
                if a != b:
                    key = (a, b) if a < b else (b, a)
                    tm[key] = max(tm.get(key, 0), r[tt])
    msg = {g for s in ent_genes for g in s}
    S = np.zeros((N, N), dtype=np.float32)
    for i in range(N):
        if not genes[i] & msg:
            continue
        for j in range(N):
            if i != j and genes[j] & msg:
                best = 1.0 if genes[i] & genes[j] & msg else 0.0
                for a in genes[i] & msg:
                    for b in genes[j] & msg:
                        if a != b:
                            best = max(best, tm.get((a, b) if a < b else (b, a), 0))
                S[i, j] = best
    sims["structure_tm"], cover["structure_tm"] = S, np.array([bool(g & msg) for g in genes])
    return sims, cover


# ------------------------------------------------------------------ cases
def drug_groups(drugs):
    ids = sorted(drugs)
    parent = {d: d for d in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    sets = {d: set(drugs[d]["indication"]) for d in ids}
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            j = len(sets[a] & sets[b]) / len(sets[a] | sets[b])
            if j >= 0.5:
                parent[find(a)] = find(b)
    return {d: find(d) for d in ids}


def build_cases(bench, sims):
    pool = bench["pool"]
    pos = {k: i for i, k in enumerate(pool)}
    N = len(pool)
    F = len(FEATURES)
    S = np.stack([sims[f] for f in FEATURES])          # F x N x N
    X, tgt, mask, meta = [], [], [], []
    for d, v in sorted(bench["drugs"].items()):
        ind = [pos[k] for k in v["indication"]]
        off = [pos[k] for k in v["offlabel"]]
        for h in ind:
            ctx = [i for i in ind if i != h]
            m = np.ones(N, bool)
            m[ctx] = False
            m[[o for o in off if o != h]] = False
            sc = S[:, ctx, :].max(axis=1)              # F x N
            mx = np.where(m[None, :], sc, 0).max(axis=1)
            sc = np.where(mx[:, None] > 0, sc / np.where(mx > 0, mx, 1)[:, None], 0)
            X.append(sc.T.astype(np.float32))
            tgt.append(h)
            mask.append(m)
            meta.append((d, h, len(v["indication"])))
    return np.stack(X), np.array(tgt), np.stack(mask), meta


def rank_stats(scores, tgt, mask):
    """scores: C x N (or C x N x W). Returns expected rank (C[,W]) and the gt/eq counts."""
    C = scores.shape[0]
    t = scores[np.arange(C), tgt]
    if scores.ndim == 2:
        gt = ((scores > t[:, None]) & mask).sum(1)
        eq = ((scores == t[:, None]) & mask).sum(1) - 1
    else:
        gt = ((scores > t[:, None, :]) & mask[:, :, None]).sum(1)
        eq = ((scores == t[:, None, :]) & mask[:, :, None]).sum(1) - 1
    return gt, eq


def metrics_from(gt, eq):
    """Per-case expected reciprocal rank and recall@k under random tie-breaking."""
    gt = gt.astype(np.float64)
    eq = eq.astype(np.float64)
    out = {}
    out["rr"] = fast_rr(gt, eq)  # expected RR over the tied positions
    for k in KS:
        out[f"r@{k}"] = np.clip((k - gt) / (eq + 1), 0, 1)
    out["rank"] = gt + eq / 2 + 1
    return out


H = np.concatenate([[0.0], np.cumsum(1.0 / np.arange(1, 5001))])


def fast_rr(gt, eq):
    gt = gt.astype(np.int64)
    eq = eq.astype(np.int64)
    return (H[gt + eq + 1] - H[gt]) / (eq + 1)


def summarize(m, groups_idx, rng_draws):
    """Mean metrics and bootstrap CIs over drug groups (cluster bootstrap)."""
    res = {}
    for key in ["rr"] + [f"r@{k}" for k in KS]:
        v = m[key]
        res[key] = round(float(v.mean()), 4)
        gsum = np.array([v[ix].sum() for ix in groups_idx])
        gcnt = np.array([len(ix) for ix in groups_idx])
        bs = (rng_draws @ gsum) / (rng_draws @ gcnt)
        res[key + "_ci"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
    res["median_rank"] = float(np.median(m["rank"]))
    res["rr_macro_group"] = round(float(np.mean([m["rr"][ix].mean() for ix in groups_idx])), 4)
    return res


def logit_fit(Xtr, ttr, mtr, lam=1.0):
    C, N, F = Xtr.shape
    neg = ~mtr

    def f(w):
        s = Xtr @ w
        s = np.where(neg, -1e9, s)
        smax = s.max(1, keepdims=True)
        e = np.exp(s - smax)
        Z = e.sum(1)
        p = e / Z[:, None]
        ll = (s[np.arange(C), ttr] - smax[:, 0] - np.log(Z)).sum()
        g = (Xtr[np.arange(C), ttr, :] - np.einsum("cn,cnf->cf", p, Xtr)).sum(0)
        return -(ll - lam * (w @ w)) / C, -(g - 2 * lam * w) / C
    r = minimize(f, np.ones(F), jac=True, method="L-BFGS-B", bounds=[(0, None)] * F)
    return r.x


def main():
    t0 = time.time()
    offl = "--offlabel" in sys.argv
    bench = json.load(open(ING / ("primekg_benchmark_offlabel.json" if offl else "primekg_benchmark.json")))
    out_path = OUT.with_name("primekg_eval_offlabel.json") if offl else OUT
    sims, cover = build_similarities(bench)
    print(f"similarities built {time.time()-t0:.0f}s", flush=True)
    X, tgt, mask, meta = build_cases(bench, sims)
    C, N, F = X.shape
    print(f"cases {C}, pool {N}, features {F}; {time.time()-t0:.0f}s", flush=True)

    grp_of = drug_groups(bench["drugs"])
    gnames = sorted(set(grp_of.values()))
    gidx = {g: i for i, g in enumerate(gnames)}
    case_group = np.array([gidx[grp_of[m[0]]] for m in meta])
    groups_idx = [np.where(case_group == i)[0] for i in range(len(gnames))]
    rng = np.random.default_rng(SEED)
    draws = rng.multinomial(len(gnames), np.ones(len(gnames)) / len(gnames), size=N_BOOT).astype(np.float64)

    results = {}
    per_case_rr = {}

    def evaluate(name, scores):
        gt, eq = rank_stats(scores, tgt, mask)
        m = metrics_from(gt, eq)
        per_case_rr[name] = m["rr"]
        results[name] = summarize(m, groups_idx, draws)
        return m

    # random
    evaluate("random", np.zeros((C, N), np.float32))
    for i, f in enumerate(FEATURES):
        evaluate(f"single:{f}", X[:, :, i])
    evaluate("equal_all", X.sum(2))
    print(f"singles done {time.time()-t0:.0f}s", flush=True)

    # exhaustive {0,1} grid: per-case RR for every subset, computed once
    subsets = [s for s in range(1, 2 ** F)]
    W = np.array([[(s >> i) & 1 for i in range(F)] for s in subsets], dtype=np.float32).T   # F x S
    RR = np.zeros((C, len(subsets)), dtype=np.float32)
    R5 = np.zeros((C, len(subsets)), dtype=np.float32)
    chunk = 64
    for a in range(0, len(subsets), chunk):
        sc = X @ W[:, a:a + chunk]                        # C x N x w
        gt, eq = rank_stats(sc, tgt, mask)
        RR[:, a:a + chunk] = fast_rr(gt, eq)
        R5[:, a:a + chunk] = np.clip((5 - gt) / (eq + 1), 0, 1)
    nfeat = W.sum(0)
    print(f"grid done {time.time()-t0:.0f}s", flush=True)

    # nested CV over drug groups
    K = 5
    perm = np.random.default_rng(SEED + 1).permutation(len(gnames))
    fold_of_group = np.empty(len(gnames), int)
    fold_of_group[perm] = np.arange(len(gnames)) % K
    fold = fold_of_group[case_group]

    def pick(rr_cols_mean, allowed):
        score = np.where(allowed, rr_cols_mean - 1e-6 * nfeat, -1)
        return int(np.argmax(score))

    def nested_grid(allowed):
        rr = np.zeros(C)
        r5 = np.zeros(C)
        chosen = []
        for k in range(K):
            tr, te = fold != k, fold == k
            j = pick(RR[tr].mean(0), allowed)
            chosen.append(j)
            rr[te] = RR[te, j]
            r5[te] = R5[te, j]
        return rr, r5, chosen

    allowed_all = np.ones(len(subsets), bool)
    rr_g, r5_g, chosen = nested_grid(allowed_all)
    sel_freq = Counter(FEATURES[i] for j in chosen for i in range(F) if W[i, j])
    jfull = pick(RR.mean(0), allowed_all)
    grid_refit = [FEATURES[i] for i in range(F) if W[i, jfull]]

    # logit nested
    scores_logit = np.zeros((C, N), np.float32)
    logit_ws = []
    for k in range(K):
        tr, te = fold != k, fold == k
        w = logit_fit(X[tr], tgt[tr], mask[tr])
        logit_ws.append(w)
        scores_logit[te] = X[te] @ w
    w_full = logit_fit(X, tgt, mask)
    print(f"logit done {time.time()-t0:.0f}s", flush=True)

    def add_custom(name, rr, r5):
        results[name] = {"rr": round(float(rr.mean()), 4), "r@5": round(float(r5.mean()), 4)}
        gsum = np.array([rr[ix].sum() for ix in groups_idx])
        g5 = np.array([r5[ix].sum() for ix in groups_idx])
        gcnt = np.array([len(ix) for ix in groups_idx])
        for key, gs in (("rr", gsum), ("r@5", g5)):
            bs = (draws @ gs) / (draws @ gcnt)
            results[name][key + "_ci"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
        per_case_rr[name] = rr

    add_custom("nested_grid", rr_g, r5_g)

    # anchored tuner (added after the first run; post hoc): phenotype at weight 1 plus at most two
    # other features at weight 0.25 or 0.5, chosen by nested CV like the grid.
    pi = FEATURES.index("phenotype")
    others = [i for i in range(F) if i != pi]
    AW = []
    base = np.zeros(F, np.float32); base[pi] = 1
    AW.append(base.copy())
    for a in others:
        for wa in (0.25, 0.5):
            v = base.copy(); v[a] = wa; AW.append(v)
    for ai, a in enumerate(others):
        for b in others[ai + 1:]:
            for wa in (0.25, 0.5):
                for wb in (0.25, 0.5):
                    v = base.copy(); v[a] = wa; v[b] = wb; AW.append(v)
    AW = np.stack(AW, 1)
    gt, eq = rank_stats(X @ AW, tgt, mask)
    ARR = fast_rr(gt, eq)
    AR5 = np.clip((5 - gt) / (eq + 1), 0, 1)
    an_rr, an_r5, an_ch = np.zeros(C), np.zeros(C), []
    nz = (AW > 0).sum(0)
    for k in range(K):
        tr, te = fold != k, fold == k
        j = int(np.argmax(ARR[tr].mean(0) - 1e-6 * nz))
        an_ch.append(j)
        an_rr[te], an_r5[te] = ARR[te, j], AR5[te, j]
    add_custom("nested_anchored", an_rr, an_r5)
    ja = int(np.argmax(ARR.mean(0) - 1e-6 * nz))
    anchored_refit = {FEATURES[i]: float(AW[i, ja]) for i in range(F) if AW[i, ja] > 0}
    anchored_folds = [{FEATURES[i]: float(AW[i, j]) for i in range(F) if AW[i, j] > 0} for j in an_ch]
    evaluate("nested_logit", scores_logit)
    evaluate("grid_refit_in_sample", X @ W[:, jfull])
    evaluate("logit_refit_in_sample", X @ w_full)
    # simple pre-declared production candidates
    def wvec(d):
        return np.array([d.get(f, 0.0) for f in FEATURES], dtype=np.float32)
    PRE = {
        "phenotype+mechanism": {"phenotype": 1, "mechanism": 1},
        "phenotype+genes": {"phenotype": 1, "genes": 1},
        "phenotype+pathway_full": {"phenotype": 1, "pathway_full": 1},
        "phenotype+genes+pathway_full+gene_family": {"phenotype": 1, "genes": 1, "pathway_full": 1, "gene_family": 1},
    }
    for name, d in PRE.items():
        evaluate(name, X @ wvec(d))

    # ablation: drop one feature from the nested grid
    ablation = {}
    for i, f in enumerate(FEATURES):
        allowed = W[i] == 0
        rr_a, _, _ = nested_grid(allowed)
        ablation[f] = round(float(rr_a.mean()), 4)
    # paired differences vs phenotype alone and vs nested grid
    def paired(a, b):
        d = per_case_rr[a] - per_case_rr[b]
        gs = np.array([d[ix].sum() for ix in groups_idx])
        gc = np.array([len(ix) for ix in groups_idx])
        bs = (draws @ gs) / (draws @ gc)
        return {"diff": round(float(d.mean()), 4), "ci": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)],
                "p_better": round(float((bs > 0).mean()), 3)}
    paired_res = {n: paired(n, "single:phenotype") for n in per_case_rr if n != "single:phenotype"}

    # subsets: specific drugs (<= 5 eligible indications) and per-feature coverage-restricted
    spec_ix = np.array([m[2] <= 5 for m in meta])
    pool_genes = [set(bench["nodes"][k]["genes"]) for k in bench["pool"]]
    ind_of = {d: [bench["pool"].index(k) for k in v["indication"]] for d, v in bench["drugs"].items()}
    nogene_ix = np.array([not any(pool_genes[h] & pool_genes[c] for c in ind_of[d] if c != h) for d, h, _ in meta])
    subset_res, nogene_res = {}, {}
    for name in ["random", "single:phenotype", "single:genes", "single:mechanism", "single:pathway_full",
                 "single:gene_family", "single:mutation_spectrum", "equal_all", "nested_grid", "nested_logit",
                 "phenotype+mechanism", "phenotype+genes+pathway_full+gene_family"]:
        subset_res[name] = round(float(per_case_rr[name][spec_ix].mean()), 4)
    for name in per_case_rr:
        v = per_case_rr[name][nogene_ix]
        gs = np.array([per_case_rr[name][ix][nogene_ix[ix]].sum() for ix in groups_idx])
        gc = np.array([nogene_ix[ix].sum() for ix in groups_idx])
        bs = (draws @ gs) / np.maximum(draws @ gc, 1)
        nogene_res[name] = {"rr": round(float(v.mean()), 4),
                            "rr_ci": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]}

    # contraindication check: context = all indications; where do contraindicated diseases rank?
    pool = bench["pool"]
    pos = {k: i for i, k in enumerate(pool)}
    S = np.stack([sims[f] for f in FEATURES])
    ci_rows = []
    for d, v in sorted(bench["drugs"].items()):
        ctr = [pos[k] for k in v["contraindication"] if k not in v["indication"]]
        if not ctr:
            continue
        ind = [pos[k] for k in v["indication"]]
        m = np.ones(N, bool)
        m[ind] = False
        m[[pos[k] for k in v["offlabel"]]] = False
        sc = S[:, ind, :].max(axis=1)
        mx = np.where(m[None, :], sc, 0).max(axis=1)
        sc = np.where(mx[:, None] > 0, sc / np.where(mx > 0, mx, 1)[:, None], 0).T   # N x F
        ci_rows.append((sc, m, ctr))
    contra = {}
    weightings = {f"single:{f}": wvec({f: 1}) for f in FEATURES}
    weightings["equal_all"] = np.ones(F, np.float32)
    weightings["grid_refit_in_sample"] = W[:, jfull]
    weightings["logit_refit_in_sample"] = w_full.astype(np.float32)
    weightings["phenotype+mechanism"] = wvec(PRE["phenotype+mechanism"])
    for name, w in weightings.items():
        pct = []
        for sc, m, ctr in ci_rows:
            s = sc @ w
            cand = s[m]
            for c in ctr:
                gt = (cand > s[c]).sum()
                eq = (cand == s[c]).sum() - (1 if m[c] else 0)
                pct.append((gt + eq / 2) / max(1, m.sum() - 1))
        # held-out indication percentile (same scorer, LOO cases)
        sc_loo = X @ w
        gt, eq = rank_stats(sc_loo, tgt, mask)
        ind_pct = ((gt + eq / 2) / (mask.sum(1) - 1)).mean()
        contra[name] = {"contraindication_mean_percentile": round(float(np.mean(pct)), 4),
                        "heldout_indication_mean_percentile": round(float(ind_pct), 4),
                        "n_contra_pairs": len(pct)}

    cov = {f: {"pool_nodes_with_data": int(cover[f].sum()), "of": N} for f in FEATURES}
    out = {
        "generated": time.strftime("%Y-%m-%d"),
        "benchmark": bench["counts"],
        "cases": C, "pool": N, "drug_groups": len(gnames), "drugs": len(bench["drugs"]),
        "specific_drug_cases": int(spec_ix.sum()),
        "features": FEATURE_DOC, "coverage": cov,
        "results": results,
        "paired_vs_phenotype_rr": paired_res,
        "nested_grid": {"selection_frequency_of_5_folds": dict(sel_freq.most_common()),
                        "fold_choices": [[FEATURES[i] for i in range(F) if W[i, j]] for j in chosen],
                        "refit_all_cases": grid_refit},
        "anchored": {"fold_choices": anchored_folds, "refit_all_cases": anchored_refit},
        "logit": {"fold_weights": [dict(zip(FEATURES, np.round(w, 3).tolist())) for w in logit_ws],
                  "refit_weights": dict(zip(FEATURES, np.round(w_full, 3).tolist()))},
        "ablation_nested_grid_mrr": ablation,
        "specific_drugs_mrr": subset_res,
        "no_shared_gene_cases": int(nogene_ix.sum()),
        "no_shared_gene_mrr": nogene_res,
        "contraindication_check": contra,
        "runtime_s": round(time.time() - t0, 1),
    }
    out["positives"] = bench.get("positives", "indication")
    out_path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ["cases", "pool", "drug_groups", "coverage"]}, indent=0))
    for n, r in results.items():
        print(f"{n:45s} MRR {r['rr']:.3f} {r.get('rr_ci')}  R@1 {r.get('r@1', float('nan')):.3f} R@5 {r['r@5']:.3f} {r.get('r@5_ci')} R@10 {r.get('r@10', float('nan')):.3f} macro {r.get('rr_macro_group', float('nan')):.3f}")
    print("grid refit", grid_refit, "sel", dict(sel_freq))
    print("logit refit", out["logit"]["refit_weights"])
    print("anchored folds", anchored_folds, "refit", anchored_refit)
    print("ablation", ablation)
    print("specific", subset_res)
    print("no-shared-gene cases", int(nogene_ix.sum()))
    for n, r in nogene_res.items():
        print(f"   nogene {n:40s} {r['rr']:.3f} {r['rr_ci']}")
    print("contra", json.dumps(contra, indent=0))
    print(f"done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
