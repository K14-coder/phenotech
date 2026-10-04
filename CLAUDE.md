# Phenotech: handoff for collaborators and their Claude

This is Phenotech ("Phenotech: a rare-disease atlas"; named Tasukeru until 2026-10-04), the project for Hack-Nation Challenge 05, "AI Atlas for the World's Rare Diseases". Internal ids, routes, env vars and the Vercel project keep the old rare-disease-atlas names. The README covers the product; this file covers where things stand and how to keep working.

**Start here:** read this file, then `docs/KNOWLEDGE.md` (decisions, benchmark lessons, traps) and `docs/TODO.md` (the prioritized to-do list; keep it updated).

**Always pull before starting and push when done.** Several people and agents work on `main`.

## Run it

```bash
cd web && npm install && npm run dev      # http://127.0.0.1:3000 (must be 127.0.0.1, not localhost)
```

- **Live site:** https://rare-disease-atlas-five.vercel.app (Vercel project `rare-disease-atlas`; `web/` is linked to it).
- **Deploy:** `npx vercel deploy --prod` from `web/`, after `npm run build` passes.
- **Data:** run `node web/scripts/sync-data.mjs` after changing anything in `data/`. `predev` and `prebuild` also run it.

## Not in git: recreate locally

- **Root `.env.local`** (copy from `.env.example`):
  - `BRIGHTDATA_API_TOKEN` (zones `serp_api1` and `web_unlocker1`);
  - optionally `OPENAI_API_KEY`;
  - `ADMIN_TOKEN` (moderation page `/admin`).
- **`web/.env.local`:** created by `vercel link` / `vercel env pull`. It holds the Vercel env vars, including the Upstash KV ones. Locally the app still uses a JSON file store in `web/.data/` unless `STORE=redis`.
- **`.secrets/`:** your own Sign in with ChatGPT login (`node integrations/openai/cli.mjs login`, ChatGPT Plus or Pro; works only for locally run apps).
- **Large raw API caches and `data/raw/downloads/`** (HPO, MONDO, GO, DisMech clone, UniProt and HPA downloads). The pipelines re-fetch them; the app runs from committed files.

## Vercel env vars (production)

| Status | Variables |
|---|---|
| Set | `KV_REST_API_URL`, `KV_REST_API_TOKEN` (Upstash, accounts and queue), `SESSION_SECRET`, `ADMIN_TOKEN` |
| Needed for email | `RESEND_API_KEY`, `EMAIL_FROM` (Resend; until a domain is verified it only delivers to the account owner), `EMAIL_DOMAIN_VERIFIED=1` once verified |
| Needed for crons | `CRON_SECRET` (daily digest and live trial/grant alerts, queue sweep) |
| Optional | `NCBI_API_KEY` (faster PubMed for the research queue), `QUEUE_MAX_ROUNDS`, `APP_URL` |

## What we collect (sources)

Every literature quote is string-verified against a stored source. Every automated match keeps its source URL, a verbatim snippet and the matching rule.

| Layer | Sources | Where |
|---|---|---|
| Genes and diseases | HGNC, UniProt, Ensembl (MANE Select CDS and exons, GRCh37/38), MONDO, OMIM ids, Orphanet/Orphadata, Monarch, Open Targets | `pipeline/biology`, `pipeline/families/*`, `pipeline/derive` |
| Symptoms | HPO annotations (IC-weighted over about 12.9k diseases) | `hpo.py`, `global_index.py` |
| Variants | Full ClinVar `variant_summary` (387k P/LP, 13,292 genes), gnomAD v4.1 constraint, AlphaMissense gene means | `clinvar.py`, `data/derived/variants.json`, `variant_positions.json` |
| Mechanisms | PubMed abstracts (curated, quote-verified), GO (QuickGO, go-basic), Reactome, Gene2Phenotype, ClinGen, DisMech (Monarch, 3,238 records, 143k snippets) | families, `data/derived/global/mechanism`, `dismech/` |
| Protein structure and families | AlphaFold all-vs-all TM-align (17,578 pairs), InterPro, Pfam, PANTHER | `data/derived/mechsim.json` (colleague), `data/derived/features/` |
| Tissue | Human Protein Atlas tissue specificity, HPO organ systems | `data/derived/features/` |
| Trials | ClinicalTrials.gov API v2 (curated for deep diseases; about 82k studies scanned at scale); central contacts for recruiting studies | community and families, `data/derived/scale/trials.json`, `data/derived/contacts/` |
| Funding and researchers | NIH RePORTER, PubMed senior authors (professional information only) | community and families |
| Patient groups and registries | Org websites (verified quotes), NORD, Global Genes, EURORDIS, Genetic Alliance UK directories, Bright Data search, Simons Searchlight, CoRDS, IAMRARE, Citizen Health; published org contact emails and phones | `data/derived/scale/`, `data/derived/contacts/` |
| Population | Orphanet prevalence (product 9) | `data/derived/population/` |
| Genetic testing options | Lab raw-data pages, GDPR/HIPAA texts, NSGC, NHS, UDN and others (125 verified quotes) | `data/curated/testing_options.json` |
| AI | OpenAI gpt-6-astra via Sign in with ChatGPT: claim extraction and cross-check on the SNAREopathies (88% agreement), 66 precomputed drafts. Claude agent reading of the other families' cited abstracts (`READER=claude`, 256 abstracts, 96% agreement; candidate edges in `data/build/claude_candidate_edges.json` wait for review) and 42 outreach drafts (`web/scripts/agent-ai.mjs`). 108 drafts in `data/ai/` | `pipeline/openai`, `web/scripts/precompute-ai.mjs`, `web/scripts/agent-ai.mjs` |
| Community research | Volunteers' OpenAI or Claude extractions via the research queue, server-verified | `/research-queue`, `pipeline/crowd/export.mjs` → `data/curated/crowd.json` (review before merging) |

