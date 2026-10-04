"""Research recommendations: for every atlas disease, which other atlas disease is closest by mechanism,
by funding route, by tissue / drug-delivery route and by symptoms, and why.

Run:  python3 pipeline/derive/research_recs.py              full build (~1-3 min; TM-align results are cached)
      python3 pipeline/derive/research_recs.py --add GENE   slot one new disease into the stored rankings
      python3 pipeline/derive/test_research_recs.py         --add on a held-out gene == full recompute
      then node web/scripts/sync-data.mjs
In:   data/derived/mechsim.json                 six-axis mechanistic similarity (profiles + all pairwise raw
                                                scores), from pipeline/derive/mechsim.py
      data/raw/comparison/hpo.json              HPO annotations per entity + information content per term
      data/raw/comparison/mutant_structures.json  experimental PDB structures carrying a ClinVar P/LP missense
                                                change, with CA traces (pipeline/derive/research_recs_fetch.py)
      data/raw/downloads/mechsim/alphafold/     AlphaFold DB v4 WT models (only for new TM-align runs)
      data/graph.json                           grants (NIH RePORTER) + funding programmes, gene attributes
Out:  data/derived/research_recs.json           per disease: the closest disease per category with a short
                                                explanation, the per-marker breakdown, top-k lists, clusters
      data/raw/derive/research_recs_state.json  cached per-disease features + stored top-k lists + clusters,
                                                so --add only computes the new disease's n similarities

Categories (all outputs are computed and therefore "inferred" / hypotheses, never facts):
  mechanistic  0.30 x mutation type   (mechsim `mutation` axis: ClinVar P/LP variant-type spectra)
             + 0.35 x molecular consequence (mechsim `fate` axis: predicted protein fate profile)
             + 0.35 x 3D structure accordance (TM-score between the two protein models: an experimental
               structure carrying a disease missense change when one exists, else the AlphaFold WT model)
               Each marker is first turned into its percentile among all 17,578 mechsim pairs (a fixed
               reference, so adding a disease never re-scales the others). A marker that cannot be scored
               (e.g. < 10 ClinVar variants) is dropped and the remaining weights renormalised; the record
               says which marker is missing. No gap is ever filled with an invented value.
  funding      mechsim `pathway` axis (IDF-weighted shared canonical pathways combined with a STRING
               interaction). Shared signalling = likely shared funders: the partner's funders (NIH institute
               from the grant number, named funding programmes) that the disease itself lacks are listed.
  tissue       mechsim `tissue` axis (symptom-anchor cosine + GTEx expression correlation), plus a rule-based
               delivery route per disease (CNS: intrathecal / ICV AAV9 or ASO; systemic: ERT for secreted
               lysosomal enzymes, small molecule or liver LNP otherwise) and whether the CDS fits one AAV.
  symptoms     IC-weighted Jaccard of the HPO term sets; shared distinctive terms (IC >= 4) are listed.
Clusters: average linkage on mechanistic closeness, cut at CLUSTER_MIN; --add joins the cluster with the
highest average linkage >= CLUSTER_MIN or starts a new one.
"""
from __future__ import annotations

import argparse
import bisect
import heapq
import json
import re
import sys
from collections import defaultdict

import numpy as np

from dcommon import DERIVED, GRAPH, RAW_DERIVE, ROOT, TODAY, read_json, write_json

IN = ROOT / "data" / "raw" / "comparison"
OUT = DERIVED / "research_recs.json"
STATE = RAW_DERIVE / "research_recs_state.json"
TM_CACHE = RAW_DERIVE / "research_recs_tmalign.jsonl"
K = 10
MECH_W = {"mutation": 0.30, "fate": 0.35, "structure": 0.35}
CATEGORIES = ["mechanistic", "funding", "tissue", "symptoms"]
CLUSTER_MIN = 0.70        # average mechanistic closeness needed to share a cluster
DISTINCTIVE_IC = 4.0
AAV_LIMIT_BP = 4700
NIH_IC = {"NS": "NIH NINDS", "DK": "NIH NIDDK", "HD": "NIH NICHD", "MH": "NIH NIMH", "TR": "NIH NCATS",
          "GM": "NIH NIGMS", "CA": "NIH NCI", "HL": "NIH NHLBI", "AR": "NIH NIAMS", "EY": "NIH NEI",
          "AI": "NIH NIAID", "AG": "NIH NIA", "DA": "NIH NIDA", "OD": "NIH Office of the Director"}
