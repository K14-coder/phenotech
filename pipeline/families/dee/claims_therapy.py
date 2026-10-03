"""Therapy claims (needles only). Evidence tuples: (ref, needle, study_type).
`counter` items are limiting or contradicting findings, attached exactly as the source states them.
"""
from claims_therapy2 import THERAPIES_2

LBL = "database_record"
RCT = "clinical_trial"

THERAPIES = [
    {"slug": "fenfluramine", "existing": True, "label": "Fenfluramine", "modality": "repurposed_drug",
     "approvals": [{"agency": "FDA", "label": "FINTEPLA", "ref": "FDA-label:FINTEPLA"}],
     "diseases": {
         "SCN1A": {"evidence": [("FDA-label:FINTEPLA", "FINTEPLA is indicated for the treatment of seizures associated with Dravet syndrome (DS)", LBL),
                                ("PMID:31862249", "fenfluramine provided significantly greater reduction in convulsive seizure frequency", RCT),
                                ("NCT02682927", "adjunctive therapy in pediatric and young adult subjects with Dravet syndrome", RCT)],
                   "note": "FDA-labelled for seizures in Dravet syndrome (a syndrome-level indication; Dravet syndrome is the main SCN1A-related disorder)."},
         "CDKL5": {"evidence": [("NCT05064878", "examine the efficacy and safety of ZX008 in children and adults with cyclin-dependent", RCT)],
                   "note": "A phase 3 trial in CDKL5 deficiency disorder is registered; no result is attached here."}}},
    {"slug": "stiripentol", "label": "Stiripentol", "synonyms": ["DIACOMIT"], "modality": "small_molecule", "stage": "approved",
     "summary": "An anti-seizure medicine with an FDA label for seizures associated with Dravet syndrome in patients taking clobazam.",
     "node_evidence": [("FDA-label:DIACOMIT", "DIACOMIT is indicated for the treatment of seizures associated with Dravet syndrome (DS)", LBL)],
     "diseases": {
         "SCN1A": {"evidence": [("FDA-label:DIACOMIT", "DIACOMIT is indicated for the treatment of seizures associated with Dravet syndrome (DS)", LBL),
                                ("PMID:11089822", "This controlled trial shows the antiepileptic efficacy", RCT),
                                ("NCT02239276", "Expanded Access Use of Stiripentol in Participants With Dravet Syndrome or Epileptic Encephalopathies Associated With Sodium Channel", RCT)],
                   "counter": [("FDA-label:DIACOMIT", "There are no clinical data to support the use of DIACOMIT as monotherapy", LBL)],
                   "note": "FDA-labelled for seizures in Dravet syndrome with clobazam; the label states no data support monotherapy."}}},
    {"slug": "cannabidiol", "label": "Cannabidiol (plant-derived, pharmaceutical)", "synonyms": ["EPIDIOLEX", "CBD", "GWP42003-P"],
     "modality": "small_molecule", "stage": "approved",
     "summary": "A purified cannabidiol oral solution with an FDA label covering seizures associated with Dravet syndrome.",
     "node_evidence": [("FDA-label:EPIDIOLEX", "EPIDIOLEX is indicated for the treatment of seizures associated with Lennox-Gastaut syndrome (LGS)", LBL)],
     "diseases": {
         "SCN1A": {"evidence": [("FDA-label:EPIDIOLEX", "EPIDIOLEX is indicated for the treatment of seizures associated with Lennox-Gastaut syndrome (LGS)", LBL),
                                ("PMID:28538134", "cannabidiol resulted in a greater reduction in convulsive-seizure frequency than placebo", RCT),
                                ("NCT02091375", "potential antiepileptic effects of cannabidiol (GWP42003-P) in children and young adults with Dravet syndrome", RCT)],
                   "counter": [("PMID:28538134", "was associated with higher rates of adverse events", RCT)],
                   "note": "FDA-labelled for seizures in Dravet syndrome (syndrome-level indication)."}}},
    {"slug": "ganaxolone", "label": "Ganaxolone", "synonyms": ["ZTALMY"], "modality": "small_molecule", "stage": "approved",
     "summary": "A neuroactive steroid with an FDA label for seizures associated with CDKL5 deficiency disorder.",
     "node_evidence": [("FDA-label:ZTALMY", "ZTALMY is indicated for the treatment of seizures associated with cyclin-dependent kinase-like 5 (CDKL5) deficiency disorder (CDD) in patients 2 years", LBL)],
     "diseases": {
         "CDKL5": {"evidence": [("FDA-label:ZTALMY", "ZTALMY is indicated for the treatment of seizures associated with cyclin-dependent kinase-like 5 (CDKL5) deficiency disorder (CDD) in patients 2 years", LBL),
                                ("PMID:35429480", "Ganaxolone significantly reduced the frequency of CDD-associated seizures", RCT),
                                ("NCT03572933", "genetically confirmed CDKL5 gene mutation", RCT)],
                   "note": "FDA-labelled for seizures in CDKL5 deficiency disorder (gene-defined indication)."}}},
    {"slug": "zorevunersen", "label": "Zorevunersen (STK-001, SCN1A TANGO antisense oligonucleotide)", "synonyms": ["STK-001", "TANGO ASO"],
     "modality": "aso", "stage": "clinical",
     "summary": "An antisense oligonucleotide designed to raise productive SCN1A (NaV1.1) expression; in phase 3 for Dravet syndrome.",
     "node_evidence": [("PMID:41780062", "an antisense oligonucleotide designed to up-regulate NaV1.1 sodium channels", "clinical_trial")],
     "targets": [("mech:haploinsufficiency", [("PMID:32848094", "Targeted Augmentation of Nuclear Gene Output (TANGO)", "animal_model")])],
     "diseases": {
         "SCN1A": {"evidence": [("PMID:41780062", "support the continued development of zorevunersen", RCT),
                                ("PMID:32848094", "reduced the incidence of electrographic seizures and sudden unexpected death", "animal_model"),
                                ("NCT06872125", "variant of uncertain significance in the sodium voltage-gated channel type 1 alpha subunit (SCN1A) gene", RCT)],
                   "counter": [("NCT06872125", "documented variant in the SCN1A gene associated with gain-of-function", RCT)],
                   "note": "Phase 1/2a data and a recruiting phase 3; the phase 3 record lists SCN1A gain-of-function variants as an exclusion."}}},
    {"slug": "etx101", "label": "ETX101 (AAV9-delivered gene therapy for SCN1A Dravet syndrome)", "synonyms": ["ETX101"],
     "modality": "other", "stage": "clinical",
     "summary": "An AAV9-delivered gene therapy in phase 1/2 for SCN1A-positive Dravet syndrome.",
     "node_evidence": [("NCT05419492", "an AAV9-Delivered Gene Therapy in Infants and Children With SCN1A-Positive Dravet Syndrome", RCT)],
     "diseases": {
         "SCN1A": {"evidence": [("NCT05419492", "predicted loss of function pathogenic or likely pathogenic SCN1A variant", RCT),
                                ("PMID:40381457", "such as zorevunersen and ETX101 for SCN1A-related Dravet syndrome", "review")],
                   "note": "Phase 1/2 trial enrolling SCN1A loss-of-function Dravet syndrome."}}},
] + THERAPIES_2
