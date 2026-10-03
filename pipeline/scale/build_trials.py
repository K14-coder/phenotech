"""Match the cached ClinicalTrials.gov pool to the monogenic universe -> data/derived/scale/trials.json
(+ data/derived/scale/_trial_orgs.json, the trial-sourced patient-org candidates used by build_orgs.py).

Every study fetched by fetch_ctgov.py (any query) is matched against every disease, so a study can be
found through one query and credited to another disease, but only if the precision filter holds:

NAME rules (disease-level):
  name_in_conditions / name_in_keywords / name_in_title
    the disease name or a synonym, token-normalised (common.norm_text: case, punctuation, possessive 's,
    roman numerals after 'type'), appears as a whole phrase in one condition / keyword / the brief title.
    MeSH-style inverted strings ('Muscular Dystrophy, Duchenne') are also tried de-inverted.
  Names used: HPO/Orphanet name + MONDO label/synonyms from data/derived/global/index.json.
  Not used: abbreviations without a digit (CF, DS, SMA...), abbreviations < 4 chars, single-word names
  < 7 chars or equal to an HPO phenotype label (e.g. 'Obesity'), names shared by >1 distinct disease
  concept (unless it is the primary name of exactly one), 'susceptibility' names.
  Common-name guard: a disease with no Orphanet xref (not 'rare' per Orphanet) and > 300 name matches
  (e.g. 'Breast cancer') keeps none of its name matches.
GENE rules (gene-level, credited to every disease of that gene with via_gene):
  gene_in_conditions / gene_in_keywords / gene_in_title
    the HGNC symbol appears case-sensitively as a whole token. Excluded: symbols < 3 chars, symbols that
    are English words (/usr/share/dict/words) or common clinical/drug abbreviations (PAH, ACE, EPO, ...),
    drug-class uses ('<SYM> inhibitor', 'anti-<SYM>'), oncology studies unless one of the gene's own
    diseases is a cancer/tumour syndrome, and studies of common complex diseases (Alzheimer, diabetes,
    HIV, ...) unless that term is in one of the gene's own disease names.
"""
from __future__ import annotations

import collections
import gzip
import json
import re
import urllib.parse
from pathlib import Path

from common import DL, GLOBAL_INDEX, OUT, RAW, ascii_fold, deinvert, norm_text, read_json, today, write_json

DIR = RAW / "ctgov"
CTG = "https://clinicaltrials.gov/study/"
STATUS_RANK = {"RECRUITING": 0, "NOT_YET_RECRUITING": 1, "ENROLLING_BY_INVITATION": 2,
               "ACTIVE_NOT_RECRUITING": 3, "AVAILABLE": 4, "COMPLETED": 5}
ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION", "AVAILABLE"}

ONCO = re.compile(r"cancer|carcinoma|tumou?r|neoplas|leuka?emia|lymphoma|melanoma|sarcoma|glioma|blastoma|"
                  r"myeloma|malignan|metasta|oncolog|myelodysplast|myeloproliferat|nsclc|adenocarcinoma|"
                  r"polyposis|paraganglioma|pheochromocytoma|mesothelioma|seminoma|histiocytosis", re.I)
COMMON = ["alzheimer", "parkinson", "diabetes", "obesity", "hypertension", "coronary", "myocardial infarction",
          "heart failure", "stroke", "atrial fibrillation", "depress", "schizophren", "bipolar", "hiv", "hepatitis",
          "covid", "sars-cov", "influenza", "malaria", "tuberculosis", "asthma", "copd", "chronic kidney disease",
          "osteoarthritis", "rheumatoid", "psoriasis", "sepsis", "pain", "smoking", "alcohol", "opioid",
          "atherosclero", "dyslipid", "hypercholesterol", "cardiovascular", "infertility", "pregnan",
          "healthy", "autism", "migraine", "osteoporosis", "glaucoma", "macular degeneration",
          "chronic obstructive", "emphysema", "amyotrophic lateral sclerosis", "multiple sclerosis", "myasthenia gravis",
          "pulmonary fibrosis", "thrombosis", "bleeding", "iron deficiency", "anemia of", "kidney transplant"]
