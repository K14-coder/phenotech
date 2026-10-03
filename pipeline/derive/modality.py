"""Product 2: rule-based modality screen -> data/curated/modality.json

Run:  python3 pipeline/derive/modality.py   (after fetch_literature.py and variants.py)
In:   data/graph.json (mechanisms, gene attrs, therapies, trials), data/derived/variants.json
      data/raw/derive/pubmed/<PMID>.json (every quote is cut from these stored files by needle)
Out:  data/curated/modality.json  -- a DRAFT RULE SET AWAITING EXPERT REVIEW. It is a transparent
      screen for a biotech scout and for patient-group leaders, not medical advice and not a
      recommendation about any individual.

How it works: the rule table (RULES) is published inside the output file. Each rule has an id, a
condition in words, the fit it votes for, and at least one citation whose quote is lifted verbatim
from a stored source. The engine reads each disease's mechanism profile from the graph's driven_by
edges (status, confidence, attrs.minority_mechanism), plus gene-level checks (AAV packaging from
attrs.cds_length_bp / aav_cds_fits_4_7kb, ClinVar variant-class mix from variants.json, target
tissue, dosage-sensitivity literature, existing programmes and trials), fires the rules that apply,
and takes the WORST fit any rule votes for. Nothing here is generated text: reasons and caveats are
written per rule, and every literature claim carries a verified verbatim quote.
"""
from __future__ import annotations

from collections import defaultdict

from dcommon import CURATED, DERIVED, SLICE_GENES, TODAY, Graph, pub_evidence, read_json, write_json

STATUS = "draft rule set; awaiting expert review"
FIT_ORDER = ["good", "conditional", "poor"]

MODALITIES = [
    {"id": "aav_gene_replacement", "label": "AAV gene replacement",
     "what_it_does": "A virus delivers an extra, working copy of the gene to neurons; the faulty copy stays.",
     "best_case_mechanism": "haploinsufficiency / loss of function with no interfering mutant protein"},
    {"id": "aso_sirna_knockdown", "label": "ASO / siRNA knockdown (total or allele-specific)",
     "what_it_does": "An oligonucleotide lowers the amount of the gene's RNA, either both copies or only the faulty one.",
     "best_case_mechanism": "gain of function or dominant-negative, where less of the faulty product is better"},
    {"id": "transcript_upregulation", "label": "Transcript upregulation (TANGO/NMD- or uORF-targeting ASO, or CRISPRa)",
     "what_it_does": "A drug makes the cell read the gene's own healthy copy more efficiently instead of adding a new copy.",
     "best_case_mechanism": "haploinsufficiency with one intact allele and a targetable regulatory element"},
    {"id": "chemical_chaperone", "label": "Chemical / pharmacological chaperone",
     "what_it_does": "A small molecule helps an unstable protein fold and reach its working place instead of being degraded.",
     "best_case_mechanism": "protein destabilization / misfolding, where the mutant protein would work if it survived"},
    {"id": "symptomatic_pathway_small_molecule", "label": "Symptomatic small molecule acting on the pathway (e.g. 3,4-DAP, 4-AP, cholinesterase inhibitors)",
     "what_it_does": "An existing drug pushes the weakened synapse to release more neurotransmitter per nerve impulse. It does not change the gene.",
     "best_case_mechanism": "reduced evoked release, especially at the neuromuscular junction"},
    {"id": "gene_editing", "label": "Gene editing (base / prime editing, CRISPR repair)",
     "what_it_does": "A tool rewrites the faulty DNA letter in the patient's own cells.",
     "best_case_mechanism": "a recurrent, editable variant whose effect is dominant-negative or gain of function"},
]