FATE_LABELS = ["absent", "degraded", "inactive", "dominant_negative", "hyperactive", "accumulates"]
FATE_TEXT = {"absent": "no protein made", "degraded": "unstable protein", "inactive": "inactive protein",
             "dominant_negative": "dominant-negative protein", "hyperactive": "overactive protein",
             "accumulates": "accumulating protein"}
NO_PREDICTOR = "not available (WT model used; no structure predictor in this environment)"
CLINICIAN = "to discuss with your clinician"


# ----------------------------------------------------------------------------------------------- context
class Context:
    """Everything shared by all diseases: mechsim pairs, reference distributions, HPO, graph funders."""

    def __init__(self):
        ms = read_json(DERIVED / "mechsim.json")
        self.ms = ms
        self.prof = {p["gene"]: p for p in ms["profiles"] if p["kind"] == "atlas"}
        self.idx = {p["gene"]: i for i, p in enumerate(ms["profiles"])}
        f = {k: i for i, k in enumerate(ms["pair_fields"])}
        self.f = f
        self.pairs = {}
        ref = defaultdict(list)
        for r in ms["pairs"]:
            self.pairs[(r[f["i"]], r[f["j"]])] = r
            for ax in ("mutation", "fate", "tm_score", "pathway", "tissue"):
                if r[f[ax]] is not None:
                    ref[ax].append(r[f[ax]])
        self.ref = {ax: np.sort(np.array(v)) for ax, v in ref.items()}
        self.pathway_sets = ms["pathway_sets"]
        hpo = read_json(IN / "hpo.json")
        self.hpo_terms = hpo["terms"]
        self.hpo_ent = hpo["entities"]
        self.mutants = read_json(IN / "mutant_structures.json")["genes"]
        g = read_json(GRAPH)
        self.nodes = {n["id"]: n for n in g["nodes"]}
        self.funders = defaultdict(list)
        for e in g["edges"]:
            src = self.nodes.get(e["source"], {})
            if e["type"] == "about" and src.get("type") == "grant":
                gene = e["target"].split(":", 1)[1]
                self.funders[gene].append(grant_record(src))
            elif e["type"] == "covers" and src.get("type") == "asset" and \
                    (src.get("attrs") or {}).get("kind") == "funding_program":
                gene = e["target"].split(":", 1)[1]
                self.funders[gene].append({"funder": src["label"], "id": src["id"], "title": src.get("summary"),
                                           "url": (src.get("attrs") or {}).get("url"), "kind": "programme"})
        self.tm_cache = {}
        if TM_CACHE.exists():
            for line in TM_CACHE.read_text().splitlines():
                a, b, t1, t2 = json.loads(line)
                self.tm_cache[(a, b)] = (t1, t2)
        self._models = {}

    def pct(self, axis, v):
        """Mid-rank percentile of v among all mechsim pairs on this axis (fixed reference)."""
        arr = self.ref[axis]
        lo = np.searchsorted(arr, v, side="left")
        hi = np.searchsorted(arr, v, side="right")
        return float((lo + hi) / 2 / len(arr))

    def pair(self, ga, gb):
        i, j = self.idx[ga], self.idx[gb]
        return self.pairs.get((i, j)) or self.pairs.get((j, i))

    # ---- structure
    def model_coords(self, model):
        """CA coordinates + sequence for a structure model descriptor."""
        key = model["id"]
        if key in self._models:
            return self._models[key]
        if model["kind"] == "experimental_mutant":
            ca = self.mutants[model["gene"]]["representative"]["ca"]
            xyz = np.array([[c[2], c[3], c[4]] for c in ca])
            seq = "".join(c[1] for c in ca)
        else:
            from mechsim_structure import load_model
            xyz, seq, _full, _pl = load_model(model["uniprot"])
        self._models[key] = (xyz, seq)
        return self._models[key]

    def tm(self, ma, mb):
        """TM-score (max of the two normalisations, as in mechsim) between two models."""
        a, b = sorted([ma["id"], mb["id"]])
        if (a, b) not in self.tm_cache:
            from tmtools import tm_align
            xa, sa = self.model_coords(ma if ma["id"] == a else mb)
            xb, sb = self.model_coords(mb if mb["id"] == b else ma)
            r = tm_align(xa, xb, sa, sb)
            self.tm_cache[(a, b)] = (round(float(r.tm_norm_chain1), 4), round(float(r.tm_norm_chain2), 4))
            TM_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(TM_CACHE, "a") as fh:
                fh.write(json.dumps([a, b, *self.tm_cache[(a, b)]]) + "\n")
        return max(self.tm_cache[(a, b)])


