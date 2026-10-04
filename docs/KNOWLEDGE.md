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
  - **Similarity is not a safety signal:** contraindications rank mid-pool.
  - **Direction-aware matching (drug up/down × disease LoF/GoF) is neutral on PrimeKG** (+0.004 MRR, the interval includes 0; eval.md section 6). The drug's target is a gene of the held-out disease in only 8 of 1,300 cases. When it fires it is right (8/8 match). Use it as a flag, not as a score term.
  - **Any "therapy target = disease gene" bonus is leakage on the curated 56-case benchmark:** the graph's `target_genes` are the genes of the diseases the therapy was developed for (32/56 held-out cases). An undirected target bonus lifts MRR 0.49 → 0.75. Always run that control.
  - **Pathway-level direction is about a coin flip** (117 match vs 96 mismatch over all PrimeKG pairs). Keep direction to the direct target.
- **Production scorers:**
  - deep atlas: phenotype + the drug's curated target mechanism;
  - global similar lists: phenotype + 0.5·genes + 0.5·full Reactome pathway.
- **Nested cross-validation:** always tune weights with nested CV grouped by therapy class. Non-nested tuning inflated MRR by about 0.03–0.05.

## Data traps

- **Seven-factor view (`web/lib/factors.ts`):** atlas pairs take gene, pathway, tissue, mutation, consequence (mechsim `fate`) and structure from `mechsim.json` pair scores. Symptoms are recomputed as the IC-weighted Jaccard of curated HPO symptoms in the graph, because mechsim's `symptom_cosine` is a tissue-anchor profile (VAMP2 vs STXBP1 scores 1.0 there just because both point to the brain). Non-atlas pairs use per-gene data from `web/factors` shards (HPA tissues, PANTHER/Pfam/InterPro, ClinVar spectrum) and `web/mechclass.json` (G2P/ClinGen class + direction), with symptoms/genes/pathway from `global/similar`. The atlas page is desktop-only: its fixed 3-column grid scrolls sideways at 390 px (pre-existing).

- **Direction flag in the web app** (`web/lib/direction.ts`, data slimmed by sync to `web/public/data/derived/web/direction.json`): it fires only when a curated therapy's `targets` (from `drug_direction.json` `curated`, not the graph's `target_genes`, which lists disease genes) include the disease gene. Gene-level "mixed" diseases (SCN2A, SCN8A, CACNA1A, GRIN2B, STX1B, UNC13A) fall back to per-variant-group flags. Cross-disease ideas (4-PBA → VAMP2) never get a flag, by design. `gene_direction.json` labels PTPN11 as LoF, although Noonan PTPN11 is usually GoF; no curated therapy targets PTPN11, so no flag shows, but check it before using that label elsewhere.

