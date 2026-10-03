"""Disease -> effect-mechanism claims (needles only; quotes are resolved from stored sources).
Tuple: (gene, mech_slug, ref, needle, supports, study_type)
supports: True = supports; False = limits/contradicts; "minority" = a minority mechanism.
"""
DISEASE_MECHANISM_CLAIMS = [
    ("SCN1A", "loss-of-function", "PMID:16921370", "Heterozygous loss-of-function mutations in Na(V)1.1", True, "animal_model"),
    ("SCN1A", "loss-of-function", "PMID:35696452", "loss-of-function variants cause the severe epilepsy Dravet syndrome", True, "cohort"),
    ("SCN1A", "haploinsufficiency", "PMID:32848094", "resulting in haploinsufficiency of the voltage-gated sodium channel", True, "animal_model"),
    ("SCN1A", "gain-of-function", "PMID:35696452", "cluster in regions of channel inactivation associated with gain of function", "minority", "cohort"),
    ("SCN1A", "gain-of-function", "PMID:36636894", "showed a gain of channel function", "minority", "case_series"),
    ("SCN2A", "gain-of-function", "PMID:28379373", "result in increased sodium channel activity with gain-of-function", True, "cohort"),
    ("SCN2A", "gain-of-function", "PMID:34850743", "Biophysical gain of function in SCN2A is seen", True, "animal_model"),
    ("SCN2A", "loss-of-function", "PMID:28379373", "were associated with loss-of-function effects", True, "cohort"),
    ("SCN2A", "loss-of-function", "PMID:41642117", "SCN2A loss-of-function (LoF) variants are associated with epilepsy", True, "cohort"),
    ("SCN8A", "gain-of-function", "PMID:31943325", "caused by de novo gain-of-function mutations of sodium channel", True, "animal_model"),
    ("SCN8A", "gain-of-function", "PMID:34431999", "showed a strong gain-of-function", True, "cohort"),
    ("SCN8A", "loss-of-function", "PMID:34431999", "all three variants causing generalized epilepsy induced a loss-of-function", True, "cohort"),
    ("SCN8A", "loss-of-function", "PMID:25725044", "heterozygous loss-of-function mutations cause intellectual disability", True, "case_series"),
]
DISEASE_MECHANISM_CLAIMS += [
    ("KCNQ2", "dominant-negative", "PMID:24318194", "exhibited a drastic dominant-negative effect", True, "functional_study"),
    ("KCNQ2", "loss-of-function", "PMID:42610455", "loss-of-function (LOF) variants known to be associated with", True, "cohort"),
    ("KCNQ2", "gain-of-function", "PMID:25740509", "thereby producing gain-of-function effects", "minority", "functional_study"),
    ("KCNQ2", "gain-of-function", "PMID:28139826", "R201H gain-of-function variants present with profound neonatal encephalopathy", "minority", "case_series"),
    ("KCNT1", "gain-of-function", "PMID:23086397", "identified de novo gain-of-function mutations", True, "case_series"),
    ("KCNT1", "gain-of-function", "PMID:26369628", "Both mutations manifested gain of function in vitro", True, "case_report"),
    ("CACNA1A", "loss-of-function", "PMID:31468518", "mutations result in loss-of-function effects", True, "functional_study"),
    ("CACNA1A", "gain-of-function", "PMID:31468518", "variants resulted in gain-of-function effects", True, "functional_study"),
    ("GRIN2B", "gain-of-function", "PMID:28533163", "De novo gain of function mutations in GRIN2B", True, "functional_study"),
    ("GRIN2B", "gain-of-function", "PMID:28377535", "revealing various potential gain-of-function and loss-of-function mechanisms", True, "case_series"),
    ("GRIN2B", "loss-of-function", "PMID:31213567", "clinical improvement of loss-of-function GRIN2B-related pediatric encephalopathy", True, "case_report"),
    ("GRIN2B", "loss-of-function", "PMID:28377535", "revealing various potential gain-of-function and loss-of-function mechanisms", True, "case_series"),
    ("CDKL5", "loss-of-function", "PMID:35997111", "result in loss of CDKL5 catalytic activity", True, "review"),
    ("SYNGAP1", "haploinsufficiency", "PMID:23161826", "a specific form of epilepsy by inducing haploinsufficiency", True, "functional_study"),
    ("SYNGAP1", "loss-of-function", "PMID:23161826", "result in a loss of its function", True, "functional_study"),
    ("SLC2A1", "haploinsufficiency", "PMID:9462754", "caused by haploinsufficiency of the blood-brain barrier hexose carrier", True, "case_series"),
    ("SLC2A1", "haploinsufficiency", "PMID:9462754", "hemizygosity of GLUT1 and nonsense mutations", True, "case_series"),
]

