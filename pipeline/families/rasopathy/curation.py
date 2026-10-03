"""Curated claims for the RASopathy family. NO hand-typed quote is ever emitted.

Each claim stores a `needle`; quote_for() resolves it against the LOCALLY STORED source:
  PMID:<id>   -> data/raw/families/rasopathy/pubmed/<id>.json (title + abstract): the full sentence
                 containing the needle is returned (needle missing or ambiguous -> ValueError)
  NCT<id>     -> clinicaltrials/<NCT>.json (all protocolSection text): the needle itself, which must
                 be a substring of the record
  FDA:<drug>  -> fda/<drug>.label.json (indications_and_usage): the needle, must be a substring
  WEB:<id>    -> web/<id>.txt (fetch_web.py): the needle, must be a substring of the stored page
verify.py later re-checks every emitted quote independently.

Run:  python3 pipeline/families/rasopathy/curation.py     # resolve and print every claim
"""
from __future__ import annotations

import json
import re

from ras_common import RAW, norm, read_json

PM, CT, FDA, WEB = RAW / "pubmed", RAW / "clinicaltrials", RAW / "fda", RAW / "web"
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“])")


def _flat(o):
    if isinstance(o, str):
        return [o]
    if isinstance(o, dict):
        return [x for v in o.values() for x in _flat(v)]
    if isinstance(o, list):
        return [x for v in o for x in _flat(v)]
    return []


def source_text(ref: str) -> str:
    if ref.startswith("PMID:"):
        r = read_json(PM / f"{ref[5:]}.json")
        return r["title"] + " " + r["abstract"]
    if ref.startswith("NCT"):
        return " ".join(_flat(read_json(CT / f"{ref}.json")["protocolSection"]))
    if ref.startswith("FDA:"):
        res = read_json(FDA / f"{ref[4:]}.label.json")["results"][0]
        return " ".join(res.get("indications_and_usage", []))
    if ref.startswith("WEB:"):
        return (WEB / f"{ref[4:]}.txt").read_text()
    raise ValueError(ref)


def quote_for(ref: str, needle: str) -> str:
    txt = source_text(ref)
    n = norm(needle)
    if not ref.startswith("PMID:"):
        if n not in norm(txt):
            raise ValueError(f"needle NOT FOUND in {ref}: {needle!r}")
        return needle
    sents = [s.strip() for s in _SENT.split(txt) if s.strip()]
    hits = [s for s in sents if n in norm(s)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"needle ambiguous in {ref}: {needle!r}")
    for i in range(len(sents) - 1):
        if n in norm(sents[i] + " " + sents[i + 1]):
            return sents[i] + " " + sents[i + 1]
    raise ValueError(f"needle NOT FOUND in {ref}: {needle!r}")


