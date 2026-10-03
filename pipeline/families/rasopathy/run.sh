#!/usr/bin/env bash
# Rebuild the RASopathy family fragment (data/curated/family_rasopathy.json).
# Every remote response is cached under data/raw/families/rasopathy/, so a re-run is fast and
# offline; pass --refresh to the fetch steps that support it to re-hit the APIs.
# NCBI: shared cross-process throttle (<= 2 req/s, pipeline/biology/common.py), tool=rare-disease-atlas, no email.
# Bright Data: only cached Web Unlocker calls (hard cap 150, counted in data/raw/families/rasopathy/bd_usage.json).
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch_bio.py "$@"        # HGNC, UniProt, Ensembl, Monarch (OMIM/Orphanet/ClinGen), Orphadata, Open Targets
python3 clinvar.py "$@"          # ClinVar P/LP spectrum per gene (E-utilities)
python3 quickgo.py "$@"          # GO process mechanisms (Ras signal transduction, MAPK cascade, ...)
python3 hpo.py                   # IC over all phenotype.hpoa diseases; phenotypes + similarity
python3 discover.py              # PubMed discovery searches (logged to pubmed_searches.json)
python3 fetch_labels.py "$@"     # FDA labels (openFDA): selumetinib, mirdametinib, trametinib
python3 fetch_ctgov.py "$@"      # ClinicalTrials.gov API v2 searches
python3 pubmed.py                # every PMID / NCT record that curation.py cites
python3 fetch_web.py             # patient-organisation pages (direct fetch)
python3 fetch_web.py --bd costellokids-home   # cached Bright Data Web Unlocker attempt (Costello network)
python3 fetch_authors.py         # PubMed senior authors per gene (research groups)
python3 curation.py | tail -1    # resolve every needle against the stored sources (must be 0 unresolved)
python3 build.py                 # assemble data/curated/family_rasopathy.json
python3 verify.py --write        # string-match every quote, check endpoints/schema (exit 1 on failure)
python3 ../../build_graph.py     # merge into data/graph.json; expect "Problems: None." in data/build/report.md
