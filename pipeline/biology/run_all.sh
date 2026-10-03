#!/usr/bin/env bash
# Rebuild the biology layer from scratch. Re-runnable: every remote response is cached
# under data/raw/biology/, so a second run is offline unless you pass --refresh.
# Large HPO downloads go to data/raw/downloads/ (gitignored).
set -euo pipefail
cd "$(dirname "$0")"
ROOT=../..
mkdir -p "$ROOT/data/raw/downloads"
BASE=https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download
for f in phenotype.hpoa hp.obo genes_to_disease.txt; do
  [ -f "$ROOT/data/raw/downloads/$f" ] || curl -sSL -o "$ROOT/data/raw/downloads/$f" "$BASE/$f"
done
python3 fetch_genes.py "$@"      # HGNC + UniProt + Ensembl CDS
python3 fetch_diseases.py "$@"   # Monarch v3 + OLS4/MONDO + Orphadata + Open Targets
python3 hpo.py                   # IC, phenotype nodes, phenotype similarity
python3 clinvar.py "$@"          # ClinVar P/LP spectrum (NCBI, throttled <=2 req/s)
python3 quickgo.py "$@"          # GO process mechanisms
python3 pubmed.py                # abstracts + trial records for every curated claim
python3 build_biology.py         # assemble data/curated/biology.json
python3 verify_quotes.py --write # string-match every quote, set verified
python3 validate.py              # schema conformance
