# Tasukeru: to-do list

Keep this file current: tick items when done (with the commit), and add new ones at the right priority. Items marked **(you)** need a human; everything else an agent can do. Read `CLAUDE.md` and `docs/KNOWLEDGE.md` first.

## How to work on this list without duplicating work

Several Claude agents and people work in parallel. Follow this every time:

1. `git pull` first, then read this file.
2. **Claim** an open item before starting. Change `- [ ]` to `- [~] (claimed by <name/agent>, <YYYY-MM-DD HH:MM CEST>)`, then commit and push that one-line change immediately. If the push is rejected, pull and re-check that nobody else claimed it.
3. Never start an item marked `[~]` unless its claim is more than 3 hours old with no related commits. In that case, take it over and note this in the claim.
4. **Stay inside the files your item needs.** Generated files (`data/graph.json`, `web/public/data/**`) are rebuilt with `python3 pipeline/build_graph.py && node web/scripts/sync-data.mjs`; never hand-edit them. On a merge conflict in a generated file, take either side and rebuild.
5. When done: run `npm run build` in `web/` if you touched `web/`, commit with a clear message, then `git pull --no-rebase && git push`. Change the item to `- [x]` and add a line under "Done". Deploy with `cd web && npx vercel deploy --prod` only if you have Vercel access.
6. Write what you learned that isn't obvious into `docs/KNOWLEDGE.md`, and new follow-ups into this list.

## P0: submission blockers

- [~] (claimed by main-session web agent, 2026-10-04) **Rename to Phenotech** everywhere (site, emails, worker, docs; `EMAIL_FROM` on Vercel is already "Phenotech <no-reply@mehro.ch>") **plus atlas controls:** hop-depth slider from the searched/focused item, toggles to hide link types and factor links, hide node types and individual nodes, lens links limited to the shown neighbourhood.

- [ ] **(you, later)** Make the repo public before submission (team decision: later). The GitHub repo `K14-coder/rare-disease-atlas` is private for now. Either make it public, or share it the way Hack-Nation asks. Run a final secret scan before making it public (see KNOWLEDGE.md → "Secret scan").
- [x] (vibrant-babbage, 2026-10-04) Refresh `README.md` for the current product: Tasukeru, depth/breadth tiers, four views, `/sequence` with genome-wide ClinVar, community and research queue, both benchmarks, OpenAI use, updated architecture diagram, acknowledgements.
- [x] (vibrant-babbage, 2026-10-04) Refresh `docs/video-script.md`: Tasukeru name, current `/method` numbers (⟨…⟩ marks numbers to re-check before recording), the 8-step "Follow a patient group" tour as the 1-minute walkthrough.
- [ ] **(you)** Record the team video and the 1-minute walkthrough.
- [ ] Do a final consistency pass on the deployed site:
  - Simple view on a phone;
  - the guided tours still match the UI;
  - no console errors;
  - load times.

- [x] (vibrant-babbage, 2026-10-04) No AI buttons that fail on the deployed site: `AiAction` renders only where a precomputed result exists when live AI is off (compare and path pairs without a draft no longer show a button). Tour buttons renamed "Take a tour".

## P1: model and evidence quality

- [x] (web agent, commit 912f426) **Seven-factor view everywhere (must-have):** genes involved, signalling pathway, tissue type, symptoms, protein structure and families, mutation type and molecular consequence. Covers the factor fingerprint on disease pages, per-factor breakdowns on similar-disease and compare views, a factor lens and weights in the atlas, and the use of `data/derived/mechsim.json` (colleague) plus the features and ingest data.

- [ ] Fix the PTPN11 direction in `data/derived/direction/gene_direction.json`: Noonan PTPN11 is gain of function, and only NSML is loss of function. Split by variant group / subtype (`pipeline/ingest/direction_build.py`).

- [x] **Direction-aware therapy matching** (done 2026-10-04): neutral on PrimeKG, no contraindication shift, atlas gain = target leakage → keep it as a flag only. See eval.md section 6.
- [x] (done 2026-10-04, commit 19be6ce) **Independent AI review of the review sheet** → `docs/review/ai-review-2026-10-04.md` and patches in `data/curated/overrides.json`. Review records use `by: "ai-review:claude"`.
  - [x] (web agent, commit 2a3070c) Web: render ai-review records as "Independently reviewed by AI (not a human expert)". Human reviews keep "Reviewed by a biochemist".
  - [ ] **(you, optional)** A human expert works through the "needs-human" list from that report.
    - SYT1 → gain of function (P401L: the authors call it dominant-negative, i.e. loss of clamping): keep or reject?
    - VAMP2 → protein destabilization (really SNARE-complex instability): reject? Same for `vg:VAMP2:missense|has_effect|mech:protein-destabilization`.
    - AChE inhibitors → targets Ca2+-triggered exocytosis (pharmacologically wrong): re-point or reject; the SNAP25 AChEI hypothesis depends on it.
    - CBL → loss of function vs G2P "gain of function" (disease and missense variant group): choose the class.
    - Aminopyridines → SYT1: is there a published SYT1 patient on 4-AP/3,4-DAP? If so, restore the clinical level.
    - SYT2 → dominant-negative: add functional evidence if any exists.
  - [ ] `pipeline/build_graph.py`: count `ai-review:*` records separately from human reviews in `data/build/report.md` (it currently says "Human-reviewed edges: 63").
  - [ ] `pipeline/review_sheet.py` should skip or mark `ai-review` items, and the sheet should be regenerated (its item 20 uses a pre-merge id).
