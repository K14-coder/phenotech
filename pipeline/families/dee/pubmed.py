"""DEE family: fetch and store the sources that curated claims rely on.

  * PubMed abstracts (E-utilities efetch XML; parser reused from pipeline/biology/pubmed.py)
    -> data/raw/families/dee/pubmed/<PMID>.json
  * ClinicalTrials.gov API v2 records -> data/raw/families/dee/clinicaltrials/<NCT>.json
  * FDA drug labels via the openFDA drug-label API -> data/raw/families/dee/labels/<BRAND>.json

Run:  python3 pipeline/families/dee/pubmed.py                 # everything referenced in curation.py
      python3 pipeline/families/dee/pubmed.py 12345 678       # specific PMIDs
      python3 pipeline/families/dee/pubmed.py --search "SCN2A[tiab] AND sodium channel blocker*"
NCBI etiquette: shared cross-process <= 2 req/s throttle (pipeline/biology/common.py),
tool=rare-disease-atlas, no email param, backoff on 429.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import xml.etree.ElementTree as ET

from dee_common import RAW, cached_json, eutils, write_json

sys.path_importer_cache.clear()
import pubmed as bio_pubmed  # noqa: E402  (pipeline/biology/pubmed.py, for parse_article)

PM_DIR = RAW / "pubmed"
CT_DIR = RAW / "clinicaltrials"
LABEL_DIR = RAW / "labels"
for d in (PM_DIR, CT_DIR, LABEL_DIR):
    d.mkdir(parents=True, exist_ok=True)


def fetch_pmids(pmids, refresh=False):
    pmids = [str(p).replace("PMID:", "").strip() for p in pmids]
    todo = [p for p in dict.fromkeys(pmids) if refresh or not (PM_DIR / f"{p}.json").exists()]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        root = ET.fromstring(eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}))
        got = set()
        for art in root.findall("PubmedArticle"):
            rec = bio_pubmed.parse_article(art)
            write_json(PM_DIR / f"{rec['pmid']}.json", rec)
            got.add(rec["pmid"])
        for p in batch:
            if p not in got:
                print(f"  ! PMID {p} not returned by efetch")
    return {p: json.loads((PM_DIR / f"{p}.json").read_text()) for p in pmids if (PM_DIR / f"{p}.json").exists()}


def fetch_trial(nct, refresh=False):
    try:
        return cached_json(CT_DIR / f"{nct}.json", f"https://clinicaltrials.gov/api/v2/studies/{nct}", refresh=refresh)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! trial {nct}: {ex}")
        return None


LABEL_QUERIES = {  # brand -> openFDA search (ZTALMY has no openfda.brand_name block, so free text)
    "FINTEPLA": 'openfda.brand_name:"FINTEPLA"', "DIACOMIT": 'openfda.brand_name:"DIACOMIT"',
    "EPIDIOLEX": 'openfda.brand_name:"EPIDIOLEX"', "ZTALMY": "ganaxolone",
}


def fetch_label(brand, refresh=False):
    """openFDA drug label (current SPL) for a brand name; stores the raw API response."""
    q = urllib.parse.quote(LABEL_QUERIES.get(brand, f'openfda.brand_name:"{brand}"'))
    try:
        return cached_json(LABEL_DIR / f"{brand.upper()}.json",
                           f"https://api.fda.gov/drug/label.json?search={q}&limit=1", refresh=refresh)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! label {brand}: {ex}")
        return None


def esearch(term, retmax=20):
    body = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json",
                                   "sort": "relevance"})
    return json.loads(body)["esearchresult"]["idlist"]


def main():
    args = sys.argv[1:]
    if args and args[0] == "--search":
        term = " ".join(args[1:])
        ids = esearch(term)
        log = RAW / "pubmed_searches.json"
        hist = json.loads(log.read_text()) if log.exists() else []
        hist.append({"term": term, "ids": ids})
        write_json(log, hist)
        recs = fetch_pmids(ids)
        for p in ids:
            r = recs.get(p)
            if r:
                print(f"{p} {r['year']} | {r['title'][:150]}")
        return
    if args:
        fetch_pmids(args)
        return
    from curation import referenced_ids  # noqa: E402
    pmids, ncts, labels = referenced_ids()
    fetch_pmids(sorted(pmids))
    for n in sorted(ncts):
        fetch_trial(n)
    for b in sorted(labels):
        fetch_label(b)
    print(f"[sources] {len(pmids)} PMIDs, {len(ncts)} trials, {len(labels)} labels available locally")


if __name__ == "__main__":
    main()
