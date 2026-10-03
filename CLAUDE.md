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

As of 00:50: the Plus usage limit was hit and the API key has no credits. **0 of 21 AI drafts are generated yet.** That's the top open item.

## Open items (newest first)

1. Profile-specific UI: "Devon" (newly diagnosed) is a simple, reassuring default; researchers get detail and recruitment and contact tools. In progress.
2. Global search for all diseases, outside-the-map pages and DisMech/scale data on disease pages. In progress.
3. Generate the 21 AI drafts once OpenAI access works, then sync, commit and redeploy.
4. Biochemist review of the review sheet.
5. 10× page: add the landscape-assessment baseline from Woan-Yu Lin (RTW Foundation) once we have her figure.
6. Videos: see `docs/video-script.md`.

## Conventions

- Commit messages end with a `Co-Authored-By` line. Never commit `.env*` or `.secrets`.
- Researchers are recorded with professional public information only, never personal contact details. No medical advice: treatment evidence is always framed as "to discuss with your clinician".
