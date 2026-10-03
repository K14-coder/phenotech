"""Build data/curated/community.json from raw API records + curated, quote-verified web evidence.

Inputs (all re-fetchable with the fetch_*.py scripts):
  data/raw/community/ctgov/*.json      ClinicalTrials.gov API v2
  data/raw/community/reporter/*.json   NIH RePORTER v2
  data/raw/community/pubmed/*.xml      PubMed efetch (affiliations; e-mails redacted)
  data/raw/community/web/*.txt|html    organisation pages (fetch_web.py)
  pipeline/community/curated_orgs.json, study_curation.json   agent curation
Every Website quote is string-matched against the stored page; unmatched quotes are dropped
(and listed in data/raw/community/build_summary.json). PubMed/RePORTER/CT.gov quotes are
extracted verbatim from the stored records.
Usage: python3 pipeline/community/build_community.py
"""
from __future__ import annotations

import glob
import html as htmlmod
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

from common import CURATED, GENES, PIPE, RAW, norm_ws, read_json, slugify, today, write_json

TODAY = today()
nodes: dict[str, dict] = {}
edges: dict[str, dict] = {}
dropped: list[dict] = []
DIS = lambda g: f"disease:{g}"  # noqa: E731

# ---------------------------------------------------------------- helpers
_web_cache: dict[tuple, str] = {}
MANIFEST = read_json(RAW / "web" / "_manifest.json") if (RAW / "web" / "_manifest.json").exists() else {}


def web_text(src: str, in_html: bool = False) -> str:
    key = (src, in_html)
    if key not in _web_cache:
        p = RAW / "web" / f"{src}.{'html' if in_html else 'txt'}"
        t = p.read_text() if p.exists() else ""
        if in_html:
            t = htmlmod.unescape(t)
        _web_cache[key] = norm_ws(t)
    return _web_cache[key]


def web_ev(e: dict, title: str | None = None) -> dict | None:
    src, quote, in_html = e["src"], e["quote"], e.get("in") == "html"
    m = MANIFEST.get(src, {})
    if m.get("status") != 200:
        dropped.append({"src": src, "quote": quote, "why": f"page status {m.get('status')}"})
        return None
    if norm_ws(quote) not in web_text(src, in_html):
        dropped.append({"src": src, "quote": quote, "why": "quote not found in stored page"})
        return None
    return {"source": "Website", "ref": m["url"], "url": m["url"], "title": title, "quote": quote,
            "kind": "website", "extracted_by": "agent-curation", "verified": True,
            "retrieved": m.get("retrieved", TODAY)}


def add_node(n: dict):
    nid = n["id"]
    if nid in nodes:
        old = nodes[nid]
        old.setdefault("sources", [])
        for s in n.get("sources", []):
            if s not in old["sources"]:
                old["sources"].append(s)
        for k, v in (n.get("attrs") or {}).items():
            old.setdefault("attrs", {}).setdefault(k, v)
        return old
    nodes[nid] = {k: v for k, v in n.items() if v not in (None, [], {})}
    return nodes[nid]


def add_edge(source, target, etype, explanation, evidence, level, confidence, label=None, attrs=None, status="supported"):
    evidence = [e for e in evidence if e]
    if not evidence and level != "hypothesis":
        dropped.append({"edge": f"{source}|{etype}|{target}", "why": "no verified evidence"})
        return None
    eid = f"{source}|{etype}|{target}"
    if eid in edges:
        ex = edges[eid]
        seen = {(e["ref"], e.get("quote")) for e in ex["evidence"]}
        for e in evidence:
            if (e["ref"], e.get("quote")) not in seen:
                ex["evidence"].append(e)
        ex["confidence"] = max(ex["confidence"], confidence)
        return ex
    edges[eid] = {"id": eid, "source": source, "target": target, "type": etype, "label": label,
                  "explanation": explanation, "evidence_level": level, "status": status,
                  "confidence": round(confidence, 2), "evidence": evidence}
    if attrs:
        edges[eid]["attrs"] = attrs
    if label is None:
        del edges[eid]["label"]
    return edges[eid]


GENE_RX = {
    "STXBP1": re.compile(r"\b(STXBP1|Munc18-1|Munc18a)\b", re.I),
    "SYT1": re.compile(r"\b(SYT1|synaptotagmin[- ]1|Baker[- ]Gordon)\b", re.I),
    "SNAP25": re.compile(r"\b(SNAP25|SNAP-25)\b", re.I),
    "VAMP2": re.compile(r"\b(VAMP2|VAMP-2|synaptobrevin[- ]2)\b", re.I),
    "STX1B": re.compile(r"\b(STX1B|(?i:syntaxin[- ]1B))\b"),  # case-sensitive symbol
    "SYT2": re.compile(r"\b(SYT2|synaptotagmin[- ]2)\b", re.I),
    "CPLX1": re.compile(r"\b(CPLX1|complexin[- ]1)\b", re.I),
    "UNC13A": re.compile(r"\b(UNC13A|Munc13-1)\b", re.I),
    "STX1A": re.compile(r"\b(STX1A|(?i:syntaxin[- ]1A))\b"),  # case-sensitive: E. coli Shiga-toxin gene is "stx1a"
    # exclude the SNARE acronym expansion "soluble N-ethylmaleimide-sensitive factor attachment protein (receptor)"
    "NSF": re.compile(r"\b(NSF\b(?![\s\])-]*attachment)|N-ethylmaleimide[\s-]*sensitive[\s-]*factor\b(?![\s\])-]*attachment))"),
    "SLC6A1": re.compile(r"\b(SLC6A1|GAT-?1)\b"),
}
MONOGENIC_RX = re.compile(r"(patient|mutation|variant|encephalopath|epilep|seizure|de novo|haploinsufficien|"
                          r"myasthen|intellectual disability|SNAREopath|developmental delay|"
                          r"related disorder|associated disorder|Baker[- ]Gordon)", re.I)
