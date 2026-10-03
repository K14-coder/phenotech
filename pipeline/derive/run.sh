#!/usr/bin/env bash
# Rebuild every derived data product. Re-runnable and offline after the first run:
# the ClinVar, HPO and PubMed payloads it reads are all cached under data/raw/.
#
#   ./pipeline/derive/run.sh              # rebuild everything from the cached sources
#   ./pipeline/derive/run.sh --refresh     # also re-fetch the PubMed/CT.gov sources this layer cites
#
# Reads:  data/graph.json, data/raw/biology/clinvar/, data/raw/biology/hpo_stats.json,
#         data/raw/downloads/{phenotype.hpoa,hp.obo,genes_to_disease.txt}, data/raw/derive/
# Writes: data/derived/{variants,variant_lookup_spec.md,variant_test_cases,beyond_slice,
#                       opportunities,counterexamples}.json
#         data/derived/global/{index,meta}.json, data/derived/global/neighbours/<0..63>.json
#         data/raw/downloads/mondo-base.obo (gitignored; downloaded once, re-fetched with --refresh)
#         data/curated/{modality,hypotheses}.json
#         data/raw/derive/{pubmed,ctgov,search_log.json}
# Touches nothing else: not web/, not integrations/, not data/graph.json, not other curated files.
#
# NOTE: data/curated/modality.json and data/curated/hypotheses.json are schema fragments, so the
# next `python3 pipeline/build_graph.py` will merge hypotheses.json into data/graph.json (the
# candidate_for edges are hypothesis-level, confidence <= 0.25, drawn dashed). modality.json is a
# standalone draft rule set and contributes no nodes or edges.
set -euo pipefail
cd "$(dirname "$0")"
REFRESH="${1:-}"

echo "== 0/6 sources this layer cites (PubMed E-utilities <=2 req/s, tool=rare-disease-atlas, no email)"
python3 fetch_literature.py ${REFRESH:+--refresh}

echo "== 1/6 variant lookup (ClinVar P/LP records -> data/derived/variants.json) + test cases"
python3 variants.py

echo "== 2/6 modality fit (draft rule set -> data/curated/modality.json)"
python3 modality.py

echo "== 3/6 hypotheses + opportunities (graph analytics)"
python3 hypotheses.py

echo "== 4/6 beyond the slice (HPO phenotype neighbours; reuses pipeline/biology/hpo.py)"
python3 beyond_slice.py

echo "== 5/6 counterexamples"
python3 counterexamples.py

echo "== 6/6 global disease index (every HPO/gene-annotated disease; MONDO identity; ~15 s)"
MONDO_OBO=../../data/raw/downloads/mondo-base.obo
if [ ! -s "$MONDO_OBO" ] || [ -n "$REFRESH" ]; then
  echo "   downloading mondo-base.obo (MONDO terms with EXACT synonyms and equivalentTo xrefs, ~50 MB)"
  curl -sSL -o "$MONDO_OBO" https://github.com/monarch-initiative/mondo/releases/latest/download/mondo-base.obo
fi
if command -v uv >/dev/null 2>&1; then
  uv run --quiet --with numpy --with scipy python3 global_index.py
else
  python3 global_index.py   # needs numpy + scipy installed
fi

cd ../..
echo
echo "== sizes (neighbour shards: $(du -sh data/derived/global/neighbours 2>/dev/null | cut -f1) in 64 files)"
ls -l data/derived/*.json data/derived/*.md data/curated/modality.json data/curated/hypotheses.json \
  data/derived/global/index.json data/derived/global/meta.json \
  | awk '{printf "  %8.1f KB  %s\n", $5/1024, $9}'
