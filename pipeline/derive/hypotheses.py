"""Product 3: therapy-transfer hypotheses -> data/curated/hypotheses.json (a SCHEMA fragment)
            plus assay/model transfer and near-misses -> data/derived/opportunities.json

Run:  python3 pipeline/derive/hypotheses.py   (after fetch_literature.py)

Search (pure graph analytics over data/graph.json):
  therapy T --targets--> mechanism M, and disease D is linked to M by one of
    chain "driven_by"      : disease:D --driven_by--> M                                  (strongest)
    chain "variant_group"  : gene:G --causes--> D, vg --variant_in--> G, vg --has_effect--> M
    chain "pathway"        : gene:G --causes--> D, gene:G --participates_in--> M         (weakest)
  and there is NO developed_for T->D and no study that both tests T and studies D.
  The pathway chain is included because no driven_by edge in this graph points at a GO process, so
  without it every process-targeting drug (the aminopyridines, cholinesterase inhibitors) would be
  invisible. It is scored lowest and named as the weakest link in the explanation.

Two filters stop nonsense:
  * product transferability: a gene-specific product (AAV vector, gene-targeted ASO, a chaperone
    designed against one protein's structure) cannot be handed to another gene. Those become
    "approach transfer" entries in opportunities.json, not candidate_for edges.
  * therapy equivalence: amifampridine, 3,4-DAP and the aminopyridine class are the same drug class,
    and the AAV products have duplicate nodes. "Already addressed" is tested over the whole class,
    so the amifampridine CMS trial (which lists SNAP25B deficiency) correctly kills the
    3,4-DAP -> SNAP25 "gap". Rejected candidates are kept in opportunities.json with the reason.
"""
from __future__ import annotations

import importlib.util
import re
from collections import defaultdict

from dcommon import CURATED, DERIVED, ROOT, TODAY, Graph, pub_evidence, read_json, write_json

MAX_HYPOTHESES = 10      # across all four families
PER_CLASS = 2            # no single therapy class may fill the list
PER_DISEASE = 2          # ... and no single disease
FAILED_CONF = 0.5        # a therapy whose every developed_for edge is contested below this failed where it was tried
MAX_RANK = 5             # a candidate must rank in the top 5 of its therapy's ranking
LEAD_DEPTH = 8           # how deep each therapy's ranking is read for leads in opportunities.json
RANK_CONF = {1: 0.2, 2: 0.17, 3: 0.15, 4: 0.13, 5: 0.12}
# "specific mechanism" = not a generic effect and reached by at most MAX_SPECIFIC_DF of the 45 diseases
GENERIC_MECH = {"mech:loss-of-function", "mech:haploinsufficiency", "mech:gain-of-function",
                "mech:dominant-negative", "mech:lysosomal-storage"}
MAX_SPECIFIC_DF = 10
NOT_TRANSFERABLE_MODALITIES = {"gene_replacement", "aso", "gene_editing"}
PROTEIN_SPECIFIC = re.compile(r"enzyme replacement|\balfa\b|pharmacological chaperone|structure-based", re.I)
CHAIN_WEIGHT = {"driven_by": 1.0, "variant_group": 0.8, "pathway": 0.45, "cluster": 0.4}
CHAIN_CONF = {"driven_by": 0.22, "variant_group": 0.18, "pathway": 0.14, "cluster": 0.12}

# Same drug / same product under different node ids. "Already developed for" and "already tested in"
# are evaluated over the whole class.
EQUIVALENCE = [
    {"id": "class:aminopyridines", "label": "Aminopyridine potassium-channel blockers (3,4-DAP / amifampridine / 4-AP)",
     "members": ["therapy:3-4-diaminopyridine", "therapy:amifampridine", "therapy:aminopyridine-presynaptic-boost"],
     "why": "3,4-diaminopyridine and amifampridine phosphate are the same active molecule, and the atlas's "
            "'aminopyridine presynaptic boost' node is the same class including 4-aminopyridine."},
    {"id": "class:aav-stxbp1", "label": "AAV STXBP1 gene supplementation (incl. CAP-002)",
     "members": ["therapy:aav-stxbp1-gene-replacement", "therapy:cap-002"],
     "why": "CAP-002 is the clinical product of the AAV STXBP1 supplementation approach."},
    {"id": "class:aav-slc6a1", "label": "AAV9 SLC6A1 gene replacement",
     "members": ["therapy:aav-slc6a1-gene-replacement", "therapy:aav9-slc6a1"],
     "why": "Two nodes for the same intrathecal AAV9.SLC6A1 product (NCT07173153)."},
]
# A product is transferable between genes only if it is not built against one gene or one protein.
TRANSFERABLE_MODALITIES = {"repurposed_drug", "chaperone"}
NOT_TRANSFERABLE_REASON = {
    "gene_replacement": "an AAV vector carries one gene's cDNA, so the product cannot treat another gene; "
                        "only the approach transfers",
    "aso": "an oligonucleotide is designed against one gene's sequence; only the approach transfers",
    "gene_editing": "an editor is designed per variant; only the approach transfers",
    "small_molecule": "designed against this protein's structure, so the molecule does not transfer to "
                      "another protein; only the approach transfers",
}