# ---------------------------------------------------------------- rule table
# (id, modality, condition in words, fit it votes for, reason, caveat or None, [(PMID, needle, study_type, supports)])
RULES = [
    # ---- AAV gene replacement
    ("R-AAV-1", "aav_gene_replacement",
     "the gene's CDS does not fit a standard AAV (>4.7 kb)", "poor",
     "The coding sequence is too large for one standard AAV genome, so a single-vector gene replacement is not available.",
     "Dual/split-vector and other strategies to exceed the limit exist, but add complexity and are not de-risked here.",
     [("PMID:34904932", "packaging capacity is restricted", "review", True),
      ("PMID:34904932", "strategies that circumvent the packaging limit", "review", True)]),
    ("R-AAV-2", "aav_gene_replacement",
     "haploinsufficiency or loss of function is a supported mechanism and the CDS fits AAV", "good",
     "Too little working protein from one lost or non-functional copy is the mechanism gene supplementation is designed for, and the coding sequence fits one AAV.",
     None,
     [("PMID:42462387", "haploinsufficiency as the principal mechanism", "review", True)]),
    ("R-AAV-3", "aav_gene_replacement",
     "a dominant-negative effect is reported and is not flagged as a minority mechanism", "conditional",
     "If the mutant protein actively jams the machine, adding healthy copies may be diluted out by it, so supplementation alone may not be enough.",
     "Whether the dominant-negative reading holds for this gene is itself contested in the graph; see the driven_by edge.",
     [("PMID:41166419", "necessity for a functional classification of SNAREopathies", "functional_study", True)]),
    ("R-AAV-4", "aav_gene_replacement",
     "a gain-of-function mechanism is reported for at least some variants", "conditional",
     "For variants that make the protein do too much, adding more of it is the wrong direction, so eligibility would have to be decided per variant.",
     "Gene supplementation is not reversible, which raises the cost of getting the variant's functional class wrong.",
     [("PMID:34378168", "risk the exacerbation of gain-of-function variants", "review", True)]),
    ("R-AAV-5", "aav_gene_replacement",
     "published overexpression data exist for this gene", "conditional",
     "Overexpression of this protein has measurable consequences in animals, so the dose window matters as much as the delivery.",
     "Dose-finding needs a biomarker of protein level; no human threshold is established for any gene in this slice.",
     []),  # citations are gene-specific, see GENE_RULE_CITATIONS
    ("R-AAV-6", "aav_gene_replacement",
     "a gene-replacement trial for this disease was terminated or stopped", "conditional",
     "A first-in-human gene-replacement trial for this disease has already been stopped, which is counter-evidence a scout must read before planning another.",
     "A stopping rule being met is not public evidence about why; treat the reason as unknown.",
     [("PMID:41883162", "no clear clinical data or human evidence defining a therapeutic threshold", "animal_model", False)]),
    # ---- ASO / siRNA knockdown
    ("R-KD-1", "aso_sirna_knockdown",
     "a gain-of-function mechanism is reported and is not flagged as a minority mechanism", "good",
     "When the faulty product does too much, lowering it is the matching direction, and ASO knockdown has done this in a gain-of-function epilepsy model.",
     "Benefit was shown in a different gene and species; nothing of the kind has been tried in this slice.",
     [("PMID:34850743", "targeted reduction in SCN2A expression", "animal_model", True)]),
    ("R-KD-1b", "aso_sirna_knockdown",
     "a gain-of-function mechanism is reported but only for a minority of variants", "conditional",
     "Only a minority of published variants in this gene act by gain of function, so knockdown would fit that subset and work against everyone else.",
     "Variant-level functional classification does not exist for this gene yet (gap:variant-level-mechanism-map).",
     [("PMID:41166419", "necessity for a functional classification of SNAREopathies", "functional_study", True)]),
    ("R-KD-2", "aso_sirna_knockdown",
     "a dominant-negative effect is reported", "conditional",
     "Silencing only the faulty copy is the standard answer to a dominant-negative protein, and has been achieved for a dominant-negative substitution in another disease.",
     "Allele-specific targeting of a single-nucleotide change is hard and has to be built per variant.",
     [("PMID:38617974", "allele-specific transcript inactivation is a valid", "functional_study", True)]),
    ("R-KD-3", "aso_sirna_knockdown",
     "haploinsufficiency is a supported mechanism and no gain of function is reported", "poor",
     "The cell already makes too little of this protein, so lowering it further (total knockdown) works against the mechanism.",
     None,
     [("PMID:41515912", "sodium channel blockers contraindicated in loss-of-function cases", "review", True)]),
    ("R-KD-4", "aso_sirna_knockdown",
     "ClinVar shows no residue with two or more distinct pathogenic alleles", "conditional",
     "No recurrent hotspot appears in the pathogenic records for this gene, so an allele-specific drug would be a one-family (n-of-1) design rather than a reusable one.",
     None, []),
    # ---- transcript upregulation
    ("R-UP-1", "transcript_upregulation",
     "haploinsufficiency is a supported mechanism", "good",
     "Making the intact copy produce more protein is the mechanism-matched approach to haploinsufficiency, and both ASO and CRISPRa versions have rescued haploinsufficient animals.",
     None,
     [("PMID:32848094", "Targeted Augmentation of Nuclear Gene Output", "animal_model", True),
      ("PMID:40963013", "upregulation of the existing functional gene copy", "animal_model", True),
      ("PMID:30545847", "endogenous gene up-regulation could be a potential", "animal_model", True)]),
    ("R-UP-2", "transcript_upregulation",
     "always: the approach needs a targetable element in THIS gene", "conditional",
     "Each of these drugs needs a specific handle in the gene itself: a non-productive splicing event, a uORF, or a workable promoter/enhancer. Whether one exists here is not established.",
     "A uORF-blocking result has failed to reproduce in independent hands, so a candidate element is not a candidate drug.",
     [("PMID:27398791", "upstream open reading frames (uORFs) to specifically increase", "functional_study", True),
      ("PMID:39759875", "No upregulation (of endogenous or reporter protein", "functional_study", False)]),
    ("R-UP-3", "transcript_upregulation",
     "protein destabilization or a dominant-negative effect is reported", "conditional",
     "Upregulation that is not allele-specific raises the mutant transcript too, and for an aggregating or interfering protein more mutant may offset more wild type.",
     "A promoter- or splicing-level drug cannot currently distinguish the two alleles.",
     [("PMID:27597756", "form large polymers that coaggregate wild-type", "functional_study", True)]),
    ("R-UP-4", "transcript_upregulation",
     "a gain-of-function mechanism is reported for some variants", "conditional",
     "For gain-of-function variants, raising expression is the wrong direction, so eligibility would be per variant.",
     None,
     [("PMID:34378168", "risk the exacerbation of gain-of-function variants", "review", True)]),
    # ---- chaperone
    ("R-CH-1", "chemical_chaperone",
     "protein destabilization / misfolding is a reported mechanism", "good",
     "A chaperone's whole purpose is to stabilise a protein that would work if it were not degraded, which is exactly what the destabilization evidence for this gene describes.",
     None,
     [("PMID:31940970", "hallmark of a pharmacological chaperone", "review", True),
      ("PMID:36205620", "most frequent mechanism associated with a congenital pathogenic missense", "review", True)]),
    ("R-CH-2", "chemical_chaperone",
     "most pathogenic ClinVar records for this gene are null-like (truncating, splice or copy-number)", "conditional",
     "A chaperone can only act where there is a mutant protein to stabilise, and most pathogenic records for this gene remove the protein instead, so the approach reaches a minority of patients.",
     "The share below is a share of ClinVar records, not of patients; recurrent variants are counted once.",
     []),
    ("R-CH-3", "chemical_chaperone",
     "no destabilization mechanism is reported for this gene", "poor",
     "Nothing in the atlas links this gene's disease to an unstable or misfolded protein, so there is no stated target for a chaperone.",
     None, []),
    ("R-CH-4", "chemical_chaperone",
     "always, when a chaperone is on the table", "conditional",
     "Generic chemical chaperones are not selective: for this class the required concentrations and possible toxicity are the stated reason to look for a targeted molecule instead.",
     "Whether the benefit comes from correcting the mutant or from helping the wild-type protein traffic is unresolved, which changes who could benefit.",
     [("PMID:33332765", "required high concentrations and potential toxicity", "functional_study", True),
      ("PMID:35911425", "forward trafficking of the wildtype", "animal_model", False)]),
    # ---- symptomatic pathway small molecule
    ("R-SX-1", "symptomatic_pathway_small_molecule",
     "the disease has a neuromuscular-junction presentation (congenital myasthenic syndrome)", "good",
     "For presynaptic congenital myasthenic syndromes these drugs are the established symptomatic option, and the choice follows the genetic defect.",
     "Benefit is symptomatic: it does not change the course of the brain phenotype.",
     [("PMID:19019305", "Therapeutic agents used in CMS depend on the underlying defect", "review", True),
      ("PMID:22911480", "the effect of these drugs differs depending on the underlying genetic defect", "review", True)]),
    ("R-SX-2", "symptomatic_pathway_small_molecule",
     "release is reduced but the presentation is central (no NMJ phenotype)", "conditional",
     "Pushing more release could compensate a weakened synapse, and single-patient and human-neuron reports exist in this family, but no controlled trial does.",
     "Evidence in the central presentation is a case report and a cell model, not a trial.",
     [("PMID:32906212", "2 years of off-label aminopyridine treatment", "case_report", True),
      ("PMID:40181518", "ameliorated by the clinically approved K+-channel blocker", "functional_study", True)]),
    ("R-SX-3", "symptomatic_pathway_small_molecule",
     "a gain-of-function or excess-spontaneous-release variant class exists in this gene", "conditional",
     "The same gene contains variants that increase release, and for those a release-boosting drug points the wrong way, so variant class has to be established first.",
     "Aminopyridines have a narrow therapeutic range and a dose-related seizure risk, which matters in a population that already has epilepsy.",
     [("PMID:40181518", "increase in spontaneous release", "functional_study", True),
      ("PMID:22703551", "narrow therapeutic range suggest the need to evaluate the seizure risk", "review", True)]),
    ("R-SX-4", "symptomatic_pathway_small_molecule",
     "no drug of this class has been reported for this gene", "conditional",
     "The fit here comes from the shared pathway only; no report names this gene, so it rests on the family argument rather than on gene-specific evidence.",
     None,
     [("PMID:41166419", "necessity for a functional classification of SNAREopathies", "functional_study", True)]),
    # ---- gene editing
    ("R-ED-1", "gene_editing",
     "always, for every gene in this slice", "conditional",
     "Editing in the brain is attractive because neurons do not divide, so one correction could last, but no editing programme exists for any disease in this slice.",
     "Delivery, per-variant design and off-target assessment are all unsolved for these genes; treat this as a research direction, not a pipeline.",
     [("PMID:42041587", "post-mitotic neurons allow lasting effects after a single treatment", "review", True),
      ("PMID:40181540", "each inherited disorder has its own unique characteristics", "review", True)]),
    ("R-ED-2", "gene_editing",
     "a dominant-negative or gain-of-function mechanism is reported", "conditional",
     "Correcting or disabling the faulty allele is the one approach that addresses an interfering protein without adding more protein.",
     None,
     [("PMID:38617974", "allele-specific transcript inactivation is a valid", "functional_study", True)]),
    ("R-VAL-1", "*",
     "the graph records a gene-disease validity or functional-evidence gap for this gene", "conditional",
     "The gene-disease link or the mechanism itself is flagged as a gap in the atlas, so no modality can score better than conditional until that is settled.",
     "This caps the fit; it is not evidence against the approach.",
     []),
    ("R-ED-3", "gene_editing",
     "ClinVar shows no recurrent pathogenic residue in this gene", "poor",
     "Without a recurrent variant, each family needs its own editor, which no current development path supports for an ultra-rare disease.",
     None, []),
]

