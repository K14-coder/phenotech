"""Curated literature / trial / label claims for the DEE family (channels, receptors, signalling).

EVIDENCE INTEGRITY DESIGN (same as pipeline/biology/curation.py)
A claim never stores a hand-typed quote. It stores a `needle`: a short, distinctive substring.
`quote_for()` locates the needle inside the LOCALLY STORED source and returns the full sentence
(or eligibility line) verbatim. A needle that is missing or ambiguous raises.
  PMID:<n>          -> data/raw/families/dee/pubmed/<n>.json        (title + abstract)
  NCT<n>            -> data/raw/families/dee/clinicaltrials/<NCT>.json (titles, summaries,
                       whyStopped, conditions, eligibility criteria)
  FDA-label:<BRAND> -> data/raw/families/dee/labels/<BRAND>.json    (openFDA drug label)
verify.py re-checks every emitted quote independently.

Run:  python3 pipeline/families/dee/curation.py     # resolve and print every claim
"""
from __future__ import annotations

import json
import re

from dee_common import RAW, norm

PM_DIR, CT_DIR, LABEL_DIR = RAW / "pubmed", RAW / "clinicaltrials", RAW / "labels"


def trial_text(rec: dict) -> str:
    ps = rec["protocolSection"]
    idm, st, d = ps["identificationModule"], ps["statusModule"], ps.get("descriptionModule", {})
    conds = ps.get("conditionsModule", {}).get("conditions", [])
    elig = ps.get("eligibilityModule", {}).get("eligibilityCriteria", "")
    return "\n".join([idm.get("briefTitle", ""), idm.get("officialTitle", ""), d.get("briefSummary", ""),
                      d.get("detailedDescription", ""), st.get("whyStopped", "") or "", "; ".join(conds), elig])


def label_text(rec: dict) -> str:
    res = rec["results"][0]
    return "\n".join(" ".join(v) for k, v in res.items() if isinstance(v, list) and v and isinstance(v[0], str)
                     and k not in ("spl_product_data_elements", "package_label_principal_display_panel"))


def source_text(ref: str) -> tuple[str, dict]:
    if ref.startswith("NCT"):
        rec = json.loads((CT_DIR / f"{ref}.json").read_text())
        ps = rec["protocolSection"]
        st = ps["statusModule"]
        return trial_text(rec), {
            "title": ps["identificationModule"].get("briefTitle"), "status": st.get("overallStatus"),
            "why_stopped": st.get("whyStopped"),
            "year": int((st.get("startDateStruct", {}).get("date") or "0")[:4]) or None,
            "phases": ps.get("designModule", {}).get("phases"),
            "sponsor": ps["sponsorCollaboratorsModule"]["leadSponsor"]["name"],
            "url": f"https://clinicaltrials.gov/study/{ref}"}
    if ref.startswith("FDA-label:"):
        brand = ref.split(":", 1)[1]
        rec = json.loads((LABEL_DIR / f"{brand}.json").read_text())
        res = rec["results"][0]
        et = res.get("effective_time", "")
        return label_text(rec), {
            "title": f"FDA prescribing information: {brand} ({', '.join(res.get('openfda', {}).get('generic_name', []) or [])})"
                     f", label effective {et[:4]}-{et[4:6]}-{et[6:]}".replace("()", ""),
            "year": int(et[:4]) if et[:4].isdigit() else None,
            "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={res.get('set_id')}"}
    pmid = ref.replace("PMID:", "")
    rec = json.loads((PM_DIR / f"{pmid}.json").read_text())
    return rec["title"] + " " + rec["abstract"], {
        "title": rec["title"], "year": rec["year"], "journal": rec["journal"], "pub_types": rec["pub_types"],
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(“\"])")
_BULLET = re.compile(r"^\s*(?:[*\-•]|\d+\.)\s+")


def quote_for(ref: str, needle: str) -> str:
    """Verbatim sentence (or eligibility line) of `ref` containing `needle`."""
    txt, _ = source_text(ref)
    n = norm(needle)
    segs = []
    for line in txt.splitlines():
        line = _BULLET.sub("", line).strip()
        segs += [s.strip() for s in _SENT.split(line) if s.strip()]
    hits = list(dict.fromkeys(s for s in segs if n in norm(s)))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"needle ambiguous in {ref} ({len(hits)} segments): {needle!r}")
    for i in range(len(segs) - 1):
        pair = segs[i] + " " + segs[i + 1]
        if n in norm(pair):
            return pair
    raise ValueError(f"needle NOT FOUND in {ref}: {needle!r}")


def meta_for(ref: str) -> dict:
    return source_text(ref)[1]


# Claims live in small data modules: claims_mech.py, claims_therapy.py, claims_family.py
from claims_mech import DISEASE_MECHANISM_CLAIMS, DISCOVERY, VARIANT_SUBGROUPS  # noqa: E402,F401
from claims_therapy import THERAPIES  # noqa: E402,F401
from claims_family import FAMILY_CLAIMS  # noqa: E402,F401


def all_claims():
    out = [(c[2], c[3]) for c in DISEASE_MECHANISM_CLAIMS]
    out += [(r, n) for r, n in DISCOVERY.values()]
    out += [(e[0], e[1]) for v in VARIANT_SUBGROUPS for e in v["evidence"]]
    out += [(c[0], c[1]) for c in FAMILY_CLAIMS]
    for t in THERAPIES:
        out += [(e[0], e[1]) for e in t.get("node_evidence", [])]
        for m in t.get("targets", []):
            out += [(e[0], e[1]) for e in m[1]]
        for d in t["diseases"].values():
            out += [(e[0], e[1]) for e in d["evidence"] + d.get("counter", [])]
    return out


def referenced_ids():
    pm, nct, lab = set(), set(), set()
    for ref, _ in all_claims():
        (nct if ref.startswith("NCT") else lab if ref.startswith("FDA-label:") else pm).add(
            ref.split(":", 1)[1] if ref.startswith("FDA-label:") else ref.replace("PMID:", ""))
    return pm, nct, lab


if __name__ == "__main__":
    bad = 0
    for ref, needle in all_claims():
        try:
            print(f"OK  {ref:22s} {quote_for(ref, needle)[:110]}")
        except Exception as ex:  # noqa: BLE001
            bad += 1
            print(f"BAD {ref:22s} {ex}")
    print("unresolved:", bad)
