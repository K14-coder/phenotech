"""Build the DEE community fragment from stored raw records + quote-verified curation.

Inputs (all under data/raw/families/dee/community/, re-fetchable with fetch_*.py):
  web/*.txt|html + web/_manifest.json   organisation / registry pages
  ctgov/*.json                           ClinicalTrials.gov API v2 responses
  reporter/*.json                        NIH RePORTER v2 responses
  pipeline/families/dee/community/curated.json   agent curation (quotes string-matched here)
  data/graph.json                        existing node / edge ids (never re-emitted)
Outputs:
  data/raw/families/dee/community/community_fragment.json  {nodes, edges, gaps}
  data/raw/families/dee/community/summary.json
Every Website quote is string-matched against the stored page; CT.gov / RePORTER quotes are copied
verbatim from the stored records and re-checked. Anything that fails is dropped and listed in
summary.json["dropped"].
Usage: python3 build_community.py
"""
from __future__ import annotations

import ast
import glob
import html as htmlmod
import json
import re
from collections import Counter, defaultdict

from dee_common import (CTGOV, FAMILY, GENE_LIST, GENE_RX, GENES, PIPE, PUBMED, RAW, REPORTER, ROOT, SYN_RX, WEB,
                        bd_used, norm, read_json, slugify, today, write_json)

TODAY = today()
GRAPH = read_json(ROOT / "data" / "graph.json")
LAYER = "dee-community"
MY_NODE_TYPES = {"patient_org", "asset", "grant", "researcher", "study"}


def _mine_node(n: dict) -> bool:
    """Items this layer emitted earlier and that were merged into data/graph.json are not 'existing'."""
    a = n.get("attrs") or {}
    return a.get("layer") == LAYER or (a.get("family") == FAMILY and n["type"] in MY_NODE_TYPES)


EXISTING_NODES = {n["id"]: n for n in GRAPH["nodes"] if not _mine_node(n)}
_MINE_IN_GRAPH = {n["id"] for n in GRAPH["nodes"] if _mine_node(n)}
EXISTING_EDGES = {e["id"] for e in GRAPH["edges"]
                  if (e.get("attrs") or {}).get("layer") != LAYER and e["source"] not in _MINE_IN_GRAPH
                  and e["target"] not in _MINE_IN_GRAPH}
MANIFEST = read_json(WEB / "_manifest.json")
CUR = read_json(PIPE / "curated.json")
DIS = lambda g: f"disease:{g}"  # noqa: E731

nodes: dict[str, dict] = {}
edges: dict[str, dict] = {}
dropped: list[dict] = []
referenced_existing: set[str] = set()


# ---------------------------------------------------------------- evidence helpers
_web_cache: dict[tuple, str] = {}


def web_text(src: str, in_html: bool) -> str:
    key = (src, in_html)
    if key not in _web_cache:
        p = WEB / f"{src}.{'html' if in_html else 'txt'}"
        t = p.read_text() if p.exists() else ""
        _web_cache[key] = norm(htmlmod.unescape(t) if in_html else t)
    return _web_cache[key]


def web_ev(e: dict, title: str | None = None) -> dict | None:
    src, quote, in_html = e["src"], e["quote"], e.get("in") == "html"
    m = MANIFEST.get(src, {})
    if m.get("status") != 200:
        dropped.append({"src": src, "quote": quote, "why": f"page status {m.get('status')}"})
        return None
    if norm(quote) not in web_text(src, in_html):
        dropped.append({"src": src, "quote": quote, "why": "quote not found in stored page"})
        return None
    ev = {"source": "Website", "ref": m["url"], "url": m["url"]}
    if title:
        ev["title"] = title
    ev.update({"quote": quote, "kind": "website", "extracted_by": "agent-curation", "verified": True,
               "retrieved": m.get("retrieved", TODAY)})
    return ev


def add_node(n: dict):
    nid = n["id"]
    if nid in EXISTING_NODES:
        referenced_existing.add(nid)
        return None
    if nid in nodes:
        old = nodes[nid]
        for s in n.get("sources", []):
            if s not in old.setdefault("sources", []):
                old["sources"].append(s)
        for k, v in (n.get("attrs") or {}).items():
            old.setdefault("attrs", {}).setdefault(k, v)
        return old
    n = dict(n, attrs=dict(n.get("attrs") or {}, layer=LAYER))
    nodes[nid] = {k: v for k, v in n.items() if v not in (None, [], {}, "")}
    if "attrs" in nodes[nid]:
        nodes[nid]["attrs"] = {k: v for k, v in nodes[nid]["attrs"].items() if v not in (None, [], {}, "")}
    return nodes[nid]


def node_exists(nid: str) -> bool:
    return nid in nodes or nid in EXISTING_NODES