# gene-specific citations attached when a rule fires for that gene (keeps the rule table generic)
GENE_RULE_CITATIONS = {
    ("R-AAV-5", "SNAP25"): [("PMID:20002519", "excess SNAP-25 activity, restricted to the adult period", "animal_model", True)],
    ("R-AAV-5", "STXBP1"): [("PMID:23340504", "transgenic mouse strain that overexpresses the protein isoform munc18-1a", "animal_model", True)],
    ("R-AAV-5", "SLC6A1"): [("PMID:11742587", "Overexpression of GAT1 in mice results in cognitive deterioration", "animal_model", True),
                            ("PMID:15106822", "impaired cognitive function of transgenic mice could be rescued", "animal_model", True)],
}
# genes with published overexpression / dosage data (fires R-AAV-5)
OVEREXPRESSION_DATA = {"SNAP25", "STXBP1", "SLC6A1"}

# gene-specific notes added to a (disease, modality) assessment after the rules run.
# Each extra claim carries its own verified quote; "fit_override" is used only where the
# literature is explicit enough to beat the generic rule, and the reason says why.
GENE_NOTES = {
    ("STXBP1", "aav_gene_replacement"): {
        "reasons": [("A preclinical programme defined a transduction threshold and a neuron-targeted vector rescued haploinsufficient mice and was tolerated in primates.",
                     [("PMID:41883162", "rescued disease-associated phenotypes, with", "animal_model", True),
                      ("PMID:40349107", "rescued key behavioral phenotypes in Stxbp1", "animal_model", True)])],
        "caveats": [("Whether the mechanism is pure haploinsufficiency is contested: mutant Munc18-1 can co-aggregate the wild-type protein, while an independent study found no mutant effect on a heterozygous background.",
                     [("PMID:27597756", "form large polymers that coaggregate wild-type", "functional_study", True),
                      ("PMID:29538625", "no effect when overexpressed on a heterozygous background", "functional_study", False)])],
        "open_questions": [
            "Does the terminated CAP-002 trial change the dose or the eligibility assumptions, or neither? Nothing public says.",
            "Is a CSF Munc18-1/syntaxin-1 assay good enough to dose to a protein target rather than a vector dose?"],
    },
    ("STXBP1", "chemical_chaperone"): {
        "reasons": [("Chemical chaperones reversed Munc18-1 deficits across several models, and a shared STXBP1/SLC6A1 phenylbutyrate protocol is already in the clinic.",
                     [("PMID:30266908", "three chemical chaperones 4-phenylbutyrate", "functional_study", True)])],
        "caveats": [("One rescue that works in pure haploinsufficiency failed for a variant that depletes a binding partner, so variant class may decide who responds.",
                     [("PMID:38242640", "unstable in the absence of Munc18-1 and aggregate", "functional_study", True)])],
        "open_questions": [
            "Which STXBP1 variants are folding-correctable, and can existing cohorts be re-analysed by variant class?",
            "Do the structure-based Munc18-1 chaperones reach the brain at a tolerated dose?"],
    },
    ("SLC6A1", "chemical_chaperone"): {
        "reasons": [("Phenylbutyrate restored GABA uptake and surface expression across tested variants, and misfolding with ER retention is documented for this transporter.",
                     [("PMID:42157447", "PBA restored GABA uptake and GAT-1 surface expression", "functional_study", True),
                      ("PMID:34028503", "reduced cell surface expression of the variant transporter", "functional_study", True)])],
        "caveats": [("About a third of loss-of-function missense variants do reach the cell surface and still fail to transport, and those are outside any chaperone's reach.",
                     [("PMID:38781976", "two-thirds of loss-of-function missense variants prevented", "functional_study", True),
                      ("PMID:36741049", "modest fraction of the mutants displayed correct targeting", "functional_study", True)])],
        "open_questions": ["Can surface-expression assays be used prospectively to select who enters a chaperone trial?"],
    },
    ("SLC6A1", "aav_gene_replacement"): {
        "reasons": [("Raising wild-type SLC6A1 expression is the stated strategy for this gene, and a first-in-human intrathecal AAV9 trial is open (by invitation, n=1).",
                     [("PMID:38781976", "Strategies to increase the expression of the wild-type SLC6A1 allele", "functional_study", True)])],
        "caveats": [("Transporter dose cuts both ways: mice overexpressing GAT-1 show cognitive deterioration, reversible with a GAT-1 inhibitor.",
                     [("PMID:11742587", "Overexpression of GAT1 in mice results in cognitive deterioration", "animal_model", True)])],
        "open_questions": ["What is the acceptable upper bound on GAT-1 expression in a developing human brain?"],
    },
    ("VAMP2", "chemical_chaperone"): {
        "reasons": [("Nine VAMP2 disease variants were characterised as having SNARE-complex affinity, stability and conformational defects, which is the stated handle for a stabiliser.",
                     [("PMID:41166419", "specific SNARE complex affinity, stability", "functional_study", True)])],
        "caveats": [("Synaptobrevin-2 is natively unstructured outside the SNARE complex, so 'stability' here is not the folded-globular-protein case most chaperones were built for.",
                     [("PMID:29949059", "natively unstructured in the absence of lipids", "functional_study", True)]),
                    ("Some VAMP2 variants increase spontaneous release instead of reducing fusion, and more of that protein is not obviously better.",
                     [("PMID:41166419", "disproportionate augmentation of spontaneous neurotransmitter release", "functional_study", False)])],
        "open_questions": [
            "Does 4-phenylbutyrate change VAMP2 variant protein levels or SNARE-complex formation at all? No experiment reports this.",
            "Is 'destabilization' in the VAMP2 paper the same cell-biological event as Munc18-1 aggregation or GAT-1 ER retention?"],
    },
    ("SNAP25", "symptomatic_pathway_small_molecule"): {
        "reasons": [("The completed amifampridine CMS trial lists SNAP25B deficiency in its eligibility criteria, so this is an existing programme and not a gap.",
                     []),
                    ("In human neurons the I67N variant's phenotype was ameliorated by 4-aminopyridine.",
                     [("PMID:40181518", "ameliorated by the clinically approved K+-channel blocker", "functional_study", True)])],
        "caveats": [("A second SNAP25 variant (V48F) increases spontaneous release in patient neurons, and one variant is strongly dominant-negative, so the gene label does not predict the direction.",
                     [("PMID:40181518", "increase in spontaneous release", "functional_study", False),
                      ("PMID:41579375", "strongly dominant negative in the presence of wild-type", "functional_study", True)])],
        "open_questions": ["Do SNAP25-DEE patients without a myasthenic diagnosis have subclinical neuromuscular involvement (is repetitive nerve stimulation worth doing)?"],
    },
    ("UNC13A", "symptomatic_pathway_small_molecule"): {
        "reasons": [("The recessive truncating presentation is a presynaptic failure with a depleted readily releasable pool, which is the physiology these drugs act on; UNC13A is in the CMS registry's gene list.",
                     [("PMID:27648472", "homozygous nonsense mutation in the N-terminal domain", "case_report", True)])],
        "caveats": [("Three mechanisms coexist in this gene, including gain of function, so the variant class has to be settled before a release-boosting drug is considered.",
                     [("PMID:41125872", "three mechanisms of pathogenicity", "functional_study", True)]),
                    ("Unlike SNAP25 and SYT2, UNC13A is NOT named in the amifampridine trial's eligibility list, so there is no existing programme for it.",
                     [])],
        "open_questions": ["Has any UNC13A patient been given 3,4-DAP, and was neuromuscular transmission measured before and after?"],
    },
    ("UNC13A", "aav_gene_replacement"): {
        "reasons": [], "caveats": [],
        "open_questions": ["Is the 5.1 kb CDS the real blocker for a Munc13-1 strategy, or is dose/regulation the bigger problem?"],
    },
    ("UNC13A", "aso_sirna_knockdown"): {
        "reasons": [("A splice-switching ASO that blocks the UNC13A cryptic exon restores the protein and synaptic function, so an UNC13A oligonucleotide already exists as a tool.",
                     [("PMID:38979232", "targeting the UNC13A cryptic exon robustly rescue", "functional_study", True)])],
        "caveats": [("That ASO was built for TDP-43-related ALS, where the cryptic exon is the problem. It raises UNC13A rather than lowering it, and nothing connects it to the Mendelian UNC13A disorder.",
                     [])],
        "open_questions": ["Could the ALS cryptic-exon ASO be repurposed as an upregulator for UNC13A haploinsufficiency, and is the cryptic exon even used in these patients?"],
    },
    ("SYT1", "aso_sirna_knockdown"): {
        "reasons": [("SYT1 variants show potent, graded dominant-negative effects, which is the clearest allele-specific knockdown rationale in the slice.",
                     [("PMID:32362337", "potent, graded dominant-negative effects", "functional_study", True)])],
        "caveats": [("One SYT1 variant instead increases spontaneous and asynchronous release, so a single gene-level strategy will not fit everyone.",
                     [("PMID:38321119", "novel cellular phenotype, distinct from what was previously found", "functional_study", True)])],
        "open_questions": ["Is residual wild-type SYT1 (plus SYT2) enough once the mutant allele is silenced, or does the cell need the lost copy back as well?"],
    },
    ("SYT2", "symptomatic_pathway_small_molecule"): {
        "reasons": [("3,4-diaminopyridine gave both clinical benefit and better neuromuscular transmission in dominant SYT2 families, and helped a recessive patient.",
                     [("PMID:26519543", "3,4-diaminopyridine produced both a clinical benefit", "case_series", True)])],
        "caveats": [("In the same recessive patient albuterol did not help, so the class is not interchangeable.",
                     [("PMID:32250532", "albuterol was ineffective", "case_report", True)])],
        "open_questions": ["Does the dominant (dominant-negative) form respond differently from the recessive (null) form?"],
    },
    ("CPLX1", "chemical_chaperone"): {
        "reasons": [], "caveats": [],
        "open_questions": ["Complexin-1 is a fusion clamp, so would stabilising a clamp even be desirable? No functional study of patient variants exists."],
    },
    ("NSF", "aav_gene_replacement"): {
        "reasons": [], "caveats": [],
        "open_questions": ["The only NSF mechanism evidence is a Drosophila eye assay; does the dominant-negative claim hold in neurons before any supplementation logic is applied?"],
    },
    ("STX1A", "aav_gene_replacement"): {
        "reasons": [], "caveats": [],
        "open_questions": ["Is STX1A an established Mendelian disease gene at all (see gap:stx1a-mendelian-validity)? Modality screening is premature until that is settled."],
    },
    ("STX1B", "aso_sirna_knockdown"): {
        "reasons": [("Different STX1B variants point in opposite directions: one reduces the releasable pool, another increases fusogenicity, and patient neurons show one variant doing both.",
                     [("PMID:32572454", "unfolded protein unable to", "functional_study", True),
                      ("PMID:42673765", "gain- and loss-of-function characteristics", "functional_study", True)])],
        "caveats": [], "open_questions": ["Can STX1B variants be sorted into release-up and release-down classes well enough to choose a direction of therapy?"],
    },
}

