"""Fetch ClinicalTrials.gov API v2 records for every slice gene / disease term.

Re-runnable: overwrites data/raw/community/ctgov/<query-slug>.json.
Usage:  python3 pipeline/community/fetch_ctgov.py
"""
from __future__ import annotations

import json
import time
import urllib.parse

from common import RAW, http, slugify, today, write_json

BASE = "https://clinicaltrials.gov/api/v2/studies"

# (parameter, value). query.term searches every field (incl. eligibility text);
# query.cond searches the conditions/keywords fields.
QUERIES = [
    # gene symbols in any field
    *[("query.term", g) for g in ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B", "SYT2",
                                   "CPLX1", "UNC13A", "STX1A", "SLC6A1"]],
    ("query.term", "\"NSF gene\""),
    ("query.term", "Munc18-1"),
    ("query.term", "SNAP-25"),
    # disease names
    ("query.cond", "STXBP1 encephalopathy"),
    ("query.cond", "STXBP1-related disorders"),
    ("query.cond", "Baker-Gordon syndrome"),
    ("query.cond", "SNAP25-related disorder"),
    ("query.cond", "VAMP2-related neurodevelopmental disorder"),
    ("query.cond", "generalized epilepsy with febrile seizures plus"),
    ("query.cond", "congenital myasthenic syndrome"),
    ("query.cond", "myoclonic-atonic epilepsy"),
    ("query.cond", "SLC6A1"),
    ("query.cond", "developmental and epileptic encephalopathy"),
]


def fetch(param: str, value: str) -> dict:
    studies, token, pages = [], None, 0
    while True:
        q = {param: value, "pageSize": 100, "format": "json"}
        if token:
            q["pageToken"] = token
        url = f"{BASE}?{urllib.parse.urlencode(q)}"
        status, body, _ = http(url, headers={"Accept": "application/json"})
        if status != 200:
            raise RuntimeError(f"{status} for {url}: {body[:200]!r}")
        data = json.loads(body)
        studies.extend(data.get("studies", []))
        token = data.get("nextPageToken")
        pages += 1
        time.sleep(0.4)
        if not token or pages >= 10:
            break
    return {"query": {param: value}, "url": f"{BASE}?{urllib.parse.urlencode({param: value, 'pageSize': 100})}",
            "retrieved": today(), "n": len(studies), "studies": studies}


def main():
    out = RAW / "ctgov"
    for param, value in QUERIES:
        res = fetch(param, value)
        name = f"{param.split('.')[-1]}__{slugify(value)}.json"
        write_json(out / name, res)
        print(f"{param}={value!r}: {res['n']} studies -> {name}")


if __name__ == "__main__":
    main()