# gene -> (ref, needle) of a discovery / key gene-disease publication for the `causes` edge
DISCOVERY = {
    "SCN1A": ("PMID:11359211", "De novo mutations in the sodium-channel gene SCN1A cause"),
    "SCN2A": ("PMID:28379373", "Genetic and phenotypic heterogeneity suggest therapeutic implications"),
    "SCN8A": ("PMID:25725044", "De novo gain-of-function and loss-of-function mutations of SCN8A in patients"),
    "KCNQ2": ("PMID:24318194", "Dominant-negative effects of KCNQ2 mutations are associated with epileptic encephalopathy"),
    "KCNT1": ("PMID:23086397", "De novo gain-of-function KCNT1 channel mutations cause malignant migrating"),
    "CACNA1A": ("PMID:31468518", "Both gain-of-function and loss-of-function de novo CACNA1A mutations cause"),
    "GRIN2B": ("PMID:28377535", "GRIN2B encephalopathy: novel findings on phenotype"),
    "CDKL5": ("PMID:15492925", "Mutations of CDKL5 cause a severe neurodevelopmental disorder"),
    "SYNGAP1": ("PMID:19196676", "We identified de novo truncating mutations"),
    "SLC2A1": ("PMID:9462754", "GLUT-1 deficiency syndrome caused by haploinsufficiency"),
}

# literature-defined missense subgroups (ClinVar cannot split missense by function)
VARIANT_SUBGROUPS = [
    {"gene": "SCN2A", "slug": "missense-gof", "label": "SCN2A: gain-of-function missense (early-onset)", "mech": "gain-of-function",
     "examples": ["R1882Q"], "evidence": [("PMID:38148154", "GoF R1882Q and LoF R853Q"), ("PMID:28379373", "result in increased sodium channel activity with gain-of-function")]},
    {"gene": "SCN2A", "slug": "missense-lof", "label": "SCN2A: loss-of-function missense (later onset / autism)", "mech": "loss-of-function",
     "examples": ["R853Q"], "evidence": [("PMID:38148154", "GoF R1882Q and LoF R853Q"), ("PMID:28379373", "were associated with loss-of-function effects")]},
    {"gene": "SCN8A", "slug": "missense-gof", "label": "SCN8A: gain-of-function missense (DEE, focal epilepsy)", "mech": "gain-of-function",
     "examples": ["R1872W"], "evidence": [("PMID:30615093", "the R1872W mutation causing severe epilepsy induced clear gain-of-function"), ("PMID:34431999", "showed a strong gain-of-function")]},
    {"gene": "SCN8A", "slug": "missense-lof", "label": "SCN8A: loss-of-function missense (generalized epilepsy / ID)", "mech": "loss-of-function",
     "examples": [], "evidence": [("PMID:34431999", "all three variants causing generalized epilepsy induced a loss-of-function")]},
    {"gene": "SCN1A", "slug": "missense-gof", "label": "SCN1A: gain-of-function missense (non-Dravet early-onset)", "mech": "gain-of-function",
     "examples": [], "evidence": [("PMID:35696452", "cluster in regions of channel inactivation associated with gain of function")]},
    {"gene": "KCNQ2", "slug": "missense-gof", "label": "KCNQ2: gain-of-function missense (R201C/R201H)", "mech": "gain-of-function",
     "examples": ["R201C", "R201H"], "evidence": [("PMID:28139826", "R201H gain-of-function variants present with profound neonatal encephalopathy")]},
    {"gene": "KCNQ2", "slug": "missense-lof", "label": "KCNQ2: dominant-negative / loss-of-function missense", "mech": "dominant-negative",
     "examples": [], "evidence": [("PMID:24318194", "exhibited a drastic dominant-negative effect")]},
    {"gene": "CACNA1A", "slug": "missense-gof", "label": "CACNA1A: gain-of-function missense (DEE)", "mech": "gain-of-function",
     "examples": ["A713T", "V1396M"], "evidence": [("PMID:31468518", "variants resulted in gain-of-function effects")]},
    {"gene": "CACNA1A", "slug": "missense-lof", "label": "CACNA1A: loss-of-function missense (DEE)", "mech": "loss-of-function",
     "examples": ["G230V", "I1357S"], "evidence": [("PMID:31468518", "mutations result in loss-of-function effects")]},
    {"gene": "GRIN2B", "slug": "missense-lof", "label": "GRIN2B: loss-of-function missense", "mech": "loss-of-function",
     "examples": ["P553T"], "evidence": [("PMID:31213567", "clinical improvement of loss-of-function GRIN2B-related pediatric encephalopathy")]},
    {"gene": "GRIN2B", "slug": "missense-gof", "label": "GRIN2B: gain-of-function missense", "mech": "gain-of-function",
     "examples": [], "evidence": [("PMID:28533163", "De novo gain of function mutations in GRIN2B")]},
]