def grant_record(n):
    a = n.get("attrs") or {}
    code = n["id"].split(":", 1)[1]
    m = re.match(r"[A-Z]\d{2}([A-Z]{2})\d", code)
    funder = a.get("agency") and f"NIH {a['agency']}" or (m and NIH_IC.get(m.group(1))) or "NIH"
    return {"funder": funder, "id": n["id"], "title": a.get("title") or n.get("label"), "url": a.get("url"),
            "org": a.get("org"), "amount": a.get("amount"), "activity_code": a.get("activity_code"), "kind": "grant"}


# ----------------------------------------------------------------------------------------------- features
def delivery(p, gene_attrs):
    """Rule-based delivery route from the symptom tissue anchors, GTEx expression and protein class."""
    anchors = dict(p["tissue"]["symptoms"])
    top = p["tissue"]["symptoms"][0][0] if p["tissue"]["symptoms"] else None
    brain = anchors.get("brain (central nervous system)", 0.0)
    expr_top = p["tissue"]["expression_top"][0][0] if p["tissue"]["expression_top"] else ""
    loc = gene_attrs.get("subcellular_location") or []
    lysosomal_enzyme = bool(gene_attrs.get("is_enzyme")) and any("Lysosome" in x for x in loc)
    cns = top == "brain (central nervous system)" or brain >= 0.3 or (not top and expr_top.startswith("Brain"))
    if lysosomal_enzyme:
        cls = "systemic + CNS" if brain >= 0.15 else "systemic"
        options = ["intravenous enzyme replacement (ERT) for body organs"]
        if brain >= 0.15:
            options.append("ERT does not cross the blood-brain barrier: intrathecal / ICV enzyme or AAV9 for the brain")
    elif cns:
        cls = "CNS"
        options = ["intrathecal / ICV AAV9 gene therapy", "intrathecal antisense oligonucleotide (ASO)"]
    else:
        cls = "systemic"
        options = ["oral / IV small molecule", "liver-directed LNP (nucleic acid) where the liver is a target"]
    cds = gene_attrs.get("cds_length_bp")
    fits = gene_attrs.get("aav_cds_fits_4_7kb")
    fits_source = "gene.attrs.aav_cds_fits_4_7kb"
    if fits is None and cds:
        fits, fits_source = cds <= AAV_LIMIT_BP, f"computed: CDS {cds} bp vs ~{AAV_LIMIT_BP} bp AAV capacity"
    return {"class": cls, "target_tissue": top, "brain_share": round(brain, 3), "expression_top": expr_top or None,
            "options": options, "cds_length_bp": cds, "aav_cds_fits": fits, "aav_fit_source": fits_source,
            "lysosomal_enzyme": lysosomal_enzyme}


