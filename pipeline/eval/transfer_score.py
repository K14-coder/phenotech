"""Therapy -> disease transfer scoring over data/graph.json (stdlib only).

Reusable core of pipeline/eval/transfer_eval.py. Given a therapy (or a therapy class) and the
diseases it is already known for, score every disease in the graph as a candidate for that therapy.

Signals (all read from data/graph.json; hypothesis edges are never used):
  mechanism match  : the therapy's `targets` mechanisms that a disease reaches by
                       driven_by                                   (chain weight 1.0)
                       gene -causes-> D, vg -variant_in-> gene, vg -has_effect-> M  (0.8)
                       gene -causes-> D, gene -participates_in-> M                   (0.7)
                     each matched mechanism weighted by its IDF over the 45 diseases, so a generic
                     effect (loss of function, in most diseases) adds little and a specific process
                     (GABA reuptake, SNARE complex assembly, MAPK cascade) adds a lot.
  phenotype        : IC-weighted Jaccard of has_phenotype sets, max over the therapy's known diseases.
  cluster          : curated clusters (graph.clusters) that contain the candidate AND one of the
                     therapy's target mechanisms or known diseases, each weighted by cluster IDF.
                     Clusters that list a therapy as a member are excluded by default, because they
                     were curated from the therapy's own trial record (leakage).

Recommended score (`pheno+mech`, see docs/agent-reports/eval.md) = phenotype/max + mechanism/max, per
query. `combined` (adds the cluster term) was pre-declared as the default but scored the same within
noise in the leave-one-out benchmark, so the simpler score is recommended.
`explain()` returns the matched mechanisms, chains, clusters and nearest known disease so a UI can
show why a candidate ranks where it does.

MultiFeatureIndex (below) adds 11 biological feature similarities from data/derived/features/
(protein families/domains, GO, Reactome, compartment, HPA tissue, HPO organ systems, ClinVar mutation
spectrum, mechanism class, GO-based target match). `MultiFeatureIndex.rank_candidates(t, scorer="multi")`
or `rank_candidates_multi(t)`; `score_weighted(weights, ...)` for any weights; `feature_matrix()` for the
per-feature scores. Evaluated in pipeline/eval/feature_eval.py; the existing TransferIndex API is unchanged.
"""
from __future__ import annotations

import json
import os
import math
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
GRAPH = ROOT / "data" / "graph.json"

RECOMMENDED = "pheno+mech"
CHAIN_W = {"driven_by": 1.0, "variant_group": 0.8, "pathway": 0.7}
# the current rule, copied from pipeline/derive/hypotheses.py (CHAIN_WEIGHT)
HYP_CHAIN_W = {"driven_by": 1.0, "variant_group": 0.8, "pathway": 0.45, "cluster": 0.4}

# Same drug / same product under different node ids. The first three are copied from
# pipeline/derive/hypotheses.py EQUIVALENCE; the MEK1/2 class is added for evaluation because the four
# drugs share one molecular target (MEK1/2) and the transfer question is asked at class level.
EQUIVALENCE = {
    "class:aminopyridines": ["therapy:3-4-diaminopyridine", "therapy:amifampridine",
                             "therapy:aminopyridine-presynaptic-boost"],
    "class:aav-stxbp1": ["therapy:aav-stxbp1-gene-replacement", "therapy:cap-002"],
    "class:aav-slc6a1": ["therapy:aav-slc6a1-gene-replacement", "therapy:aav9-slc6a1"],
    "class:mek-inhibitors": ["therapy:trametinib", "therapy:selumetinib", "therapy:mirdametinib",
                             "therapy:binimetinib"],
}


def load_graph(path=GRAPH):
    return json.loads(pathlib.Path(path).read_text())


def _ai_proposed_ai_reviewed(e):
    by = str((e.get("review") or {}).get("by", ""))
    return (by.startswith("ai-review:") and (e.get("attrs") or {}).get("extraction") == "claude"
            and all(str(ev.get("extracted_by", "")).startswith("claude:") for ev in e.get("evidence", [])))


