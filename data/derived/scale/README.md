# Breadth layer: trials, patient organisations and registries for every monogenic disease

Built 2026-10-04 by `pipeline/scale/` (stdlib Python, re-runnable, raw data cached in `data/raw/scale/`). Everything here is **`extracted_by: "automated"`**: each link carries its source record URL, a verbatim quote and the name of the matching rule that produced it. Precision beats recall: rules were tightened until the 30-link spot-checks below came back clean enough to show families, and every remaining error pattern is listed.

## Coverage

Universe: **10309 monogenic diseases** (6611 OMIM + 3698 ORPHA ids; 5088 genes; 9980 mapped to MONDO).

| | diseases (native OMIM/ORPHA ids) |
|---|---|
| >= 1 trial (any rule) | 3181 (30.9%) |
| >= 1 trial matched by disease name/synonym | 1834 (17.8%) |
| >= 1 recruiting/active trial | 2133 (20.7%) |
| >= 1 patient organisation | 1362 (13.2%) |
| >= 1 registry / data platform | 1979 (19.2%) |
| all three | 603 (5.8%) |
| at least one of the three | 4180 (40.5%) |

Distinct MONDO concepts with >= 1 trial / org / registry: 2302 / 1004 / 1389.

Organisations by source (diseases reached): nord 714, globalgenes 553, eurordis 512, serp 126, geneticalliance_uk 86, clinicaltrials.gov 54.
Org nodes: 1475 (3131 org-disease links; 32 reuse an existing `org:` id from `data/graph.json`).
Trials: 81886 unique CT.gov studies fetched; 4088 referenced in the output; 614 genes have a gene-matched study.
Assets: `asset:simons-searchlight` 144, `asset:cords-registry` 1770, `asset:iamrare-the-aps-type-1-apeced-registry` 2, `asset:iamrare-kat6a-kat6b-patient-registry` 4, `asset:iamrare-aspartylglucosaminuria-agu-registry-and-natural-hi` 2, `asset:iamrare-international-bloom-syndrome-registry` 2, plus 21 more IAMRARE registries.

## Files

All ids are native: `OMIM:<n>` / `ORPHA:<n>` (plus `mondo` where `data/derived/global/index.json` maps them) and HGNC symbols. Join to the global index by `mondo` (several native ids can share one MONDO concept, so union them on a MONDO page).

### `universe.json`
`{meta, diseases: {<id>: {id, name, genes[], gene_rules{SYMBOL: rule}, mondo, synonyms[], n_hpo}}, genes: {SYMBOL: [disease ids]}}`
- OMIM rows: HPO `genes_to_disease.txt` `association_type == MENDELIAN`.
- ORPHA rows: the HPO file flattens every Orphanet association to UNKNOWN, so the type is recovered from Orphanet product6 (`en_product6.xml`, cached in `data/raw/scale/orphanet/`); only *Disease-causing germline mutation(s) ...* with status *Assessed* is kept (dropped: 582 OMIM:POLYGENIC, 391 ORPHA:Major susceptibility factor in|Assessed, 289 ORPHA:Candidate gene tested in|Not yet assessed, 268 ORPHA:Role in the phenotype of|Assessed, 261 ORPHA:Part of a fusion gene in|Assessed, ...).

### `trials.json`
```
{ meta,
  studies:  { NCTxxxxxxxx: {title, status, type, phases[], start, enrollment, sponsor, conditions[], url} },
  diseases: { <id>: { name, mondo, genes[],
              by_name: {n, by_type{}, by_status{}, active},   # studies matched by disease name/synonym
              by_gene: {n, by_type{}, by_status{}, active},   # studies matched only via a causal gene symbol
              top: [ {nct, rule, quote, url, via_gene?} ]  ,  # <= 8: name matches, interventional, recruiting, newest first
              ctgov_search } },
  genes:    { SYMBOL: {n, by_type, by_status, active, diseases[], top[]} } }
```
`quote` is the verbatim condition / keyword / brief-title string that matched; `rule` is one of `name_in_conditions|name_in_keywords|name_in_title|gene_in_conditions|gene_in_keywords|gene_in_title`.