def add_edge(source, target, etype, explanation, evidence, level, confidence, label=None, attrs=None, status="supported"):
    evidence = [e for e in evidence if e]
    eid = f"{source}|{etype}|{target}"
    if not evidence:
        dropped.append({"edge": eid, "why": "no verified evidence"})
        return None
    if eid in EXISTING_EDGES:
        dropped.append({"edge": eid, "why": "edge already exists in data/graph.json (not re-emitted)"})
        return None
    for nid in (source, target):
        if nid in EXISTING_NODES:
            referenced_existing.add(nid)
    if eid in edges:
        ex = edges[eid]
        seen = {(e["ref"], e.get("quote")) for e in ex["evidence"]}
        for e in evidence:
            if (e["ref"], e.get("quote")) not in seen:
                ex["evidence"].append(e)
        ex["confidence"] = round(max(ex["confidence"], confidence), 2)
        return ex
    edge = {"id": eid, "source": source, "target": target, "type": etype}
    if label:
        edge["label"] = label
    edge.update({"explanation": explanation, "evidence_level": level, "status": status,
                 "confidence": round(confidence, 2), "evidence": evidence})
    edge["attrs"] = dict(attrs or {}, layer=LAYER)
    edges[eid] = edge
    return edge


# ---------------------------------------------------------------- 1. patient organisations
for o in CUR["orgs"]:
    evs = [x for x in (web_ev(e, o["label"]) for e in o["evidence"]) if x]
    if not evs:
        dropped.append({"org": o["id"], "why": "no verified evidence"})
        continue
    attrs = {"url": o["url"], "country": o.get("country"), "scope": o.get("scope"), "family": FAMILY,
             **(o.get("attrs_extra") or {})}
    add_node({"id": o["id"], "type": "patient_org", "label": o["label"], "summary": o.get("summary"),
              "attrs": attrs, "sources": evs})
    for g, cfg in o["serves"].items():
        sev = [x for x in (web_ev(e, o["label"]) for e in cfg["evidence"]) if x]
        match = cfg.get("match", "gene")
        expl = cfg.get("explanation") or f"{o['label']} states on its own website that it serves people with {g}-related disorders."
        add_edge(o["id"], DIS(g), "serves", expl, sev, "observational", cfg.get("confidence", 0.9),
                 label="serves", attrs={"match": match, "family": FAMILY})

# ---------------------------------------------------------------- 2. registries / natural history / data assets
for a in CUR["assets"]:
    evs = [x for x in (web_ev(e, a["label"]) for e in a["evidence"]) if x]
    if not evs:
        dropped.append({"asset": a["id"], "why": "no verified evidence"})
        continue
    attrs = {"kind": a["kind"], "url": a.get("url"), "access": a.get("access"), "status": a.get("status"), "family": FAMILY}
    add_node({"id": a["id"], "type": "asset", "label": a["label"], "summary": evs[0]["quote"][:300],
              "attrs": attrs, "sources": evs})
    for g in a.get("covers", []):
        add_edge(a["id"], DIS(g), "covers",
                 a.get("covers_explanation") or f"{a['label']} collects data from people with {g}-related disorders, according to the cited page.",
                 evs, "observational", a.get("covers_confidence", 0.85), label="covers", attrs={"family": FAMILY})
    for org in a.get("maintained_by", []):
        if node_exists(org):
            add_edge(org, a["id"], "maintains",
                     a.get("maintains_explanation") or f"{(nodes.get(org) or EXISTING_NODES.get(org))['label']} runs {a['label']}, according to the cited page.",
                     evs, "observational", 0.85, label="runs")

# ---------------------------------------------------------------- 3. edges from existing graph nodes
for x in CUR["existing_edges"]:
    src = x["source"]
    if not node_exists(src):
        dropped.append({"existing_edge": x, "why": "source node not found"})
        continue
    evs = [y for y in (web_ev(e) for e in x["evidence"]) if y]
    if x["type"] == "maintains":
        if not node_exists(x["asset"]):
            dropped.append({"existing_edge": x, "why": "asset node not found"})
            continue
        add_edge(src, x["asset"], "maintains", x["explanation"], evs, "observational", x["confidence"],
                 label=x.get("label", "runs / partners on"))
    elif x["type"] == "covers":
        add_edge(src, DIS(x["gene"]), "covers", x["explanation"], evs, "observational", x["confidence"],
                 label="covers", attrs={"family": FAMILY})
    elif x["type"] == "serves":
        add_edge(src, DIS(x["gene"]), "serves", x["explanation"], evs, x.get("level", "observational"), x["confidence"],
                 label="serves (umbrella)", attrs={"match": "umbrella", "family": FAMILY})

