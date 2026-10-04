# Tasukeru: project knowledge

The non-obvious things we learned, the decisions we made and why, and the traps. Read this together with `CLAUDE.md` (how to run, status) and `docs/TODO.md` (what's next). The layer reports in `docs/agent-reports/` hold the details.

## Product decisions

- **The challenge:** Hack-Nation Challenge 05, "AI Atlas for the World's Rare Diseases" (OpenAI × Buffalo Initiative).
  - Judging covers graph quality, evidence integrity, patient progress, 10× impact and product craft.
  - Prize-track eligibility requires using OpenAI models or tools.
- **The name:** Tasukeru (助ける, "to help"). The internal ids, routes and Vercel project still say rare-disease-atlas.
- **Four views:** Simple is the default, for families; then Detailed (patient-group leaders), Research and Industry. The internal ids are family, leader, researcher and biotech, and `?as=` overrides the view. Persona names (Devon, Maria and so on) are deliberately not shown.
- **Depth plus breadth:**
  - 45 diseases are curated in depth with verbatim quotes.
  - About 10k diseases have automated, sourced breadth data.
  - 11,456 are searchable.
  - Every page states which tier it is in.
- **No medical advice.** Treatment evidence is always "to discuss with your clinician"; the variant/VCF tools say "not a diagnostic test".
- **Privacy:**
  - Show organisations' published contacts, people an organisation itself names on its own site as its contact, and ClinicalTrials.gov central contacts for recruiting studies.
  - **Never** individual researchers' personal contact details, and never combine sources to find a person's details.
  - Researcher contact goes through a relay, only to members who opted in.
  - Interest counts are shown only when there are at least 5 people.

## Evidence rules (enforced in code)

- Never invent an id, PMID, NCT id, URL or quote.
- **Quotes:** literature quotes are stored as short "needles" that resolve to one verbatim sentence in a stored source. Separate verifiers re-read the sources from disk. A quote that doesn't match is rejected, never "fixed".
- **Evidence levels:** clinical, curated, experimental, observational, inferred, hypothesis. Hypotheses are drawn dashed and capped at confidence 0.25.
- **Counter-evidence:** an edge with reviewed counter-evidence is marked contested. Contradictions found only by the OpenAI cross-check wait for human review (`needs_review`).
- **Human and AI review** go through `data/curated/overrides.json` (merges, drops, node and edge patches). AI reviews must say `ai-review:...`, never pose as human ones.

## What the benchmarks taught us (important for model changes)

- **Curated leave-one-out** (56 therapy→disease cases, `pipeline/eval/transfer_eval.py`):
  - phenotype + specificity-weighted mechanism → top-5 recall 0.73, MRR 0.49 (random 0.12 / 0.10);
  - drug-target-aware;
  - partly circular, because the curators built both the graph and the test.
- **PrimeKG external benchmark** (1,300 cases, `pipeline/eval/primekg_eval.py`, about 10 s; use it as a regression test):
  - **Phenotype (HPO IC) is the only factor that works across different genes.**
  - "Same gene" is the second signal, and Reactome pathways and protein families add a little.
  - Tissue, ClinVar mutation spectrum, gnomAD constraint, AlphaMissense and AlphaFold structure didn't improve ranking. They're shown as explanations instead.
  - **Coarse mechanism class (LoF/GoF) makes ranking worse.**
  - **Similarity is not a safety signal:** contraindications rank mid-pool. That's why direction-aware matching is being tested.
- **Production scorers:**
  - deep atlas: phenotype + the drug's curated target mechanism;
  - global similar lists: phenotype + 0.5·genes + 0.5·full Reactome pathway.
- **Nested cross-validation:** always tune weights with nested CV grouped by therapy class. Non-nested tuning inflated MRR by about 0.03–0.05.

## Data traps

- **Disease ids:** deep diseases are gene-defined umbrellas, `disease:<GENE>`; the specific MONDO/OMIM/ORPHA ids sit in xrefs and subtypes. The global index uses MONDO. `atlas_flags.py` links the two.
- **Sharding:** everything at global scale is sharded by `djb2(id) % 64` (Python and TypeScript match; see `data/derived/global/README.md` for the test vectors).
- **Duplicate drug nodes across layers** (amifampridine = 3,4-DAP; CAP-002 = AAV-STXBP1) are merged through `overrides.json` → `merge_nodes`.
- **Rebuild order:** if a generated `web/public/data/graph.json` conflicts on a git merge, take either side, then rebuild: `python3 pipeline/build_graph.py && node web/scripts/sync-data.mjs`.
- **ClinVar** lacks most repeat expansions (e.g. the HTT CAG repeat). Say "ClinVar small variants" for those diseases.
- **Orphanet** website pages are JavaScript-rendered and unscrapeable. Use Orphadata products (prevalence = product 9, genes = product 6).
- **GeneCards** blocks automated access and needs a licence for non-academic reuse, so we don't use it.
- **Bright Data** (`pipeline/brightdata.py`) caches responses, including bad ones. Delete empty cache files before retrying a URL.
- **solve-rd.eu** showed injected spam; don't link it.

## Infrastructure

- **Vercel:** project `rare-disease-atlas`, account khezanirani-3585 (team "khezan"), and `web/` is linked to it. Two crons in `web/vercel.json`: `/api/cron/digest` (live trial and grant alerts) and `/api/queue/sweep`.
  - **Env vars:**
    - KV (Upstash);
    - `SESSION_SECRET`, `ADMIN_TOKEN`, `CRON_SECRET`;
    - `EMAIL_FROM="Tasukeru <no-reply@mehro.ch>"`;
    - `SMTP_HOST=mail.infomaniak.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASS` (secret).
  - A new env var only takes effect after a redeploy.
- **Local:**
  - the file store in `web/.data/`; never point local tests at production Redis;
  - the root `.env.local` holds the Bright Data token and the admin token;
  - `web/.env.local` comes from `vercel link`.
- **OpenAI:**
  - Sign in with ChatGPT works only for locally running apps; the hosted-site flow is waitlisted.
  - The plan's per-app cap runs out quickly, so batch AI work and use `--ids` with `precompute-ai.mjs`.
  - The API key in `.env.local` has had no credits.
- **Research queue:** a 7-hour lease, incomplete diseases requeued at the top, a cap of 3 rounds, and the server re-verifies every quote. Volunteers use their own OpenAI or Anthropic key in the browser, or the local worker (ChatGPT plan).
- **Secret scan** before any publish:
  ```bash
  git ls-files | xargs grep -lE "sk-[A-Za-z0-9_-]{20,}|sk-proj-|Bearer [A-Za-z0-9._-]{24,}|eyJ[A-Za-z0-9_-]{30,}\.|gho_[A-Za-z0-9]{20,}"
  ```
  Also check that no personal emails are committed.

## People and credit

- **Team:** two first-year ETH Zurich students (electrical engineering and biochemistry), plus collaborator Chronify-CH, who built the mechanistic similarity layer, AlphaFold TM-align, research recommendations and `/mechanisms`.
- **Thanks:** to Woan-Yu Lin (RTW Foundation) and Joe Katakowski for conversations. They are mentioned in the README only, not on the site.
- **Data credits:** DisMech (Monarch Initiative, BSD-3), PrimeKG (MIT/CC0), Orphadata (CC-BY-4.0), AlphaMissense (see the licence note in `data/derived/ingest/README.md`), and the public NCBI, EBI and NIH resources.
