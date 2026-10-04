# Graph build report

Built 2026-10-04T04:42:03+00:00 from `biology.json`, `community.json`, `contributions.json`, `cross_family.json`, `family_dee.json`, `family_lysosomal.json`, `family_rasopathy.json`, `hypotheses.json`, `mechanism_hierarchy.json`, `mechanistic_links.json`, `openai_extracted.json`.

## Summary

- **1412 nodes, 2977 edges, 17 clusters, 63 gaps**
- Edges with at least one source: **2977/2977**
- Evidence items with a verbatim quote: 2012/4201; quotes string-verified against the stored source: **2012/2012**
- Contested edges (with counter-evidence): 75
- OpenAI cross-check: 73 cited sources re-read and stamped; 108 new supporting and 0 new contradicting sources added (contradictions wait for human review)
- Cited sources where the OpenAI reading disagrees with the curators: 12
- Human-reviewed edges: 0; AI-reviewed edges (not human): 63
- Dropped by review: 1; dropped as dangling: 0

## Fragments

| File | Nodes | Edges |
|---|---|---|
| `biology.json` | 201 | 332 |
| `community.json` | 200 | 280 |
| `contributions.json` | 0 | 0 |
| `cross_family.json` | 1 | 24 |
| `family_dee.json` | 351 | 668 |
| `family_lysosomal.json` | 416 | 653 |
| `family_rasopathy.json` | 248 | 548 |
| `hypotheses.json` | 0 | 10 |
| `mechanism_hierarchy.json` | 0 | 2 |
| `mechanistic_links.json` | 0 | 406 |
| `openai_extracted.json` | 17 | 57 |

## Nodes by type

- phenotype: 509
- variant_group: 214
- researcher: 185
- study: 148
- patient_org: 69
- grant: 63
- asset: 54
- therapy: 47
- disease: 45
- gene: 45
- mechanism: 33

## Edges by type

- has_phenotype: 812
- studies: 252
- variant_in: 214
- works_on: 193
- has_effect: 145
- serves: 124
- covers: 102
- shares_pathway: 101
- participates_in: 100
- similar_protein_fate: 100
- driven_by: 92
- tests: 85
- similar_phenotype: 75
- funds: 72
- shares_tissue: 65
- about: 64
- developed_for: 63
- shares_mechanism: 47
- causes: 45
- similar_mutation_spectrum: 41
- targets: 39
- maintains: 35
- shares_gene: 32
- similar_protein_structure: 32
- mechanistically_similar: 22
- shares_pharmacology: 13
- candidate_for: 10
- part_of: 2

## Edges by evidence level

- curated: 1396
- inferred: 687
- observational: 404
- clinical: 272
- experimental: 208
- hypothesis: 10

## Problems

None.
### Attribute conflicts (1)

- node `therapy:4-phenylbutyrate` attrs.modality: kept 'chaperone', ignored 'repurposed_drug'