SYMBOL_STOP = set("""PAH APP ACE REN AGT CRP ALB EPO INS GH1 IGF1 PTH OXT AVP GCG TNF LEP AMH CGA NPPA NPPB MPO
PRL TPO CETP PCSK9 HMGCR NPC1L1 DPP4 ANGPTL3 APOC3 LPA APOE APOB MTOR VEGFA EGFR ERBB2 HLA CD4 CD8 CD19 CD20
TSH FSHB LHB CYP2D6 CYP2C19 CYP2C9 CYP3A5 VKORC1 SLCO1B1 TPMT NUDT15 DPYD UGT1A1 IL6 IL2 IL1B IL10 IFNG
TGFB1 MTHFR F2 F5 ESR1 AR PGR GNRH1 KISS1 ACTH POMC GHRH SST INSR GLP1R GIPR SLC5A2 AQP4 MOG PLP1 MBP
ABO RHD KEL FUT2 ADA ATM CAD SDS PDF NRL MAX ASL CBS GLA HEX TAT TTR PIGA ACAN TF VWF
GPI NHS IHH ATR DCC HBB MCC REST CAT CLOCK SMS PHB NOS CPS PKD POR ARC PDS IPS DMP FAP MSS CAP RNA DNA""".split())
# kept on purpose despite the stoplist above: none. TTR/GLA/VWF/ADA/CBS etc. are genuine but their symbols
# double as drug names or common abbreviations (tafamidis 'TTR' cardiomyopathy trials are still found by
# name: 'transthyretin amyloidosis'), so gene-symbol matching is skipped for them.

GENERIC_SINGLE = set("""obesity epilepsy deafness anemia anaemia asthma autism dementia hypertension diabetes
cataract cataracts glaucoma myopia infertility lymphoma leukemia ataxia dystonia neuropathy cardiomyopathy
microcephaly macrocephaly hydrocephalus scoliosis osteoporosis hypothyroidism hyperthyroidism neutropenia
thrombocytopenia cholestasis proteinuria hematuria ichthyosis albinism craniosynostosis polydactyly syndactyly
nephropathy myopathy retinopathy encephalopathy leukodystrophy dwarfism hypogonadism hypoparathyroidism
infection arrhythmia thrombophilia hemophilia coloboma anophthalmia microphthalmia nystagmus strabismus
achromatopsia amyloidosis lipodystrophy porphyria hyperinsulinism hypoglycemia hyperammonemia hypercalcemia
hypocalcemia hypokalemia hyperkalemia hypophosphatemia hyperphosphatemia osteopetrosis neurodegeneration""".split())
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*")


def load_studies() -> dict:
    studies = {}
    for p in sorted(DIR.glob("studies_*.jsonl.gz")):
        with gzip.open(p, "rt") as f:
            for line in f:
                s = json.loads(line)
                studies[s["nct"]] = s
    return studies


def load_queries() -> dict:
    out = {}
    for line in (DIR / "queries.jsonl").read_text().splitlines():
        r = json.loads(line)
        if "error" not in r:
            out[r["key"]] = r
    return out


def hpo_labels() -> set:
    labels = set()
    for line in (DL / "hp.obo").read_text().splitlines():
        if line.startswith("name: "):
            labels.add(norm_text(line[6:]))
        elif line.startswith("synonym: \"") and "EXACT" in line:
            labels.add(norm_text(line.split('"')[1]))
    return labels


def is_abbrev(s: str) -> bool:
    return " " not in s.strip() and len(s) <= 10 and sum(c.isupper() or c.isdigit() for c in s) >= 0.6 * len(s)


PRIMARY_KEYS: set = set()
QUALIFIERS = set("""severe classic classical atypical juvenile infantile adult familial congenital hereditary autosomal
x-linked early late the with and of in for type patients children mild typical nonclassic non-classic""".split())


