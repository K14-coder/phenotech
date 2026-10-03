#!/usr/bin/env bash
# Rebuild the lysosomal storage disorder family fragment. Cached responses under data/raw/families/lysosomal/
# make a re-run fast and offline; delete a cache file (or pass --refresh to fetch_biology/clinvar/fetch_fda) to re-fetch.
# Needs data/raw/downloads/{phenotype.hpoa,hp.obo,genes_to_disease.txt} (see docs/agent-reports/biology.md).
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch_biology.py "$@"     # HGNC, UniProt, Ensembl, Monarch, Orphadata, Open Targets
python3 clinvar.py "$@"           # ClinVar P/LP spectrum (shared NCBI throttle)
python3 hpo.py                    # IC-weighted phenotypes + similarity (incl. cross-family vs SNAREopathies)
python3 fetch_fda.py "$@"         # FDA labels via openFDA
python3 fetch_ctgov.py            # ClinicalTrials.gov API v2
python3 fetch_web.py              # patient-organisation pages listed in web_sources.json
python3 check_orgs.py             # every org/asset quote string-matched against the stored page
python3 -c "import curation, lyso_common as L; L.fetch_pmids(sorted(r for r in curation.all_refs() if r.startswith('PMID:')))"
python3 curation.py | tail -1     # every needle must resolve to exactly one stored sentence
python3 research_groups.py        # senior authors of recent title-matched PubMed papers
python3 build_fragment.py         # -> data/curated/family_lysosomal.json
python3 verify.py --write         # independent quote + endpoint verification (exit 1 on any failure)
cd ../../.. && python3 pipeline/build_graph.py && grep -A2 "## Problems" data/build/report.md
