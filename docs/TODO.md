# Tasukeru: to-do list

Keep this file current: tick items when done (with the commit), and add new ones at the right priority. Items marked **(you)** need a human; everything else an agent can do. Read `CLAUDE.md` and `docs/KNOWLEDGE.md` first.

## P0: submission blockers

- [ ] **(you)** Decide how judges get the source code. The GitHub repo `K14-coder/rare-disease-atlas` is private. Either make it public, or share it the way Hack-Nation asks. Run a final secret scan before making it public (see KNOWLEDGE.md → "Secret scan").
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

- [ ] **Direction-aware therapy matching** (agent running): disease too-little vs too-much function × drug increases vs decreases. Evaluate on PrimeKG indications and contraindications plus the sodium-channel cases → `docs/agent-reports/eval.md`, `data/derived/eval_direction.json`. Adopt it in production only if it helps; then update `/method` and the hypotheses ranking.
- [ ] **Independent AI review of the review sheet** (agent running) → `docs/review/ai-review-2026-10-04.md` and patches in `data/curated/overrides.json`. Review records use `by: "ai-review:claude"`.
  - [ ] Web: render ai-review records as "Independently reviewed by AI (not a human expert)". Human reviews keep "Reviewed by a biochemist".
  - [ ] **(you, optional)** A human expert works through the "needs-human" list from that report.
- [ ] **Cross-family biology** (agent running): the RAS → MAPK link for LZTR1/RIT1/SOS1, SYNGAP1 ↔ RAS/ERK, misfolding/ER stress, lysosomal/autophagy and synaptic-release links → `data/curated/cross_family.json`. Target: well above 11 of 45 diseases with a specific cross-family link. Re-run the eval.
- [ ] Recompute hypotheses (`pipeline/derive/run.sh`) after the cross-family and direction work lands, then precompute `experiment` AI drafts for the new top ideas.
- [ ] Merge the research-queue output: run `node pipeline/crowd/export.mjs`, review `data/curated/crowd.json` (crowd diseases become `disease:<GENE>` nodes), then merge.
- [ ] A timed **10× measurement**: build a VAMP2 landscape (neighbours, reusable assets, partners, next step) by plain web search vs with Tasukeru. Count steps, time and errors; put the result on `/impact`.
- [ ] The STXBP1 enrollment total in the Research view includes multi-disease Simons Searchlight. Exclude multi-disease registries from the sum.

## P2: contacts and community

- [ ] Decide whether to show board members who list their own email (5 orgs show 12–19 people). Option: filter `people.json` to contact roles (family support, executive director, founder, president). See `pipeline/contacts/people_review.json`.

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

- Friendlier emails with logo; Tasukeru rebrand; SMTP via Infomaniak.
- Live daily ClinicalTrials.gov and NIH RePORTER alerts; published org and trial contacts.
- Genome-wide ClinVar in the VCF checker; gene factors panel; similar-disease lists (phenotype + genes + pathway); PrimeKG benchmark.
- Research queue (OpenAI or Claude, BYOK or local worker); accuracy evaluation on `/method`; DNA-test request flow.
- Community accounts, onboarding, moderated announcements, k-anonymous interest counts; `/help` for no-result searches.
- Views (Simple/Detailed/Research/Industry), guided search, FASTA/VCF checker; 58 AI drafts.
- 4 deep families (45 diseases); global index of 11,456; DisMech; breadth layer for 10,309 diseases; population, readiness and channels.