OTHER_DISEASE_RX = re.compile(r"(alzheimer|parkinson|\bPD\b|amyotrophic|\bALS\b|frontotemporal|\bFTD\b|huntington|cancer|tumou?r|"
                              r"carcinoma|diabet|insulin|schizophren|bipolar|ADHD|depress|addict|alcohol|cocaine|opioid|"
                              r"\bpain\b|stroke|isch[a]?emi|prion|botulinum|nephrogenic|Shiga|neurofibromatosis|\bNF1\b|Williams|7q11|cortico|cardiac|synuclein|spinal muscular atrophy|\bSMA\b|TDP-43)", re.I)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text or "") if s.strip()]


GENE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]{2,}[A-Z0-9-]*\b")
NOT_GENES = {"DNA", "RNA", "EEG", "MRI", "DEE", "DEES", "NDD", "CMS", "HPO", "ACMG", "AAV", "ASO", "SNARE", "SNARES", "SNAP", "NIH",
             "USA", "WES", "WGS", "CNV", "ATP", "GABA", "CNS", "PET", "FDA", "EMA", "ADHD", "ASD", "QOL", "IPSC", "IPSCS", "GEFS"}


def gene_list_sentence(s: str, gene: str) -> bool:
    """True if the sentence names >= 4 other gene-like symbols (a panel / candidate list, not a focus)."""
    toks = {t for t in GENE_TOKEN.findall(s) if t not in NOT_GENES and not GENE_RX[gene].fullmatch(t)}
    return len(toks) >= 3


def disease_sentence(gene: str, title: str, abstract: str) -> tuple[str | None, str | None]:
    """Return (sentence linking gene to a monogenic disorder, sentence merely mentioning gene)."""
    rx = GENE_RX[gene]
    mention = None
    for i, s in enumerate([title] + sentences(abstract)):
        if not s or not rx.search(s):
            continue
        mention = mention or s
        if i > 0 and gene_list_sentence(s, gene):
            continue
        if MONOGENIC_RX.search(s) and not OTHER_DISEASE_RX.search(s):
            return s, mention
    return None, mention


