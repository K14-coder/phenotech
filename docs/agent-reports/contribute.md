# Contribute evidence: backend API

This backend lets "the graph grow as new evidence and communities contribute" (stretch goal: "let patient groups contribute missing evidence").

A patient-group leader pastes the URL of a page about something that already exists: a registry, a natural history study, a biobank, a model, an outcome measure, a press release. The atlas reads the page and proposes additions. Nothing reaches the graph until the contributor commits.

Code: `pipeline/contribute/`. It is dependency-free Node ESM.

| File | What it does |
|---|---|
| `contribute.mjs` | `preview()`, `commit()`, `toHttpError()`, the CLI, the model prompt and schema, and the deterministic analysis |
| `page.mjs` | Fetching: a plain fetch, then the Bright Data Web Unlocker fallback. Also the page cache, `htmlToText()`, the ~12k-character excerpt, and the private-host guard |
| `match.mjs` | Quote verification, disease and gene reconciliation, and duplicate detection. No network |
| `test.mjs` | 19 tests. They inject a fake `complete` and mock `fetch`/DNS, and write only to a temp directory |

Data written: `data/curated/contributions.json` (a normal `{nodes, edges}` fragment, empty until the first commit) and `data/raw/contributions/` (the page and extraction cache).

## The flow

**`preview({ url, diseaseId? })`** writes only the raw cache:

1. **URL.** Only `http(s)` is accepted, with no credentials. The `#fragment` and `utm_*`-style parameters are dropped. Local and private-network hosts (`localhost`, `10.x`, `192.168.x`, `*.local`, …) are refused, and every redirect hop is checked again. This matters because the URL comes from a browser.
2. **Fetch.**
   - A plain `fetch` comes first.
   - On a network error, an HTTP error (except 404/410), a bot wall (Cloudflare, Anubis, Imperva, DataDome, Akamai), or a page with almost no text (a JS shell), the backend makes **one** `POST https://api.brightdata.com/request` with `{zone, url, format:"raw"}` and `Authorization: Bearer $BRIGHTDATA_API_TOKEN`. The zone is `BRIGHTDATA_UNLOCKER_ZONE`. Both are read from the environment or `.env.local`.
   - Bright Data's `x-brd-status-code` header gives the target's real status, and `x-unblocker-redirected-to` gives the final URL.
   - Soft 404s ("Page not found" titles) are rejected.
   - E-mail addresses are redacted before anything is stored.
   - The page is cached in `data/raw/contributions/<sha256(url)[:24]>.json`, with the retrieval date, the HTML and the text.
   - The token is never logged, returned or stored. Error messages are scrubbed of it, and a test checks this.
3. **Text.** `htmlToText()` drops script, style, head, svg, comments and similar elements. It decodes named, numeric and cp1252 entities, puts blocks on separate lines and collapses whitespace. The title and meta description go on top.
4. **One structured OpenAI call** through `integrations/openai/llm.mjs` `complete({instructions, input, schema})`. Each item is `{kind, name, asset_kind, diseases_or_genes_mentioned[], what_it_offers, how_to_access, quote, nct_id}`.
   - The model reads at most 12,000 characters. Long pages keep the title lines plus the blocks with the most resource keywords and atlas gene or disease names. Repeated menus and footers are dropped, and the original order is kept.
   - The page text is fenced as data, and the prompt tells the model to ignore instructions inside it.
   - The extraction is cached per page text and prompt version in `<sha>.extraction.json`. Previewing the same page again costs no model call.
5. **Quote check.** The quote must be a verbatim substring of the full page text after NFKC, dash/curly-quote folding and whitespace collapsing. It must be 20–800 characters. Case is kept, and quotes are never edited. Failing items are `rejected`.
6. **Reconcile.** A deterministic index is built from `data/graph.json`:
   - It holds disease labels and their parenthetical parts, plus *specific* synonyms: those with a number ("DEE4"), the gene ("GAT-1 deficiency") or part of the label.
   - It also holds gene symbols ("STXBP1", "Stxbp1") and gene names with a number ("Munc18-1"), via `causes` edges.
   - Broad clinical names that many genes cause ("Doose syndrome", "MAE", "GEFS+") are deliberately not used. Neither are names that point to two diseases.
   - Each mention must also appear on the page. Atlas diseases named in the quote are added.
   - Only reconciled diseases get edges.
7. **Duplicates.** Existing `patient_org`/`asset`/`study` nodes are matched in this order:
   1. NCT number (study id or asset `xrefs.NCT`)
   2. normalised name (label, synonyms, label parts, acronyms)
   3. the node's own `attrs.url`
   4. 80% word overlap

   Derived names made only of gene symbols and generic words are not used: "STXBP1 patient registry" does not match "STXBP1 patient registry (University Hospital Heidelberg)". A duplicate becomes a new supporting source on the existing node, not a new node. If the atlas already cites that exact sentence, the item adds nothing.