def build_name_index(universe: dict, idx_rare: dict, hpo: set):
    """key (normalised phrase) -> set(disease ids); plus rejected names with reasons (for the README)."""
    ds = universe["diseases"]
    key_to = collections.defaultdict(set)
    primary_of = collections.defaultdict(set)
    rejected = collections.Counter()
    for did, d in ds.items():
        names = [d["name"]] + d.get("synonyms", [])
        cands = []
        for i, n in enumerate(names):
            cands.append((n, i == 0))
            cands += [(x, False) for x in deinvert(n)]
        for n, primary in cands:
            if not n or "susceptibility" in n.lower() or "{" in n:
                rejected["susceptibility/curly"] += 1
                continue
            nn = norm_text(n)
            if is_abbrev(n):
                if not (re.search(r"\d", n) and len(n) >= 4 and sum(c.isalpha() for c in n) >= 2):
                    rejected["abbreviation"] += 1
                    continue
                if n in universe["genes"]:
                    rejected["abbreviation=gene symbol"] += 1
                    continue
            toks = nn.split()
            if len(nn) < 5:
                rejected["too short"] += 1
                continue
            if len(toks) == 1 and (len(nn) < 7 or nn in GENERIC_SINGLE or (nn in hpo and not (primary and len(nn) >= 9))):
                rejected["single generic word"] += 1
                continue
            pn = norm_text(d["name"])
            if not primary and nn != pn and f" {nn} " in f" {pn} ":
                rejected["synonym is a sub-phrase of the primary name"] += 1
                continue
            key_to[nn].add(did)
            if primary:
                primary_of[nn].add(did)
    # concept = MONDO id if mapped else native id
    concept = {did: (d.get("mondo") or did) for did, d in ds.items()}
    final = {}
    for k, dids in key_to.items():
        concepts = {concept[x] for x in dids}
        if len(concepts) == 1:
            final[k] = dids
        else:
            prim = primary_of.get(k, set())
            pc = {concept[x] for x in prim}
            if len(pc) == 1:
                final[k] = {x for x in dids if concept[x] in pc}
            else:
                rejected["ambiguous across concepts"] += 1
    PRIMARY_KEYS.clear()
    PRIMARY_KEYS.update(primary_of)
    by_first = collections.defaultdict(set)
    for k in final:
        toks = k.split()
        by_first[toks[0]].add(len(toks))
    return final, by_first, rejected


def find_names(text: str, index: dict, by_first: dict, original: str | None = None) -> set:
    """Whole-phrase matches of name keys in normalised `text`. Longest span wins (a key strictly inside a longer
    matched key is dropped: 'refsum disease' inside 'infantile refsum disease'). With `original`, a phrase whose
    every occurrence is hyphen-glued to a preceding word ('Crigler-Najjar' -> not 'Najjar syndrome') or followed
    by a gene context ('Ataxia Telangiectasia Mutated', '... gene') is dropped."""
    toks = text.split()
    spans = []
    for i, t in enumerate(toks):
        lens = by_first.get(t)
        if not lens:
            continue
        for L in lens:
            if i + L <= len(toks):
                k = " ".join(toks[i:i + L])
                if k in index:
                    spans.append((i, i + L, k))
    keep = set()
    for a, b, k in spans:
        if any((a2 <= a and b <= b2) and (b2 - a2) > (b - a) for a2, b2, _ in spans):
            continue
        keep.add(k)
    if original and keep:
        o = ascii_fold(original)
        for k in list(keep):
            pat = re.compile(r"[\s\-'’,.]*".join(re.escape(t) for t in k.split()), re.I)
            occ = list(pat.finditer(o))
            if not occ:
                continue
            ok = False
            for m in occ:
                before = o[max(0, m.start() - 1):m.start()]
                after = o[m.end():m.end() + 14].lower()
                if before == "-" or (before and before.isalnum()):
                    continue
                if re.match(r"^[\s\-]*(mutated|gene\b|genes\b|mutation|carrier|variant|and rad3|protein|kinase|inhibit)", after):
                    continue
                if k not in PRIMARY_KEYS and len(k.split()) == 2 and k.split()[1] in ("syndrome", "disease"):
                    prev = re.findall(r"([A-Za-z][\w']*)[\s]+$", o[:m.start()])
                    if prev and prev[-1][:1].isupper() and prev[-1].lower() not in QUALIFIERS:
                        continue   # eponym synonym inside a multi-eponym name ('Crigler Najjar Syndrome')
                ok = True
                break
            if not ok:
                keep.discard(k)
    return keep


