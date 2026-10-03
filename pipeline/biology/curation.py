"""Curated literature claims for the SNAREopathies slice.

EVIDENCE INTEGRITY DESIGN
A claim never stores a hand-typed quote. It stores a `needle`: a short, distinctive
substring of the sentence we want. `quote_for()` locates that needle inside the LOCALLY
STORED source text (data/raw/biology/pubmed/<PMID>.json, or the ClinicalTrials.gov v2
record) and returns the full sentence verbatim. A needle that is missing or ambiguous
raises, so a claim can never carry text that is not in the stored source.
pipeline/biology/verify_quotes.py then re-checks every emitted quote independently.

Run:  python3 pipeline/biology/curation.py        # print every claim with its resolved quote
"""
from __future__ import annotations

import json
import re
import unicodedata

from common import RAW

PM_DIR = RAW / "pubmed"
CT_DIR = RAW / "clinicaltrials"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"'))
    return " ".join(s.split())


def source_text(ref: str) -> tuple[str, dict]:
    """Full searchable text of a stored source, plus its metadata."""
    if ref.startswith("NCT"):
        rec = json.loads((CT_DIR / f"{ref}.json").read_text())
        ps = rec["protocolSection"]
        idm, st = ps["identificationModule"], ps["statusModule"]
        desc = ps.get("descriptionModule", {})
        txt = " ".join([idm.get("briefTitle", ""), idm.get("officialTitle", ""),
                        desc.get("briefSummary", ""), desc.get("detailedDescription", ""),
                        st.get("whyStopped", "")])
        meta = {"title": idm.get("briefTitle"), "status": st.get("overallStatus"),
                "why_stopped": st.get("whyStopped"),
                "year": int((st.get("startDateStruct", {}).get("date") or "0")[:4]) or None,
                "phases": ps.get("designModule", {}).get("phases"),
                "sponsor": ps["sponsorCollaboratorsModule"]["leadSponsor"]["name"],
                "url": f"https://clinicaltrials.gov/study/{ref}"}
        return txt, meta
    pmid = ref.replace("PMID:", "")
    rec = json.loads((PM_DIR / f"{pmid}.json").read_text())
    meta = {"title": rec["title"], "year": rec["year"], "journal": rec["journal"],
            "pub_types": rec["pub_types"], "doi": rec.get("doi"),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
    return rec["title"] + " " + rec["abstract"], meta


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(“\"])")


def quote_for(ref: str, needle: str) -> str:
    """Return the verbatim sentence(s) of `ref` containing `needle`."""
    txt, _ = source_text(ref)
    n_needle = norm(needle)
    sents = [s.strip() for s in _SENT.split(txt) if s.strip()]
    hits = [s for s in sents if n_needle in norm(s)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"needle ambiguous in {ref} ({len(hits)} sentences): {needle!r}")
    # needle may straddle a sentence break -> try adjacent pairs
    for i in range(len(sents) - 1):
        pair = sents[i] + " " + sents[i + 1]
        if n_needle in norm(pair):
            return pair
    raise ValueError(f"needle NOT FOUND in {ref}: {needle!r}")


def meta_for(ref: str) -> dict:
    return source_text(ref)[1]


# --------------------------------------------------------------------------------------
# Effect mechanisms (schema: mechanism nodes with attrs.kind == "effect")
# --------------------------------------------------------------------------------------
EFFECT_MECHANISMS = [
    ("haploinsufficiency", "Haploinsufficiency (one working copy is not enough)",
     "One of the two gene copies is lost or inactive, so the cell makes too little of a protein "
     "it needs. The remaining copy cannot cover the shortfall."),
    ("protein-destabilization", "Protein destabilization / misfolding",
     "The variant protein is made but is unstable or misfolds, so it is degraded, aggregates, or is "
     "retained inside the cell instead of reaching its working location. The usable protein level "
     "falls even though the gene copy is present."),
    ("dominant-negative", "Dominant-negative effect (the altered protein blocks the good one)",
     "The altered protein is still present and actively interferes with the normal protein or the "
     "machine it belongs to, so the damage is worse than simply having half the normal amount."),
    ("gain-of-function", "Gain of function (the protein does too much)",
     "The variant protein is overactive: in these disorders that usually means synaptic vesicles "
     "fuse too readily, or neurotransmitter is released when it should not be."),
    ("loss-of-function", "Loss of function",
     "The variant protein cannot do its normal job. Used where the evidence shows loss of activity "
     "without specifying whether the cause is reduced dose, instability or blocked function."),
]

# --------------------------------------------------------------------------------------
# disease -> effect-mechanism claims.  needle = distinctive substring of the sentence.
# --------------------------------------------------------------------------------------
# tuple: (gene, mech_slug, ref, needle, supports, study_type, note)
#   supports=True      -> the paper supports this gene/mechanism link
#   supports=False     -> the paper contradicts or limits THIS mechanism for this gene
#   supports="minority"-> the paper demonstrates THIS mechanism (so it supports this edge) while
#                         contradicting the gene's mainstream mechanism; build_biology.py also
#                         attaches it as counter-evidence on that gene's dominant mechanism edge.
DISEASE_MECHANISM_CLAIMS = [
    # ---------------- STXBP1
    ("STXBP1", "haploinsufficiency", "PMID:18469812",
     "haploinsufficiency of STXBP1 causes EIEE", True, "case_series",
     "The original 2008 discovery paper already proposed haploinsufficiency."),
    ("STXBP1", "haploinsufficiency", "PMID:26280581",
     "heterozygous STXBP1 mutations lower the levels of Munc18-1 protein", True, "functional_study",
     "Isogenic human neurons: one bad copy lowers Munc18-1 and syntaxin-1 and halves release."),
    ("STXBP1", "haploinsufficiency", "PMID:29538625",
     "impaired protein stability and STXBP1 haploinsufficiency explain", True, "animal_model",
     "Allelic series plus Stxbp1+/- mice: instability feeding into haploinsufficiency."),
    ("STXBP1", "protein-destabilization", "PMID:29538625",
     "All disease variants had severely decreased protein levels", True, "functional_study",
     "Seven disease variants, all with severely reduced protein levels."),
    ("STXBP1", "protein-destabilization", "PMID:30266908",
     "destabilization and aggregation of the mutant protein", True, "functional_study",
     "At least five missense variants destabilize and aggregate Munc18-1."),
    ("STXBP1", "protein-destabilization", "PMID:25284778",
     "renders the protein unstable at 37", True, "functional_study",
     "C180Y is temperature-sensitive: unstable at 37 C, rescued at a permissive temperature."),
    ("STXBP1", "protein-destabilization", "PMID:25284778",
     "polyubiquitination, which is highly increased by the mutation", True, "functional_study",
     "Names the degradation route: K48 polyubiquitination and proteasomal degradation."),
    ("STXBP1", "dominant-negative", "PMID:27597756",
     "form large polymers that coaggregate wild-type Munc18-1", True, "functional_study",
     "The aggregation evidence underpinning the dominant-negative reading."),
    ("STXBP1", "dominant-negative", "PMID:29538625",
     "no effect when overexpressed on a heterozygous background", False, "functional_study",
     "COUNTER: no measurable mutant effect on a wild-type-containing background."),
    ("STXBP1", "dominant-negative", "PMID:32643187",
     "both haploinsufficiency and dominant-negative mechanisms have been proposed", False, "review",
     "The field's own review states the mechanism is not settled."),
    ("STXBP1", "gain-of-function", "PMID:31855252",
     "homozygous L446F mutation causes a gain-of-function phenotype", "minority", "functional_study",
     "A recessive (homozygous) STXBP1 variant acts by gain of function, against the uniform loss-of-function model."),
    ("STXBP1", "haploinsufficiency", "PMID:38242640",
     "how haploinsufficiency alone can account for the significant heterogeneity", False, "functional_study",
     "COUNTER: haploinsufficiency alone does not explain patient heterogeneity (Doc2A/B co-depletion)."),
    # ---------------- SYT1
    ("SYT1", "dominant-negative", "PMID:25705886",
     "dominant negative SYT1 mutation highlight presynaptic mechanisms", True, "case_report",
     "First human SYT1 variant, already described as dominant negative."),
    ("SYT1", "dominant-negative", "PMID:32362337",
     "demonstrated potent, graded dominant-negative effects", True, "functional_study",
     "Three patient variants: potent, graded dominant-negative effects."),
    ("SYT1", "dominant-negative", "PMID:39481209",
     "share an underlying pathogenic mechanism", True, "functional_study",
     "Extends the graded dominant-negative mechanism to C2A-domain variants."),
    ("SYT1", "gain-of-function", "PMID:38321119",
     "distinct from what was previously found for other SYT1 disease variants", "minority", "functional_study",
     "COUNTER: P401L de-clamps spontaneous/asynchronous release instead of only reducing evoked release."),
    ("SYT1", "haploinsufficiency", "PMID:41438914",
     "preliminary data favoring a dominant-negative effect", "minority", "case_report",
     "COUNTER: a structural-variant case argues haploinsufficiency can also cause the disorder."),
    # ---------------- SNAP25
    ("SNAP25", "dominant-negative", "PMID:41579375",
     "I192N is strongly dominant negative in the presence of wild-type", True, "functional_study",
     "Direct dominant-negative demonstration with a SNARE-ring stoichiometry model."),
    ("SNAP25", "gain-of-function", "PMID:33147442",
     "aberrant spontaneous release is sufficient to cause disease", True, "functional_study",
     "One variant augments spontaneous release without changing evoked release."),
    ("SNAP25", "loss-of-function", "PMID:40181518",
     "could be ameliorated by the clinically approved", True, "functional_study",
     "Patient-derived human neurons: I67N reduces release and responds to 4-aminopyridine."),
    ("SNAP25", "loss-of-function", "PMID:40181518",
     "which displayed an increase in spontaneous release", False, "functional_study",
     "COUNTER: V48F shows the opposite phenotype, so the mechanism is variant-specific, not gene-level."),
    # ---------------- VAMP2
    ("VAMP2", "loss-of-function", "PMID:30929742",
     "five heterozygous de novo mutations in VAMP2", True, "case_series",
     "Discovery paper: five de novo VAMP2 variants impairing membrane fusion."),
    ("VAMP2", "protein-destabilization", "PMID:41166419",
     "SNARE complex affinity, stability, and conformational deficits", True, "functional_study",
     "Nine variants differing in SNARE-complex affinity, stability and conformation."),
    ("VAMP2", "gain-of-function", "PMID:41166419",
     "disproportionate augmentation of spontaneous neurotransmitter release", "minority", "functional_study",
     "Some VAMP2 variants augment spontaneous release rather than only impairing fusion."),
    # ---------------- STX1B
    ("STX1B", "loss-of-function", "PMID:30737342",
     "loss-of-function mutations in benign syndromes", True, "cohort",
     "Genotype-phenotype split: truncating/LoF milder, SNARE-motif missense more severe."),
    ("STX1B", "loss-of-function", "PMID:26818399",
     "deletion results in haploinsufficiency of STX1B", True, "case_report",
     "A deletion causing STX1B haploinsufficiency with myoclonic astatic epilepsy."),
    ("STX1B", "loss-of-function", "PMID:32572454",
     "size of the readily releasable pool of vesicles", True, "functional_study",
     "G226R: lost Munc18-1 interaction, smaller releasable pool, less Ca2+-triggered release."),
    ("STX1B", "gain-of-function", "PMID:32572454",
     "enhanced fusogenicity and increased vesicular release probability", "minority", "functional_study",
     "COUNTER: V216E, equally severe clinically, increases fusogenicity and release probability."),
    ("STX1B", "loss-of-function", "PMID:33677401",
     "no clear genotype-phenotype correlation can be established", False, "cohort",
     "COUNTER: loss-of-function variants in very differently affected individuals."),
    ("STX1B", "gain-of-function", "PMID:42673765",
     "exhibited both gain- and loss-of-function characteristics", "minority", "functional_study",
     "COUNTER/nuance: patient iPSC neurons show mixed gain and loss of function for G226R."),
    # ---------------- SYT2
    ("SYT2", "dominant-negative", "PMID:34037996",
     "dominant-negative effect due to disruption of the dual function", True, "case_series",
     "Dominant SYT2-CMS proposed to act by a dominant-negative effect on the Ca2+ sensor."),
    ("SYT2", "loss-of-function", "PMID:32776697",
     "biallelic loss of function variants in SYT2", True, "case_series",
     "Biallelic loss of function also causes presynaptic CMS, so the disease is not dominant-only."),
    # ---------------- CPLX1
    ("CPLX1", "loss-of-function", "PMID:28422131",
     "loss of complexin 1 function may lead to a complex but variable clinical phenotype", True, "case_series",
     "Recessive CPLX1 disease; the authors flag the evidence as limited."),
    # ---------------- UNC13A
    ("UNC13A", "gain-of-function", "PMID:28192369",
     "distinct dominant gain of function", True, "functional_study",
     "P814L increases vesicle fusion propensity: dominant gain of function."),
    ("UNC13A", "loss-of-function", "PMID:27648472",
     "homozygous nonsense mutation in the N-terminal domain", True, "case_report",
     "Recessive truncating loss of function with microcephaly and fatal myasthenia."),
    ("UNC13A", "gain-of-function", "PMID:41125872",
     "we identify three mechanisms of pathogenicity", False, "functional_study",
     "Resolves the debate: reduced expression, gain of function and impaired regulation coexist."),
    # ---------------- STX1A
    ("STX1A", "loss-of-function", "PMID:36564538",
     "eight individuals harboring ultra rare variants in STX1A", True, "case_series",
     "Gene-disease evidence for STX1A as a Mendelian neurodevelopmental gene."),
    # ---------------- NSF
    ("NSF", "dominant-negative", "PMID:31675180",
     "two pathogenic variants exert a dominant negative effect", True, "animal_model",
     "Only Mendelian NSF report; dominant-negative inferred from a Drosophila eye assay."),
    # ---------------- SLC6A1
    ("SLC6A1", "loss-of-function", "PMID:25865495",
     "lead to loss of function of GAT-1", True, "case_series",
     "Discovery paper: SLC6A1 variants reduce GABA re-uptake in myoclonic-atonic epilepsy."),
    ("SLC6A1", "protein-destabilization", "PMID:34028503",
     "endoplasmic reticulum retention, and subsequent degradation", True, "functional_study",
     "22 variants: misfolding, ER retention and degradation as the shared molecular defect."),
    ("SLC6A1", "protein-destabilization", "PMID:31176687",
     "caused instability of the mutant transporter protein", True, "functional_study",
     "G234S: protein instability with reduced surface and total protein."),
    ("SLC6A1", "protein-destabilization", "PMID:36741049",
     "absent from their regular site of action at the cell surface", True, "functional_study",
     "Independent lab (Drosophila platform): misfolding/trafficking failure is a dominant class."),
    ("SLC6A1", "haploinsufficiency", "PMID:38781976",
     "no evidence for dominant-negative or gain-of-function effects", True, "functional_study",
     "213 variants: haploinsufficiency without dominant-negative or gain-of-function effects."),
    ("SLC6A1", "protein-destabilization", "PMID:38781976",
     "GAT-1 was on the surface but with reduced activity for the remaining third", False, "functional_study",
     "COUNTER/limit: about a third of LoF missense variants traffic normally but transport poorly."),
    ("SLC6A1", "protein-destabilization", "PMID:36741049",
     "modest fraction of the mutants displayed correct targeting", False, "functional_study",
     "COUNTER/limit: independent confirmation of a surface-expressed, transport-dead class."),
]

# --------------------------------------------------------------------------------------
# Family framing: the reviews that justify treating these genes as ONE cluster.
# --------------------------------------------------------------------------------------
FAMILY_CLAIMS = [
    ("PMID:32559416", "We propose to unify these syndromes",
     ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B", "STX1A", "UNC13A", "CPLX1", "NSF"],
     "Verhage & Sorensen 2020 coin and define the SNAREopathies family."),
    ("PMID:33299146", 'may be termed "SNAREopathie',
     ["SNAP25", "STX1B", "STXBP1", "VAMP2"],
     "Clinical-cohort framing: overlapping core symptoms across SNARE-complex genes."),
    ("PMID:36564538", "expands the group of rare diseases called SNAREopathies",
     ["STX1A"], "Places STX1A inside the family."),
    ("PMID:32916768", "disorders of synaptic vesicle fusion caused either by toxic insult",
     ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1A", "UNC13A", "CPLX1"],
     "Alternative framing: 'disorders of synaptic vesicle fusion machinery'."),
    ("PMID:32738165", "disturbance of at least one SVC subprocess",
     ["STXBP1", "SYT1"], "Maps each gene onto a synaptic-vesicle-cycle subprocess."),
    ("PMID:35095745", 'recently defined as "SNAREopathies',
     ["STX1B", "VAMP2", "SNAP25", "STXBP1"], "Independent review reusing the label."),
    ("PMID:41166419", "necessity for a functional classification of SNAREopathies",
     ["VAMP2", "SNAP25", "STX1B", "STXBP1"],
     "Argues the family should be subdivided by variant FUNCTION, not by gene."),
]

# --------------------------------------------------------------------------------------
# The bridge hypothesis: STXBP1 <-> SLC6A1 shared destabilization + chaperone approach.
# --------------------------------------------------------------------------------------
BRIDGE_CLAIMS = [
    # supporting
    ("PMID:30266908", "destabilization and aggregation of the mutant protein", True, "functional_study",
     "STXBP1 arm: missense variants destabilize/aggregate Munc18-1."),
    ("PMID:30266908", "chemical chaperones 4-phenylbutyrate, sorbitol, and trehalose", True,
     "functional_study", "4-PBA and other chemical chaperones reverse Munc18-1 mutant deficits."),
    ("PMID:34028503", "endoplasmic reticulum retention, and subsequent degradation", True,
     "functional_study", "SLC6A1 arm: misfolding/ER retention/degradation across 22 variants."),
    ("PMID:35911425", "suppressed spike wave discharges in heterozygous knockin mice", True,
     "animal_model", "4-PBA raises GAT-1 and suppresses EEG discharges in knockin mice."),
    ("PMID:42157447", "PBA restored GABA uptake and GAT-1 surface expression across all variants", True,
     "functional_study", "32 variants plus two knockin models; TUDCA reproduces the effect."),
    ("PMID:42650175", "PBA reduced ER retention", True, "functional_study",
     "Quantified ER-retention correction in iPSC-derived human cells."),
    ("PMID:36741049", "three compounds (chemical and pharmacological chaperones)", True,
     "functional_study", "Independent lab replicates chaperone rescue in SLC6A1."),
    ("PMID:41625255", "such as the use of chemical or pharmacological chaperones", True, "review",
     "States the cross-gene proteostasis-plus-chaperone hypothesis explicitly (for SLC6A1 + GABA-A receptors)."),
    ("NCT04937062", "may help the the remaining proteins work better", True, "clinical_trial",
     "The strongest bridge artifact: ONE trial enrolls STXBP1 and SLC6A1 patients on this shared rationale."),
    # limiting / contradicting
    ("PMID:38781976", "GAT-1 was on the surface but with reduced activity for the remaining third",
     False, "functional_study",
     "About a third of SLC6A1 LoF missense variants traffic normally: outside any chaperone's reach."),
    ("PMID:38781976", "no evidence for dominant-negative or gain-of-function effects", False,
     "functional_study",
     "No dominant-negative effect in SLC6A1, so the Munc18-1 co-aggregation model does not transfer."),
    ("PMID:29538625", "no effect when overexpressed on a heterozygous background", False,
     "functional_study", "Same limit on the STXBP1 side of the bridge."),
    ("PMID:35911425", "regardless of rescuing the mutant", False, "animal_model",
     "The proponents note 4-PBA may act on wild-type trafficking, i.e. not mutant-specific."),
    ("PMID:33332765", "their required high concentrations and potential toxicity", False,
     "functional_study", "Chemical chaperones need high, potentially toxic concentrations."),
    ("PMID:38242640", "but not heterozygous knockout neurons expressing G544D", False,
     "functional_study", "A specific missense variant resists a rescue that works in pure haploinsufficiency."),
    ("PMID:34028503", "did not find a clear correlation of GABA uptake function", False,
     "functional_study", "Uptake deficit does not track clinical phenotype, so rescue may not predict benefit."),
    ("PMID:39923323", "moderate reduction in epileptiform discharges", False, "case_series",
     "Only human outcome data: n=2, uncontrolled, and in deletion (not misfolding) patients."),
    ("PMID:42157447", "HDAC inhibitors exhibited modest rescue in vitro but failed", False,
     "functional_study", "Narrows the mechanism: PBA's HDAC-inhibitor activity is not the therapeutic axis."),
]

# --------------------------------------------------------------------------------------
# Therapies.  slug -> node + edges.  evidence entries are (ref, needle, supports, study_type)
# --------------------------------------------------------------------------------------
THERAPIES = [
    {"slug": "4-phenylbutyrate", "label": "4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone)",
     "synonyms": ["4-PBA", "PBA", "sodium phenylbutyrate", "glycerol phenylbutyrate", "Ravicti"],
     "modality": "chaperone", "stage": "clinical",
     "summary": "An FDA-approved drug (for urea-cycle disorders) that acts as a chemical chaperone, "
                "helping unstable or misfolded proteins fold and reach their working location. It is "
                "being tested in STXBP1- and SLC6A1-related disorders because both can involve "
                "destabilized protein.",
     "mechanisms": ["mech:protein-destabilization"], "diseases": ["STXBP1", "SLC6A1"],
     "evidence": [("PMID:30266908", "chemical chaperones 4-phenylbutyrate, sorbitol, and trehalose", True, "functional_study"),
                  ("PMID:35911425", "suppressed spike wave discharges in heterozygous knockin mice", True, "animal_model"),
                  ("PMID:42157447", "PBA restored GABA uptake and GAT-1 surface expression across all variants", True, "functional_study"),
                  ("NCT04937062", "test if glycerol phenylbutyrate is safe and well tolerated", True, "clinical_trial")],
     "counter": [("PMID:33332765", "their required high concentrations and potential toxicity", False, "functional_study"),
                 ("PMID:35911425", "regardless of rescuing the mutant", False, "animal_model"),
                 ("PMID:39923323", "moderate reduction in epileptiform discharges", False, "case_series"),
                 ("PMID:38781976", "GAT-1 was on the surface but with reduced activity for the remaining third", False, "functional_study")],
     "trials": ["NCT04937062", "NCT07847918"]},
    {"slug": "munc18-1-pharmacological-chaperone",
     "label": "Structure-based pharmacological chaperones for Munc18-1",
     "synonyms": ["Munc18-1 pharmacochaperone"], "modality": "small_molecule", "stage": "preclinical",
     "summary": "Small molecules designed from the Munc18-1 structure to bind and stabilize the protein. "
                "Intended to replace generic chemical chaperones, which need high doses.",
     "mechanisms": ["mech:protein-destabilization"], "diseases": ["STXBP1"],
     "evidence": [("PMID:33332765", "identify two pharmacological chaperones via structure-based drug design", True, "functional_study")],
     "counter": [], "trials": []},
    {"slug": "aav-stxbp1-gene-replacement", "label": "AAV STXBP1 gene supplementation",
     "synonyms": ["AAV-STXBP1", "CAP-002"], "modality": "gene_replacement", "stage": "clinical",
     "summary": "A virus-delivered extra copy of STXBP1, aimed at raising Munc18-1 back toward normal "
                "levels. Preclinical work set a transduction threshold; the first human trial was "
                "terminated after a stopping rule was met.",
     "mechanisms": ["mech:haploinsufficiency"], "diseases": ["STXBP1"],
     "evidence": [("PMID:41883162", "cortical neuronal transduction needed for phenotypic improvement", True, "animal_model"),
                  ("NCT06983158", "learn about the safety of CAP-002 gene therapy", True, "clinical_trial")],
     "counter": [("PMID:41883162", "no clear clinical data or human evidence defining a therapeutic threshold", False, "animal_model"),
                 ("NCT06983158", "Stopping rule for study was met", False, "clinical_trial")],
     "trials": ["NCT06983158"]},
    {"slug": "aav-slc6a1-gene-replacement", "label": "scAAV9.P546.SLC6A1 intrathecal gene replacement",
     "synonyms": ["scAAV9.P546.SLC6A1"], "modality": "gene_replacement", "stage": "clinical",
     "summary": "A virus-delivered extra copy of SLC6A1, given into the spinal fluid, to restore GABA "
                "re-uptake. First-in-human trial is open by invitation.",
     "mechanisms": ["mech:haploinsufficiency", "mech:gaba-reuptake"], "diseases": ["SLC6A1"],
     "evidence": [("NCT07173153", "AAV9 vector carrying the", True, "clinical_trial"),
                  ("PMID:38781976", "Strategies to increase the expression of the wild-type", True, "functional_study")],
     "counter": [], "trials": ["NCT07173153"]},
    {"slug": "3-4-diaminopyridine", "label": "3,4-Diaminopyridine (amifampridine)",
     "synonyms": ["3,4-DAP", "amifampridine"], "modality": "repurposed_drug", "stage": "clinical",
     "summary": "A potassium-channel blocker that lengthens the nerve signal so more neurotransmitter is "
                "released. Used in presynaptic congenital myasthenic syndromes; reported to help SYT2 patients.",
     "mechanisms": ["mech:ca-triggered-exocytosis"], "diseases": ["SYT2"],
     "evidence": [("PMID:26519543", "3,4-diaminopyridine produced both a clinical benefit", True, "case_series"),
                  ("PMID:32250532", "diaminopyridine and pyridostigmine were effective", True, "case_report")],
     "counter": [("PMID:32250532", "albuterol was ineffective", False, "case_report")], "trials": []},
    {"slug": "aminopyridine-presynaptic-boost", "label": "Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost",
     "synonyms": ["4-aminopyridine", "4-AP", "dalfampridine"], "modality": "repurposed_drug",
     "stage": "clinical",
     "summary": "The same class of potassium-channel blockers, used to push more neurotransmitter release "
                "when a SNARE-machinery variant has weakened it. Reported for VAMP2 and SYT1, and in "
                "human neurons carrying a SNAP25 variant.",
     "mechanisms": ["mech:ca-triggered-exocytosis"], "diseases": ["VAMP2", "SYT1", "SNAP25"],
     "evidence": [("PMID:32906212", "clinical response of the patient to 2 years of off-label aminopyridine", True, "case_report"),
                  ("PMID:32362337", "clinically approved K+ channel antagonist is able to rescue", True, "functional_study"),
                  ("PMID:40181518", "could be ameliorated by the clinically approved", True, "functional_study")],
     "counter": [("PMID:40181518", "which displayed an increase in spontaneous release", False, "functional_study"),
                 ("PMID:41166419", "necessity for a functional classification of SNAREopathies", False, "functional_study")],
     "trials": []},
    {"slug": "unc13a-splice-switching-aso", "label": "UNC13A cryptic-exon splice-switching ASO",
     "synonyms": ["UNC13A ASO"], "modality": "aso", "stage": "preclinical",
     "summary": "An antisense oligonucleotide that blocks a cryptic exon so the cell makes full-length "
                "UNC13A protein again. Developed for TDP-43-related ALS, not for the Mendelian UNC13A "
                "neurodevelopmental disorder.",
     "mechanisms": ["mech:synaptic-vesicle-priming"], "diseases": ["UNC13A"],
     "evidence": [("PMID:38979232", "robustly rescue UNC13A protein levels", True, "functional_study")],
     "counter": [], "trials": [],
     "caveat": "Source is a bioRxiv preprint (not peer reviewed), and the target population is ALS."},
    {"slug": "acetylcholinesterase-inhibitor-cms", "label": "Acetylcholinesterase inhibitors (e.g. pyridostigmine)",
     "synonyms": ["pyridostigmine"], "modality": "repurposed_drug", "stage": "clinical",
     "summary": "Drugs that make each released packet of acetylcholine act for longer at the "
                "neuromuscular junction. Reported to improve strength in SYT2-related presynaptic "
                "congenital myasthenic syndrome.",
     "mechanisms": ["mech:ca-triggered-exocytosis"], "diseases": ["SYT2"],
     "evidence": [("PMID:32776697", "acetylcholinesterase inhibitor pursued in three patients", True, "case_series"),
                  ("PMID:32250532", "diaminopyridine and pyridostigmine were effective", True, "case_report")],
     "counter": [], "trials": []},
]


def referenced_ids() -> tuple[set[str], set[str]]:
    """Every PMID / NCT any claim depends on (used by pubmed.py to pre-fetch)."""
    pmids, ncts = set(), set()

    def add(ref):
        (ncts if ref.startswith("NCT") else pmids).add(ref.replace("PMID:", ""))
    for c in DISEASE_MECHANISM_CLAIMS:
        add(c[2])
    for c in FAMILY_CLAIMS:
        add(c[0])
    for c in BRIDGE_CLAIMS:
        add(c[0])
    for t in THERAPIES:
        for e in t["evidence"] + t["counter"]:
            add(e[0])
        for n in t["trials"]:
            ncts.add(n)
    return pmids, ncts


def main() -> None:
    bad = 0
    groups = [("disease-mechanism", [(c[2], c[3]) for c in DISEASE_MECHANISM_CLAIMS]),
              ("family", [(c[0], c[1]) for c in FAMILY_CLAIMS]),
              ("bridge", [(c[0], c[1]) for c in BRIDGE_CLAIMS]),
              ("therapy", [(e[0], e[1]) for t in THERAPIES for e in t["evidence"] + t["counter"]])]
    for name, items in groups:
        print(f"\n=== {name} ({len(items)} claims)")
        for ref, needle in items:
            try:
                q = quote_for(ref, needle)
                print(f"  OK   {ref:14s} {q[:120]}")
            except Exception as ex:  # noqa: BLE001
                bad += 1
                print(f"  BAD  {ref:14s} {ex}")
    print(f"\nunresolved needles: {bad}")


if __name__ == "__main__":
    main()
