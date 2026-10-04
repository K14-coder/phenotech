# Atlas graph schema (v0.1)

This is the contract between `pipeline/` (which writes data) and `web/` (which reads it).

- Curated fragments live in `data/curated/*.json`. Each has the shape `{ "nodes": [], "edges": [], "clusters": [], "gaps": [] }`.
- A build step merges them into `data/graph.json`, which has the same shape plus `meta`.
- **Never invent an ID, a PMID, a quote or a fact.** If something can't be verified, leave it out or record it as a gap.

## IDs (stable, namespaced)

| Node type | ID format | Example |
|---|---|---|
| gene | `gene:<HGNC symbol>` | `gene:STXBP1` |
| disease | `disease:<HGNC symbol>` (gene-defined umbrella, "GENE-related disorders") | `disease:STXBP1` |
| variant_group | `vg:<SYMBOL>:<slug>` | `vg:STXBP1:truncating` |
| mechanism | `mech:<slug>` | `mech:haploinsufficiency`, `mech:snare-complex-assembly` |
| phenotype | `phenotype:<HPO id>` | `phenotype:HP:0001250` |
| patient_org | `org:<slug>` | `org:stxbp1-foundation` |
| asset | `asset:<slug>` | `asset:stxbp1-natural-history-study` |
| study | `study:<NCT id>` | `study:NCT01234567` |
| publication | `pub:PMID:<pmid>` | `pub:PMID:12345678` |
| researcher | `researcher:<name-slug>--<institution-slug>` | `researcher:jane-doe--ucsf` |
| grant | `grant:<NIH project number>` | `grant:R01NS123456` |
| therapy | `therapy:<slug>` | `therapy:4-phenylbutyrate` |

Disease nodes are gene-defined umbrella entities, because patient communities organize by gene, e.g. "STXBP1-related disorders". The specific clinical entities (MONDO, OMIM and ORPHA IDs) go in `xrefs` and `attrs.subtypes`.

## Node

```ts
{
  id: string,
  type: "disease"|"gene"|"variant_group"|"mechanism"|"phenotype"|"patient_org"|"asset"|"study"|"publication"|"researcher"|"grant"|"therapy",
  label: string,
  synonyms?: string[],                 // for search and synonym resolution, e.g. "Munc18-1", "DEE4", "Baker-Gordon syndrome"
  xrefs?: Record<string, string|string[]>, // {"HGNC":"HGNC:11444","OMIM":["612164"],"MONDO":["MONDO:..."],"ORPHA":["..."]}
  summary?: string,                    // 1–2 plain-language sentences
  attrs?: object,                      // type-specific, see below
  sources?: Evidence[]                 // where this node comes from
}
```

Type-specific `attrs`:

- disease: `{ subtypes?: {name, MONDO?, OMIM?, ORPHA?, inheritance?}[], inheritance?: string, onset?: string, prevalence?: string, approved_treatment?: boolean }`
- gene: `{ protein?: string, function?: string, protein_length_aa?: number, cds_length_bp?: number }`
- variant_group: `{ gene: string, consequence: "truncating"|"missense"|"splice"|"cnv"|"mixed", example_variants?: string[], clinvar_counts?: Record<string, number> }`
- mechanism: `{ kind: "effect"|"process", go_id?: string }` (effect = LoF/haploinsufficiency/dominant-negative/GoF/destabilization; process = biological process)
- phenotype: `{ ic: number, n_diseases?: number }` (information content; higher means more specific/informative)
- patient_org: `{ url: string, country?: string, scope?: string }`
- asset: `{ kind: "registry"|"natural_history_study"|"biobank"|"animal_model"|"cell_model"|"outcome_measure"|"assay"|"trial_design"|"research_network"|"funding_program"|"data_platform", url?: string, access?: string, status?: string }`
- study: `{ status: string, study_type?: "interventional"|"observational", phase?: string, start?: string, sponsor?: string, enrollment?: number, interventions?: string[], conditions?: string[], eligibility_note?: string, url: string }`
- publication: `{ title: string, year: number, journal?: string, url: string, pub_type?: string }`
- researcher: `{ affiliation?: string, url?: string, orcid?: string }`. Professional public info only. **No personal contact details.**
- grant: `{ title: string, pis?: string[], org?: string, fiscal_year?: number, amount?: number, url: string }`
- therapy: `{ modality: "gene_replacement"|"aso"|"small_molecule"|"chaperone"|"gene_editing"|"repurposed_drug"|"other", stage: "idea"|"preclinical"|"clinical"|"approved" }`

## Edge