GENE_CTX = re.compile(r"^(gene|genes|mutation|mutations|mutated|variant|variants|pathogenic|germline|related|"
                      r"associated|deficiency|deficient|syndrome|disorder|disorders|encephalopathy|disease|carrier|"
                      r"carriers|gof|lof|haploinsufficiency|biallelic|heterozygous|homozygous|mosaic|alteration|"
                      r"alterations|positive|negative|linked|dee|epilepsy|ndd|patients|individuals|children|"
                      r"loss|gain|function|defect|defects|deletion|duplication|spectrum|dystrophy|myopathy|"
                      r"cardiomyopathy|retinopathy|neuropathy|ataxia|dependent)$", re.I)
NON_GENE_CTX = re.compile(r"inhibit|antagon|agonist|antibod|blocker|modulator|polymorphism|\bsnps?\b|\brs\d+|"
                          r"level|levels|expression|serum|plasma|biomarker|staining|immunohisto|vaccine", re.I)


def acronym_defined(sym: str, texts: list[str]) -> bool:
    """True if the study spells out `sym` as the initials of a phrase (Helping Babies Breathe -> HBB)."""
    letters = [c.lower() for c in sym if c.isalpha()]
    if len(letters) < 3 or len(letters) != len([c for c in sym if not c.isdigit()]):
        return False
    for t in texts:
        words = re.findall(r"[A-Za-z][A-Za-z']*", t)
        for i in range(len(words) - len(letters) + 1):
            if [w[0].lower() for w in words[i:i + len(letters)]] == letters and \
                    sum(w[0].isupper() for w in words[i:i + len(letters)]) >= len(letters) - 1:
                return True
    return False


def gene_hits(text: str, genes: set, strict: bool = False, all_texts: list[str] | None = None) -> set:
    """Case-sensitive whole-token gene symbols in `text`. strict=True (trials) additionally requires a gene
    context: the field is the bare symbol (optionally + 'gene'), or a gene-context word (mutation, variant,
    related, deficiency, syndrome, ...) is within 3 words of the symbol; and rejects drug/biomarker/SNP contexts,
    drug codes (DCC-3116), 'anti-SYM', and symbols the study defines as an acronym of a phrase."""
    hits = set()
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        parts = {tok} | set(re.split(r"[-./]", tok))
        for p in parts:
            if p not in genes:
                continue
            if tok.lower().startswith("anti-") or re.search(re.escape(p) + r"-\d{2,}", tok):
                continue
            after = text[m.end():m.end() + 14].lower()
            before = text[max(0, m.start() - 5):m.start()].lower()
            if after.startswith((" inhibitor", "-inhibitor", "-inhibit", "i ", " antagonist", " agonist", " antibod")) \
                    or before.endswith(("anti-", "anti ")):
                continue
            if strict:
                if NON_GENE_CTX.search(text):
                    continue
                words = re.findall(r"[A-Za-z0-9']+", text)
                bare = re.fullmatch(r"\s*(the\s+)?" + re.escape(p) + r"(\s+gene)?\s*", text, re.I) is not None
                idxs = [i for i, w in enumerate(words) if w == p or p in re.split(r"[-./]", w)]
                near = any(GENE_CTX.match(w) for i in idxs for w in words[max(0, i - 3):i + 4] if w != p)
                if not (bare or near):
                    continue
                if all_texts and acronym_defined(p, all_texts):
                    continue
            hits.add(p)
    return hits