def structure_model(ctx, gene):
    p = ctx.prof[gene]
    acc = p["structure"]["uniprot"]
    null_share = round(p["fate"]["vector"][0], 3)
    m = ctx.mutants.get(gene) or {}
    rep = m.get("representative")
    note = None
    if null_share > 0.5:
        note = (f"{round(null_share * 100)}% of ClinVar P/LP variants are predicted to leave no stable protein; "
                "the structure marker compares the protein made by the missense minority")
    if rep:
        return {"kind": "experimental_mutant", "id": f"pdb:{rep['entity']}", "gene": gene, "uniprot": acc,
                "pdb_entity": rep["entity"], "chain": rep["chain"], "mutations": rep["disease_mutations"],
                "engineered_mutations": rep["other_mutations"], "author_numbering": rep["author_numbering"],
                "residues": rep["residue_range"], "coordinates": rep["coordinates"],
                "clinvar": rep["clinvar"], "n_mutant_entities": m.get("n_mutant_entities", 0),
                "label": f"experimental mutant PDB {rep['entity']} ({', '.join(rep['disease_mutations'])}), "
                         f"residues {rep['residue_range'][0]}-{rep['residue_range'][1]}",
                "null_share": null_share, "note": note}
    af = p["structure"]["pdb"]["alphafold"]
    return {"kind": "alphafold_wt", "id": f"af:{acc}", "gene": gene, "uniprot": acc, "alphafold": af["id"],
            "mutant_model": NO_PREDICTOR, "label": f"AlphaFold WT model {af['id']} (pLDDT >= 70 residues)",
            "partial_model": af.get("partial_model", False), "n_mutant_entities": m.get("n_mutant_entities", 0),
            "null_share": null_share, "note": note}


def features(ctx, gene):
    p = ctx.prof[gene]
    gattrs = (ctx.nodes.get(f"gene:{gene}") or {}).get("attrs") or {}
    hpo = {t: ctx.hpo_terms[t]["ic"] for t in ctx.hpo_ent.get(f"disease:{gene}", []) if t in ctx.hpo_terms}
    vec = p["fate"]["vector"]
    dom = FATE_LABELS[int(np.argmax(vec))] if any(vec) else None
    return {"gene": gene, "id": p["id"], "label": p["label"], "family": p["family"],
            "pathways": sorted(p["pathways"]), "hpo": hpo, "delivery": delivery(p, gattrs),
            "structure": structure_model(ctx, gene), "dominant_fate": dom,
            "n_variants": p["mutation"]["n"], "funders": ctx.funders.get(gene, [])}


# ----------------------------------------------------------------------------------------------- pair scores
def r4(x):
    return None if x is None else round(float(x), 4)


def pair_scores(ctx, fa, fb):
    """All category scores for one pair. Symmetric and deterministic (rounded), so incremental == full."""
    row = ctx.pair(fa["gene"], fb["gene"])
    f = ctx.f
    mut = row[f["mutation"]] if row else None
    fate = row[f["fate"]] if row else None
    sa, sb = fa["structure"], fb["structure"]
    if sa["kind"] == "alphafold_wt" and sb["kind"] == "alphafold_wt":
        tm = row[f["tm_score"]] if row else None          # reuse mechsim's WT all-vs-all
    else:
        tm = ctx.tm(sa, sb)
    markers, missing = {}, []
    for name, raw, ax in (("mutation", mut, "mutation"), ("fate", fate, "fate"), ("structure", tm, "tm_score")):
        if raw is None:
            missing.append(name)
        else:
            markers[name] = {"raw": r4(raw), "pct": r4(ctx.pct(ax, raw))}
    wsum = sum(MECH_W[m] for m in markers)
    mech = r4(sum(MECH_W[m] * markers[m]["pct"] for m in markers) / wsum) if wsum else None
    pathway = row[f["pathway"]] if row else None
    tissue = row[f["tissue"]] if row else None
    ha, hb = fa["hpo"], fb["hpo"]
    union = sum(max(ha.get(t, 0), hb.get(t, 0)) for t in set(ha) | set(hb))
    inter = sum(min(ha[t], hb[t]) for t in set(ha) & set(hb))
    sym = r4(inter / union) if union else None
    return {"mechanistic": mech, "markers": markers, "missing": missing, "renormalised": bool(missing),
            "funding": r4(pathway), "string": r4(row[f["string_score"]]) if row else None,
            "tissue": r4(tissue), "symptoms": sym}


def key(score, gene):
    """Sort key for top-k lists: higher score first, then gene name (deterministic tie-break)."""
    return (-score, gene)


