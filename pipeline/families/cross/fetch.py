"""PubMed fetcher for the cross-family curation (stdlib only).

Run:  python3 pipeline/families/cross/fetch.py --search "LZTR1[tiab] AND ERK[tiab]" [--n 10]
      python3 pipeline/families/cross/fetch.py 30442762 30872527         # fetch + store abstracts
      python3 pipeline/families/cross/fetch.py --show 30442762            # print stored title+abstract
Out:  data/raw/families/cross/pubmed/<PMID>.json   {pmid,title,abstract,authors,journal,year,doi,url}
      data/raw/families/cross/pubmed_searches.json  (every esearch term, count, ids, date)
NCBI etiquette: <= 2 requests/s (0.6 s spacing), tool=tasukeru, no email param, backoff on 429.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "families" / "cross"
PM = RAW / "pubmed"
SEARCH_LOG = RAW / "pubmed_searches.json"
PM.mkdir(parents=True, exist_ok=True)
TODAY = datetime.date.today().isoformat()
_last = [0.0]


def eutils(path, params):
    params = dict(params, tool="tasukeru")
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        wait = 0.6 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"eutils failed: {url}")


def _text(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def parse(art):
    mc = art.find("MedlineCitation")
    a = mc.find("Article")
    secs = [((at.get("Label") + ": ") if at.get("Label") else "") + _text(at) for at in a.findall("Abstract/AbstractText")]
    j = a.find("Journal")
    year = j.findtext("JournalIssue/PubDate/Year") or (j.findtext("JournalIssue/PubDate/MedlineDate") or "")[:4]
    doi = next((x.text for x in art.findall("PubmedData/ArticleIdList/ArticleId") if x.get("IdType") == "doi"), None)
    pmid = mc.findtext("PMID")
    return {"pmid": pmid, "title": _text(a.find("ArticleTitle")), "abstract": " ".join(secs),
            "authors": [" ".join(x for x in [au.findtext("LastName"), au.findtext("Initials")] if x)
                        for au in a.findall("AuthorList/Author")],
            "journal": j.findtext("Title"), "year": int(year) if year and year.isdigit() else None,
            "pub_types": [_text(p) for p in a.findall("PublicationTypeList/PublicationType")], "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "source": "NCBI E-utilities efetch (XML)",
            "retrieved": TODAY}


def fetch(pmids):
    todo = [p for p in dict.fromkeys(pmids) if not (PM / f"{p}.json").exists()]
    for i in range(0, len(todo), 50):
        root = ET.fromstring(eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(todo[i:i + 50]), "retmode": "xml"}))
        for art in root.findall("PubmedArticle"):
            rec = parse(art)
            (PM / f"{rec['pmid']}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return [json.loads((PM / f"{p}.json").read_text()) for p in pmids if (PM / f"{p}.json").exists()]


def search(term, n=10):
    res = json.loads(eutils("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": n, "retmode": "json",
                                             "sort": "relevance"}))["esearchresult"]
    log = json.loads(SEARCH_LOG.read_text()) if SEARCH_LOG.exists() else []
    log.append({"term": term, "count": res.get("count"), "ids": res.get("idlist", []), "date": TODAY})
    SEARCH_LOG.write_text(json.dumps(log, indent=1))
    return res.get("count"), res.get("idlist", [])


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--search":
        n = int(args[args.index("--n") + 1]) if "--n" in args else 10
        cnt, ids = search(args[1], n)
        print(f"## {args[1]}  (count {cnt})")
        for r in fetch(ids):
            print(f"  {r['pmid']} {r['year']} {r['title'][:150]}")
    elif args and args[0] == "--show":
        for r in fetch(args[1:]):
            print(f"=== {r['pmid']} ({r['year']}) {r['title']}\n{r['abstract']}\n")
    else:
        for r in fetch(args):
            print(r["pmid"], r["title"][:120])