def main():
    universe = read_json(OUT / "universe.json")
    ds = universe["diseases"]
    gene_diseases = universe["genes"]

    # Orphanet 'rare' flag: ORPHA id itself, or its MONDO row carries an ORPHA xref
    idx = read_json(GLOBAL_INDEX, None)
    mondo_has_orpha = {}
    if idx:
        F = {k: i for i, k in enumerate(idx["f"])}
        for r in idx["rows"]:
            mondo_has_orpha[r[F["id"]]] = bool(r[F["orpha"]])
    rare = {did: did.startswith("ORPHA:") or mondo_has_orpha.get(d.get("mondo"), False) for did, d in ds.items()}

    hpo = hpo_labels()
    index, by_first, rejected = build_name_index(universe, rare, hpo)
    words = set(w.strip().lower() for w in Path("/usr/share/dict/words").read_text().splitlines())
    genes = {g for g in gene_diseases if len(g) >= 3 and g.lower() not in words and g not in SYMBOL_STOP
             and not g.startswith("HLA-")}
    gene_is_onco = {g: any(ONCO.search(ds[d]["name"]) for d in dids) for g, dids in gene_diseases.items()}
    gene_names_lc = {g: " ".join(ds[d]["name"].lower() for d in dids) for g, dids in gene_diseases.items()}
    print(f"name keys: {len(index)}; gene symbols usable: {len(genes)}/{len(gene_diseases)}; rejected: {dict(rejected)}")

    studies = load_studies()
    print(f"studies in pool: {len(studies)}")

    name_matches = collections.defaultdict(dict)   # did -> nct -> (rule, field_text)
    gene_matches = collections.defaultdict(dict)   # gene -> nct -> (rule, field_text)
    for nct, s in studies.items():
        fields = [("conditions", c) for c in s["conditions"]] + [("keywords", k) for k in s["keywords"]] + \
                 [("title", s["title"])]
        onco = any(ONCO.search(t) for f, t in fields if f in ("conditions", "title"))
        cond_lc = " ".join(s["conditions"] + [s["title"]]).lower()
        common_terms = [c for c in COMMON if c in cond_lc]
        for field, text in fields:
            variants = [text] + (deinvert(text) if field != "title" else [])
            for v in variants:
                for k in find_names(norm_text(v), index, by_first, original=v):
                    for did in index[k]:
                        name_matches[did].setdefault(nct, (f"name_in_{field}", text, k))
            for g in gene_hits(text, genes, strict=True, all_texts=[t for f, t in fields]):
                if onco:   # somatic/oncology contexts are never credited to a germline disease via the symbol
                    continue
                if any(c not in gene_names_lc[g] for c in common_terms):
                    continue
                gene_matches[g].setdefault(nct, (f"gene_in_{field}", text, g))

    # common-name guard
    dropped_common = {}
    for did in list(name_matches):
        if not rare[did] and len(name_matches[did]) > 300:
            dropped_common[did] = {"name": ds[did]["name"], "n": len(name_matches[did])}
            del name_matches[did]

    def sort_key(nct, rule):
        s = studies[nct]
        return (0 if rule.startswith("name") else 1,
                0 if s["type"] == "INTERVENTIONAL" else 1,
                STATUS_RANK.get(s["status"], 6),
                "".join(chr(255 - ord(c)) for c in (s.get("start") or "0000")))

    def counts(ncts):
        bt, bs = collections.Counter(), collections.Counter()
        for n in ncts:
            bt[studies[n]["type"] or "UNKNOWN"] += 1
            bs[studies[n]["status"] or "UNKNOWN"] += 1
        return {"n": len(ncts), "by_type": dict(bt), "by_status": dict(bs),
                "active": sum(v for k, v in bs.items() if k in ACTIVE)}

    out_d, used = {}, set()
    for did, d in ds.items():
        nm = name_matches.get(did, {})
        gm = {}
        gene_target_ok = not ("somatic" in d["name"].lower() or ONCO.search(d["name"]) or len(d["genes"]) >= 10)
        for g in (d["genes"] if gene_target_ok else []):
            for nct, v in gene_matches.get(g, {}).items():
                if nct not in nm:
                    gm.setdefault(nct, v)
        if not nm and not gm:
            continue
        allm = [(n, v) for n, v in nm.items()] + [(n, v) for n, v in gm.items()]
        allm.sort(key=lambda x: sort_key(x[0], x[1][0]))
        top = []
        for nct, (rule, text, term) in allm[:8]:
            e = {"nct": nct, "rule": rule, "quote": text, "url": CTG + nct}
            if rule.startswith("gene"):
                e["via_gene"] = term
            top.append(e)
            used.add(nct)
        out_d[did] = {"name": d["name"], "mondo": d.get("mondo"), "genes": d["genes"],
                      "by_name": counts(list(nm)), "by_gene": counts(list(gm)), "top": top,
                      "ctgov_search": "https://clinicaltrials.gov/search?cond=" + urllib.parse.quote(d["name"])}

    out_g = {}
    for g, m in gene_matches.items():
        ncts = sorted(m, key=lambda n: sort_key(n, "gene"))
        out_g[g] = {**counts(list(m)), "diseases": gene_diseases[g],
                    "top": [{"nct": n, "rule": m[n][0], "quote": m[n][1], "url": CTG + n} for n in ncts[:8]]}
        used.update(ncts[:8])

    st_table = {}
    for n in used:
        s = studies[n]
        st_table[n] = {"title": s["title"], "status": s["status"], "type": s["type"], "phases": s["phases"],
                       "start": s["start"], "enrollment": s["enrollment"], "sponsor": s["lead"]["name"],
                       "conditions": s["conditions"][:8], "url": CTG + n}

    n_any = len(out_d)
    n_name = sum(1 for v in out_d.values() if v["by_name"]["n"])
    meta = {
        "generated": today(),
        "source": {"name": "ClinicalTrials.gov API v2", "url": "https://clinicaltrials.gov/api/v2/studies",
                   "queries": "query.cond=<disease name> for every disease; query.term=<gene symbol> for every gene; "
                              "pageSize 100 (up to 10 pages when >=30 of the first 100 pass the filter)",
                   "studies_in_pool": len(studies)},
        "extracted_by": "automated",
        "rules": __doc__.strip(),
        "counts": {"diseases_with_any_trial": n_any, "diseases_with_name_matched_trial": n_name,
                   "diseases_with_gene_matched_trial_only": n_any - n_name,
                   "genes_with_trial": len(out_g), "studies_referenced": len(st_table),
                   "name_keys": len(index), "rejected_names": dict(rejected)},
        "dropped_common_names": dropped_common,
        "fields": {"diseases.<id>.by_name": "counts over studies matched by disease name/synonym",
                   "diseases.<id>.by_gene": "counts over studies matched only through a causal gene symbol",
                   "diseases.<id>.top": "up to 8 studies: name matches first, then interventional, then "
                                        "recruiting/active, then newest; quote = the verbatim condition/keyword/"
                                        "title string that matched"},
    }
    write_json(OUT / "trials.json", {"meta": meta, "studies": st_table, "diseases": out_d, "genes": out_g})
    print(json.dumps(meta["counts"], indent=1))
    print("dropped common:", list(dropped_common.values())[:10])

    # ---- trial-sourced patient-org candidates (rule 2a)
    KW = re.compile(r"\b(foundation|association|alliance|society|network|coalition|connect|trust|federation|support)\b", re.I)
    EXCL = re.compile(r"universit|hospital|college|institut|school|clinic|medical cent|medical cent|health ?(system|care|service|network|science|authority|board)|"
                      r"\bNHS\b|ministry|government|department|council|agency|pharma|therapeutic|biotech|\binc\b|\bltd\b|"
                      r"\bllc\b|gmbh|\bs\.?a\.?\b|\bcorp|company|laborator|research cent|centre|center|\bCHU\b|IRCCS|"
                      r"fondazione|klinik|consortium|cooperative|study group|trials? (group|network|unit)|oncolog|"
                      r"society (of|for)|academy|federation of|association (of|for the study)|physician|surgeon|nurs|"
                      r"science foundation|natural science|research foundation of|national institutes|gates|wellcome|"
                      r"novo nordisk|doris duke|robert wood johnson|chan zuckerberg|kavli|simons foundation|"
                      r"\bnih\b|foundation for the national|innovation|technolog|medicine|medical|clinical research|"
                      r"research network|registry|hematolog|cardiolog|neurolog|endocrin|pediatric|paediatric|"
                      r"genetics|transplant|marrow|radiolog|dermatolog|ophthalmolog|nephrolog|gastroenterolog|"
                      r"health foundation|charitable|bank|insurance|funds?\b|football|sport|cultural|dairy|research foundation$|"
                      r"\bresearch (trust|alliance)\b|laerdal|lundbeck|rosetrees|kuni|assisi|vancouver foundation|"
                      r"korea research|german research|michael smith|thoracic|kidney association|dialysis|santelys|"
                      r"diabetes|alzheimer|arthritis|healthy living|macula foundation|nutrition|heart (association|foundation)|"
                      r"lung (association|foundation)|stroke", re.I)
    orgs = {}
    for nct, s in studies.items():
        dmatch = [(did, "name") for did, m in name_matches.items() if nct in m] if False else None
    # invert matches once
    by_study = collections.defaultdict(list)
    for did, m in name_matches.items():
        for nct, (rule, text, k) in m.items():
            by_study[nct].append((did, rule, None))
    for g, m in gene_matches.items():
        for nct, (rule, text, k) in m.items():
            for did in gene_diseases[g]:
                by_study[nct].append((did, rule, g))
    concept = {did: (d.get("mondo") or did) for did, d in ds.items()}
    for nct, links in by_study.items():
        s = studies[nct]
        n_concepts = len({concept[did] for did, rule, via in links if via is None})
        n_genes = len({via for did, rule, via in links if via})
        parties = [("lead_sponsor", s["lead"])] + [("collaborator", c) for c in s["collaborators"]]
        for role, p in parties:
            nm, cl = (p.get("name") or "").strip(), p.get("class")
            if cl != "OTHER" or not nm or not KW.search(nm) or EXCL.search(nm) or ONCO.search(nm):
                continue
            key = norm_text(nm)
            o = orgs.setdefault(key, {"name": nm, "trials": {}, "diseases": {}})
            o["trials"][nct] = role
            for did, rule, via in links:
                # focused trials only: <= 3 name-matched disease concepts, <= 2 matched genes
                if (via is None and n_concepts > 3) or (via and n_genes > 2):
                    continue
                if via:
                    # gene-via links only for gene-named orgs ('POLG Foundation'), never to somatic/cancer/umbrella entities
                    dn = ds[did]["name"].lower()
                    if not re.search(r"(?<![A-Za-z0-9])" + re.escape(via) + r"(?![A-Za-z0-9])", nm) or \
                            "somatic" in dn or ONCO.search(dn) or len(ds[did]["genes"]) >= 10:
                        continue
                ev = o["diseases"].setdefault(did, [])
                if len(ev) < 3:
                    ev.append({"url": CTG + nct, "ref": nct, "quote": nm, "field": f"sponsorCollaboratorsModule ({role})",
                               "rule": f"trial_{role}:{rule}" + (f":{via}" if via else ""),
                               "context": s["title"], "conditions": s["conditions"][:12]})
    write_json(OUT / "_trial_orgs.json", {"generated": today(), "orgs": orgs})
    print(f"trial-sourced org candidates: {len(orgs)}; with >=1 disease: {sum(1 for o in orgs.values() if o['diseases'])}")


if __name__ == "__main__":
    main()