8. **Return** the proposed fragment, the per-item verification results and the duplicates.

**`commit(previewResult, { contributor? })`**:

- It **recomputes** everything from the server-side cache (page plus extraction) and the current graph. It only reads `url`, `requested_url`, `disease_id`, `contributor` and `extraction.id` from the preview, so a tampered preview cannot inject quotes or edges.
- It **replaces** any earlier contribution from the same page URL in `contributions.json`, then adds the new one. Committing the same URL twice produces the same file byte for byte (`changed: false`). Re-committing after a new preview replaces the old version, so nothing is duplicated.
- A lock file serialises concurrent commits. It then runs `python3 pipeline/build_graph.py` and `node web/scripts/sync-data.mjs`. If the build fails, the fragment is rolled back.

### What gets written

| Item | Node | Edge to each reconciled disease |
|---|---|---|
| `patient_org` | `org:<slug>` with `attrs {url, access?, contributed}` | `serves` |
| `asset` | `asset:<slug>` with `attrs {kind, url, access?, contributed}` | `covers` |
| `study` (NCT on the page) | `study:<NCT>` with `attrs {status:"unknown", url: ClinicalTrials.gov record, contributed}` and `xrefs.NCT` | `studies`, the SCHEMA relation for study → disease |
| duplicate of an existing node | a stub `{id, type, label, attrs:{contributed_sources:[{by,date,url}]}, sources:[evidence]}`; `build_graph.py` merges it into the existing node | as above; added to the existing edge's evidence if the edge exists |

- `attrs.contributed = {by, date, url}`. `by` defaults to `"community"`.
- A study item without an NCT number becomes an asset if it has an `asset_kind`. Otherwise it is rejected.
- `maintains` (org → asset, labelled "runs / partners on") is added when the asset's quote names the organisation (0.5), or when the page is on an existing organisation's own website (0.4; the same convention as `community.json`).

Every edge has `status: "unverified"`, `evidence_level: "observational"`, `attrs: {contributed, basis}`, and a confidence that depends on the basis:

| basis | meaning | confidence |
|---|---|---|
| `quote` | the quoted sentence names the disease | 0.5 |
| `page` | the page names it, though not in the quote; or the contributor picked it and the page names it | 0.4 |
| `contributor` | only the contributor's `diseaseId`; the page does not name it | 0.3 |
| `quote_names_org` / `org_website` | for `maintains` | 0.5 / 0.4 |

The contributor's `diseaseId` is used only for items that reconcile to no disease. Items that name other diseases get those, with a warning.

A new item with no disease and no organisation link is held back as `unlinked`, so no node floats unconnected. The UI should ask the user to pick the disease and preview again. The page and model output are cached, so this costs nothing.