# ---------------------------------------------------------------- institutions & names
INST_PATTERNS = [
    (r"Children'?s Hosp(?:ital)?\.? (?:of )?Philadelphia|\bCHOP\b", "childrens-hospital-of-philadelphia"),
    (r"Univ(?:ersity)?\.? of Pennsylvania|Perelman School", "university-of-pennsylvania"),
    (r"Baylor College of Medicine|Texas Children'?s Hospital|Duncan Neurological", "baylor-college-of-medicine"),
    (r"Vrije Universiteit|VU University|VU Amsterdam|Amsterdam UMC|VU Medical|Neurogenomics and Cognitive Research", "vu-amsterdam"),
    (r"MRC Cognition and Brain Sciences|University of Cambridge|Cambridge Biomedical", "university-of-cambridge"),
    (r"Florey Institute", "florey-institute"),
    (r"Murdoch Children'?s", "murdoch-childrens-research-institute"),
    (r"University of Melbourne", "university-of-melbourne"),
    (r"Columbia Univ", "columbia-university"),
    (r"Boston Children'?s Hosp", "boston-childrens-hospital"),
    (r"Massachusetts General Hosp", "massachusetts-general-hospital"),
    (r"Brigham and Women", "brigham-and-womens-hospital"),
    (r"Broad Institute", "broad-institute"),
    (r"Danish Epilepsy Cent|Filadelfia", "danish-epilepsy-centre-filadelfia"),
    (r"University of Copenhagen|Københavns", "university-of-copenhagen"),
    (r"Vanderbilt", "vanderbilt-university"),
    (r"Weill Cornell|Weill Medical Coll", "weill-cornell-medicine"),
    (r"Stanford", "stanford-university"),
    (r"UT Southwestern|Univ(?:ersity)?\.? of (?:TX|Texas) Southwestern", "ut-southwestern"),
    (r"University of Antwerp|Universiteit Antwerpen|Antwerp University Hospital", "university-of-antwerp"),
    (r"Heidelberg", "heidelberg-university"),
    (r"Leipzig", "university-of-leipzig"),
    (r"T[üu]e?bingen", "university-of-tuebingen"),
    (r"University College London|\bUCL\b", "university-college-london"),
    (r"Yale", "yale-university"),
    (r"Mayo Clinic", "mayo-clinic"),
    (r"Radboud", "radboud-university-medical-center"),
    (r"University of Colorado|Children'?s Hospital Colorado|Anschutz", "university-of-colorado"),
    (r"Charit[ée]", "charite-berlin"),
    (r"University of Oxford|Oxford University", "university-of-oxford"),
    (r"Newcastle University|Newcastle upon Tyne", "newcastle-university"),
    (r"Sant Joan de D[ée]u", "hospital-sant-joan-de-deu"),
    (r"Gaslini", "istituto-giannina-gaslini"),
    (r"Scripps", "scripps-research"),
    (r"G[öo]e?ttingen", "university-of-goettingen"),
    (r"University of Missouri", "university-of-missouri"),
    (r"Emory", "emory-university"),
    (r"Duke University", "duke-university"),
    (r"Johns Hopkins", "johns-hopkins-university"),
    (r"University of California,? San Francisco|\bUCSF\b", "ucsf"),
    (r"University of California,? Los Angeles|\bUCLA\b", "ucla"),
    (r"University of California,? San Diego|\bUCSD\b", "ucsd"),
    (r"University of Washington", "university-of-washington"),
    (r"Washington University", "washington-university-in-st-louis"),
    (r"National Institute of Neurological Disorders|\bNINDS\b", "ninds"),
    (r"Max Planck Institute for Multidisciplinary Sciences|Max Planck Institute of Experimental Medicine", "max-planck-goettingen"),
    (r"Max Planck", "max-planck-society"),
    (r"Erasmus", "erasmus-mc"),
    (r"Utrecht", "umc-utrecht"),
    (r"Karolinska", "karolinska-institutet"),
    (r"University of Sydney", "university-of-sydney"),
    (r"Children'?s Medical Research Institute", "childrens-medical-research-institute"),
    (r"Great Ormond Street", "great-ormond-street-hospital"),
    (r"King'?s College London", "kings-college-london"),
    (r"Hospital Ruber Internacional", "hospital-ruber-internacional"),
    (r"Sheba", "sheba-medical-center"),
    (r"Aix[- ]Marseille", "aix-marseille-universite"),
    (r"University of Utah", "university-of-utah"),
    (r"Rush University", "rush-university"),
    (r"Seattle Children", "seattle-childrens"),
    (r"Cincinnati Children", "cincinnati-childrens"),
    (r"Nationwide Children", "nationwide-childrens-hospital"),
    (r"Lurie Children|Northwestern University", "northwestern-university"),
    (r"University of Toronto|Hospital for Sick Children|SickKids", "university-of-toronto"),
    (r"McGill", "mcgill-university"),
    (r"Fudan", "fudan-university"),
    (r"Peking University", "peking-university"),
    (r"Zhejiang University", "zhejiang-university"),
    (r"Kyoto University", "kyoto-university"),
    (r"Yokohama City University", "yokohama-city-university"),
    (r"University of Tokyo", "university-of-tokyo"),
]
INST_RX = [(re.compile(p, re.I), s) for p, s in INST_PATTERNS]
INST_WORD = re.compile(r"(Universit|Hospital|Institut|College|Center|Centre|School|Klinik|Clinic|Foundation|Laborator|Hôpital|Ospedale|Hospices)", re.I)


def inst_key(aff: str) -> tuple[str, str]:
    """Map an affiliation string to (slug, display name)."""
    aff = (aff or "").replace("[email-redacted]", "")
    for rx, slug in INST_RX:
        m = rx.search(aff)
        if m:
            return slug, slug.replace("-", " ").title()
    parts = [p.strip(" .;") for p in re.split(r"[,;]", aff) if p.strip(" .;")]
    for p in parts:
        if INST_WORD.search(p) and not re.match(r"(Department|Dept|Division|Section|Laboratory of|Program|Unit)\b", p, re.I):
            return slugify(p, 50), p
    for p in parts:
        if INST_WORD.search(p):
            return slugify(p, 50), p
    return (slugify(parts[0], 50), parts[0]) if parts else ("unknown", "unknown")


def tidy_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in s.split(" "))


# researcher registry: key=(last, first-token) -> list of person records
people: dict[str, dict] = {}         # rid -> {name, last, first, inst, inst_name, orcid, sources...}
name_inst_index: dict[tuple, str] = {}
orcid_index: dict[str, str] = {}


def get_person(first: str, last: str, aff: str, orcid: str | None = None, profile_id=None) -> str:
    first, last = tidy_name(first), tidy_name(last)
    fkey = (first.split(" ")[0] if first else "").lower().strip(".")
    ik, iname = inst_key(aff)
    if orcid and orcid in orcid_index:
        rid = orcid_index[orcid]
        people[rid]["affiliations"].add(iname)
        return rid
    key = (last.lower(), fkey, ik)
    if key in name_inst_index:
        rid = name_inst_index[key]
        if orcid and not people[rid].get("orcid"):
            people[rid]["orcid"] = orcid
            orcid_index[orcid] = rid
        if profile_id and not people[rid].get("nih_profile_id"):
            people[rid]["nih_profile_id"] = profile_id
        return rid
    rid = f"researcher:{slugify(f'{first} {last}', 50)}--{ik}"
    people[rid] = {"first": first, "last": last, "inst": ik, "inst_name": iname, "affiliations": {iname},
                   "orcid": orcid, "nih_profile_id": profile_id, "aff_raw": aff}
    name_inst_index[key] = rid
    if orcid:
        orcid_index[orcid] = rid
    return rid


