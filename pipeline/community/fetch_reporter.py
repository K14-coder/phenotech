"""Fetch NIH RePORTER v2 projects (FY2020-2026) for every slice gene / disease term.

Re-runnable: overwrites data/raw/community/reporter/<slug>.json. Sleeps >=1.1 s between calls.
Single-token gene symbols use operator "or" (as specified); multi-word disease
phrases use operator "advanced" with a quoted phrase so that e.g. "syndrome" alone
does not match.
Usage:  python3 pipeline/community/fetch_reporter.py
"""
from __future__ import annotations

import json
import time

from common import RAW, http, slugify, today, write_json

URL = "https://api.reporter.nih.gov/v2/projects/search"
FIELDS = ["ProjectNum", "CoreProjectNum", "ApplId", "FiscalYear", "ProjectTitle", "AbstractText",
          "Terms", "PrefTerms", "PrincipalInvestigators", "ContactPiName", "Organization",
          "AwardAmount", "ProjectStartDate", "ProjectEndDate", "AgencyIcAdmin", "ProjectDetailUrl",
          "ActivityCode", "IsActive", "SpendingCategoriesDesc"]

TERMS = ["STXBP1", "Munc18-1", "SYT1", "Baker-Gordon syndrome", "SNAP25", "VAMP2", "STX1B",
         "SYT2", "CPLX1", "UNC13A", "STX1A", "SLC6A1",
         "STXBP1 encephalopathy", "congenital myasthenic syndrome", "myoclonic-atonic epilepsy",
         "SNAREopathy", "SNAREopathies"]
# NSF is not searched as a bare token: "NSF" overwhelmingly matches the National Science Foundation.


def search(term: str, offset: int = 0) -> dict:
    phrase = (" " in term) or ("-" in term)  # hyphens are tokenised by RePORTER -> quote as phrase
    ats = {"operator": "advanced" if phrase else "or",
           "search_field": "projecttitle,terms,abstracttext",
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
    out = RAW / "reporter"
    for term in TERMS:
        res = search(term)
        time.sleep(1.2)
        total = res["response"].get("meta", {}).get("total", 0) or 0
        results = list(res["response"].get("results", []))
        offset = 50
        while offset < min(total, 200):  # page (limit 50 per call) up to 200 records
            more = search(term, offset)
            time.sleep(1.2)
            results.extend(more["response"].get("results", []))
            offset += 50
        res["response"]["results"] = results
        write_json(out / f"{slugify(term)}.json", {"term": term, "retrieved": today(), **res})
        print(f"{term!r}: total={total} got={len(results)}")


if __name__ == "__main__":
    main()
