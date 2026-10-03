"""Patient-organisation discovery via Bright Data Google SERP (pipeline/brightdata.py; responses cached
under data/raw/brightdata/). A search snippet is NOT evidence: candidates found here are fetched with
fetch_web.py (via=brightdata for blocked sites) and quoted verbatim from the stored page.

Usage: python3 pipeline/community/bd_discover.py            # run all queries, save + print results
Results: data/raw/community/brightdata_search/<query-slug>.json
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/khezanirani/Desktop/hacknation/pipeline")
import brightdata  # noqa: E402

from common import RAW, slugify, today, write_json  # noqa: E402

QUERIES = {
    "VAMP2": ["VAMP2 foundation", "VAMP2 patient advocacy", "VAMP2 syndrome family support group", "VAMP2 registry natural history study"],
    "STX1B": ["STX1B foundation", "STX1B patient advocacy", "STX1B epilepsy family support group", "STX1B registry natural history study"],
    "SNAP25": ["SNAP25 foundation", "SNAP25 patient advocacy", "SNAP25 registry natural history study"],
    "SYT2": ["SYT2 foundation", "SYT2 congenital myasthenic syndrome family support group", "congenital myasthenic syndrome patient advocacy organization", "SYT2 registry natural history study"],
    "CPLX1": ["CPLX1 foundation", "CPLX1 patient advocacy", "CPLX1 family support group"],
    "UNC13A": ["UNC13A foundation", "UNC13A neurodevelopmental disorder family support group", "UNC13A patient advocacy"],
    "STX1A": ["STX1A foundation", "STX1A family support group"],
    "NSF": ["NSF gene developmental epileptic encephalopathy 96 family support group", "NSF-related disorder foundation"],
    "SLC6A1": ["SLC6A1 foundation", "SLC6A1 patient advocacy Europe", "SLC6A1 registry natural history study", "SLC6A1 family support group"],
    "SYT1": ["SYT1 foundation", "Baker-Gordon syndrome family support group"],
    "DIRECTORY": ["orpha.net patient organisations STXBP1", "orpha.net patient organisations SLC6A1", "orpha.net congenital myasthenic syndrome patient organisation"],
}


def main():
    out = RAW / "brightdata_search"
    only = sys.argv[1:] or None
    for gene, qs in QUERIES.items():
        if only and gene not in only:
            continue
        for q in qs:
            try:
                res = brightdata.search(q, num=10)
            except Exception as e:  # keep going; record the failure
                print(f"[{gene}] {q!r}: ERROR {str(e)[:120]}")
                continue
            write_json(out / f"{slugify(q)}.json", {"gene": gene, "query": q, "retrieved": today(), "results": res})
            print(f"[{gene}] {q!r}")
            for r in res[:8]:
                print(f"    {r['rank']}. {(r['title'] or '')[:70]} | {r['link']}")


if __name__ == "__main__":
    main()