### `orgs.json`
```
{ meta, by_disease: {<id>: [org ids]},
  orgs: [ { id: 'org:<slug>', name, url, website, directory_profile, country, nord_member, sources[],
            directory_records: [{source, url, record, profile, quote}], reused_graph_id, extracted_by,
            diseases: [ {id, name, mondo, evidence: {source, url, quote, rule, matched?, context?}, also: [...], n_evidence} ] } ] }
```
### `assets.json`
```
{ meta, by_disease: {<id>: [asset ids]},
  assets: [ { id, name, kind, url, program?, listed_at?, disease_label?, extracted_by,
              diseases: [ {id, name, evidence{url, quote, rule}} | {gene, ids[], names[], evidence{url, quote, rule}} ] } ] }
```
### `spotcheck/`
`<source>.json`: the 30 random links (seed 7) per source that were judged by hand; `verdicts.json` holds the verdicts and the error notes.

## Matching rules and observed precision

Precision = links judged true out of 30 random links (seed 7) read by hand against the quoted record. Samples were drawn after the final rule set unless noted.

| Source | Rule (rule names appear in the data) | Precision |
|---|---|---|
| CT.gov, disease name | `name_in_conditions/keywords/title`: name or synonym, token-normalised, as a whole phrase; longest span wins; no hyphen-glued or gene-context hits ('Ataxia Telangiectasia Mutated'); no digit-free abbreviations, no generic single words, no ambiguous synonyms; non-Orphanet diseases with > 300 hits dropped (breast cancer, Alzheimer, T2D ...) | 29/30 (post-fix sample; first build 27/30) |
| CT.gov, gene symbol | `gene_in_*`: case-sensitive symbol with a gene context (bare symbol, or mutation/variant/related/deficiency... within 3 words); no oncology studies, no common-disease studies, no drug/biomarker/SNP contexts, no acronyms spelled out in the study (HBB = Helping Babies Breathe), symbol stoplist | 27/30 at gene level (first build: 13/30) |
| Orgs from trials | sponsor/collaborator class OTHER + keyword (foundation, association ...), minus universities/hospitals/companies/funders/professional bodies/cancer charities; focused trials only (<= 3 disease concepts); org listed in a directory or name shares a distinctive token with the disease; gene-via links only for gene-named orgs | 29/30 (intermediate rules: 24/30) |
| Global Genes Global Advocacy Alliance | `dir_text_name` (name in org name / mission text), `dir_text_gene` | 27/30 |
| NORD Organizational Database | `dir_disease_field_name` (whole 'Related Rare Diseases' entry = disease name/synonym), `dir_text_*` on the org name | 27/30 |
| EURORDIS members | `dir_disease_field_name` on the 'Disease:' entries (Orphanet names), `dir_text_*` | 28/30 |
| Genetic Alliance UK | `dir_text_name` / `dir_text_gene` on the member name (the directory lists names and websites only) | 26/30 |
| Web search (Bright Data SERP) | `serp_page_mentions_name|gene`: non-news/social/hospital/university/journal/portal/lab/pharma domain, org-like title or domain, fetched page self-describes as an org and contains the name (or the gene in a gene context); quote = that page sentence | 27/30 (first filters: 20/30) |
| Simons Searchlight | `list_item_gene`: gene line on 'Genetic Disorders We Study' -> all diseases of the gene | 30/30 at gene level |
| CoRDS | `list_item_exact_name` (whole list line = name/synonym), `list_item_gene` | 29/30 |
| NORD IAMRARE | per registry: label/registry name -> `list_item_exact_name`, `list_item_name_phrase`, `list_item_gene` | 30/30 |
| Citizen Health | partner list items -> `list_item_exact_name`, `list_item_gene` | 30/30 at gene level |

Gene-level links (any rule containing `gene`) are true for the gene but are credited to every disease of that gene (except somatic, cancer-named and >= 10-gene umbrella entities), so for multi-disease genes the specific disease may be a sibling phenotype (CACNA1C -> Brugada 3 via Simons). The UI must word them as *'mentions / studies <GENE>'*.

## Bright Data usage

