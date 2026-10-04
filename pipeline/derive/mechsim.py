"""Mechanistic similarity, step 2 of 2: compare diseases on six mechanistic axes and link them.

Run:  python3 pipeline/derive/mechsim.py          (needs numpy, scipy, biopython; ~1 min)
      then python3 pipeline/build_graph.py && node web/scripts/sync-data.mjs
In:   data/raw/comparison/*  (written by mechsim_fetch.py, committed, so this step is offline)
      data/graph.json        (atlas diseases, curated variant-group -> mechanism edges)
      data/derived/global/mechanism/<b>.json (G2P mechanism class + variant consequence per disease)
Out:  data/derived/mechsim.json             every entity's six profiles + every pair's six scores
      data/curated/mechanistic_links.json   graph fragment: computed disease-disease links between
                                            atlas diseases, one edge type per axis, plus clusters

Entities: one per gene (gene-defined umbrella disease). The 45 atlas diseases plus a channelopathy
panel (every Mendelian ion-channel gene in the global index), see mechsim_fetch.py.

The six axes (each pair gets a raw similarity in [0, 1] and a percentile among all pairs):
  1. gene        Jaccard of the gene sets of each entity's MONDO disease entries (entries with <= 5 genes).
                 Two umbrellas share genes when the same clinical entity is caused by both genes.
  2. pathway     IDF-weighted Jaccard of canonical pathway memberships (MSigDB: Reactome, WikiPathways,
                 KEGG, BioCarta, PID; disease-named sets dropped), combined with a STRING physical /
                 curated interaction between the two gene products (atlas genes only):
                 1 - (1 - wJaccard) * (1 - 0.5 * STRING score).
  3. tissue      mean of (a) cosine of IC-weighted HPO symptom profiles over 20 tissue / organ anchors
                 ("which tissue do the symptoms point to") and (b) Pearson correlation of GTEx v10
                 log2(TPM + 1) expression across 68 tissues ("where is the gene expressed").
  4. mutation    similarity of the ClinVar P/LP germline variant-type spectra (substitution, deletion,
                 duplication, insertion, indel, inversion, repeat, copy-number loss/gain, translocation,
                 complex): 1 - Jensen-Shannon distance of the smoothed distributions.
  5. protein fate  cosine of the predicted protein-fate profile: share of variants that remove the
                 protein (truncating, canonical splice, start loss, whole-gene loss: predicted null),
                 and the remaining protein-altering share split by curated mechanism evidence into
                 degraded (destabilised / decreased level), present but inactive (loss of function),
                 dominant negative, hyperactive (gain of function) and accumulating (increased level /
                 non-degradable). Evidence: the atlas's curated variant-group edges and G2P records.
  6. structure   0.5 x 3D fold similarity: TM-align TM-score of the AlphaFold models (pLDDT >= 70 residues),
                 normalised by the shorter protein (>= 0.5 = same fold), see mechsim_structure.py
                 + 0.2 x normalised Smith-Waterman alignment score (BLOSUM62) of the sequences
                 + 0.2 x protein-family overlap (0.6 Pfam family Jaccard + 0.4 Pfam clan Jaccard)
                 + 0.1 x Jaccard of UniProt molecular-function keywords (channel type, ion, gating).
                 Missing parts are dropped and the weights renormalised.
  +  drugs       (supplementary, not in the combined score) Jaccard of the compounds measured active
                 (pChEMBL >= 5, <= 10 uM) on each protein in ChEMBL 36, with the approved drugs among them:
                 "could the same molecules act on both?"
Combined: the mean percentile over the six axes that could be scored for that pair.

Graph links (atlas pairs only; inferred, confidence 0.30-0.49 by the schema rubric):
  an axis link is drawn when the pair's raw score clears the axis's floor (FLOOR), set near the 95th-98th
  percentile of all pairs on that axis. One `mechanistically_similar` link summarises pairs whose
  combined score clears COMBINED_MIN.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict

import numpy as np
from Bio import Align
from Bio.Align import substitution_matrices
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from dcommon import CURATED, DERIVED, ROOT, TODAY, read_json, write_json

IN = ROOT / "data" / "raw" / "comparison"
AXES = ["gene", "pathway", "tissue", "mutation", "fate", "structure", "drugs"]
CORE_AXES = AXES[:6]
AXIS_LABEL = {
    "gene": "same genes involved",
    "pathway": "same pathway / signalling route",
    "tissue": "same tissue",
    "mutation": "similar mutation types",
    "fate": "same molecular consequence for the protein",
    "structure": "similar protein structure / family",
    "drugs": "same compounds act on both proteins",
}
EDGE_TYPE = {
    "gene": "shares_gene",
    "pathway": "shares_pathway",
    "tissue": "shares_tissue",
    "mutation": "similar_mutation_spectrum",
    "fate": "similar_protein_fate",
    "structure": "similar_protein_structure",
    "drugs": "shares_pharmacology",
}
# absolute floors, set near the 95th-98th percentile of all 17,578 pairs (see meta.axis_quantiles), so each
# axis link marks a pair that is unusually alike on that axis, not merely "both neurological"
FLOOR = {"gene": 0.10, "pathway": 0.35, "tissue": 0.87, "mutation": 0.93, "fate": 0.98, "structure": 0.40,
         "drugs": 0.02}
COMBINED_MIN = 0.80
CLUSTER_CUT = 0.30          # average-linkage distance (1 - combined) at which clusters are cut
MIN_HPO_TERMS = 5
MIN_VARIANTS = 10
FATES = ["absent", "degraded", "inactive", "dominant_negative", "hyperactive", "accumulates"]
FATE_LABEL = {
    "absent": "no protein made (predicted null: truncating, canonical splice, start loss, whole-gene loss)",
    "degraded": "protein made but unstable / degraded",
    "inactive": "protein present but inactive (loss of function)",
    "dominant_negative": "protein present and poisons its partners (dominant negative)",
    "hyperactive": "protein present and overactive (gain of function)",
    "accumulates": "protein accumulates / is not degraded (increased level)",
}
NULL_CONSEQUENCES = {"frameshift", "nonsense (stop gained)", "canonical splice site", "start lost",
                     "whole-gene or multi-exon copy-number change"}
ALTERING_CONSEQUENCES = {"missense", "in-frame insertion/deletion", "other protein change", "stop lost"}
SIGNALLING = re.compile(r"SIGNAL|CASCADE|_PATHWAY$|RAS|MAPK|ERK|PI3K|MTOR", re.I)
CHANNEL_KEYWORDS = {"Voltage-gated channel", "Ligand-gated ion channel", "Sodium channel", "Potassium channel",
                    "Calcium channel", "Chloride channel"}


def pct_rank(values: np.ndarray) -> np.ndarray:
    """Mid-rank percentile among scored pairs: (n lower + n tied / 2) / n. Ties (e.g. the many pairs
    sharing no gene) get the middle of their block, so "no overlap" reads as neutral, not as dissimilar."""
    out = np.full(values.shape, np.nan)
    ok = ~np.isnan(values)
    v = values[ok]
    order = np.sort(v)
    lo = np.searchsorted(order, v, side="left")
    hi = np.searchsorted(order, v, side="right")
    out[ok] = (lo + hi) / 2 / max(len(v), 1)
    return out


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def cosine(u, v):
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    return float(u @ v / (nu * nv)) if nu and nv else float("nan")


def js_similarity(p, q):
    m = 0.5 * (p + q)
    def kl(x, y):
        nz = x > 0
        return float(np.sum(x[nz] * np.log2(x[nz] / y[nz])))
    return 1.0 - math.sqrt(max(0.0, 0.5 * kl(p, m) + 0.5 * kl(q, m)))


def pretty_pathway(name: str) -> str:
    head, _, rest = name.partition("_")
    return rest.replace("_", " ").lower().capitalize() if head in ("REACTOME", "WP", "KEGG", "BIOCARTA", "PID") else name


# ------------------------------------------------------------------ inputs
def load():
    ents = read_json(IN / "entities.json")["entities"]
    hpo = read_json(IN / "hpo.json")
    cv = read_json(IN / "clinvar.json")
    pw = read_json(IN / "pathways.json")
    gtex = read_json(IN / "gtex.json")
    prot = read_json(IN / "proteins.json")
    structures = read_json(IN / "structures.json")["genes"] if (IN / "structures.json").exists() else {}
    pharm = read_json(IN / "pharmacology.json")["genes"] if (IN / "pharmacology.json").exists() else {}
    drug_names = read_json(IN / "chembl_drug_names.json")["drugs"] if (IN / "chembl_drug_names.json").exists() else {}
    tm = {}
    if (IN / "tmalign.json").exists():
        rows = read_json(IN / "tmalign.json")["pairs"]
    else:  # structure step still running: use the pairs finished so far
        cache = ROOT / "data" / "raw" / "downloads" / "mechsim" / "tmalign_cache.jsonl"
        rows = [json.loads(l) for l in cache.read_text().splitlines()] if cache.exists() else []
    for a, b, t1, t2, rmsd in rows:
        tm[frozenset((a, b))] = (t1, t2, rmsd)
    string = {}
    with (IN / "string_network.tsv").open() as fh:
        rows = [l for l in fh if not l.startswith("#")]
    for r in csv.DictReader(rows, delimiter="\t"):
        string[frozenset((r["gene_a"], r["gene_b"]))] = {k: float(r[k]) for k in ("combined", "experimental", "database")}
    return ents, hpo, cv, pw, gtex, prot, string, structures, pharm, drug_names, tm


def g2p_by_gene():
    out = defaultdict(list)
    for path in sorted((ROOT / "data" / "derived" / "global" / "mechanism").glob("*.json")):
        shard = read_json(path)
        for disease, rec in shard.get("d", {}).items():
            for m in rec.get("mechanisms", []):
                if m.get("source") == "G2P" and m.get("gene"):
                    out[m["gene"]].append(dict(m, disease=disease))
    return out


# ------------------------------------------------------------------ profiles
def fate_profile(gene, ent_id, cv_gene, graph_edges, g2p):
    """Predicted protein fate. ClinVar gives the null vs protein-altering split; curated mechanism
    evidence says what the altering variants do to the protein."""
    cq = cv_gene.get("consequence", {}) if cv_gene else {}
    n_null = sum(v for k, v in cq.items() if k in NULL_CONSEQUENCES)
    n_alt = sum(v for k, v in cq.items() if k in ALTERING_CONSEQUENCES)
    votes, sources = Counter(), []
    for e in graph_edges.get(gene, []):
        votes[e["fate"]] += e["weight"]
        sources.append(f"atlas: {e['id']}")
    for m in g2p.get(gene, []):
        cons = (m.get("variant_consequence") or "").lower()
        label = (m.get("label_verbatim") or "").lower()
        cls = m.get("class")
        if "increased gene product level" in cons:
            fate = "accumulates"
        elif "destabilising" in label or ("decreased gene product level" in cons and "altered gene product structure" not in cons):
            fate = "degraded"
        elif cls == "mech:dominant-negative":
            fate = "dominant_negative"
        elif cls == "mech:gain-of-function":
            fate = "hyperactive"
        elif cls == "mech:loss-of-function" and "altered gene product structure" in cons:
            fate = "inactive"
        else:
            continue
        votes[fate] += 0.7
        sources.append(f"G2P {m.get('record')}: {m.get('label_verbatim')} / {m.get('variant_consequence')}")
    total = n_null + n_alt
    vec = np.zeros(len(FATES))
    if total:
        vec[FATES.index("absent")] = n_null / total
        alt_share = n_alt / total
        if votes:
            s = sum(votes.values())
            for f, w in votes.items():
                vec[FATES.index(f)] += alt_share * w / s
            unresolved = 0.0
        else:
            unresolved = alt_share
    else:
        unresolved = 1.0
    return {"vector": [round(x, 4) for x in vec], "unresolved": round(unresolved, 4),
            "n_null": n_null, "n_altering": n_alt, "missense_fate_votes": {k: round(v, 2) for k, v in votes.items()},
            "evidence": sources[:12]}


def curated_fate_edges(graph):
    """Atlas evidence on what protein-altering (missense / in-frame) variants do, as weighted fate votes.

    * variant-group -> mechanism edges of missense groups, weighted by edge confidence x the group's share
      of the gene's missense ClinVar records; curated subgroups without counts (e.g. vg:SCN1A:missense-gof,
      a minority subtype) count a quarter;
    * when the gene's main missense group has no mechanism edge, the disease-level driven_by effect edges
      stand in at half weight (e.g. SCN1A: loss of function / haploinsufficiency, plus a gain-of-function
      minority)."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    m2f = {"mech:gain-of-function": "hyperactive", "mech:dominant-negative": "dominant_negative",
           "mech:protein-destabilization": "degraded", "mech:loss-of-function": "inactive",
           "mech:haploinsufficiency": "inactive"}
    groups = defaultdict(list)
    for n in graph["nodes"]:
        a = n.get("attrs") or {}
        if n["type"] == "variant_group" and a.get("consequence") in ("missense", "mixed"):
            groups[a["gene"]].append(n)
    effects = defaultdict(list)
    for e in graph["edges"]:
        if e["type"] == "has_effect" and e["target"] in m2f:
            effects[e["source"]].append(e)
    driven = defaultdict(list)
    for e in graph["edges"]:
        if e["type"] == "driven_by" and e["target"] in m2f:
            driven[e["source"]].append(e)
    out = defaultdict(list)
    for gene, vgs in groups.items():
        sym = gene.removeprefix("gene:")
        total = sum(v["attrs"].get("clinvar_total_in_group") or 0 for v in vgs) or 1
        main_has_edge = False
        for vg in vgs:
            n_in = vg["attrs"].get("clinvar_total_in_group")
            share = n_in / total if n_in else 0.25
            for e in effects.get(vg["id"], []):
                out[sym].append({"id": e["id"], "fate": m2f[e["target"]], "weight": e.get("confidence", 0.5) * share})
                if n_in:
                    main_has_edge = True
        if not main_has_edge:
            for e in driven.get(f"disease:{sym}", []):
                out[sym].append({"id": e["id"], "fate": m2f[e["target"]], "weight": e.get("confidence", 0.5) * 0.5})
    return out