# ---------------------------------------------------------------- 4. ClinicalTrials.gov studies
THERAPY_RX = [  # (therapy id, regex on the intervention name) -- only the therapy ids the biology agent creates
    ("therapy:fenfluramine", r"fenfluramine|ZX008|Fintepla"),
    ("therapy:stiripentol", r"stiripentol|Diacomit"),
    ("therapy:cannabidiol", r"cannabidiol|GWP42003|Epidiolex|Epidyolex"),
    ("therapy:ganaxolone", r"ganaxolone|Ztalmy"),
    ("therapy:ketogenic-diet", r"ketogenic"),
    ("therapy:zorevunersen", r"zorevunersen|STK-001"),
    ("therapy:etx101", r"ETX-?101"),
    ("therapy:elsunersen", r"elsunersen|PRAX-?222"),
    ("therapy:relutrigine", r"relutrigine|PRAX-?562"),
    ("therapy:nbi-921352", r"NBI-?921352|XEN-?901"),
    ("therapy:quinidine", r"quinidine"),
    ("therapy:kv7-openers", r"ezogabine|retigabine|XEN-?496|XEN-?1101|azetukalner"),
    ("therapy:radiprodil", r"radiprodil"),
    ("therapy:l-serine", r"\bL-serine\b|\bserine\b"),
    ("therapy:triheptanoin", r"triheptanoin|UX007|Dojolvi"),
    ("therapy:soticlestat", r"soticlestat|TAK-?935"),
    ("therapy:sodium-channel-blockers", r"carbamazepine|oxcarbazepine|phenytoin|lacosamide|lamotrigine"),
]
THERAPY_RX = [(t, re.compile(r, re.I)) for t, r in THERAPY_RX]
GENE_TARGETED = {"therapy:zorevunersen", "therapy:etx101", "therapy:elsunersen", "therapy:relutrigine", "therapy:nbi-921352",
                 "therapy:kv7-openers", "therapy:quinidine", "therapy:radiprodil", "therapy:l-serine", "therapy:triheptanoin"}
APPROVED_OR_PIVOTAL = {"therapy:fenfluramine", "therapy:stiripentol", "therapy:cannabidiol", "therapy:ganaxolone",
                       "therapy:soticlestat", "therapy:ketogenic-diet"}
OFF_TARGET_RX = re.compile(r"cancer|tumou?r|carcinoma|lymphoma|leuk[a]?emia|glioma|melanoma|diabet|obes|alzheimer|parkinson|"
                           r"cardiac|myocard|heart|stroke|malaria|arrhythm", re.I)
NEG_RX = re.compile(r"\b(not|no|without|excluded?|exclusion|other than|except|non-)\b", re.I)
DISORDER_RX = re.compile(r"variant|mutation|patholog|diagnos|confirm|encephalopath|epilep|seizure|syndrome|disorder|deficien|de novo|gene", re.I)
STUDY_CAP = 48
PER_GENE_CAP = {g: 8 for g in GENE_LIST}
PER_GENE_CAP["SCN1A"] = 13

raw_studies: dict[str, tuple] = {}
for f in sorted(glob.glob(str(CTGOV / "*.json"))):
    if f.endswith("_queries.json"):
        continue
    d = read_json(f)
    for s in d.get("studies", []):
        nct = s["protocolSection"]["identificationModule"]["nctId"]
        raw_studies.setdefault(nct, (s, d["retrieved"], f.split("/")[-1]))


def all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_strings(v)


def record_text(s) -> str:
    return norm(" | ".join(all_strings(s)))


def study_fields(s):
    ps = s["protocolSection"]
    im, cm, em = ps["identificationModule"], ps.get("conditionsModule", {}), ps.get("eligibilityModule", {})
    crit = em.get("eligibilityCriteria") or ""
    m = re.search(r"exclusion criteria", crit, re.I)
    incl = crit[:m.start()] if m else crit
    return {"title": im.get("briefTitle") or "", "otitle": im.get("officialTitle") or "",
            "conds": cm.get("conditions") or [], "kws": cm.get("keywords") or [],
            "incl_lines": [ln.strip().lstrip("*-•·").strip() for ln in incl.split("\n") if ln.strip()],
            "ivs": [i.get("name") or "" for i in ps.get("armsInterventionsModule", {}).get("interventions", [])]}


# CT.gov matching uses gene SYMBOLS only (protein aliases such as "Nav1.6" match mechanism keywords of
# trials in unrelated populations), and only title / conditions / inclusion criteria (never keywords).
CT_GENE_RX = {g: re.compile(rf"\b{g}\b", re.I) for g in GENE_LIST}
CT_GENE_RX["SYNGAP1"] = re.compile(r"\bSYNGAP1?\b", re.I)


def _window(txt: str, m: re.Match, width: int = 160) -> str:
    """Verbatim substring of a long eligibility line around the match, cut at word boundaries."""
    a, b = max(0, m.start() - width), min(len(txt), m.end() + width)
    if a > 0:
        a = txt.find(" ", a) + 1 or a
    if b < len(txt):
        b = txt.rfind(" ", m.end(), b) if txt.rfind(" ", m.end(), b) > 0 else b
    return txt[a:b].strip()