# ---------------------------------------------------------------- 1. organisations & assets
cur = read_json(PIPE / "curated_orgs.json")
for o in cur["orgs"]:
    evs = [web_ev(e, o["label"]) for e in o["evidence"]]
    evs = [e for e in evs if e]
    if not evs:
        dropped.append({"org": o["id"], "why": "no verified evidence"})
        continue
    attrs = {"url": o["url"], "country": o.get("country"), "scope": o.get("scope")}
    for k, e in (o.get("extra") or {}).items():
        ev = web_ev(e, f"{o['label']}: {k}")
        if ev:
            attrs[k] = {"present": True, "url": ev["url"], "quote": ev["quote"]}
    add_node({"id": o["id"], "type": "patient_org", "label": o["label"], "summary": o.get("summary"),
              "attrs": attrs, "sources": evs})
    for g in o["serves"]:
        sev = [web_ev(e, o["label"]) for e in o.get("serves_evidence", {}).get(g, [])] or evs
        level = o.get("serves_level", "observational")
        conf = o.get("serves_confidence", 0.9)
        expl = (f"{o['label']} states on its own website that it serves people with {g}-related disorders."
                if level != "inferred" else
                f"{o['label']} is an umbrella group. A link between it and the {g} community appears on one of the "
                f"two organisations' websites; this is a partnership signal, not a formal membership record.")
        add_edge(o["id"], DIS(g), "serves", expl, sev, level, conf, label="serves")

for a in cur["assets"]:
    evs = [e for e in (web_ev(x, a["label"]) for x in a["evidence"]) if e]
    if not evs:
        dropped.append({"asset": a["id"], "why": "no verified evidence"})
        continue
    attrs = {"kind": a["kind"], "url": a.get("url"), "access": a.get("access"), "status": a.get("status")}
    if len(a.get("covers", [])) > 1:
        attrs["multi_gene_slice"] = a["covers"]
    add_node({"id": a["id"], "type": "asset", "label": a["label"], "xrefs": a.get("xrefs"),
              "summary": evs[0]["quote"][:300], "attrs": attrs, "sources": evs})
    for g in a.get("covers", []):
        cev = [e for e in (web_ev(x, a["label"]) for x in a.get("covers_evidence", {}).get(g, [])) if e] or evs
        add_edge(a["id"], DIS(g), "covers",
                 f"{a['label']} includes people with {g}-related disorders, according to the cited page.",
                 cev, "observational", 0.85, label="covers")
    for org in a.get("maintained_by", []):
        if org in nodes:
            add_edge(org, a["id"], "maintains",
                     f"{nodes[org]['label']} runs or partners on {a['label']}, according to the cited page.",
                     evs, "observational", 0.8, label="runs / partners on")

# ---------------------------------------------------------------- 2. studies (ClinicalTrials.gov)
sc = read_json(PIPE / "study_curation.json")
raw_studies = {}
for f in sorted(glob.glob(str(RAW / "ctgov" / "*.json"))):
    d = read_json(f)
    for s in d["studies"]:
        raw_studies[s["protocolSection"]["identificationModule"]["nctId"]] = (s, d["retrieved"])

therapy_defs = sc["therapies"]
for nct, cfg in sc["studies"].items():
    if nct not in raw_studies:
        dropped.append({"study": nct, "why": "not in raw CT.gov pulls"})
        continue
    s, retrieved = raw_studies[nct]
    ps = s["protocolSection"]
    rec_text = norm_ws(json.dumps(s, ensure_ascii=False).replace("\\n", " "))
    im, stm, dm = ps["identificationModule"], ps["statusModule"], ps.get("designModule", {})
    spm = ps.get("sponsorCollaboratorsModule", {})
    ivs = ps.get("armsInterventionsModule", {}).get("interventions", [])
    url = f"https://clinicaltrials.gov/study/{nct}"
    sponsor = spm.get("leadSponsor", {}).get("name")
    collabs = [c.get("name") for c in spm.get("collaborators", [])]
    phases = dm.get("phases") or []
    attrs = {"status": stm.get("overallStatus"), "study_type": (dm.get("studyType") or "").lower() or None,
             "phase": "/".join(phases) if phases else None, "start": (stm.get("startDateStruct") or {}).get("date"),
             "sponsor": sponsor, "collaborators": collabs or None,
             "enrollment": (dm.get("enrollmentInfo") or {}).get("count"),
             "interventions": [i.get("name") for i in ivs] or None,
             "conditions": ps.get("conditionsModule", {}).get("conditions"),
             "eligibility_note": cfg["note"], "url": url}
    if len(cfg["genes"]) > 1:
        attrs["multi_gene_slice"] = cfg["genes"]
    base_ev = {"source": "ClinicalTrials.gov", "ref": nct, "url": url, "title": im.get("briefTitle"),
               "kind": "trial", "study_type": "clinical_trial" if attrs["study_type"] == "interventional" else "database_record",
               "extracted_by": "database", "verified": True, "retrieved": retrieved}
    add_node({"id": f"study:{nct}", "type": "study", "label": im.get("briefTitle"),
              "summary": (ps.get("descriptionModule", {}).get("briefSummary") or "")[:300] or None,
              "xrefs": {"NCT": nct}, "attrs": {k: v for k, v in attrs.items() if v not in (None, [], "")},
              "sources": [dict(base_ev)]})
    for g in cfg["genes"]:
        snip = cfg["snippets"].get(g)
        if snip:
            if norm_ws(snip) not in rec_text:
                dropped.append({"study": nct, "gene": g, "snippet": snip, "why": "snippet not in record"})
                continue
            ev = dict(base_ev, quote=snip)
            expl = f"{nct} names {g} in its conditions or eligibility criteria, so people with {g}-related disorders can take part."
        else:
            # coverage known from the sponsor's website, not the CT.gov record
            asset = next((a for a in cur["assets"] if (a.get("xrefs") or {}).get("NCT") == nct), None)
            evs = [e for e in (web_ev(x) for x in (asset or {}).get("covers_evidence", {}).get(g, [])) if e] if asset else []
            if not evs:
                continue
            ev = evs[0]
            expl = f"{nct} enrols by genetic diagnosis. The sponsor's website lists {g} among the genes it studies, but the CT.gov condition list does not name it."
        conf = cfg.get("confidence", 0.9 if snip else 0.6)
        add_edge(f"study:{nct}", DIS(g), "studies", expl, [ev], "curated", conf, label="enrols / studies")
    for iv in ivs:
        nm = iv.get("name") or ""
        for tid, td in therapy_defs.items():
            if any(m.lower() in nm.lower() for m in td["match"]) and not (tid == "therapy:cap-002" and nct != "NCT06983158"):
                add_node({"id": tid, "type": "therapy", "label": td["label"], "synonyms": td.get("synonyms"),
                          "attrs": {"modality": td["modality"], "stage": td["stage"]}, "sources": [dict(base_ev)]})
                add_edge(f"study:{nct}", tid, "tests", f"{nct} lists '{nm}' as an intervention.",
                         [dict(base_ev, quote=nm)], "clinical" if attrs["study_type"] == "interventional" else "curated",
                         0.9, label="tests")
                for g in td.get("developed_for", []):
                    add_edge(tid, DIS(g), "developed_for",
                             f"{td['label']} is being tested in {nct}, which requires a {g} variant for eligibility.",
                             [dict(base_ev, quote=cfg["snippets"].get(g, nm))], "clinical", 0.85, label="developed for")

