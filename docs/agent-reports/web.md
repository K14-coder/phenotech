# Web front end: agent report

Next.js 16.3 (App Router, TypeScript, Turbopack), Tailwind v4, Cytoscape.js + fcose, Fuse.js. The app lives in `web/` and reads only `web/public/data/graph.json`, following `docs/SCHEMA.md`.

## How to run

```bash
cd web
npm install
npm run dev          # predev syncs data, then: next dev -H 127.0.0.1 -p 3000
npm run build        # prebuild syncs data, then: next build (passes)
npm run lint         # clean
npm run sample-data  # regenerates the sample graph (scripts/make-sample-graph.mjs)
```

- `.claude/launch.json` defines the `web` server (`npm --prefix web run dev`, port 3000).
- Dev binds to **127.0.0.1** only, as required for the later OAuth loopback flow. Open `http://127.0.0.1:3000`.
- **Vercel:** set Root Directory = `web`. No env vars needed. `/`, `/atlas` and `/path` are static; `/disease/[id]` renders on demand. `next.config.ts` pins `turbopack.root` to `web/`, so a stray lockfile elsewhere does not confuse the build.
- **Data sync:** `scripts/sync-data.mjs` runs before dev and build. It copies `../data/graph.json` to `public/data/graph.json` if it exists, and `../data/ai/*.json` to `public/data/ai/` if that folder exists. Otherwise it keeps the committed sample. Commit the real `public/data/graph.json` so Vercel builds have it even when `../data` is not available.

## Structure

```
web/
  app/                     layout (Inter, providers, header), page.tsx (Home), atlas/, disease/[id]/, path/
  components/
    GraphProvider.tsx      loads + indexes graph.json once, exposes useAtlas() / <WithGraph>
    SiteHeader.tsx         nav, compact global search, "Sample data" badge (shown when meta.sample)
    search/SearchBox.tsx   ARIA combobox: fuzzy search, explicit synonym resolution ("Munc18-1" → STXBP1), "/" shortcut
    evidence/              EvidenceProvider (app-wide drawer, focus trap, Esc), EvidencePanel, badges, meter, chips, legend
    atlas/                 AtlasView, GraphCanvas (Cytoscape, client-only), LeftRail (clusters + type filters + legend), AtlasPanels
    disease/               DiseaseView (3 questions), ProposalDraft (AI button)
    path/PathView.tsx      evidence-weighted route as a vertical list
    Term.tsx               glossary tooltips (plain-language one-liners, e.g. "haploinsufficiency")
  lib/
    types.ts               mirrors SCHEMA.md (discriminated node union, Edge, Evidence, Cluster, Gap, Meta)
    graph.ts               load, index by id, adjacency/neighbors, synonym index, clusters, gaps, Dijkstra path, URL helpers
    search.ts              Fuse.js over label + synonyms + protein + subtypes + xrefs; exact/prefix boosts
    insights.ts            disease page logic: mechanisms per disease, closest diseases, reuse labels, partners, next step, gaps
    ai.ts                  generate(kind, payload): precomputed file, else "AI not connected"
    text.ts, glossary.ts, style.ts   plain-language labels, evidence-level meta, rubric, palette
  scripts/sync-data.mjs, scripts/make-sample-graph.mjs
  public/data/graph.json   SAMPLE (32 nodes, 52 edges, 3 clusters, 4 gaps, meta.sample = true)
```

## Views

1. **Home `/`**: value proposition, one global search over diseases, genes, proteins/synonyms, symptoms (incl. HPO IDs), mechanisms and patient groups. Synonym hits show as `"Munc18-1" → STXBP1 · Matched a synonym`. Gene hits also show the linked disease. Example chips (kept only if they resolve), plus a "New diagnosis? Start with the gene name" hint.
2. **Atlas `/atlas?focus=<id>`**:
   - Left rail: cluster legend with colour toggles (click a name for the cluster view: rationale, members, evidence, open questions), and type filters. Publications, researchers and grants are off by default.
   - Centre: fcose layout. Colour = cluster (gray = none), shape = type, size ∝ degree. Lines: solid = evidence-backed, dashed = inferred, faint dotted = hypothesis, amber "!" = contested; thickness = confidence. Hover lights up the neighbourhood.
   - Right panel: summary first, then key facts, actions, connections (each with an evidence chip), and "Details and identifiers" on demand.
   - Clicking a line opens the Evidence panel. The URL tracks the selection.
3. **Evidence panel** (drawer, available on every page):
   - Plain-language sentence and relation type, explanation, evidence-level badge, contested/unverified status, and a confidence meter with rubric ticks plus a "what this score means" line.
   - Sources with source, kind, ref, year, retrieved date, verbatim quote as a blockquote, link (placeholder links are shown as such), verified tick or "Not verified", and extracted_by in words. It flags PubMed/Website evidence missing its required quote.
   - A separate **Contradicting or limiting evidence** section (counter_evidence plus any `supports:false` entries), which says "None found in sources searched" when empty.
   - Collapsible legend for levels and the rubric.
4. **Disease page `/disease/STXBP1`** (also accepts `/disease/disease:STXBP1`):
   - Header with gene, synonyms, mechanisms (with evidence), and facts (inheritance, onset, approved treatment, patient group, cluster). A one-line answer strip covers the three questions.
   - (a) Ranked closest diseases. Each shows the shared mechanism (evidence chips for both sides), shared symptoms (distinctive ones flagged), the atlas link, what differs, and "See the connecting path".
   - (b) What exists, grouped as Reusable as-is / Adaptable / Not directly applicable, each with the reason, "What differs" and a source chip.
   - (c) Suggested next step with "Before joining forces, check:", the "Based on" evidence chips and the proposal button. Then patient communities, with the honest gap when there are none, e.g. `/disease/VAMP2`: "No patient group found… Searched: …" plus the closest related communities. Then researchers who bridge diseases, and the **What we don't know yet** box from `graph.gaps`.
5. **Path `/path?from=&to=`**:
   - Pickers with search, swap, and an "Allow untested hypotheses" toggle (off by default).
   - Summary: number of steps and the weakest link. Then a vertical step list with sentence, explanation, level badge, status, meter and "See evidence".
   - When no route exists, it says so, lists what was searched, offers the hypothesis-only route if there is one, and shows related gaps.

## Heuristics (computed client-side, explained in the UI)

- **Path cost** per edge = `-ln(confidence)` + level penalty (inferred +0.4, hypothesis +1.5, experimental +0.1, case reports +0.15) + 0.6 if contested + 0.15 per hop. Passing through a common symptom costs more than a distinctive one (uses `attrs.ic`). Hypothesis edges are excluded unless toggled on.
- **Disease ↔ mechanism** links count in three ways: a direct `driven_by` edge counts fully; gene `participates_in` counts at ×0.7; variant-group `has_effect` counts at ×0.85, and ×0.6 more when contested.
- **Closest diseases** score = 0.45 × shared mechanism + 0.30 × direct `shares_mechanism`/`similar_phenotype` edge confidence + 0.25 × IC-weighted symptom overlap. A symptom is "distinctive" when its IC is at or above the median IC in the graph.
- **Reuse** labels:
  - Reusable as-is: built for this disease, or a shared platform/network (`data_platform`, `research_network`, `funding_program`) on a mechanism-sharing neighbour.
  - Adaptable: a neighbour shares a mechanism. Registries, outcome measures and similar can also qualify on distinctive shared symptoms. Interventional trials qualify only when the therapy targets a shared mechanism.
  - Not directly applicable: animal and cell models of a different gene, and weak overlaps.
- **Next step**: offer your registry or natural history study to the best mechanism-sharing neighbour, or ask the neighbour's maintainer to include you, or contact their patient group. Checks come from missing patient groups, bridging researchers, unshared symptoms, contested links and gaps.

## Stubbed / placeholder

- **AI** (`lib/ai.ts`): `generate(kind, payload)` fetches `public/data/ai/<kind>--<safe id>.json`. The safe id replaces non-`[A-Za-z0-9._-]` characters with `_`, e.g. `proposal--disease_STXBP1.json`; the raw id is also tried. The file takes `text` (or `markdown` / `content` / `output_text`), plus optional `model`, `generated_at` and `edge_ids` (rendered as evidence chips). Without a file it returns status `not_connected` and the UI says "AI not connected… Nothing here was generated." A `liveProvider()` slot is ready for the OpenAI integration. The only caller today is the proposal button, with `kind = "proposal"` and payload `{ id, disease, next_step, checks, neighbours, partners, gaps, edge_ids }`.
- **Sample data:** every evidence entry has ref `SAMPLE`, url `#`, `verified: false` and a placeholder quote. Orgs, assets, study, therapy, researchers, grant and publication are clearly labelled "(sample)". Real vocabulary is used (gene names, HPO IDs, mechanism names). The only xrefs are the two from the schema examples (HGNC:11444, OMIM 612164). There are no PMIDs or NCT IDs. Confidences follow the schema rubric. The sample is slightly larger than the ~25/35 target so every view has something to show: a contested edge with counter-evidence, a hypothesis edge with no sources, an inferred edge, a disease with no patient group, and a gene-specific model marked "not applicable".

## Known issues

- Graph keyboard access: the canvas is mouse-only. Keyboard users reach everything through search, the left rail, the right-panel connection lists and the evidence chips. Focus states are visible, and the Evidence drawer traps focus and closes on Esc.
- When no precomputed AI file exists, the browser console logs two expected 404s for the probed file names.
- The layout targets desktop (polished at 1440, checked at 1280). Below about 1100px the atlas's three columns get tight; no mobile layout yet.
- Re-layout runs on every filter change (animated, incremental). On a large graph (thousands of nodes) consider capping visible nodes or switching `quality` to `"default"` in `GraphCanvas.tsx` (`LAYOUT_BASE`).
- Reuse and next-step logic are heuristics. They are explained in the UI but are not curated judgements.
- The Next.js dev indicator ("N" bubble, bottom-left) only appears in dev.

## What a real `graph.json` needs for each view to look good

- **Everywhere:**
  - `meta.sample` false or absent (hides the badge), `meta.slice`, `meta.version`, `meta.generated_at`.
  - `meta.sources[]`, which the "no route" message uses as "searched".
  - Edge ids exactly `${source}|${type}|${target}`, since clusters and AI files reference them.
- **Search:** `synonyms` on genes (protein names such as "Munc18-1"), diseases (OMIM/MONDO names, eponyms such as "Baker-Gordon syndrome"), mechanisms and phenotypes. Also `attrs.protein` on genes, `attrs.subtypes[].name` on diseases, and `xrefs`.
- **Atlas:**
  - `clusters[]` with `members` (diseases, genes and mechanisms, so colours spread) and a family-readable `rationale`. Clusters also need `edge_ids` that support the grouping.
  - `basis` set correctly.
  - Keep to about 6 clusters or fewer; colours repeat after 6.
  - Node `summary` in plain language, one or two sentences.