Evidence items look like this (they satisfy SCHEMA and `build_graph.py`'s checks):

```json
{ "source": "Website", "ref": "<page url>", "url": "<page url>", "title": "<page title>", "quote": "<verbatim sentence>",
  "kind": "website", "extracted_by": "openai:<model>", "verified": true, "retrieved": "2026-10-03" }
```

`extracted_by` is `human:<contributor>` when the items were typed in by a person (`items` option; see below).

Merge order is safe. `build_graph.py` loads fragments alphabetically: `community.json` comes before `contributions.json` and is the only file with `covers`/`serves`/`maintains`/`studies` edges. So an existing curated edge keeps its status and confidence (for example, "supported", 0.85), and our evidence is only appended. A test checks this against a copy of the real fragments.

## API for the web route

Suggested routes are `POST /api/contribute/preview` and `POST /api/contribute/commit`. Both call the module in-process.

### Preview

Request:

```json
{ "url": "https://www.bagosfoundation.org/natural-history-study", "diseaseId": "disease:SYT1" }
```

- `diseaseId` is optional, and `"SYT1"` also works.
- The route may also pass the contributor's name as `preview(req, { contributor })`.
- Optional manual mode (no AI): `{ url, diseaseId?, items: [ {kind, name, asset_kind, diseases_or_genes_mentioned, what_it_offers, how_to_access, quote, nct_id}, … ] }`. The items are verified exactly like model output and attributed to `human:<contributor>`. This is useful while the ChatGPT usage limit is exhausted.

Response `200` (abbreviated, from a real run on the page above):

```json
{
  "ok": true,
  "url": "https://www.bagosfoundation.org/natural-history-study",
  "requested_url": "https://www.bagosfoundation.org/natural-history-study",
  "disease_id": "disease:SYT1",
  "contributor": "BAGOS Foundation",
  "page": { "title": "Natural History Study | … The Baker-Gordon Syndrome Foundation", "via": "direct",
            "retrieved": "2026-10-03", "from_cache": true, "text_chars": 5143,
            "cache_file": "data/raw/contributions/fdeeaef896271caa0d30e725.json", "direct_problem": "HTTP 403 (only when via brightdata)" },
  "extraction": { "id": "b90fe5f9603d35a7", "source": "openai|manual", "extracted_by": "openai:gpt-6.1-sol", "model": "gpt-6.1-sol",
                  "from_cache": false, "generated_at": "…", "excerpt_chars": 5143, "excerpt_truncated": false, "item_count": 4 },
  "items": [
    {
      "index": 1, "status": "new", "reason": null, "reason_text": null,
      "kind": "asset", "name": "Optional blood and skin sample collection", "asset_kind": "biobank",
      "diseases_or_genes_mentioned": ["BAGOS"], "what_it_offers": "…", "how_to_access": null,
      "quote": "This study also has an optional portion in which the participant with BAGOS can choose …",
      "nct_id": null, "node_type": "asset", "node_id": "asset:optional-blood-and-skin-sample-collection",
      "verification": { "ok": true, "verbatim": true, "reason": null },
      "mentions": [ { "mention": "BAGOS", "status": "unreconciled", "matches": [] } ],
      "diseases": [ { "id": "disease:SYT1", "label": "SYT1-related disorders (Baker-Gordon syndrome)", "basis": "page" } ],
      "duplicate_of": null,
      "edges": [ { "id": "asset:optional-blood-and-skin-sample-collection|covers|disease:SYT1", "type": "covers", "confidence": 0.4, "basis": "page", "status": "new" },
                 { "id": "org:baker-gordon-syndrome-foundation|maintains|asset:optional-blood-and-skin-sample-collection", "type": "maintains", "confidence": 0.4, "basis": "org_website", "status": "new" } ],
      "warnings": []
    }
  ],
  "verification": { "checked": 4, "passed": 3, "failed": [ { "index": 3, "name": "BAGOS Registry", "reason": "not_on_page", "quote": "…" } ] },
  "duplicates": [ { "index": 0, "name": "Baker Gordon Syndrome Natural History Study", "existing_id": "asset:bagos-natural-history-study",
                    "existing_label": "Baker Gordon Syndrome Natural History Study (University of Missouri)", "match": "name", "already_cites_url": true } ],
  "fragment": { "nodes": [ "…exactly what commit would add…" ], "edges": [ "…" ] },
  "summary": { "items": 4, "new_nodes": 1, "new_sources_for_existing_nodes": 1, "new_edges": 2, "evidence_for_existing_edges": 1,
               "rejected": 1, "unlinked": 0, "excluded": 0 },
  "previous_contribution": null,
  "can_commit": true
}
```

- `items[].status` is one of:
  - `new`: becomes a new node.
  - `duplicate`: `duplicate_of` gives `{id, label, type, match: nct|name|url|similar_name|id, already_cites_url}`. It adds a source. If `already_cited: true`, the exact sentence is already cited and it adds nothing.
  - `rejected`: `reason` is `not_on_page`, `quote_too_short`, `quote_too_long`, `missing_quote`, `invalid_kind`, `invalid_asset_kind`, `study_without_nct` or `missing_name`; `reason_text` is readable.
  - `unlinked`: no disease or organisation link.
  - `excluded`: not in `include`.
- `items[].mentions[].status` is `reconciled`, `unreconciled` (not in the atlas, e.g. "SYNGAP1"), `ambiguous`, or `not_on_page` (the model named something the page doesn't).
- `items[].edges[].status` is `new` or `adds_evidence` (the edge already exists in the atlas).
- `previous_contribution`: `{nodes:[ids], edges:[ids]}` when this URL was committed before. Committing replaces it.
- `can_commit`: false when nothing would be written.

### Commit

Request: send the preview back (only `url`, `requested_url`, `disease_id`, `contributor` and `extraction.id` are read), plus options:

```json
{ "preview": { "...": "the preview response" }, "contributor": "BAGOS Foundation", "include": [0, 1, 2] }
```

`include` is optional and lists item indexes to commit (checkboxes). The route calls `commit(body.preview, { contributor: body.contributor, include: body.include })`.

Response `200`:

```json
{
  "ok": true,
  "url": "https://www.bagosfoundation.org/natural-history-study",
  "requested_url": "https://www.bagosfoundation.org/natural-history-study",
  "contributor": "BAGOS Foundation",
  "disease_id": "disease:SYT1",
  "fragment_path": "data/curated/contributions.json",
  "changed": true,
  "replaced": { "evidence": 0, "nodes": [], "edges": [] },
  "written": { "nodes": ["asset:optional-blood-and-skin-sample-collection", "org:baker-gordon-syndrome-foundation"],
               "edges": ["asset:optional-blood-and-skin-sample-collection|covers|disease:SYT1", "…"] },
  "summary": { "…": "same shape as preview" },
  "items": [ { "index": 0, "name": "…", "status": "duplicate", "node_id": "asset:bagos-natural-history-study", "reason": null } ],
  "rebuild": { "ran": true, "ok": true,
               "build_graph": { "ok": true, "command": "python3 pipeline/build_graph.py", "output": "…nodes, …edges…" },
               "sync_data": { "ok": true, "command": "node web/scripts/sync-data.mjs", "output": "[sync-data] copied ../data/graph.json (…)" } }
}
```

A second identical commit returns `"changed": false` and `"rebuild": { "ran": false, "reason": "nothing changed" }`. After `changed: true`, the app should re-fetch `/data/graph.json` (no-store) to show the new nodes.

### Errors

Every error thrown is a `ContributeError`. `toHttpError(err)` returns `{ status, error: { code, message, …details } }`. Return `Response.json({ error }, { status })`. No error ever contains the Bright Data token or OpenAI credentials.

| code | HTTP | when / extra fields |
|---|---|---|
| `invalid_url` | 400 | not http(s), user:password@, malformed, over 2000 chars |
| `blocked_host` | 400 | localhost or a private network address, including after a redirect or DNS lookup |
| `unknown_disease` | 400 | `diseaseId` is not a disease node; `known_diseases: [ids]` |
| `invalid_items` / `invalid_include` / `invalid_preview` | 400 | malformed manual items, `include` or commit body |
| `not_found` | 404 | HTTP 404/410, Bright Data `x-brd-status-code` 404, or a "Page not found" page |
| `too_large` | 413 | page over 5 MB |
| `unsupported_content` | 415 | a PDF or another non-HTML link |
| `fetch_failed` | 502 | direct fetch blocked or failed, and Bright Data is not configured, failed, or was blocked too (the message says which) |
| `llm_unavailable` | 401 | no ChatGPT sign-in and no `OPENAI_API_KEY`; `llm.action` = "Continue with ChatGPT" |
| `llm_usage_limit` | 429 | ChatGPT plan or app usage limit, rate limit, or quota; `llm.manage_usage_url` |
| `llm_bad_output` | 502 | refusal, invalid JSON, or no `items` list |
| `llm_failed` | 502 | any other OpenAI error; `llm.kind`, `llm.retryable` |
| `preview_expired` | 409 | commit without a cached preview for that URL: preview again |
| `stale_preview` | 409 | the URL was previewed again after this preview: commit the latest |
| `busy` | 409 | another commit has held the lock for over 60 s |
| `nothing_to_commit` | 422 | nothing verified and linked; `summary` |
| `graph_unavailable` / `fragment_invalid` | 500 | `data/graph.json` or `contributions.json` unreadable |
| `rebuild_failed` | 500 | `build_graph.py` failed; the fragment was rolled back; `rebuild.build_graph.output` |
| `internal` | 500 | anything unexpected (`detail`) |

## How to try it

```bash
# tests: no OpenAI, no network, temp files only (19 tests, ~0.4 s)
node --test pipeline/contribute/test.mjs

# fetch a page and see exactly what the model would read (no model call)
node pipeline/contribute/contribute.mjs https://www.bagosfoundation.org/natural-history-study --fetch-only

# preview with the model: ONE call through Sign in with ChatGPT or OPENAI_API_KEY; nothing written to the graph
node pipeline/contribute/contribute.mjs https://www.bagosfoundation.org/natural-history-study --disease disease:SYT1 --by "BAGOS Foundation"

# commit: writes data/curated/contributions.json, rebuilds data/graph.json, copies it into web/public/data/
node pipeline/contribute/contribute.mjs <same url> --disease disease:SYT1 --by "BAGOS Foundation" --commit

# safe trial: commit into another file, no rebuild
node pipeline/contribute/contribute.mjs <url> --commit --fragment /tmp/trial.json --no-rebuild

# without AI: hand-written items, verified the same way (extracted_by "human:<by>")
node pipeline/contribute/contribute.mjs <url> --items items.json --by "Jane Doe"
```

Other flags:

- `--refresh`: re-fetch the page.
- `--reextract`: a new model call.
- `--include 0,2`: commit only those items.
- `--json`: raw output.

Two real pages are already cached for the demo:

- `https://www.bagosfoundation.org/natural-history-study` (direct fetch)
- `https://rarediseases.org/advancing-research/iamrare-patient-registry-platform/`: NORD answers HTTP 403 to a plain fetch, so this one came through Bright Data, which redirected to `/advancing-research/patient-registry`.

Previewing either needs only the one model call.

## Wiring into the web app (to do; `web/` was not touched)

1. **Loader.** Load the module at runtime, outside the bundler, the same way `docs/openai-integration.md` loads `llm.mjs`:
   ```ts
   const mod = await import(/* webpackIgnore: true */ /* turbopackIgnore: true */
     pathToFileURL(path.join(ROOT, "pipeline/contribute/contribute.mjs")).href);
   ```
   `contribute.mjs` itself imports `integrations/openai/llm.mjs` lazily, only when it has to call the model.
2. **Routes** (`runtime = "nodejs"`, `dynamic = "force-dynamic"`). Use the same guards as the AI routes: `liveAIEnabled()` (404 on Vercel, where the file system is read-only anyway), `isLocalRequest(req)`, and a JSON content type. These routes spend Bright Data and OpenAI credit and write files.
   ```ts
   export async function POST(req: Request) {            // /api/contribute/preview
     if (!liveAIEnabled()) return new Response("Not found", { status: 404 });
     if (!isLocalRequest(req) || !(req.headers.get("content-type") ?? "").startsWith("application/json")) return new Response("Forbidden", { status: 403 });
     const { url, diseaseId, contributor } = await req.json().catch(() => ({}));
     const mod = await loadContribute();
     try { return Response.json(await mod.preview({ url, diseaseId }, { contributor })); }
     catch (e) { const { status, error } = mod.toHttpError(e); return Response.json({ error }, { status }); }
   }
   // /api/contribute/commit: same guards; body { preview, contributor?, include? }
   //   -> mod.commit(body.preview, { contributor: body.contributor, include: body.include })
   ```
   Preview takes a few seconds for the fetch plus about 5–30 s for the model call, so show a spinner. Commit runs the graph build (a few seconds).
3. **UI.**
   - A form with the URL, a disease picker (the graph's `disease` nodes; optional) and the contributor's name.
   - The preview list: a status chip per item (New / Already in atlas / Rejected / Needs a disease), the quote with a ✓, the reconciled diseases, "not in the atlas yet" mentions, and each proposed edge with its confidence. Add checkboxes for `include` and a **Add to atlas** button.
   - For `llm_usage_limit`, show **Manage usage**, as in the OpenAI UI states.
   - After commit, reload `/data/graph.json`.
4. **Graph view.**
   - Mark nodes with `attrs.contributed` and edges with `attrs.contributed` as "Community-contributed · not yet reviewed".
   - Their `status` is `unverified` and confidence ≤ 0.5, so draw them lighter.
   - Existing nodes can now carry `attrs.contributed_sources` and extra `sources`. List those as "New source from <by>".
   - Review uses the existing `data/curated/overrides.json` (`edge_patches` with a `review` record).

## Verified, and not

- **Verified:**
  - 19 offline tests: HTML to text; excerpt selection; quote pass and fail; reconciliation; duplicates; manual items; the Bright Data fallback (403, a 200 bot page, a network error, `x-brd-status-code` 404, the redirect header, missing token, Bright Data errors, the token never in results, cache or errors); input and host errors; model error mapping; idempotent and replacing commits on a temp copy; and merging through the real `build_graph.py` on a temp copy of the real fragments.
  - A guard test shows the real `contributions.json` and raw cache are untouched.
  - Live: plain fetch and preview of a real page with hand-written items (no model).
  - Live: 2 Bright Data requests, one to a soft-404 that led to the soft-404 handling, and one to NORD's IAMRARE page (HTTP 403 direct, 200 through Web Unlocker).
- **Not verified:** a live OpenAI call. The ChatGPT Plus usage limit is exhausted, so the prompt and schema have only been exercised with a fake `complete`. The schema follows the strict-mode rules used by `pipeline/openai/extract.mjs`. Run one real preview before the demo.
- **Known limits:**
  - PDFs are not supported.
  - An item's `attrs.url` is the contributed page, not the resource's own homepage.
  - Acronym-only disease names ("BAGOS", "NEDHAHM") don't reconcile, a deliberate choice for precision. The contributor's `diseaseId` covers them.
  - A contributed study's `status` is `"unknown"` until it is checked on ClinicalTrials.gov.
