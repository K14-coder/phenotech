"""Fetch NIH RePORTER v2 projects (FY2020-2026) per DEE gene / syndrome term.

Stores raw responses in data/raw/families/dee/community/reporter/<slug>.json. >= 1.2 s between calls.
Single-token gene symbols use operator "or"; multi-word phrases use "advanced" with a quoted phrase.
Usage:  python3 fetch_reporter.py [--refresh]
"""
from __future__ import annotations

import json
import sys
import time

from dee_common import REPORTER, http, slugify, today, write_json

URL = "https://api.reporter.nih.gov/v2/projects/search"
FIELDS = ["ProjectNum", "CoreProjectNum", "ApplId", "FiscalYear", "ProjectTitle", "AbstractText",
          "PrincipalInvestigators", "ContactPiName", "Organization", "AwardAmount", "ProjectStartDate",
          "ProjectEndDate", "AgencyIcAdmin", "ProjectDetailUrl", "ActivityCode", "IsActive"]
TERMS = ["SCN1A", "SCN2A", "SCN8A", "KCNQ2", "KCNT1", "CACNA1A", "GRIN2B", "CDKL5", "SYNGAP1", "SLC2A1",
         "Dravet syndrome", "CDKL5 deficiency disorder", "GLUT1 deficiency"]


def search(term: str, offset: int = 0) -> dict:
    phrase = (" " in term) or ("-" in term)
    ats = {"operator": "advanced" if phrase else "or", "search_field": "projecttitle,abstracttext",
           "search_text": f'"{term}"' if phrase else term}
    body = {"criteria": {"advanced_text_search": ats, "fiscal_years": list(range(2020, 2027))},
            "include_fields": FIELDS, "offset": offset, "limit": 50,
            "sort_field": "fiscal_year", "sort_order": "desc"}
    status, raw, _ = http(URL, data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
    if status != 200:
        raise RuntimeError(f"{status}: {raw[:300]!r}")
    return {"request": body, "response": json.loads(raw)}


def main():
    refresh = "--refresh" in sys.argv
    for term in TERMS:
        out = REPORTER / f"{slugify(term)}.json"
        if out.exists() and not refresh:
            continue
        res = search(term)
        time.sleep(1.2)
        total = res["response"].get("meta", {}).get("total", 0) or 0
        results = list(res["response"].get("results", []))
        offset = 50
        while offset < min(total, 150):
            more = search(term, offset)
            time.sleep(1.2)
            results.extend(more["response"].get("results", []))
            offset += 50
        res["response"]["results"] = results
        write_json(out, {"term": term, "retrieved": today(), "url": URL, **res})
        print(f"{term!r}: total={total} got={len(results)}", file=sys.stderr)


if __name__ == "__main__":
    main()