def find_match(f, g):
    """Return (match_kind, quote, where) for gene g, or None. Gene name beats syndrome name."""
    grx, srx = CT_GENE_RX[g], SYN_RX[g]
    items = [("condition list", c) for c in f["conds"]] + [("title", f["title"]), ("official title", f["otitle"])]
    elig = [("inclusion criteria", ln) for ln in f["incl_lines"]]
    for rx, kind in ((grx, "gene"), (srx, "syndrome")):
        for where, txt in items:
            if txt and rx.search(txt) and not OFF_TARGET_RX.search(txt):
                return kind, txt, where
        for where, txt in elig:
            m = rx.search(txt)
            if m and not OFF_TARGET_RX.search(txt) and not NEG_RX.search(txt) and DISORDER_RX.search(txt):
                return kind, (txt if len(txt) <= 400 else _window(txt, m)), where
            if m and len(txt) > 400 and not NEG_RX.search(_window(txt, m)) and not OFF_TARGET_RX.search(_window(txt, m)):
                return kind, _window(txt, m), where
    return None


candidates = []
for nct, (s, retrieved, fname) in raw_studies.items():
    f = study_fields(s)
    if OFF_TARGET_RX.search(f["title"] + " " + " ".join(f["conds"])):
        continue
    hits = {}
    for g in GENE_LIST:
        m = find_match(f, g)
        if m and m[1]:
            hits[g] = m
    if not hits:
        continue
    ps = s["protocolSection"]
    dm, stm = ps.get("designModule", {}), ps["statusModule"]
    stype = (dm.get("studyType") or "").lower()
    phases = dm.get("phases") or []
    ther = sorted({t for iv in f["ivs"] for t, rx in THERAPY_RX if rx.search(iv)})
    if stype == "interventional" and set(ther) & GENE_TARGETED:
        p = 3.0
    elif stype == "interventional" and set(ther) & APPROVED_OR_PIVOTAL and "PHASE3" in phases:
        p = 2.5
    elif stype == "interventional" and set(ther) & APPROVED_OR_PIVOTAL:
        p = 1.6
    elif stype == "observational" and re.search(r"natural history|registry|longitudinal|cohort|biomarker", f["title"] + " " + f["otitle"], re.I):
        p = 2.0
    elif stype == "observational":
        p = 1.2
    else:
        p = 0.8
    if any(m[0] == "gene" for m in hits.values()):
        p += 0.3
    start = (stm.get("startDateStruct") or {}).get("date") or ""
    candidates.append((p, start, nct, hits, ther, s, retrieved))

candidates.sort(key=lambda x: (-x[0], -(int(x[1][:4]) if x[1][:4].isdigit() else 0)))
selected, chosen, per_gene = [], set(), Counter()


def n_new():
    return sum(1 for x in selected if f"study:{x[2]}" not in EXISTING_NODES)


def take(c):
    if c[2] in chosen:
        return
    chosen.add(c[2])
    selected.append(c)
    if f"study:{c[2]}" not in EXISTING_NODES:
        for g in c[3]:
            per_gene[g] += 1


for c in candidates:                       # existing graph study nodes: edges only, never re-emitted, not counted
    if f"study:{c[2]}" in EXISTING_NODES:
        take(c)
for g in GENE_LIST:                        # pass A: best study per (gene, listed therapy) -> every drug represented
    for t in sorted({t for c in candidates for t in c[4] if g in c[3]}):
        pool = [c for c in candidates if g in c[3] and t in c[4] and c[2] not in chosen]
        pivotal = [c for c in pool if t in APPROVED_OR_PIVOTAL and "PHASE3" in (raw_studies[c[2]][0]["protocolSection"].get("designModule", {}).get("phases") or [])]
        # approved drugs: the earliest Phase 3 record is the pivotal trial; otherwise highest priority
        best = min(pivotal, key=lambda c: c[1] or "9999") if pivotal else (pool[0] if pool else None)
        if best and n_new() < STUDY_CAP:
            take(best)
for g in GENE_LIST:                        # pass B: at least 3 studies per gene where available
    for c in [c for c in candidates if g in c[3]]:
        if per_gene[g] >= 3 or n_new() >= STUDY_CAP:
            break
        take(c)
for c in candidates:                       # pass C: fill by priority
    if n_new() >= STUDY_CAP:
        break
    if c[2] in chosen or all(per_gene[g] >= PER_GENE_CAP[g] for g in c[3]):
        continue
    take(c)