class TransferIndex:
    """Precomputed disease profiles. `classes` maps class id -> member therapy ids."""

    def __init__(self, graph, classes=EQUIVALENCE, exclude_levels=("hypothesis",), family=None, include_ai_reviewed=None):
        # AI-proposed, AI-reviewed links (claude_reviewed.json): off by default here (hypotheses.py and other
        # users stay on curated links); the published benchmark (transfer_eval.py) turns them on and labels it.
        if include_ai_reviewed is None:
            include_ai_reviewed = os.environ.get("EVAL_INCLUDE_AI_REVIEWED") == "1"
        self.g = graph
        self.family = family or {}
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        ex = set(exclude_levels)
        # Edges proposed by an independent AI reading and accepted only by an AI review (data/curated/claude_reviewed.json)
        # stay out of the benchmark until a person reviews them: AI-found, AI-reviewed links from the same literature
        # would otherwise raise the score on their own (top-5 0.73 -> 0.79 when included).
        self.edges = [e for e in graph["edges"] if e["evidence_level"] not in ex and e["type"] != "candidate_for"
                      and (include_ai_reviewed or not _ai_proposed_ai_reviewed(e))]
        self.n_ai_reviewed = sum(1 for e in graph["edges"] if _ai_proposed_ai_reviewed(e))
        self.include_ai_reviewed = include_ai_reviewed
        self.diseases = sorted(n for n, v in self.nodes.items() if v["type"] == "disease")
        N = len(self.diseases)
        by = defaultdict(list)
        for e in self.edges:
            by[e["type"]].append(e)

        # ---- therapy classes
        self.class_of = {}
        for cid, mem in classes.items():
            for m in mem:
                if m in self.nodes:
                    self.class_of[m] = cid
        for n, v in self.nodes.items():
            if v["type"] == "therapy":
                self.class_of.setdefault(n, n)
        self.members = defaultdict(list)
        for t, c in self.class_of.items():
            self.members[c].append(t)
        self.targets = defaultdict(set)
        for e in by["targets"]:
            self.targets[self.class_of[e["source"]]].add(e["target"])

        # ---- known therapy-disease pairs: developed_for, and study -tests-> therapy + study -studies-> disease
        self.known = defaultdict(lambda: defaultdict(set))   # class -> disease -> {provenance}
        for e in by["developed_for"]:
            self.known[self.class_of[e["source"]]][e["target"]].add("developed_for:" + e["id"])
        tests = defaultdict(set)
        for e in by["tests"]:
            tests[e["source"]].add(self.class_of[e["target"]])
        for e in by["studies"]:
            for c in tests.get(e["source"], ()):
                self.known[c][e["target"]].add("study:" + e["source"])

        # ---- disease -> mechanism profile with chains
        gene_of = {e["target"]: e["source"] for e in by["causes"]}
        vg_of_gene = defaultdict(list)
        for e in by["variant_in"]:
            vg_of_gene[e["target"]].append(e)
        eff = defaultdict(list)
        for e in by["has_effect"]:
            eff[e["source"]].append(e)
        part = defaultdict(list)
        for e in by["participates_in"]:
            part[e["source"]].append(e)
        self.chains = defaultdict(lambda: defaultdict(list))   # d -> m -> [(kind, [edge ids])]
        self.driven = defaultdict(set)
        for e in by["driven_by"]:
            self.chains[e["source"]][e["target"]].append(("driven_by", [e["id"]]))
            self.driven[e["source"]].add(e["target"])
        for d in self.diseases:
            gene = gene_of.get(d)
            if not gene:
                continue
            for pe in part.get(gene, ()):
                self.chains[d][pe["target"]].append(("pathway", [pe["id"]]))
            for vi in vg_of_gene.get(gene, ()):
                for he in eff.get(vi["source"], ()):
                    self.chains[d][he["target"]].append(("variant_group", [vi["id"], he["id"]]))
        self.prof = {d: {m: max(CHAIN_W[k] for k, _ in chs) for m, chs in self.chains[d].items()}
                     for d in self.diseases}
        df = defaultdict(int)
        for d in self.diseases:
            for m in self.prof[d]:
                df[m] += 1
        self.mech_df = dict(df)
        self.idf = {m: math.log((N + 1) / (df[m] + 1)) for m in df}

        # ---- phenotypes
        self.pheno = defaultdict(dict)
        for e in by["has_phenotype"]:
            p = self.nodes[e["target"]]
            self.pheno[e["source"]][e["target"]] = float(p.get("attrs", {}).get("ic") or 0.0)
        self._psim = {}

        # ---- curated clusters
        self.clusters = []
        for cl in graph.get("clusters", []):
            mem = set(cl["members"])
            ds = {m for m in mem if self.nodes.get(m, {}).get("type") == "disease"}
            has_t = any(self.nodes.get(m, {}).get("type") == "therapy" for m in mem)
            self.clusters.append({"id": cl["id"], "label": cl["label"], "basis": cl["basis"], "members": mem,
                                  "diseases": ds, "therapy_informed": has_t,
                                  "idf": math.log((N + 1) / (len(ds) + 1))})

    # ------------------------------------------------------------------ pairwise similarities
    def phen_sim(self, a, b):
        k = (a, b) if a < b else (b, a)
        if k not in self._psim:
            pa, pb = self.pheno.get(a, {}), self.pheno.get(b, {})
            inter = sum(pa[p] for p in pa.keys() & pb.keys())
            union = sum(pa.values()) + sum(pb.values()) - inter
            self._psim[k] = inter / union if union else 0.0
        return self._psim[k]

    def mech_sim(self, a, b):
        va = {m: w * self.idf[m] for m, w in self.prof[a].items()}
        vb = {m: w * self.idf[m] for m, w in self.prof[b].items()}
        num = sum(va[m] * vb[m] for m in va.keys() & vb.keys())
        den = math.sqrt(sum(x * x for x in va.values()) * sum(x * x for x in vb.values()))
        return num / den if den else 0.0

    # ------------------------------------------------------------------ component scores
    def s_phenotype(self, cls, context, d):
        return max((self.phen_sim(d, k) for k in context), default=0.0)

    def s_mechanism(self, cls, context, d):
        p = self.prof[d]
        return sum(p.get(m, 0.0) * self.idf.get(m, 0.0) for m in self.targets.get(cls, ()))

    def s_mech_similarity(self, cls, context, d):
        return max((self.mech_sim(d, k) for k in context), default=0.0)

    def matching_clusters(self, cls, context, d, include_therapy_informed=False):
        anchors = set(self.targets.get(cls, ())) | set(context)
        mem_t = set(self.members.get(cls, ()))
        out = []
        for cl in self.clusters:
            if d not in cl["diseases"]:
                continue
            if cl["therapy_informed"] and not include_therapy_informed:
                continue
            if (cl["members"] - {d}) & anchors or (include_therapy_informed and cl["members"] & mem_t):
                out.append(cl)
        return out

    def s_cluster(self, cls, context, d, include_therapy_informed=False):
        return sum(cl["idf"] for cl in self.matching_clusters(cls, context, d, include_therapy_informed))

    def s_mech_plus_cluster(self, cls, context, d, include_therapy_informed=False):
        return self.s_mechanism(cls, context, d) + self.s_cluster(cls, context, d, include_therapy_informed)

    def s_same_family(self, cls, context, d):
        """Baseline: how many of the therapy's known diseases are in the candidate's disease family."""
        f = self.family.get(d)
        return float(sum(1 for k in context if f and self.family.get(k) == f))

    def s_naive(self, cls, context, d):
        return 1.0 if self.targets.get(cls, set()) & self.driven[d] else 0.0

    def s_hypotheses_rule(self, cls, context, d, use_cluster_chain=True):
        """pipeline/derive/hypotheses.py: strongest chain kind from a target mechanism to the disease,
        plus the 'cluster' chain (a curated cluster that lists the therapy and the disease)."""
        best = 0.0
        for m in self.targets.get(cls, ()):
            for kind, _ in self.chains[d].get(m, ()):
                best = max(best, HYP_CHAIN_W[kind])
        if use_cluster_chain:
            mem_t = set(self.members.get(cls, ()))
            for cl in self.clusters:
                if d in cl["diseases"] and cl["members"] & mem_t:
                    best = max(best, HYP_CHAIN_W["cluster"])
        return best

    # ------------------------------------------------------------------ scorers over a candidate list
    def score(self, scorer, cls, context, candidates):
        context = set(context)
        if scorer == "random":
            return {d: 0.0 for d in candidates}
        if scorer in SIMPLE:
            f = getattr(self, SIMPLE[scorer][0])
            kw = SIMPLE[scorer][1]
            return {d: f(cls, context, d, **kw) for d in candidates}

        def norm(sc):
            mx = max(sc.values(), default=0.0)
            return {d: (v / mx if mx > 0 else 0.0) for d, v in sc.items()}

        ph = {d: self.s_phenotype(cls, context, d) for d in candidates}
        me = {d: self.s_mechanism(cls, context, d) for d in candidates}
        if scorer == "pheno+mech":
            a, b = norm(ph), norm(me)
            return {d: a[d] + b[d] for d in candidates}
        cl = {d: self.s_cluster(cls, context, d) for d in candidates}
        if scorer == "combined":
            a, b = norm(ph), norm({d: me[d] + cl[d] for d in candidates})
            return {d: a[d] + b[d] for d in candidates}
        raise KeyError(scorer)

    # ------------------------------------------------------------------ public API
    def known_diseases(self, cls):
        return set(self.known.get(cls, {}))

    def rank_candidates(self, therapy, known=None, scorer=RECOMMENDED, top=None):
        """Rank every disease not already known for `therapy` (a therapy id or class id).
        Returns [(disease, score, explanation)] best first; ties keep alphabetical order."""
        cls = self.class_of.get(therapy, therapy)
        known = self.known_diseases(cls) if known is None else set(known)
        cands = [d for d in self.diseases if d not in known]
        sc = self.score(scorer, cls, known, cands)
        ranked = sorted(cands, key=lambda d: (-sc[d], d))
        out = [(d, round(sc[d], 4), self.explain(cls, known, d)) for d in ranked]
        return out[:top] if top else out

    def explain(self, cls, known, d):
        mm = []
        for m in sorted(self.targets.get(cls, ())):
            chs = self.chains[d].get(m)
            if chs:
                kind, eids = max(chs, key=lambda c: CHAIN_W[c[0]])
                mm.append({"mechanism": m, "idf": round(self.idf[m], 2), "n_diseases": self.mech_df[m],
                           "chain": kind, "edges": eids})
        near = max(known, key=lambda k: self.phen_sim(d, k), default=None)
        return {"mechanisms": mm,
                "clusters": [c["id"] for c in self.matching_clusters(cls, known, d)],
                "nearest_known_by_phenotype": near,
                "phenotype_similarity": round(self.phen_sim(d, near), 3) if near else 0.0}


