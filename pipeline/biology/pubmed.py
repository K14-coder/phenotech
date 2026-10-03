"""Task 5/6: fetch and store PubMed abstracts (NCBI E-utilities efetch, XML) and
ClinicalTrials.gov v2 records that curated claims rely on.

Run:  python3 pipeline/biology/pubmed.py            # fetch everything referenced in curation.py
      python3 pipeline/biology/pubmed.py 12345 678  # fetch specific PMIDs
      python3 pipeline/biology/pubmed.py --search "STXBP1[tiab] AND chaperone"  # esearch helper
Out:  data/raw/biology/pubmed/<PMID>.json  {pmid,title,abstract,authors,journal,year,pub_types,doi}
      data/raw/biology/clinicaltrials/<NCT>.json (raw API v2 record)
NCBI etiquette: shared <=2 req/s throttle (common.py), tool=rare-disease-atlas, no email param.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET

from common import RAW, cached_json, eutils, write_json

PM_DIR = RAW / "pubmed"
CT_DIR = RAW / "clinicaltrials"
PM_DIR.mkdir(parents=True, exist_ok=True)
CT_DIR.mkdir(parents=True, exist_ok=True)


def _text(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def parse_article(art) -> dict:
    mc = art.find("MedlineCitation")
    pmid = mc.findtext("PMID")
    a = mc.find("Article")
    title = _text(a.find("ArticleTitle"))
    sections = []
    for at in a.findall("Abstract/AbstractText"):
        sections.append({"label": at.get("Label"), "text": _text(at)})
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
    doi = None
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = aid.text
    pub_types = [_text(p) for p in a.findall("PublicationTypeList/PublicationType")]
    return {"pmid": pmid, "title": title, "abstract": abstract, "abstract_sections": sections,
            "authors": authors, "journal": journal, "year": int(year) if year else None,
            "pub_types": pub_types, "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "source": "NCBI E-utilities efetch (XML)"}


def fetch_pmids(pmids: list[str], refresh: bool = False) -> dict:
    pmids = [str(p).replace("PMID:", "").strip() for p in pmids]
    todo = [p for p in dict.fromkeys(pmids) if refresh or not (PM_DIR / f"{p}.json").exists()]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        xml = eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
        root = ET.fromstring(xml)
        got = set()
        for art in root.findall("PubmedArticle"):
            rec = parse_article(art)
            write_json(PM_DIR / f"{rec['pmid']}.json", rec)
            got.add(rec["pmid"])
        for p in batch:
            if p not in got:
                print(f"  ! PMID {p} not returned by efetch")
        print(f"[pubmed] fetched {len(got)}/{len(batch)}")
    return {p: json.loads((PM_DIR / f"{p}.json").read_text()) for p in pmids if (PM_DIR / f"{p}.json").exists()}


def fetch_trial(nct: str, refresh: bool = False) -> dict | None:
    try:
        return cached_json(CT_DIR / f"{nct}.json", f"https://clinicaltrials.gov/api/v2/studies/{nct}",
                           refresh=refresh)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! trial {nct}: {ex}")
        return None


def esearch(term: str, retmax: int = 30) -> list[str]:
    body = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json",
                                   "sort": "relevance"})
    return json.loads(body)["esearchresult"]["idlist"]


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--search":
        ids = esearch(" ".join(args[1:]))
        recs = fetch_pmids(ids)
        for p in ids:
            r = recs.get(p)
            if r:
                print(f"{p} {r['year']} | {r['title'][:110]}")
        return
    if args:
        fetch_pmids(args)
        return
    from curation import referenced_ids  # noqa: E402  (curation.py lists every claim's source)
    pmids, ncts = referenced_ids()
    fetch_pmids(sorted(pmids))
    for n in sorted(ncts):
        fetch_trial(n)
    print(f"[pubmed] {len(pmids)} PMIDs, {len(ncts)} trials available locally")


if __name__ == "__main__":
    main()
