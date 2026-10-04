"""Fetch study contact details from ClinicalTrials.gov API v2 for every study referenced in
data/graph.json and data/derived/scale/trials.json.

Only the CENTRAL CONTACT (published by the sponsor so participants can reach the study) is kept
as contact data, and only for studies whose *current* status is RECRUITING or NOT_YET_RECRUITING.
Overall officials: affiliation + role only (no names). Locations: facility, city, country, status
only (site-level contacts are dropped).

Raw API pages are cached in data/raw/contacts/ctgov/ (re-runs are free; pass --refresh to refetch).
Output: data/raw/contacts/trials_extracted.json (validated + written to derived by build.py).
"""

import datetime
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "contacts" / "ctgov"
OUT = ROOT / "data" / "raw" / "contacts" / "trials_extracted.json"
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ",".join([
    "protocolSection.identificationModule",
    "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "protocolSection.contactsLocationsModule",
])
KEEP = {"RECRUITING", "NOT_YET_RECRUITING"}


def referenced_ncts():
    ids = set()
    g = json.loads((ROOT / "data" / "graph.json").read_text())
    for n in g["nodes"]:
        if n["type"] == "study":
            nct = (n.get("xrefs") or {}).get("NCT") or n["id"].split(":", 1)[1]
            ids.add(nct)
    t = json.loads((ROOT / "data" / "derived" / "scale" / "trials.json").read_text())
    ids.update(t["studies"].keys())
    return sorted(i for i in ids if i.startswith("NCT"))


def fetch_batch(batch, idx, refresh):
    f = RAW / f"batch_{idx:04d}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    q = urllib.parse.urlencode({"filter.ids": ",".join(batch), "fields": FIELDS, "pageSize": 100})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "rare-disease-atlas/contacts"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            break
        except Exception as e:  # noqa: BLE001
            print("retry", idx, e)
            time.sleep(2 + 3 * attempt)
    else:
        raise RuntimeError(f"batch {idx} failed")
    rec = {"query_ids": batch, "retrieved": datetime.date.today().isoformat(), "response": data}
    f.write_text(json.dumps(rec))
    time.sleep(0.3)
    return rec


def main():
    refresh = "--refresh" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    ncts = referenced_ncts()
    print("referenced studies:", len(ncts))
    out, statuses = {}, {}
    for i in range(0, len(ncts), 100):
        rec = fetch_batch(ncts[i:i + 100], i // 100, refresh)
        for s in rec["response"].get("studies", []):
            ps = s.get("protocolSection", {})
            ident = ps.get("identificationModule", {})
            nct = ident.get("nctId")
            status = ps.get("statusModule", {}).get("overallStatus")
            statuses[status] = statuses.get(status, 0) + 1
            if status not in KEEP:
                continue
            clm = ps.get("contactsLocationsModule", {})
            central = []
            for c in clm.get("centralContacts", []) or []:
                central.append({k: c[k] for k in ("name", "role", "phone", "phoneExt", "email") if c.get(k)})
            officials = [{k: o[k] for k in ("role", "affiliation") if o.get(k)}
                         for o in clm.get("overallOfficials", []) or []]
            officials = [o for o in officials if o.get("affiliation")]
            locs = [{k: l[k] for k in ("facility", "city", "state", "country", "status") if l.get(k)}
                    for l in clm.get("locations", []) or []]
            out[nct] = {
                "nct": nct,
                "title": ident.get("briefTitle"),
                "status": status,
                "sponsor": ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
                "central_contacts": central,
                "official_affiliations": officials,
                "locations": locs,
                "source_url": f"https://clinicaltrials.gov/study/{nct}",
                "api_url": f"{API}/{nct}",
                "retrieved": rec["retrieved"],
            }
    OUT.write_text(json.dumps({"meta": {"referenced": len(ncts), "current_status_counts": statuses},
                               "studies": out}, indent=1, ensure_ascii=False))
    print("statuses:", statuses)
    print("kept (recruiting/not yet):", len(out), "with central contact:",
          sum(1 for v in out.values() if v["central_contacts"]))


if __name__ == "__main__":
    main()
