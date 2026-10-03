"""FDA drug labels (openFDA drug/label API) used as the regulatory source for approved MEK inhibitors
and for the approved indications of trametinib (oncology only, so RASopathy use is off-label).

Run:  python3 pipeline/families/rasopathy/fetch_labels.py [--refresh]
Out:  data/raw/families/rasopathy/fda/<drug>.label.json  (raw openFDA response)
"""
from __future__ import annotations

import sys

from ras_common import RAW, cached_json

REFRESH = "--refresh" in sys.argv
LABELS = {
    "selumetinib": 'openfda.generic_name:"selumetinib"',
    "mirdametinib": "mirdametinib",   # not yet indexed under openfda.generic_name; full-text search
    "trametinib": 'openfda.generic_name:"trametinib"',
}


def label(drug: str) -> dict:
    obj = cached_json(RAW / "fda" / f"{drug}.label.json", "https://api.fda.gov/drug/label.json",
                      params={"search": LABELS[drug], "limit": 3}, refresh=REFRESH)
    res = obj.get("results") or []
    assert len(res) == 1, f"expected exactly one label for {drug}, got {len(res)}"
    return res[0]


def label_text(drug: str) -> str:
    r = label(drug)
    return " ".join(r.get("indications_and_usage", []))


def label_meta(drug: str) -> dict:
    r = label(drug)
    return {"set_id": r["set_id"], "effective_time": r.get("effective_time"),
            "brand": (r.get("openfda", {}).get("brand_name") or [None])[0],
            "application_number": r.get("openfda", {}).get("application_number"),
            "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={r['set_id']}"}


if __name__ == "__main__":
    for d in LABELS:
        m = label_meta(d)
        print(d, m, label_text(d)[:200])