SIMPLE = {
    "phenotype": ("s_phenotype", {}),
    "mechanism": ("s_mechanism", {}),
    "mech-similarity": ("s_mech_similarity", {}),
    "naive-driven_by": ("s_naive", {}),
    "hypotheses-rule": ("s_hypotheses_rule", {}),
    "hypotheses-rule-no-cluster": ("s_hypotheses_rule", {"use_cluster_chain": False}),
    "cluster-only": ("s_cluster", {}),
    "same-family": ("s_same_family", {}),
    "mech+cluster": ("s_mech_plus_cluster", {}),
    "mech+cluster-leaky": ("s_mech_plus_cluster", {"include_therapy_informed": True}),
}


# ====================================================================== multi-feature scorer
FEATURES = ROOT / "data" / "derived" / "features" / "atlas_features.json"
# context features compare the candidate with the therapy's known diseases (max over them);
# therapy features compare the candidate with the therapy's own targets (usable with no known disease).
CONTEXT_FEATURES = ["symptoms", "phenotype_systems", "gene_family", "protein_domains", "go_process", "reactome",
                    "compartment", "tissue", "mutation_type", "molecular_consequence", "shared_gene"]
THERAPY_FEATURES = ["mechanism_target", "target_go"]
ALL_FEATURES = THERAPY_FEATURES + CONTEXT_FEATURES
FEATURE_DOC = {
    "symptoms": "IC-weighted Jaccard of curated HPO phenotypes (the old phenotype scorer)",
    "phenotype_systems": "cosine of IC-weighted HPO top-level organ-system profiles, system IDF over HPO diseases",
    "gene_family": "IDF-weighted cosine of PANTHER family + InterPro Family entries (gene-family membership)",
    "protein_domains": "IDF-weighted cosine of InterPro Domain/Repeat/Homologous-superfamily + Pfam (structure)",
    "go_process": "IDF-weighted cosine of UniProt GO biological-process terms, propagated over is_a/part_of",
    "reactome": "IDF-weighted cosine of Reactome pathways incl. ancestors (signalling / metabolic pathway)",
    "compartment": "IDF-weighted cosine of UniProt GO cellular-component terms, propagated",
    "tissue": "cosine of HPA enriched-tissue vectors, log1p(nTPM) x tissue IDF (0 for low-specificity genes)",
    "mutation_type": "1 - Jensen-Shannon divergence of ClinVar P/LP spectra (truncating/missense/inframe/splice/CNV)",
    "molecular_consequence": "IDF-weighted cosine of mechanism classes (LoF/HI/DN/GoF/destabilization + G2P consequence)",
    "shared_gene": "1 if the candidate's causal gene is a known disease's gene (degenerate here: one gene per disease)",
    "mechanism_target": "the old IDF-weighted therapy-target mechanism match over graph chains",
    "target_go": "therapy target mechanism's GO term found in the candidate gene's propagated UniProt GO, x GO IDF",
}
# Result of pipeline/eval/feature_eval.py (data/derived/eval_features.json): no tuned combination of the
# richer features beat the old best under nested leave-one-therapy-class-out CV (nested MRR 0.457-0.485 vs
# 0.491), so the default multi-feature weights ARE the old best (identical ranking to "pheno+mech").
# ANCHORED_WEIGHTS is the best-scoring alternative (old best + half-weight target_go and mutation_type);
# selected in 35/38 outer folds, nested MRR 0.485, in-sample 0.510. Use it only as a tie-breaker/explainer.
MULTI_WEIGHTS = {"symptoms": 1.0, "mechanism_target": 1.0}
ANCHORED_WEIGHTS = {"symptoms": 1.0, "mechanism_target": 1.0, "target_go": 0.5, "mutation_type": 0.5}