# Curated per-candidate detail. Keys are (therapy class or therapy id, disease id).
DETAIL = {
    ("class:4-pba", "disease:VAMP2"): {
        "title": "4-phenylbutyrate for VAMP2-related disorders",
        "caveats": [
            ("variant-class mismatch", "Only 7 of 35 pathogenic VAMP2 records in ClinVar are missense; a chaperone "
                                       "has nothing to stabilise in a truncating or whole-gene-deletion case.", []),
            ("evidence only from model systems", "The VAMP2 'stability' finding is a biophysical and neuronal "
                                                 "characterisation of nine variants, not a patient result.",
             [("PMID:41166419", "specific SNARE complex affinity, stability", "functional_study", True)]),
            ("mechanism may not be the same kind of instability",
             "Synaptobrevin-2 is natively unstructured outside the SNARE complex, so 'destabilization' here is not "
             "the folded-protein-degraded case that chemical chaperones were developed for.",
             [("PMID:29949059", "natively unstructured in the absence of lipids", "functional_study", True)]),
            ("counter-evidence on a chain edge", "4-phenylbutyrate's own mechanism is unresolved: in SLC6A1 models it "
                                                 "may act on wild-type trafficking rather than on the mutant protein, "
                                                 "and the generic chaperones need high concentrations.",
             [("PMID:35911425", "forward trafficking of the wildtype", "animal_model", False),
              ("PMID:33332765", "required high concentrations and potential toxicity", "functional_study", True)]),
            ("opposite-direction variants", "Some VAMP2 variants increase spontaneous release rather than reduce "
                                            "fusion; raising the amount of such a protein is not obviously good.",
             [("PMID:41166419", "disproportionate augmentation of spontaneous neurotransmitter release",
               "functional_study", False)]),
        ],
        "test": {
            "what_to_test": "In a VAMP2-variant neuronal model, measure variant protein level, SNARE-complex "
                            "formation and evoked/spontaneous release with and without 4-phenylbutyrate, variant by "
                            "variant - starting with the C-terminal SNARE-motif variants that were characterised as "
                            "destabilised, and including one variant that augments spontaneous release as a negative "
                            "control.",
            "existing_assay_or_model": ["asset:vamp2-mrc-ucl-yale-project", "asset:simons-searchlight",
                                        "PMID:41166419", "PMID:30266908"],
            "existing_assay_note": "The readouts already exist on both sides: the Munc18-1 chaperone work "
                                   "(PMID:30266908) established the rescue assay, and the VAMP2 variant panel "
                                   "(PMID:41166419) established the electrophysiology. The MRC UCL-Yale VAMP2 project "
                                   "is the group with the reagents; Simons Searchlight covers VAMP2 patients.",
            "what_result_would_change_the_plan": "If 4-PBA raises variant VAMP2 protein and restores evoked release "
                                                 "without increasing spontaneous release, VAMP2 becomes a candidate "
                                                 "arm on the existing phenylbutyrate protocol. If it only raises "
                                                 "wild-type protein, or if it increases spontaneous release, the "
                                                 "hypothesis dies and the STXBP1/SLC6A1 bridge stays a two-gene story.",
        },
        "weakest_link": "the VAMP2 destabilization edge itself: it is a contested edge resting on one 2025 paper, and "
                        "that paper's 'stability' defect is a SNARE-complex property, not the degradation-and-rescue "
                        "event that 4-PBA is known to act on.",
    },
    ("class:aminopyridines", "disease:UNC13A"): {
        "title": "Aminopyridines for the UNC13A presynaptic myasthenic presentation",
        "caveats": [
            ("tissue mismatch within one gene", "The release-boosting argument applies to the neuromuscular junction. "
                                                "Most UNC13A patients have a central neurodevelopmental syndrome, "
                                                "where the same drug lowers the seizure threshold.",
             [("PMID:22703551", "narrow therapeutic range suggest the need to evaluate the seizure risk",
               "review", True)]),
            ("variant-class mismatch", "Three mechanisms coexist in UNC13A, including gain of function; a drug that "
                                       "increases release is the wrong direction for the gain-of-function class.",
             [("PMID:41125872", "three mechanisms of pathogenicity", "functional_study", True)]),
            ("evidence only from model systems", "The strongest UNC13A release-deficit evidence is one patient's "
                                                 "in vitro microelectrode study plus worm and mouse neuron assays.",
             [("PMID:27648472", "Neuromuscular transmission was severely compromised by marked depletion",
               "case_report", True)]),
            ("chain weakness", "UNC13A is linked to vesicle priming in the graph, not to Ca2+-triggered exocytosis "
                               "that the aminopyridines target, so the mechanism match is one step looser than for "
                               "SNAP25 or SYT2.", []),
        ],
        "test": {
            "what_to_test": "In a patient with biallelic truncating UNC13A and fatigable weakness, repetitive nerve "
                            "stimulation before and after a single supervised 3,4-DAP dose, with the quantal content "
                            "measured if a muscle biopsy is available; and in parallel the same readout in an "
                            "UNC13A-null neuromuscular model.",
            "existing_assay_or_model": ["asset:cmdir-congenital-muscle-disease-registry", "study:NCT02562066",
                                        "PMID:27648472"],
            "existing_assay_note": "CMDIR lists UNC13A in its gene list, so the patients are findable; NCT02562066 is "
                                   "the completed amifampridine CMS protocol whose design (MFM score plus up-titration) "
                                   "could be reused. PMID:27648472 is the microelectrode protocol.",
            "what_result_would_change_the_plan": "Post-tetanic facilitation plus clinical improvement would make "
                                                 "UNC13A a candidate addition to the CMS eligibility list. No "
                                                 "facilitation, or any seizure worsening, ends it.",
        },
        "weakest_link": "the pathway chain: UNC13A reaches the aminopyridines only through 'the gene participates in "
                        "vesicle priming', which is a statement about the protein, not about the direction the drug "
                        "should push a particular patient's synapse.",
    },
    ("class:aminopyridines", "disease:STX1B"): {
        "title": "Aminopyridines for the loss-of-function end of STX1B epilepsy",
        "caveats": [
            ("opposite-effect variants in one gene", "STX1B contains variants that reduce the releasable pool AND "
                                                     "variants that increase fusogenicity, and patient iPSC neurons "
                                                     "show one variant doing both.",
             [("PMID:32572454", "The mutation STX1BV216E", "functional_study", True),
              ("PMID:42673765", "gain- and loss-of-function characteristics", "functional_study", True)]),
            ("counter-evidence on a chain edge", "The STX1B loss-of-function edge is contested in the graph, and one "
                                                 "cohort found loss-of-function variants in very differently affected "
                                                 "people.", []),
            ("seizure risk", "This is an epilepsy population and the drug class has a dose-related seizure risk.",
             [("PMID:22703551", "narrow therapeutic range suggest the need to evaluate the seizure risk",
               "review", True)]),
            ("tissue mismatch", "No neuromuscular presentation is recorded for STX1B, so the NMJ evidence behind this "
                                "drug class does not carry over.", []),
        ],
        "test": {
            "what_to_test": "Sort STX1B variants into release-down and release-up classes in human iPSC-derived "
                            "neurons (the network-excitability assay already published for G226R), then test "
                            "4-aminopyridine only on the release-down class.",
            "existing_assay_or_model": ["PMID:42673765", "PMID:32572454", "PMID:40181518"],
            "existing_assay_note": "The STX1B iPSC network assay exists (PMID:42673765) and the SNAP25 I67N study "
                                   "(PMID:40181518) is the template for using 4-AP as a readout in human neurons. "
                                   "No STX1B patient organisation or registry exists to find participants.",
            "what_result_would_change_the_plan": "If 4-AP rescues the release-down class and worsens the release-up "
                                                 "class, this becomes an argument for functional classification "
                                                 "before any drug, not for the drug.",
        },
        "weakest_link": "the direction of effect: the gene's own variants point both ways, so a gene-level "
                        "hypothesis is unsafe and only a variant-level one survives.",
    },
    ("class:aminopyridines", "disease:STXBP1"): {
        "title": "Aminopyridines for STXBP1 variants that reduce release",
        "caveats": [
            ("opposite-effect variants in one gene", "A homozygous STXBP1 variant (L446F) causes a gain-of-function "
                                                     "phenotype for release probability, the opposite of the group a "
                                                     "release-boosting drug would help.", []),
            ("counter-evidence on a chain edge", "Every STXBP1 mechanism edge in the graph is contested: "
                                                 "haploinsufficiency, destabilization and dominant-negative all carry "
                                                 "counter-evidence.", []),
            ("tissue mismatch", "No neuromuscular presentation is recorded for STXBP1, and the drug's clinical "
                                "evidence base is neuromuscular.", []),
            ("competing explanation", "Reduced release in STXBP1 comes with depleted interacting proteins "
                                      "(syntaxin-1, Doc2), so pushing the remaining machinery harder may not be "
                                      "equivalent to restoring it.",
             [("PMID:26280581", "lower the levels of Munc18-1 protein", "functional_study", True),
              ("PMID:38242640", "unstable in the absence of Munc18-1 and aggregate", "functional_study", True)]),
        ],
        "test": {
            "what_to_test": "In Stxbp1+/- neurons and in patient iPSC neurons, test whether 4-aminopyridine restores "
                            "evoked release, and whether it does so without increasing spontaneous release or "
                            "network hyperexcitability.",
            "existing_assay_or_model": ["asset:stxbp1-haploinsufficient-mice-xue-lab",
                                        "asset:stxbp1-floxed-null-mouse-innoser", "asset:stxbp1-s-comb-consortium",
                                        "PMID:40181518"],
            "existing_assay_note": "STXBP1 is the only disease in the slice with model assets and an outcome-measure "
                                   "consortium, so this is the cheapest of these experiments to run.",
            "what_result_would_change_the_plan": "Network hyperexcitability in the model would end it immediately. A "
                                                 "clean rescue would make a variant-stratified pilot arguable - but "
                                                 "only alongside the existing anti-seizure regimen, never instead.",
        },
        "weakest_link": "the pathway chain plus the contested mechanism: STXBP1 reaches this drug class only through "
                        "'the gene participates in Ca2+-triggered exocytosis', while the direction of its own "
                        "release defect is disputed in the literature.",
    },
    ("class:ache-inhibitors", "disease:SNAP25"): {
        "title": "Cholinesterase inhibitors for the SNAP25 myasthenic presentation",
        "caveats": [
            ("tissue mismatch for most patients", "SNAP25 mostly causes a central epileptic encephalopathy; the "
                                                  "cholinergic argument only applies to the myasthenic presentation "
                                                  "(CMS18).", []),
            ("mechanism mismatch", "Cholinesterase inhibitors prolong the action of each released packet; they do not "
                                   "fix a presynaptic release defect, and in presynaptic CMS they are usually "
                                   "combined with a release-boosting drug rather than used alone.",
             [("PMID:22911480", "the effect of these drugs differs depending on the underlying genetic defect",
               "review", True)]),
            ("variant-class mismatch", "One SNAP25 variant is strongly dominant-negative and another increases "
                                       "spontaneous release, so the gene label does not predict who could benefit.",
             [("PMID:41579375", "strongly dominant negative in the presence of wild-type", "functional_study", True),
              ("PMID:40181518", "increase in spontaneous release", "functional_study", False)]),
        ],
        "test": {
            "what_to_test": "In people with SNAP25 variants and any fatigable weakness, do repetitive nerve "
                            "stimulation first; only those with a decrement are candidates for a supervised "
                            "cholinesterase-inhibitor trial, with the SYT2 case series as the comparison.",
            "existing_assay_or_model": ["asset:cmdir-congenital-muscle-disease-registry", "asset:rare-x-data-collection",
                                        "study:NCT02562066", "PMID:32776697"],
            "existing_assay_note": "The SYT2 biallelic series (PMID:32776697) is the closest precedent: three patients "
                                   "improved on a cholinesterase inhibitor. CMDIR and the RARE-X SNAP25 programme can "
                                   "find the patients.",
            "what_result_would_change_the_plan": "A decrement on repetitive nerve stimulation in SNAP25-DEE patients "
                                                 "without a myasthenic diagnosis would turn this from a hypothesis "
                                                 "into a clinical screening question (gap:snap25-cms-vs-dee).",
        },
        "weakest_link": "the pathway chain and the phenotype split: the drug argument needs a neuromuscular junction, "
                        "and whether SNAP25-DEE patients have one has never been measured.",
    },
    ("class:ache-inhibitors", "disease:SYT1"): {
        "title": "Cholinesterase inhibitors for SYT1-related disorder",
        "caveats": [
            ("tissue mismatch", "SYT1-related disorder is central (hypotonia, movement disorder, developmental delay) "
                                "with no reported neuromuscular-junction failure, while this drug class acts at the "
                                "neuromuscular junction. SYT2, not SYT1, is the junction isoform.", []),
            ("mechanism mismatch", "SYT1 variants act as dominant negatives on the calcium sensor; prolonging "
                                   "acetylcholine in the cleft does not address that.",
             [("PMID:32362337", "potent, graded dominant-negative effects", "functional_study", True)]),
        ],
        "test": {
            "what_to_test": "Nothing in a patient. The first step is to ask whether SYT1 patients have any measurable "
                            "neuromuscular transmission defect at all; if they do not, this candidate should be "
                            "removed rather than tested.",
            "existing_assay_or_model": ["asset:bagos-natural-history-study", "asset:bagos-registry"],
            "existing_assay_note": "The Baker-Gordon natural history study is the place where such a measurement "
                                   "would already be collectable.",
            "what_result_would_change_the_plan": "No decrement on repetitive nerve stimulation in a SYT1 cohort "
                                                 "retires this hypothesis - which is a useful result, because it "
                                                 "also tells the atlas that the shared-pathway chain is too loose.",
        },
        "weakest_link": "the chain is purely pathway-level and the tissue is wrong; this is included as the example of "
                        "a computed candidate that a clinician should reject.",
    },
}
# Candidates the curator rejects after reading the chain: they pass the graph search but the
# mechanism argument does not survive a human read. They are reported in opportunities.json, with
# the reason, instead of being emitted as hypotheses.
REJECT_ON_REVIEW = {
    ("therapy:quinidine", "disease:KCNQ2"):
        "Direction is backwards: quinidine is a potassium-channel blocker tried in KCNT1 gain-of-function epilepsy, "
        "while KCNQ2 encephalopathy is driven by reduced Kv7 current (disease:KCNQ2|driven_by|mech:dominant-negative "
        "is the supported edge). The shared node 'potassium channel activity' does not encode direction.",
    ("therapy:kv7-openers", "disease:KCNT1"):
        "Direction is backwards: Kv7 openers increase potassium current and were studied in loss-of-function "
        "KCNQ2, while KCNT1-related epilepsy is driven by gain of function (disease:KCNT1|driven_by|"
        "mech:gain-of-function). The shared node 'potassium channel activity' does not encode direction.",
    ("class:ache-inhibitors", "disease:SYT1"):
        "Tissue is wrong and the chain is pathway-only: SYT2, not SYT1, is the neuromuscular-junction isoform, and "
        "no neuromuscular transmission defect is reported in SYT1-related disorder. Kept visible as the worked "
        "example of a computed candidate that a clinician should reject.",
}