- [x] **Cross-family biology**: done (2026-10-04). `data/curated/cross_family.json`: 24 quote-verified edges + `mech:autophagy`; 11/45 → 29/45 diseases with a specific cross-family mechanism. See `docs/agent-reports/cross-family.md`.
  - [ ] Follow-up: close `gap:ras-to-mapk-hierarchy` in `data/curated/mechanism_hierarchy.json` (answered at gene level by cross_family.json).
  - [ ] Follow-up: find PTPN11 → mTOR evidence independent of PMID 21339643 (the rapamycin-NSML paper; using it would leak into the benchmark).
  - [ ] Follow-up: still not cross-linked: KCNT1, SCN2A, SCN8A, SLC2A1, ARSA, GALC, IDS, IDUA, SMPD1, TPP1, CPLX1, NSF, SNAP25, STX1A, STX1B, UNC13A. Candidates: non-IEA evidence for SNAP25/STX1B in Ca2+-triggered exocytosis, an HCN/excitability node for NF1, UPR markers in DEE/SNARE iPSC neurons.
- [x] (web agent, commit 2a3070c) Show the direction flag in the UI ("direction mismatch: this drug lowers SCN1A function; Dravet is SCN1A loss of function") from `data/derived/direction/` via `direction_compat()`. Apply it per variant group or subtype, not per gene-level disease node.
- [x] (vibrant-babbage, 2026-10-04) Direction coverage: relutrigine and NBI-921352 now "decrease" from PubMed (`CURATED_DIRECTION` in `direction_build.py`, PMID:35037706 and PMID:40808385); curated therapies with a direction 39 → 41. `mechanism_index.py` now follows MONDO `replaced_by` for G2P/ClinGen rows (Dravet MONDO:0011794 → MONDO:0100135).
  - [ ] Rerun `global_index.py` → `mechanism_index.py` → `direction_build.py` (full) → `direction_eval.py` on a machine with `data/raw/downloads/`, so Dravet gets its G2P mechanism record and a disease-side direction. The cloud session could not reach EBI, ClinGen or OBO hosts.
- [x] Hypotheses recomputed with the cross-family links (10 ideas, now including 4-PBA → SCN1A and rapamycin → NF1).
- [x] Experiment AI drafts for all 10 current ideas (gpt-6-astra).
- [x] (vibrant-babbage, 2026-10-04) **Independent Claude re-reading of the cited family abstracts**: 256 abstracts (DEE 47, lysosomal 98, RASopathy 84, cross-family 27), 1,499 claims, all quote-verified by code; agreement with the curators 172/179 (96.1%), 274 new supporting sources on existing edges, 56 synonyms. `READER=claude` in `pipeline/openai/*`, report `docs/agent-reports/claude-extraction.md`.
  - [x] (vibrant-babbage, 2026-10-04) Review the 169 Claude candidate edges (independent AI review, not a human): 142 accepted into `data/curated/claude_reviewed.json`, 11 rejected, 16 needs-human. `docs/review/claude-candidates-2026-10-04.md`.
  - [ ] **(you, optional)** A human expert checks the 16 needs-human candidates in that file (mostly variant-group direction: SCN2A, SCN8A, KCNQ2, CACNA1A missense; LZTR1 haploinsufficiency; PTPN11 mTOR).
  - [x] (vibrant-babbage, 2026-10-04) Review the 8 Claude disagreements: failed trials stay limiting (curators right); phenytoin/Dravet finding added as supporting (edge stays contested); PTPN11 readings are subtype-specific (filings stand). Review notes in `overrides.json`.