def _cos(a, b):
    num = sum(a[k] * b[k] for k in a.keys() & b.keys())
    den = math.sqrt(sum(x * x for x in a.values()) * sum(x * x for x in b.values()))
    return num / den if den else 0.0


class MultiFeatureIndex(TransferIndex):
    """TransferIndex plus biological feature similarities from data/derived/features/atlas_features.json
    (built by pipeline/eval/build_features.py). Scorer names: "multi" (MULTI_WEIGHTS), "feat:<name>" for one
    feature, or score_weighted(weights, ...) for any weight dict."""

    def __init__(self, graph, features_path=FEATURES, weights=None, **kw):
        super().__init__(graph, **kw)
        fx = json.loads(pathlib.Path(features_path).read_text())
        self.fx = fx["diseases"]
        self.fidf = fx["idf"]
        self.mech_go = fx.get("mechanism_go", {})
        self.weights = dict(weights or MULTI_WEIGHTS)
        N = len(self.diseases)
        mc_df = defaultdict(int)
        for d in self.diseases:
            for c in self.fx[d]["molecular_consequence"]:
                mc_df[c] += 1
        self.mc_idf = {c: math.log((N + 1) / (v + 1)) for c, v in mc_df.items()}
        self.vec = {}
        for d in self.diseases:
            p = self.fx[d]
            ti = self.fidf["tissue"]
            self.vec[d] = {
                "phenotype_systems": {s: w * self.fidf["phenotype_system"].get(s, 0) for s, w in p["phenotype_systems"].items()},
                "gene_family": {t: self.fidf["family"][t] for t in p["family_tokens"]},
                "protein_domains": {t: self.fidf["domain"][t] for t in p["domain_tokens"]},
                "go_process": {t: self.fidf["go_bp"][t] for t in p["go_bp"]},
                "reactome": {t: self.fidf["reactome"][t] for t in p["reactome"]},
                "compartment": {t: self.fidf["go_cc"][t] for t in p["go_cc"]},
                "tissue": {t: math.log1p(v) * ti.get(t, 0) for t, v in p["hpa_enriched_nTPM"].items()},
                "molecular_consequence": {c: w * self.mc_idf[c] for c, w in p["molecular_consequence"].items()},
            }
            self.vec[d]["_go_all"] = set(p["go_bp"]) | set(p["go_mf"]) | set(p["go_cc"])
        self._fsim = {}

    # ---------------------------------------------------------------- disease-disease feature similarity
    def feat_sim(self, f, a, b):
        if f == "symptoms":
            return self.phen_sim(a, b)
        if f == "shared_gene":
            return 1.0 if self.fx[a]["gene"] == self.fx[b]["gene"] else 0.0
        k = (f, a, b) if a < b else (f, b, a)
        if k in self._fsim:
            return self._fsim[k]
        if f == "mutation_type":
            pa, pb = self.fx[a]["clinvar_spectrum"], self.fx[b]["clinvar_spectrum"]
            if not pa or not pb:
                v = 0.0
            else:
                js = 0.0
                for s in pa:
                    m = (pa[s] + pb[s]) / 2
                    for x in (pa[s], pb[s]):
                        if x > 0:
                            js += 0.5 * x * math.log2(x / m)
                v = 1.0 - js
        else:
            v = _cos(self.vec[a][f], self.vec[b][f])
        self._fsim[k] = v
        return v

    def feature(self, f, cls, context, d):
        if f == "mechanism_target":
            return self.s_mechanism(cls, context, d)
        if f == "target_go":
            tot = 0.0
            for m in self.targets.get(cls, ()):
                mg = self.mech_go.get(m)
                if mg and mg["go"] in self.vec[d]["_go_all"]:
                    tot += mg["idf"]
            return tot
        return max((self.feat_sim(f, d, k) for k in context), default=0.0)

    def feature_matrix(self, cls, context, candidates, feats=ALL_FEATURES):
        """{feature: {disease: score normalised by the max over candidates}}"""
        context = set(context)
        out = {}
        for f in feats:
            raw = {d: self.feature(f, cls, context, d) for d in candidates}
            mx = max(raw.values(), default=0.0)
            out[f] = {d: (v / mx if mx > 0 else 0.0) for d, v in raw.items()}
        return out

    def score_weighted(self, weights, cls, context, candidates):
        fm = self.feature_matrix(cls, context, candidates, [f for f, w in weights.items() if w])
        return {d: sum(w * fm[f][d] for f, w in weights.items() if w) for d in candidates}

    def score(self, scorer, cls, context, candidates):
        if scorer == "multi":
            return self.score_weighted(self.weights, cls, context, candidates)
        if scorer.startswith("feat:"):
            return self.score_weighted({scorer[5:]: 1.0}, cls, context, candidates)
        return super().score(scorer, cls, context, candidates)

    def explain(self, cls, known, d):
        out = super().explain(cls, known, d)
        fm = {}
        for f, w in self.weights.items():
            if not w or f in THERAPY_FEATURES:
                continue
            near = max(known, key=lambda k: self.feat_sim(f, d, k), default=None)
            if near:
                fm[f] = {"nearest_known": near, "similarity": round(self.feat_sim(f, d, near), 3)}
        out["features"] = fm
        return out


