"""Production similar-disease index + per-gene explanatory factors (numpy, ~1-2 min).

    uv run --with numpy python3 pipeline/ingest/similar_index.py

Scorer (recommended in docs/agent-reports/ingest.md, validated on the PrimeKG benchmark):
    score = phen/max_phen + 0.5 * genes/max_genes + 0.5 * pathway/max_pathway
  phen    : HPO IC-weighted cosine over ancestor-propagated annotations (global_entries.json)
  genes   : Jaccard of the causal gene sets (index.json `genes`)
  pathway : IDF-weighted cosine of full Reactome sets (lowest level + all ancestors, NCBI2Reactome)
  Each component is divided by its maximum over the query's candidates (self excluded), exactly as in
  the benchmark. Queries: every index row with >= 1 HPO phenotype term. Candidates: the same rows minus
  QTL / susceptibility entries (as in neighbours/).

Outputs:
  data/derived/global/similar/<djb2(id)%64>.json
  data/derived/global/gene_factors.json
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys
import time
from collections import Counter, defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "eval"))
from build_features import load_reactome  # noqa: E402

RAW = ROOT / "data/raw/downloads"
GLOB = ROOT / "data/derived/global"
ING = ROOT / "data/derived/ingest"
TOP = 10
W_GENE, W_PATH = 0.5, 0.5
DISTINCTIVE_IC = 4.0
EXCLUDE = re.compile(r"\bQTL|susceptibility", re.I)
# reason quality (display only; never used in scoring)
MIN_REASON_IC = 2.5
TOP_OWN = 30                     # a term is "characteristic" if it covers one of the disease's top-30 terms by IC
MSK_ROOT = "HP:0033127"          # Abnormality of the musculoskeletal system
MSK_WEIGHT = 0.3                 # down-weight unless both diseases are mainly (>= 50% of terms) musculoskeletal
GENERIC_PATHWAY_GENES = 300
GENERIC_PATHWAY_NAMES = {"Generic Transcription Pathway", "RNA Polymerase II Transcription", "Gene expression (Transcription)",
                         "Metabolism of proteins", "Signal Transduction", "Metabolism", "Disease", "Immune System",
                         "Developmental Biology", "Post-translational protein modification", "Metabolism of lipids",
                         "Transport of small molecules", "Cellular responses to stimuli", "Hemostasis"}
FREQ_CODE = {"HP:0040280": 1.0, "HP:0040281": 0.9, "HP:0040282": 0.55, "HP:0040283": 0.17, "HP:0040284": 0.03, "HP:0040285": 0.0}


def parse_freq(x):
    x = x.strip()
    if not x:
        return None
    if x in FREQ_CODE:
        return FREQ_CODE[x]
    try:
        if "/" in x:
            a, b = x.split("/")
            return int(a) / int(b) if int(b) else None
        if x.endswith("%"):
            return float(x[:-1]) / 100
    except ValueError:
        return None
    return None


def hpo_ancestors():
    parents = defaultdict(set)
    cur = None
    for line in open(RAW / "hp.obo", encoding="utf-8"):
        if line.startswith("id: HP:"):
            cur = line[4:].strip()
        elif line.startswith("is_a: HP:") and cur:
            parents[cur].add(line[6:16])
    memo = {}

    def anc(t):
        if t not in memo:
            out = {t}
            for q in parents.get(t, ()):
                out |= anc(q)
            memo[t] = out
        return memo[t]
    return anc


def characteristic(direct, freq, ic, anc_of):
    """term -> (c weight) for every propagated term of one disease."""
    top = set(sorted((t for t in direct if ic.get(t, 0) > 0), key=lambda t: -ic[t])[:TOP_OWN])
    best_f, in_top = {}, set()
    for u in direct:
        f = freq.get(u)
        for t in anc_of(u):
            if f is not None:
                best_f[t] = max(best_f.get(t, 0.0), f)
            if u in top:
                in_top.add(t)
    out = {}
    for t in {t for u in direct for t in anc_of(u)}:
        if t in best_f:
            f = best_f[t]
            out[t] = 1.0 if f >= 0.3 else (0.5 if f >= 0.05 else 0.2)
        else:
            out[t] = 0.8 if t in in_top else 0.4
    return out


def djb2(s):
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def r3(x):
    return round(float(x), 3)


def main():
    t0 = time.time()
    ge = json.load(open(RAW / "global_entries.json"))
    E, ic, anc, hname = ge["entries"], ge["ic"], ge["ancestors"], ge["hpo_names"]
    idx = json.load(open(GLOB / "index.json"))
    f = idx["f"]
    genes_of = {r[f.index("id")]: [g for g in r[f.index("genes")].split(",") if g] for r in idx["rows"]}
    ids = sorted(k for k, v in E.items() if v["direct"])
    N = len(ids)
    pos = {k: i for i, k in enumerate(ids)}
    cand_ok = np.array([not EXCLUDE.search(E[k]["name"]) for k in ids])

    # phenotype matrix (dense rows, normalised) --------------------------------
    prop = []
    for k in ids:
        s = set()
        for t in E[k]["direct"]:
            s |= set(anc.get(t, [t]))
        prop.append({t for t in s if ic.get(t, 0) > 0})
    vocab = {t: i for i, t in enumerate(sorted({t for s in prop for t in s}))}
    P = np.zeros((N, len(vocab)), np.float32)
    for i, s in enumerate(prop):
        for t in s:
            P[i, vocab[t]] = ic[t]
    nrm = np.linalg.norm(P, axis=1)
    P[nrm > 0] /= nrm[nrm > 0, None]

    # reason helpers: HPO frequency per disease, characteristic weights, musculoskeletal share ------
    anc_of = hpo_ancestors()
    raw_freq = defaultdict(dict)
    for line in open(RAW / "phenotype.hpoa", encoding="utf-8"):
        if line.startswith("#") or line.startswith("database_id"):
            continue
        r = line.rstrip("\n").split("\t")
        if len(r) < 11 or r[2] == "NOT" or r[10] != "P":
            continue
        f = parse_freq(r[7])
        if f is not None:
            raw_freq[r[0]][r[3]] = max(raw_freq[r[0]].get(r[3], 0.0), f)
    charw, mainly_msk = [], []
    for k in ids:
        fr = {}
        for rid in E[k]["raw"]:
            for t, f in raw_freq.get(rid, {}).items():
                fr[t] = max(fr.get(t, 0.0), f)
        d = E[k]["direct"]
        charw.append(characteristic(d, fr, ic, anc_of))
        mainly_msk.append(sum(1 for t in d if MSK_ROOT in anc_of(t)) >= 0.5 * len(d))

    def symptom_reasons(i, j):
        both_msk = mainly_msk[i] and mainly_msk[j]
        cands = []
        for t in prop[i] & prop[j]:
            if ic[t] < MIN_REASON_IC:
                continue
            w = ic[t] * charw[i].get(t, 0.4) * charw[j].get(t, 0.4)
            if not both_msk and MSK_ROOT in anc_of(t):
                w *= MSK_WEIGHT
            cands.append((w, t))
        cands.sort(key=lambda x: (-x[0], x[1]))
        st = []
        for _, t in cands:
            if any(t in anc_of(u) or u in anc_of(t) for u in st):
                continue   # no ancestor/descendant pairs
            st.append(t)
            if len(st) == 3:
                break
        if not st:
            sh = sorted(prop[i] & prop[j], key=lambda t: -ic[t])
            st = sh[:1]
        return st

    # pathway matrix -------------------------------------------------------------
    gene_paths, pnames = load_reactome()
    sym2ncbi = {}
    for line in open(RAW / "genes_to_disease.txt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if p[0].startswith("NCBIGene:"):
            sym2ncbi.setdefault(p[1], p[0].split(":")[1])
    df = Counter(t for s in gene_paths.values() for t in s)
    ng = len(gene_paths)
    pidf = {t: math.log((ng + 1) / (c + 1)) for t, c in df.items()}
    generic_pw = {t for t, c in df.items() if c > GENERIC_PATHWAY_GENES or pnames.get(t) in GENERIC_PATHWAY_NAMES}
    genes = [set(genes_of.get(k, [])) for k in ids]
    paths = [set().union(*[gene_paths.get(sym2ncbi.get(g, ""), set()) for g in gs]) if gs else set() for gs in genes]
    pv = {t: i for i, t in enumerate(sorted({t for s in paths for t in s}))}
    R = np.zeros((N, len(pv)), np.float32)
    for i, s in enumerate(paths):
        for t in s:
            R[i, pv[t]] = pidf[t]
    nrm = np.linalg.norm(R, axis=1)
    R[nrm > 0] /= nrm[nrm > 0, None]

    # gene index for Jaccard ------------------------------------------------------
    by_gene = defaultdict(list)
    for i, gs in enumerate(genes):
        for g in gs:
            by_gene[g].append(i)
    print(f"matrices {P.shape} {R.shape} {time.time()-t0:.0f}s", flush=True)

    shards = defaultdict(dict)
    shard_t = defaultdict(dict)
    shard_p = defaultdict(dict)
    B = 512
    for a in range(0, N, B):
        Sp = P[a:a + B] @ P.T
        Sr = R[a:a + B] @ R.T
        for bi in range(Sp.shape[0]):
            i = a + bi
            sp, sr = Sp[bi].copy(), Sr[bi].copy()
            sg = np.zeros(N, np.float32)
            for g in genes[i]:
                for j in by_gene[g]:
                    sg[j] = len(genes[i] & genes[j]) / len(genes[i] | genes[j])
            ok = cand_ok.copy()
            ok[i] = False
            comp = []
            for s in (sp, sg, sr):
                m = s[ok].max() if ok.any() else 0
                comp.append(s / m if m > 0 else np.zeros_like(s))
            score = comp[0] + W_GENE * comp[1] + W_PATH * comp[2]
            score[~ok] = -1
            top = np.argpartition(-score, TOP)[:TOP]
            top = top[np.argsort(-score[top])]
            key = ids[i]
            b = djb2(key) % 64
            nb = []
            for j in top:
                if score[j] <= 0:
                    break
                st = symptom_reasons(i, j)
                sgn = sorted(genes[i] & genes[j])
                spw = sorted(paths[i] & paths[j] - generic_pw, key=lambda t: -pidf[t])[:2]   # display: generic pathways dropped (scoring keeps them)
                for t in st:
                    shard_t[b][t] = [hname.get(t, t), round(ic[t], 2)]
                for t in spw:
                    shard_p[b][t] = pnames.get(t, t)
                nb.append([ids[j], r3(score[j]), r3(sp[j]), r3(sg[j]), r3(sr[j]), st, sgn, spw])
            shards[b][key] = nb
        print(f"  {min(a+B, N)}/{N} {time.time()-t0:.0f}s", flush=True)

    out = GLOB / "similar"
    out.mkdir(exist_ok=True)
    sizes = []
    for b in range(64):
        doc = {"bucket": b, "f": ["id", "score", "phenotype", "genes", "pathway", "shared_hpo", "same_genes", "shared_pathways"],
               "t": dict(sorted(shard_t[b].items())), "p": dict(sorted(shard_p[b].items())),
               "d": dict(sorted(shards[b].items()))}
        p = out / f"{b}.json"
        p.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
        sizes.append(p.stat().st_size)
    print(f"similar: {len(ids)} diseases, {sum(sizes)/1e6:.1f} MB, max {max(sizes)/1e3:.0f} KB")

    # gene factors -----------------------------------------------------------------
    con = json.load(open(ING / "constraint.json"))["genes"]
    spec = json.load(open(ING / "clinvar_gene_spectrum.json"))["genes"]
    am = json.load(open(ING / "alphamissense_gene.json"))["genes"]
    all_genes = sorted({g for gs in genes_of.values() for g in gs})

    def loeuf_label(loeuf, pli):
        if loeuf is None:
            return None
        if loeuf < 0.35 or (pli is not None and pli >= 0.99):
            return "very intolerant to losing one copy"
        if loeuf < 0.6 or (pli is not None and pli >= 0.9):
            return "intolerant to losing one copy"
        if loeuf < 1.0:
            return "somewhat tolerant of losing one copy"
        return "tolerant of losing one copy"

    SPEC_LABEL = {"nonsense": "nonsense (premature stop)", "frameshift": "frameshift", "splice": "splice-site",
                  "missense": "missense (single amino-acid change)", "inframe": "in-frame insertion/deletion",
                  "cnv": "copy-number / exon deletion or duplication", "other": "other"}

    def am_label(x):
        if x >= 0.564:
            return "most missense changes predicted damaging"
        if x >= 0.34:
            return "missense changes predicted mixed"
        return "most missense changes predicted tolerated"

    gf = {}
    for g in all_genes:
        row = [None, None, None, None, None, None, None, None, None]
        c = con.get(g)
        if c:
            row[0], row[1], row[2] = c[1], c[0], loeuf_label(c[1], c[0])
        s = spec.get(g)
        if s and s["n"]:
            dom = max(s["c"], key=lambda k: s["c"][k])
            trunc = sum(s["c"].get(k, 0) for k in ("nonsense", "frameshift", "splice")) / s["n"]
            row[3], row[4], row[5], row[6] = SPEC_LABEL[dom], s["f"][dom], s["n"], round(trunc, 3)
        a = am.get(g)
        if a:
            row[7], row[8] = a[0], am_label(a[0])
        if any(v is not None for v in row):
            gf[g] = row
    gpath = GLOB / "gene_factors.json"
    gpath.write_text(json.dumps({
        "note": "Explanatory text only; NOT used for ranking (see docs/agent-reports/ingest.md). Sources: gnomAD v4.1 constraint, ClinVar P/LP (2026-09-29), AlphaMissense (Cheng et al. 2023).",
        "f": ["loeuf", "pli", "constraint_label", "clinvar_dominant_type", "clinvar_dominant_fraction", "clinvar_pathogenic_n",
              "clinvar_truncating_fraction", "alphamissense_mean", "alphamissense_label"],
        "labels": {"constraint": "LOEUF < 0.35 or pLI >= 0.99: very intolerant; LOEUF < 0.6 or pLI >= 0.9: intolerant; LOEUF < 1: somewhat tolerant; else tolerant (of losing one copy)",
                   "alphamissense": ">= 0.564 mostly damaging; >= 0.34 mixed; else mostly tolerated (the AlphaMissense variant-class cut-offs, applied to the gene mean)",
                   "truncating": "nonsense + frameshift + splice share of ClinVar P/LP variants"},
        "genes": gf}, separators=(",", ":"), ensure_ascii=False))
    print(f"gene_factors: {len(gf)} genes, {gpath.stat().st_size/1e3:.0f} KB; {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
