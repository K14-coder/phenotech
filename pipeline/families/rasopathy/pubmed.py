"""PubMed abstracts (E-utilities efetch XML) and ClinicalTrials.gov v2 records that the RASopathy
claims rely on, plus an esearch helper whose every query is logged (for gaps[].searched).

Run:  python3 pipeline/families/rasopathy/pubmed.py                 # fetch everything curation.py cites
      python3 pipeline/families/rasopathy/pubmed.py 123 456         # fetch specific PMIDs
      python3 pipeline/families/rasopathy/pubmed.py --search "PTPN11[tiab] AND LEOPARD[tiab]"
      python3 pipeline/families/rasopathy/pubmed.py --nct NCT01362803
Out:  data/raw/families/rasopathy/pubmed/<PMID>.json   {pmid,title,abstract,authors,journal,year,...}
      data/raw/families/rasopathy/clinicaltrials/<NCT>.json (raw CT.gov API v2 record)
      data/raw/families/rasopathy/pubmed_searches.json  (every esearch term, count, ids, date)
NCBI etiquette: shared cross-process throttle (pipeline/biology/common.py), tool=rare-disease-atlas,
no email param, backoff on 429.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET

from ras_common import RAW, TODAY, cached_json, eutils, load_bio, read_json, redact_emails, write_json

PM_DIR = RAW / "pubmed"
CT_DIR = RAW / "clinicaltrials"
SEARCH_LOG = RAW / "pubmed_searches.json"
PM_DIR.mkdir(parents=True, exist_ok=True)
CT_DIR.mkdir(parents=True, exist_ok=True)
bio_pubmed = load_bio("pubmed")   # reuse parse_article()


def parse_article(art) -> dict:
    rec = bio_pubmed.parse_article(art)
    # keep last-author affiliation (professional info only; e-mails redacted) for research-group curation
    a = art.find("MedlineCitation/Article")
    auths = a.findall("AuthorList/Author") if a is not None else []
    if auths:
        last = auths[-1]
        rec["last_author"] = {"last": last.findtext("LastName"), "fore": last.findtext("ForeName"),
                              "affiliation": redact_emails(last.findtext("AffiliationInfo/Affiliation") or ""),
                              "orcid": next((i.text for i in last.findall("Identifier")
                                             if i.get("Source") == "ORCID"), None)}
    return rec


def fetch_pmids(pmids, refresh=False) -> dict:
    pmids = [str(p).replace("PMID:", "").strip() for p in pmids]
    todo = [p for p in dict.fromkeys(pmids) if refresh or not (PM_DIR / f"{p}.json").exists()]
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        root = ET.fromstring(eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}))
        got = set()
        for art in root.findall("PubmedArticle"):
            rec = parse_article(art)
            write_json(PM_DIR / f"{rec['pmid']}.json", rec)
            got.add(rec["pmid"])
        for p in batch:
            if p not in got:
                print(f"  ! PMID {p} not returned by efetch")
        print(f"[pubmed] fetched {len(got)}/{len(batch)}")
    return {p: read_json(PM_DIR / f"{p}.json") for p in pmids if (PM_DIR / f"{p}.json").exists()}


def fetch_trial(nct, refresh=False):
    try:
        return cached_json(CT_DIR / f"{nct}.json", f"https://clinicaltrials.gov/api/v2/studies/{nct}",
                           refresh=refresh)
    except Exception as ex:  # noqa: BLE001
        print(f"  ! trial {nct}: {ex}")
        return None


def esearch(term, retmax=20, sort="relevance"):
    body = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json", "sort": sort})
    res = json.loads(body)["esearchresult"]
    log = read_json(SEARCH_LOG) if SEARCH_LOG.exists() else []
    log.append({"term": term, "count": res.get("count"), "ids": res.get("idlist", []), "date": TODAY,
                "sort": sort})
    write_json(SEARCH_LOG, log)
    return res.get("idlist", [])


def main():
    args = sys.argv[1:]
    if args and args[0] == "--search":
        ids = esearch(" ".join(args[1:]))
        recs = fetch_pmids(ids)
        for p in ids:
            r = recs.get(p)
            if r:
                print(f"{p} {r['year']} | {r['title'][:150]}")
        return
    if args and args[0] == "--nct":
        for n in args[1:]:
            fetch_trial(n)
        return
    if args:
        fetch_pmids(args)
        return
    import curation  # noqa: E402  (this family's claims)
    pmids, ncts = curation.referenced_ids()
    fetch_pmids(sorted(pmids))
    for n in sorted(ncts):
        fetch_trial(n)
    print(f"[pubmed] {len(pmids)} PMIDs, {len(ncts)} trials available locally")


if __name__ == "__main__":
    main()