- **Evidence panel:**
  - `explanation` written for a parent.
  - Honest `evidence_level`, `status` and `confidence` following the rubric.
  - Evidence with real `url`, `ref`, `year`, `title`, verbatim `quote` (required for PubMed/Website), `verified` and `extracted_by`.
  - `counter_evidence` whenever anything contradicts or limits a link.
- **Disease page:**
  - (a) `driven_by` edges, plus `causes`, `participates_in`, `variant_in` and `has_effect` chains; `has_phenotype` edges; phenotype `attrs.ic` (needed for "distinctive"); and computed `shares_mechanism` / `similar_phenotype` edges.
  - (b) `asset` nodes with `attrs.kind` and `covers` edges, `study` nodes with `studies` (and `tests` → therapy → `targets` for trial reuse), and `maintains` edges from orgs or researchers.
  - (c) `patient_org` + `serves` edges, and `researcher` + `works_on` edges to genes, diseases or mechanisms (to detect bridges). Also `gaps[]` with `about` set to the disease, gene, variant group, mechanism or cluster id, and a filled-in `searched` (shown verbatim in the honest-gap box).
  - Disease `attrs.inheritance`, `onset` and `approved_treatment`.
- **Path:** connected chains with realistic confidences. Hypothesis edges with `evidence: []` are fine; they are hidden unless the user opts in.

---

## AI wiring (OpenAI, Sign in with ChatGPT)

This supersedes the "AI" stub described above. `integrations/openai/` was **not modified**.

### What works
- **Routes** (`web/app/api/ai/*`, Node runtime, `force-dynamic`, never return tokens):
  - `GET /api/ai/status` returns `{mode, liveDisabled, authPath: chatgpt|api_key|none, signedIn, email, planUsage, planUsageFirstEnabledAt, apiKeyConfigured, model, manageUsageUrl, billingUrl, login:{status, authorizeUrl?, error?}}`.
  - `POST /api/ai/login {reconsent?}` calls `siwc.beginLogin()`, opens the system browser on this machine and returns `{authorizeUrl}` at once. The UI polls status every 2 s for up to 10 min.
  - `POST /api/ai/logout` revokes and clears the session.
  - `POST /api/ai/generate {kind, payload}`.
- **Security** (`web/lib/server/openai-local.ts`, `guardLocal`):
  - Host must be loopback (`127.0.0.1`, `localhost` or `[::1]`) on `PORT` (default 3000), which blocks LAN access and DNS rebinding.
  - Origin must be same-origin. It is required on every POST, and a cross-origin value is rejected on GET.
  - `Sec-Fetch-Site` must be same-origin when present.
  - POSTs must be `application/json` (415 otherwise).
  - When `VERCEL` is set (or `AI_MODE=precomputed`), login, logout and generate return 404, status returns `{mode:"precomputed"}`, and the integration is never loaded.
- **Runtime import:** `import(/* webpackIgnore: true */ /* turbopackIgnore: true */ pathToFileURL(<repo>/integrations/openai/llm.mjs))` works in `next dev` (Turbopack) and in the production build (`next start`). No `serverExternalPackages` or other workaround was needed. `.secrets/` and the repo-root `.env.local` resolve correctly; `SIWC_PROJECT_ROOT` overrides the root.
- **Payload integrity:** `payload` is a *target*, not evidence: `{id}` for `proposal`, `{from, to, includeHypotheses?}` for `explain-path`. The server rebuilds the context from `public/data/graph.json` with the same `lib/insights.ts` and `lib/graph.ts` code the UI uses (`web/lib/ai-tasks.ts`), so the browser cannot inject evidence.
  - Each connection gets a short ref (`E1…`) plus its statement, explanation, evidence level, confidence, status, top 2 quotes, and its count and first quote of limiting evidence.
- **Structured output:** `{title, sections:[{heading, sentences:[{text, edge_ids[]}]}]}` as a strict JSON Schema.
  - Server-side validation (`sanitizeDoc`) maps refs back to edge ids and drops any id not in the payload.
  - A sentence left with no ids is kept and rendered **muted and labelled "AI framing, no direct source"**.
  - Citations render as numbered superscript chips that open the existing Evidence panel.
  - Every output shows model, generation time and source (live via ChatGPT plan / API / precomputed) and is labelled "AI-generated from the cited sources".
- **Kinds:**
  - **explain-path:** "Explain this in plain language" on `/path`. Written for a parent, under 150 words, and must say what is uncertain.
  - **proposal:** "Draft a collaboration proposal" on `/disease/[id]`. A one-page proposal from the patient-group leader to the partner organisation, with sections: Why our communities are connected / What already exists that we could share / What must be checked before we join forces / Proposed first step this month / What we don't know yet / Short outreach email.
