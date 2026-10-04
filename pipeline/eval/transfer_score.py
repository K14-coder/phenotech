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
"""
from __future__ import annotations

import json
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


class TransferIndex:
    """Precomputed disease profiles. `classes` maps class id -> member therapy ids."""

    def __init__(self, graph, classes=EQUIVALENCE, exclude_levels=("hypothesis",), family=None):
        self.g = graph
        self.family = family or {}
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        ex = set(exclude_levels)
        self.edges = [e for e in graph["edges"] if e["evidence_level"] not in ex and e["type"] != "candidate_for"]
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


if __name__ == "__main__":
    import sys
    idx = TransferIndex(load_graph())
    t = sys.argv[1] if len(sys.argv) > 1 else "therapy:4-phenylbutyrate"
    for d, s, ex in idx.rank_candidates(t, top=8):
        print(f"{s:6.3f}  {d:22s} mech={[m['mechanism'] for m in ex['mechanisms']]} "
              f"clusters={ex['clusters']} near={ex['nearest_known_by_phenotype']}")