study_log = []
for p, start, nct, hits, ther, s, retrieved in selected:
    ps = s["protocolSection"]
    f = study_fields(s)
    rtext = record_text(s)
    im, stm, dm = ps["identificationModule"], ps["statusModule"], ps.get("designModule", {})
    spm = ps.get("sponsorCollaboratorsModule", {})
    stype = (dm.get("studyType") or "").lower() or None
    phases = dm.get("phases") or []
    url = f"https://clinicaltrials.gov/study/{nct}"
    notes = []
    for g, (kind, q, where) in sorted(hits.items()):
        if kind == "gene":
            notes.append(f"{g} named in the {where}")
        else:
            notes.append(f"{GENES[g]['syndromes'][0]} named in the {where}; no {g} requirement found in the record")
    attrs = {"status": stm.get("overallStatus"), "study_type": stype, "phase": "/".join(phases) if phases else None,
             "start": (stm.get("startDateStruct") or {}).get("date"), "sponsor": (spm.get("leadSponsor") or {}).get("name"),
             "collaborators": [c.get("name") for c in spm.get("collaborators", [])] or None,
             "enrollment": (dm.get("enrollmentInfo") or {}).get("count"), "interventions": f["ivs"] or None,
             "conditions": f["conds"] or None, "eligibility_note": "; ".join(notes), "url": url, "family": FAMILY,
             "dee_genes": sorted(hits)}
    base = {"source": "ClinicalTrials.gov", "ref": nct, "url": url, "title": im.get("briefTitle"), "kind": "trial",
            "study_type": "clinical_trial" if stype == "interventional" else "database_record",
            "extracted_by": "database", "verified": True, "retrieved": retrieved}
    if norm(im.get("briefTitle") or "") in rtext:
        add_node({"id": f"study:{nct}", "type": "study", "label": im.get("briefTitle"),
                  "summary": (ps.get("descriptionModule", {}).get("briefSummary") or "")[:300] or None,
                  "xrefs": {"NCT": nct}, "attrs": attrs, "sources": [dict(base, quote=im.get("briefTitle"))]})
    for g, (kind, q, where) in sorted(hits.items()):
        if norm(q) not in rtext:
            dropped.append({"study": nct, "gene": g, "quote": q, "why": "quote not in record"})
            continue
        if kind == "gene":
            expl = f"{nct} names {g} in its {where}, so people with {g}-related disorders are studied."
            conf = 0.9
        else:
            syn = GENES[g]["syndromes"][0]
            expl = (f"{nct} names {syn} in its {where} but does not require a {g} variant, so this link is at syndrome level "
                    f"(not every person with {syn} has a {g} variant).")
            conf = 0.7
        add_edge(f"study:{nct}", DIS(g), "studies", expl, [dict(base, quote=q)], "clinical", conf,
                 label="enrols / studies", attrs={"match": kind, "family": FAMILY})
    for iv in f["ivs"]:
        for tid, rx in THERAPY_RX:
            if rx.search(iv):
                if tid == "therapy:sodium-channel-blockers" and not any(k == "gene" for k, _, _ in hits.values()):
                    continue
                if norm(iv) not in rtext:
                    continue
                add_edge(f"study:{nct}", tid, "tests", f"{nct} lists '{iv}' as an intervention.",
                         [dict(base, quote=iv)], "clinical" if stype == "interventional" else "observational", 0.9,
                         label="tests")
    study_log.append({"nct": nct, "priority": p, "genes": {g: h[0] for g, h in hits.items()}, "therapies": ther,
                      "existing_node": f"study:{nct}" in EXISTING_NODES})

# ---------------------------------------------------------------- 5. researchers from NIH RePORTER (max 3 per gene)
src = (ROOT / "pipeline" / "community" / "build_community.py").read_text()
INST_PATTERNS = next(ast.literal_eval(n.value) for n in ast.parse(src).body
                     if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "INST_PATTERNS")
INST_RX = [(re.compile(p, re.I), s) for p, s in INST_PATTERNS]
INST_WORD = re.compile(r"(Universit|Hospital|Institut|College|Center|Centre|School|Klinik|Clinic|Foundation|Laborator|Hôpital|Ospedale|Hospices)", re.I)


def inst_key(aff: str) -> tuple[str, str]:
    """Same mapping as pipeline/community/build_community.py so researcher ids line up across layers."""
    for rx, slug in INST_RX:
        if rx.search(aff or ""):
            return slug, slug.replace("-", " ").title()
    parts = [p.strip(" .;") for p in re.split(r"[,;]", aff or "") if p.strip(" .;")]
    for p in parts:
        if INST_WORD.search(p) and not re.match(r"(Department|Dept|Division|Section|Laboratory of|Program|Unit)\b", p, re.I):
            return slugify(p, 50), p
    return (slugify(parts[0], 50), parts[0]) if parts else ("unknown", "unknown")


def tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in s.split(" "))


MONO_RX = re.compile(r"patient|mutation|variant|encephalopath|epilep|seizure|de novo|haploinsufficien|intellectual disability|"
                     r"developmental delay|related disorder|deficiency|syndrome|children|ataxia|migraine", re.I)
