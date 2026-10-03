"""Curated claims for the lysosomal storage disorder family.

EVIDENCE INTEGRITY: a claim never stores a hand-typed quote. It stores (ref, needle): `ref` is a stored
source ("PMID:<id>" -> data/raw/families/lysosomal/pubmed/<id>.json, "FDA:<slug>" -> the openFDA label in
data/raw/families/lysosomal/fda/<slug>.json, "NCT<id>" -> the ClinicalTrials.gov v2 record), and
`needle` is a short substring. lyso_common.quote_for() returns the one full sentence that contains the
needle, or raises if it is missing or ambiguous. verify.py re-checks every emitted quote independently.

Run:  python3 pipeline/families/lysosomal/curation.py     # resolve and print every claim
"""
from __future__ import annotations

# --------------------------------------------------------------------------- family-level framing
FAMILY_REF = ("PMID:30275469", "are a group of over 70 diseases")
FAMILY_STORAGE_REF = ("PMID:30275469", "(that is, 'storage')")
FAMILY_PROTEINS_REF = ("PMID:30275469", "including lysosomal enzymes and lysosomal membrane proteins")
FAMILY_THERAPY_REF = ("PMID:30275469", "Several LSDs can be treated with approved")
BBB_REVIEW_REF = ("PMID:33304924", "constitutes a significant obstacle")
BBB_ERT_REF = ("PMID:42794762", "generally do not reach therapeutically meaningful concentrations")