**Refresh cadence:**
- The static layers update when a pipeline is re-run and the site is redeployed.
- A daily cron does live ClinicalTrials.gov and NIH RePORTER checks for followed diseases, plus the digest emails. This is being finished now (see Open).

## How the data fits together

- **Contract:** `docs/SCHEMA.md`.
- **Merge:** `python3 pipeline/build_graph.py` merges `data/curated/*.json` into `data/graph.json`. `data/build/report.md` must say "Problems: None".
- **Families:** `biology.json` and `community.json` (SNAREopathies, 11), plus `family_dee.json`, `family_lysosomal.json` and `family_rasopathy.json` (34).
- **Also merged:** `openai_extracted.json`, `hypotheses.json`, `mechanism_hierarchy.json`, `contributions.json`, the colleague's mechsim edges, and `overrides.json` (human decisions).
- **Breadth:** `data/derived/global/` has 11,456 diseases sharded by `djb2(MONDO) % 64` (see its README), plus `groups.json`, `mechanism/`, `clusters.json`, `dismech/` and `dismech_evidence/` (the latter isn't deployed).
- **Evaluation:** `pipeline/eval/` (leave-one-out therapy transfer). Phenotype + specific mechanism gives top-5 recall 0.73 and MRR 0.49. Richer features (tissue, families, pathways, mutation type) did not beat it under nested cross-validation. See `docs/agent-reports/eval.md`.
- **Layer reports:** `docs/agent-reports/*.md`.

## Status

**Done and deployed**
- **Views:** Simple (default), Detailed, Research and Industry.
- **Search and pages:** guided search; "Which disease are you looking for?"; `/help` for no-result searches; `/d/<MONDO>` pages.
- **Tools:** the on-device FASTA/VCF checker (`/sequence`) and the DNA-file request flow (`/sequence/request`).
- **Data:** 45 deep diseases in 4 families; breadth for 10,309 diseases; DisMech; population, readiness and channels; `/research` cohort table; `/mechanisms` (colleague).
- **AI:** 58 drafts.
- **Community:** accounts, onboarding, inbox, researcher announcements with moderation, relayed contact, export and delete. Email code is in, but needs the Resend env vars.
- **Research queue:** OpenAI or Claude, BYOK in the browser or the local worker (`/worker/rare-atlas-worker.mjs`).

**Also done (Oct 4)**
- Live daily ClinicalTrials.gov and NIH RePORTER alerts for followed diseases (crons in `web/vercel.json`; `CRON_SECRET` is set).
- Published contacts: 210 orgs and 1,463 recruiting-trial central contacts (`data/derived/contacts/`, privacy-validated).
- Full ClinVar (387k P/LP in 13,292 genes) for the genome-wide VCF and variant lookup; gnomAD constraint and AlphaMissense as explanatory gene factors.
- PrimeKG external benchmark (1,300 cases): symptoms carry the cross-gene signal. The global similar lists use phenotype + 0.5·genes + 0.5·pathway (`data/derived/global/similar/`). See `docs/agent-reports/ingest.md`.

**Open**
1. Resend: run `npx vercel integration add resend` (accept the terms), set `EMAIL_FROM`, decide on a domain, and set `CRON_SECRET`.
2. Biochemist review (`docs/review/biochem-review.md`). Also check:
   - the SNAP25 loss-of-function edge (PMID 25381298, read by DisMech as dominant-negative);
   - the CBL and SCN8A mechanism classes, which disagree with G2P;
   - possibly missing MONDO xrefs (CDKL5 MONDO:0100039, GLUT1 MONDO:0000188, Gaucher MONDO:0018150, NPC MONDO:0018982, MLD MONDO:0018868);
   - the obsolete Dravet id MONDO:0011794 → MONDO:0100135.
3. ~~A curated LZTR1/RIT1 → MAPK link~~: done in `data/curated/cross_family.json` (29/45 diseases now cross-linked).
4. ~~STXBP1 enrollment total includes Simons Searchlight~~: done; multi-disease registries are listed as "not counted".
5. Before merging `data/curated/crowd.json`, review it: crowd diseases become `disease:<GENE>` nodes.
6. Videos: the script in `docs/video-script.md` is refreshed (Oct 4); re-check the ⟨…⟩ numbers on `/method` right before recording.
7. Delete the duplicate Vercel project "web".

## Conventions

- Commit messages end with a `Co-Authored-By` line. Never commit `.env*`, `.secrets` or `web/.data`.
- Researchers: professional public information only. Never personal contact details for individuals. Contacts shown are organisations' published contacts and ClinicalTrials.gov central contacts for recruiting studies.
- No medical advice: treatment evidence is always "to discuss with your clinician".