EFFECT_MECHS = ["mech:haploinsufficiency", "mech:loss-of-function", "mech:dominant-negative",
                "mech:gain-of-function", "mech:protein-destabilization"]
NMJ_GENES_NOTE = ("A neuromuscular-junction presentation is recorded for this gene in the graph "
                  "(myasthenic subtype and/or neuromuscular HPO features).")


def ev(cites):
    out = []
    for ref, needle, st, supports in cites:
        out.append(pub_evidence(ref, needle, st, supports=supports))
    return out


def main():
    g = Graph()
    variants = read_json(DERIVED / "variants.json")

    # ---- mechanism profile per disease, straight from the graph's driven_by edges
    profile = {}
    for sym in SLICE_GENES:
        d = f"disease:{sym}"
        prof = {}
        for e in g.edges_of("driven_by", source=d):
            if e["target"] in EFFECT_MECHS:
                prof[e["target"]] = {"edge_id": e["id"], "status": e["status"], "confidence": e["confidence"],
                                     "minority": bool(e.get("attrs", {}).get("minority_mechanism")),
                                     "n_counter": len(e.get("counter_evidence") or [])}
        profile[sym] = prof

    # ---- gene-level checks
    checks = {}
    for sym in SLICE_GENES:
        gene = g.nodes[f"gene:{sym}"]
        ga = gene.get("attrs", {})
        v = variants["genes"][sym]
        dis = g.nodes[f"disease:{sym}"]
        subtypes = [s.get("name", "") for s in dis.get("attrs", {}).get("subtypes", [])]
        nmj_pheno = [g.nodes[e["target"]]["label"] for e in g.edges_of("has_phenotype", source=f"disease:{sym}")
                     if any(k in g.nodes[e["target"]]["label"].lower()
                            for k in ("fatigable", "compound muscle action potential", "areflexia", "myasthen"))]
        nmj = any("myasthen" in s.lower() for s in subtypes) or bool(nmj_pheno)
        programmes = []
        for e in g.edges_of("developed_for", target=f"disease:{sym}"):
            t = g.nodes[e["source"]]
            programmes.append({"therapy": e["source"], "label": t["label"],
                               "modality": t.get("attrs", {}).get("modality"),
                               "stage": t.get("attrs", {}).get("stage"), "edge_id": e["id"],
                               "edge_status": e["status"],
                               "trials": [tr.get("nct") for tr in t.get("attrs", {}).get("trials", []) or []],
                               "trial_status": [tr.get("status") for tr in t.get("attrs", {}).get("trials", []) or []],
                               "why_stopped": [tr.get("why_stopped") for tr in t.get("attrs", {}).get("trials", []) or []
                                               if tr.get("why_stopped")]})
        interventional = [{"study": e["source"], "label": g.nodes[e["source"]]["label"],
                           "status": g.nodes[e["source"]].get("attrs", {}).get("status"), "edge_id": e["id"]}
                          for e in g.edges_of("studies", target=f"disease:{sym}")
                          if g.nodes[e["source"]].get("attrs", {}).get("study_type") == "interventional"]
        terminated = [p for p in programmes if any(s in ("TERMINATED", "WITHDRAWN", "SUSPENDED") for s in p["trial_status"])]
        checks[sym] = {
            "aav_packaging": {"cds_length_bp": ga.get("cds_length_bp"), "fits_4_7kb": ga.get("aav_cds_fits_4_7kb"),
                              "protein_length_aa": ga.get("protein_length_aa")},
            "variant_class_mix": {"n_clinvar_plp": v["n"], "by_consequence": v["by_consequence"],
                                  "null_like_share": v["null_like_share"],
                                  "recurrent_residues": [r["residue"] for r in v["recurrent_residues"][:5]],
                                  "allele_specific_plausible": bool(v["recurrent_residues"])},
            "minority_mechanisms": [m for m, p in profile[sym].items() if p["minority"]],
            "contested_mechanisms": [m for m, p in profile[sym].items() if p["status"] == "contested"],
            "target_tissue": (["CNS", "neuromuscular junction"] if nmj else ["CNS"]),
            "nmj_evidence": {"subtypes": [s for s in subtypes if "myasthen" in s.lower()], "phenotypes": nmj_pheno},
            "overexpression_data": sym in OVEREXPRESSION_DATA,
            "validity_gaps": [gp["id"] for gp in g.gaps
                              if sym.lower() in gp["id"].lower()
                              and any(k in gp["id"] for k in ("mendelian-validity", "functional-evidence"))],
            "existing_programmes": programmes,
            "interventional_studies": interventional,
            "stopped_programmes": [{"therapy": p["therapy"], "trials": p["trials"],
                                    "status": p["trial_status"], "why_stopped": p["why_stopped"]} for p in terminated],
        }

    # ---- rule engine
    def fires(rule_id, sym):
        p, c = profile[sym], checks[sym]
        has = lambda m: m in p                                     # noqa: E731
        strong = lambda m: m in p and not p[m]["minority"]         # noqa: E731
        hi = has("mech:haploinsufficiency") or has("mech:loss-of-function")
        return {
            "R-AAV-1": c["aav_packaging"]["fits_4_7kb"] is False,
            "R-AAV-2": hi and c["aav_packaging"]["fits_4_7kb"] is True,
            "R-AAV-3": strong("mech:dominant-negative"),
            "R-AAV-4": has("mech:gain-of-function"),
            "R-AAV-5": c["overexpression_data"],
            "R-AAV-6": bool(c["stopped_programmes"]),
            "R-KD-1": strong("mech:gain-of-function"),
            "R-KD-1b": has("mech:gain-of-function") and not strong("mech:gain-of-function"),
            "R-KD-2": has("mech:dominant-negative"),
            "R-KD-3": hi and not has("mech:gain-of-function"),
            "R-KD-4": not c["variant_class_mix"]["allele_specific_plausible"],
            "R-UP-1": has("mech:haploinsufficiency"),
            "R-UP-2": True,
            "R-UP-3": has("mech:protein-destabilization") or has("mech:dominant-negative"),
            "R-UP-4": has("mech:gain-of-function"),
            "R-CH-1": has("mech:protein-destabilization"),
            "R-CH-2": has("mech:protein-destabilization") and c["variant_class_mix"]["null_like_share"] >= 0.5,
            "R-CH-3": not has("mech:protein-destabilization"),
            "R-CH-4": has("mech:protein-destabilization"),
            "R-SX-1": "neuromuscular junction" in c["target_tissue"],
            "R-SX-2": "neuromuscular junction" not in c["target_tissue"] and (hi or has("mech:dominant-negative")),
            "R-SX-3": has("mech:gain-of-function"),
            "R-SX-4": not any(p_["modality"] in ("repurposed_drug", "small_molecule") for p_ in c["existing_programmes"]),
            "R-ED-1": True,
            "R-ED-2": has("mech:dominant-negative") or has("mech:gain-of-function"),
            "R-ED-3": not c["variant_class_mix"]["allele_specific_plausible"],
            "R-VAL-1": bool(c["validity_gaps"]),
        }[rule_id]

    assessments, citations = {}, {}
    for sym in SLICE_GENES:
        per_mod = {}
        for mod in MODALITIES:
            fired = [r for r in RULES if r[1] in (mod["id"], "*") and fires(r[0], sym)]
            if not fired:
                per_mod[mod["id"]] = {"fit": "not_assessed", "reasons": [], "caveats": [],
                                      "citation_ids": [], "rules_fired": [], "open_questions_for_expert": [
                                          "No rule in the draft set applies here; the mechanism profile for this "
                                          "gene is too thin to screen this modality."]}
                continue
            fit = max((r[3] for r in fired), key=FIT_ORDER.index)
            reasons, caveats, evidence, rule_ids = [], [], [], []
            for rid, _m, cond, rfit, reason, caveat, cites in fired:
                rule_ids.append(rid)
                reasons.append({"rule": rid, "votes": rfit, "text": reason})
                if caveat:
                    caveats.append({"rule": rid, "text": caveat})
                evidence += ev(cites) + ev(GENE_RULE_CITATIONS.get((rid, sym), []))
            note = GENE_NOTES.get((sym, mod["id"]), {})
            for text, cites in note.get("reasons", []):
                reasons.append({"rule": "gene-specific", "votes": fit, "text": text})
                evidence += ev(cites)
            for text, cites in note.get("caveats", []):
                caveats.append({"rule": "gene-specific", "text": text})
                evidence += ev(cites)
            # graph evidence: the mechanism edges and programme edges this rests on
            edge_ids = sorted({p["edge_id"] for p in profile[sym].values()})
            prog_edges = sorted({p["edge_id"] for p in checks[sym]["existing_programmes"]})
            cit_ids = []
            for e in evidence:
                key = e["ref"] + "#" + str(abs(hash(e["quote"])) % 10 ** 6)
                if key not in citations:
                    citations[key] = e
                if key not in cit_ids:
                    cit_ids.append(key)
            oq = list(note.get("open_questions", []))
            if checks[sym]["contested_mechanisms"]:
                oq.append("The mechanism edges this screen rests on are contested in the graph: "
                          + ", ".join(checks[sym]["contested_mechanisms"]) + ". Which reading is right changes the fit.")
            per_mod[mod["id"]] = {
                "fit": fit, "reasons": reasons, "caveats": caveats,
                "citation_ids": cit_ids,
                "graph_edge_ids": {"mechanism": edge_ids, "existing_programmes": prog_edges},
                "rules_fired": rule_ids,
                "open_questions_for_expert": oq,
            }
        assessments[f"disease:{sym}"] = {"gene": sym, "label": g.nodes[f"disease:{sym}"]["label"],
                                         "checks": checks[sym], "modalities": per_mod}

    out = {
        "status": STATUS,
        "not_advice": ("This is a transparent, rule-based screen of which therapeutic approach could fit which "
                       "mechanism, written for a biotech scout and for patient-group leaders. It is NOT medical "
                       "advice, NOT a recommendation for any individual, and NOT a claim that any approach will "
                       "work. 'Good fit' means only that the published mechanism matches what the approach does. "
                       "Treatment decisions belong to a patient's own clinicians."),
        "meta": {
            "generated": TODAY, "graph": g.meta.get("generated_at"),
            "fit_scale": {"good": "the mechanism matches what the approach does, with at least one citation",
                          "conditional": "possible, but a named condition must be met first (variant class, dose, "
                                         "a missing target element, or counter-evidence)",
                          "poor": "the mechanism points the other way, or a hard constraint blocks it",
                          "not_assessed": "no rule applies; the mechanism profile is too thin"},
            "aggregation": "the WORST fit voted by any rule that fired, so one blocking rule is never averaged away",
            "citations": "assessments carry citation_ids into the top-level `citations` map; each entry is a "
                         "schema Evidence item whose quote was string-matched against the stored source",
            "inputs": ["data/graph.json driven_by / developed_for / studies edges and gene attrs",
                       "data/derived/variants.json ClinVar variant-class mix per gene",
                       "data/raw/derive/pubmed/<PMID>.json (every quote cut from the stored record)"],
            "code": "pipeline/derive/modality.py",
            "expert_review_checklist": "not yet attached; a rare-disease advisor's checklist may be added later "
                                       "and should record, per (disease, modality): agree/disagree with the fit, "
                                       "the missing condition, and anything the rule table gets backwards.",
        },
        "citations": citations,
        "modalities": MODALITIES,
        "rules": [{"id": r[0], "modality": r[1], "condition": r[2], "votes": r[3], "reason": r[4],
                   "caveat": r[5], "citations": [{"ref": c[0], "supports": c[3]} for c in r[6]]} for r in RULES],
        "assessments": assessments,
    }
    size = write_json(CURATED / "modality.json", out)
    n_ev = sum(len(m["citation_ids"]) for a in assessments.values() for m in a["modalities"].values())
    bad = [e for e in citations.values() if not e.get("verified")]
    print(f"[modality] {len(assessments)} diseases x {len(MODALITIES)} modalities, {len(RULES)} rules, "
          f"{n_ev} citation links over {len(citations)} distinct quotes ({len(bad)} unverified), {size / 1024:.0f} KB")
    for d, a in assessments.items():
        print(f"  {d:20s} " + " ".join(f"{m.split('_')[0][:5]}={v['fit'][:4]}" for m, v in a["modalities"].items()))
    if bad:
        raise SystemExit("unverified quote(s) in modality.json")


if __name__ == "__main__":
    main()