# ---------------------------------------------------------------- 3. NIH RePORTER grants
grants: dict[str, dict] = {}
for f in sorted(glob.glob(str(RAW / "reporter" / "*.json"))):
    d = read_json(f)
    for r in d["response"].get("results", []):
        core = r.get("core_project_num") or r.get("project_num")
        if not core:
            continue
        prev = grants.get(core)
        if prev is None or (r.get("fiscal_year") or 0) > (prev["rec"].get("fiscal_year") or 0):
            fys = (prev or {}).get("fys", set())
            grants[core] = {"rec": r, "fys": fys, "retrieved": d["retrieved"], "terms": set()}
        grants[core]["fys"].add(r.get("fiscal_year"))
        grants[core]["terms"].add(d["term"])

grant_hits = defaultdict(dict)  # core -> gene -> (kind, quote)
for core, g in grants.items():
    r = g["rec"]
    title, abstract = r.get("project_title") or "", r.get("abstract_text") or ""
    other_disease_grant = bool(OTHER_DISEASE_RX.search(title))  # e.g. ALS/FTD, Parkinson, SMA programmes -> gene-level only
    for gene in GENES:
        dis_s, mention = disease_sentence(gene, title, abstract)
        if dis_s and not other_disease_grant:
            grant_hits[core][gene] = ("disease", dis_s)
        elif (mention or dis_s) and GENE_RX[gene].search(title):
            grant_hits[core][gene] = ("gene", mention or dis_s)

for core, hits in grant_hits.items():
    if not hits:
        continue
    g = grants[core]
    r = g["rec"]
    url = r.get("project_detail_url") or f"https://reporter.nih.gov/project-details/{r.get('appl_id')}"
    org = (r.get("organization") or {}).get("org_name") or ""
    pis = r.get("principal_investigators") or []
    pi_names = [tidy_name(f"{p.get('first_name','')} {p.get('last_name','')}") for p in pis]
    gid = f"grant:{core}"
    ev0 = {"source": "NIH RePORTER", "ref": core, "url": url, "title": r.get("project_title"), "year": r.get("fiscal_year"),
           "kind": "grant", "study_type": "database_record", "extracted_by": "database", "verified": True,
           "retrieved": g["retrieved"]}
    add_node({"id": gid, "type": "grant", "label": tidy_name(r.get("project_title") or core) if (r.get("project_title") or "").isupper() else r.get("project_title"),
              "attrs": {"title": r.get("project_title"), "pis": pi_names, "org": org, "fiscal_year": r.get("fiscal_year"),
                        "fiscal_years": sorted(x for x in g["fys"] if x), "amount": r.get("award_amount"), "url": url,
                        "activity_code": r.get("activity_code"), "agency": r.get("agency_ic_admin", {}).get("abbreviation") if isinstance(r.get("agency_ic_admin"), dict) else None,
                        "slice_genes": sorted(hits)},
              "sources": [ev0]})
    for gene, (kind, quote) in hits.items():
        if kind == "disease":
            add_edge(gid, DIS(gene), "about",
                     f"The NIH project record ties {gene} to the human disorder (patients, variants or epilepsy) in its title or abstract.",
                     [dict(ev0, quote=quote)], "curated",
                     0.85 if (GENE_RX[gene].search(r.get("project_title") or "") and MONOGENIC_RX.search(r.get("project_title") or "")) else 0.7,
                     label="about")
        else:
            add_edge(gid, f"gene:{gene}", "about",
                     f"The NIH project names {gene} in its title as a basic-science focus; the abstract does not tie it to the human disorder.",
                     [dict(ev0, quote=quote)], "curated", 0.7, label="about (gene)")
    for p in pis:
        rid = get_person(p.get("first_name", ""), p.get("last_name", ""), org, profile_id=p.get("profile_id"))
        people[rid].setdefault("grants", set()).add(core)
        add_edge(gid, rid, "funds", f"{tidy_name(org)} holds NIH project {core}; this person is listed as a principal investigator.",
                 [dict(ev0, quote=r.get("project_title"))], "curated", 0.95, label="funds")
        for gene, (kind, quote) in hits.items():
            target = DIS(gene) if kind == "disease" else f"gene:{gene}"
            add_edge(rid, target, "works_on",
                     f"Principal investigator on NIH project {core}, which covers {gene}" +
                     (" in the context of the human disorder." if kind == "disease" else " (basic science)."),
                     [dict(ev0, quote=quote)], "observational", 0.8 if kind == "disease" else 0.65, label="works on")