- **Cross-family links come from the literature, not GO.** QuickGO over all 45 genes found no TOR-signalling or ER-stress annotation at all, and MAPK cascade only for the core RAF/MEK/RAS genes. LZTR1, RIT1, SOS1, CBL and SYNGAP1 reach the MAPK cascade only through functional papers (`data/curated/cross_family.json`).
- **The connectivity metric ignores `part_of` (mechanism → mechanism) edges.** `transfer_eval.py` links diseases only through `driven_by`, gene `participates_in` and variant-group `has_effect` edges to the *same* node. A hierarchy edge does not create a cross-family link; a gene-level edge does.
- **One bridge edge can carry a whole family.** SYNGAP1 → MAPK cascade alone makes 8 RASopathies "cross-family". Report bridge counts per edge, not only per disease.
- **Avoid benchmark leakage when adding mechanism edges.** Never source a disease → target edge from the same paper as a held-out `developed_for` edge. For example, PTPN11 → mTOR from PMID 21339643 would leak the rapamycin–NSML case. Adding shared processes also widens tie sets, which can lower ranks slightly (MEK inhibitors now tie SYNGAP1 and CBL with NF1 and PTPN11).
- **Disease ids:** deep diseases are gene-defined umbrellas, `disease:<GENE>`; the specific MONDO/OMIM/ORPHA ids sit in xrefs and subtypes. The global index uses MONDO. `atlas_flags.py` links the two.
- **Sharding:** everything at global scale is sharded by `djb2(id) % 64` (Python and TypeScript match; see `data/derived/global/README.md` for the test vectors).
- **Duplicate drug nodes across layers** (amifampridine = 3,4-DAP; CAP-002 = AAV-STXBP1) are merged through `overrides.json` → `merge_nodes`.
- **Rebuild order:** if a generated `web/public/data/graph.json` conflicts on a git merge, take either side, then rebuild: `python3 pipeline/build_graph.py && node web/scripts/sync-data.mjs`.
- **Therapy `target_genes` lists disease genes, not drug targets** (the AChE inhibitor lists SYT2, the SCN8A ASO lists SCN1A). `pipeline/ingest/direction_build.py` keeps a documented `TARGET_OVERRIDE` table.
- **ChEMBL REST** returned HTTP 500 on 2026-10-04. The same ChEMBL mechanism table, with action types, is in the Open Targets Platform bulk parquet (`drug_mechanism_of_action`, `drug_molecule` for the DrugBank xrefs; about 7 MB in all).
- **Gene-level ClinGen HI scores are copied onto every dominant MONDO entry of the gene,** so they wrongly call GoF allelic disorders (SCN2A DEE11) "haploinsufficiency". Down-weight them. Direction has to be called per subtype or variant group, not per gene.
- **ClinVar** lacks most repeat expansions (e.g. the HTT CAG repeat). Say "ClinVar small variants" for those diseases.
- **Orphanet** website pages are JavaScript-rendered and unscrapeable. Use Orphadata products (prevalence = product 9, genes = product 6).
- **GeneCards** blocks automated access and needs a licence for non-academic reuse, so we don't use it.
- **Bright Data** (`pipeline/brightdata.py`) caches responses, including bad ones. Delete empty cache files before retrying a URL.
- **solve-rd.eu** showed injected spam; don't link it.
- **AI-reviewed links and the benchmark:** links proposed by the Claude reading and accepted by an AI review (`claude_reviewed.json`, `attrs.extraction: "claude"`, `review.by: ai-review:*`) are excluded by `transfer_score.py` (`_ai_proposed_ai_reviewed`). Including them lifts the curated benchmark from top-5 0.73 / MRR 0.48 to 0.79 / 0.51, which is AI grading its own homework.
- **AI buttons on the deployed site:** `AiAction` returns nothing when live AI is off and no precomputed file exists for that target (`hasPrecomputed`). Proposal and outreach drafts exist for all 45 diseases; compare and path drafts only for the pairs in `web/scripts/ai-targets.json`, so add pairs there (and draft them with `agent-ai.mjs`) to show more buttons.
- **Second readers and the benchmark:** unreviewed candidate edges from an AI reading become test cases and features of `transfer_eval.py` (Claude's 169 candidates moved the curated benchmark from 56 to 59 cases and top-5 0.73 → 0.80). Keep them out of the graph until reviewed (`data/build/claude_candidate_edges.json`); only stamps, new supporting sources and synonyms merge.
- **"Failed trial" filing:** both AI readers take "drug X was tested in disease Y" as support for `developed_for`, while curators file a negative trial as limiting. Most reader disagreements are this pattern, not errors.
- **Same-family caveat:** the curated graph was built partly by Claude agents, so Claude-vs-curator agreement is weaker evidence than OpenAI-vs-curator agreement. The Claude reading was done blind to the graph (readers saw only the instructions and the abstracts).
- **Don't regenerate the OpenAI layer from a partial checkout:** `data/raw/community/` is gitignored, so `node pipeline/openai/compare.mjs` here drops the 16 community abstracts (78 → 62). Run it only where those files exist.
- **AI drafts without a model call:** `node web/scripts/agent-ai.mjs --emit DIR --only <kind>` writes the exact evidence pack and instructions; answers go back through `--apply DIR`, which reruns `sanitizeDoc` and refuses if the graph changed since `--emit`. Drafts are labelled "Claude (agent draft)".
- **Enrollment totals:** never sum a multi-disease registry into one disease's total (Simons Searchlight lists 100,000 participants across about 200 conditions). The Research view treats a study linked to 3+ atlas diseases, or listing more than 5 conditions, as multi-disease: it is listed but "not counted". Two-disease studies stay in the sum under "overlap possible".
- **Obsolete MONDO ids in source files:** G2P and ClinGen still cite some obsolete MONDO ids (Dravet MONDO:0011794 → MONDO:0100135). `global_index.py` exports `mondo_replaced` from `mondo-base.obo`, and `mechanism_index.py` follows it, with a fallback table for older intermediates.
- **Drugs without a ChEMBL mechanism record** (relutrigine, NBI-921352) get their direction from `CURATED_DIRECTION` in `direction_build.py`, each with a PMID and a verbatim quote. `python3 pipeline/ingest/direction_build.py --curated-only` re-classifies the atlas therapies without any download, reusing the ChEMBL table already in `drug_direction.json`.
- **Cloud (claude.ai/code) sessions** could not reach EBI (G2P, Open Targets FTP), ClinGen or purl.obolibrary.org on 2026-10-04, while GitHub, NCBI-backed PubMed tools and storage.googleapis.com (HGNC) worked. Global-layer reruns need a machine with `data/raw/downloads/`.
- **Edge and node patches in `overrides.json` replace whole fields** (`dict.update`) before the OpenAI cross-check runs. So: copy the full current list when patching `evidence`/`counter_evidence`; a patched list hides evidence that fragments add later; patch `status` yourself when removing all counter-evidence (the build only promotes supported → contested, never back); node `xrefs`/`attrs` must be complete. Keys starting with `_` (e.g. `_review`) are not copied into the graph.
- **To dismiss an AI-only contradiction, move it, don't delete it.** The cross-check re-adds any crosscheck paper whose ref is not already on the edge. Moving it to `evidence` (or keeping it with `needs_review` cleared) is what makes the decision stick.
- **Common curation errors found by the AI review (2026-10-04):**
  - sources about a sibling gene cited on a link (VAMP2/SNAP25 papers on SYT1 and STXBP1 therapy links);
  - one sentence filed as both support and counter-evidence;
  - a positive result filed as a "limit" (the quote must state the limitation);
  - "clinical" level on iPSC-only data;
  - author speculation ("likely", "thought to") recorded as experimental.
  Check these first in any new curation.
- **Some mechanism labels are frame-dependent.** CBL is "loss of ligase function" or "gain of signalling" (G2P says GoF). SYT1 P401L has more release, but the authors call it dominant-negative. SNAP25 I67N is LoF and also DN, because it inhibits even with wild-type present. Record both readings with sources instead of picking one silently.
- **Don't build a graph for commit while other agents have uncommitted fragments in `data/curated/`.** The build globs every `*.json` there. To commit a consistent graph, build from `git ls-files data/curated` in a scratch copy.

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
  Known hits on 2026-10-04: org slugs ending in "sk-" (e.g. "cystisk-fibros"), DisMech text, and this file itself are false positives. `data/raw/testing/fedreg_clia_hipaa_2014.html` holds a federalregister.gov sign-in JWT from the saved page: strip it before making the repo public.

## People and credit

- **Team:** two first-year ETH Zurich students (electrical engineering and biochemistry), plus collaborator Chronify-CH, who built the mechanistic similarity layer, AlphaFold TM-align, research recommendations and `/mechanisms`.
- **Thanks:** to Woan-Yu Lin (RTW Foundation) and Joe Katakowski for conversations. They are mentioned in the README only, not on the site.
- **Data credits:** DisMech (Monarch Initiative, BSD-3), PrimeKG (MIT/CC0), Orphadata (CC-BY-4.0), AlphaMissense (see the licence note in `data/derived/ingest/README.md`), and the public NCBI, EBI and NIH resources.
