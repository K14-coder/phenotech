"""Independent verifier for data/raw/families/dee/community/community_fragment.json.

Re-reads every stored source from disk and string-matches every quote (NFKC, folded dashes and
curly quotes, collapsed whitespace), and checks the data contract. Exits non-zero on any failure.

  Website            -> web/_manifest.json (url -> page id, must be HTTP 200) -> web/<id>.txt (or unescaped .html)
  ClinicalTrials.gov -> every string field of the stored API v2 record for that NCT id (ctgov/*.json)
  NIH RePORTER       -> title + abstract of the stored project records with that core project number (reporter/*.json)
  PubMed             -> title + abstract of the stored efetch XML for that PMID (pubmed/*.efetch.xml)
Usage: python3 verify_community.py
"""
from __future__ import annotations

import glob
import html as htmlmod
import json
import re
import sys
import xml.etree.ElementTree as ET

from dee_common import CTGOV, EMAIL_RE, GENE_LIST, PUBMED, RAW, REPORTER, ROOT, WEB, norm, read_json

FRAG = read_json(RAW / "community_fragment.json")
GRAPH = read_json(ROOT / "data" / "graph.json")
LAYER = "dee-community"
_mine = {n["id"] for n in GRAPH["nodes"] if (n.get("attrs") or {}).get("layer") == LAYER
         or ((n.get("attrs") or {}).get("family") == "dee" and n["type"] in ("patient_org", "asset", "grant", "researcher", "study"))}
EXISTING_NODES = {n["id"] for n in GRAPH["nodes"]} - _mine   # this layer's own merged output is not "existing"
EXISTING_EDGES = {e["id"] for e in GRAPH["edges"] if (e.get("attrs") or {}).get("layer") != LAYER
                  and e["source"] not in _mine and e["target"] not in _mine}
ALLOWED_THERAPIES = {"therapy:fenfluramine", "therapy:stiripentol", "therapy:cannabidiol", "therapy:ganaxolone",
                     "therapy:ketogenic-diet", "therapy:zorevunersen", "therapy:etx101", "therapy:elsunersen",
                     "therapy:relutrigine", "therapy:nbi-921352", "therapy:quinidine", "therapy:kv7-openers",
                     "therapy:radiprodil", "therapy:l-serine", "therapy:triheptanoin", "therapy:soticlestat",
                     "therapy:sodium-channel-blockers"}
OUR_DISEASES = {f"disease:{g}" for g in GENE_LIST} | {f"gene:{g}" for g in GENE_LIST}
LEVELS = {"clinical", "curated", "experimental", "observational", "inferred", "hypothesis"}
SOURCES = {"Website", "ClinicalTrials.gov", "PubMed", "NIH RePORTER"}

failures: list[str] = []
checked = passed = 0

# ---------------------------------------------------------------- source stores
manifest = read_json(WEB / "_manifest.json")
url_to_page = {}
for pid, m in manifest.items():
    for u in (m.get("url"), m.get("final_url")):
        if u and m.get("status") == 200:
            url_to_page.setdefault(u, pid)
_page_cache: dict[tuple, str] = {}


def page_text(pid: str, kind: str) -> str:
    if (pid, kind) not in _page_cache:
        p = WEB / f"{pid}.{kind}"
        t = p.read_text() if p.exists() else ""
        _page_cache[(pid, kind)] = norm(htmlmod.unescape(t) if kind == "html" else t)
    return _page_cache[(pid, kind)]


def all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_strings(v)


ctgov: dict[str, list[str]] = {}
for f in glob.glob(str(CTGOV / "*.json")):
    if f.endswith("_queries.json"):
        continue
    for s in read_json(f).get("studies", []):
        nct = s["protocolSection"]["identificationModule"]["nctId"]
        ctgov.setdefault(nct, []).append(norm(" | ".join(all_strings(s))))

reporter: dict[str, list[str]] = {}
for f in glob.glob(str(REPORTER / "*.json")):
    for r in read_json(f)["response"].get("results", []):
        for key in {r.get("core_project_num"), r.get("project_num")} - {None}:
            reporter.setdefault(key, []).append(norm(f"{r.get('project_title') or ''} | {r.get('abstract_text') or ''}"))

pubmed: dict[str, str] = {}
for f in glob.glob(str(PUBMED / "*.efetch.xml")):
    for chunk in open(f).read().split("<!-- batch -->"):
        chunk = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", chunk).strip()
        if not chunk:
            continue
        for art in ET.fromstring(chunk).iter("PubmedArticle"):
            pmid = art.findtext(".//PMID")
            title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
            ab = " ".join("".join(a.itertext()) for a in art.findall(".//Abstract/AbstractText"))
            pubmed[pmid] = norm(title + " " + ab)


