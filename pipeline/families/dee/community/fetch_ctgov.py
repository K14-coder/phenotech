"""Fetch ClinicalTrials.gov API v2 records for the DEE genes, their gene-defined syndromes and
gene-targeted drugs. Every raw response is stored under data/raw/families/dee/community/ctgov/.

Usage:  python3 fetch_ctgov.py [--refresh]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse

from dee_common import CTGOV, http, slugify, today, write_json

BASE = "https://clinicaltrials.gov/api/v2/studies"

QUERIES = [
    # gene symbols in any field (title, conditions, keywords, eligibility, ...)
    *[("query.term", g) for g in ["SCN1A", "SCN2A", "SCN8A", "KCNQ2", "KCNT1", "CACNA1A", "GRIN2B",
                                   "CDKL5", "SYNGAP1", "SLC2A1"]],
    # gene-defined syndromes
    ("query.cond", "Dravet syndrome"),
    ("query.cond", "CDKL5 deficiency disorder"),
    ("query.cond", "Glut1 deficiency syndrome"),
    ("query.term", "\"GLUT1 deficiency\""),
    ("query.cond", "episodic ataxia type 2"),
    ("query.cond", "familial hemiplegic migraine"),
    ("query.cond", "epilepsy of infancy with migrating focal seizures"),
    ("query.cond", "SYNGAP1-related intellectual disability"),
    # gene-targeted / named investigational drugs
    *[("query.intr", d) for d in ["zorevunersen", "STK-001", "ETX101", "elsunersen", "PRAX-222", "relutrigine",
                                   "PRAX-562", "NBI-921352", "XEN496", "ezogabine", "radiprodil", "ganaxolone",
                                   "triheptanoin", "soticlestat", "TAK-935", "quinidine"]],
]
# existing graph study nodes we may add edges from: store their records too
NCT_IDS = ["NCT01238250", "NCT06555965", "NCT05232630", "NCT06585605", "NCT06967727", "NCT02885389"]


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
        if not token or pages >= 6:
            break
    return {"query": {param: value}, "url": f"{BASE}?{urllib.parse.urlencode({param: value, 'pageSize': 100})}",
            "retrieved": today(), "n": len(studies), "truncated": bool(token), "studies": studies}


def main():
    refresh = "--refresh" in sys.argv
    log = []
    for param, value in QUERIES:
        name = f"{param.split('.')[-1]}__{slugify(value)}.json"
        out = CTGOV / name
        if out.exists() and not refresh:
            d = json.loads(out.read_text())
        else:
            d = fetch(param, value)
            write_json(out, d)
        log.append({"param": param, "value": value, "n": d["n"], "file": name, "url": d["url"]})
        print(f"{param}={value!r}: {d['n']} studies -> {name}", file=sys.stderr)
    for nct in NCT_IDS:
        out = CTGOV / f"nct__{nct}.json"
        if not out.exists() or refresh:
            status, body, _ = http(f"{BASE}/{nct}?format=json", headers={"Accept": "application/json"})
            if status != 200:
                print(f"{nct}: HTTP {status}", file=sys.stderr)
                continue
            write_json(out, {"query": {"nct": nct}, "url": f"{BASE}/{nct}", "retrieved": today(), "n": 1,
                             "studies": [json.loads(body)]})
            time.sleep(0.4)
        log.append({"param": "nct", "value": nct, "n": 1, "file": out.name, "url": f"{BASE}/{nct}"})
    write_json(CTGOV / "_queries.json", log)


if __name__ == "__main__":
    main()
