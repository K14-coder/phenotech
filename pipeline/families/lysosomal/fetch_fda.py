"""FDA prescribing information (openFDA drug label API) for approved lysosomal therapies.

Run:  python3 pipeline/families/lysosomal/fetch_fda.py [--refresh]
Out:  data/raw/families/lysosomal/fda/<slug>.json  (raw openFDA response; quotes are matched against
      the label sections listed in lyso_common.LABEL_FIELDS)
The evidence URL is the DailyMed page for the label's set_id, so a reader can open the same label.
"""
import sys
import time

from lyso_common import FDA_DIR, cached_json

REFRESH = "--refresh" in sys.argv
BRANDS = {  # slug -> openFDA brand name
    "cerezyme": "CEREZYME", "cerdelga": "CERDELGA", "zavesca": "ZAVESCA",
    "lumizyme": "LUMIZYME", "nexviazyme": "NEXVIAZYME", "pombiliti": "POMBILITI", "opfolda": "OPFOLDA",
    "fabrazyme": "FABRAZYME", "elfabrio": "ELFABRIO", "galafold": "GALAFOLD",
    "miplyffa": "MIPLYFFA", "aqneursa": "AQNEURSA", "xenpozyme": "XENPOZYME",
    "aldurazyme": "ALDURAZYME", "elaprase": "ELAPRASE", "brineura": "BRINEURA", "lenmeldy": "LENMELDY",
    "vpriv": "VPRIV", "elelyso": "ELELYSO",
}


def main():
    for slug, brand in BRANDS.items():
        try:
            obj = cached_json(FDA_DIR / f"{slug}.json", "https://api.fda.gov/drug/label.json",
                              params={"search": f'openfda.brand_name:"{brand}"', "limit": 1}, refresh=REFRESH)
        except Exception as ex:  # noqa: BLE001  (404 = no label in openFDA)
            print(f"  ! {slug}: {str(ex)[:100]}")
            continue
        r = (obj.get("results") or [{}])[0]
        of = r.get("openfda", {})
        print(f"{slug}: set_id={r.get('set_id')} generic={of.get('generic_name')} eff={r.get('effective_time')}")
        print("    IND:", " ".join(r.get("indications_and_usage", [""]))[:400])
        time.sleep(0.3)


if __name__ == "__main__":
    main()
