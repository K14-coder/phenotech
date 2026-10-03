# Population and trial-readiness layer

This layer answers three questions a researcher asks about a disease:

- How many people live with it, and where?
- How ready is its community for a clinical trial?
- Which organisations could help reach patients?

It is built by `python3 pipeline/derive/population.py` (stdlib only, about 3 s). Add `--fetch` to download the Orphanet file again. Inputs:

- `data/raw/downloads/en_product9_prev.xml`: Orphadata product 9, Epidemiology. Fetched from https://www.orphadata.com/data/xml/en_product9_prev.xml (Orphadata date 2026-06-23, CC-BY-4.0, 16 MB, gitignored).
- `data/graph.json`.
- `data/derived/global/index.json`.
- `data/derived/scale/{orgs,assets,trials}.json`.
- Stored organisation pages under `data/raw/**/web/`.
- The cached ClinicalTrials.gov pool `data/raw/scale/ctgov/`, used only for each trial's sponsor class.

| File | Size | Content |
|---|---|---|
| `prevalence.json` | 0.3 MB | meta, `deep` (45 umbrella diseases), `mondo` (index row id → ORPHA codes with prevalence) |
| `prevalence_orpha.json` | 5.7 MB | all 6,728 ORPHA codes: records and estimate. Load lazily. |
| `readiness.json` | 0.1 MB | 8-component readiness profile for the 45 deep diseases |
| `channels.json` | 0.4 MB | 362 recruitment channels for the 45 deep diseases, plus a `by_disease` index |

## Coverage

- **Deep diseases:**
  - 33 of 45 have Orphanet prevalence records on their own ORPHA entities.
  - 40 of 45 have records when related clinical entities are counted too.
  - 25 of 45 get an estimated-people range.
  - The diseases with no own records are BRAF, CBL, NSF, RAF1, RIT1, SHOC2, SNAP25, SOS1, STX1A, SYT2, UNC13A and VAMP2. SNAP25, SYT2 and UNC13A map to ORPHA:716903, which has no epidemiology record.
- **All MONDO rows in the global index:** 5,423 of 11,334 have at least one Orphanet record, and 4,097 have an estimated-people range.
- **Channels:** 43 of 45 deep diseases have at least one. NSF and STX1A have none.

## `prevalence_orpha.json` → `orpha[<code>]`

```json
{"orpha":"636","name":"Neurofibromatosis type 1","group":"Disorder","url":"https://www.orpha.net/en/disease/detail/636",
 "records":[{"type":"Point prevalence","qualification":"Value and class","class":"1-5 / 10 000","area":"Europe",
             "validation":"Validated","pmids":["2511318","6807042","10991696","20082463"],
             "source":"10991696[PMID]_20082463[PMID]_2511318[PMID]_6807042[PMID]_ORPHANET","mean_per_100k":21.3}, ...],
 "estimate":{"basis":"point prevalence",
             "worldwide":{"low":810000,"high":4000000,"classes":["1-5 / 10 000"],"rate_from":"Europe","from_mean_value":1700000},
             "europe":{...},"us":{"low":34000,"high":170000,...,"from_mean_value":71000}}}
```

| Field | Meaning |
|---|---|
| `type` | Point prevalence, Prevalence at birth, Lifetime Prevalence, Annual incidence, or Cases/families. |
| `class` | Orphanet prevalence class. Absent for case counts. |
| `mean_per_100k` | Orphanet `ValMoy`: the published mean value per 100,000. Only present when one was given; Orphanet writes 0.0 for "not given". |
| `n_reported` | For Cases/families records: the number of cases or families reported in the literature. |
| `area` | Orphanet's geographic area, e.g. Worldwide, Europe, or a single country. |
| `validation` | Orphanet's validation status. |
| `pmids` | Parsed from `source`. `source` keeps the raw string, e.g. `[EXPERT]` or `ORPHANET`. |

## Estimated people affected (rough, NOT a count)

The estimate is `people = class bounds × population`. Populations are worldwide 8.1 billion, Europe 750 million and US 335 million.

| Class | Rate bounds per person |
|---|---|
| `<1 / 1 000 000` | 0 to 1e-6, so the range reads "fewer than ~N" |
| `1-9 / 1 000 000` | 1e-6 to 9e-6 |
| `1-9 / 100 000` | 1e-5 to 9e-5 |
| `1-5 / 10 000` | 1e-4 to 5e-4 |
| `6-9 / 10 000` | 6e-4 to 9e-4 |
| `>1 / 1000` | 1e-3 with no upper bound, so the range reads "more than ~N" |

How the estimate is chosen:

