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
#         data/derived/global/mechanism/<0..63>.json, data/derived/global/clusters.json
#         data/derived/global/{dismech,dismech_evidence}/<0..63>.json, dismech_index.json, index_extra.json,
#         dismech_atlas_links.json (+ the `dismech` section of meta.json)
#         data/raw/downloads/ (gitignored): mondo-base.obo, g2p_all.csv, clingen_*.csv/.tsv, Reactome files,
#         and the intermediates global_entries.json / global_vectors.npz (downloaded once; --refresh re-fetches)
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

echo "== 0/7 sources this layer cites (PubMed E-utilities <=2 req/s, tool=rare-disease-atlas, no email)"
python3 fetch_literature.py ${REFRESH:+--refresh}

echo "== 1/7 variant lookup (ClinVar P/LP records -> data/derived/variants.json) + test cases"
python3 variants.py

echo "== 2/7 modality fit (draft rule set -> data/curated/modality.json)"
python3 modality.py

echo "== 3/7 hypotheses + opportunities (graph analytics)"
python3 hypotheses.py

echo "== 4/7 beyond the slice (HPO phenotype neighbours; reuses pipeline/biology/hpo.py)"
python3 beyond_slice.py

echo "== 5/7 counterexamples"
python3 counterexamples.py

echo "== 6/7 global disease index (every HPO/gene-annotated disease; MONDO identity; ~15 s)"
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

echo "== 7/7 mechanism layer (G2P + ClinGen mechanism class, Reactome mid-level pathways, Leiden clusters)"
DL=../../data/raw/downloads
fetch() { [ -s "$DL/$1" ] && [ -z "$REFRESH" ] || curl -sSL --max-time 600 -o "$DL/$1" "$2"; }
fetch g2p_all.csv https://www.ebi.ac.uk/gene2phenotype/api/panel/all/download/
fetch clingen_gene_validity.csv https://search.clinicalgenome.org/kb/gene-validity/download
fetch clingen_gene_dosage.csv https://search.clinicalgenome.org/kb/gene-dosage/download
fetch ClinGen_gene_curation_list_GRCh38.tsv https://ftp.clinicalgenome.org/ClinGen_gene_curation_list_GRCh38.tsv
for f in NCBI2Reactome.txt ReactomePathways.txt ReactomePathwaysRelation.txt; do
  fetch "$f" "https://reactome.org/download/current/$f"
done
if command -v uv >/dev/null 2>&1; then
  uv run --quiet --with numpy --with scipy --with igraph --with leidenalg python3 mechanism_index.py
else
  python3 mechanism_index.py   # needs numpy, scipy, python-igraph, leidenalg
fi
# When a family lands in data/curated/family_*.json, only this is needed (stdlib, < 1 s):
#   python3 pipeline/derive/atlas_flags.py

echo "== 8/8 DisMech (Monarch Initiative, BSD-3-Clause): curated mechanism pathographs + verbatim evidence"
DMR="$DL/dismech"
if [ ! -d "$DMR/kb/disorders" ]; then
  git clone --depth 1 --quiet https://github.com/monarch-initiative/dismech "$DMR"   # ~1 GB checkout
elif [ -n "$REFRESH" ]; then
  git -C "$DMR" pull --depth 1 --quiet --ff-only || echo "   (dismech pull failed; using the pinned clone)"
fi
echo "   dismech commit $(git -C "$DMR" rev-parse HEAD)"
if command -v uv >/dev/null 2>&1; then
  uv run --quiet --with pyyaml python3 dismech.py
else
  python3 dismech.py   # needs pyyaml
fi

cd ../..
echo
echo "== sizes (neighbour shards: $(du -sh data/derived/global/neighbours 2>/dev/null | cut -f1); mechanism shards: $(du -sh data/derived/global/mechanism 2>/dev/null | cut -f1); 64 files each)"
ls -l data/derived/*.json data/derived/*.md data/curated/modality.json data/curated/hypotheses.json \
  data/derived/global/index.json data/derived/global/meta.json data/derived/global/clusters.json \
  | awk '{printf "  %8.1f KB  %s\n", $5/1024, $9}'
