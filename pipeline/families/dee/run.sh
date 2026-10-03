#!/usr/bin/env bash
# Rebuild the DEE family fragment (data/curated/family_dee.json). Cached raw responses under
# data/raw/families/dee/ make a re-run offline; pass --refresh to fetch steps to re-hit the APIs.
# NCBI calls use the shared cross-process throttle in pipeline/biology/common.py (<=2 req/s,
# tool=rare-disease-atlas, no email). Needs data/raw/downloads/{phenotype.hpoa,hp.obo,genes_to_disease.txt}.
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch_bio.py "$@"       # HGNC, UniProt, Ensembl, Monarch, OLS4, Orphadata, Open Targets
python3 clinvar.py "$@"         # ClinVar P/LP spectrum (E-utilities)
python3 quickgo.py "$@"         # GO mechanisms (+ cross-family checks against SNARE genes)
python3 hpo.py                  # IC-weighted phenotypes + similarity incl. SNAREopathies
python3 pubmed.py               # (re)fetch any PMIDs / NCTs / FDA labels the claims need
python3 curation.py | tail -1   # every needle must resolve ("unresolved: 0")
[ -x community/run.sh ] && (cd community && ./run.sh) || true   # community sub-layer (optional)
python3 build.py                # -> data/curated/family_dee.json
python3 verify.py --write       # string-match every quote + endpoint check; exit 1 on failure