- **Basis:** point prevalence is used first. When a disease has none, prevalence at birth stands in as a proxy (`basis: "prevalence at birth (proxy)"`). The proxy overestimates the number of living patients when survival is reduced.
- **Validated records:** if any validated records exist, only they are used.
- **Records excluded:** classes Unknown and Not yet documented, annual incidence, and case counts are never turned into people.
- **Rate source:** each area uses its own record when one exists. Otherwise it falls back in this order:
  - worldwide: Worldwide → Europe;
  - Europe: Europe → Worldwide;
  - US: United States → Worldwide → Europe.

  `rate_from` says which record was used.
- **Conflicting classes:** when one area has several classes, the range spans all of them.
- **`from_mean_value`:** the same calculation using the mean of `mean_per_100k`, when available.
- **Rounding:** all numbers are rounded to 2 significant figures.

**Deep umbrella aggregate.** This is `prevalence.json` → `deep[<disease>].estimated_people`.

- **Which entities are added:** only **gene-specific** ORPHA entities. That means the code is on the graph node's xrefs or subtypes **and** the global index links it to at most 2 genes.
- **How they are combined:** `low` is the largest single low. `high` is the sum of highs, which is a ceiling because entities can overlap.
- **Entities shown but never added:** `shared_clinical_entity` (e.g. Lennox-Gastaut and Dravet syndrome under SCN1A, each linked to 7 genes) and `related_clinical_entity` (any index row naming the gene, e.g. Noonan syndrome for PTPN11). Their prevalence includes patients with other genes. Each entity carries `scope`, `genes` and `in_aggregate`.

Read these with care:

- **SCN1A gets no headline range.** Dravet syndrome is a shared entity, so it is not added.
- **Somatic or mostly non-genetic entities can inflate a range.** Some xref'd entities are like this, e.g. KRAS ↔ ORPHA:46724 brain arteriovenous malformation, or MAP2K1 ↔ melorheostosis. Check `entities` before quoting a number.

## `readiness.json` → `diseases[<disease>]`

Each disease has 8 components, each `{status: yes|no|partial, edges: [graph edge ids], note}`:

- `registry_or_natural_history`
- `outcome_measures_or_consortium`
- `animal_or_cell_model`
- `interventional_trial` (adds `highest_phase`, `highest_phase_trial` and `latest_trial`)
- `approved_therapy`
- `patient_organisation`
- `known_mechanism`
- `research_groups_and_grants`

The exact rules are in `meta.rules`. `tally` counts yes as 1 and partial as 0.5, out of 8. It describes what the atlas has recorded, not a validated score, and **"no" means "not in the graph"**. The data comes from `graph.json` only. `estimated_people_worldwide` is copied from `prevalence.json` for convenience.

## `channels.json`

```json
{"id":"org:stxbp1-foundation","type":"patient_org","name":"STXBP1 Foundation","url":"https://www.stxbp1disorders.org/",
 "how_to_reach":"research page: https://www.stxbp1disorders.org/clinicaltrialsandresearch; ...",
 "reach_links":[{"kind":"research","url":"...","link_text":"Clinical Trials and Research","seen_on":"data/raw/community/web/stxbp1-foundation-home.html"}],
 "layer":"deep","diseases":["disease:STXBP1"],"evidence":[{"edge":"org:stxbp1-foundation|serves|disease:STXBP1"}]}
```

`type` is one of: `registry`, `natural_history_study`, `data_platform`, `biobank`, `research_network`, `consortium`, `patient_org` or `recruiting_trial`. A trial counts as recruiting when its status is RECRUITING, NOT_YET_RECRUITING or ENROLLING_BY_INVITATION.

Evidence:

- Deep items cite graph edge ids (`{edge}`).
- Breadth items cite `{scale: <file>, rule, quote, ...}`. They are automated matches from `data/derived/scale/` and are labelled `layer: "scale (automated match)"`.

How to reach each type:

- **Assets:** the graph's `access` text, plus the organisation that runs the asset.
- **Organisations:** research, registry, participate or contact pages. They come from the stored page itself, or from same-domain links on it. Otherwise the homepage or directory profile is given.
- **Trials:** the sponsor plus the ClinicalTrials.gov record.

Privacy:

- Only professional and organisational channels are included.
- `mailto:` and `tel:` links, and any link containing `@`, are skipped.
- Trial contacts are not copied.
- When a trial's sponsor is an individual, the name is withheld and the text says "Investigator-sponsored study". This applies to sponsor class INDIVIDUAL, and to non-industry sponsors whose name looks like a person's.

## Caveats

- Orphanet prevalence classes are coarse. Many records are for a single country, and Orphanet itself flags estimates for ultra-rare conditions as uncertain.
- The MONDO mapping uses the global index's `orpha` column, so an ORPHA group code can attach to a broader row.
- Readiness and channels describe what the atlas recorded; they are not an exhaustive search. Breadth-layer matches are automatic and unreviewed.
