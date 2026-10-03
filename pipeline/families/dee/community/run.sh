#!/usr/bin/env bash
# Re-runs the DEE community sub-layer. Every fetcher skips what is already stored, so a re-run is
# offline unless raw files are deleted (Bright Data responses are cached in
# data/raw/families/dee/community/brightdata; budget 100 requests, logged in bd_usage.json).
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch_ctgov.py      # ClinicalTrials.gov API v2 -> data/raw/families/dee/community/ctgov/
python3 fetch_reporter.py   # NIH RePORTER v2 (FY2020-2026) -> .../reporter/
python3 fetch_pubmed.py     # PubMed via pipeline/biology/common.py eutils() (shared throttle, no email) -> .../pubmed/
python3 fetch_web.py        # org / registry pages in web_sources.json (direct first, Bright Data fallback) -> .../web/
python3 build_community.py  # -> community_fragment.json + summary.json
python3 verify_community.py # string-matches every quote against the stored sources; non-zero exit on failure