# ---------------------------------------------------------------- 4. PubMed research groups
def itertext(el):
    return norm_ws("".join(el.itertext())) if el is not None else ""


EXCL = read_json(PIPE / "pubmed_exclusions.json")["pmids"] if (PIPE / "pubmed_exclusions.json").exists() else {}
pub_counts = {}
author_papers = defaultdict(lambda: defaultdict(list))  # rid -> gene -> [paper]
for f in sorted(glob.glob(str(RAW / "pubmed" / "*.efetch.xml"))):
    gene = f.split("/")[-1].split(".")[0]
    raw = open(f).read()
    retrieved = read_json(RAW / "pubmed" / f"{gene}.esearch.json")["retrieved"]
    n_rel = 0
    for chunk in raw.split("<!-- batch -->"):
        chunk = chunk.strip()
        chunk = re.sub(r"<\?xml[^>]*\?>", "", chunk)
        chunk = re.sub(r"<!DOCTYPE[^>]*>", "", chunk)
        if not chunk:
            continue
        root = ET.fromstring(chunk)
        for art in root.iter("PubmedArticle"):
            pmid = art.findtext(".//PMID")
            title = itertext(art.find(".//ArticleTitle"))
            abstract = " ".join(itertext(a) for a in art.findall(".//Abstract/AbstractText"))
            year = art.findtext(".//JournalIssue/PubDate/Year") or (art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4]
            journal = art.findtext(".//Journal/ISOAbbreviation") or art.findtext(".//Journal/Title")
            dis_s, _ = disease_sentence(gene, title, abstract)
            if not dis_s or EXCL.get(pmid, {}).get("gene") == gene:
                continue
            n_mentions = sum(1 for x in sentences(abstract) if GENE_RX[gene].search(x))
            other_in_title = any(GENE_RX[g2].search(title) for g2 in GENES if g2 != gene)
            if not GENE_RX[gene].search(title) and (n_mentions < 2 or other_in_title):
                continue  # works_on requires the gene to be a focus: named in the title or in >= 2 abstract sentences
            ptypes = {pt.text for pt in art.findall(".//PublicationTypeList/PublicationType")}
            n_slice = sum(1 for g2 in GENES if GENE_RX[g2].search(title + " " + abstract))
            if any(("Review" in (t or "")) or ("Erratum" in (t or "")) for t in ptypes) or title.startswith("Correction to") or (n_slice >= 3 and not GENE_RX[gene].search(title)):
                continue  # reviews / multi-gene lists are not evidence that a group works on this disorder
            authors = [a for a in art.findall(".//AuthorList/Author") if a.findtext("LastName")]
            if not authors:
                continue
            n_rel += 1
            last = authors[-1]
            aff = last.findtext(".//AffiliationInfo/Affiliation") or ""
            orcid = None
            for idf in last.findall("Identifier"):
                if idf.get("Source") == "ORCID":
                    orcid = re.sub(r"^https?://orcid.org/", "", (idf.text or "").strip())
            if not aff:
                continue
            rid = get_person(last.findtext("ForeName") or last.findtext("Initials") or "", last.findtext("LastName"), aff, orcid)
            author_papers[rid][gene].append({"pmid": pmid, "title": title, "year": int(year) if year.isdigit() else None,
                                             "journal": journal, "quote": dis_s, "retrieved": retrieved})
    pub_counts[gene] = n_rel

# keep the most active last-author groups per gene
THRESH = {g: 1 for g in GENES}  # rank by paper count then recency; keep top 15 groups per gene
selected = defaultdict(dict)
for gene in GENES:
    ranked = sorted(((rid, ps[gene]) for rid, ps in author_papers.items() if gene in ps),
                    key=lambda x: (-len(x[1]), -max(p["year"] or 0 for p in x[1])))
    for rid, papers in ranked:
        if len(papers) >= THRESH[gene] and len(selected[gene]) < 15:
            selected[gene][rid] = papers

