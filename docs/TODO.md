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

- [ ] **(you, later)** Make the repo public before submission (team decision: later). The GitHub repo `K14-coder/rare-disease-atlas` is private for now. Either make it public, or share it the way Hack-Nation asks. Run a final secret scan before making it public (see KNOWLEDGE.md → "Secret scan").
- [ ] Refresh `README.md` for the current product:
  - the name Tasukeru;
  - the four views;
  - search across 11,456 diseases;
  - the FASTA/VCF checker with genome-wide ClinVar;
  - community accounts and alerts, and the research queue;
  - the benchmarks (56-case curated eval and the 1,300-case PrimeKG eval);
  - how OpenAI is used;
  - the architecture diagram;
  - the acknowledgements.
- [ ] Refresh `docs/video-script.md`: the Tasukeru name, the current numbers from `/method`, and the guided tour "Follow a patient group" as the 1-minute walkthrough.
- [ ] **(you)** Record the team video and the 1-minute walkthrough.
- [ ] Do a final consistency pass on the deployed site:
  - Simple view on a phone;
  - the guided tours still match the UI;
  - no console errors;
  - load times.

## P1: model and evidence quality

- [x] **Direction-aware therapy matching** (done 2026-10-04): neutral on PrimeKG, no contraindication shift, atlas gain = target leakage → keep it as a flag only. See eval.md section 6.
- [~] (claimed by main-session agent "ai-review", 2026-10-04) **Independent AI review of the review sheet** → `docs/review/ai-review-2026-10-04.md` and patches in `data/curated/overrides.json`. Review records use `by: "ai-review:claude"`.
  - [ ] Web: render ai-review records as "Independently reviewed by AI (not a human expert)". Human reviews keep "Reviewed by a biochemist".
  - [ ] **(you, optional)** A human expert works through the "needs-human" list from that report.
- [~] (claimed by main-session agent "cross-family", 2026-10-04) **Cross-family biology**: the RAS → MAPK link for LZTR1/RIT1/SOS1, SYNGAP1 ↔ RAS/ERK, misfolding/ER stress, lysosomal/autophagy and synaptic-release links → `data/curated/cross_family.json`. Target: well above 11 of 45 diseases with a specific cross-family link. Re-run the eval.
- [ ] Show the direction flag in the UI ("direction mismatch: this drug lowers SCN1A function; Dravet is SCN1A loss of function") from `data/derived/direction/` via `direction_compat()`. Apply it per variant group or subtype, not per gene-level disease node.
- [ ] Direction coverage: add MONDO:0100135 (Dravet) to the G2P/ClinGen join (obsolete id MONDO:0011794). Get directions for relutrigine and NBI-921352 (Nav1.6 inhibitors; ChEMBL has no mechanism record for them).
- [ ] Recompute hypotheses (`pipeline/derive/run.sh`) after the cross-family and direction work lands, then precompute `experiment` AI drafts for the new top ideas.
- [ ] Merge the research-queue output: run `node pipeline/crowd/export.mjs`, review `data/curated/crowd.json` (crowd diseases become `disease:<GENE>` nodes), then merge.
- [ ] A timed **10× measurement**: build a VAMP2 landscape (neighbours, reusable assets, partners, next step) by plain web search vs with Tasukeru. Count steps, time and errors; put the result on `/impact`.
- [ ] The STXBP1 enrollment total in the Research view includes multi-disease Simons Searchlight. Exclude multi-disease registries from the sum.

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

- Direction layer (`data/derived/direction/`, `DirectionIndex` in `transfer_score.py`) and evaluation (`data/derived/eval_direction.json`, eval.md section 6). Not adopted in ranking.
- Friendlier emails with logo; Tasukeru rebrand; SMTP via Infomaniak.
- Live daily ClinicalTrials.gov and NIH RePORTER alerts; published org and trial contacts.
- Genome-wide ClinVar in the VCF checker; gene factors panel; similar-disease lists (phenotype + genes + pathway); PrimeKG benchmark.
- Research queue (OpenAI or Claude, BYOK or local worker); accuracy evaluation on `/method`; DNA-test request flow.
- Community accounts, onboarding, moderated announcements, k-anonymous interest counts; `/help` for no-result searches.
- Views (Simple/Detailed/Research/Industry), guided search, FASTA/VCF checker; 58 AI drafts.
- 4 deep families (45 diseases); global index of 11,456; DisMech; breadth layer for 10,309 diseases; population, readiness and channels.
