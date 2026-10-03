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