# ----------------------------------------------------------------------------------------------- build
def full_state(ctx, genes):
    feats = {g: features(ctx, g) for g in genes}
    scores = {}
    for i, a in enumerate(genes):
        for b in genes[i + 1:]:
            scores[pair_id(a, b)] = pair_scores(ctx, feats[a], feats[b])
    topk = {}
    for a in genes:
        topk[a] = {}
        for cat in CATEGORIES:
            cand = [key(scores[pair_id(a, b)][cat], b) for b in genes if b != a
                    and scores[pair_id(a, b)][cat] is not None]
            topk[a][cat] = [list(x) for x in sorted(cand)[:K]]
    clusters = cluster_full(genes, scores)
    return {"genes": list(genes), "features": feats, "scores": scores, "topk": topk, "clusters": clusters}


def pair_id(a, b):
    return "|".join(sorted([a, b]))


def cluster_full(genes, scores):
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    n = len(genes)
    if n < 2:
        return [[g] for g in genes]
    d = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            s = scores[pair_id(genes[i], genes[j])]["mechanistic"]
            d[i, j] = d[j, i] = 1 - (s if s is not None else 0)
    lab = fcluster(linkage(squareform(d), "average"), t=1 - CLUSTER_MIN, criterion="distance")
    groups = defaultdict(list)
    for g, l in zip(genes, lab):
        groups[l].append(g)
    return sorted((sorted(v) for v in groups.values()), key=lambda c: (-len(c), c[0]))


def add_disease(ctx, state, gene):
    """Incremental: n new similarities, bisect into each stored top-k (O(n log k)), cluster by average linkage."""
    if gene in state["genes"]:
        raise SystemExit(f"{gene} is already in the rankings")
    if gene not in ctx.prof:
        raise SystemExit(f"{gene} has no mechsim profile; run pipeline/derive/mechsim.py with it first")
    fa = features(ctx, gene)
    state["features"][gene] = fa
    new = {}
    for b in state["genes"]:
        s = pair_scores(ctx, fa, state["features"][b])
        state["scores"][pair_id(gene, b)] = s
        new[b] = s
    state["topk"][gene] = {}
    for cat in CATEGORIES:
        cand = (key(s[cat], b) for b, s in new.items() if s[cat] is not None)
        state["topk"][gene][cat] = [list(x) for x in heapq.nsmallest(K, cand)]          # O(n log k)
        for b, s in new.items():                                                        # n x O(log k)
            if s[cat] is None:
                continue
            lst = [tuple(x) for x in state["topk"][b][cat]]
            item = key(s[cat], gene)
            if len(lst) < K or item < lst[-1]:
                bisect.insort(lst, item)
                state["topk"][b][cat] = [list(x) for x in lst[:K]]
    best, best_avg = None, -1.0
    for ci, members in enumerate(state["clusters"]):
        vals = [new[m]["mechanistic"] or 0 for m in members]
        avg = sum(vals) / len(vals)
        if avg >= CLUSTER_MIN and avg > best_avg:
            best, best_avg = ci, avg
    if best is None:
        state["clusters"].append([gene])
    else:
        state["clusters"][best] = sorted(state["clusters"][best] + [gene])
    state["clusters"] = sorted(state["clusters"], key=lambda c: (-len(c), c[0]))
    state["genes"] = sorted(state["genes"] + [gene])
    return state


# ----------------------------------------------------------------------------------------------- output
def funder_names(fs):
    return {x["funder"] for x in fs}