def channel_traits(p):
    mf = set(p.get("molecular_function") or [])
    if "Ion channel" not in mf:
        return None
    gating = "voltage-gated" if "Voltage-gated channel" in mf else "ligand-gated" if "Ligand-gated ion channel" in mf else "other gating"
    ions = [k.split()[0].lower() for k in ("Sodium channel", "Potassium channel", "Calcium channel", "Chloride channel") if k in mf]
    return {"gating": gating, "ions": ions or ["unspecified"]}


def main():
    ents, hpo, cv, pw, gtex, prot, string, structures, pharm, drug_names, tm = load()
    graph = read_json(ROOT / "data" / "graph.json")
    g2p = g2p_by_gene()
    fate_edges = curated_fate_edges(graph)
    n = len(ents)
    genes = [e["gene"] for e in ents]
    print(f"{n} entities ({sum(e['kind'] == 'atlas' for e in ents)} atlas, {sum(e['channel'] for e in ents)} channels)")

    # ---- tissue: symptom anchors + GTEx
    anchors = list(hpo["tissue_anchors"])
    terms = hpo["terms"]
    symptom = np.zeros((n, len(anchors)))
    n_terms = []
    for i, e in enumerate(ents):
        ts = hpo["entities"].get(e["id"], [])
        n_terms.append(len(ts))
        for t in ts:
            info = terms[t]
            for a in info["tissues"]:
                symptom[i, anchors.index(a)] += info["ic"]
    tissues_gtex = gtex["tissues"]
    expr = np.full((n, len(tissues_gtex)), np.nan)
    for i, g in enumerate(genes):
        if g in gtex["genes"]:
            expr[i] = np.log2(np.array(gtex["genes"][g]) + 1)

    # ---- pathways
    pw_sets = pw["sets"]
    n_univ = pw["n_genes_universe"]
    idf = {s: math.log(n_univ / v["size"]) for s, v in pw_sets.items()}
    gene_pw = [set(pw["genes"].get(g, [])) for g in genes]

    # ---- mutation spectra
    vtypes = sorted({k for g in genes for k in cv["genes"].get(g, {}).get("variant_type", {})})
    spec = np.zeros((n, len(vtypes)))
    for i, g in enumerate(genes):
        for k, v in cv["genes"].get(g, {}).get("variant_type", {}).items():
            spec[i, vtypes.index(k)] = v
    n_var = spec.sum(1)
    background = spec.sum(0) / spec.sum()
    smooth = (spec + 2 * background) / (n_var[:, None] + 2)

    # ---- fate
    fates = [fate_profile(g, e["id"], cv["genes"].get(g), fate_edges, g2p) for g, e in zip(genes, ents)]
    fvec = np.array([f["vector"] for f in fates])

    # ---- structure
    P = prot["genes"]
    aligner = Align.PairwiseAligner(mode="local")
    aligner.substitution_matrix = substitution_matrices.load("BLOSUM62")
    aligner.open_gap_score, aligner.extend_gap_score = -11, -1
    seqs = [P.get(g, {}).get("sequence") or structures.get(g, {}).get("sequence_from_model") for g in genes]
    self_score = [aligner.score(s, s) if s else None for s in seqs]
    pfam = [set(P.get(g, {}).get("pfam", [])) for g in genes]
    clans = [{prot["pfam"].get(x, {}).get("clan") for x in s} - {None} for s in pfam]
    mfk = [set(P.get(g, {}).get("molecular_function", [])) for g in genes]
    traits = [channel_traits(P.get(g, {})) for g in genes]
    active = [set(pharm.get(g, {}).get("active", [])) for g in genes]
    approved = [set(pharm.get(g, {}).get("approved", [])) for g in genes]

    # ---- pairwise
    iu = np.triu_indices(n, 1)
    npairs = len(iu[0])
    raw = {a: np.full(npairs, np.nan) for a in AXES}
    parts = {"seq": np.full(npairs, np.nan), "pfam": np.zeros(npairs), "string": np.zeros(npairs),
             "wjaccard": np.zeros(npairs), "symptom": np.full(npairs, np.nan), "expression": np.full(npairs, np.nan),
             "tm": np.full(npairs, np.nan)}
    for k, (i, j) in enumerate(zip(*iu)):
        a, b = ents[i], ents[j]
        raw["gene"][k] = jaccard(a["genes"], b["genes"])
        shared = gene_pw[i] & gene_pw[j]
        union = gene_pw[i] | gene_pw[j]
        wj = sum(idf[s] for s in shared) / sum(idf[s] for s in union) if union else 0.0
        st = string.get(frozenset((genes[i], genes[j])), {}).get("combined", 0.0)
        parts["wjaccard"][k], parts["string"][k] = wj, st
        raw["pathway"][k] = 1 - (1 - wj) * (1 - 0.5 * st) if (union or st) else np.nan
        sym = cosine(symptom[i], symptom[j]) if min(n_terms[i], n_terms[j]) >= MIN_HPO_TERMS else np.nan
        ex = np.nan
        if not (np.isnan(expr[i]).any() or np.isnan(expr[j]).any()) and expr[i].std() and expr[j].std():
            ex = max(0.0, float(np.corrcoef(expr[i], expr[j])[0, 1]))
        parts["symptom"][k], parts["expression"][k] = sym, ex
        vals = [v for v in (sym, ex) if not np.isnan(v)]
        raw["tissue"][k] = float(np.mean(vals)) if vals else np.nan
        if min(n_var[i], n_var[j]) >= MIN_VARIANTS:
            raw["mutation"][k] = js_similarity(smooth[i], smooth[j])
        if fates[i]["unresolved"] <= 0.8 and fates[j]["unresolved"] <= 0.8:
            raw["fate"][k] = cosine(fvec[i], fvec[j])
        comp = []  # (weight, value)
        t = tm.get(frozenset((genes[i], genes[j])))
        if t:
            parts["tm"][k] = max(t[0], t[1])
            comp.append((0.5, min(1.0, max(0.0, (parts["tm"][k] - 0.2) / 0.6))))
        if seqs[i] and seqs[j]:
            sw = aligner.score(seqs[i], seqs[j]) / math.sqrt(self_score[i] * self_score[j])
            parts["seq"][k] = sw
            comp.append((0.2, min(1.0, max(0.0, (sw - 0.02) / 0.5))))
        if pfam[i] and pfam[j]:
            fam = 0.6 * jaccard(pfam[i], pfam[j]) + 0.4 * jaccard(clans[i], clans[j])
            parts["pfam"][k] = fam
            comp.append((0.2, fam))
        if mfk[i] and mfk[j]:
            comp.append((0.1, jaccard(mfk[i], mfk[j])))
        if comp:
            raw["structure"][k] = sum(w * v for w, v in comp) / sum(w for w, _ in comp)
        if active[i] and active[j]:
            raw["drugs"][k] = jaccard(active[i], active[j])
        if k % 3000 == 0:
            print(f"  pairs {k}/{npairs}")
    pct = {a: pct_rank(raw[a]) for a in AXES}
    stack = np.vstack([pct[a] for a in CORE_AXES])
    combined = np.nanmean(np.where(np.isnan(stack), np.nan, stack), axis=0)
    n_axes = (~np.isnan(stack)).sum(0)

    # ---- clusters (average linkage over 1 - combined)
    dist = np.ones((n, n))
    dist[iu] = 1 - np.nan_to_num(combined, nan=0.0)
    dist[(iu[1], iu[0])] = dist[iu]
    np.fill_diagonal(dist, 0)
    Z = linkage(squareform(dist, checks=False), method="average")
    labels = fcluster(Z, t=CLUSTER_CUT, criterion="distance")

    # ---- profiles for output
    def top_tissues_symptom(i):
        v = symptom[i]
        s = v.sum()
        if not s or n_terms[i] < MIN_HPO_TERMS:
            return []
        order = np.argsort(-v)
        return [[anchors[t], round(float(v[t] / s), 3)] for t in order[:4] if v[t] / s >= 0.08]

    def top_tissues_expr(i):
        if np.isnan(expr[i]).any():
            return []
        order = np.argsort(-expr[i])[:3]
        return [[tissues_gtex[t], round(float(2 ** expr[i][t] - 1), 1)] for t in order]

    profiles = []
    for i, e in enumerate(ents):
        g = genes[i]
        p = P.get(g, {})
        top_pw = sorted(gene_pw[i], key=lambda s: -idf[s])
        profiles.append({
            "id": e["id"], "gene": g, "kind": e["kind"], "label": e["label"], "family": e.get("family"),
            "channel": traits[i], "mondo": e["mondo"][:20], "diseases": e["diseases"], "genes": e["genes"],
            "pathways": top_pw[:40], "n_pathways": len(gene_pw[i]),
            "tissue": {"symptoms": top_tissues_symptom(i), "n_hpo_terms": n_terms[i],
                       "expression_top": top_tissues_expr(i), "hpa_specificity": p.get("tissue_specificity")},
            "mutation": {"n": int(n_var[i]), "types": {vtypes[t]: int(spec[i, t]) for t in np.argsort(-spec[i]) if spec[i, t]},
                         "consequence": cv["genes"].get(g, {}).get("consequence", {})},
            "fate": dict(fates[i], labels=FATES),
            "structure": {"uniprot": p.get("uniprot"), "length": len(p["sequence"]) if p.get("sequence") else None,
                          "pfam": sorted(pfam[i]), "clans": sorted(clans[i]),
                          "molecular_function": sorted(mfk[i]), "protein_class": p.get("protein_class", []),
                          "fda_drug_target": "FDA approved drug targets" in (p.get("protein_class") or []),
                          "pdb": {k: structures.get(g, {}).get(k) for k in
                                  ("n_pdb_entries", "pdb_entries", "methods", "best_resolution", "longest_construct",
                                   "alphafold")}},
            "drugs": {"n_active": len(active[i]), "approved": [
                {"id": c, "name": (drug_names.get(c) or {}).get("name")} for c in sorted(approved[i])][:40]},
            "cluster": int(labels[i]),
        })

    cl_members = defaultdict(list)
    for i, c in enumerate(labels):
        cl_members[int(c)].append(i)
    clusters = []
    for c, idx in sorted(cl_members.items(), key=lambda kv: -len(kv[1])):
        if len(idx) < 2:
            continue
        sub = [k for k, (i, j) in enumerate(zip(*iu)) if i in idx and j in idx]
        axis_mean = {a: round(float(np.nanmean(pct[a][sub])), 3) if np.any(~np.isnan(pct[a][sub])) else None for a in AXES}
        strongest = sorted((a for a in CORE_AXES if axis_mean[a] is not None), key=lambda a: -axis_mean[a])[:3]
        clusters.append({"id": f"MS{c:03d}", "members": [ents[i]["id"] for i in idx],
                         "genes": [genes[i] for i in idx], "axis_mean_percentile": axis_mean,
                         "strongest_axes": strongest,
                         "label": " · ".join(AXIS_LABEL[a] for a in strongest)})

    pair_rows = []
    for k, (i, j) in enumerate(zip(*iu)):
        extra = [parts["tm"][k], parts["seq"][k], parts["symptom"][k], parts["expression"][k], parts["string"][k]]
        pair_rows.append([int(i), int(j)] + [None if np.isnan(raw[a][k]) else round(float(raw[a][k]), 3) for a in AXES]
                         + [None if np.isnan(combined[k]) else round(float(combined[k]), 3)]
                         + [None if (x is None or np.isnan(x)) else round(float(x), 3) for x in extra])
    pfam_info = {x: prot["pfam"].get(x) for x in sorted(set().union(*pfam))}
    used_drugs = {c for s in approved for c in s}
    drug_info = {c: drug_names.get(c, {}).get("name") for c in sorted(used_drugs)}
    used_pw = sorted({s for p in profiles for s in p["pathways"]})
    out = {
        "meta": {
            "generated": TODAY, "method": "pipeline/derive/mechsim.py (see its docstring)",
            "entities": n, "pairs": npairs, "axes": AXES, "core_axes": CORE_AXES, "axis_label": AXIS_LABEL,
            "tmalign_pairs": len(tm),
            "edge_rule": {"floor": FLOOR, "combined_min": COMBINED_MIN},
            "fate_labels": FATE_LABEL, "tissue_anchors": anchors,
            "sources": {k: read_json(IN / f).get("source") for k, f in
                        (("clinvar", "clinvar.json"), ("pathways", "pathways.json"), ("gtex", "gtex.json"),
                         ("proteins", "proteins.json"))} | {
                "hpo": f"hp.obo {hpo['hp_obo']}, phenotype.hpoa {hpo['phenotype_hpoa']}",
                "string": "STRING v12 network among atlas genes (data/raw/comparison/string_network.tsv)",
                "g2p": "Gene2Phenotype records in data/derived/global/mechanism",
                "structures": "RCSB PDB (Search + Data API) entries per UniProt accession; AlphaFold DB v4 models",
                "tmalign": "TM-align (tmtools) on AlphaFold models, residues with pLDDT >= 70",
                "pharmacology": "ChEMBL 36 bioactivities, pChEMBL >= 5"},
            "pathway_percentile_note": "percentile = mid-rank share of all scored pairs with a lower raw score on that axis",
            "axis_quantiles": {a: [round(float(q), 3) for q in np.nanquantile(raw[a], [0.5, 0.9, 0.95, 0.98])]
                               for a in AXES},
        },
        "pathway_sets": {s: {"name": pretty_pathway(pw_sets[s]["name"]), "origin": pw_sets[s]["origin"],
                             "url": pw_sets[s]["url"], "size": pw_sets[s]["size"]} for s in used_pw},
        "pfam": pfam_info,
        "drug_names": drug_info,
        "profiles": profiles,
        "clusters": clusters,
        "pair_fields": ["i", "j"] + AXES + ["combined", "tm_score", "sequence_score", "symptom_cosine",
                                             "expression_correlation", "string_score"],
        "pairs": pair_rows,
    }
    size = write_json(DERIVED / "mechsim.json", out, compact=True)
    print(f"wrote data/derived/mechsim.json ({size / 1e6:.2f} MB), {len(clusters)} clusters")

    # ---- graph fragment (atlas pairs only)
    write_fragment(ents, genes, iu, raw, pct, combined, n_axes, parts, profiles, gene_pw, pw_sets, idf, string,
                   pfam_info, labels, clusters, (active, approved, drug_names))

    # ---- sanity summary
    for a in AXES:
        v = raw[a][~np.isnan(raw[a])]
        print(f"  {a:9s} scored {len(v):6d} pairs  median {np.median(v):.3f}  p90 {np.quantile(v, .9):.3f}")