OTHER_RX = re.compile(r"alzheimer|parkinson|cancer|tumou?r|schizophren|bipolar|addict|alcohol|opioid|\bpain\b|stroke|"
                      r"cardiac|diabet|autism spectrum disorder \(ASD\) and schizophrenia", re.I)


def sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text or "") if x.strip()]


TERM_GENE = {"dravet-syndrome": "SCN1A", "cdkl5-deficiency-disorder": "CDKL5", "glut1-deficiency": "SLC2A1"}
projects: dict[str, dict] = {}
for fpath in sorted(glob.glob(str(REPORTER / "*.json"))):
    d = read_json(fpath)
    for r in d["response"].get("results", []):
        core = r.get("core_project_num") or r.get("project_num")
        if not core:
            continue
        prev = projects.get(core)
        if prev is None or (r.get("fiscal_year") or 0) > (prev["rec"].get("fiscal_year") or 0):
            projects[core] = {"rec": r, "retrieved": d["retrieved"], "fys": (prev or {}).get("fys", set())}
        projects[core]["fys"].add(r.get("fiscal_year"))

pi_hits = defaultdict(lambda: defaultdict(list))  # gene -> rid -> [(core, quote, fy)]
people: dict[str, dict] = {}
for core, pr in projects.items():
    r = pr["rec"]
    title, abstract = r.get("project_title") or "", r.get("abstract_text") or ""
    if OTHER_RX.search(title):
        continue
    for g in GENE_LIST:
        rx_t = GENE_RX[g].search(title) or SYN_RX[g].search(title)
        if not rx_t:
            continue  # gene / syndrome must be the focus: named in the project title
        quote = None
        for s_ in [title] + sentences(abstract):
            if (GENE_RX[g].search(s_) or SYN_RX[g].search(s_)) and MONO_RX.search(s_) and not OTHER_RX.search(s_) and len(s_) <= 600:
                # drop a leading section header ("PROJECT SUMMARY", "ABSTRACT", ...): the rest stays a verbatim substring
                quote = re.sub(r"^(?:PROJECT SUMMARY/ABSTRACT|PROJECT SUMMARY|Project Summary/Abstract|Project Summary|"
                               r"SUMMARY|ABSTRACT|Abstract)\s*[:.]?\s+", "", s_).strip()
                break
        if not quote:
            continue
        org = (r.get("organization") or {}).get("org_name") or ""
        for p in r.get("principal_investigators") or []:
            first, last = tidy(p.get("first_name", "")), tidy(p.get("last_name", ""))
            ik, iname = inst_key(org)
            rid = f"researcher:{slugify(f'{first} {last}', 50)}--{ik}"
            people.setdefault(rid, {"name": f"{first} {last}".strip(), "org": org, "inst": iname,
                                    "profile_id": p.get("profile_id")})
            pi_hits[g][rid].append((core, quote, r.get("fiscal_year") or 0))

RESEARCHERS_PER_GENE = 3
researchers_by_gene = {}
for g in GENE_LIST:
    ranked = sorted(pi_hits[g].items(), key=lambda kv: (-len({c for c, _, _ in kv[1]}), -max(fy for _, _, fy in kv[1])))
    researchers_by_gene[g] = [rid for rid, _ in ranked[:RESEARCHERS_PER_GENE]]
    for rid in researchers_by_gene[g]:
        info = people[rid]
        hits = sorted(pi_hits[g][rid], key=lambda h: -h[2])
        seen_core, evs = set(), []
        for core, quote, fy in hits:
            if core in seen_core or len(seen_core) >= 3:
                continue
            seen_core.add(core)
            pr = projects[core]
            r = pr["rec"]
            url = r.get("project_detail_url") or f"https://reporter.nih.gov/project-details/{r.get('appl_id')}"
            ev0 = {"source": "NIH RePORTER", "ref": core, "url": url, "title": r.get("project_title"), "year": r.get("fiscal_year"),
                   "kind": "grant", "study_type": "database_record", "extracted_by": "database", "verified": True,
                   "retrieved": pr["retrieved"]}
            gid = f"grant:{core}"
            pis = [tidy(f"{p.get('first_name', '')} {p.get('last_name', '')}") for p in r.get("principal_investigators") or []]
            add_node({"id": gid, "type": "grant", "label": r.get("project_title") if not (r.get("project_title") or "").isupper() else tidy(r.get("project_title")),
                      "attrs": {"title": r.get("project_title"), "pis": pis, "org": (r.get("organization") or {}).get("org_name"),
                                "fiscal_year": r.get("fiscal_year"), "fiscal_years": sorted(x for x in pr["fys"] if x),
                                "amount": r.get("award_amount"), "url": url, "activity_code": r.get("activity_code"), "family": FAMILY},
                      "sources": [dict(ev0, quote=r.get("project_title"))]})
            add_edge(gid, DIS(g), "about", f"The NIH project record ties {g} to the human disorder in its title or abstract.",
                     [dict(ev0, quote=quote)], "curated", 0.85 if GENE_RX[g].search(r.get("project_title") or "") else 0.75,
                     label="about", attrs={"family": FAMILY})
            add_edge(gid, rid, "funds", f"NIH project {core} lists this person as a principal investigator.",
                     [dict(ev0, quote=r.get("project_title"))], "curated", 0.95, label="funds")
            evs.append(dict(ev0, quote=quote))
        n = len(seen_core)
        attrs = {"affiliation": tidy(info["org"]) if info["org"].isupper() else info["org"],
                 "url": evs[0]["url"] if evs else None, "nih_profile_id": info.get("profile_id"),
                 "identity_basis": "NIH RePORTER principal-investigator record (name + organisation)", "family": FAMILY}
        add_node({"id": rid, "type": "researcher", "label": info["name"], "attrs": attrs, "sources": evs[:2]})
        add_edge(rid, DIS(g), "works_on",
                 f"Principal investigator on {n} NIH project{'s' if n > 1 else ''} (FY2020+) whose title names {g} or its syndrome and whose record ties it to the human disorder.",
                 evs, "observational", 0.8, label="works on", attrs={"family": FAMILY})

