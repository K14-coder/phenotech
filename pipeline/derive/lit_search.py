"""Helper used while curating the modality rules: run PubMed searches and print titles.

Run:  python3 pipeline/derive/lit_search.py "query one" "query two" ...
Every search (term, date, PMIDs returned) is appended to data/raw/derive/search_log.json so the
literature behind data/curated/modality.json can be re-traced. Abstracts are fetched only for the
PMIDs that are actually cited (fetch_literature.py).
"""
from __future__ import annotations

import json
import sys

from dcommon import RAW_DERIVE, TODAY, eutils, esearch, read_json, write_json

LOG = RAW_DERIVE / "search_log.json"


def titles(pmids):
    if not pmids:
        return {}
    body = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    res = json.loads(body)["result"]
    return {p: (res[p].get("pubdate", "")[:4], res[p].get("title", ""), res[p].get("source", ""),
                ",".join(res[p].get("pubtype", []))) for p in res.get("uids", [])}


def main():
    log = read_json(LOG) if LOG.exists() else []
    for term in sys.argv[1:]:
        ids = esearch(term, retmax=12)
        t = titles(ids)
        print(f"\n### {term}  ({len(ids)})")
        for p in ids:
            y, ti, src, pt = t.get(p, ("", "", "", ""))
            print(f"  {p} {y} [{src}] {ti[:150]}  <{pt}>")
        log.append({"term": term, "date": TODAY, "pmids": ids})
    write_json(LOG, log)


if __name__ == "__main__":
    main()