def explain(ctx, state, a):
    fa = state["features"][a]
    out = {"gene": a, "id": fa["id"], "label": fa["label"], "family": fa["family"],
           "structure_model": {k: v for k, v in fa["structure"].items() if k not in ("clinvar",)},
           "structure_clinvar": fa["structure"].get("clinvar"),
           "delivery": fa["delivery"], "dominant_fate": fa["dominant_fate"],
           "funders": sorted(funder_names(fa["funders"])), "best": {}, "top": {}}
    for cat in CATEGORIES:
        out["top"][cat] = [[g, -s] for s, g in state["topk"][a][cat]]
    own_f = funder_names(fa["funders"])

    def partner(cat):
        lst = state["topk"][a][cat]
        if not lst or -lst[0][0] <= 0:
            return None, None
        b = lst[0][1]
        return b, state["scores"][pair_id(a, b)]

    # mechanistic
    b, s = partner("mechanistic")
    if b:
        fb = state["features"][b]
        mk = dict(s["markers"])
        if "fate" in mk:
            mk["fate"] = {**mk["fate"], "a": fa["dominant_fate"], "b": fb["dominant_fate"]}
        if "structure" in mk:
            mk["structure"] = {**mk["structure"], "model_a": fa["structure"]["label"],
                               "model_b": fb["structure"]["label"]}
        parts = []
        if "fate" in mk and fa["dominant_fate"] and fb["dominant_fate"]:
            same = fa["dominant_fate"] == fb["dominant_fate"]
            parts.append(f"{'both mostly' if same else 'mostly'} {FATE_TEXT[fa['dominant_fate']]}"
                         + ("" if same else f" vs {FATE_TEXT[fb['dominant_fate']]}"))
        if "structure" in mk:
            t = mk["structure"]["raw"]
            parts.append(f"protein models {'share a fold' if t >= 0.5 else 'align partly' if t >= 0.3 else 'differ'}"
                         f" (TM-score {t:.2f})")
        if "mutation" in mk:
            parts.append(f"mutation-type spectrum more alike than {round(mk['mutation']['pct'] * 100)}% of pairs")
        out["best"]["mechanistic"] = {
            "partner": b, "partner_label": fb["label"], "score": s["mechanistic"], "markers": mk,
            "missing": s["missing"], "weights": MECH_W,
            "explanation": "; ".join(parts) + "." + (f" Not scored: {', '.join(s['missing'])} (weights renormalised)."
                                                     if s["missing"] else "")}
    # funding
    b, s = partner("funding")
    if b:
        fb = state["features"][b]
        shared = sorted(set(fa["pathways"]) & set(fb["pathways"]),
                        key=lambda p: (ctx.pathway_sets.get(p, {}).get("size", 1e9), p))
        # human (M) and mouse-ortholog (MM) MSigDB sets often carry the same name: show each name once
        seen, uniq = set(), []
        for p in shared:
            nm = ctx.pathway_sets.get(p, {}).get("name", p)
            if nm.lower() not in seen:
                seen.add(nm.lower())
                uniq.append((p, nm))
        names = [nm for _p, nm in uniq]
        missing_f = defaultdict(list)
        for x in fb["funders"]:
            if x["funder"] not in own_f:
                missing_f[x["funder"]].append({k: x.get(k) for k in ("id", "title", "url", "kind")})
        # funders reached through any of the k closest pathway partners, not just the first
        via = defaultdict(set)
        for _s, g in state["topk"][a]["funding"]:
            if -_s <= 0:
                continue
            for x in state["features"][g]["funders"]:
                if x["funder"] not in own_f:
                    via[x["funder"]].add(g)
        expl = (f"shares {len(shared)} canonical pathway{'s' if len(shared) != 1 else ''}"
                + (f" (e.g. {', '.join(names[:3])})" if names else "")
                + (f" and a STRING interaction (score {s['string']:.2f})" if s["string"] else "")
                + ". Whoever funds work on one is a plausible funder for the other (inferred).")
        out["best"]["funding"] = {
            "partner": b, "partner_label": fb["label"], "score": s["funding"], "string": s["string"],
            "shared_pathways": [{"id": p, "name": n} for p, n in uniq[:8]],
            "n_shared_pathways": len(shared),
            "partner_funders_missing": [{"funder": k, "records": v[:3], "n": len(v)}
                                        for k, v in sorted(missing_f.items())],
            "funders_via_pathway_partners": [{"funder": k, "via": sorted(v)}
                                             for k, v in sorted(via.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
            "explanation": expl}
    # tissue / delivery
    b, s = partner("tissue")
    if b:
        fb = state["features"][b]
        da, db = fa["delivery"], fb["delivery"]
        same = da["class"] == db["class"]
        expl = (f"symptoms point to {da['target_tissue'] or 'no single tissue'} vs {db['target_tissue'] or 'no single tissue'}"
                f"; both are {da['class']} delivery problems" if same else
                f"symptoms point to {da['target_tissue'] or 'no single tissue'} vs {db['target_tissue'] or 'no single tissue'}"
                f"; delivery differs ({da['class']} vs {db['class']})")
        expl += (". A delivery route built for one could carry over to the other (inferred)." if same else ".")
        out["best"]["tissue"] = {"partner": b, "partner_label": fb["label"], "score": s["tissue"],
                                 "same_delivery_class": same, "partner_delivery": db,
                                 "explanation": expl}
    # symptoms
    b, s = partner("symptoms")
    if b:
        fb = state["features"][b]
        shared = sorted((t for t in set(fa["hpo"]) & set(fb["hpo"]) if fa["hpo"][t] >= DISTINCTIVE_IC),
                        key=lambda t: (-fa["hpo"][t], t))
        terms = [{"id": t, "name": ctx.hpo_terms[t]["name"], "ic": round(fa["hpo"][t], 2)} for t in shared]
        n_all = len(set(fa["hpo"]) & set(fb["hpo"]))
        expl = (f"{n_all} shared HPO features, {len(terms)} of them distinctive (IC >= {DISTINCTIVE_IC:g}). "
                "Overlapping symptoms suggest that short-term symptom-relieving treatments used in one disease "
                f"may be worth raising for the other ({CLINICIAN}).")
        out["best"]["symptoms"] = {"partner": b, "partner_label": fb["label"], "score": s["symptoms"],
                                   "n_shared_terms": n_all, "shared_distinctive": terms[:10],
                                   "explanation": expl}
    for c in state["clusters"]:
        if a in c:
            out["cluster"] = {"members": c, "size": len(c)}
    return out


def write_outputs(ctx, state):
    diseases = {g: explain(ctx, state, g) for g in state["genes"]}
    n_mut = {g: v for g, v in ctx.mutants.items() if v.get("n_mutant_entities")}
    meta = {
        "generated": TODAY, "method": "pipeline/derive/research_recs.py (see its docstring); "
                                      "docs/agent-reports/research-recommendations.md",
        "status": "inferred", "k": K, "weights": MECH_W, "cluster_min": CLUSTER_MIN,
        "categories": {
            "mechanistic": "0.30 mutation type + 0.35 molecular consequence (protein fate) + 0.35 3D structure "
                           "accordance; each marker as a percentile among all mechsim pairs",
            "funding": "shared signalling / canonical pathways (+ STRING interaction): shared pathway, likely shared funders",
            "tissue": "symptom-tissue and expression similarity; decides the delivery route",
            "symptoms": "IC-weighted overlap of HPO features"},
        "structures": {
            "experimental_mutant_genes": sorted(g for g, v in ctx.mutants.items() if v.get("representative")),
            "genes_with_mutant_entities": {g: v["n_mutant_entities"] for g, v in sorted(n_mut.items())},
            "other_genes": "AlphaFold DB v4 WT model; " + NO_PREDICTOR},
        "not_advice": "Computed hypotheses for researchers and patient groups. Not medical advice; any treatment "
                      f"idea is {CLINICIAN}.",
        "clusters": state["clusters"]}
    write_json(OUT, {"meta": meta, "diseases": diseases}, compact=True)
    write_json(STATE, {k: state[k] for k in ("genes", "features", "scores", "topk", "clusters")}, compact=True)
    return diseases


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", metavar="GENE", help="slot one new disease into the stored rankings")
    ap.add_argument("--exclude", metavar="GENE", action="append", default=[],
                    help="full build without these genes (used by the --add test)")
    args = ap.parse_args(argv)
    ctx = Context()
    if args.add:
        state = read_json(STATE)
        state = add_disease(ctx, state, args.add)
        print(f"added {args.add}: {len(state['genes'])} diseases")
    else:
        genes = sorted(g for g in ctx.prof if g not in set(args.exclude))
        state = full_state(ctx, genes)
        print(f"full build: {len(genes)} diseases, {len(state['scores'])} pairs")
    diseases = write_outputs(ctx, state)
    for g in ("STXBP1", "SCN1A", "GAA", "HRAS"):
        if g in diseases:
            d = diseases[g]["best"]
            print(g, {c: (d[c]["partner"], d[c]["score"]) if c in d else None for c in CATEGORIES})
    print("clusters:", [c for c in state["clusters"] if len(c) > 1])


if __name__ == "__main__":
    sys.exit(main())