```ts
{
  id: string,                    // deterministic: `${source}|${type}|${target}`
  source: string, target: string,
  type: RelationType,
  label?: string,                // short verb phrase for hover
  explanation: string,           // 1–2 sentences a family can follow; restates the evidence only
  evidence_level: "clinical"|"curated"|"experimental"|"observational"|"inferred"|"hypothesis",
  status: "supported"|"contested"|"unverified",
  confidence: number,            // 0–1, see rubric
  evidence: Evidence[],          // >= 1 unless evidence_level is "hypothesis"
  counter_evidence?: Evidence[], // contradicting or limiting findings: show them, never hide them
  attrs?: object                 // e.g. {frequency: "HP:0040281"} on has_phenotype
}
```

`RelationType`:

| From → To | type |
|---|---|
| gene → disease | `causes` |
| variant_group → gene | `variant_in` |
| variant_group → mechanism (effect) | `has_effect` |
| gene → mechanism (process) | `participates_in` |
| mechanism → mechanism (GO is_a / part_of / regulates hierarchy) | `part_of` |
| disease → mechanism | `driven_by` |
| disease → phenotype | `has_phenotype` |
| disease → disease (computed) | `shares_mechanism`, `similar_phenotype` |
| disease → disease (computed, six mechanistic axes; `pipeline/derive/mechsim.py`) | `shares_gene`, `shares_pathway`, `shares_tissue`, `similar_mutation_spectrum`, `similar_protein_fate`, `similar_protein_structure`, `shares_pharmacology`, `mechanistically_similar` |
| patient_org → disease | `serves` |
| patient_org / researcher → asset | `maintains` |
| asset → disease | `covers` |
| study → disease | `studies` |
| study → therapy | `tests` |
| therapy → mechanism | `targets` |
| therapy → disease | `developed_for` |
| therapy → disease (computed hypothesis, never fact) | `candidate_for` |
| researcher → gene / disease / mechanism | `works_on` |
| researcher → publication | `authored` |
| grant → researcher | `funds` |
| grant → gene / disease | `about` |

Publications mostly appear as `Evidence` on edges. Only create `publication` nodes when they are needed, e.g. for `authored`.

## Evidence

```ts
{
  source: "HGNC"|"MONDO"|"OMIM"|"Orphanet"|"HPO"|"ClinVar"|"ClinGen"|"GO"|"UniProt"|"PubMed"|"ClinicalTrials.gov"|"NIH RePORTER"|"OpenTargets"|"Monarch"|"Website"|"Atlas"|"Expert",
  ref: string,        // "PMID:12345678", "NCT01234567", "OMIM:612164", "VCV000012345", or a URL
  url: string,        // clickable link to the record
  title?: string,
  year?: number,
  quote?: string,     // VERBATIM text from the fetched source (required for PubMed and Website evidence)
  kind: "database"|"publication"|"trial"|"grant"|"website"|"computed"|"expert",
  study_type?: "clinical_trial"|"case_report"|"case_series"|"cohort"|"functional_study"|"animal_model"|"review"|"database_record",
  supports?: boolean, // default true; false means it contradicts the edge
  extracted_by: "database"|"agent-curation"|`openai:${string}`|`human:${string}`|"computed",
  verified?: boolean, // true once the quote was string-matched against the stored source text, or a human checked it
  retrieved: string,  // YYYY-MM-DD
  cross_checked?: { by: string, agrees: boolean, date: string }, // an independent OpenAI re-reading of this source
  needs_review?: boolean // set on contradictions found only by the OpenAI cross-check; they don't make an edge contested until a human confirms them
}
```

Edges can also carry a human review record (written via `data/curated/overrides.json`):

```ts
review?: { by: string, date: string, verdict: "confirmed"|"corrected"|"rejected", note?: string }
```

## Confidence rubric (v0)

| Confidence | Meaning |
|---|---|
| 0.9–1.0 | Curated database record plus at least 1 publication, or a clinical trial result |
| 0.7–0.89 | At least 2 independent publications, or 1 curated database record |
| 0.5–0.69 | A single publication, or experimental evidence only |
| 0.3–0.49 | Inferred by the atlas from shared features |
| < 0.3 | Hypothesis (e.g. LLM-proposed, untested). Drawn dashed, never presented as fact |

## Top level (`data/graph.json`)

```ts
{
  meta: { version: string, generated_at: string, slice: string, sample?: boolean,
          sources: { name: string, version_or_date: string, url: string }[] },
  nodes: Node[],
  edges: Edge[],
  clusters: { id: string, label: string, basis: "mechanism"|"phenotype"|"pathway",
              members: string[], rationale: string, edge_ids: string[] }[],
  gaps: { id: string, about: string, question: string, what_is_missing: string[],
          searched: string[], how_to_find_out: string }[]
}
```