# 4-PBA is a chaperone node without an equivalence class; give it a class id for DETAIL lookup
THERAPY_CLASS_ID = {"therapy:4-phenylbutyrate": "class:4-pba",
                    "therapy:acetylcholinesterase-inhibitor-cms": "class:ache-inhibitors",
                    "therapy:munc18-1-pharmacological-chaperone": "class:munc18-chaperone",
                    "therapy:unc13a-splice-switching-aso": "class:unc13a-aso"}
MODEL_ASSET_KINDS = {"animal_model", "cell_model", "assay", "outcome_measure", "biobank"}


def ev_pub(cites):
    return [pub_evidence(r, n, st, supports=sup) for r, n, st, sup in cites]


def main():
    g = Graph()
    cls_of, cls_meta = {}, {}
    for c in EQUIVALENCE:
        # a member may have been merged away upstream (duplicate therapy nodes are consolidated in
        # data/graph.json); keep the class, record which ids are no longer present
        c = dict(c, members_present=[m for m in c["members"] if m in g.nodes],
                 members_absent=[m for m in c["members"] if m not in g.nodes])
        cls_meta[c["id"]] = c
        for m in c["members"]:
            cls_of[m] = c["id"]
    for t, cid in THERAPY_CLASS_ID.items():
        cls_of.setdefault(t, cid)

    def klass(t):
        return cls_of.get(t, t)

    def members(cid):
        return cls_meta.get(cid, {}).get("members", [t for t in g.nodes if klass(t) == cid])

    # ---- disease -> mechanism chains
    chains = defaultdict(list)   # (disease, mech) -> [{"kind":..., "edges":[ids]}]
    causes = {e["target"]: e for e in g.edges_of("causes")}
    for e in g.edges_of("driven_by"):
        chains[(e["source"], e["target"])].append({"kind": "driven_by", "edges": [e["id"]]})
    for d, ce in causes.items():
        gene = ce["source"]
        for pe in g.edges_of("participates_in", source=gene):
            chains[(d, pe["target"])].append({"kind": "pathway", "edges": [ce["id"], pe["id"]]})
        for vi in g.edges_of("variant_in", target=gene):
            for he in g.edges_of("has_effect", source=vi["source"]):
                chains[(d, he["target"])].append({"kind": "variant_group",
                                                  "edges": [ce["id"], vi["id"], he["id"]]})

    # ---- already addressed, over the equivalence class
    developed = defaultdict(set)   # class -> {disease}
    for e in g.edges_of("developed_for"):
        developed[klass(e["source"])].add(e["target"])
    tested_in = defaultdict(set)   # class -> {disease: [study ids]}
    study_tests = defaultdict(set)
    for e in g.edges_of("tests"):
        study_tests[e["source"]].add(klass(e["target"]))
    for s, classes in study_tests.items():
        for se in g.edges_of("studies", source=s):
            for c in classes:
                tested_in[c].add((se["target"], s))

    # ---- candidate search: the benchmark's best honest scorer (docs/agent-reports/eval.md):
    # TransferIndex.rank_candidates(..., scorer="pheno+mech") from pipeline/eval/transfer_score.py.
    # Known diseases (developed_for, or a study that tests the class and studies the disease) are
    # excluded by the scorer itself, over therapy classes. Gates below are filters, never rankers.
    spec = importlib.util.spec_from_file_location("transfer_score", ROOT / "pipeline" / "eval" / "transfer_score.py")
    ts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ts)
    tidx = ts.TransferIndex(ts.load_graph())
    family = {d: (g.nodes[d].get("attrs") or {}).get("family") or "snare"
              for d in g.nodes if g.nodes[d]["type"] == "disease"}

    def detail_key(cls):
        return THERAPY_CLASS_ID.get(cls, cls)

    def rep_of(cls):
        mem = sorted(tidx.members[cls], key=lambda m: (-len(g.edges_of("developed_for", source=m)), m))
        with_t = [m for m in mem if g.edges_of("targets", source=m)]
        return (with_t or mem)[0]

    def transferable(cls):
        for m in tidx.members[cls]:
            n_ = g.nodes.get(m, {})
            mod = (n_.get("attrs") or {}).get("modality")
            if mod in NOT_TRANSFERABLE_MODALITIES:
                return False, NOT_TRANSFERABLE_REASON.get(mod, "gene-specific product")
            if PROTEIN_SPECIFIC.search(n_.get("label", "")):
                return False, ("the product replaces or binds one specific protein (an enzyme, or a pharmacological "
                               "chaperone made for one protein), so only the approach transfers")
        return True, None

    def compact(cls, d, rank, n, score, ex):
        return {"therapy_class": cls, "therapy": rep_of(cls), "therapy_label": g.nodes[rep_of(cls)]["label"],
                "disease": d, "disease_label": g.nodes[d]["label"], "family": family.get(d),
                "transfer_rank": rank, "transfer_n_candidates": n, "transfer_score": score, "explain": ex}

    def failed_where_tried(cls):
        de = [e for m_ in tidx.members[cls] for e in g.edges_of("developed_for", source=m_)]
        return bool(de) and all(e["status"] == "contested" and e["confidence"] < FAILED_CONF for e in de), \
            [e["id"] for e in de]

    candidates, rejected, approach_transfer, reviewed_out = [], [], [], []
    look_alike, generic_only, failed = [], [], []
    for cls in sorted(tidx.targets):
        for d, prov in sorted(tidx.known.get(cls, {}).items()):
            rejected.append({"therapy_class": cls, "disease": d, "reason": "already developed for, or already "
                             "tested in, this disease (over the therapy class)", "provenance": sorted(prov)})
        ranked = tidx.rank_candidates(cls, scorer="pheno+mech")
        n = len(ranked)
        ok, why_not = transferable(cls)
        fail, fail_edges = failed_where_tried(cls)
        for rank, (d, score, ex) in enumerate(ranked, 1):
            if score <= 0 or rank > LEAD_DEPTH:
                continue
            rec = compact(cls, d, rank, n, score, ex)
            if not ex["mechanisms"]:
                look_alike.append(dict(rec, reason="symptom similarity only: no target mechanism of this therapy is "
                                                   "reached by the disease, so no candidate_for edge"))
                continue
            if not ok:
                approach_transfer.append(dict(rec, reason=why_not))
                continue
            specific = [m for m in ex["mechanisms"]
                        if m["mechanism"] not in GENERIC_MECH and m["n_diseases"] <= MAX_SPECIFIC_DF]
            if not specific:
                generic_only.append(dict(rec, reason="only a generic mechanism links them ("
                                         + ", ".join(f"{m['mechanism']} in {m['n_diseases']} diseases"
                                                     for m in ex["mechanisms"]) + ")"))
                continue
            if fail:
                failed.append(dict(rec, reason="the therapy failed in the disease it was tried in (every developed_for "
                                               f"edge contested, confidence < {FAILED_CONF})", edges=fail_edges))
                continue
            if (detail_key(cls), d) in REJECT_ON_REVIEW:
                reviewed_out.append(dict(rec, review_rejection=REJECT_ON_REVIEW[(detail_key(cls), d)],
                                         curated_detail=DETAIL.get((detail_key(cls), d))))
                continue
            candidates.append(dict(rec, specific=specific))
    # quality first: best rank within its therapy, then score; at most PER_CLASS per therapy, MAX overall
    candidates.sort(key=lambda c: (c["transfer_rank"], -c["transfer_score"], c["disease"]))
    scored, per_class, per_dis, undetailed = [], defaultdict(int), defaultdict(int), []
    for c in candidates:
        if len(scored) < MAX_HYPOTHESES and per_class[c["therapy_class"]] < PER_CLASS \
                and per_dis[c["disease"]] < PER_DISEASE and c["transfer_rank"] <= MAX_RANK:
            scored.append(c)
            per_class[c["therapy_class"]] += 1
            per_dis[c["disease"]] += 1
        else:
            undetailed.append(c)

    # ---- emit candidate_for edges
    assets_by_disease = defaultdict(list)
    for e in g.edges_of("covers"):
        a = g.nodes.get(e["source"], {})
        if (a.get("attrs") or {}).get("kind") in MODEL_ASSET_KINDS:
            assets_by_disease[e["target"]].append(e["source"])
    edges = []
    for c in scored:
        t, d, cls, ex = c["therapy"], c["disease"], c["therapy_class"], c["explain"]
        det = DETAIL.get((detail_key(cls), d), {})
        mech_ids = [m["mechanism"] for m in c["specific"]]
        tgt_edges = [e["id"] for m_ in tidx.members[cls] for e in g.edges_of("targets", source=m_)
                     if e["target"] in mech_ids]
        chain_edges = list(dict.fromkeys(tgt_edges + [eid for m in c["specific"] for eid in m["edges"]]))
        chain_edges = [x for x in chain_edges if x in g.edges]
        contested = [x for x in chain_edges if g.edges[x]["status"] == "contested"]
        weakest_edge = min(chain_edges, key=lambda x: g.edges[x]["confidence"])
        we = g.edges[weakest_edge]
        auto_weak = (f"the {we['type']} edge {weakest_edge} (confidence {we['confidence']}"
                     + (f", contested with {len(we.get('counter_evidence') or [])} contradicting items" if we["status"] == "contested" else "")
                     + ")")
        if ex["phenotype_similarity"] < 0.05:
            auto_weak += (f"; and the symptoms barely overlap with the closest known disease "
                          f"({ex['nearest_known_by_phenotype']}, similarity {ex['phenotype_similarity']})")
        weakest = det.get("weakest_link", auto_weak)
        mech_txt = "; ".join(f"{g.nodes[m['mechanism']]['label']} (reached by {m['n_diseases']} of "
                             f"{len(tidx.diseases)} diseases, via {m['chain'].replace('_', ' ')})" for m in c["specific"])
        evidence = [{"source": "Atlas", "ref": eid, "url": f"/path?from={d}&to={t}",
                     "title": g.edges[eid].get("explanation", eid)[:300], "kind": "computed",
                     "extracted_by": "computed", "retrieved": TODAY} for eid in chain_edges]
        caveat_ev, caveats = [], []
        for lab, txt, cites in det.get("caveats", []):
            caveats.append({"kind": lab, "text": txt})
            caveat_ev += ev_pub(cites)
        if not det:
            if contested:
                caveats.append({"kind": "counter-evidence on a chain edge",
                                "text": "Contested edges on the chain: " + ", ".join(contested) + "."})
            if max(m["n_diseases"] for m in c["specific"]) >= 8:
                caveats.append({"kind": "family-level mechanism",
                                "text": "The shared mechanism is reached by "
                                        f"{max(m['n_diseases'] for m in c['specific'])} diseases, so it does not single "
                                        "out this pair; it says the approach is plausible, not that this disease responds."})
            if ex["phenotype_similarity"] < 0.05:
                caveats.append({"kind": "phenotype mismatch",
                                "text": f"Symptom overlap with the closest known disease is minimal "
                                        f"(similarity {ex['phenotype_similarity']})."})
            caveats.append({"kind": "untested", "text": "No study, case report or model result in the graph tests "
                                                        "this therapy class in this disease."})
        seen, uniq = set(), []
        for e_ in caveat_ev:
            if (e_["ref"], e_["quote"]) not in seen:
                seen.add((e_["ref"], e_["quote"]))
                uniq.append(e_)
        known = sorted(tidx.known_diseases(cls))
        test = det.get("test") or {
            "what_to_test": (f"In a {g.nodes[d]['label']} model, measure the readout of "
                             f"{', '.join(g.nodes[m]['label'] for m in mech_ids)} with and without {c['therapy_label']}, "
                             "using the same readout that supported it in its known disease(s)."),
            "existing_assay_or_model": sorted(set(assets_by_disease.get(d, [])) |
                                              {a for k in known for a in assets_by_disease.get(k, [])})[:8],
            "existing_assay_note": "Model/assay assets in the graph for this disease or for the therapy's known diseases.",
            "what_result_would_change_the_plan": ("Rescue of the readout in the model would justify a carefully "
                                                  "monitored n-of-1 or case-series design; no effect retires the link."),
        }
        rank = c["transfer_rank"]
        conf = RANK_CONF.get(rank, 0.10) - 0.02 * len(contested)
        edges.append({
            "id": f"{t}|candidate_for|{d}", "source": t, "target": d, "type": "candidate_for",
            "label": "hypothesis: could be worth testing",
            "explanation": (f"HYPOTHESIS, not a finding. Ranked {rank} of {c['transfer_n_candidates']} candidate diseases "
                            f"for {c['therapy_label']} by the benchmark's best scorer (phenotype + mechanism). Shared "
                            f"mechanism: {mech_txt}. Symptoms closest to {g.nodes[ex['nearest_known_by_phenotype']]['label'] if ex['nearest_known_by_phenotype'] else 'none'}"
                            f" (similarity {ex['phenotype_similarity']}). The graph has no developed_for edge and no "
                            f"study testing this therapy class here. The weakest link is {weakest}. Nobody has tested this."),
            "evidence_level": "hypothesis", "status": "unverified",
            "confidence": round(max(0.05, min(0.25, conf)), 2),
            "evidence": evidence,
            **({"counter_evidence": [e_ for e_ in uniq if e_.get("supports") is False]}
               if any(e_.get("supports") is False for e_ in uniq) else {}),
            "attrs": {
                "title": det.get("title", f"{c['therapy_label'].split(' (')[0]} for {g.nodes[d]['label']}"),
                "family": family.get(d), "generated_by": "pipeline/derive/hypotheses.py",
                "transfer_score": c["transfer_score"], "transfer_rank": rank,
                "transfer_n_candidates": c["transfer_n_candidates"], "scorer": "pheno+mech (pipeline/eval/transfer_score.py)",
                "transfer_explanation": ex, "therapy_class": cls, "known_diseases_of_class": known,
                "chain": {"mechanisms": mech_ids, "edges": chain_edges, "contested_edges": contested},
                "weakest_link": weakest,
                "caveats": caveats, "caveat_citations": uniq, "test": test,
            },
        })

    frag = {
        "nodes": [],
        "edges": edges,
        "clusters": [],
        "gaps": [{
            "id": "gap:therapy-transfer-untested",
            "about": "computed candidate_for edges",
            "question": "Has anyone tested the therapy classes the atlas flags as mechanism-matched but undeveloped "
                        "for these diseases?",
            "what_is_missing": [f"{e['attrs']['title']} ({e['source']} -> {e['target']}): no trial, no model result, "
                                f"no case report" for e in edges],
            "searched": ["data/graph.json developed_for / tests / studies edges over therapy classes as defined in "
                         "pipeline/eval/transfer_score.py EQUIVALENCE (aminopyridines, AAV-STXBP1, AAV-SLC6A1, "
                         "MEK1/2 inhibitors)",
                         "ClinicalTrials.gov records stored under data/raw/community/ctgov and data/raw/derive/ctgov"],
            "how_to_find_out": "Each edge carries attrs.test with the experiment, the existing assay or model to "
                               "borrow, and the result that would kill it. Start with the one whose chain has no "
                               "contested edge.",
        }],
        "meta_note": ("DRAFT HYPOTHESES, computed by pipeline/derive/hypotheses.py. Every edge is "
                      "evidence_level=hypothesis, status=unverified, confidence<=0.25, and must be drawn as a dashed "
                      "line labelled 'hypothesis'. None of these is a treatment suggestion for any person."),
    }
    size_h = write_json(CURATED / "hypotheses.json", frag)

    # ---- assay / model transfer: diseases sharing an effect mechanism where one has a model asset
    assets = {nid: n for nid, n in g.nodes.items() if n["type"] == "asset"}
    model_of = defaultdict(list)
    for e in g.edges_of("covers"):
        a = assets.get(e["source"])
        if a and a.get("attrs", {}).get("kind") in MODEL_ASSET_KINDS:
            model_of[e["target"]].append({"asset": e["source"], "label": a["label"],
                                          "kind": a["attrs"]["kind"], "edge_id": e["id"]})
    effect_mechs = [m for m, n in g.nodes.items()
                    if n["type"] == "mechanism" and n.get("attrs", {}).get("kind") == "effect"]
    transfer = []
    for m in effect_mechs:
        linked = sorted({d for (d, mm) in chains if mm == m and g.nodes[d]["type"] == "disease"})
        haves = [d for d in linked if model_of.get(d)]
        lacks = [d for d in linked if not model_of.get(d)]
        for h in haves:
            for l in lacks:
                transfer.append({
                    "shared_mechanism": m, "shared_mechanism_label": g.nodes[m]["label"],
                    "has_model": h, "has_model_label": g.nodes[h]["label"], "assets": model_of[h],
                    "lacks_model": l, "lacks_model_label": g.nodes[l]["label"],
                    "chain_kinds": {h: max((c["kind"] for c in chains[(h, m)]), key=lambda k: CHAIN_WEIGHT[k]),
                                    l: max((c["kind"] for c in chains[(l, m)]), key=lambda k: CHAIN_WEIGHT[k])},
                    "chain_edges": {h: chains[(h, m)][0]["edges"], l: chains[(l, m)][0]["edges"]},
                    "gap_ids": [gp["id"] for gp in g.gaps if gp["id"] == f"gap:{l.split(':')[1]}:models"],
                })
    strong = [t for t in transfer if t["chain_kinds"][t["has_model"]] == "driven_by"
              and t["chain_kinds"][t["lacks_model"]] == "driven_by"]

    opportunities = {
        "about": ("Node-free companion to data/curated/hypotheses.json: assay and model transfer opportunities, the "
                  "candidates the search REJECTED and why, approach-level (not product-level) transfers, and "
                  "near-misses that one curated edge away would become candidates. Nothing here is a graph node or "
                  "edge, so it cannot be mistaken for a finding."),
        "meta": {"generated": TODAY, "code": "pipeline/derive/hypotheses.py",
                 "hypotheses_emitted": len(edges), "hypotheses_file": "data/curated/hypotheses.json",
                 "ranking": "TransferIndex.rank_candidates(scorer='pheno+mech') from pipeline/eval/transfer_score.py "
                            "(best honest scorer in docs/agent-reports/eval.md); the curated-cluster chain is no "
                            "longer used (clusters that list therapies leak the answer)",
                 "gates": ["already developed for / tested in (over the therapy class)",
                           "product transferability (no AAV, ASO, editing, enzyme replacement or one-protein chaperone "
                           "across genes)",
                           f"specific mechanism: at least one matched target mechanism that is not generic "
                           f"({', '.join(sorted(GENERIC_MECH))}) and is reached by <= {MAX_SPECIFIC_DF} diseases",
                           "curator review rejection (REJECT_ON_REVIEW), e.g. channel drugs whose direction is backwards",
                           f"failed where tried: every developed_for edge contested below {FAILED_CONF}",
                           "symptom-only matches never become edges (look_alike_leads)"],
                 "selection": f"rank <= {MAX_RANK} within its therapy, at most {PER_CLASS} per therapy class and {PER_DISEASE} per "
                     f"disease, at most "
                              f"{MAX_HYPOTHESES} overall, sorted by rank then score",
                 "chain_kinds": {"driven_by": "disease -> mechanism edge (strongest)",
                                 "variant_group": "gene -> variant group -> effect mechanism",
                                 "pathway": "gene participates in the process (weakest: says nothing about direction)"}},
        "look_alike_leads": {
            "rule": "the disease ranks in a therapy's top 8 on symptom similarity, but reaches none of the therapy's "
                    "target mechanisms; a lead to read, never a candidate_for edge",
            "items": look_alike,
        },
        "failed_where_tried": {
            "rule": "the therapy's every developed_for edge is contested with confidence < "
                    f"{FAILED_CONF} (a documented failure in its own disease); transfer is not proposed",
            "items": failed,
        },
        "generic_mechanism_only": {
            "rule": "the only shared mechanism is generic (loss/gain of function, haploinsufficiency, dominant "
                    "negative, lysosomal storage) or reaches more than "
                    f"{MAX_SPECIFIC_DF} diseases",
            "items": generic_only,
        },
        "model_and_assay_transfer": {
            "rule": "two diseases are linked to the same EFFECT mechanism, one has a model/assay/biobank/"
                    "outcome-measure asset in the graph and the other has none",
            "n_pairs": len(transfer),
            "strongest_pairs_both_driven_by": strong,
            "all_pairs": transfer,
        },
        "computed_candidates_rejected_on_review": {
            "rule": "the chain passes the graph search but a human read of the mechanism rejects it; these are NOT "
                    "emitted as hypotheses",
            "items": reviewed_out,
        },
        "therapy_equivalence_classes": [{"id": k, "members": v} for k, v in ts.EQUIVALENCE.items()],
        "rejected_candidates": {
            "rule": "the therapy class is already developed for, or already tested in, this disease",
            "items": rejected,
        },
        "approach_transfer_not_product": {
            "rule": "the mechanism matches but the product is built against one gene or one protein, so only the "
                    "approach transfers; no candidate_for edge is emitted",
            "items": approach_transfer,
        },
        "ranked_candidates_without_a_slot": {
            "note": "these passed every gate but were not promoted (rank above "
                    f"{MAX_RANK}, or the per-therapy cap of {PER_CLASS}, or the overall cap of {MAX_HYPOTHESES})",
            "items": undetailed,
        },
        "near_misses_one_edge_away": [
            {"what": "4-phenylbutyrate for the STX1B InDel class",
             "why_not_a_candidate": "the graph has no has_effect edge from any STX1B variant group to "
                                    "mech:protein-destabilization, so no chain exists",
             "what_would_create_it": "curating the published finding that the STX1B K45/RMCIE,L46M InDel yields an "
                                     "unfolded protein as a has_effect edge to protein destabilization",
             "citation": ev_pub([("PMID:32572454", "unfolded protein unable to", "functional_study", True)])},
            {"what": "transcript upregulation (TANGO-style ASO or CRISPRa) for any haploinsufficient disease here",
             "why_not_a_candidate": "no therapy node of this modality exists in the graph, so the search cannot "
                                    "produce an edge; the modality screen covers it instead",
             "what_would_create_it": "a therapy node for a specific upregulation product with a targets edge to "
                                     "mech:haploinsufficiency",
             "citation": ev_pub([("PMID:32848094", "Targeted Augmentation of Nuclear Gene Output", "animal_model", True),
                                 ("PMID:40963013", "upregulation of the existing functional gene copy", "animal_model", True)])},
            {"what": "the UNC13A cryptic-exon ASO as an UNC13A upregulator",
             "why_not_a_candidate": "it is a gene-specific product and its developed_for edge already points at "
                                    "disease:UNC13A, so there is no transfer to compute",
             "what_would_create_it": "evidence that the TDP-43-dependent cryptic exon is used in Mendelian UNC13A "
                                     "patients at all",
             "citation": ev_pub([("PMID:38979232", "targeting the UNC13A cryptic exon robustly rescue",
                                  "functional_study", True)])},
        ],
    }
    size_o = write_json(DERIVED / "opportunities.json", opportunities)

    print(f"[hypotheses] {len(edges)} candidate_for edges ({size_h / 1024:.0f} KB); {len(rejected)} known pairs; "
          f"{len(approach_transfer)} approach-only; {len(generic_only)} generic-only; {len(look_alike)} look-alike leads; "
          f"{len(reviewed_out)} rejected on review; {len(failed)} failed-where-tried; {len(undetailed)} without a slot; "
          f"{len(transfer)} model-transfer pairs ({size_o / 1024:.0f} KB)")
    for e in edges:
        a = e["attrs"]
        print(f"  {e['confidence']:.2f} rank {a['transfer_rank']}/{a['transfer_n_candidates']} score {a['transfer_score']} "
              f"[{a['family']}] {e['source']} -> {e['target']} via {a['chain']['mechanisms']}")
        print(f"       weakest: {a['weakest_link'][:220]}")
    for r in reviewed_out:
        print(f"  REVIEW-REJECTED {r['therapy_class']} -> {r['disease']}")


if __name__ == "__main__":
    main()
