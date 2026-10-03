"""Shared helpers for the lysosomal storage disorder family (stdlib only).

Reuses, rather than copies, the project's existing plumbing:
  * pipeline/biology/common.py  -> NCBI E-utilities with the CROSS-PROCESS file-lock throttle
    (<= 2 req/s shared by every agent), tool=rare-disease-atlas, no email param, 429/5xx backoff.
  * pipeline/brightdata.py      -> Bright Data SERP / Web Unlocker client. Its cache directory is
    redirected to data/raw/families/lysosomal/brightdata/, and every *live* (uncached) request is
    counted in a ledger so the family never exceeds BRIGHTDATA_BUDGET requests.

Every remote payload is cached under data/raw/families/lysosomal/ so the fragment can be rebuilt
offline and every quote can be string-matched against the exact text we fetched.
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import html as _html
import importlib.util
import json
import pathlib
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RAW = ROOT / "data" / "raw" / "families" / "lysosomal"
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
FRAGMENT = ROOT / "data" / "curated" / "family_lysosomal.json"
GRAPH = ROOT / "data" / "graph.json"
RAW.mkdir(parents=True, exist_ok=True)
TODAY = _dt.date.today().isoformat()
FAMILY = "lysosomal"

# ------------------------------------------------------------------ the family
GENES = ["GBA1", "GAA", "GLA", "HEXA", "NPC1", "SMPD1", "IDUA", "IDS", "CLN3", "TPP1", "ARSA", "GALC"]

# ------------------------------------------------------------------ reuse biology/common.py
_spec = importlib.util.spec_from_file_location("bio_common", ROOT / "pipeline" / "biology" / "common.py")
bio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bio)  # type: ignore[union-attr]

http_get = bio.http_get          # (url, params, headers, data, retries, timeout, ncbi)
cached_json = bio.cached_json    # (cache_path, url, params, headers, refresh, ncbi, data)
cached_text = bio.cached_text
eutils = bio.eutils              # NCBI E-utilities through the shared throttle; strips any email param
edge_id = bio.edge_id


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def evidence(source: str, ref: str, url: str, kind: str, extracted_by: str = "database",
             title: str | None = None, year: int | None = None, quote: str | None = None,
             study_type: str | None = None, supports: bool | None = None,
             verified: bool | None = None, retrieved: str | None = None) -> dict:
    return bio.evidence(source, ref, url, kind, extracted_by=extracted_by, title=title, year=year,
                        quote=quote, study_type=study_type, supports=supports, verified=verified,
                        retrieved=retrieved)


# ------------------------------------------------------------------ text normalisation
def norm(s: str) -> str:
    """Normalisation used for every quote match (same folding as the biology verifier)."""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
         .replace(" ", " ").replace("​", ""))
    return " ".join(s.split())


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def redact_emails(text: str) -> str:
    return EMAIL_RE.sub("[email-redacted]", text or "")


_TRANS = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "å": "a", "Å": "A", "ß": "ss",
                        "ł": "l", "Ł": "L", "đ": "d"})


def slugify(s: str, maxlen: int = 60) -> str:
    s = unicodedata.normalize("NFKD", (s or "").translate(_TRANS)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-")


# ------------------------------------------------------------------ PubMed (efetch XML -> JSON)
PM_DIR = RAW / "pubmed"


def _text(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def parse_article(art) -> dict:
    mc = art.find("MedlineCitation")
    pmid = mc.findtext("PMID")
    a = mc.find("Article")
    title = _text(a.find("ArticleTitle"))
    sections = [{"label": at.get("Label"), "text": _text(at)} for at in a.findall("Abstract/AbstractText")]
    abstract = " ".join((f"{s['label']}: " if s["label"] else "") + s["text"] for s in sections)
    authors = []
    for au in a.findall("AuthorList/Author"):
        if au.findtext("CollectiveName"):
            authors.append({"name": au.findtext("CollectiveName")})
            continue
        affs = [redact_emails(_text(x)) for x in au.findall("AffiliationInfo/Affiliation")]
        orcid = None
        for idf in au.findall("Identifier"):
            if idf.get("Source") == "ORCID":
                orcid = re.sub(r"^https?://orcid.org/", "", (idf.text or "").strip())
        authors.append({"last": au.findtext("LastName"), "fore": au.findtext("ForeName"),
                        "initials": au.findtext("Initials"), "affiliations": affs, "orcid": orcid})
    j = a.find("Journal")
    journal = j.findtext("Title") or j.findtext("ISOAbbreviation")
    year = j.findtext("JournalIssue/PubDate/Year")
    if not year:
        md = j.findtext("JournalIssue/PubDate/MedlineDate") or ""
        year = md[:4] if md[:4].isdigit() else None
    if not year:
        year = a.findtext("ArticleDate/Year")
    doi = None
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = aid.text
    pub_types = [_text(p) for p in a.findall("PublicationTypeList/PublicationType")]
    return {"pmid": pmid, "title": title, "abstract": abstract, "abstract_sections": sections,
            "authors": authors, "journal": journal, "year": int(year) if year else None,
            "pub_types": pub_types, "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "source": "NCBI E-utilities efetch (XML)",
            "retrieved": TODAY}


def fetch_pmids(pmids, refresh: bool = False) -> dict:
    pmids = [str(p).replace("PMID:", "").strip() for p in pmids]
    PM_DIR.mkdir(parents=True, exist_ok=True)
    todo = [p for p in dict.fromkeys(pmids) if refresh or not (PM_DIR / f"{p}.json").exists()]
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        xml = eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
        root = ET.fromstring(xml)
        for art in root.findall("PubmedArticle"):
            rec = parse_article(art)
            write_json(PM_DIR / f"{rec['pmid']}.json", rec)
    return {p: read_json(PM_DIR / f"{p}.json") for p in pmids if (PM_DIR / f"{p}.json").exists()}


def esearch_pubmed(term: str, retmax: int = 30, sort: str = "relevance", **extra) -> list[str]:
    params = {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json", "sort": sort}
    params.update(extra)
    body = eutils("esearch.fcgi", params)
    return json.loads(body)["esearchresult"]["idlist"]


def pubmed_text(pmid: str) -> str | None:
    p = PM_DIR / f"{str(pmid).replace('PMID:', '')}.json"
    if not p.exists():
        return None
    r = read_json(p)
    return r["title"] + " " + r["abstract"]


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(“\"])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s.strip()]


def quote_for(ref: str, needle: str) -> str:
    """Verbatim sentence of a stored PubMed record (or trial / label text) that contains `needle`.
    Raises if the needle is missing or ambiguous, so a claim can never carry text that is not in
    the stored source."""
    txt = source_text_for_ref(ref)
    if txt is None:
        raise ValueError(f"no stored source for {ref}")
    n = norm(needle)
    sents = sentences(txt)
    hits = [s for s in sents if n in norm(s)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"needle ambiguous in {ref} ({len(hits)} sentences): {needle!r}")
    for i in range(len(sents) - 1):
        pair = sents[i] + " " + sents[i + 1]
        if n in norm(pair):
            return pair
    raise ValueError(f"needle NOT FOUND in {ref}: {needle!r}")


# ------------------------------------------------------------------ ClinicalTrials.gov
CT_DIR = RAW / "ctgov"


def fetch_trial(nct: str, refresh: bool = False) -> dict | None:
    try:
        return cached_json(CT_DIR / "studies" / f"{nct}.json", f"https://clinicaltrials.gov/api/v2/studies/{nct}",
                           refresh=refresh)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! trial {nct}: {ex}")
        return None


def trial_text(nct: str) -> str | None:
    p = CT_DIR / "studies" / f"{nct}.json"
    if not p.exists():
        return None
    ps = read_json(p)["protocolSection"]
    d = ps.get("descriptionModule", {})
    parts = [ps["identificationModule"].get("briefTitle", ""), ps["identificationModule"].get("officialTitle", ""),
             d.get("briefSummary", ""), d.get("detailedDescription", ""),
             ps.get("statusModule", {}).get("whyStopped", ""),
             ps.get("eligibilityModule", {}).get("eligibilityCriteria", "")]
    parts += ps.get("conditionsModule", {}).get("conditions", []) or []
    parts += [i.get("name", "") for i in ps.get("armsInterventionsModule", {}).get("interventions", []) or []]
    parts += [i.get("description", "") or "" for i in ps.get("armsInterventionsModule", {}).get("interventions", []) or []]
    return " \n ".join(p for p in parts if p)


# ------------------------------------------------------------------ FDA labels (openFDA)
FDA_DIR = RAW / "fda"
LABEL_FIELDS = ["indications_and_usage", "description", "clinical_pharmacology", "mechanism_of_action",
                "dosage_and_administration", "warnings_and_cautions", "limitations_of_use",
                "use_in_specific_populations", "pediatric_use", "clinical_studies", "spl_unclassified_section"]


def label_text(slug: str) -> str | None:
    p = FDA_DIR / f"{slug}.json"
    if not p.exists():
        return None
    res = (read_json(p).get("results") or [{}])[0]
    out = []
    for k in LABEL_FIELDS:
        for v in res.get(k, []) or []:
            out.append(v)
    return " \n ".join(out)


# ------------------------------------------------------------------ web pages
WEB_DIR = RAW / "web"
_BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
          "header", "footer", "ul", "ol", "table", "blockquote", "figcaption"}
_SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.meta = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        if tag == "meta":
            a = dict(attrs)
            if (a.get("name") or a.get("property") or "").lower() in ("description", "og:description", "og:title") \
                    and a.get("content"):
                self.meta.append(a["content"])
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    try:
        p.feed(raw)
    except Exception:  # noqa: BLE001
        pass
    body = "".join(p.parts)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body)
    meta = "\n".join(_html.unescape(m) for m in p.meta)
    return (("[meta] " + meta + "\n") if meta else "") + body.strip()


def web_text(sid: str) -> str | None:
    p = WEB_DIR / f"{sid}.txt"
    return p.read_text() if p.exists() else None


# ------------------------------------------------------------------ Bright Data (budgeted)
BRIGHTDATA_BUDGET = 150
_LEDGER = RAW / "brightdata" / "_ledger.json"


def _bd_module():
    spec = importlib.util.spec_from_file_location("brightdata_lyso", ROOT / "pipeline" / "brightdata.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod.CACHE_DIR = RAW / "brightdata"   # keep every cached Bright Data payload inside this family's raw dir
    return mod


def _bd_charge(kind: str, what: str) -> None:
    """Count one live Bright Data request (file-locked, shared by every process of this family)."""
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    _LEDGER.touch(exist_ok=True)
    with open(_LEDGER, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            raw = fh.read().strip()
            led = json.loads(raw) if raw else {"count": 0, "requests": []}
            if led["count"] >= BRIGHTDATA_BUDGET:
                raise RuntimeError(f"Bright Data budget of {BRIGHTDATA_BUDGET} requests exhausted")
            led["count"] += 1
            led["requests"].append({"kind": kind, "what": what, "date": TODAY})
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(led, indent=1))
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _bd_cached(mod, zone_key: str, url: str, kind: str) -> bool:
    import hashlib
    cfg = mod._config()
    zone = cfg[zone_key]
    f = mod.CACHE_DIR / kind / (hashlib.sha256(f"{zone}|{url}".encode()).hexdigest()[:24] + ".json")
    return f.exists()


def bd_search(query: str, num: int = 10) -> list[dict]:
    """Google results via Bright Data SERP (cached; live calls are budget-counted)."""
    import urllib.parse
    mod = _bd_module()
    params = urllib.parse.urlencode({"q": query, "num": num, "hl": "en", "gl": "us", "brd_json": 1})
    if not _bd_cached(mod, "serp_zone", f"https://www.google.com/search?{params}", "serp"):
        _bd_charge("serp", query)
    return mod.search(query, num=num)


def bd_fetch(url: str) -> dict:
    """Page via Bright Data Web Unlocker (cached; live calls are budget-counted)."""
    mod = _bd_module()
    if not _bd_cached(mod, "unlocker_zone", url, "unlocker"):
        _bd_charge("unlocker", url)
    return mod.fetch(url)


def bd_used() -> int:
    if not _LEDGER.exists() or not _LEDGER.read_text().strip():
        return 0
    return json.loads(_LEDGER.read_text())["count"]


# ------------------------------------------------------------------ NIH RePORTER
REPORTER_DIR = RAW / "reporter"


def reporter_text(core: str) -> str | None:
    """All stored RePORTER text for a core project number (titles + abstracts)."""
    out = []
    for f in sorted(REPORTER_DIR.glob("*.json")):
        try:
            d = read_json(f)
        except Exception:  # noqa: BLE001
            continue
        for r in (d.get("response") or {}).get("results", []) or []:
            if (r.get("core_project_num") or r.get("project_num")) == core:
                out.append((r.get("project_title") or "") + " \n " + (r.get("abstract_text") or ""))
    return " \n ".join(out) if out else None


# ------------------------------------------------------------------ resolve any ref to stored text
def source_text_for_ref(ref: str) -> str | None:
    ref = ref.strip()
    if ref.startswith("PMID:") or ref.isdigit():
        return pubmed_text(ref.replace("PMID:", ""))
    if ref.startswith("NCT"):
        return trial_text(ref)
    if ref.startswith("FDA:"):
        return label_text(ref.split(":", 1)[1])
    if ref.startswith("WEB:"):
        return web_text(ref.split(":", 1)[1])
    return None


if __name__ == "__main__":
    print("RAW", RAW)
    print("Bright Data used:", bd_used(), "of", BRIGHTDATA_BUDGET)
    sys.exit(0)
