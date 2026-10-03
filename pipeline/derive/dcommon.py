"""Shared helpers for the derived-data products (stdlib only).

Reuses the biology layer's NCBI client (pipeline/biology/common.py): a cross-process <=2 req/s
throttle, tool=rare-disease-atlas, no email parameter, exponential backoff on 429/5xx.
Everything this layer fetches is cached under data/raw/derive/.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_bio_common = _load_module("bio_common", ROOT / "pipeline" / "biology" / "common.py")
eutils = _bio_common.eutils  # biology layer's throttled E-utilities client (shared lock file)

GRAPH = ROOT / "data" / "graph.json"
DERIVED = ROOT / "data" / "derived"
CURATED = ROOT / "data" / "curated"
RAW_DERIVE = ROOT / "data" / "raw" / "derive"
PM_DIR = RAW_DERIVE / "pubmed"
BIO_RAW = ROOT / "data" / "raw" / "biology"
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
TODAY = _dt.date.today().isoformat()

SLICE_GENES = ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B", "SYT2", "CPLX1", "UNC13A", "STX1A",
               "NSF", "SLC6A1"]

for d in (DERIVED, PM_DIR):
    d.mkdir(parents=True, exist_ok=True)


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def write_json(path, obj, compact: bool = False) -> int:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1)
    path.write_text(text + "\n")
    return len(text.encode())


class Graph:
    """Read-only index over data/graph.json."""

    def __init__(self, path=GRAPH):
        g = read_json(path)
        self.meta = g["meta"]
        self.nodes = {n["id"]: n for n in g["nodes"]}
        self.edges = {e["id"]: e for e in g["edges"]}
        self.clusters = g["clusters"]
        self.gaps = g["gaps"]
        self.out = defaultdict(list)
        self.inc = defaultdict(list)
        for e in g["edges"]:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)

    def edges_of(self, etype, source=None, target=None):
        pool = self.out[source] if source else (self.inc[target] if target else self.edges.values())
        return [e for e in pool if e["type"] == etype and (target is None or e["target"] == target)
                and (source is None or e["source"] == source)]

    def has(self, edge_id):
        return edge_id in self.edges


# ---------------------------------------------------------------- PubMed (stored under data/raw/derive)

def _text(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def parse_article(art) -> dict:
    mc = art.find("MedlineCitation")
    pmid = mc.findtext("PMID")
    a = mc.find("Article")
    sections = [{"label": at.get("Label"), "text": _text(at)} for at in a.findall("Abstract/AbstractText")]
    abstract = " ".join((f"{s['label']}: " if s["label"] else "") + s["text"] for s in sections)
    authors = []
    for au in a.findall("AuthorList/Author"):
        if au.findtext("CollectiveName"):
            authors.append(au.findtext("CollectiveName"))
        else:
            authors.append(" ".join(x for x in [au.findtext("LastName"), au.findtext("Initials")] if x))
    j = a.find("Journal")
    journal = j.findtext("Title") or j.findtext("ISOAbbreviation")
    year = j.findtext("JournalIssue/PubDate/Year")
    if not year:
        md = j.findtext("JournalIssue/PubDate/MedlineDate") or ""
        year = md[:4] if md[:4].isdigit() else None
    if not year:
        year = a.findtext("ArticleDate/Year")
    pub_types = [_text(p) for p in a.findall("PublicationTypeList/PublicationType")]
    return {"pmid": pmid, "title": _text(a.find("ArticleTitle")), "abstract": abstract,
            "abstract_sections": sections, "authors": authors[:6] + (["et al."] if len(authors) > 6 else []),
            "journal": journal, "year": int(year) if year else None, "pub_types": pub_types,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "source": "NCBI E-utilities efetch (XML)",
            "retrieved": TODAY}


def fetch_pmids(pmids, refresh=False) -> dict:
    pmids = [str(p).replace("PMID:", "").strip() for p in pmids]
    todo = [p for p in dict.fromkeys(pmids) if refresh or not (PM_DIR / f"{p}.json").exists()]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        root = ET.fromstring(eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}))
        for art in root.findall("PubmedArticle"):
            rec = parse_article(art)
            write_json(PM_DIR / f"{rec['pmid']}.json", rec)
    return {p: read_json(PM_DIR / f"{p}.json") for p in pmids if (PM_DIR / f"{p}.json").exists()}


def esearch(term: str, retmax: int = 15) -> list:
    body = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json",
                                   "sort": "relevance"})
    return json.loads(body)["esearchresult"]["idlist"]


# ---------------------------------------------------------------- verbatim quotes

def _norm(s: str) -> str:
    s = s.replace(" ", " ").replace(" ", " ")
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[‐-―]", "-", s)
    return " ".join(s.split())


def sentences(text: str) -> list:
    # split on sentence end followed by a capital/digit; keep abbreviations like "e.g." intact
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])", text)
    return [p.strip() for p in parts if p.strip()]


def source_text(ref: str) -> str:
    """Stored text of a source: data/raw/derive/pubmed/<PMID>.json (title + abstract)."""
    pmid = ref.replace("PMID:", "")
    rec = read_json(PM_DIR / f"{pmid}.json")
    return rec["title"] + " " + rec["abstract"]


def quote_for(ref: str, needle: str) -> str:
    """Return the single sentence of the stored source that contains `needle` (verbatim)."""
    hits = [s for s in sentences(source_text(ref)) if _norm(needle).lower() in _norm(s).lower()]
    if len(hits) != 1:
        raise ValueError(f"needle {needle!r} matched {len(hits)} sentences in {ref}")
    return hits[0]


def verify_quote(ref: str, quote: str) -> bool:
    return _norm(quote) in _norm(source_text(ref))


def pub_evidence(ref: str, needle: str, study_type: str, supports: bool = True) -> dict:
    rec = read_json(PM_DIR / f"{ref.replace('PMID:', '')}.json")
    q = quote_for(ref, needle)
    ev = {"source": "PubMed", "ref": ref, "url": rec["url"], "title": rec["title"], "year": rec["year"],
          "quote": q, "kind": "publication", "study_type": study_type, "extracted_by": "agent-curation",
          "verified": verify_quote(ref, q), "retrieved": rec.get("retrieved", TODAY)}
    if not supports:
        ev["supports"] = False
    return ev