# ------------------------------------------------------------------ explanations
def explain(axis, a, b, k, ctx):
    (genes, raw, parts, profiles, gene_pw, pw_sets, idf, string, pfam_info, i, j, drugs) = ctx
    A, B = profiles[i], profiles[j]
    ga, gb = A["gene"], B["gene"]
    if axis == "gene":
        shared = sorted(set(A["genes"]) & set(B["genes"]))
        shared_d = sorted(set(A["mondo"]) & set(B["mondo"]))
        return (f"{ga}- and {gb}-related disorders share clinical entities caused by the same genes "
                f"({', '.join(shared)}){'; shared MONDO entries ' + ', '.join(shared_d[:4]) if shared_d else ''}."), \
            {"shared_genes": shared, "shared_mondo": shared_d}
    if axis == "pathway":
        shared = sorted(gene_pw[i] & gene_pw[j], key=lambda s: -idf[s])
        sig = [s for s in shared if SIGNALLING.search(pw_sets[s]["name"])]
        names = [pretty_pathway(pw_sets[s]["name"]) for s in shared[:5]]
        st = string.get(frozenset((ga, gb)))
        txt = f"{ga} and {gb} sit in the same canonical pathways"
        if names:
            txt += f": {'; '.join(names)}"
        if sig:
            txt += f". Both act in the same signalling route ({pretty_pathway(pw_sets[sig[0]]['name'])}), as different parts of it"
        if st:
            kind = "experimentally" if st["experimental"] >= 0.15 else "in curated pathway databases"
            txt += f". STRING links the two proteins directly ({kind}; combined score {st['combined']:.2f})"
        return txt + ".", {"shared_pathways": shared[:15], "signalling": sig[:5], "weighted_jaccard": round(float(parts["wjaccard"][k]), 3),
                           "string": st}
    if axis == "tissue":
        ta = [t for t, _ in A["tissue"]["symptoms"]]
        tb = [t for t, _ in B["tissue"]["symptoms"]]
        both = [t for t in ta if t in tb]
        ea = [t for t, _ in A["tissue"]["expression_top"]]
        eb = [t for t, _ in B["tissue"]["expression_top"]]
        txt = f"Symptoms of both point to the same tissues ({', '.join(both) or 'similar organ-system mix'})"
        sym, ex = parts["symptom"][k], parts["expression"][k]
        txt += f" (symptom-profile cosine {sym:.2f})" if not np.isnan(sym) else ""
        if not np.isnan(ex):
            txt += f"; GTEx expression profiles correlate at {ex:.2f} (top tissues {', '.join(ea[:2])} vs {', '.join(eb[:2])})"
        return txt + ".", {"shared_symptom_tissues": both, "symptom_cosine": None if np.isnan(sym) else round(float(sym), 3),
                           "expression_correlation": None if np.isnan(ex) else round(float(ex), 3)}
    if axis == "mutation":
        def top(p):
            n = p["mutation"]["n"]
            return ", ".join(f"{t} {100 * c / n:.0f}%" for t, c in list(p["mutation"]["types"].items())[:3])
        return (f"The pathogenic ClinVar variants have a similar type mix: {ga} ({A['mutation']['n']} variants: {top(A)}) "
                f"vs {gb} ({B['mutation']['n']}: {top(B)})."), {}
    if axis == "fate":
        def top(p):
            v = p["fate"]["vector"]
            order = sorted(range(len(FATES)), key=lambda x: -v[x])
            return ", ".join(f"{FATES[x].replace('_', ' ')} {100 * v[x]:.0f}%" for x in order[:2] if v[x] >= 0.05)
        return (f"Variants do the same thing to the protein: {ga} ({top(A)}) and {gb} ({top(B)}). "
                "Null share from ClinVar consequences; the fate of protein-altering variants from curated mechanism evidence."), {}
    if axis == "structure":
        sa, sb = set(A["structure"]["pfam"]), set(B["structure"]["pfam"])
        shared = sorted(sa & sb)
        fam = [f"{pfam_info[x]['name']} ({x})" for x in shared if pfam_info.get(x) and pfam_info[x].get("name")]
        cl = sorted(set(A["structure"]["clans"]) & set(B["structure"]["clans"]))
        txt = f"{ga} and {gb} proteins are structurally related"
        if fam:
            txt += f": shared Pfam families {', '.join(fam)}"
        elif cl:
            txt += f": same Pfam clan {', '.join(cl)}"
        if not np.isnan(parts["tm"][k]):
            txt += (f"; AlphaFold models superpose with TM-score {parts['tm'][k]:.2f}"
                    f"{' (same fold)' if parts['tm'][k] >= 0.5 else ''}")
        if not np.isnan(parts["seq"][k]):
            txt += f"; sequence alignment score {parts['seq'][k]:.2f} of self-alignment"
        ca, cb = A["channel"], B["channel"]
        if ca and cb:
            same_gate = ca["gating"] == cb["gating"]
            same_ion = sorted(set(ca["ions"]) & set(cb["ions"]))
            txt += (f". Both are {ca['gating']} channels" if same_gate else f". Gating differs ({ca['gating']} vs {cb['gating']})")
            if same_ion:
                txt += f" for {'/'.join(same_ion)}"
            if same_gate and (parts["seq"][k] >= 0.3 or parts["tm"][k] >= 0.6):
                txt += (". Closely related channels may share activation mechanism and drug binding sites, so a compound "
                        "acting on one is a candidate to test on the other (hypothesis, to discuss with experts)")
        return txt + ".", {"shared_pfam": shared, "shared_clans": cl,
                           "sequence_score": None if np.isnan(parts["seq"][k]) else round(float(parts["seq"][k]), 3),
                           "tm_score": None if np.isnan(parts["tm"][k]) else round(float(parts["tm"][k]), 3)}
    if axis == "drugs":
        active, approved, names = drugs
        shared = active[i] & active[j]
        shared_appr = sorted(approved[i] & approved[j])
        nm = [(names.get(c) or {}).get("name") or c for c in shared_appr]
        txt = (f"{len(shared)} compounds in ChEMBL are measured active (<= 10 uM) on both the {ga} and the {gb} protein")
        if nm:
            txt += f", including approved drugs: {', '.join(n.lower() for n in nm[:8])}"
        txt += (". Shared pharmacology suggests similar binding sites; any use for these disorders is a hypothesis "
                "to discuss with clinicians and researchers, not a treatment recommendation.")
        return txt, {"n_shared_active": len(shared), "shared_approved": shared_appr[:20]}
    raise ValueError(axis)