- **UI states** (`components/ai/*`):
  - **Signed out:** black "Continue with ChatGPT" button plus "Precomputed results only until you connect" (or "Using an OpenAI API key until you connect"). While pending, "If nothing opened, open the sign-in page".
  - **Signed in:** "Using ChatGPT plan · Manage usage" (https://chatgpt.com/settings/usage), the account and Sign out, beside each AI action.
  - **One-time notice:** "You're using your ChatGPT plan" with **Got it**, keyed on `planUsageFirstEnabledAt` in localStorage.
  - **Errors:** `usage_limit`/`rate_limited` make **Manage usage** the primary action. `credits_exhausted` (API key with no credits, `credit_balance_exhausted` or `insufficient_quota`) shows "API credits used up" with **Manage billing** (https://platform.openai.com/settings/organization/billing/) as the primary action. `not_eligible`/`policy_or_region` show an explanation plus the API-key or precomputed options. `plan_usage_not_granted` offers "Enable ChatGPT plan usage" (re-consent). `no_llm_available`/`login_required` offer "Continue with ChatGPT". Other errors offer "Try again". Every error panel also offers "Show precomputed version if available".
- **Precomputed mode** (`lib/ai.ts`): reads `public/data/ai/<kind>--<safe id>.json` in the same shape plus `model` and `generated_at`.
  - Ids: `proposal--disease_STXBP1.json` and `explain-path--disease_SLC6A1__to__disease_STXBP1.json` (`pathAiId`, with a `__hyp` suffix when hypotheses are allowed).
  - A precomputed result is shown first (instant, uses no plan) with "Generate a fresh version" when live AI is available. Otherwise the click generates live, or says "AI not connected".
- **`web/scripts/precompute-ai.mjs`:**
  - Drives the local `/api/ai/generate` (same prompts, validation and signed-in session) and writes `../data/ai/*.json`, which `sync-data` copies into `public/data/ai/`.
  - Targets: a proposal for every disease, plus explain-path pairs from `scripts/ai-targets.json`.
  - Flags: `--dry-run`, `--only`, `--limit`, `--pairs`, `--out`, `--force`, `--base`.
  - Runs sequentially, stops on usage or credit limits, and backs off once on temporary errors.
  - **Not run in bulk.**

### Tested live (3 ChatGPT-plan calls in total, all `gpt-6-astra`, `structured_mode: json_schema`, 0 dropped citations)
1. curl `explain-path` SLC6A1 → STXBP1: 200 in about 16 s. This output showed the model writing "E1" in prose, so the prompts now forbid refs in text.
2. UI `proposal` for STXBP1 on `/disease/STXBP1`: about 40 s, 19 citation chips, framing labels; a chip opened the Evidence panel with the real GO record.
3. `precompute-ai.mjs --only explain-path --limit 1 --out <scratch>` for VAMP2 → STXBP1: wrote the file and showed no ref leakage.

No live output was left in `public/data/ai/` or `data/ai/`.

### Also tested (no plan usage)
- Guard: foreign Host, wrong port, cross Origin, `Sec-Fetch-Site: cross-site`, POST without Origin, and a form-encoded POST are all rejected (403/415). `localhost:3000` is accepted.
- **Production bundle:** `next start` loads the integration.
- **API-key path:** `OPENAI_AUTH=api_key` gives `credits_exhausted` with the billing link, and the UI shows the billing panel.
  - My curl test used `--retry` and re-sent that POST 15 times against the no-credit key (no charge, no Plus usage). The route now answers 402 for this case so generic clients don't retry it.
- **`VERCEL=1`:** status returns precomputed, generate/login/logout return 404, and the UI shows "Precomputed results only" with no ChatGPT button.
- **Precomputed rendering:** shown with a "Generate a fresh version" button.
- **One-time plan notice:** appears once and stays dismissed after Got it.
- **Not tested live:** the login flow itself (never triggered by me; the user signed in via the CLI), logout, and the usage-limit, not-eligible and plan-not-granted panels (code paths only).

### Real data is now in
`data/graph.json` (400 nodes, 612 edges, 5 clusters, 34 gaps, not sample) is synced into `public/data/graph.json` by `prebuild`/`predev`, so the Sample badge is gone. Fixes for it:
- Umbrella patient groups that serve several diseases are listed once (`relatedOrgsFor`); this fixed a duplicate-key error.
- The long patient-group and cluster lists in the disease header are truncated ("and N more").

### Known issues / follow-ups
- **Logo:** the official ChatGPT mark is not bundled. The button is the black "Continue with ChatGPT" format with a logo slot in `components/ai/AiConnect.tsx`; add OpenAI's approved asset per their brand guidelines.
- **Unmapped error code:** `credit_balance_exhausted` is not in llm.mjs `KNOWN_CODES`, so the route maps it. Adding it to llm.mjs (owner's call) would make `describeError` correct everywhere.
- **Default model swap:** the account's model list did not include the default `gpt-6.1-sol` on the ChatGPT path, so llm.mjs used the first listed model (`gpt-6-astra`). Set `OPENAI_MODEL` to pin one.
- **Latency:** proposals take 30–45 s and explanations about 15 s; the UI shows a "Writing…" state. No streaming to the browser yet.
- **Single-process state:** login state is kept in memory (`globalThis`), so restarting the dev server mid-login loses the "pending" state. The user can just click again.
- **Dense atlas:** with real data the default atlas view is dense (117 symptom nodes). Consider hiding non-distinctive symptoms by default.

---

## Demo polish (real data: 400 nodes, 612 edges, 5 clusters)

### Atlas density (`components/atlas/AtlasView.tsx`, `GraphCanvas.tsx`, `LeftRail.tsx`)
- **Default view:** diseases, genes, mechanisms, patient groups, resources, studies and therapies, plus only the **distinctive shared symptoms** (`attrs.ic ≥ 3.5` and annotated to 2 or more diseases in the graph; 22 of 117). That is 124 of 400 nodes.
  - A "Show all symptoms" toggle adds the rest.
  - Variant groups appear automatically when their gene is selected or focused (the 5 STXBP1 groups ring the gene).
  - Researchers, grants and publications stay off.
- **Focus mode** (`/atlas?focus=<id>`): shows the 2-hop neighbourhood through visible types, e.g. "Showing what is within two steps of VAMP2-related disorders · 76 of 400 · Show whole atlas".
  - It fits the view on load. "Focus the map here" in the node panel re-focuses; `view=all` in the URL keeps the whole atlas.
- **Stable layout:** fcose runs once, over the whole-atlas default view. Filters only hide and show nodes.
  - Nodes that appear for the first time are placed beside their visible neighbours.
  - Large reveals run an incremental fcose with every existing node pinned (`fixedNodeConstraint`). Measured: showing all symptoms (124 → 219 nodes) moved **0** existing nodes.
  - A ↻ button re-arranges on demand.
- **Multi-cluster nodes** are drawn as Cytoscape pie slices, one per visible cluster (8 nodes; e.g. STXBP1 has 4). Genes, mechanisms and therapies follow the same rule.
  - Cluster toggles filter by membership: a node hides only when all of its clusters are off, and its slices update.

### Evidence panel: new schema fields
- `evidence.cross_checked` with `agrees: true` shows a green "Cross-checked by GPT-6-Astra · date" tick. The model name comes from `by`.
- With `agrees: false` it shows an amber "AI re-reading disagrees, needs expert review" marker.
- `evidence.needs_review` entries are listed under "Contradicting or limiting evidence" as "Flagged by AI re-reading, not yet reviewed". They do not count as supporting.
- `edge.review` shows "Reviewed by a biochemist · date · Confirmed/Corrected/Rejected" with the note (amber if rejected).
- **Dev-only fixture:** `npm run dev`, then `node scripts/make-review-fixture.mjs`, then open `/disease/VAMP2?graph=review-demo` or `/disease/CPLX1?graph=review-demo`.
  - The fixture is written to the gitignored `public/data/fixtures/` and marked sample.
  - The `?graph=` switch is ignored in production builds. `public/data/graph.json` is untouched.

### AI wait state
`/api/ai/generate` streams NDJSON (`Accept: application/x-ndjson`) with real phases:
1. "Collecting N cited connections from the atlas" (the payload's ref count).
2. "Drafting with GPT-6-Astra · K sentences so far" (the model is predicted with llm.mjs's own choice rule via `listModels()`; the sentence count comes from the streamed JSON).
3. "Checking every citation against the atlas".

An elapsed timer reads "usually 15 to 45 seconds". The plain JSON mode is unchanged for `precompute-ai.mjs`.

### Trust page `/method` ("How we know" in the header)
- **Live counts from graph.json:**
  - links with a source: 612/612
  - quotes string-verified: x/y
  - connections cross-checked by OpenAI, with disagreements flagged
  - connections reviewed by a biochemist, with how many were corrected
  - contested: 31
  - open questions: 34
- "How the atlas is built": sources (from `meta.sources`), curation, verified verbatim quotes, the independent OpenAI re-reading, and human review.
- "What the atlas will not do": no medical advice; AI never invents a link; inferred links and hypotheses are drawn dashed or dotted; unknowns stay visible.
- The evidence-label legend.
- Cross-check and review counts are 0 until tonight's data lands; the fixture shows them non-zero.

### Demo journey fixes
- **Search:** "VAMP2" now ranks *VAMP2-related disorders* first (a whole-word prefix of a disease name counts as exact).
- **Patient groups:** a group counts as "yours" only if a source (not an inference) says it serves the disease and it is not an umbrella or multi-gene group. Umbrella groups and registries that already accept the disease are listed as the **closest community**.
- **Section 2 groups:** "**Already covers VAMP2**" (green; with "Also includes STXBP1…" and the study sponsor, e.g. Boston Children's Hospital), "**Could be adapted**" (blue; closest neighbour first, ordered natural history → outcome measures → registries → models), and "Not directly applicable".
  - Gene-specific models of a mechanism-sharing neighbour are now "Could be adapted" (methods, not the animal).
  - Long groups collapse to "Show N more", and the redundant "Built for…" and "Type:…" lines are gone.
- **Treatments** appear as "Treatment evidence to discuss with your neurologist", which says it is not medical advice. The proposal prompt also forbids treatment advice.
- **Next step:** prefers a neighbour's natural history study run by a patient group. For VAMP2: "Ask STXBP1 Foundation whether STARR (STXBP1 Clinical Trial Ready) natural history study could include VAMP2-related disorders". The proposal is now addressed to the organisation that step names.
- **Legibility:** the header shows short cluster names, a compact "Searched …" line with the full list on demand, larger evidence chips (28 px) and larger citation marks.

### Live AI usage in this pass
One ChatGPT-plan call (4 in total today): the VAMP2 proposal through the new streaming path. It returned 6 sections, 30 citations, 4 framing labels and 0 citations dropped. The partner-alignment change was made after that call and is only typechecked.

### Still rough
- The whole-atlas view is still busy at 124 nodes. Focus mode is the demo view.
- Pie slices on rounded-rectangle genes show the first cluster colour in the corners.
- Focus-mode dimming keeps 2-hop nodes faint while the focus node is selected (deliberate, but it can read as "missing").
- The ChatGPT logo is still not bundled.
- Graph JSON is about 1.2 MB, fetched client-side on first load.

---

## Compare page, personas and guided tour

### A. `/compare?a=VAMP2&b=STXBP1`: "Before we join forces"
The logic lives in `lib/compare.ts` (pure, shared by the page and the AI task). The UI is `components/compare/CompareView.tsx`. Gene symbols or full disease ids both work in the URL.
1. **What we share:**
   - mechanisms, with an evidence chip per side and "minority view" tags (`attrs.minority_mechanism`);
   - distinctive shared symptoms, highest IC first, with broad ones collapsed and labelled "broad";
   - shared clusters.
2. **What differs:**
   - mechanisms on one side only, with minority and contested tags;
   - distinctive symptoms on one side only;
   - inheritance and onset;
   - **variant spectrum** from `clinvar_counts`: truncating, missense and splice shares among small changes (large deletions listed separately), e.g. "VAMP2: mostly missense (62%)" vs "STXBP1: a mix, most often truncating (42%)", plus a one-line "why it matters".
3. **Assets:** covers both / covers A only ("Could it work for B?") / covers B only, using the existing reuse logic and labels.
4. **Studies enrolling both**, with eligibility notes.
5. **People and groups linked to both:** patient groups (`serves`), researchers (`works_on`) and grants (`about`), with chips for both sides.
6. **Questions an expert should answer before joining forces:** deterministic templates triggered by the differences found.
   - Topics: disputed or thin shared mechanisms, one-sided mechanisms, variant spectrum, one-sided distinctive symptoms, inheritance and onset, shared-study eligibility, and adaptable assets.
   - At most 4 Biology questions and 10 in total.
   - Plus the AI button "Sharpen these questions with AI" (kind `compare-questions`). It uses the same structured, cited format and server validation; the context is rebuilt from graph.json.

**Entry points:**
- "Compare side by side →" on every related disease in Question 1.
- "Compare X and Y side by side before you write →" on the next-step card.
- The two pickers (with swap) on the page.

**Precomputed ids:** `compare-questions--<a>__vs__<b>` in page order, after the usual encoding, e.g. `compare-questions--disease_VAMP2__vs__disease_STXBP1.json`. `scripts/ai-targets.json` now lists VAMP2↔STXBP1, SLC6A1↔STXBP1 and SYT2↔SNAP25. `precompute-ai.mjs` reads `{"kind":"compare-questions","a","b"}` entries and supports `--only compare-questions`.

### B1. "Viewing as" (header; localStorage, overridable with `?as=family|leader|researcher|biotech`)
- **Family:** "Find your community" comes first, researcher lists are hidden, the wording is plainer, and the gaps box becomes "What nobody knows yet, and how you could help".
- **Leader:** unchanged default.
- **Researcher:** "Mechanisms first" with mechanism tabs and "Who else works on this mechanism, across gene names".
  - Researchers are grouped by gene, and people linked to 2 or more diseases are highlighted.
  - Links go only to papers (via the evidence panel) and `attrs.url`.
- **Biotech:** "Mechanism and unmet need" covers approved treatment, interventional trials, community (dedicated and umbrella groups, ClinVar variant count) and infrastructure counts.
  - Hook: `approachHref(mechanismId)` in `lib/graph.ts` returns null today; return a path and the "Therapy approaches →" links appear.

Every persona now also gets a data-grounded "How to help build the missing community" box when no dedicated group exists (registries, umbrella group, clinic, community gap).

### B2. Guided tour (`lib/tours.ts`, `components/tour/TourProvider.tsx`)
Two home buttons start the tours. Each step shows a spotlight, a caption card, Back/Next/Exit (and Esc, ←, →) and "n of N".
- The overlay navigates between pages, waits for each `[data-tour=…]` anchor and scrolls it into view.
- Tour position persists in sessionStorage.
- **No live AI:** the proposal step clicks the button only when `proposal--disease_VAMP2.json` is precomputed.
- The evidence step opens a VAMP2–STXBP1 link that carries limiting evidence.

Both tours were walked step by step: all targets found and highlighted, and the drawer closes at the end.

### C. Fixes
- Multi-cluster nodes with non-round shapes now have a white body and a cluster-coloured outline, so there are no pie corners.
- In focus mode the focused node no longer dims its own 2-hop ring.

### Live AI this round
1 call (`compare-questions`, VAMP2 vs STXBP1) produced 4 sections, 10 questions, every one cited, 0 citations dropped and no ref leakage. The output is not saved into the app.

---

## Derived data products in the UI (variant lookup, approaches, ideas, counterexamples, look-alikes)

Zero live AI calls in this round.

### 0. Data plumbing
`scripts/sync-data.mjs` now also copies `../data/derived/*.json` to `public/data/derived/` and `../data/curated/{modality,impact}.json` to `public/data/curated/`, skipping any invalid JSON. `lib/derived.ts` lazy-loads them only on the pages that use them (`useDerived(name)`, cached):
- `variants.json`: `/variant` only.
- `modality.json`: `/variant` and `/approach`.
- `opportunities.json`: `/ideas`.
- `counterexamples.json` and `beyond_slice.json`: disease pages and `/method`.

### 1. "Paste your genetic report" (`lib/variant.ts`, `/variant?q=`)
- **Parser:** a line-by-line port of `pipeline/derive/hgvs.py`, with the same regexes, canonical forms, index order (c → p → isoform), warnings and fallback classification. It is self-contained, so `npm run test:variants` runs it directly with Node's TS stripping. **20/20 cases pass.**
- **Global search:** `looksLikeVariant()` adds a top "Look up this variant" option for inputs like "STXBP1 R388X", "c.1162C>T" or "NM_003165.6(STXBP1):c.1162C>T (p.Arg388Ter)". No false positives on gene, symptom or mechanism queries.
- **Page:**
  - **Always shows** the not-a-diagnosis notice.
  - **Variant:** gene → disease link; for a ClinVar hit, the classification, consequence in plain words, stars, submissions and the ClinVar link; for a miss, the inferred type with its certainty and "read from the notation only", plus the scope note. Warnings (transcript, isoform, c./p. disagreement) appear too.
  - **Mechanism:** the variant group's `has_effect` mechanisms, with evidence chips and contested or minority-view tags.
  - **Therapy approaches** for this disease from `modality.json`: fit labels with the reasons most relevant to the variant class first, then `status` and `not_advice`.
  - **"Same gene, different mechanism":** the gene's other variant groups that act differently.
  - **Entry points:** a home-page hint ("paste a line from a genetic report") and a Family-persona pointer.

### 2. `/approach` (therapy-approach view)
- **Choosing:** pick one of the 6 modalities, or a mechanism. A mechanism filters to diseases linked to it and preselects the matching modalities.
- **Ranking:** diseases are ranked good > conditional > poor, then by the number of "good" votes. Each row shows its reasons with rule ids (the rule condition on hover) and `rules_fired`.
- **Details on expand:**
  - mechanistic evidence chips (`graph_edge_ids.mechanism`)
  - unmet need (approved treatment, interventional trials)
  - patient communities and existing infrastructure
  - existing programmes, including stopped ones and why they stopped
  - named contacts (researchers via `works_on`, with paper chips and publications links only)
  - caveats, open questions for an expert, and the cited sources (verbatim quotes)
- **Notice:** the page carries `status` and `not_advice` at the top.
- **Biotech hook:** `approachHref(mechanismId)` now returns `/approach?mechanism=…`, so the Biotech persona's "Therapy approaches →" links are live.

### 3. Ideas worth testing
- **Disease pages** get the section "Ideas worth testing (hypotheses, not evidence)". The cards are shared with `/ideas` (`components/ideas/IdeaCard.tsx`) and each shows:
  - the chain as numbered steps with evidence chips;
  - the **weakest link highlighted**: lowest confidence, contested breaks ties, plus the curated `weakest_link` text;
  - the caveats with their sources;
  - the test plan (what to test, existing assets linked into the atlas or PMIDs linked to PubMed, what would change the plan);
  - **"Draft the experiment"** (kind `experiment`, the same structured, cited and validated format).
- **`/ideas`:** all 5 hypotheses, plus "Models and assays that could be reused" (opportunities.json, strongest pairs) and "Rejected on review". It is linked from the method page and each disease section.
- **Atlas:** candidate_for edges render dashed with a "Hypothesis" label.
- **Precomputed ids:** `experiment--<edge id with every non [A-Za-z0-9._-] character replaced by _>.json`, e.g. `experiment--therapy_4-phenylbutyrate_candidate_for_disease_VAMP2.json`. The top two by confidence (4-PBA→VAMP2, cholinesterase inhibitors→SNAP25) are in `scripts/ai-targets.json`, and `precompute-ai.mjs --only experiment` supports them.
- **Not exercised live:** no AI call was made; the route rejects unknown or non-candidate ids with 404 before any model call.

### 4. Where the pattern breaks
- **`/method#breaks`:** all 10 counterexamples (title, plain language, why it matters, evidence chips).
- **Disease pages:** the items whose `edge_ids` touch the disease, its gene(s) or its variant groups.

### 5. Look-alikes beyond our map
On disease pages: the top 5 phenotype neighbours outside the slice, labelled "phenotype only, mechanism not assessed", with gene(s), percentile, shared distinctive symptoms with their IC, and one line on how the atlas would grow to include them. For STX1A, which has no annotated entity, the data's own note is shown instead.

### Not done / rough
- `impact.json` is synced but not displayed (not in this task's list).
- The "Draft the experiment" output was not rendered with real content: no precomputed experiment file exists, and no fake fixture was created.

---

## Console bugs fixed, and the 10× page

### Bugs (root causes and fixes)
1. **GraphCanvas errors.** There were two causes.
   - **`reading 'get'`:** the canvas assumed every prop was present. During hot reload a stale parent rendered the new canvas without `clusterColors`.
     - Fix: props now have safe defaults (empty Set and Map, guarded `?.get`).
   - **`reading 'source'` in `findEdgeControlPoints`:** this was a real bug. `fitAround()` (selecting a node from the side panel, or re-focusing) fitted to `closedNeighborhood()`. That includes edges to hidden neighbours, and an edge whose endpoint is `display:none` has no geometry.
     - Fix: every fit and zoom now targets visible nodes only, wrapped in a guard.
   - **Element building:** `buildElements` now adds each id once and never adds an edge unless both endpoints exist.
   - **Data changes under a mounted canvas:** the canvas is rebuilt from scratch on a new graph index.
   - **Checked:** a fresh `/atlas?focus=disease:STXBP1` with "Show all symptoms" on and off, all 5 clusters off and on, "Show whole atlas", a click on a panel connection and "Focus the map here" gave a clean console.
2. **Duplicate React keys.**
   - The edge key came from the UNC13A hypothesis's chain, which lists `therapy:3-4-diaminopyridine|targets|mech:ca-triggered-exocytosis` twice (convergent paths after the merge). Chain steps are now deduped.
   - The org keys came from organisations reachable through several diseases.
   - **General fixes:**
     - `buildIndex` keeps one node and one edge per id, with a warning, and dedupes cluster members and edge ids.
     - `uniqBy` is applied to communities, registries, therapies, researcher links and related organisations.
3. **"MARKER-after-dedupe-fix"** was never in the source. It was a `console.error` I injected through the browser tool during an earlier test, to tell old log entries from new ones. A grep finds no debug logs. The only console call is the intentional data-warning `console.warn` in GraphProvider.
4. **404 noise.** `sync-data.mjs` now always writes `public/data/ai/index.json` (`{generated, files[]}`). `lib/ai.ts` and the tour read it and only fetch listed files. Missing outputs are never requested.

**Clean-console check** (fresh loads, dev build): `/`, `/atlas`, `/disease/VAMP2`, `/disease/SYT2`, `/compare?a=VAMP2&b=STXBP1`, `/variant?q=STXBP1%20R388X`, `/approach`, `/ideas`, `/method`, `/path?from=disease:SLC6A1&to=disease:STXBP1` and `/impact`. The only messages were React's DevTools notice and `[HMR] connected`: no errors, warnings or 404s.

### `/impact`: "Why this could be 10× faster"
It reads `public/data/curated/impact.json` as it is, and is linked in the header ("Why 10×") and from `/method`.
1. **Milestone:** one sentence with an accent rule, plus the draft status line.
2. **"What sharing a mechanism has already done once":** horizontal bars on a shared axis of years since the gene was found.
   - STXBP1 12.7 y, neutral.
   - SLC6A1 5.8 y, accent, annotated "joined the STXBP1 trial".
   - VAMP2 7.5 y and counting: a dashed open-ended bar with an arrow and "No trial yet".
   - Each start and end date links to its PMID or NCT record.
   - The caveat is shown in a visible box.
3. **"Today's route vs the atlas route":** a two-column grid with steps aligned row by row; times are right-aligned (atlas times in the accent colour). `BASELINE_FROM_EXPERT` shows "awaiting expert figure" in muted text, and each step's basis and source link are shown. "Sources checked" sits underneath.
4. **"What this assumes"** and **"What we must validate next"**, side by side.
5. **Footer:** "follow Maria's VAMP2 journey →" starts the guided tour, with a link to "how we know".

Plain divs, no chart library and no gradients. Checked at 1280px: no horizontal scroll, and bars at 717, 327 and 423 px.

---

## "Contribute what you know"

The backend is `pipeline/contribute/` (see `docs/agent-reports/contribute.md`). This round made zero live AI calls and zero Bright Data requests.

### Routes (local only)
- **`POST /api/contribute/preview`** takes `{url, diseaseId?, contributor?, items?}` and calls `preview()`. `items` is the hand-entered mode: no AI, verified exactly like model output.
- **`POST /api/contribute/commit`** takes `{preview, contributor?, include?}` and calls `commit()`. It writes `data/curated/contributions.json`, rebuilds `data/graph.json` and re-syncs `web/public/data`.
- **Loading:** `lib/server/contribute-local.ts` loads `pipeline/contribute/contribute.mjs` at runtime outside the bundler, the same way as `llm.mjs`.
- **Guards:** the same as the AI routes (loopback Host, same-origin Origin, JSON only), plus a body-size cap. Both routes return 404 when `VERCEL` is set. Errors go through `toHttpError()`.
- **Test-only overrides:** `CONTRIBUTE_RAW_DIR`, `CONTRIBUTE_FRAGMENT_PATH`, `CONTRIBUTE_GRAPH_PATH` and `CONTRIBUTE_REBUILD=0` are read from the server environment only, never from the request. They let the full flow run against scratch copies.

### `/contribute`
- **Form:** URL, an optional disease (pre-filled from `?disease=`; `?gap=` shows the question being answered), an optional contributor name, and "Enter the items by hand (no AI)". That last one is an item editor for kind, name, type or NCT, the verbatim quote, mentions and what it offers. It opens automatically on AI errors.
- **Review screen:**
  - **Header:** the page title and link, how it was read (directly or through Bright Data, cached), and who proposed the items (the model or "entered by hand"), plus a summary line.
  - **Per item:** a status chip (New / Already in the atlas / Rejected / Needs a disease / Excluded) with its reason, and the verbatim quote with "✓ Verified on the page, word for word" or "✗ Not found on the page".
  - **Links:** "Links to" diseases with their basis, and "Not in the atlas yet" mentions.
  - **Duplicates:** shown as "Adds a source to an existing entry: …", plus "already cites this page" when it does.
  - **Proposed links:** each with its confidence and whether it is new or adds evidence.
  - **Include:** a checkbox, off and disabled for rejected or unlinked items. Unlinked items say to pick a disease and read the page again.
- **"Add to the atlas":** commits the ticked items. When the rebuild ran, the graph is re-fetched with `no-store` and re-indexed in place (`useGraphReload()` in GraphProvider), with no page refresh. The written nodes are then linked.
- **Errors:**
  - `llm_unavailable`: "Continue with ChatGPT", or enter the items by hand.
  - `llm_usage_limit`: "Manage usage" as the primary action, or enter the items by hand.
  - `preview_expired`, `stale_preview`, `fetch_failed` and `llm_failed`: "Read the page again".
  - Everything else: the backend's message.
- **Entry points:**
  - "Know something we missed? Add it →" in "What already exists".
  - "Help fill this gap →" on every gap.
  - "Know a group, registry or study we missed? Add it to the atlas →" in the help-build-the-community box.
- **Deployed site:** two sentences on running it locally (with the commands) and a five-step description of the flow. No form, no buttons.

### Contributed data in the UI
- **Badge:** "Community-contributed · not yet reviewed" appears for nodes with `attrs.contributed` or `attrs.contributed_sources`. It shows in the atlas node panel and on disease-page resource and organisation cards; the tooltip says who added it and when.
- **Evidence panel:** a contributed edge gets a banner. Sources whose URL came from a contribution (`GraphIndex.contributedUrls`) carry the badge.
- **Atlas:** contributed edges are lighter (pale, dotted, 55% opacity).

### How it was tested without AI
- **Scratch server:** a separate production server on port 3013 with scratch overrides. The cached BAGOS page was copied to a scratch raw directory, the fragment pointed at a scratch file and rebuild was off, so `data/` stayed untouched.
- **Guards:** cross-origin 403, form post 415, localhost URL `blocked_host` 400, unknown disease 400 with `known_diseases`.
- **Preview with hand-entered items:**
  - It read the cached page directly, with no Bright Data request.
  - The new biobank came back New and verified, with a `covers` and a `maintains` link.
  - The natural history study came back as a duplicate of `asset:bagos-natural-history-study`, adding evidence to two links.
  - The invented registry sentence was rejected as `not_on_page`.
- **Commit:** `changed: true`, writing 2 nodes and 4 edges to the scratch fragment. A second identical commit returned `changed: false`.
- **UI:**
  - The same flow through the page worked: disease pre-filled, review chips and ticks, the rejected item disabled, and "Add to the atlas" showing the done panel.
  - The AI error states were checked with an in-page fetch stub: both actions rendered.
  - Badges and lighter edges were checked with the dev fixture (`node scripts/make-review-fixture.mjs`, then `?graph=review-demo`), which now includes a contributed asset, edge and source.
  - The deployed mode was checked with `VERCEL=1`: routes 404, and the explainer has no buttons.
- **Data:** `data/curated/contributions.json` is still the backend's empty fragment, and there are no new files in `data/raw/contributions/`.

### Before the demo
- **One real AI preview:** once the Plus limit resets, run one AI preview of a cached page, e.g. https://www.bagosfoundation.org/natural-history-study with SYT1. It costs one model call; the page is cached and the extraction is cached afterwards.
- **One real commit:** commit it if wanted. That writes `data/curated/contributions.json` and rebuilds `data/graph.json`, so the in-place graph reload gets exercised for real.
- **Fallback:** the hand-entered path works today with no AI.

---

## Atlas closer to the brief's concept mockup

No live AI calls were made in this round.

### Node size = centrality
- **Mapping:** `attrs.centrality` is the build's 0–100 betweenness percentile and is present on all 397 nodes. Diameter = 10 + 46·(c/100)² px, so sizes run from 10 to 56 px.
- **Why squared:** the hubs stand out from the long tail of leaf symptoms and researchers.
- **Fallback:** a graph without centrality falls back to sizing by link count.
- **Legend:** "Size = how central it is in the atlas".
- **Data note:** the 11 diseases are all at 97–100 and the genes at 92–97. So size separates kinds of node (diseases, genes and the main mechanisms are largest; groups, resources and symptoms are smaller), not one disease from another.

### Cross-cluster bridges (`lib/bridges.ts`)
**Definition.** A link is a bridge in three cases:
- **family:** a `shares_mechanism` or `similar_phenotype` link between two diseases that share no pathway-basis cluster, where at least one of them is in one.
- **therapy-cluster:** a `developed_for` or `candidate_for` link where the therapy belongs to clusters, none of which include the disease.
- **therapy-span:** a `developed_for` or `candidate_for` link where the same therapy is also linked to a disease across a pathway boundary.

**There are 8 bridges in the current data:**
1. STXBP1 ↔ SLC6A1, shares mechanism (experimental, contested)
2. STXBP1 ↔ SLC6A1, similar symptoms (inferred)
3. STX1B ↔ SLC6A1, similar symptoms (inferred)
4. 3,4-diaminopyridine → STXBP1, candidate (hypothesis). The drug belongs to the drug-responsive NMJ cluster.
5. 3,4-diaminopyridine → STX1B, candidate (hypothesis). Same reason.
6. 4-phenylbutyrate → SLC6A1, developed for (clinical, contested). The drug spans SLC6A1 and the SNAREopathies.
7. 4-phenylbutyrate → STXBP1, developed for (clinical, contested). Same reason.
8. 4-phenylbutyrate → VAMP2, candidate (hypothesis). Same reason.

**Per disease** (connections, with links to one node counted once):
- STXBP1: 3
- SLC6A1: 3
- STX1B: 2
- VAMP2: 1
- the other 7 diseases: 0

**On the map:**
- Each bridge is an accent-blue line (#3e6ea5) on a pale accent band (#c7d8ea), drawn above other lines.
- The dash pattern still shows the evidence level, so dashes keep meaning inferred or hypothesis.
- Hovering a bridge darkens it and labels it "Bridge across clusters · <relation>".

**Elsewhere:**
- **Legend:** "Bridge across clusters · 8 in the atlas".
- **Evidence panel:** "Bridge across clusters." followed by one sentence on which boundary the link crosses.

### Disease panel (`components/atlas/Glance.tsx`, `lib/glance.ts`)
The rows follow the mockup's order:
1. **Clusters:** shown as before.
2. **Centrality:** "Centrality N/100" with a thin bar and "How much this disease connects others in the atlas."
3. **Key investigators:** "N researchers, M institutions". Researchers with `works_on` links to the disease or its gene; institutions are their distinct affiliations.
4. **Cross-cluster bridges:** "N connections worth exploring".
5. **Patient groups active:** "N organizations, M registries", plus natural history studies when there are any. These are `serves` organizations, and registry or natural-history assets with a `covers` link.
6. **"Explore connections →":** opens `/disease/<id>#shares`.

Each count expands its list in place:
- Items select the node on the map.
- Bridge items show why the link counts as a bridge, plus evidence chips.

Other node types show only the centrality row. The existing summary, facts, buttons and connections follow below.

### Viewing as
- **One switch per page:** there is still one switch (`components/ViewingAs.tsx`) and one persona store. It sits in the header on every page except `/atlas`, where it moves to the top of the selection panel as "Viewing as · Maria, patient leader".
- **Persona names:** the personas are now named after the brief's people: Maria, patient leader; Devon, newly diagnosed; Priya, biotech scout; Dr. Osei, researcher.

### Checks
- **Static checks:** `tsc`, `eslint .` and `npm run build` pass.
- **Bridge logic:** checked against the real graph, finding the 8 bridges above.
- **Browser:**
  - STXBP1, SLC6A1 and VAMP2 panels with every row expanded.
  - The evidence panel on a bridge.
  - Bridge styles read back from Cytoscape.
  - A persona change on the atlas shows up in the disease-page header.
  - The console is clean in a fresh tab.

---

## Any rare disease (global index, basic data)

No live AI calls were made in this round. The data comes from `data/derived/global/` (see its README).

### Sync and loading
- **Sync:** `scripts/sync-data.mjs` copies `data/derived/global/**/*.json` into `public/data/derived/global/`, keeping the folder structure. Each file is checked as valid JSON first; a bad file is skipped with a warning.
- **Loader (`lib/global.ts`):** the djb2 bucketing, ported exactly and checked against the README test vectors (38, 60 and 3).
  - `searchGlobal()`, the README search recipe.
  - `mappedAtlasId()` and `rowHref()`.
  - The shard loader. `GlobalShardKind` is the slot for the mechanism, pathway and cluster shards that use the same bucketing; the `/d/` page has a marked place for them.
- **Cache (`lib/resource.ts`):** a keyed cache for lazy loads. Loads are triggered from handlers and effects, never during render. Errors stick until `retry()`, so a missing file is never fetched in a loop.
- **When files load:**
  - `index.json` loads only on the first focus or keystroke in a search box, when a link opens search with text in it, or about a second after Home opens (idle prefetch). `/atlas` and the other pages do not fetch it.
  - A `/d/` page loads `index.json`, `meta.json` and exactly one `neighbours/<bucket>.json`.

### Search (`components/search/SearchBox.tsx`)
- **Second group:** "Other rare diseases (basic data)", shown with synonym resolution, e.g. "“Huntington's chorea” → Huntington disease", plus the genes and the number of annotated symptoms.
- **Mapped rows:** index rows with `atlas` set join the atlas group and open the existing disease page, but only if the loaded graph has that disease. The index flag can land before the graph is rebuilt; until then the row stays basic data.
- **Order:**
  - Atlas results stay on top when they are real matches.
  - A clearly better global match goes first, so Enter opens it:
    - the global match is exact (name, synonym, gene or id) and the atlas has no exact match; or
    - the global match is a whole-word prefix and the atlas has only loose fuzzy matches.
  - With global results present, the loosest fuzzy atlas matches (score above 0.3) are dropped.
- **Ranking tweaks** on top of the README recipe:
  - Within each rank, a whole-word match beats a partial one, and fewer extra words win before `n` ("rett" → Rett syndrome first).
  - Among the atlas's own prefix matches, shorter names now come first.
- **Path pickers:** the path pickers accept global diseases.
- **Disease not found:** `/disease/<unknown>` now opens with the search filled in, so "huntington" lists Huntington disease immediately.

### `/d/<id>` (`components/global/GlobalDiseaseView.tsx`)
- **Header:** the name, synonyms, genes (with the Orphanet-only note when `gsrc` is 2), inheritance, number of annotated symptoms and identifiers. Links out to OMIM, Orphanet, Monarch, ClinicalTrials.gov, NORD and GeneReviews, built from `meta.url_templates`.
- **Status line:** "Mapped in basic form. The atlas maps N disease families in depth today (…); this disease isn't one of them yet."
  - N and the family names come from the graph's pathway clusters, so they update as families land.
  - When an in-depth atlas disease lists this name among its own names (Dravet syndrome → SCN1A, Gaucher disease → GBA1), the line links to it instead.
- **Caveat:** `meta.caveat` is shown under the status line on every page.
- **Most distinctive symptoms:** the top 8, each labelled distinctive or broad (IC ≥ 4) with the IC, linked to HPO.
- **Diseases with the most similar symptom patterns:** the top 10 with their shared symptoms. Each links to its `/d/` page, or to its atlas page if mapped.
- **Closest disease in our mapped families:**
  - "Close to …" for every near disease.
  - Or the far sentence, with the nearest mapped disease and `meta.far_text`.
  - The symptom comparison was computed against the SNAREopathies only, so when the graph has newer families the page says the comparison doesn't cover them yet. The far sentence then names the families actually compared.
- **How the atlas would map it in depth:** three steps and a link to /contribute.
- **Edge cases:**
  - A disease with fewer than 5 annotated symptoms says it has too few to compare and still shows the links.
  - A row that is mapped in the live graph redirects to its disease page.
  - The tab title updates to the disease name.

### Path page
When either end is a global disease, the page explains that paths run only inside the families mapped in depth, and links to that disease's `/d/` page.

### Load sizes (gzip is what goes over the wire)
- `index.json`: 1.62 MB raw, 431 KB gzip, once.
- `meta.json`: 29 KB raw, 8 KB gzip, `/d/` pages only.
- Neighbour shard: 235 KB raw / 55 KB gzip on average; the largest is 451 KB / 102 KB. One shard per `/d/` page.
- **Whole synced folder:** 147 MB. Another agent added `dismech/` (31 MB) and `dismech_evidence/` (87 MB) while I worked; `**` copies them, but no page loads them.

### Checks
- `tsc`, `eslint .` and `npm run build` pass.
- The console was clean in fresh tabs.
- The search order and bucketing were checked against the real data with Node.

---

## Profile-specific experience (docs/persona-spec.md)

No live AI calls were made in this round.

### Profile switch
- **The switch:** "Viewing as: Devon (new to this) ▾" sits top right on every page, the atlas included. It opens a menu that gives each profile a one-line description (`components/ViewingAs.tsx`).
- **First visit:** a gentle chooser appears under the header, "Who are you? (You can change this anytime)", with Devon preselected. It blocks nothing.
- **Ids and defaults (`lib/persona.ts`):**
  - The ids stay `family`, `leader`, `researcher` and `biotech`, and `?as=` still works.
  - Devon is the default.
- **Devon's header:** no technical navigation (only Search and How we know), and it works on a phone.
- **Tours:** the Maria tour sets the Maria profile; the SYT2 tour sets Devon and walks his page.

### Devon
- **Landing (`/`):** "What diagnosis did you receive?", a hint, the search box, three reassurance lines and the safety note. Nothing else above the fold.
- **Diagnosis page:** `components/devon/DevonPage.tsx` is fed by `DevonDisease.tsx` (mapped diseases) and `devonGlobal.ts` (`/d/` pages), in the spec's order:
  - plain words, with glossary terms explained on tap (`components/PlainText.tsx`);
  - "You are not alone", a rounded range labelled estimated;
  - contact cards for groups, then registries;
  - a "this week" checklist;
  - questions for the doctor, with a one-page printable sheet (print CSS);
  - studies looking for participants, in plain words;
  - the honest no-group path;
  - "Learn more" collapsed, holding the full detailed page.
- **Sourcing:**
  - Every fact has "How do we know this?": it opens the graph edge's evidence, or names the source with links.
  - No confidence numbers are shown.
  - Text comes from templates filled with real data; where data is missing, the page says so.
- **Data used:**
  - population/`prevalence.json`, `channels.json` and `readiness.json`;
  - for `/d/` pages, the web/scale shards: organisations, studies, registries and prevalence.

### Dr. Osei
Disease pages add, in this order:
- **Patient population:** estimated ranges for the world, Europe and the US; Orphanet records with type, class, area and source; ClinVar variant groups; and enrollment in existing studies.
- **Trial readiness:** the readiness.json scorecard (tick, partial or gap), with evidence chips.
- **Reach patients for a study:** organisational channels only (`channels.json`), plus investigators grouped by institution, and "Draft an outreach message".
  - The new AI kind is `outreach`. Precomputed files are named `outreach--<id>.json`, and targets for VAMP2, STXBP1 and SCN2A are in `ai-targets.json`.
  - Nothing has been precomputed yet.

The DisMech chain sits on the detailed page.

**`/research` cohort view:** all 45 diseases, sortable and filterable by family and mechanism. Columns: estimated affected, recruiting studies, registry, organisations, readiness and mechanism class.

### Priya
- **Landing:** Priya lands on `/approach` (once per visit), and Dr. Osei on `/research`.
- **`/approach`:** opens with "Unmet need and trial readiness first" for Priya. Other profiles get it collapsed.
- **`/research`:** for Priya, it leads with the unmet-need and readiness columns.

### Data and sync
- **Excluded:** `dismech_evidence/` (87 MB) is no longer copied.
- **Distilled at sync** into `public/data/derived/web/`:
  - `scale/<bucket>.json`: organisations, studies, registries and prevalence per index row and per atlas disease. 5.6 MB, one shard per page.
  - `dismech_snippets/<bucket>.json`: one verbatim snippet per DisMech step.
  - `available.json`: which optional products exist, so pages never probe for missing files.
- **Not shipped:** `prevalence_orpha.json` (5.7 MB) is distilled into the scale shards.
- **Search:** `index_extra.json` is now searched alongside the main index.
- **`/d/` pages:**
  - The mechanism layer: G2P and ClinGen records, Reactome pathways, the mechanism family and its members.
  - The DisMech chain, only where DisMech has a record. It loads only when opened and carries attribution.

---

## View names, guided search, sequence and VCF check

No live AI calls were made in this round.

- **View names:** Simple (default), Detailed, Research and Industry, each with a one-line description. Persona names are gone from the switch, the first-visit chooser, the tours ("Follow a patient group", "Follow a family with no patient group"), Home and Impact. /method now has "One atlas, four views". Ids and `?as=` are unchanged.
- **Guided search (Simple only):**
  - The search box shows one result: the general disease. That is an in-depth disease when the atlas has a strong match; otherwise the global row's head from `data/derived/global/groups.json`, falling back to a name-stem heuristic in `lib/groups.ts` behind the same interface. "Not it? See all matches" opens the normal list.
  - Picking it opens `/start?d=<id>`:
    - a reassurance;
    - "Do you know which type?" with large options and plain distinctions;
    - "I'm not sure, show me the general information";
    - a collapsed "Similar names that are different conditions".
  - It then goes to the plain diagnosis page, which repeats the type that was chosen.
- **/sequence:** FASTA or VCF (.vcf, .vcf.gz via DecompressionStream), compared in the browser. The page says so prominently.
  - **FASTA:** banded global alignment against the MANE CDS (`data/derived/sequences/<GENE>.json`), with HGVS c. (3'-shifted indels, dup detection) and p., and a consequence class with a splice-region flag.
  - **VCF:**
    - Streams line by line and detects GRCh37 or GRCh38 from ##reference or ##contig, with a manual override.
    - Maps changes in the 45 genes through the exon table, both strands, including intronic c.N±k. Checked against ClinVar HGVS: 543 of 543 substitutions agree.
    - Looks up `variant_positions.json` (exact substitution keys and SPDI indels).
    - Gives a count summary.
  - **Shared by both:**
    - ClinVar lookups through `lib/variant.ts` (`variants.json`).
    - A one-page "Print for your doctor" with the disclaimer.
    - An opt-in NCBI BLAST POST form; the sequence is never put in a URL.
    - Synthetic examples.
    - A kind message, linking to the report-line lookup, for genes outside the 45.
- **Linked from:** Simple Home and the Simple diagnosis pages of the 45 deep genes.
- **Sync:** `data/derived/sequences/**` is copied. `web/sequence_examples.json` and the availability flags for groups, sequences and variant positions are written.

---

## Community accounts, onboarding and the no-result flow

### Wording and no-result flow (Simple view)
- **Landing:** "Which disease are you looking for?", with copy that also suits relatives and friends. The safety note no longer assumes a child.
- **Nothing matched:** the search box says "We couldn't find '<q>' in the atlas yet." It offers "Did you mean" (trigram similarity over the global index and index_extra) and a link to `/help?q=`.
  - In Simple, the loosest fuzzy atlas matches no longer hide this answer.
- **/help:**
  - Did you mean.
  - Closely related problems: symptoms recorded in the atlas, matched by phrase or word, with their diseases; and partial gene symbols with their conditions.
  - Who you can contact now (`components/help/GeneralHelp.tsx`): NORD, EURORDIS, Global Genes RARE Concierge, Genetic Alliance UK, and a genetic counsellor by referral.
  - Tell us about this disease, linking to /contribute.
- **Basic-data `/d/` pages:** in Simple, they start with the same "Who you can contact now" block.

### Accounts
- **Storage (`lib/server/store.ts`):**
  - Upstash Redis over REST, using `KV_REST_API_URL`/`KV_REST_API_TOKEN` or `UPSTASH_REDIS_REST_*`.
  - Locally, a JSON file in `web/.data/` (gitignored). Redis is used locally only with `STORE=redis`.
  - On Vercel without Redis: off, and the UI says "Sign-up opens soon".
- **Server (`lib/server/community.ts`):**
  - Passwords: scrypt with a per-user salt.
  - Sessions: an HMAC-signed, httpOnly, sameSite=lax cookie (secure in production), signed with `SESSION_SECRET`.
  - Validation of every field; same-origin checks; rate limits per IP; no logging of emails.
- **Routes:** `/api/account` (GET, PATCH, DELETE), `signup`, `login`, `logout`, `export`, `/api/research/{announce,interest,contact}`, `/api/admin/announcements` (needs the `ADMIN_TOKEN` header).
- **Pages:**
  - Join box (`components/community/JoinBox.tsx`): appears at 40% scroll, can be dismissed for 7 days, hidden during tours, and shows "Sign-up opens soon" when off.
  - `/join`: 3 steps, then a welcome screen.
  - `/me`: followed diseases; inbox with reviewed announcements, relayed researcher messages, and studies recruiting now from the channels and scale data; saved items; privacy toggles; export; a real delete; researcher tools.
  - `/admin`: the moderation queue.
  - `/privacy`.
  - A header link ("Sign in" or "My atlas"), and "Save to my atlas" on the doctor questions.
- **Researcher tools:**
  - Announce a study (pending review).
  - Community interest: counts per disease and coarse country, with k ≥ 5.
  - Request contact: relayed only to members who opted in; a delivery count is shown only at 5 or more.
  - Researcher accounts are verified by institutional email domain; the page says how full verification would work.
- **Cheap extras built:** "notify me when a patient group forms", a weekly-digest preference, export my data.

### End-to-end test
Run against a local `next start` on port 3015 (file store, test `ADMIN_TOKEN`), plus the UI on the dev server:
- The family follows STXBP1 with contact consent.
- A researcher signs up from an `.edu` address and comes out verified.
- The researcher's announcement is pending, and the family inbox is empty.
- The admin queue shows 1; after approval, the family inbox has the announcement and the researcher sees "approved".
- A contact request is relayed: the note says fewer than 5, so no number is shown, and the family inbox gets the message.
- The interest count is withheld (fewer than 5 members).
- A family account cannot announce. A wrong password is refused. A cross-site PATCH is refused.
- Export returns the account and inbox.
- In the UI, a third account went through the join steps, the welcome screen, `/me` with the inbox, and "Delete my account".
- All three accounts were deleted, the store file was wiped, and no emails appear in the server log.

### AI drafts
41 precomputed files are synced (28 proposals, 5 explain-path, 3 compare-questions, 2 experiments, 3 outreach). The STXBP1 outreach draft renders on the Research view.

## Email, DNA-file requests, accuracy on /method, impact cleanup

### Email (Resend over plain HTTP)
`web/lib/server/email.ts` sends email with `fetch("https://api.resend.com/emails")`; there is no SDK. It has three modes:
- **dry-run:** with `EMAIL_DRY_RUN=1`, each email is written to `web/.data/outbox/` (gitignored) as `.json` (to, subject, headers, text) plus `.html`.
- **resend:** with `RESEND_API_KEY` and `EMAIL_FROM` set, email is sent.
- **disabled:** with neither set, the server logs `email disabled (<tag>)` and never the address. Notices stay in the inbox on /me, and the UI does not claim an email was sent.

What it does:
- **Templates:** confirmation, password reset, approved announcement, relayed researcher message, and new recruiting studies (single notice or weekly summary). Each has HTML and text versions and says why the reader is receiving it.
- **Unsubscribe:** every notification email has an unsubscribe link, plus the `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers.

**Tokens** are HMAC-signed with `SESSION_SECRET`, bound to a purpose, and compared with `timingSafeEqual`:
- confirmation: 7 days;
- reset: 1 hour and single use (a nonce is stored as `reset:<uid>` and deleted on use);
- unsubscribe: no expiry.

**Rules:**
- Notification emails go only to confirmed addresses that have not unsubscribed, and only for the matching consent (trials or researcher contact).
- Unconfirmed accounts see a banner with "Send the link again" and get no study emails.
- "Forgot password" gives the same answer whether or not the address exists.
- A plain GET of the unsubscribe API changes nothing, because link scanners prefetch links. The `/unsubscribe` page and mail clients POST instead.

**Cron:** `/api/cron/digest` runs daily from `web/vercel.json` (08:00 UTC). It accepts `Authorization: Bearer <CRON_SECRET>` (what Vercel sends) or `x-cron-secret`, and is closed if `CRON_SECRET` is unset.
- It reads open studies per followed disease from the synced data: `population/channels.json` for atlas diseases and the `web/scale` shards for global ids.
- It keeps a per-disease baseline (`trials:known:<d>`). The first run only records the baseline.
- New studies are emailed at once to members who chose single notices. For weekly members they are queued (`pending:<uid>`, together with approved announcements) and sent once 7 days have passed.
- `sent:<uid>` prevents duplicates.
- It returns counts only.

**Admin:** `/admin` shows the email mode, and "Email delivery is in test mode" unless `EMAIL_DOMAIN_VERIFIED=1`. After an approval it says how many members were emailed and how many were queued.

**New routes:**
- `/api/account/verify` and `/api/account/verify/resend`
- `/api/account/forgot` and `/api/account/reset`
- `/api/account/unsubscribe`
- `/api/cron/digest`

**New pages:** `/verify`, `/forgot`, `/reset`, `/unsubscribe`. Sign-in has a "Forgot password?" link, and /me has an "Email me these notices" switch. `/privacy` now has an Emails section.

Followed-disease names travel with follow and sign-up (`labels`, sanitized). Emails can therefore say "SCN2A-related disorder" rather than an id.

**Local test support:** `STORE_FILE` (a separate throwaway JSON store) and `NEXT_DIST_DIR` (in `next.config.ts`) let an isolated dev server run next to the shared one without touching `.next` or `.data/store.json`. Neither is used in production.

### Email test (38/38 passed)
The test ran against an isolated dry-run dev server on port 3100, with its own store file and throwaway `example.org`/`example.edu` accounts. All accounts were deleted, and the store file and build folder were removed afterwards. It covered:
- Sign-up writes a confirmation email. A tampered token is refused (400). The valid link confirms the account.
- Admin GET reports the dry-run mode and test mode. Approval emails the one opted-in follower, with the disease named and both unsubscribe headers, and without the researcher's address.
- A contact relay emails the opted-in member, and the researcher's response contains no address.
- Forgot/reset:
  - an unknown address gets the same answer and no email;
  - a short password is refused;
  - the reset works once, and the link is refused the second time;
  - the old password fails and the new one works.
- Unsubscribe: a GET only redirects. The RFC 8058 POST unsubscribes, and a tampered token is refused.
- Cron:
  - 401 without the secret or with the wrong one;
  - run 1 records the baseline and sends nothing;
  - after 2 studies were made "new", run 2 sends one single-notice email and one weekly summary listing both;
  - run 3 sends nothing (no duplicates).
- The server log contains no email addresses.

### "Don't have a DNA file?" (`/sequence/request`)
- `/sequence` has the line "Don't have one and want to request one? Click here" under "Your sequence never leaves this device".
- The page asks "Have you already had a genetic test?":
  - **Yes:**
    - which files to ask for (VCF, BAM, FASTQ, CRAM);
    - lab cards with a region filter: what each lab provides, who can ask, how to ask, cost as stated, caveats, source links, and the verbatim quotes under "What the page says";
    - rights for the EU, UK and US, labelled general information, not legal advice;
    - an editable request letter with Copy and Print (Print opens a plain page so the site menus are not printed).
  - **No:**
    - a doctor or genetic counsellor first, then sponsored no-cost programmes, then research programmes, filtered by where you live;
    - route cards show the status (for example "paused"), whether a referral is needed, eligibility in the source's words, who pays and what happens to the data;
    - the consumer-test caution with its sources.
  - **Not sure:** six questions to ask your doctor, which can be printed.
- All content comes from `data/curated/testing_options.json`. It is now synced, with an `available.testing_options` flag, and no company outside that file is named. Without the file, the page says so.

### "How well does it work?" on /method
This section reads `data/derived/eval.json` (synced automatically with the derived files; flag `available.eval`). Every number comes from the file, so it follows re-runs.
- **Big numbers:** 73% in the top 5 (random 12%), 29% first (random 2%), 83% in the top 5 when the therapy already helps another disease, and 60/68 readings agreeing with the independent AI.
- **A table of 8 ranking methods:** top 1, top 5 and MRR, with 95% ranges for the best honest method. It includes the same-family baseline and the rule behind today's ideas page.
- **The rest:** the 5-sentence plain summary, the known-collaboration checks (4-PBA, MEK inhibitors, miglustat), agreement with other sources, the limitations, and a link to the full JSON. The wording follows `docs/agent-reports/eval.md`.

### /impact
The landscape step is gone from impact.json, and the "awaiting expert figure" code path is removed. The gene-to-trial timeline links now wrap on phones; they caused 17 px of sideways scroll at 390 px.

### Checks
- `tsc --noEmit` and `eslint` are clean. One `npm run build` at the end passed.
- These pages were checked at 1440 and 390 px with headless Chromium, with no sideways scroll and no console errors: `/sequence/request` (yes, no, not sure), `/method`, `/impact`, `/verify`, `/forgot`, `/reset`, `/me` (signed out, and signed in with the confirm banner), `/admin` (test-mode notice) and `/sequence`.
- The only console error found was a deliberately invalid unsubscribe link, which shows a 400 and a friendly page.

## Live alerts, contact details, "What we collect"

### Live "new trial / new researchers" alerts
`/api/cron/digest` now checks live sources (`web/lib/server/live.ts`, `web/lib/server/digest.ts`).

**What it looks for**, for each disease at least one member follows:
- **ClinicalTrials.gov API v2:** RECRUITING and NOT_YET_RECRUITING studies matching the name, synonyms or gene.
- **NIH RePORTER:** projects in fiscal year ≥ the current year minus 1 that name one of the disease's genes.

**Trial precision filter**, a compact port of `pipeline/scale/build_trials.py`, as described in `data/derived/scale/README.md`:
- Names and synonyms must match as whole phrases. These are rejected:
  - hyphen-glued hits;
  - hits followed by a gene context ("… gene", "mutated");
  - digit-free abbreviations;
  - generic single words.
- Gene symbols are case-sensitive and need a gene context within 3 words. They are rejected in:
  - oncology or common-disease studies;
  - drug, biomarker or SNP contexts;
  - acronyms the study spells out;
  - the symbol stoplist.
- Gene matches are labelled "mentions <GENE>".

**Grants:** RePORTER is asked only for the title, organisation and fiscal year; no investigator fields are requested. Projects are deduplicated by core project number and link to the public project page.

**State in the store:**
- a seen-set per source and disease (`alerts:seen:<trials|grants>:<d>`);
- the first check of a disease only seeds the seen-set;
- a failed request never seeds.

**Notices:**
- Every follower gets an inbox notice (new inbox kinds `trial` and `grant`, with a link).
- Members who asked for study news by email (the `trials` consent, now worded "new recruiting studies and newly funded research") also get an email, now or in their weekly summary.
- `sent:<uid>` prevents duplicates.

**Limits:**
- `ALERTS_MAX_REQUESTS` caps requests per run (default 40, which is 20 diseases).
- Diseases are checked 4 at a time, with an 8 s timeout per request and a 40 s budget.
- A rotating cursor (`alerts:cursor`) covers long lists across runs.
- The run logs a single counts line.

**Follow for alerts:** disease pages (Simple, Detailed/Research and global) now show a one-tap "Follow for alerts" for signed-in members. Once followed it reads "Following: new studies and research appear in My atlas". Signed-out visitors still get the join box.

**vercel.json:** adds `/api/queue/sweep` daily at 08:30 UTC. It uses the same `CRON_SECRET`; the sweep route requires at least 16 characters.

### Contact details
- **Sync:** `scripts/sync-data.mjs` turns `data/derived/contacts/{orgs,trials}.json` into slim browser files (`public/data/derived/contacts/`, 47 KB and 160 KB) and sets the `available.contacts` flag.
  - Personal names are dropped at this step; CT.gov central contacts keep only phone and email.
  - Snippets and evidence text are dropped too.
  - Result: 210 organisations and 1,463 recruiting studies.
- **Display:** `components/contacts/ContactLine.tsx` shows a `tel:` and `mailto:` with "From their website · retrieved <date>" or "From ClinicalTrials.gov · retrieved <date>". It appears on:
  - the Simple view's "People you can contact" cards and registries;
  - study cards;
  - Research "Reach patients" channels.
- **Matching:** organisations are matched by id, then website host, then name; studies by NCT.
- **Simple tip:** the Simple view adds "When you call or write, it helps to mention the gene name and that you found them through the Rare Disease Atlas." It appears only when a card has a contact.
- **Researchers:** no contacts are shown for individual researchers; they stay reachable through "Request contact" or their institution.

### /method
"What we collect and how often" is generated from `available.json` and the graph's source list:
- daily live checks for followed diseases;
- static layers refreshed on rebuild, with the build date.

### Tests
**Cron dry run:** an isolated dev server on port 3100 with its own store file, `EMAIL_DRY_RUN=1` and one throwaway follower of STXBP1, SCN2A and Duchenne (`MONDO:0010679`), with live APIs.
- Run 1 seeded 6 sets (STXBP1 6 trials and 1 grant; SCN2A 1 trial and 23 grants; DMD 30 trials and 16 grants) with 6 requests, 0 failures and no notices, in about 1 s.
- After 4 seen entries were removed, run 2 found 3 new trials and 1 new grant, wrote 4 inbox notices and 1 email (written to the outbox only).
- Run 3 sent nothing.
- With `ALERTS_MAX_REQUESTS=2`, each run checked 1 disease, and the cursor went 1, 2, 0, 1.
- 401 without the secret. No addresses in the log. All accounts and the store file were deleted.

**UI:** 1440 and 390 px, with no sideways scroll and no console errors:
- STXBP1 Simple: 7 tel and 7 mailto links, with the tip.
- STXBP1 Research: 9 tel and 10 mailto links.
- DMD Simple (global page).
- `/method`, `/me`.
- The follow button on a global page, signed in.

**Fixed along the way:** 748 px of sideways scroll on the Research view at 390 px (the ClinVar variant-type grid).

**Checks:** `tsc` and `eslint` are clean; one `npm run build` passed.

## Full ClinVar, gene factors, similar diseases, PrimeKG on /method

### Full ClinVar in /sequence and /variant
- **Sync:** `sync-data.mjs` copies all 64 shards, unfiltered, to `public/data/derived/ingest/clinvar/` (43 MB raw). It also writes `web/clinvar_genes.json` (361 KB), which holds, per assembly and chromosome, the span of each gene's exact ClinVar keys ±200 bp. That covers 6,206 genes; genes with only CNV-style records have no exact keys to match anyway.
- **Lookup library:** `web/lib/clinvar.ts` finds the genes covering a position by binary search, with a running maximum of span ends. It loads shards lazily, one at a time, and caches them.
- **VCF check (`/sequence`)** runs in two passes:
  1. Read every line. Keep only variants inside an atlas gene or a ClinVar gene span.
  2. Group by gene, fetch only the shards those genes need (24 genes at a time), and match exact `chr:pos:ref:alt` keys.
- **Results:**
  - The 45 atlas genes keep their c./p. mapping and atlas context.
  - Other genes are listed only when they match. They show ClinVar's own name, consequence, class and stars, and a link to the record.
  - The summary says how many genes and files were checked.
  - The printout includes these matches.
- **Report-line lookup (`/variant`):** a gene outside the atlas falls back to that gene's shard. It matches the c. change, treating `c.1100delC` and `c.1100del` as the same, then the protein change.

### Explanatory gene factors
- **Data:** sync-data builds `web/factors/<djb2(gene)%64>.json` (2.4 MB in total; each shard is small) for 25,335 genes. It draws on `constraint.json`, `clinvar_gene_spectrum.json` and `alphamissense_gene.json`.
- **Labels:** the rules in the global README's "Gene explanatory factors" section.
- **Display:** `components/disease/GeneFactors.tsx`, titled "What the gene tells us". It shows:
  - gnomAD constraint (LOEUF and pLI) with a plain label;
  - the ClinVar mutation spectrum as a stacked bar with a legend;
  - the AlphaMissense mean with a plain label.
- **Placement:** the Research and Industry views and Simple's "Learn more" on atlas pages, and every view except Detailed on `/d/` pages.
- **Wording:** each panel says these are explanations, not a score, because they did not improve rankings on the PrimeKG test.

### Similar diseases on /d/
- **Source:** `global/similar/<bucket>.json`, flag `available.similar`.
- **Display:** "Diseases most similar to this one" lists the top 10, each with its reasons as chips: "same gene: X", shared distinctive symptoms, and shared Reactome pathways linked to Reactome.
- **Coverage:** rows with too few symptoms for `neighbours/` now get a list too.
- **Fallback:** the old symptom-only list.

### /method
- **"Tested on 1,300 external cases":** PrimeKG, `primekg_eval.json`.
  - Three big numbers: 0.37 for the site's scorer (symptoms, same gene and pathways), 0.32 for symptoms alone, and 49% in the top 5.
  - A table of 10 single factors: MRR, top 5, and MRR on the 644 cases where the diseases share no gene.
  - The plain conclusion.
- **"What we collect":** now also lists full ClinVar, gene factors and similar diseases.

### Tests
**VCF test:** the synthetic `STXBP1_c.1162C>T_GRCh38.vcf` plus two lines on chr22, CHEK2 c.1100delC (GRCh38 22:28695868 AG>A) and a nearby change that is not in ClinVar.
- Result: 4 variants checked; 2 in atlas genes; 2 known disease-causing.
  - STXBP1 c.1162C>T, p.Arg388Ter, is Pathogenic (VCV000006730), with the atlas variant group.
  - CHEK2 c.1100del, p.Thr367fs, matched with ClinVar's name `NM_007194.4(CHEK2):c.1100del (p.Thr367fs)` and variation 128042: pathogenic, several labs agree.
  - The nearby change was not listed.
- Only 2 shard files were fetched (buckets 39 and 18).

**`/variant?q=CHEK2 c.1100delC`:** "Found in ClinVar", with the same record.

**UI:** at 1440 and 390 px there is no sideways scroll and no console errors on `/sequence`, `/variant`, `/d/MONDO:0010679` (Research and Simple), `/disease/STXBP1` (Research and Simple) and `/method`.

**Checks:** `tsc` and `eslint` are clean; one `npm run build` passed.

## Rebrand to Tasukeru, SMTP transport

### Rebrand
"Rare Disease Atlas" no longer appears in user-facing text in `web/`.
- **Root metadata:** the title is "Tasukeru: a rare-disease atlas". The description explains 助ける, "to help". Also set: `applicationName`, OpenGraph (`siteName` Tasukeru) and Twitter tags.
- **Page titles:** all 28 page titles now read "<page> · Tasukeru", including global disease pages.
- **Header and first visit:** the header logo text is "Tasukeru", and the first-visit chooser starts with "Welcome to Tasukeru."
- **Copy:**
  - the Simple view printout line, and the contact tip "found them through Tasukeru, a rare-disease atlas";
  - the ChatGPT-plan notice;
  - the DNA printout footer;
  - `/privacy`: "Privacy at Tasukeru", sending from no-reply@mehro.ch through Resend or our own mail server;
  - `/method`: a new line saying Tasukeru (助ける) means "to help" or "to rescue" in Japanese.
- **Emails:**
  - the header reads "Tasukeru · a rare-disease atlas", and the footer adds "Tasukeru (助ける, 'to help') · a rare-disease atlas";
  - subjects are prefixed "Tasukeru: …", and the weekly one is "Your Tasukeru weekly summary";
  - the sender comes from `EMAIL_FROM`; a bare address gets the display name "Tasukeru".
- **Worker and user agents:**
  - `APP_NAME` (the Sign in with ChatGPT `agent_name_hint`) is "Tasukeru";
  - the banner and help text read "Tasukeru research worker";
  - the worker's user agent is `tasukeru-worker/<v>`;
  - the live alerts user agent is `tasukeru/0.1`;
  - the NCBI `tool` is `tasukeru`.
- **Unchanged:** routes, ids, env vars, file names (`rare-atlas-worker.mjs`, `~/.rare-atlas-worker/`) and the Vercel URL.

### SMTP transport
- **Order in `lib/server/email.ts`:** `EMAIL_DRY_RUN=1`, then SMTP when `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and `SMTP_PASS` are all set, then Resend when `RESEND_API_KEY` is set, otherwise disabled.
- **SMTP:** sends with nodemailer 7.
  - Port 465 uses TLS from the start; 587 requires STARTTLS; other ports use STARTTLS if offered.
  - Connection timeouts are set, and nodemailer's logger and debug output are off.
  - Errors return only a short code (`smtp EAUTH`, `smtp ESOCKET`, `HTTP 403`). The log shows tag and code only, never addresses or credentials.
- **Admin test email:** `/admin` has "Send a test email to myself", which calls `POST /api/admin/test-email`.
  - It needs the `ADMIN_TOKEN` header, a same-origin request and a signed-in, confirmed account. It is rate-limited.
  - It always sends to the session's own address and reports the transport and the result.

### Tests
**Fake SMTP server:** written for the test (scratchpad, no TLS; it accepts or rejects AUTH on demand), with an isolated dev server using made-up SMTP credentials.
- Test email before signing in: "Please sign in."
- Sign-up: the confirmation arrived at the fake server, from "Tasukeru <no-reply@mehro.ch>", subject "Tasukeru: please confirm your email". Its link confirmed the account.
- Wrong admin token: refused.
- Test email: `{"transport":"smtp","sent":true}`, and "Tasukeru: test email" arrived.
- AUTH rejected: `smtp EAUTH`. Server down: `smtp ESOCKET`.
- Credentials and addresses appear 0 times in the server log. The account and the store file were deleted.

**UI:** at 1440 and 390 px, `/`, `/method`, `/privacy`, `/disease/STXBP1` and `/admin` show the new titles and OG site name, with no sideways scroll and no console errors. The test button appears after the queue loads.

**Checks:** `tsc` and `eslint` are clean; one `npm run build` passed.
