"""ClinicalTrials.gov API v2 searches for the RASopathy family (adapted from
pipeline/community/fetch_ctgov.py). Every query and its hit count is stored, so gaps can list
exactly what was searched.

Run:  python3 pipeline/families/rasopathy/fetch_ctgov.py [--refresh]
Out:  data/raw/families/rasopathy/ctgov/<slug>.json  {query, url, retrieved, n, studies}
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse

from ras_common import RAW, TODAY, http_get, slugify, write_json

BASE = "https://clinicaltrials.gov/api/v2/studies"
REFRESH = "--refresh" in sys.argv
OUT = RAW / "ctgov"

MEK = ["selumetinib", "trametinib", "mirdametinib", "binimetinib", "cobimetinib", "tunlametinib", "MEK inhibitor"]
QUERIES = (
    [{"query.cond": c} for c in ["Noonan syndrome", "Costello syndrome", "cardiofaciocutaneous syndrome",
                                 "cardio-facio-cutaneous syndrome", "RASopathy", "RASopathies",
                                 "LEOPARD syndrome", "Noonan syndrome with multiple lentigines",
                                 "neurofibromatosis-Noonan syndrome", "metachondromatosis",
                                 "Noonan syndrome-like disorder with loose anagen hair"]]
    + [{"query.term": g} for g in ["PTPN11", "SOS1", "RAF1", "SHOC2", "RIT1", "LZTR1", "MAP2K1"]]
    + [{"query.cond": "neurofibromatosis 1", "query.intr": m} for m in MEK]
    + [{"query.cond": "plexiform neurofibroma", "query.intr": m} for m in MEK]
    + [{"query.cond": "neurofibromatosis 1", "query.term": t} for t in ["natural history", "registry"]]
    + [{"query.cond": c, "query.intr": "trametinib"} for c in ["cardiomyopathy", "lymphatic malformation",
                                                               "chylothorax"]]
    + [{"query.cond": "neurofibromatosis 1", "query.intr": i} for i in ["simvastatin", "lovastatin", "tipifarnib"]]
)


def fetch(q):
    studies, token, pages = [], None, 0
    while True:
        params = dict(q, pageSize=100, format="json")
        if token:
            params["pageToken"] = token
        data = json.loads(http_get(BASE, params=params, headers={"Accept": "application/json"}))
        studies += data.get("studies", [])
        token = data.get("nextPageToken")
        pages += 1
        time.sleep(0.35)
        if not token or pages >= 5:
            break
    return {"query": q, "url": f"{BASE}?{urllib.parse.urlencode(q)}", "retrieved": TODAY, "n": len(studies),
            "studies": studies}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for q in QUERIES:
        name = "__".join(f"{k.split('.')[-1]}-{slugify(v)}" for k, v in q.items()) + ".json"
        if (OUT / name).exists() and not REFRESH:
            continue
        res = fetch(q)
        write_json(OUT / name, res)
        print(f"{q}: {res['n']} studies -> {name}")


if __name__ == "__main__":
    main()