- [x] (vibrant-babbage, 2026-10-04) Outreach drafts for all 45 deep diseases (42 new, by Claude through the app's evidence packs and `sanitizeDoc`; `web/scripts/agent-ai.mjs`; 0 citations dropped).
- [ ] Merge the research-queue output: run `node pipeline/crowd/export.mjs`, review `data/curated/crowd.json` (crowd diseases become `disease:<GENE>` nodes), then merge.
- [ ] A timed **10× measurement**: build a VAMP2 landscape (neighbours, reusable assets, partners, next step) by plain web search vs with Tasukeru. Count steps, time and errors; put the result on `/impact`.
- [x] (vibrant-babbage, 2026-10-04) The STXBP1 enrollment total in the Research view excluded multi-disease registries: a study linked to 3+ atlas diseases or listing more than 5 conditions is shown as "not counted" (STXBP1: 101,363 → 863 across 8 studies).

## P2: contacts and community

- [x] Contact people only: `pipeline/contacts/filter_people.py` keeps contact roles (66 people at 20 orgs) and drops board members and advisors.

- [x] Named contact persons published by organisations (112, `data/derived/contacts/people.json`), Call/Email buttons in every view, "Report or remove a contact" form on /privacy, handled in /admin.
- [ ] Email: works via Infomaniak SMTP (`no-reply@mehro.ch`, sender "Tasukeru"). Watch the deliverability of the first real alerts. Optionally add SPF/DKIM/DMARC checks for mehro.ch.
- [ ] Researcher verification beyond the email domain (ORCID sign-in or an institutional confirmation link).
- [ ] Passkeys; a trial waitlist through patient groups; letting patient groups claim their entry and see member counts.
- [ ] More AI drafts: experiment drafts for the new hypotheses, outreach for more diseases (`node web/scripts/precompute-ai.mjs --ids ...`, dev server running, ChatGPT plan signed in).

## P3: coverage

- [ ] More deep families, using the template in `pipeline/families/*`. Candidates: mitochondrial disease (POLG, MT-ATP6 …), ciliopathies, CDG (glycosylation), leukodystrophies.
- [ ] Repeat-expansion disorders (HTT, FMR1, ATXN*): ClinVar lacks the expansions; add a note and sources.
- [ ] Orphanet expert centres / clinics, for "who to see" in the Simple view (Orphanet pages are JavaScript-rendered; find a data product).
- [ ] Non-English patient groups.

## Housekeeping

- [ ] **(you)** Delete the duplicate Vercel project "web" in the dashboard.
- [ ] Keep `CLAUDE.md`, this file and `docs/KNOWLEDGE.md` up to date after every merge.

## Done (most recent first)

- AI review of the 169 Claude candidate edges (142 accepted, AI-labelled, kept out of the benchmark) and the 8 reader disagreements; AI actions hidden where no precomputed draft exists; "Take a tour" buttons (vibrant-babbage).
- Independent Claude re-reading of 256 family abstracts (96.1% agreement, 274 new supporting sources); 42 Claude outreach drafts; `/method` counts both readers (vibrant-babbage).
- Web: seven-factor view. Disease fingerprint (7 rows) on atlas and /d/ pages (plain in Simple "Learn more", open in Research/Industry); 7-segment factor bars with the strongest factors in words on closest diseases (atlas) and most similar diseases (/d/); "Seven factors side by side" on /compare; atlas factor lens (Off / All / each factor, width = similarity) and a Research weights panel (tested defaults symptoms 1, genes 0.5, pathway 0.5); "The seven factors" on /method (commit 912f426).
- README and video script refreshed; Research-view enrollment excludes multi-disease registries; relutrigine and NBI-921352 directions; obsolete-MONDO join in the mechanism layer (vibrant-babbage).
- Web: direction flag ("Direction fits" / "Direction mismatch", direct target only, per variant group where a gene mixes directions) on disease therapy evidence, idea cards, /approach programmes, /variant and /sequence; AI reviews labelled "Independently reviewed by AI (not a human expert)" and counted separately on /method; direction result on /method (commit 2a3070c).
- Cross-family biology: RAS → MAPK (LZTR1, RIT1, SOS1, CBL), SYNGAP1 ↔ MAPK/mTOR, mTOR, synaptic plasticity, misfolding (SCN1A, KCNQ2), autophagy; 11/45 → 29/45 diseases cross-linked by a specific mechanism. `docs/agent-reports/cross-family.md`.
- Independent AI review (Claude, not a human expert): 63 links, 31 confirmed, 26 corrected, 6 needs-human; MONDO umbrella ids for CDKL5/SLC2A1/GBA1/NPC1/ARSA; Dravet MONDO:0011794 → MONDO:0100135 on SCN1A and SCN2A. `docs/review/ai-review-2026-10-04.md`.
- Direction layer (`data/derived/direction/`, `DirectionIndex` in `transfer_score.py`) and evaluation (`data/derived/eval_direction.json`, eval.md section 6). Not adopted in ranking.
- Friendlier emails with logo; Tasukeru rebrand; SMTP via Infomaniak.
- Live daily ClinicalTrials.gov and NIH RePORTER alerts; published org and trial contacts.
- Genome-wide ClinVar in the VCF checker; gene factors panel; similar-disease lists (phenotype + genes + pathway); PrimeKG benchmark.
- Research queue (OpenAI or Claude, BYOK or local worker); accuracy evaluation on `/method`; DNA-test request flow.
- Community accounts, onboarding, moderated announcements, k-anonymous interest counts; `/help` for no-result searches.
- Views (Simple/Detailed/Research/Industry), guided search, FASTA/VCF checker; 58 AI drafts.
- 4 deep families (45 diseases); global index of 11,456; DisMech; breadth layer for 10,309 diseases; population, readiness and channels.
