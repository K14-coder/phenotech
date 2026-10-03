"""Fetch and store every source the derived products quote (run before modality.py).

Run:  python3 pipeline/derive/fetch_literature.py [--refresh]
Out:  data/raw/derive/pubmed/<PMID>.json   (efetch XML parsed: title, abstract, year, url)
      data/raw/derive/ctgov/<NCT>.json     (ClinicalTrials.gov API v2 record)
NCBI etiquette: the biology layer's shared <=2 req/s throttle, tool=rare-disease-atlas, no email,
exponential backoff on 429/5xx. Quotes are then cut from these files by needle (dcommon.quote_for).
"""
from __future__ import annotations

import json
import sys
import urllib.request

from dcommon import RAW_DERIVE, fetch_pmids

PMIDS = """
34904932 38581234 34378168 34850743 38617974 32848094 30545847 40963013 27398791 39759875
31940970 36205620 22911480 19019305 41515912 42041587 22703551 42462387 40349107 41883162
23340504 20002519 11742587 15106822 30266908 33332765 42157447 38781976 35911425 26519543
32250532 40181518 32362337 32906212 41166419 29949059 27648472 41125872 28192369 38979232
32572454 42673765 29538625 27597756 31675180 38242640 30929742 32776697 34037996 41579375
33147442 28422131 36564538 38321119 25705886 18469812 26280581 34028503 31176687 36741049
""".split()
NCTS = ["NCT02562066", "NCT06983158", "NCT04937062", "NCT07173153", "NCT07847918"]


def main():
    refresh = "--refresh" in sys.argv
    got = fetch_pmids(PMIDS, refresh=refresh)
    missing = [p for p in PMIDS if p not in got]
    print(f"[literature] {len(got)}/{len(PMIDS)} PubMed records stored" + (f"; missing {missing}" if missing else ""))
    ct = RAW_DERIVE / "ctgov"
    ct.mkdir(parents=True, exist_ok=True)
    for nct in NCTS:
        path = ct / f"{nct}.json"
        if path.exists() and not refresh:
            continue
        req = urllib.request.Request(f"https://clinicaltrials.gov/api/v2/studies/{nct}",
                                     headers={"User-Agent": "rare-disease-atlas/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_text(json.dumps(json.loads(r.read()), indent=1))
    print(f"[literature] {len(NCTS)} ClinicalTrials.gov records stored")


if __name__ == "__main__":
    main()