def rank_candidates_multi(therapy, known=None, top=None, graph=None, weights=None):
    """Convenience wrapper: rank diseases for `therapy` with the tuned multi-feature scorer."""
    idx = MultiFeatureIndex(graph or load_graph(), weights=weights)
    return idx.rank_candidates(therapy, known=known, scorer="multi", top=top)


if __name__ == "__main__":
    import sys
    idx = TransferIndex(load_graph())
    t = sys.argv[1] if len(sys.argv) > 1 else "therapy:4-phenylbutyrate"
    for d, s, ex in idx.rank_candidates(t, top=8):
        print(f"{s:6.3f}  {d:22s} mech={[m['mechanism'] for m in ex['mechanisms']]} "
              f"clusters={ex['clusters']} near={ex['nearest_known_by_phenotype']}")


# ====================================================================== direction-aware matching
# Built by pipeline/ingest/direction_build.py; evaluated by pipeline/eval/direction_eval.py
# (data/derived/eval_direction.json, docs/agent-reports/eval.md "Direction-aware matching").
DIRECTION_DIR = ROOT / "data" / "derived" / "direction"


def direction_compat(drug_direction, drug_targets, disease_gene_directions):
    """+1 if the drug pushes a disease gene's function the right way (decrease + GoF, increase + LoF),
    -1 if the wrong way, 0 if unknown, unrelated, or both. disease_gene_directions: {gene: 'LoF'|'GoF'}."""
    if drug_direction not in ("increase", "decrease"):
        return 0
    pos = neg = 0
    for g, gd in disease_gene_directions.items():
        if g in drug_targets and gd in ("LoF", "GoF"):
            good = (drug_direction == "decrease") == (gd == "GoF")
            pos += good
            neg += not good
    return 1 if pos and not neg else -1 if neg and not pos else 0


