#!/usr/bin/env bash
# Rebuild the whole atlas dataset: biology, community, OpenAI cross-check, merge, copy into the app.
# Cached API responses under data/raw/ make a re-run fast and mostly offline; pass --refresh to re-fetch.
# The OpenAI step runs only when an OpenAI credential is available (Sign in with ChatGPT or OPENAI_API_KEY).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Biology layer (HGNC, MONDO/Orphanet, HPO, ClinVar, GO, PubMed)"
(cd pipeline/biology && ./run_all.sh "$@")

echo "== Community layer (ClinicalTrials.gov, NIH RePORTER, PubMed, patient-group websites)"
(cd pipeline/community && python3 fetch_ctgov.py && python3 fetch_reporter.py && python3 fetch_pubmed.py \
  && python3 fetch_web.py && python3 build_community.py)

if node integrations/openai/cli.mjs status | grep -q "auth path:.*\(chatgpt\|api_key\)"; then
  echo "== OpenAI extraction and cross-check"
  for step in extract reconcile compare; do
    [ -f "pipeline/openai/$step.mjs" ] && node "pipeline/openai/$step.mjs"
  done
else
  echo "== Skipping OpenAI cross-check (no OpenAI credential; run: node integrations/openai/cli.mjs login)"
fi

echo "== Merge and validate"
python3 pipeline/build_graph.py

echo "== Derived products (variants, therapy-approach rules, hypotheses, look-alikes, counterexamples)"
pipeline/derive/run.sh

echo "== Merge again with the hypotheses"
python3 pipeline/build_graph.py

echo "== Copy into the web app"
node web/scripts/sync-data.mjs