for gene, sel in selected.items():
    for rid, papers in sel.items():
        evs = [{"source": "PubMed", "ref": f"PMID:{p['pmid']}", "url": f"https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/",
                "title": p["title"], "year": p["year"], "quote": p["quote"], "kind": "publication",
                "extracted_by": "database", "verified": True, "retrieved": p["retrieved"]} for p in papers[:6]]
        n = len(papers)
        add_edge(rid, DIS(gene), "works_on",
                 f"Last (senior) author on {n} paper{'s' if n > 1 else ''} since 2018 that focus on {gene} and tie it to the human disorder.",
                 evs, "observational", 0.75 if n >= 2 else 0.6, label="works on")
        people[rid].setdefault("papers", set()).update(p["pmid"] for p in papers)

# grant PIs whose only link is a grant still count; build researcher nodes for everyone with an edge
used = {e["source"] for e in edges.values() if e["type"] == "works_on"} | \
       {e["target"] for e in edges.values() if e["type"] == "funds"}
for rid in used:
    p = people[rid]
    name = f"{p['first']} {p['last']}".strip()
    aff_disp = p["inst_name"] if p["inst_name"] != p["inst"] else p["inst"].replace("-", " ").title()
    attrs = {"affiliation": tidy_name(aff_disp) if aff_disp.isupper() else aff_disp}
    if p.get("orcid"):
        attrs["orcid"] = p["orcid"]
        attrs["url"] = f"https://orcid.org/{p['orcid']}"
    elif p.get("papers"):
        attrs["url"] = "https://pubmed.ncbi.nlm.nih.gov/?term=" + "+OR+".join(sorted(p["papers"])[:20]) + "&sort=date"
    elif p.get("grants"):
        g0 = sorted(p["grants"])[0]
        attrs["url"] = nodes[f"grant:{g0}"]["attrs"]["url"]
    if p.get("nih_profile_id"):
        attrs["nih_profile_id"] = p["nih_profile_id"]
    if len(p["affiliations"]) > 1:
        attrs["other_affiliations"] = sorted(p["affiliations"] - {p["inst_name"]})
    attrs["identity_basis"] = ("ORCID in PubMed author record" if p.get("orcid") else "name + institution") + \
                              ("; linked to the NIH RePORTER PI record by exact name + institution match" if p.get("papers") and p.get("grants") else "")
    add_node({"id": rid, "type": "researcher", "label": name, "attrs": attrs})

for link in cur.get("researcher_links", []):
    if link["researcher"] in nodes and link["asset"] in nodes:
        evs = [e for e in (web_ev(x) for x in link["evidence"]) if e]
        add_edge(link["researcher"], link["asset"], "maintains", link["explanation"], evs, "observational", 0.85, label="leads")
    else:
        dropped.append({"researcher_link": link, "why": "researcher or asset node missing"})

# ---------------------------------------------------------------- 5. network overlap
dis_of = defaultdict(set)
for e in edges.values():
    if e["target"].startswith("disease:") and e["type"] in ("works_on", "serves", "covers", "studies", "about"):
        dis_of[e["source"]].add(e["target"])
overlap_researchers = {rid: sorted(ds) for rid, ds in dis_of.items() if rid.startswith("researcher:") and len(ds) >= 2}
overlap_orgs = {i: sorted(ds) for i, ds in dis_of.items() if i.startswith(("org:", "asset:")) and len(ds) >= 2}
multi_studies = {i: sorted(ds) for i, ds in dis_of.items() if i.startswith("study:") and len(ds) >= 2}
for rid, ds in overlap_researchers.items():
    nodes[rid]["attrs"]["bridges_diseases"] = ds
# sponsors / collaborators spanning >= 2 diseases
sponsor_dis = defaultdict(set)
sponsor_studies = defaultdict(set)
for nid, n in nodes.items():
    if n["type"] == "study":
        for sp in [n["attrs"].get("sponsor")] + (n["attrs"].get("collaborators") or []):
            if sp:
                sponsor_dis[sp] |= dis_of.get(nid, set())
                sponsor_studies[sp].add(nid.split(":")[1])
overlap_sponsors = {sp: {"diseases": sorted(ds), "studies": sorted(sponsor_studies[sp])} for sp, ds in sponsor_dis.items() if len(ds) >= 2}

# same-name / different-institution candidates (NOT merged)
by_name = defaultdict(list)
for rid in used:
    p = people[rid]
    by_name[(p["last"].lower(), (p["first"].split(" ")[0] if p["first"] else "").lower())].append(rid)
name_collisions = {f"{k[1]} {k[0]}": v for k, v in by_name.items() if len(v) > 1}
for v in name_collisions.values():
    for rid in v:
        nodes[rid]["attrs"]["possible_same_person_as"] = [x for x in v if x != rid]
        nodes[rid]["attrs"]["identity_note"] = ("Same name appears at another institution. Not merged: affiliations differ and no shared ORCID, "
                                                "so these may be one person who moved or two different people.")