def write_fragment(ents, genes, iu, raw, pct, combined, n_axes, parts, profiles, gene_pw, pw_sets, idf, string,
                   pfam_info, labels, clusters, drugs):
    ev_source = {"gene": ("MONDO", "https://github.com/monarch-initiative/mondo/releases"),
                 "pathway": ("Atlas", "https://www.gsea-msigdb.org/gsea/msigdb/human/genesets.jsp?collection=CP"),
                 "tissue": ("HPO", "https://github.com/obophenotype/human-phenotype-ontology/releases"),
                 "mutation": ("ClinVar", "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/"),
                 "fate": ("ClinVar", "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/"),
                 "structure": ("UniProt", "https://www.rcsb.org/"),
                 "drugs": ("Atlas", "https://www.ebi.ac.uk/chembl/")}
    ev_title = {"gene": "Gene sets of MONDO disease entries (global index, OMIM/mim2gene genes)",
                "pathway": "MSigDB canonical pathways (Reactome, WikiPathways, KEGG, BioCarta, PID) + STRING v12",
                "tissue": "HPO symptom profiles over 20 tissue anchors + GTEx v10 median expression",
                "mutation": "ClinVar P/LP germline variant types (variant_summary)",
                "fate": "ClinVar consequences + curated mechanism edges (atlas, Gene2Phenotype)",
                "structure": "AlphaFold DB models (TM-align), Swiss-Prot sequences (Smith-Waterman, BLOSUM62), Pfam families/clans, UniProt keywords",
                "drugs": "ChEMBL 36 bioactivities (pChEMBL >= 5)"}
    edges, by_pair = [], defaultdict(list)
    for k, (i, j) in enumerate(zip(*iu)):
        a, b = ents[i], ents[j]
        if a["kind"] != "atlas" or b["kind"] != "atlas":
            continue
        src, tgt = sorted((a["id"], b["id"]))
        ctx = (genes, raw, parts, profiles, gene_pw, pw_sets, idf, string, pfam_info, i, j, drugs)
        scores = {x: None if np.isnan(raw[x][k]) else round(float(raw[x][k]), 3) for x in AXES}
        pcts = {x: None if np.isnan(pct[x][k]) else round(float(pct[x][k]), 3) for x in AXES}
        for axis in AXES:
            r, p = raw[axis][k], pct[axis][k]
            if np.isnan(r) or r < FLOOR[axis]:
                continue
            text, detail = explain(axis, a, b, k, ctx)
            by_pair[(src, tgt)].append(axis)
            source, url = ev_source[axis]
            edges.append({
                "id": f"{src}|{EDGE_TYPE[axis]}|{tgt}", "source": src, "target": tgt, "type": EDGE_TYPE[axis],
                "label": AXIS_LABEL[axis], "explanation": text, "evidence_level": "inferred", "status": "supported",
                "confidence": round(0.30 + 0.19 * float(r), 2),
                "evidence": [{"source": "Atlas", "ref": "pipeline/derive/mechsim.py", "url": url,
                              "title": f"{ev_title[axis]} ({source}); score {r:.2f}, above {100 * p:.0f}% of "
                                       f"{int((~np.isnan(raw[axis])).sum())} disease pairs",
                              "kind": "computed", "extracted_by": "computed", "retrieved": TODAY}],
                "attrs": {"axis": axis, "score": round(float(r), 3), "percentile": round(float(p), 3),
                          "all_axes": scores, "all_percentiles": pcts, "computed": True, **detail},
            })
        c = combined[k]
        if not np.isnan(c) and c >= COMBINED_MIN and n_axes[k] >= 4:
            strong = [x for x in CORE_AXES if pcts[x] is not None and pcts[x] >= 0.75]
            edges.append({
                "id": f"{src}|mechanistically_similar|{tgt}", "source": src, "target": tgt,
                "type": "mechanistically_similar", "label": "mechanistically similar",
                "explanation": (f"Across the six mechanistic axes, {genes[i]} and {genes[j]} are more alike than "
                                f"{100 * c:.0f}% of disease pairs on average. Strongest: "
                                f"{', '.join(AXIS_LABEL[x] for x in strong) or 'no single axis'}."),
                "evidence_level": "inferred", "status": "supported", "confidence": round(0.30 + 0.19 * float(c), 2),
                "evidence": [{"source": "Atlas", "ref": "pipeline/derive/mechsim.py", "url": "https://github.com/k14-coder/rare-disease-atlas/blob/main/pipeline/derive/mechsim.py",
                              "title": "Mean percentile over gene, pathway, tissue, mutation-type, protein-fate and "
                                       "protein-structure similarity", "kind": "computed", "extracted_by": "computed",
                              "retrieved": TODAY}],
                "attrs": {"combined": round(float(c), 3), "axes_scored": int(n_axes[k]), "strong_axes": strong,
                          "all_axes": scores, "all_percentiles": pcts, "computed": True},
            })
    # clusters with at least two atlas diseases
    ids = {e["id"] for e in edges}
    frag_clusters = []
    for c in clusters:
        members = [m for m in c["members"] if m.startswith("disease:")]
        if len(members) < 2:
            continue
        eids = sorted(x for x in ids if x.split("|")[0] in members and x.split("|")[2] in members
                      and "|mechanistically_similar|" in x)
        frag_clusters.append({
            "id": f"cluster:mechsim-{c['id'].lower()}", "label": f"Mechanistic cluster: {', '.join(m.split(':')[1] for m in members[:6])}"
                                                            f"{'…' if len(members) > 6 else ''}",
            "basis": "mechanism", "members": members,
            "rationale": (f"Computed by average-linkage clustering on the six mechanistic axes. Strongest shared axes: "
                          f"{c['label']}. Includes {len(c['members']) - len(members)} channelopathy-panel genes outside the atlas "
                          f"({', '.join(g for g, m in zip(c['genes'], c['members']) if not m.startswith('disease:'))[:200]})." if
                          len(c["members"]) > len(members) else
                          f"Computed by average-linkage clustering on the six mechanistic axes. Strongest shared axes: {c['label']}."),
            "edge_ids": eids,
        })
    counts = Counter(e["type"] for e in edges)
    write_json(CURATED / "mechanistic_links.json", {
        "_about": "Computed by pipeline/derive/mechsim.py; do not edit by hand. Inferred disease-disease links on six "
                  "mechanistic axes (gene, pathway, tissue, mutation type, protein fate, protein structure).",
        # clusters stay in data/derived/mechsim.json (shown on /mechanisms): as graph clusters they would
        # recolour the curated map
        "nodes": [], "edges": edges, "clusters": [], "gaps": [], "_clusters_preview": frag_clusters})
    print(f"wrote data/curated/mechanistic_links.json: {dict(counts)}; {len(frag_clusters)} clusters")


if __name__ == "__main__":
    main()