# --------------------------------------------------------------------------- per-disease mechanism claims
# (gene, mechanism slug, ref, needle, supports, study_type, plain-language note)
#   storage            -> mech:lysosomal-storage
#   enzyme-deficiency  -> mech:lysosomal-enzyme-deficiency
#   destabilization    -> mech:protein-destabilization (shared with the SNAREopathy layer)
#   loss-of-function   -> mech:loss-of-function (shared)
CLAIMS = [
    # GBA1 / Gaucher
    ("GBA1", "storage", "PMID:28218669", "which leads to an accumulation of its substrate, glucosylceramide", True, "review",
     "Glucocerebrosidase deficiency makes glucosylceramide build up, mainly in macrophages."),
    ("GBA1", "enzyme-deficiency", "PMID:28218669", "which leads to an accumulation of its substrate, glucosylceramide", True, "review",
     "Gaucher disease is caused by deficiency of the lysosomal enzyme glucocerebrosidase."),
    ("GBA1", "storage", "PMID:23622393", "responsible for the lysosomal accumulation of glucosylceramide", True, "review",
     "Independent review: lysosomal accumulation of glucosylceramide."),
    ("GBA1", "destabilization", "PMID:17644022", "earmark these proteins for destruction", True, "review",
     "Common GBA1 mutations make a misfolded enzyme that the endoplasmic reticulum destroys before it reaches the lysosome."),
    ("GBA1", "destabilization", "PMID:27449603", "Mutant enzyme recognized as misfolded is retained in the ER", True, "review",
     "Misfolded mutant glucocerebrosidase is retained in the endoplasmic reticulum."),
    # GAA / Pompe
    ("GAA", "storage", "PMID:32962155", "due to progressive accumulation of glycogen", True, "review",
     "Acid alpha-glucosidase deficiency makes glycogen accumulate, damaging heart and skeletal muscle."),
    ("GAA", "enzyme-deficiency", "PMID:32962155", "due to progressive accumulation of glycogen", True, "review",
     "Pompe disease is caused by deficiency of one lysosomal enzyme, acid alpha-glucosidase."),
    ("GAA", "storage", "PMID:18929906", "acid alpha-glucosidase deficiency leading to lysosomal glycogen storage", True, "review",
     "Independent review: lysosomal glycogen storage."),
    ("GAA", "destabilization", "PMID:25036864", "binds and stabilizes wild-type as well as multiple mutant forms of GAA", True, "animal_model",
     "A small-molecule chaperone binds and stabilizes mutant acid alpha-glucosidase."),
    # GLA / Fabry
    ("GLA", "storage", "PMID:21092187", "results in progressive accumulation of globotriaosylceramide within lysosomes", True, "review",
     "Alpha-galactosidase A deficiency makes globotriaosylceramide (Gb3) accumulate in lysosomes."),
    ("GLA", "enzyme-deficiency", "PMID:21092187", "due to deficient or absent lysosomal", True, "review",
     "Fabry disease is due to deficient or absent alpha-galactosidase A activity."),
    ("GLA", "destabilization", "PMID:30875019", "stabilizes and facilitates trafficking of amenable mutant forms", True, "review",
     "Many GLA missense variants make an unstable enzyme stuck in the endoplasmic reticulum that a chaperone can rescue."),
    ("GLA", "destabilization", "PMID:27834756", "stabilises specific mutant (amenable) forms", True, "clinical_trial",
     "Phase III trial: the chaperone stabilises amenable mutant enzyme and restores its trafficking."),
    # HEXA / Tay-Sachs
    ("HEXA", "storage", "PMID:30524313", "resulting in GM2 ganglioside accumulation predominantly in lysosomes of nerve cells", True, "review",
     "Hexosaminidase A deficiency makes GM2 ganglioside accumulate in nerve-cell lysosomes."),
    ("HEXA", "enzyme-deficiency", "PMID:30524313", "resulting in GM2 ganglioside accumulation predominantly in lysosomes of nerve cells", True, "review",
     "Tay-Sachs disease is caused by beta-hexosaminidase A deficiency."),
    ("HEXA", "destabilization", "PMID:20926324", "can be partially rescued", True, "clinical_trial",
     "Many HEXA variants can be partly rescued in patient cells by a pharmacological chaperone (pyrimethamine)."),
    # NPC1 / Niemann-Pick C
    ("NPC1", "storage", "PMID:20525256", "accumulation of unesterified cholesterol in perinuclear vesicles", True, "review",
     "Unesterified cholesterol accumulates in lysosomes of NPC patient cells."),
    ("NPC1", "loss-of-function", "PMID:20525256", "caused by mutations of either the NPC1 (95% of families)", True, "review",
     "Recessive mutations in NPC1 cause 95% of NPC families; NPC1 is a membrane transporter, not an enzyme."),
    ("NPC1", "destabilization", "PMID:24891511", "give rise to unstable proteins selected for endoplasmic reticulum-associated degradation", True, "functional_study",
     "The most frequent NPC1 variant (I1061T) makes an unstable protein that is destroyed by ER-associated degradation."),
    # SMPD1 / ASMD
    ("SMPD1", "storage", "PMID:39669638", "resulting in subsequent accumulation of its substrate, sphingomyelin", True, "review",
     "Acid sphingomyelinase deficiency makes sphingomyelin accumulate."),
    ("SMPD1", "enzyme-deficiency", "PMID:39669638", "resulting in subsequent accumulation of its substrate, sphingomyelin", True, "review",
     "SMPD1 variants cause low or absent acid sphingomyelinase activity."),
    ("SMPD1", "storage", "PMID:40414757", "leads to the accumulation of sphingomyelin mainly in macrophages", True, "review",
     "Independent review: sphingomyelin accumulates mainly in macrophages."),
    # IDUA / MPS I
    ("IDUA", "storage", "PMID:32188113", "leading to the storage of dermatan and heparan sulfate", True, "review",
     "Alpha-L-iduronidase deficiency makes dermatan and heparan sulfate accumulate."),
    ("IDUA", "enzyme-deficiency", "PMID:32188113", "leading to the storage of dermatan and heparan sulfate", True, "review",
     "MPS I is caused by deficiency of alpha-L-iduronidase."),
    # IDS / MPS II
    ("IDS", "storage", "PMID:34893157", "result in the accumulation of glycosaminoglycans (GAGs), heparan sulfate and dermatan sulfate", True, "review",
     "Loss of iduronate-2-sulfatase activity makes heparan and dermatan sulfate accumulate."),
    ("IDS", "enzyme-deficiency", "PMID:34893157", "The mutations cause a loss of enzymatic performance", True, "review",
     "MPS II mutations cause a loss of enzyme activity."),
    # CLN3
    ("CLN3", "storage", "PMID:27491213", "intracellular accumulation of autofluorescent storage material", True, "review",
     "Juvenile CLN3 disease is a lysosomal storage disease with autofluorescent storage material."),
    # TPP1 / CLN2
    ("TPP1", "storage", "PMID:27491216", "The deficiency of TPP1 causes the lysosomal accumulation", True, "review",
     "TPP1 deficiency makes ceroid lipofuscin accumulate in lysosomes."),
    ("TPP1", "enzyme-deficiency", "PMID:27491216", "caused by the deficiency of the lysosomal enzyme tripeptidyl peptidase 1", True, "review",
     "CLN2 disease is caused by deficiency of the lysosomal enzyme tripeptidyl peptidase 1."),
    # ARSA / MLD
    ("ARSA", "storage", "PMID:40577679", "leading to deficient enzyme activity and subsequent accumulation of sulfatides", True, "review",
     "Arylsulfatase A deficiency makes sulfatides accumulate, damaging myelin."),
    ("ARSA", "enzyme-deficiency", "PMID:40577679", "leading to deficient enzyme activity and subsequent accumulation of sulfatides", True, "review",
     "MLD is caused by variants that leave arylsulfatase A activity deficient."),
    ("ARSA", "storage", "PMID:25987178", "results in the accumulation of sulfatides in the central and peripheral nervous system", True, "review",
     "Independent review: sulfatide accumulation in central and peripheral nerves."),
    # GALC / Krabbe
    ("GALC", "storage", "PMID:27491217", "GALC-deficiency leads to psychosine accumulation", True, "review",
     "Galactocerebrosidase deficiency is thought to cause toxic psychosine accumulation."),
    ("GALC", "enzyme-deficiency", "PMID:27491217", "caused by a deficiency in the lysosomal enzyme galactocerebrosidase", True, "review",
     "Krabbe disease is caused by deficiency of the lysosomal enzyme galactocerebrosidase."),
]