def check_quote(ev: dict, where: str) -> None:
    global checked, passed
    src, quote = ev.get("source"), ev.get("quote")
    if src in ("Website", "PubMed") and not quote:
        failures.append(f"{where}: {src} evidence without a quote")
        return
    if not quote:
        return
    checked += 1
    q = norm(quote)
    ok = False
    if src == "Website":
        pid = url_to_page.get(ev.get("url")) or url_to_page.get(ev.get("ref"))
        if not pid:
            failures.append(f"{where}: no stored HTTP-200 page for {ev.get('url')}")
            return
        ok = q in page_text(pid, "txt") or q in page_text(pid, "html")
    elif src == "ClinicalTrials.gov":
        ok = any(q in t for t in ctgov.get(ev.get("ref"), []))
    elif src == "NIH RePORTER":
        ok = any(q in t for t in reporter.get(ev.get("ref"), []))
    elif src == "PubMed":
        ok = q in pubmed.get(str(ev.get("ref", "")).replace("PMID:", ""), "")
    else:
        failures.append(f"{where}: unexpected evidence source {src}")
        return
    if not ok:
        failures.append(f"{where}: quote not found in stored {src} source: {quote[:120]!r}")
        return
    if ev.get("verified") is not True:
        failures.append(f"{where}: matched quote not marked verified")
        return
    passed += 1


def check_ev_shape(ev: dict, where: str) -> None:
    for k in ("source", "ref", "url", "kind", "extracted_by", "retrieved"):
        if not ev.get(k):
            failures.append(f"{where}: evidence missing {k}")
    if ev.get("source") not in SOURCES:
        failures.append(f"{where}: evidence source {ev.get('source')} not allowed here")
    if ev.get("extracted_by") not in ("agent-curation", "database"):
        failures.append(f"{where}: extracted_by {ev.get('extracted_by')}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ev.get("retrieved", "")):
        failures.append(f"{where}: bad retrieved date")


# ---------------------------------------------------------------- nodes
node_ids = set()
for n in FRAG["nodes"]:
    nid = n["id"]
    if nid in node_ids:
        failures.append(f"duplicate node {nid}")
    node_ids.add(nid)
    if nid in EXISTING_NODES:
        failures.append(f"node {nid} already exists in data/graph.json (must be referenced, not re-emitted)")
    if not n.get("sources"):
        failures.append(f"node {nid} has no sources")
    if n["type"] in ("patient_org", "asset", "study", "grant", "researcher") and (n.get("attrs") or {}).get("family") != "dee":
        failures.append(f"node {nid} lacks attrs.family = 'dee'")
    if n["type"] == "patient_org" and not (n.get("attrs") or {}).get("url"):
        failures.append(f"org {nid} lacks attrs.url")
    if n["type"] == "study" and not ((n.get("attrs") or {}).get("url") and (n.get("attrs") or {}).get("status")):
        failures.append(f"study {nid} lacks url/status")
    for i, ev in enumerate(n.get("sources", [])):
        check_ev_shape(ev, f"node {nid} source {i}")
        check_quote(ev, f"node {nid} source {i}")

# ---------------------------------------------------------------- edges
edge_ids = set()
for e in FRAG["edges"]:
    eid = e["id"]
    where = f"edge {eid}"
    if eid != f"{e['source']}|{e['type']}|{e['target']}":
        failures.append(f"{where}: id is not source|type|target")
    if eid in edge_ids:
        failures.append(f"{where}: duplicate edge")
    edge_ids.add(eid)
    if eid in EXISTING_EDGES:
        failures.append(f"{where}: already in data/graph.json")
    for end in (e["source"], e["target"]):
        if end not in node_ids and end not in EXISTING_NODES and end not in OUR_DISEASES and end not in ALLOWED_THERAPIES:
            failures.append(f"{where}: unknown endpoint {end}")
    if e["type"] == "tests" and e["target"] not in ALLOWED_THERAPIES:
        failures.append(f"{where}: tests edge to a therapy outside the agreed list")
    if e.get("evidence_level") not in LEVELS or e.get("status") not in ("supported", "contested", "unverified"):
        failures.append(f"{where}: bad evidence_level/status")
    if not (0 <= e.get("confidence", -1) <= 1):
        failures.append(f"{where}: confidence out of range")
    if not e.get("explanation"):
        failures.append(f"{where}: no explanation")
    if not e.get("evidence"):
        failures.append(f"{where}: no evidence")
    for i, ev in enumerate(e.get("evidence", [])):
        check_ev_shape(ev, f"{where} evidence {i}")
        check_quote(ev, f"{where} evidence {i}")

# ---------------------------------------------------------------- gaps + privacy
for g in FRAG["gaps"]:
    if not g["id"].startswith("gap:dee-") or g.get("about") not in OUR_DISEASES:
        failures.append(f"gap {g['id']}: bad id/about")
    for k in ("question", "what_is_missing", "searched", "how_to_find_out"):
        if not g.get(k):
            failures.append(f"gap {g['id']}: missing {k}")
blob = json.dumps(FRAG, ensure_ascii=False)
if EMAIL_RE.search(blob):
    failures.append(f"e-mail address found in fragment: {EMAIL_RE.search(blob).group(0)[:3]}...")

print(f"nodes={len(FRAG['nodes'])} edges={len(FRAG['edges'])} gaps={len(FRAG['gaps'])}")
print(f"quotes checked={checked} passed={passed} failures={len(failures)}")
for f_ in failures[:50]:
    print("  FAIL", f_)
sys.exit(1 if failures else 0)