# same name at two institutions: NOT merged (no shared identifier); flag both nodes
by_name = defaultdict(list)
for nid, n in nodes.items():
    if n["type"] == "researcher":
        by_name[n["label"].lower()].append(nid)
for ids in by_name.values():
    if len(ids) > 1:
        for nid in ids:
            nodes[nid]["attrs"]["possible_same_person_as"] = [x for x in ids if x != nid]
            nodes[nid]["attrs"]["identity_note"] = ("Same name appears at another institution in NIH RePORTER. Not merged: "
                                                    "affiliations differ and no shared identifier was checked.")

# ---------------------------------------------------------------- 6. gaps
SEARCH_LOG = {
    "ctgov": read_json(CTGOV / "_queries.json") if (CTGOV / "_queries.json").exists() else [],
    "reporter_terms": sorted({read_json(p)["term"] for p in glob.glob(str(REPORTER / "*.json"))}),
    "pubmed": [{"gene": read_json(p)["gene"], "query": read_json(p)["query"], "count": read_json(p)["count"]}
               for p in sorted(glob.glob(str(PUBMED / "*.esearch.json")))],
    "web": [{"id": k, "url": v["url"], "status": v.get("status"), "via": v.get("via")} for k, v in sorted(MANIFEST.items())],
    "brightdata": bd_used(),
}


def gene_searches(g: str) -> list[str]:
    out = [f"ClinicalTrials.gov API v2 {q['param']}={q['value']!r} ({q['n']} records)" for q in SEARCH_LOG["ctgov"]
           if g.lower() in q["value"].lower() or any(s_.lower() in q["value"].lower() for s_ in GENES[g]["syndromes"])
           or (g == "SCN1A" and "dravet" in q["value"].lower()) or (g == "SLC2A1" and "glut1" in q["value"].lower())]
    out += [f"NIH RePORTER v2 projects/search '{t}' FY2020-2026" for t in SEARCH_LOG["reporter_terms"]
            if t.lower() == g.lower() or TERM_GENE.get(slugify(t)) == g]
    out += [f"{w['url']} (HTTP {w['status']}, via {w['via']})" for w in SEARCH_LOG["web"]
            if g.lower() in w["url"].lower() or g.lower() in w["id"]]
    out += [f"https://www.citizen.health/communities", "https://dee-p.org/deep-collaborative/ (partner logos)",
            "https://www.rareepilepsynetwork.org/members-partners", "https://combinedbrain.org/Membership (HTTP 302, PAG list not retrievable)"]
    for u in CUR["unverified"]:
        if u["gene"] == g:
            out += [f"{u['name']}: {t}" for t in u["tried"]]
    return out