# ---------------------------------------------------------------- 6. gaps
WEB_QUERIES = read_json(PIPE / "search_log.json")
gaps = []
for gene in GENES:
    d = DIS(gene)
    orgs_specific = [e["source"] for e in edges.values() if e["type"] == "serves" and e["target"] == d and e["confidence"] >= 0.8]
    orgs_umbrella = [e["source"] for e in edges.values() if e["type"] == "serves" and e["target"] == d and e["confidence"] < 0.8]
    reg_assets = [e["source"] for e in edges.values() if e["type"] == "covers" and e["target"] == d
                  and nodes[e["source"]]["attrs"]["kind"] in ("registry", "natural_history_study", "research_network", "data_platform")]
    obs_studies = [e["source"] for e in edges.values() if e["type"] == "studies" and e["target"] == d
                   and nodes[e["source"]]["attrs"].get("study_type") == "observational"]
    int_studies = [e["source"] for e in edges.values() if e["type"] == "studies" and e["target"] == d
                   and nodes[e["source"]]["attrs"].get("study_type") == "interventional"]
    models = [e["source"] for e in edges.values() if e["type"] == "covers" and e["target"] == d
              and nodes[e["source"]]["attrs"]["kind"] in ("animal_model", "cell_model")]
    org_searches = WEB_QUERIES["org_searches"].get(gene, []) + WEB_QUERIES["directories_checked"]
    ct_searches = [f"ClinicalTrials.gov API v2 {q}" for q in WEB_QUERIES["ctgov"].get(gene, [])]
    if not orgs_specific:
        gaps.append({"id": f"gap:{gene}:patient-org", "about": d,
                     "question": f"Is there a patient organisation dedicated to {gene}-related disorders?",
                     "what_is_missing": [f"No {gene}-specific patient organisation was found."] +
                                        ([f"Umbrella groups linked to this community: {', '.join(orgs_umbrella)}"] if orgs_umbrella else []),
                     "searched": org_searches,
                     "how_to_find_out": "Ask the clinicians who reported cases (see researcher works_on edges) whether families have formed a group; post in DEE-P Connections / COMBINEDBrain / CMDIR family networks; check Facebook family groups; contact Unique (rarechromo.org) and EURORDIS member directories."})
    if not reg_assets and not obs_studies:
        gaps.append({"id": f"gap:{gene}:registry", "about": d,
                     "question": f"Is there a registry or natural history study that enrols people with {gene}-related disorders?",
                     "what_is_missing": ["No registry, natural history study or observational study with gene-based eligibility was found."],
                     "searched": org_searches + ct_searches,
                     "how_to_find_out": "Ask Simons Searchlight, Citizen Health, RARE-X or CMDIR to add the gene; check Human Disease Genes (humandiseasegenes.nl) for a clinician-entered case series; consider a cross-gene SNAREopathy registry."})
    if not int_studies:
        gaps.append({"id": f"gap:{gene}:trials", "about": d,
                     "question": f"Is any interventional trial enrolling people with {gene}-related disorders?",
                     "what_is_missing": ["No interventional study registered on ClinicalTrials.gov names this gene in its conditions or eligibility."]
                                        + (["Adjacent: TRCN-1023 (NCT07674667) aims to restore UNC13A function, but in ALS, not in the UNC13A neurodevelopmental/CMS disorder."] if gene == "UNC13A" else []),
                     "searched": ct_searches,
                     "how_to_find_out": "Re-run pipeline/community/fetch_ctgov.py; check EU CTR / ISRCTN; ask sponsors of related trials (e.g. the phenylbutyrate, CAP-002 and amifampridine studies) whether their protocols could add this gene."})
    if not models:
        gaps.append({"id": f"gap:{gene}:models", "about": d,
                     "question": f"Is there a documented, accessible animal or cell model for {gene}-related disorders in the atlas?",
                     "what_is_missing": ["No animal or cell model asset with verified access information was recorded for this gene (MGI/JAX, hPSCreg and EBiSC were not systematically searched in this pass)."],
                     "searched": ["Organisation researcher-resource pages listed in pipeline/community/web_sources.json"],
                     "how_to_find_out": f"Search MGI (informatics.jax.org) for {gene[0] + gene[1:].lower()} alleles, the JAX strain catalogue, hPSCreg and EBiSC for {gene} iPSC lines, and ask the researchers linked to this disease."})

# ---------------------------------------------------------------- write
out = {"nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
       "edges": sorted(edges.values(), key=lambda e: e["id"]), "clusters": [], "gaps": gaps}
write_json(CURATED / "community.json", out)
summary = {"built": TODAY, "counts": Counter(n["type"] for n in nodes.values()),
           "edge_counts": Counter(e["type"] for e in edges.values()), "pubmed_relevant_papers": pub_counts,
           "overlap_researchers": overlap_researchers, "overlap_orgs_assets": overlap_orgs,
           "multi_gene_studies": multi_studies, "overlap_sponsors": overlap_sponsors,
           "same_name_different_institution": name_collisions, "dropped": dropped,
           "gaps": [g["id"] for g in gaps]}
write_json(RAW / "build_summary.json", summary)
print(json.dumps({k: summary[k] for k in ("counts", "edge_counts", "pubmed_relevant_papers")}, indent=1))
print("multi-gene studies:", multi_studies)
print("overlap orgs/assets:", overlap_orgs)
print("overlap sponsors:", overlap_sponsors)
print("overlap researchers:", json.dumps(overlap_researchers, indent=0))
print("name collisions:", name_collisions)
print("dropped:", json.dumps(dropped, indent=0, ensure_ascii=False)[:3000])
print("gaps:", [g["id"] for g in gaps])
