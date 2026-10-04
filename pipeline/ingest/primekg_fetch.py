"""Stream PrimeKG kg.csv (Harvard Dataverse doi:10.7910/DVN/IXA7BM, file 6180620, ~982 MB) and keep only
drug-disease edges (indication, contraindication, off-label use). The full file is never written to
disk; the subset goes to data/raw/downloads/primekg/kg_drug_disease.csv (gitignored).

    python3 pipeline/ingest/primekg_fetch.py
"""
import csv, io, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data/raw/downloads/primekg/kg_drug_disease.csv"
URL = "https://dataverse.harvard.edu/api/access/datafile/6180620"
KEEP = {"indication", "contraindication", "off-label use"}

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "rare-disease-atlas/ingest"})
    n = kept = 0
    with urllib.request.urlopen(req) as r, open(OUT, "w", newline="") as fo:
        rd = csv.reader(io.TextIOWrapper(r, encoding="utf-8", newline=""))
        hdr = next(rd); w = csv.writer(fo); w.writerow(hdr)
        ri = hdr.index("relation"); xt = hdr.index("x_type")
        for row in rd:
            n += 1
            if row[ri] in KEEP and row[xt] == "drug":   # kg.csv lists both directions; keep drug->disease
                w.writerow(row); kept += 1
            if n % 1000000 == 0:
                print(n, kept, file=sys.stderr, flush=True)
    print(f"rows {n} kept {kept} -> {OUT}")

if __name__ == "__main__":
    main()