def meta_for(ref: str) -> dict:
    if ref.startswith("PMID:"):
        r = read_json(PM / f"{ref[5:]}.json")
        return {"title": r["title"], "year": r["year"], "journal": r["journal"], "pub_types": r["pub_types"],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{ref[5:]}/"}
    if ref.startswith("NCT"):
        ps = read_json(CT / f"{ref}.json")["protocolSection"]
        st = ps["statusModule"]
        return {"title": ps["identificationModule"]["briefTitle"], "status": st.get("overallStatus"),
                "why_stopped": st.get("whyStopped"),
                "year": int((st.get("startDateStruct", {}).get("date") or "0")[:4]) or None,
                "phases": ps.get("designModule", {}).get("phases"),
                "sponsor": ps["sponsorCollaboratorsModule"]["leadSponsor"]["name"],
                "url": f"https://clinicaltrials.gov/study/{ref}"}
    if ref.startswith("FDA:"):
        res = read_json(FDA / f"{ref[4:]}.label.json")["results"][0]
        brand = (res.get("openfda", {}).get("brand_name") or [None])[0]
        return {"title": f"FDA prescribing information{(' (' + brand + ')') if brand else ''}, "
                         f"DailyMed set id {res['set_id']}, effective {res.get('effective_time')}",
                "year": int(str(res.get("effective_time", "0"))[:4]) or None,
                "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={res['set_id']}"}
    if ref.startswith("WEB:"):
        man = read_json(WEB / "_manifest.json")[ref[4:]]
        return {"title": None, "url": man["url"], "retrieved": man["retrieved"]}
    raise ValueError(ref)


# ------------------------------------------------------------------------------------------
# disease -> effect mechanism (driven_by).  (gene, mech, ref, needle, supports, study_type, note, subtype)
#   supports True = supports this gene->mechanism edge; False = limits/contradicts it
# ------------------------------------------------------------------------------------------
MECH = [
    # PTPN11: three mechanisms in one gene
    ("PTPN11", "gain-of-function", "PMID:11704759", "This implies that they are gain-of-function changes", True,
     "case_series", "Discovery paper: Noonan-causing PTPN11 missense changes favour the active SHP-2 conformation.",
     "Noonan syndrome 1"),
    ("PTPN11", "gain-of-function", "PMID:16358218", "NS-causative mutations have less potency for promoting SHP-2 gain of function",
     True, "functional_study", "Noonan mutations are activating, but milder than leukemia-associated ones.",
     "Noonan syndrome 1"),
    ("PTPN11", "dominant-negative", "PMID:16377799", "LS mutants are catalytically defective and act as dominant negative mutations",
     True, "functional_study", "NSML (LEOPARD) mutants are catalytically defective and dominant negative, unlike Noonan mutants.",
     "Noonan syndrome with multiple lentigines (LEOPARD syndrome 1)"),
    ("PTPN11", "dominant-negative", "PMID:16358218", "engender loss of SHP-2 catalytic activity", True,
     "functional_study", "The recurrent NSML substitutions Y279C and T468M abolish catalytic activity.",
     "Noonan syndrome with multiple lentigines (LEOPARD syndrome 1)"),
    ("PTPN11", "dominant-negative", "PMID:21339643", "LS mutations have dominant-negative effects in vivo", True,
     "animal_model", "Knock-in Y279C mice: dominant-negative in vivo, with excess mTOR activity driving HCM.",
     "Noonan syndrome with multiple lentigines (LEOPARD syndrome 1)"),
    ("PTPN11", "dominant-negative", "PMID:24935154", "catalytically impaired SHP2 mutants could display gain-of-function properties",
     False, "functional_study", "Kinetic and structural work argues NSML mutants can still behave as gain of function in cells.",
     "Noonan syndrome with multiple lentigines (LEOPARD syndrome 1)"),
    ("PTPN11", "loss-of-function", "PMID:21533187", "heterozygous loss-of-function mutations in PTPN11 are a frequent cause of MC",
     True, "case_series", "Truncating and splice PTPN11 variants cause metachondromatosis, with a second hit in lesions.",
     "Metachondromatosis"),
    # SOS1
    ("SOS1", "gain-of-function", "PMID:17143285", "Noonan syndrome-associated SOS1 mutations are hypermorphs", True,
     "case_series", "SOS1 Noonan mutants enhance RAS and ERK activation.", "Noonan syndrome 4"),
    ("SOS1", "gain-of-function", "PMID:17143282", "implicate gain-of-function mutations in a RAS guanine nucleotide exchange factor",
     True, "case_series", "Independent discovery: SOS1 mutations relieve autoinhibition.", "Noonan syndrome 4"),
    # RAF1
    ("RAF1", "gain-of-function", "PMID:17603482", "implicate RAF1 gain-of-function mutations as a causative agent", True,
     "case_series", "RAF1 Noonan mutants increase kinase and ERK activity.", "Noonan syndrome 5"),
    ("RAF1", "gain-of-function", "PMID:17603483", "non-HCM-associated mutants were kinase impaired", True,
     "case_series", "HCM-hotspot RAF1 mutants are kinase-activating; non-HCM mutants are kinase impaired, so the "
     "gain-of-function label holds best for the HCM-associated alleles.", "Noonan syndrome 5"),
    ("RAF1", "gain-of-function", "PMID:21339642", "enhanced MEK-ERK activity is critical for causing HCM", True,
     "animal_model", "Raf1 L613V knock-in mice: enhanced MEK-ERK signalling drives HCM.", "Noonan syndrome 5"),
    # BRAF
    ("BRAF", "gain-of-function", "PMID:16439621", "suggest previously unknown mechanisms of B-Raf activation", True,
     "case_series", "CFC-causing BRAF missense changes activate B-Raf.", "Cardiofaciocutaneous syndrome 1"),
    ("BRAF", "gain-of-function", "PMID:16474404", "dysregulation of the RAS-RAF-ERK pathway is a common molecular basis",
     True, "case_series", "KRAS and BRAF mutations in CFC: one shared pathway with Noonan and Costello syndromes.",
     "Cardiofaciocutaneous syndrome 1"),
    # KRAS
    ("KRAS", "gain-of-function", "PMID:16474405", "impaired responsiveness to GTPase activating proteins", True,
     "functional_study", "KRAS Noonan mutants hydrolyse GTP poorly and escape GAP control: hyperactive Ras.",
     "Noonan syndrome 3"),
    # HRAS
    ("HRAS", "gain-of-function", "PMID:16170316", "previously reported as somatic and oncogenic mutations in various tumors",
     True, "case_series", "Costello syndrome HRAS changes are the same activating changes found in tumours.",
     "Costello syndrome"),
    # MAP2K1
    ("MAP2K1", "gain-of-function", "PMID:16439621", "missense mutations in either MEK1 or MEK2", True, "case_series",
     "MEK1/MEK2 missense changes cause CFC in BRAF-negative patients.", "Cardiofaciocutaneous syndrome 3"),
    ("MAP2K1", "gain-of-function", "PMID:17981815", "cannot induce ERK unless they are phosphorylated by RAF", False,
     "functional_study", "The CFC MEK1 variants still depend on RAF phosphorylation: they amplify rather than "
     "bypass upstream signalling.", "Cardiofaciocutaneous syndrome 3"),
    # SHOC2
    ("SHOC2", "gain-of-function", "PMID:19684605", "enhanced MAPK activation in a cell type-specific fashion", True,
     "functional_study", "SHOC2 S2G gains an N-myristoylation site, is mistargeted to the membrane and enhances MAPK "
     "signalling.", "Noonan syndrome-like disorder with loose anagen hair 1"),
    # RIT1
    ("RIT1", "gain-of-function", "PMID:23791108", "gain-of-function mutations in RIT1 cause Noonan syndrome", True,
     "case_series", "RIT1 Noonan mutants enhance ELK1 transactivation; 70% of carriers had HCM.", "Noonan syndrome 8"),
    # CBL: loss of RAS regulation
    ("CBL", "loss-of-function", "PMID:20619386", "affect CBL-mediated receptor ubiquitylation and dysregulate signal flow through RAS",
     True, "functional_study", "Germline CBL missense changes impair the E3 ligase that switches receptor signalling off.",
     "Noonan syndrome-like disorder with or without JMML"),
    ("CBL", "loss-of-function", "PMID:20694012", "JMML specimens from affected children show loss of the normal CBL allele",
     True, "case_series", "Leukaemia in carriers needs loss of the remaining normal allele (a second hit).",
     "Noonan syndrome-like disorder with or without JMML"),
    # NF1: loss of RAS regulation
    ("NF1", "loss-of-function", "PMID:35066574", "loss of NF1 results in increased RAS signaling", True, "review",
     "Neurofibromin is a RAS GTPase-activating protein; losing it leaves RAS switched on.", "Neurofibromatosis type 1"),
    ("NF1", "loss-of-function", "PMID:16271875", "caused by excessive p21Ras activity", True, "animal_model",
     "Nf1+/- mice: learning deficits come from excess Ras activity.", "Neurofibromatosis type 1"),
    # LZTR1: loss of RAS degradation, dominant and recessive forms
    ("LZTR1", "loss-of-function", "PMID:30442762", "Disease-associated LZTR1 mutations disrupted either LZTR1-CUL3 complex formation",
     True, "functional_study", "LZTR1 tags RAS for ubiquitination; disease mutations break this.", "Noonan syndrome 2 / 10"),
    ("LZTR1", "loss-of-function", "PMID:30442766", "Inactivation of LZTR1 led to decreased ubiquitination", True,
     "functional_study", "Independent screen: LZTR1 loss raises membrane KRAS and MAPK activity.", "Noonan syndrome 2 / 10"),
    ("LZTR1", "loss-of-function", "PMID:29469822", "identify biallelic mutations in LZTR1", True, "case_series",
     "Recessive Noonan syndrome from biallelic LZTR1 variants with unaffected carrier parents.", "Noonan syndrome 2 (recessive)"),
    ("LZTR1", "loss-of-function", "PMID:39140257", "The molecular spectrum mainly consisted of truncating variants, indicating loss-of-function",
     True, "cohort", "Heterozygous LZTR1 loss of function: isolated cafe-au-lait macules (and schwannomatosis).",
     "LZTR1-related schwannomatosis / isolated cafe-au-lait macules"),
    ("LZTR1", "loss-of-function", "PMID:30481304", "but not the missense changes occurring as biallelic mutations in recessive NS",
     True, "functional_study", "Dominant Noonan LZTR1 mutations leave the protein stable but hit the Kelch substrate-"
     "recognition surface and enhance RAS-MAPK signalling, unlike recessive missense changes.",
     "Noonan syndrome 10 (dominant)"),
]

# ------------------------------------------------------------------------------------------
# Family framing (cluster:rasopathy-family and the family shares_mechanism edges)
# ------------------------------------------------------------------------------------------
FAMILY = [
    ("PMID:19467855", "is caused by germline mutations in genes that encode protein components of the Ras/MAPK pathway"),
    ("PMID:19467855", "The vast majority of these mutations result in increased signal transduction"),
    ("PMID:23875798", "Because of the common underlying Ras/MAPK pathway dysregulation"),
    ("PMID:29924299", "so these syndromes have been gathered under the name RASopathies"),
    ("PMID:30311384", "Eleven genes were classified as definitively associated with at least one RASopathy condition"),
    ("PMID:38929714", "These variants functionally converge towards the overactivation of the pathway"),
]

# ------------------------------------------------------------------------------------------
# Therapies. evidence tuples: (ref, needle, supports, study_type, applies_to_genes or None)
# ------------------------------------------------------------------------------------------
THERAPIES = [
    {"slug": "selumetinib", "label": "Selumetinib (MEK1/2 inhibitor; Koselugo)",
     "synonyms": ["Koselugo", "AZD6244", "ARRY-142886"], "modality": "small_molecule", "stage": "approved",
     "summary": "An oral MEK1/2 inhibitor. FDA-approved for symptomatic, inoperable plexiform neurofibromas in "
                "neurofibromatosis type 1; the first approved drug that acts on the RAS/MAPK pathway in a RASopathy.",
     "targets": {"mapk-cascade": [("PMID:28029918", "an oral selective inhibitor of MAPK kinase (MEK) 1 and 2", True, "clinical_trial")]},
     "developed_for": {
         "NF1": {"level": "clinical", "approved": True,
                 "evidence": [("FDA:selumetinib", "KOSELUGO is indicated for the treatment of adult and pediatric patients 1 year of age and older with neurofibromatosis type 1 (NF1) who have symptomatic, inoperable plexiform neurofibromas (PN)", True, "database_record"),
                              ("PMID:32187457", "most children with neurofibromatosis type 1 and inoperable plexiform neurofibromas had durable tumor shrinkage", True, "clinical_trial"),
                              ("PMID:40473450", "selumetinib achieved a significant objective response rate versus placebo", True, "clinical_trial")],
                 "counter": [("PMID:40473450", "Change from baseline to cycle 12 in PlexiQoL total scores between treatment groups was not significant", False, "clinical_trial"),
                             ("PMID:32187457", "Five patients discontinued treatment because of toxic effects possibly related to selumetinib", False, "clinical_trial")]}}},
    {"slug": "mirdametinib", "label": "Mirdametinib (MEK1/2 inhibitor; Gomekli)",
     "synonyms": ["Gomekli", "PD-0325901"], "modality": "small_molecule", "stage": "approved",
     "summary": "An oral MEK inhibitor, FDA-approved for symptomatic plexiform neurofibromas in NF1 in adults and "
                "children 2 years and older; the second approved MEK inhibitor in the family.",
     "targets": {"mapk-cascade": [("NCT03962543", "MEK Inhibitor Mirdametinib (PD-0325901) in Patients With Neurofibromatosis Type 1", True, "clinical_trial")]},
     "developed_for": {
         "NF1": {"level": "clinical", "approved": True,
                 "evidence": [("FDA:mirdametinib", "GOMEKLI is indicated for the treatment of adult and pediatric patients 2 years of age and older with neurofibromatosis type 1 (NF1) who have symptomatic plexiform neurofibromas (PN) not amenable to complete resection", True, "database_record"),
                              ("PMID:39514826", "mirdametinib treatment demonstrated significant confirmed ORRs by BICR", True, "clinical_trial")],
                 "counter": []}}},
    {"slug": "trametinib", "label": "Trametinib (MEK1/2 inhibitor; Mekinist), off-label in RASopathies",
     "synonyms": ["Mekinist", "GSK1120212"], "modality": "repurposed_drug", "stage": "clinical",
     "summary": "A MEK inhibitor approved for BRAF-mutant cancers. Used off-label for life-threatening hypertrophic "
                "cardiomyopathy and lymphatic disease in Noonan syndrome and related RASopathies; a phase 2 "
                "randomised trial is recruiting and a phase 3 infant trial is registered.",
     "targets": {"mapk-cascade": [("PMID:35052347", "Trametinib, a MEK-inhibitor approved for treatment of RAS/MAPK-mutated cancers", True, "case_report")]},
     "node_sources": [("FDA:trametinib", "MEKINIST is a kinase inhibitor indicated as a single agent for the treatment of BRAF-inhibitor treatment-naïve patients with unresectable or metastatic melanoma with BRAF V600E or V600K mutations", True, "database_record")],
     "developed_for": {
         "RAF1": {"level": "observational",
                  "evidence": [("PMID:38827265", "We provide the first report of the successful treatment of an adult with RAF1-associated hypertrophic cardiomyopathy using trametinib", True, "case_report"),
                               ("PMID:35052347", "Trametinib was introduced (0.022 mg/kg/day) with prompt clinical improvement", True, "case_report"),
                               ("PMID:21339642", "postnatal MEK inhibition normalized the growth, facial, and cardiac defects", True, "animal_model")],
                  "counter": [("PMID:35052347", "it appears insufficient to revert pulmonary hypertension", False, "case_report")]},
         "RIT1": {"level": "observational",
                  "evidence": [("PMID:36184070", "She received off-label treatment with the MEK-inhibitor trametinib which resulted in complete remission of the cardiac hypertrophy", True, "case_report")],
                  "counter": []},
         "SOS1": {"level": "observational",
                  "evidence": [("PMID:33219052", "the patient initiated treatment by mitogen-activated protein kinase inhibition using trametinib", True, "case_report")],
                  "counter": []},
         "PTPN11": {"level": "clinical",
                    "evidence": [("NCT07817186", "Qualifying genotypes will included variants in any gene causing Noonan, Costello or cardiofaciocutaneous syndrome", True, "clinical_trial")],
                    "counter": [("NCT07817186", "PTPN11 pathogenic/likely pathogenic variants causing NSML", False, "clinical_trial")]},
         "LZTR1": {"level": "clinical",
                   "evidence": [("NCT07817186", "two alleles in trans for the autosomal recessive form of LZTR1-related Noonan syndrome", True, "clinical_trial")],
                   "counter": []}},
     "general": [("PMID:40131150", "provides evidence for decreased mortality and morbidity with improved cardiac status", True, "cohort"),
                 ("PMID:35605646", "Subjects demonstrated improvement in lymphatic leak", True, "case_series")],
     "general_counter": [("PMID:38929714", "dedicated clinical trials are required to establish standardized treatment protocols", False, "review"),
                         ("PMID:35605646", "Larger, prospective studies are needed to confirm efficacy and assess long-term safety", False, "case_series")]},
    {"slug": "binimetinib", "label": "Binimetinib (MEK162; MEK1/2 inhibitor)", "synonyms": ["MEK162", "ARRY-162"],
     "modality": "small_molecule", "stage": "clinical",
     "summary": "A MEK inhibitor tested in NF1 plexiform neurofibromas (phase 2, completed). The first MEK-inhibitor "
                "trial in Noonan syndrome hypertrophic cardiomyopathy (2012) was withdrawn before enrolling.",
     "targets": {"mapk-cascade": [("NCT01556568", "the ability of MEK162 to antagonize MEK activation in NS HCM patients", True, "clinical_trial")]},
     "developed_for": {
         "NF1": {"level": "clinical",
                 "evidence": [("NCT03231306", "Phase II Study of Binimetinib in Children and Adults With NF1 Plexiform Neurofibromas", True, "clinical_trial")],
                 "counter": []}}},
    {"slug": "rapamycin-nsml", "label": "Rapamycin (sirolimus) for NSML-associated hypertrophic cardiomyopathy",
     "synonyms": ["sirolimus", "mTOR inhibitor"], "modality": "repurposed_drug", "stage": "preclinical",
     "summary": "An approved mTOR inhibitor that reversed hypertrophic cardiomyopathy in mice carrying NSML-type "
                "(catalytically impaired) PTPN11 mutations. Human heart tissue data advise caution. This is the "
                "opposite branch to MEK inhibition: NSML variants are excluded from the infant MEK-inhibitor trial.",
     "targets": {"tor-signaling": [("PMID:21339643", "The cardiac defects in LS/+ mice were completely reversed by treatment with rapamycin, an inhibitor of mTOR", True, "animal_model")]},
     "developed_for": {
         "PTPN11": {"level": "experimental",
                    "evidence": [("PMID:21339643", "suggest that TOR inhibitors be considered for treatment of HCM in LS patients", True, "animal_model"),
                                 ("PMID:22058153", "rapamycin treatment started shortly after birth rescued the Q510E-Shp2-induced phenotype in vivo", True, "animal_model")],
                    "counter": [("PMID:31722741", "caution should be applied when using rapamycin to treat heart hypertrophy in LS", False, "case_series")]}}},
    {"slug": "statins-nf1-cognition", "label": "Statins (lovastatin, simvastatin) for RASopathy cognition",
     "synonyms": ["lovastatin", "simvastatin", "HMG-CoA reductase inhibitor"], "modality": "repurposed_drug",
     "stage": "clinical",
     "summary": "Cholesterol-lowering drugs that reduce RAS-MAPK activity and rescued learning in Nf1+/- mice. "
                "Randomised trials in children with NF1 did not improve cognition: a documented failure of "
                "pathway-level repurposing.",
     "targets": {"ras-protein-signal-transduction": [("PMID:16271875", "we identify lovastatin as a potent inhibitor of p21Ras/Mitogen Activated Protein Kinase (MAPK) activity in the brain", True, "animal_model")]},
     "developed_for": {
         "NF1": {"level": "clinical",
                 "evidence": [("PMID:16271875", "reversed their spatial learning and attention impairments", True, "animal_model")],
                 "counter": [("PMID:18632543", "simvastatin did not improve cognitive function in children with NF1", False, "clinical_trial"),
                             ("PMID:27956565", "is not recommended for amelioration of cognitive deficits in this population", False, "clinical_trial")]}}},
    {"slug": "tipifarnib", "label": "Tipifarnib (farnesyltransferase inhibitor)", "synonyms": ["R115777", "Zarnestra"],
     "modality": "small_molecule", "stage": "clinical",
     "summary": "Blocks RAS membrane anchoring by inhibiting farnesylation. A randomised placebo-controlled phase 2 trial "
                "in NF1 plexiform neurofibromas did not prolong time to progression: targeting RAS itself failed where "
                "targeting MEK later succeeded.",
     "targets": {"ras-protein-signal-transduction": [("PMID:24500418", "which blocks RAS signaling by inhibiting its farnesylation", True, "clinical_trial")]},
     "developed_for": {
         "NF1": {"level": "clinical",
                 "evidence": [("NCT00021541", "R115777 to Treat Children With Neurofibromatosis Type 1 and Progressive Plexiform Neurofibromas", True, "clinical_trial")],
                 "counter": [("PMID:24500418", "did not significantly prolong TTP of PNs compared with placebo", False, "clinical_trial")]}}},
]

# The MEK-inhibitor in-vitro evidence for CFC MEK1 variants (used on the MAP2K1 repurposing edge)
CFC_MEK = ("PMID:17981815", "All three mutants are sensitive to the MEK inhibitor U0126", True, "functional_study")
CFC_MEK_GENERAL = ("PMID:17981815", "regardless of mutations identified in an individual with CFC, MEK inhibition is a potential therapeutic approach",
                   True, "functional_study")

# ------------------------------------------------------------------------------------------
# Studies (ClinicalTrials.gov). genes: explicit {gene: needle} named in the record;
# syndromes: condition/eligibility syndromes mapped to umbrellas via ras_subtypes.SYNDROME_KEYS
# (inferred); tests: therapy slugs; kind: role in the atlas.
# ------------------------------------------------------------------------------------------
STUDIES = {
    "NCT01362803": {"genes": {"NF1": "Neurofibromatosis Type 1"}, "tests": ["selumetinib"], "kind": "mek_trial"},
    "NCT04924608": {"genes": {"NF1": "Efficacy and Safety of Selumetinib in Adults With NF1"}, "tests": ["selumetinib"], "kind": "mek_trial"},
    "NCT02407405": {"genes": {"NF1": "Neurofibromatosis 1 (NF1)"}, "tests": ["selumetinib"], "kind": "mek_trial"},
    "NCT03871257": {"genes": {"NF1": "Neurofibromatosis Type 1"}, "tests": ["selumetinib"], "kind": "mek_trial"},
    "NCT03962543": {"genes": {"NF1": "Neurofibromatosis Type 1 (NF1)"}, "tests": ["mirdametinib"], "kind": "mek_trial"},
    "NCT03231306": {"genes": {"NF1": "NF1 Plexiform Neurofibromas"}, "tests": ["binimetinib"], "kind": "mek_trial"},
    "NCT03741101": {"genes": {"NF1": "Treatment of NF1-related Plexiform Neurofibroma With Trametinib"}, "tests": ["trametinib"], "kind": "mek_trial"},
    "NCT06555237": {"syndromes": {"noonan": "patient with diagnosed RASopathy"}, "tests": ["trametinib"], "kind": "mek_trial"},
    "NCT07817186": {"genes": {"PTPN11": "PTPN11 pathogenic/likely pathogenic variants causing NSML",
                              "LZTR1": "two alleles in trans for the autosomal recessive form of LZTR1-related Noonan syndrome"},
                    "syndromes": {"noonan": "any gene causing Noonan, Costello or cardiofaciocutaneous syndrome",
                                  "costello": "any gene causing Noonan, Costello or cardiofaciocutaneous syndrome",
                                  "cfc": "any gene causing Noonan, Costello or cardiofaciocutaneous syndrome"},
                    "tests": ["trametinib"], "kind": "mek_trial",
                    "notes": {"PTPN11": "NSML-causing PTPN11 variants are explicitly excluded; Noonan-causing PTPN11 variants qualify."}},
    "NCT01556568": {"syndromes": {"noonan": "Noonan syndrome patients with confirmed cardiac hypertrophy"}, "tests": ["binimetinib"], "kind": "mek_trial"},
    "NCT00021541": {"genes": {"NF1": "Neurofibromatosis Type 1 and Progressive Plexiform Neurofibromas"}, "tests": ["tipifarnib"], "kind": "failed_trial"},
    "NCT00853580": {"genes": {"NF1": "Lovastatin in Children With Neurofibromatosis Type 1"}, "tests": ["statins-nf1-cognition"], "kind": "failed_trial"},
    "NCT03504501": {"genes": {"NF1": "Group 1: NS, Group 2: NF1 (both genetically assured)"},
                    "syndromes": {"noonan": "Group 1: NS, Group 2: NF1 (both genetically assured)"},
                    "tests": ["statins-nf1-cognition"], "kind": "failed_trial"},
    "NCT02713945": {"syndromes": {"noonan": "Genetically confirmed Noonan syndrome"}, "tests": ["statins-nf1-cognition"], "kind": "trial"},
    "NCT04888936": {"genes": {g: "These include but are not limited to: BRAF, CBL, HRAS, KRAS, LZTR1, MAP2K1, MAP2K2, MAP3K8, MRAS, NRAS, PPP1CB, PTPN11, RAF1, RASA1, RASA2, RIT1, RRAS, SHOC2, SOS1, SPRED1"
                              for g in ["BRAF", "CBL", "HRAS", "KRAS", "LZTR1", "MAP2K1", "PTPN11", "RAF1", "RIT1", "SHOC2", "SOS1"]},
                    "tests": [], "kind": "natural_history",
                    "notes": {"_all": "The NCI cohort explicitly excludes NF1 (\"excluding NF1\")."}},
    "NCT07344480": {"syndromes": {"rasopathy": "pathogenic or likely pathogenic variant in one of the RAS-MAPK pathway genes"},
                    "tests": [], "kind": "natural_history"},
    "NCT04395495": {"genes": {"NF1": "Neurofibromatosis 1"},
                    "syndromes": {"noonan": "Noonan Syndrome", "nsml": "Noonan Syndrome With Multiple Lentigines",
                                  "cfc": "Cardiofaciocutaneous Syndrome", "costello": "Costello Syndrome"},
                    "tests": [], "kind": "biorepository"},
    "NCT00924196": {"genes": {"NF1": "Natural History Study of Patients With Neurofibromatosis Type I"}, "tests": [], "kind": "natural_history"},
    "NCT01885767": {"genes": {"NF1": "Neurofibromatosis 1"}, "tests": [], "kind": "registry"},
    "NCT01410006": {"genes": {"NF1": "Neurofibromatosis Type 1 Patient Registry"}, "tests": [], "kind": "registry"},
}

# ------------------------------------------------------------------------------------------
# Patient organisations and assets (Website evidence, quotes must match the stored page)
# serves: gene -> list of (WEB ref, needle); "level"/"confidence" per mapping kind
# ------------------------------------------------------------------------------------------
RASNET_GENES = {
    "noonan": ("WEB:rasopathiesnet-syndromes", "Genes: BRAF, CBL, KRAS, LZTR1, MAP2K1 (MEK1), MRAS, NRAS, PTPN11, RAF1, RIT1, RRAS2, SOS1, SOS2, SPRED2"),
    "cfc": ("WEB:rasopathiesnet-syndromes", "Genes: BRAF, KRAS, MAP2K1 (MEK1), MAP2K2 (MEK2)"),
    "costello": ("WEB:rasopathiesnet-syndromes", "Costello syndrome (CS) 1:1.29 million (Abe, Aoki et al., 2012); 1:300,000 (Gripp et al., 2019) Gene: HRAS"),
    "nf1": ("WEB:rasopathiesnet-syndromes", "Neurofibromatosis Type 1 (NF1) 1:2,000 to 1:5,000 Gene: NF1"),
    "nsml": ("WEB:rasopathiesnet-syndromes", "Genes: PTPN11, RAF1, BRAF, MAP2K1 (MEK1)"),
    "shoc2": ("WEB:rasopathiesnet-syndromes", "Genes: SHOC2 (for NSLH1), PPP1CB (for NSLH2)"),
}
# genes covered by each RASNet gene list (read off the quoted list; checked in build.py)
RASNET_LIST_GENES = {"noonan": ["BRAF", "CBL", "KRAS", "LZTR1", "MAP2K1", "PTPN11", "RAF1", "RIT1", "SOS1"],
                     "cfc": ["BRAF", "KRAS", "MAP2K1"], "costello": ["HRAS"], "nf1": ["NF1"],
                     "nsml": ["PTPN11", "RAF1", "BRAF", "MAP2K1"], "shoc2": ["SHOC2"]}

ORGS = [
    {"id": "org:rasopathies-network", "label": "RASopathies Network (RASopathiesNet USA / UK)", "url": "https://rasopathiesnet.org/",
     "country": "US/UK", "scope": "all RASopathies",
     "evidence": [("WEB:rasopathiesnet-mission", "Our mission is to advance awareness and research toward improving the quality of life for individuals with RASopathies by bringing together clinicians, scientists, & families."),
                  ("WEB:rasopathiesnet-mission", "These conditions are associated with pathogenic mutations that increase RAS-RAF-MEK-ERK signaling.")],
     "serves_lists": ["noonan", "cfc", "costello", "nf1", "nsml", "shoc2"], "level": "observational", "confidence": 0.9},
    {"id": "org:noonan-syndrome-foundation", "label": "Noonan Syndrome Foundation (US)", "url": "https://www.teamnoonan.org/",
     "country": "US", "scope": "Noonan and Noonan-like syndromes",
     "evidence": [("WEB:teamnoonan-about", "Our mission is to support and empower individuals and families affected by Noonan and Noonan-like syndromes through education, advocacy, and facilitating research to advance knowledge and care.")],
     "serves_syndromes": ["noonan", "noonan_like"], "level": "observational", "confidence": 0.7},
    {"id": "org:noonan-syndrome-association-uk", "label": "Noonan Syndrome Association (UK)", "url": "https://www.noonansyndrome.org.uk/",
     "country": "UK", "scope": "Noonan syndrome",
     "evidence": [("WEB:noonan-uk-home", "We support families and individuals affected by NS with information, webinars with expert medical speakers, Families Day events, and involvement in research projects.")],
     "serves_syndromes": ["noonan"], "named_genes": {"PTPN11": ("WEB:noonan-uk-what", "The first gene to be discovered was the PTPN11 gene but it is now known that several genes can be involved.")},
     "level": "observational", "confidence": 0.7},
    {"id": "org:cfc-international", "label": "CFC International (Cardio Facio Cutaneous syndrome International)", "url": "https://cfcsyndrome.org/",
     "country": "US", "scope": "cardiofaciocutaneous syndrome",
     "evidence": [("WEB:cfcsyndrome-home", "27 years of supporting families and advancing research for CFC syndrome."),
                  ("WEB:cfcsyndrome-whatiscfc", "CFC syndrome is a rare genetic condition that typically affects the heart (cardio), facial features (facio) and skin (cutaneous).")],
     "serves_syndromes": ["cfc"], "level": "observational", "confidence": 0.75},
    {"id": "org:childrens-tumor-foundation", "label": "Children's Tumor Foundation (CTF)", "url": "https://www.ctf.org/",
     "country": "US", "scope": "neurofibromatosis (NF1) and schwannomatosis",
     "evidence": [("WEB:ctf-home", "The Children's Tumor Foundation is the drug discovery engine for neurofibromatosis - driving research, expanding knowledge, and advancing care for NF."),
                  ("WEB:ctf-home", "NF includes neurofibromatosis type 1 (NF1) and all types of schwannomatosis (SWN), including NF2-related schwannomatosis (NF2-SWN), formerly known as neurofibromatosis type 2, or NF2.")],
     "serves_syndromes": ["nf1"], "schwannomatosis": True, "level": "observational", "confidence": 0.9},
    {"id": "org:nf-network", "label": "Neurofibromatosis Network (NF Network)", "url": "https://nfnetwork.org/",
     "country": "US", "scope": "neurofibromatosis",
     "evidence": [("WEB:nfnetwork-home", "The Neurofibromatosis Network is the leading national organization advocating for federal funding for NF research and building and supporting NF communities.")],
     "serves_syndromes": ["nf1"], "level": "observational", "confidence": 0.8},
    {"id": "org:nerve-tumours-uk", "label": "Nerve Tumours UK", "url": "https://nervetumours.org.uk/", "country": "UK",
     "scope": "NF1, schwannomatosis, Legius syndrome",
     "evidence": [("WEB:nervetumours-home", "Nerve Tumours UK is the national charity providing support to people with conditions that cause nerve tumours, such as neurofibromatosis, Schwannomatosis and legius syndrome")],
     "serves_syndromes": ["nf1"], "schwannomatosis": True, "level": "observational", "confidence": 0.8},
]

ASSETS = [
    {"id": "asset:nf-registry-ctf", "label": "NF Registry (Children's Tumor Foundation, IAMRARE platform)", "kind": "registry",
     "url": "https://nfregistry.org/", "status": "recruiting",
     "evidence": [("WEB:nfregistry-home", "The NF Registry is an online registry for people with all types of NF, which includes neurofibromatosis type 1 (NF1), and all types of schwannomatosis (SWN), including NF2-related schwannomatosis (NF2-SWN).")],
     "covers": ["NF1"], "maintained_by": ["org:childrens-tumor-foundation"], "xrefs": {"NCT": "NCT01885767"},
     "maintainer_evidence": [("NCT01885767", "The Children's Tumor Foundation")]},
    {"id": "asset:cfc-citizen-registry", "label": "CITIZEN CFC Syndrome Registry (CFC International)", "kind": "registry",
     "url": "https://cfcsyndrome.org/ciitzen-registry", "status": "open",
     "evidence": [("WEB:cfcsyndrome-registry", "CFC International has partnered with CITIZEN to develop a centralized patient registry that not only provides vital information for researchers")],
     "covers_syndromes": ["cfc"], "maintained_by": ["org:cfc-international"]},
    {"id": "asset:rasopathies-network-contact-registry", "label": "RASopathies Network contact registry", "kind": "registry",
     "url": "https://rasopathiesnet.org/research/patient-registry-coming-soon/", "status": "being built",
     "evidence": [("WEB:rasopathiesnet-registry", "The RASopathies Network is building a contact registry to help advance RASopathies research.")],
     "covers_lists": ["noonan", "cfc", "costello", "nf1", "nsml", "shoc2"], "maintained_by": ["org:rasopathies-network"]},
    {"id": "asset:patras-registry-euras", "label": "PATRAS: PATient-based Registry for phenotyping and therapy evaluation in RASopathies (EURAS)",
     "kind": "registry", "url": "https://rasopathiesnet.org/research/research-studies-clinical-trials/", "status": "listed as recruiting by RASopathiesNet",
     "evidence": [("WEB:rasopathiesnet-studies", "The PATient-based Registry for phenotyping and therapy evaluation in RASopathies (PATRAS) is at the heart of EURAS")],
     "covers_syndromes": ["rasopathy"], "maintained_by": []},
]
RASNET_MEKINRAS = ("WEB:rasopathiesnet-studies", "Interventional phase 2 trial of MEK Inhibitors for the Treatment of Hypertrophic Cardiomyopathy in Patients With RASopathies (MEKinRAS)")


def all_claims():
    out = [(c[2], c[3]) for c in MECH] + list(FAMILY) + [(CFC_MEK[0], CFC_MEK[1]), (CFC_MEK_GENERAL[0], CFC_MEK_GENERAL[1]),
                                                       RASNET_MEKINRAS]
    for t in THERAPIES:
        for evs in t["targets"].values():
            out += [(e[0], e[1]) for e in evs]
        out += [(e[0], e[1]) for e in t.get("node_sources", []) + t.get("general", []) + t.get("general_counter", [])]
        for d in t["developed_for"].values():
            out += [(e[0], e[1]) for e in d["evidence"] + d["counter"]]
    for n, s in STUDIES.items():
        out += [(n, v) for v in s.get("genes", {}).values()] + [(n, v) for v in s.get("syndromes", {}).values()]
    out += list(RASNET_GENES.values())
    for o in ORGS:
        out += list(o["evidence"]) + list(o.get("named_genes", {}).values())
    for a in ASSETS:
        out += list(a["evidence"]) + list(a.get("maintainer_evidence", []))
    return out


def referenced_ids():
    pm, ct = set(), set()
    for ref, _ in all_claims():
        if ref.startswith("PMID:"):
            pm.add(ref[5:])
        elif ref.startswith("NCT"):
            ct.add(ref)
    ct |= set(STUDIES)
    return pm, ct


def main():
    bad = 0
    claims = all_claims()
    for ref, needle in claims:
        try:
            q = quote_for(ref, needle)
            print(f"  OK  {ref:24s} {q[:110]}")
        except Exception as ex:  # noqa: BLE001
            bad += 1
            print(f"  BAD {ref:24s} {ex}")
    print(f"\n{len(claims)} claims, unresolved: {bad}")



# ------------------------------------------------------------------------------------------
# Curated cross-member shares_mechanism edges: (a, b, label, [(ref, needle, supports, study_type)], basis)
# ------------------------------------------------------------------------------------------
SHARES = [
    ("NF1", "RAF1", "MEK-inhibitor-responsive MAPK overactivation",
     [("PMID:28029918", "which are characterized by elevated RAS-mitogen-activated protein kinase (MAPK) signaling", True, "clinical_trial"),
      ("PMID:21339642", "enhanced MEK-ERK activity is critical for causing HCM", True, "animal_model"),
      ("PMID:38827265", "RASopathies cause nonsarcomeric hypertrophic cardiomyopathy via dysregulated signaling through RAS and upregulated mitogen-activated protein kinase activity", True, "case_report"),
      ("PMID:35052347", "it appears insufficient to revert pulmonary hypertension", False, "case_report")],
     "mapk-overactivation; MEK inhibitor approved for NF1 tried for RAF1 HCM"),
    ("NF1", "RIT1", "MEK-inhibitor-responsive MAPK overactivation",
     [("PMID:28029918", "which are characterized by elevated RAS-mitogen-activated protein kinase (MAPK) signaling", True, "clinical_trial"),
      ("PMID:36184070", "Meanwhile, several approved agents targeting the same RAS/MAPK signaling pathway are used in cancer treatment", True, "case_report"),
      ("PMID:23791108", "show a similar biological effect to mutations in other RASopathy-related genes", True, "case_series")],
     "mapk-overactivation; MEK inhibitor approved for NF1 tried for RIT1 HCM"),
    ("NF1", "CBL", "Loss of RAS regulation (negative regulators lost)",
     [("PMID:35066574", "loss of NF1 results in increased RAS signaling", True, "review"),
      ("PMID:20694012", "resemble disorders that are caused by hyperactive Ras/Raf/MEK/ERK signaling and include neurofibromatosis type 1", True, "case_series"),
      ("PMID:20619386", "affect CBL-mediated receptor ubiquitylation and dysregulate signal flow through RAS", True, "functional_study")],
     "loss of a RAS off-switch (GAP / E3 ubiquitin ligase)"),
    ("NF1", "LZTR1", "Loss of RAS regulation (negative regulators lost)",
     [("PMID:35066574", "loss of NF1 results in increased RAS signaling", True, "review"),
      ("PMID:30442762", "LZTR1-mediated ubiquitination inhibited RAS signaling by attenuating its association with the membrane", True, "functional_study"),
      ("PMID:39140257", "Pathogenic LZTR1 variants cause schwannomatosis and dominant/recessive Noonan syndrome (NS)", True, "cohort")],
     "loss of a RAS off-switch (GAP / CUL3-LZTR1 ubiquitination)"),
]


def _shares_claims():
    return [(e[0], e[1]) for s in SHARES for e in s[3]]


_all_claims_base = all_claims


def all_claims():  # noqa: F811  (extend the base list with the shares_mechanism needles)
    return _all_claims_base() + _shares_claims()


if __name__ == "__main__":
    main()