Live requests: **659** of the 1,200 budget: SERP 367 ok + 140 failed, Web Unlocker 151 ok + 1 failed (log: `data/raw/scale/brightdata_usage.jsonl`; responses cached in `data/raw/scale/brightdata/`, so re-runs are free). Used for: directory discovery searches, Global Genes (Cloudflare) JSON pages, NORD listing pages, the RARE-X page, the SERP stage and fallback fetches of org pages that block plain requests. EURORDIS, Genetic Alliance UK, Simons Searchlight, CoRDS, IAMRARE, Citizen Health, ClinicalTrials.gov and Orphanet were fetched directly.

## How the UI should use this (disease page for any monogenic disease)

1. Resolve the page's ids: the native OMIM/ORPHA ids of the MONDO concept (global index) -> union `trials.diseases[id]`, `orgs.by_disease[id]`, `assets.by_disease[id]`; dedupe NCT ids and org ids.
2. **Patient groups**: list org name + link (`url`), source badges (`sources`), and on expand the evidence quote with its link. Label every item **'automated match'** and show the rule in plain words: *'listed by NORD for <disease>'*, *'names <GENE> in its name'*, *'collaborator on NCT...'*, *'found by web search; page mentions <disease>'*. Rank directory field matches first, then name, trial, search and gene matches.
3. **Trials**: show `by_name` counts (by status / type) and `top` studies (title, status, phase, sponsor from `studies`), linking `https://clinicaltrials.gov/study/<NCT>`; show gene-matched studies (`via_gene`) in a separate *'Trials mentioning <GENE>'* group; always offer `ctgov_search` as the 'see all' link.
4. **Registries**: list assets with kind + link; for gene-level links say *'<Asset> enrols people with <GENE> variants'*.
5. Never merge these into curated deep-layer edges without review. Show an empty state with the CT.gov / NORD search links when nothing matched.

## Re-run
```
cd pipeline/scale
python3 build_universe.py      # universe.json (+ Orphanet product6 download, once)
python3 fetch_ctgov.py         # ~14.9k CT.gov queries, 4 parallel, resumable (about 25 min cold)
python3 discover.py            # directory URL discovery (Bright Data SERP, cached)
python3 fetch_directories.py   # Global Genes, NORD, EURORDIS, Genetic Alliance UK (cached)
python3 build_trials.py        # trials.json + _trial_orgs.json
python3 build_orgs.py          # orgs.json (directories + trials [+ SERP if present])
python3 serp_orgs.py           # up to 300 Bright Data searches for diseases without an org -> _serp_orgs.json
python3 build_orgs.py          # merge SERP orgs
python3 assets.py              # assets.json
python3 spotcheck.py <source>  # draw a 30-link sample; verdicts are recorded in spotcheck/verdicts.json
python3 write_readme.py
```

## Caveats

- **Trials**: the CT.gov pool is the union of ~14.9k query result pages (100 per query; up to 1,000 when a query kept matching), so counts for very large diseases can be lower bounds. Name matching is literal: numbered OMIM subtypes ('... 96') rarely appear in trial records, so most of them only get gene-level trials. Multi-condition registries (e.g. CoRDS NCT, NBIA, NCL registries) legitimately list hundreds of diseases and appear as matches.
- **Gene-level matches** are true for the gene, not necessarily for the specific sibling disease (see above). Somatic and cancer studies are excluded from gene matching entirely, so hereditary cancer syndromes only get trials by name.
- **Directories describe themselves**: NORD's ODB includes broad bodies (American Heart Association, professional societies) and the occasional registry. They are correct per the directory but are not disease-specific groups. `nord_member` marks NORD members. Global Genes and Genetic Alliance UK have no structured disease field, so their links come from org names and mission text.
- **Web search** precision is the lowest of the sources: the result is a page that mentions the disease on an org-like site, not a verified organisation profile. Treat these as leads.
- **Synonyms** come from MONDO (via the global index) and Orphanet. A wrong synonym upstream becomes a wrong match (guarded by the ambiguity, sub-phrase, hyphen and eponym rules).
- Not done in this pass: NORD org profile pages (websites for NORD-only orgs point to the NORD profile), RARE-X communities (JavaScript-rendered), Orphanet's own patient-org directory (JavaScript-rendered), and non-English directory text.
- Privacy: e-mail addresses are redacted from every stored page; no personal contact details are recorded.