# limiting / contradicting findings attached to the matching driven_by edge
COUNTER = [
    ("GBA1", "destabilization", "PMID:38797393", "begun to question its activity as a chaperone", "review",
     "Some data question whether ambroxol really acts as a chaperone for every GCase variant."),
    ("GLA", "destabilization", "PMID:30875019", "there was no significant difference between the migalastat and placebo groups", "clinical_trial",
     "In the trial population that included non-amenable variants, the chaperone did not beat placebo: misfolding rescue only works for amenable variants."),
    ("NPC1", "destabilization", "FDA:miplyffa", "by which arimoclomol exerts its clinical effects in patients with NPC is unknown", "database_record",
     "The FDA label states that the mechanism of arimoclomol in NPC is unknown, so its effect cannot be credited to correcting misfolding."),
]

# --------------------------------------------------------------------------- therapies
# evidence / counter: (ref, needle, study_type); node_notes: limitation quotes shown on the node
THERAPIES = [
    {"slug": "gaucher-enzyme-replacement", "label": "Enzyme replacement for Gaucher disease (imiglucerase, velaglucerase alfa, taliglucerase alfa)",
     "synonyms": ["imiglucerase", "Cerezyme", "velaglucerase alfa", "VPRIV", "taliglucerase alfa", "Elelyso", "ERT"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["GBA1"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous replacement of the missing glucocerebrosidase enzyme. Approved for the body (non-brain) "
                "manifestations of Gaucher disease; it does not treat the brain disease of types 2 and 3.",
     "evidence": [("FDA:cerezyme", "CEREZYME is indicated for the treatment of non-central nervous system (CNS) manifestations", "database_record"),
                  ("FDA:vpriv", "VPRIV is indicated for long-term enzyme replacement therapy", "database_record"),
                  ("FDA:elelyso", "ELELYSO is indicated for the treatment of patients 4 years of age and older", "database_record")],
     "node_notes": [("PMID:39116528", "neurological complications in GD2 and GD3 persist", "review")],
     "match": ["imiglucerase", "velaglucerase", "taliglucerase", "cerezyme", "vpriv", "elelyso"]},
    {"slug": "eliglustat", "label": "Eliglustat (substrate reduction)", "synonyms": ["Cerdelga", "Genz-112638"],
     "modality": "small_molecule", "approach": "substrate reduction (glucosylceramide synthase inhibitor)", "stage": "approved",
     "reaches_cns": False, "diseases": ["GBA1"], "targets": ["mech:lysosomal-storage"],
     "summary": "An oral drug that slows production of the lipid that builds up in Gaucher disease (substrate reduction).",
     "evidence": [("FDA:cerdelga", "CERDELGA is indicated for the long-term treatment of adult patients with Gaucher disease type 1", "database_record"),
                  ("PMID:25239269", "received its first global approval", "review")],
     "match": ["eliglustat", "cerdelga", "genz-112638"]},
    {"slug": "miglustat", "label": "Miglustat (substrate reduction; also an enzyme stabilizer)",
     "synonyms": ["Zavesca", "Opfolda", "N-butyl-deoxynojirimycin", "NB-DNJ"],
     "modality": "small_molecule", "approach": "substrate reduction (glucosylceramide synthase inhibitor); enzyme stabilizer with cipaglucosidase alfa",
     "stage": "approved", "reaches_cns": True, "diseases": ["GBA1", "NPC1", "GAA", "CLN3"], "targets": ["mech:lysosomal-storage"],
     "summary": "An oral iminosugar that slows glycosphingolipid production and crosses the blood-brain barrier. Approved "
                "for type 1 Gaucher disease and (outside the US) for the neurological manifestations of NPC; under the "
                "name Opfolda it is approved as a stabilizer of the enzyme cipaglucosidase alfa in Pompe disease, and it "
                "has been studied open-label in CLN3 disease.",
     "evidence": [("FDA:zavesca", "ZAVESCA is indicated as monotherapy for the treatment of adult patients with mild to moderate type 1 Gaucher disease", "database_record"),
                  ("PMID:24338084", "is the only disease-specific drug approved for the treatment of progressive neurological manifestations", "review"),
                  ("PMID:17689147", "Miglustat is able to cross the blood-brain barrier", "clinical_trial"),
                  ("FDA:opfolda", "OPFOLDA is an enzyme stabilizer indicated", "database_record"),
                  ("PMID:40924969", "associated with a slower rate of physical decline compared with historical controls", "clinical_trial")],
     "per_disease": {"GBA1": ["FDA:zavesca"], "NPC1": ["PMID:24338084", "PMID:17689147"], "GAA": ["FDA:opfolda"],
                     "CLN3": ["PMID:40924969"]},
     "disease_stage": {"CLN3": "clinical"},
     "match": ["miglustat", "zavesca", "opfolda", "at2221"]},
    {"slug": "pompe-enzyme-replacement", "label": "Enzyme replacement for Pompe disease (alglucosidase alfa, avalglucosidase alfa, cipaglucosidase alfa)",
     "synonyms": ["alglucosidase alfa", "Lumizyme", "Myozyme", "avalglucosidase alfa", "Nexviazyme", "cipaglucosidase alfa", "Pombiliti"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["GAA"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous replacement of acid alpha-glucosidase, the only disease-specific treatment class for Pompe disease.",
     "evidence": [("FDA:lumizyme", "LUMIZYME ® is a hydrolytic lysosomal glycogen-specific enzyme indicated for patients with Pompe disease (acid", "database_record"),
                  ("FDA:nexviazyme", "NEXVIAZYME is indicated for the treatment of patients 1 year of age and older", "database_record"),
                  ("FDA:pombiliti", "POMBILITI is indicated, in combination with Opfolda", "database_record"),
                  ("PMID:32962155", "The only disease-specific treatment available for Pompe disease patients", "review")],
     "match": ["alglucosidase", "avalglucosidase", "cipaglucosidase", "lumizyme", "myozyme", "nexviazyme", "pombiliti", "atb200", "neogaa", "gzgaa"]},
    {"slug": "fabry-enzyme-replacement", "label": "Enzyme replacement for Fabry disease (agalsidase beta, pegunigalsidase alfa)",
     "synonyms": ["agalsidase beta", "Fabrazyme", "pegunigalsidase alfa", "Elfabrio", "agalsidase alfa"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["GLA"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous replacement of alpha-galactosidase A for people with Fabry disease.",
     "evidence": [("FDA:fabrazyme", "FABRAZYME ® is indicated for the treatment of adult and pediatric patients 2 years of age and older", "database_record"),
                  ("FDA:elfabrio", "ELFABRIO is indicated for the treatment of adults with confirmed Fabry disease", "database_record")],
     "match": ["agalsidase", "pegunigalsidase", "fabrazyme", "replagal", "elfabrio", "prx-102"]},
    {"slug": "migalastat", "label": "Migalastat (pharmacological chaperone)", "synonyms": ["Galafold", "AT1001", "1-deoxygalactonojirimycin"],
     "modality": "chaperone", "approach": "pharmacological chaperone (oral)", "stage": "approved", "reaches_cns": None,
     "diseases": ["GLA"], "targets": ["mech:protein-destabilization"],
     "summary": "The first approved pharmacological chaperone: an oral small molecule that binds misfolded but 'amenable' "
                "alpha-galactosidase A variants, stabilizes them and lets them reach the lysosome. It only works for "
                "variants that pass an in-vitro amenability test.",
     "evidence": [("FDA:galafold", "reversibly binds to the active site of the alpha-galactosidase A", "database_record"),
                  ("FDA:galafold", "GALAFOLD is indicated for the treatment of adults with a confirmed diagnosis of Fabry disease and an amenable", "database_record"),
                  ("PMID:30875019", "is the first pharmacological chaperone approved", "review"),
                  ("PMID:27834756", "stabilises specific mutant (amenable) forms", "clinical_trial")],
     "node_notes": [("PMID:30875019", "there was no significant difference between the migalastat and placebo groups", "clinical_trial")],
     "match": ["migalastat", "galafold", "at1001"]},
    {"slug": "ambroxol", "label": "Ambroxol (repurposed pharmacological chaperone for glucocerebrosidase)", "synonyms": ["ambroxol hydrochloride"],
     "modality": "chaperone", "approach": "repurposed pharmacological chaperone (oral, crosses the blood-brain barrier)", "stage": "clinical",
     "reaches_cns": True, "diseases": ["GBA1"], "targets": ["mech:protein-destabilization"],
     "summary": "A cough medicine that also acts as a chaperone for misfolded glucocerebrosidase and crosses the blood-brain "
                "barrier; studied in neuronopathic Gaucher disease. Whether it acts as a chaperone for every variant is debated.",
     "evidence": [("PMID:39116528", "Ambroxol, a BBB-permeable chaperone, enhances GCase activity", "review"),
                  ("PMID:38797393", "Several compounds with chaperone activities against GCase have already been tested", "review")],
     "counter": [("PMID:38797393", "begun to question its activity as a chaperone", "review")],
     "match": ["ambroxol"]},
    {"slug": "pyrimethamine", "label": "Pyrimethamine (pharmacological chaperone for hexosaminidase A)", "synonyms": ["PMT"],
     "modality": "chaperone", "approach": "repurposed pharmacological chaperone (oral)", "stage": "clinical", "reaches_cns": None,
     "diseases": ["HEXA"], "targets": ["mech:protein-destabilization"],
     "summary": "An old antiparasitic drug that partly rescues misfolded hexosaminidase A; it raised enzyme activity in "
                "late-onset Tay-Sachs patients, but higher doses caused side effects.",
     "evidence": [("PMID:20926324", "pyrimethamine treatment enhances leukocyte Hex A activity", "clinical_trial"),
                  ("PMID:21185210", "PMT therapy can increase HexA activity in LOTS in vivo", "clinical_trial")],
     "counter": [("PMID:21185210", "Reversible decline in motor activity", "clinical_trial")],
     "match": ["pyrimethamine"]},
    {"slug": "arimoclomol", "label": "Arimoclomol (heat-shock response amplifier)", "synonyms": ["Miplyffa"],
     "modality": "small_molecule", "approach": "heat shock protein amplifier (oral), with miglustat", "stage": "approved",
     "reaches_cns": None, "diseases": ["NPC1"], "targets": ["mech:protein-destabilization"],
     "summary": "An oral drug that amplifies the cell's heat-shock (protein-folding) response. FDA-approved with miglustat "
                "for the neurological manifestations of NPC; the label says its mechanism in NPC is unknown.",
     "evidence": [("FDA:miplyffa", "MIPLYFFA is indicated for use in combination with miglustat for the treatment of neurological manifestations", "database_record"),
                  ("PMID:34418116", "amplifies the heat shock response to target NPC protein misfolding", "clinical_trial")],
     "counter": [("FDA:miplyffa", "by which arimoclomol exerts its clinical effects in patients with NPC is unknown", "database_record")],
     "match": ["arimoclomol", "miplyffa"]},
    {"slug": "levacetylleucine", "label": "Levacetylleucine (N-acetyl-L-leucine)", "synonyms": ["NALL", "N-acetyl-L-leucine", "IB1001", "Aqneursa"],
     "modality": "small_molecule", "approach": "oral modified amino acid", "stage": "clinical", "reaches_cns": None,
     "diseases": ["NPC1"], "targets": [],
     "summary": "An oral modified amino acid that improved ataxia scores versus placebo in a 12-week crossover trial in NPC; "
                "it is also being trialled in GM2 gangliosidoses.",
     "evidence": [("PMID:38294974", "treatment with NALL for 12 weeks led to better neurologic status than placebo", "clinical_trial")],
     "match": ["acetyl-l-leucine", "levacetylleucine", "ib1001", "nall"]},
    {"slug": "olipudase-alfa", "label": "Olipudase alfa (enzyme replacement for ASMD)", "synonyms": ["Xenpozyme", "rhASM"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["SMPD1"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous recombinant acid sphingomyelinase, approved only for the non-brain manifestations of ASMD.",
     "evidence": [("FDA:xenpozyme", "XENPOZYME is indicated for treatment of non", "database_record"),
                  ("PMID:35471153", "for non-central nervous system manifestations of acid sphingomyelinase deficiency", "clinical_trial")],
     "match": ["olipudase", "xenpozyme", "rhasm"]},
    {"slug": "laronidase", "label": "Laronidase (enzyme replacement for MPS I)", "synonyms": ["Aldurazyme"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["IDUA"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous recombinant alpha-L-iduronidase for MPS I. It does not cross the blood-brain barrier, so it is "
                "not expected to treat the brain disease of the severe (Hurler) form.",
     "evidence": [("PMID:17011223", "was approved as an enzyme replacement therapy for patients with the lysosomal storage disorder", "cohort")],
     "node_notes": [("PMID:15895714", "as laronidase does not cross the blood-brain barrier", "review")],
     "match": ["laronidase", "aldurazyme"]},
    {"slug": "idursulfase", "label": "Idursulfase (enzyme replacement for MPS II)", "synonyms": ["Elaprase"],
     "modality": "other", "approach": "enzyme replacement (intravenous)", "stage": "approved", "reaches_cns": False,
     "diseases": ["IDS"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Intravenous recombinant iduronate-2-sulfatase for Hunter syndrome (MPS II).",
     "evidence": [("FDA:elaprase", "ELAPRASE is indicated for patients with Hunter syndrome", "database_record")],
     "match": ["idursulfase", "elaprase"]},
    {"slug": "pabinafusp-alfa", "label": "Pabinafusp alfa (brain-penetrant enzyme replacement for MPS II)", "synonyms": ["JR-141", "Izcargo"],
     "modality": "other", "approach": "enzyme fused to an anti-transferrin-receptor antibody (crosses the blood-brain barrier)",
     "stage": "clinical", "reaches_cns": True, "diseases": ["IDS"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Iduronate-2-sulfatase fused to an antibody that ferries it across the blood-brain barrier via the "
                "transferrin receptor, aimed at the neurological form of MPS II.",
     "evidence": [("PMID:33038326", "crosses the blood-brain barrier by transcytosis via transferrin receptors", "clinical_trial")],
     "match": ["pabinafusp", "jr-141"]},
    {"slug": "cerliponase-alfa", "label": "Cerliponase alfa (intraventricular enzyme replacement for CLN2)", "synonyms": ["Brineura", "rhTPP1"],
     "modality": "other", "approach": "enzyme replacement infused directly into the brain ventricles", "stage": "approved",
     "reaches_cns": True, "diseases": ["TPP1"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Recombinant TPP1 delivered straight into the fluid spaces of the brain, bypassing the blood-brain barrier. "
                "It slows the loss of walking and language in CLN2 disease.",
     "evidence": [("FDA:brineura", "BRINEURA is indicated to slow the loss of ambulation in pediatric patients", "database_record"),
                  ("PMID:29688815", "resulted in less decline in motor and language function", "clinical_trial")],
     "counter": [("PMID:29688815", "Serious adverse events included failure of the intraventricular device", "clinical_trial")],
     "match": ["cerliponase", "brineura", "bmn 190", "bmn190"]},
    {"slug": "atidarsagene-autotemcel", "label": "Atidarsagene autotemcel (stem-cell gene therapy for MLD)",
     "synonyms": ["arsa-cel", "Libmeldy", "Lenmeldy", "OTL-200"],
     "modality": "gene_replacement", "approach": "autologous haematopoietic stem cells transduced with a lentiviral ARSA vector",
     "stage": "approved", "reaches_cns": True, "diseases": ["ARSA"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "The child's own blood stem cells are given a working ARSA gene and returned; their descendants supply the "
                "enzyme in the nervous system. Approved for pre-symptomatic and early-symptomatic early-onset MLD.",
     "evidence": [("FDA:lenmeldy", "LENMELDY is indicated for the treatment of children with pre-symptomatic late infantile", "database_record"),
                  ("PMID:36811406", "by the European Medicines Agency (EMA) in December 2020", "review"),
                  ("PMID:35065785", "treatment benefits were particularly apparent in patients treated before symptom onset", "clinical_trial")],
     "match": ["atidarsagene", "otl-200", "arsa-cel", "libmeldy", "lenmeldy"]},
    {"slug": "hsct-krabbe", "label": "Haematopoietic stem cell transplantation (early, for Krabbe disease)",
     "synonyms": ["HSCT", "umbilical cord blood transplantation"],
     "modality": "other", "approach": "cell transplantation (donor cells supply the enzyme)", "stage": "clinical",
     "reaches_cns": True, "diseases": ["GALC"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "Donor blood stem cells that supply galactocerebrosidase. The only disease-modifying option for Krabbe "
                "disease, and only effective when done very early.",
     "evidence": [("PMID:27638597", "The only disease-modifying treatment currently available is hematopoietic stem cell transplantation", "review")],
     "match": ["hematopoietic stem cell transplant", "cord blood", "hsct"]},
    {"slug": "aav-hexa-hexb-gene-therapy", "label": "Intrathecal AAVrh8-HEXA/HEXB gene therapy (Tay-Sachs)",
     "synonyms": ["AXO-AAV-GM2", "AAVrh8-HEXA/HEXB"],
     "modality": "gene_replacement", "approach": "AAV gene transfer into the cerebrospinal fluid", "stage": "clinical",
     "reaches_cns": True, "diseases": ["HEXA"], "targets": ["mech:lysosomal-enzyme-deficiency"],
     "summary": "AAV vectors carrying working HEXA and HEXB genes given into the spinal fluid; first tested in two children "
                "with infantile Tay-Sachs disease under expanded access.",
     "evidence": [("PMID:35145305", "expanded-access trial in two patients with infantile TSD", "case_series")],
     "match": ["axo-aav-gm2", "aavrh8", "hexa/hexb"]},
]

# cross-family bridge: SNAREopathy-layer evidence for the SLC6A1 side (stored in this family's pubmed dir)
SLC6A1_BRIDGE = [("PMID:34028503", "variant protein misfolding, endoplasmic reticulum retention, and subsequent degradation", True, "functional_study"),
                 ("PMID:42157447", "PBA restored GABA uptake and GAT-1 surface expression across all variants", True, "functional_study")]
SLC6A1_BRIDGE_COUNTER = [("PMID:38781976", "GAT-1 was on the surface but with reduced activity for the remaining third", False, "functional_study")]


def all_refs():
    refs = {FAMILY_REF[0], BBB_REVIEW_REF[0], BBB_ERT_REF[0]}
    refs |= {c[2] for c in CLAIMS} | {c[2] for c in COUNTER}
    for t in THERAPIES:
        for e in t["evidence"] + t.get("counter", []) + t.get("node_notes", []):
            refs.add(e[0])
    refs |= {e[0] for e in SLC6A1_BRIDGE + SLC6A1_BRIDGE_COUNTER}
    return refs


if __name__ == "__main__":
    import lyso_common as L
    bad = 0
    items = [FAMILY_REF, FAMILY_STORAGE_REF, FAMILY_PROTEINS_REF, FAMILY_THERAPY_REF, BBB_REVIEW_REF, BBB_ERT_REF]
    items += [(c[2], c[3]) for c in CLAIMS + COUNTER]
    for t in THERAPIES:
        items += [(e[0], e[1]) for e in t["evidence"] + t.get("counter", []) + t.get("node_notes", [])]
    items += [(e[0], e[1]) for e in SLC6A1_BRIDGE + SLC6A1_BRIDGE_COUNTER]
    for ref, needle in items:
        try:
            q = L.quote_for(ref, needle)
            print(f"  OK  {ref:16s} {q[:110]}")
        except Exception as ex:  # noqa: BLE001
            bad += 1
            print(f"  BAD {ref:16s} {ex}")
    print(f"unresolved needles: {bad} of {len(items)}")