class DirectionIndex(TransferIndex):
    """TransferIndex plus a direction-compatibility term. Disease directions come from the graph's
    driven_by / variant_group has_effect edges (gene_direction.json `atlas_graph`); therapy directions from
    drug_direction.json `curated` (modality + summary, ChEMBL by name as fallback).
    Scorer "pheno+mech+direction" = pheno+mech + bonus * match - penalty * mismatch (default 0, 0.5)."""

    def __init__(self, graph, direction_dir=DIRECTION_DIR, bonus=0.0, penalty=0.5, **kw):
        super().__init__(graph, **kw)
        gd = json.loads((pathlib.Path(direction_dir) / "gene_direction.json").read_text())
        dd = json.loads((pathlib.Path(direction_dir) / "drug_direction.json").read_text())
        self.dis_dir = {d: v["direction"] for d, v in gd["atlas_graph"].items()}
        self.ther_dir = dd["curated"]
        self.gene_of = {e["target"]: e["source"].replace("gene:", "") for e in self.edges if e["type"] == "causes"}
        self.bonus, self.penalty = bonus, penalty

    def disease_direction(self, d):
        return self.dis_dir.get(d)

    def class_direction(self, cls):
        ds, tg = set(), set()
        for t in self.members.get(cls, [cls]):
            v = self.ther_dir.get(t)
            if v and v["direction"]:
                ds.add(v["direction"])
                tg |= set(v["targets"])
        return (ds.pop() if len(ds) == 1 else None), tg

    def s_direction(self, cls, context, d):
        dr, tg = self.class_direction(cls)
        gene, gd = self.gene_of.get(d), self.dis_dir.get(d)
        if not gene or gd not in ("LoF", "GoF"):
            return 0
        return direction_compat(dr, tg, {gene: gd})

    def score_direction(self, cls, context, candidates, bonus=None, penalty=None):
        b = self.bonus if bonus is None else bonus
        p = self.penalty if penalty is None else penalty
        base = TransferIndex.score(self, "pheno+mech", cls, context, candidates)
        out = {}
        for d in candidates:
            c = self.s_direction(cls, context, d)
            out[d] = base[d] + b * max(c, 0) - p * max(-c, 0)
        return out

    def score(self, scorer, cls, context, candidates):
        if scorer == "pheno+mech+direction":
            return self.score_direction(cls, context, candidates)
        return super().score(scorer, cls, context, candidates)

    def explain(self, cls, known, d):
        out = super().explain(cls, known, d)
        dr, tg = self.class_direction(cls)
        out["direction"] = {"therapy": dr, "therapy_targets": sorted(tg), "disease": self.dis_dir.get(d),
                            "compat": self.s_direction(cls, known, d)}
        return out
