"""ClinicalTrials.gov API v2 pulls for the lysosomal family.

Run:  python3 pipeline/families/lysosomal/fetch_ctgov.py
Out:  data/raw/families/lysosomal/ctgov/search/<slug>.json  ({query, url, retrieved, n, studies})
      data/raw/families/lysosomal/ctgov/studies/<NCT>.json  (one raw v2 record per study, used for
      quote verification)
"""
import json
import time
import urllib.parse

from lyso_common import CT_DIR, TODAY, http_get, slugify, write_json

BASE = "https://clinicaltrials.gov/api/v2/studies"
QUERIES = {  # gene -> query.cond values
    "GBA1": ["Gaucher Disease"], "GAA": ["Pompe Disease"], "GLA": ["Fabry Disease"],
    "HEXA": ["Tay-Sachs Disease", "GM2 Gangliosidosis"], "NPC1": ["Niemann-Pick Disease, Type C"],
    "SMPD1": ["Acid Sphingomyelinase Deficiency", "Niemann-Pick Disease, Type A", "Niemann-Pick Disease, Type B"],
    "IDUA": ["Mucopolysaccharidosis I"], "IDS": ["Mucopolysaccharidosis II"],
    "CLN3": ["CLN3 Disease", "Juvenile Neuronal Ceroid Lipofuscinosis"],
    "TPP1": ["CLN2 Disease", "Late Infantile Neuronal Ceroid Lipofuscinosis"],
    "ARSA": ["Metachromatic Leukodystrophy"], "GALC": ["Krabbe Disease", "Globoid Cell Leukodystrophy"],
}


def fetch(value: str) -> dict:
    studies, token, pages = [], None, 0
    while True:
        q = {"query.cond": value, "pageSize": 100, "format": "json"}
        if token:
            q["pageToken"] = token
        data = json.loads(http_get(f"{BASE}?{urllib.parse.urlencode(q)}", headers={"Accept": "application/json"}))
        studies.extend(data.get("studies", []))
        token, pages = data.get("nextPageToken"), pages + 1
        time.sleep(0.4)
        if not token or pages >= 4:
            break
    return {"query": {"query.cond": value}, "url": f"{BASE}?{urllib.parse.urlencode({'query.cond': value})}",
            "retrieved": TODAY, "n": len(studies), "studies": studies}


def main():
    for gene, values in QUERIES.items():
        for v in values:
            res = fetch(v)
            write_json(CT_DIR / "search" / f"{gene}__{slugify(v)}.json", res)
            for s in res["studies"]:
                nct = s["protocolSection"]["identificationModule"]["nctId"]
                write_json(CT_DIR / "studies" / f"{nct}.json", s)
            print(f"{gene} {v!r}: {res['n']} studies", flush=True)


if __name__ == "__main__":
    main()