gaps, coverage = [], {}
for g in GENE_LIST:
    d = DIS(g)
    ein = [e for e in edges.values() if e["target"] == d]
    orgs_specific = sorted({e["source"] for e in ein if e["type"] == "serves" and e["source"] in nodes})
    orgs_umbrella = sorted({e["source"] for e in ein if e["type"] == "serves" and e["source"] not in nodes})
    assets = sorted({e["source"] for e in ein if e["type"] == "covers"})
    st_int = sorted({e["source"] for e in ein if e["type"] == "studies" and
                     ((nodes.get(e["source"]) or EXISTING_NODES.get(e["source"]) or {}).get("attrs") or {}).get("study_type") == "interventional"})
    st_obs = sorted({e["source"] for e in ein if e["type"] == "studies"} - set(st_int))
    st_gene = sorted({e["source"] for e in ein if e["type"] == "studies" and (e.get("attrs") or {}).get("match") == "gene"})
    res = sorted({e["source"] for e in ein if e["type"] == "works_on"})
    grants = sorted({e["source"] for e in ein if e["type"] == "about"})
    coverage[g] = {"orgs_gene_specific": orgs_specific, "orgs_umbrella": orgs_umbrella, "assets": assets,
                   "studies_interventional": st_int, "studies_observational": st_obs, "studies_gene_match": st_gene,
                   "researchers": res, "grants": grants}
    missing = []
    if not orgs_specific:
        missing.append(f"No {g}-specific patient organisation verified on its own website.")
    if not [a for a in assets]:
        missing.append(f"No registry, natural history study or data platform verified for {g}.")
    if not st_int:
        missing.append(f"No interventional ClinicalTrials.gov record that names {g} or its gene-defined syndrome was found.")
    if not st_obs:
        missing.append(f"No observational / natural history ClinicalTrials.gov record that names {g} or its syndrome was found.")
    if st_int and not [s_ for s_ in st_int if s_ in st_gene]:
        missing.append(f"Interventional trials found only at syndrome level: none requires a {g} variant in the record.")
    if not res:
        missing.append(f"No NIH-funded principal investigator found with a {g}-titled project (FY2020+) tied to the disorder.")
    if g in ("SCN8A", "KCNQ2", "KCNT1", "CACNA1A", "CDKL5", "SLC2A1"):
        missing.append(f"Simons Searchlight has no {g} gene page (https://www.simonssearchlight.org/research/what-we-study/{g.lower()}/ returned HTTP 404) and its gene list does not include {g}.")
    for u in CUR["unverified"]:
        if u["gene"] == g:
            missing.append(f"{u['name']} could not be verified on its own website, so it is not in the graph.")
    if missing:
        gaps.append({"id": f"gap:dee-{g.lower()}-community", "about": d,
                     "question": f"What patient organisations, registries, trials and research groups exist for {g}-related disorders, beyond those verified here?",
                     "what_is_missing": missing, "searched": gene_searches(g),
                     "how_to_find_out": ("Ask the gene's patient organisation for its registry / natural history study and partner list; "
                                         "check Citizen Health, RARE-X and Simons Searchlight intake lists directly; search CT.gov and "
                                         "EU CTR / ISRCTN with syndrome synonyms; add PubMed senior-author groups (raw records already stored).")})

# ---------------------------------------------------------------- 7. write
node_list = sorted(nodes.values(), key=lambda n: (n["type"], n["id"]))
edge_list = sorted(edges.values(), key=lambda e: (e["type"], e["id"]))
frag = {"nodes": node_list, "edges": edge_list, "gaps": gaps}
write_json(RAW / "community_fragment.json", frag)

cross = {}
for nid in ("asset:simons-searchlight", "asset:citizen-health", "asset:rare-x-data-collection", "asset:combinedbrain-biorepository",
            "asset:endd-stxbp1-syngap1-center", "org:dee-p-connections", "org:rare-epilepsy-network", "study:NCT01238250",
            "study:NCT06555965", "study:NCT05232630", "study:NCT06585605", "study:NCT06967727"):
    old = sorted({e["target"] for e in GRAPH["edges"] if e["source"] == nid and e["target"].startswith("disease:")})
    new = sorted({e["target"] for e in edge_list if e["source"] == nid and e["target"].startswith("disease:")})
    if new:
        cross[nid] = {"existing_slice_diseases": old, "new_dee_diseases": new}

bd = bd_used()
summary = {
    "built": TODAY, "family": FAMILY,
    "counts": {"nodes_by_type": dict(Counter(n["type"] for n in node_list)), "edges_by_type": dict(Counter(e["type"] for e in edge_list)),
               "gaps": len(gaps), "existing_nodes_referenced": sorted(referenced_existing),
               "evidence_items": sum(len(e["evidence"]) for e in edge_list) + sum(len(n.get("sources", [])) for n in node_list)},
    "per_gene_coverage": {g: {k: len(v) for k, v in c.items()} for g, c in coverage.items()},
    "per_gene_detail": coverage,
    "cross_family_assets": cross,
    "studies_selected": study_log,
    "study_candidates_considered": len(candidates),
    "brightdata": {"requests_used": len(bd), "budget": 100, "log": bd},
    "searches": SEARCH_LOG,
    "dropped": dropped,
}
write_json(RAW / "summary.json", summary)
print(json.dumps({"nodes": summary["counts"]["nodes_by_type"], "edges": summary["counts"]["edges_by_type"], "gaps": len(gaps),
                  "dropped_quotes": [d_ for d_ in dropped if "quote" in d_ or "org" in d_ or "asset" in d_]}, indent=1))
