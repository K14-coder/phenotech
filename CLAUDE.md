# Rare Disease Atlas: handoff for collaborators and their Claude

This is the project for Hack-Nation Challenge 05, "AI Atlas for the World's Rare Diseases". Submission is due 2026-10-04, around 15:00 CEST. The README covers the product; this file covers how to keep working on it.

## Run it

```bash
cd web && npm install && npm run dev      # http://127.0.0.1:3000 (must be 127.0.0.1, not localhost)
```

Live site: https://rare-disease-atlas-five.vercel.app (Vercel project `rare-disease-atlas`). It serves precomputed AI output only.

To deploy, run `npx vercel deploy --prod` from `web/`. It needs `npx vercel login` and access to the project.

## Not in git: recreate locally

- **`.env.local`** (root): copy it from `.env.example`. It holds `BRIGHTDATA_API_TOKEN` (hackathon Bright Data credits; zones `serp_api1` and `web_unlocker1`) and an optional `OPENAI_API_KEY`. Never commit it.
- **`.secrets/`**: Sign in with ChatGPT credentials. Run `node integrations/openai/cli.mjs login` with your own ChatGPT Plus or Pro account; it only works for apps running locally.
- **Large raw API caches** (`data/raw/**/clinvar`, `ctgov`, `web`, `community` and so on) and **`data/raw/downloads/`** (HPO, MONDO, DisMech). The pipelines re-fetch them; see `pipeline/run_all.sh` and `pipeline/derive/run.sh`. You only need them to rebuild data. The app runs from committed files.

## How the data fits together

- **Contract:** `docs/SCHEMA.md` defines node, edge and evidence shapes. Never invent an id, PMID or quote. Every literature quote is string-verified against a stored source.
- **Deep graph:** curated fragments in `data/curated/*.json` are merged by `python3 pipeline/build_graph.py` into `data/graph.json`, then copied into the app by `node web/scripts/sync-data.mjs`. `data/build/report.md` must say "Problems: None".
  - Families: `biology.json` and `community.json` (SNAREopathies, 11 diseases), plus `family_dee.json`, `family_lysosomal.json` and `family_rasopathy.json` (34 diseases).
  - `openai_extracted.json` and `hypotheses.json` are also merged.
  - Human decisions go in `overrides.json`: merges, drops and patches.
- **Breadth:** `data/derived/global/` holds an index of 11,456 diseases, phenotype neighbours, mechanism and pathway data, 225 clusters and DisMech mechanisms. Everything is sharded by `djb2(MONDO id) % 64`; see its README.md. `data/derived/scale/` holds trials, orgs and registries matched automatically at scale.
- **Other derived data:** `data/derived/*.json` holds the variant lookup, look-alikes and counterexamples. `data/curated/modality.json` holds the therapy-approach rules; `impact.json` holds the 10× page content.
- **Expert review:** `docs/review/biochem-review.md` is the review sheet. Tick boxes, then run `python3 pipeline/apply_review.py && python3 pipeline/build_graph.py`.
- **Layer reports:** `docs/agent-reports/*.md` explains how each layer was built and how to re-run it.

## OpenAI

All AI goes through `integrations/openai/llm.mjs`. It tries Sign in with ChatGPT first, then `OPENAI_API_KEY`. Precomputed demo outputs are made with `node web/scripts/precompute-ai.mjs`, which needs the dev server running. They land in `data/ai/`; sync them afterwards.

As of about 02:00 on Oct 4, ChatGPT plan calls fail with "this app's usage limit was reached" (an app-specific cap, so check chatgpt.com/settings/usage → Rare Disease Atlas), and the API key has no credits. **0 of 24 AI drafts are generated yet.** That's the top open item.

## Status (newest first)

**Done and deployed**
- Views: Simple (default), Detailed, Research and Industry (internal ids family/leader/researcher/biotech). See `docs/persona-spec.md`.
- Guided Simple search (`/start`, using `data/derived/global/groups.json`) and the on-device FASTA/VCF checker (`/sequence`).
- `/research` cohort table.
- Global search over 11,456 diseases (plus DisMech extras) and `/d/<MONDO>` pages.
- 4 deep families covering 45 diseases.
- Breadth layer: trials, orgs and registries for 10,309 diseases.
- DisMech: 3,238 mechanism records.
- Population, readiness and recruitment channels.

**Open**
1. Generate the AI drafts: `cd web && node scripts/precompute-ai.mjs` with the dev server running. Then sync, commit and run `npx vercel deploy --prod` from `web/`, which is linked to the `rare-disease-atlas` project.
2. Biochemist review (`docs/review/biochem-review.md`). Items flagged by the DisMech comparison:
   - our SNAP25 loss-of-function edge cites PMID 25381298, which DisMech reads as dominant-negative;
   - possibly missing MONDO xrefs: CDKL5 MONDO:0100039, GLUT1 MONDO:0000188, Gaucher MONDO:0018150, NPC MONDO:0018982 and MLD MONDO:0018868;
   - the SCN1A/SCN2A nodes use the obsolete Dravet id MONDO:0011794 (replacement MONDO:0100135).
3. The STXBP1 enrollment total for Dr. Osei includes Simons Searchlight (multi-disease, 100k), so it reads inflated. Exclude multi-disease registries from the sum.
4. 10× page: add the landscape-assessment baseline from Woan-Yu Lin (RTW Foundation).
5. Videos: see `docs/video-script.md`. Refresh the numbers from the `/method` page.
6. A duplicate Vercel project called "web" was created by mistake. Delete it in the dashboard.

## Conventions

- Commit messages end with a `Co-Authored-By` line. Never commit `.env*` or `.secrets`.
- Researchers are recorded with professional public information only, never personal contact details. No medical advice: treatment evidence is always framed as "to discuss with your clinician".
