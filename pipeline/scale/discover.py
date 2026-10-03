"""Find the real URLs of the org directories and registry lists with Bright Data Google SERP.
Results (title/link/description only; never used as evidence) -> data/raw/scale/discovery/<slug>.json

Usage: python3 discover.py ["extra query" ...]
"""
from __future__ import annotations

import sys

from common import RAW, bd_search, slugify, today, write_json

QUERIES = [
    "Global Genes RARE Foundation Alliance member directory",
    "globalgenes.org foundation alliance directory organizations",
    "NORD member organizations directory rarediseases.org",
    "rarediseases.org patient organizations directory",
    "EURORDIS members list directory",
    "eurordis.org our members map",
    "Genetic Alliance UK member directory",
    "geneticalliance.org.uk our members list charities",
    "Simons Searchlight genes we study list",
    "NORD IAMRARE registry program participating organizations list",
    "CoRDS registry Sanford Research list of diseases",
]


def main():
    qs = sys.argv[1:] or QUERIES
    for q in qs:
        try:
            res = bd_search(q, num=10)
        except Exception as e:
            print(f"{q!r}: ERROR {str(e)[:100]}")
            continue
        write_json(RAW / "discovery" / f"{slugify(q)}.json", {"query": q, "retrieved": today(), "results": res}, indent=1)
        print(f"== {q}")
        for r in res[:8]:
            print(f"   {r['rank']}. {(r['title'] or '')[:70]} | {r['link']}")


if __name__ == "__main__":
    main()
