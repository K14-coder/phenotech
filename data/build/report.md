# Graph build report

Built 2026-10-04T03:03:29+00:00 from `biology.json`, `community.json`, `contributions.json`, `family_dee.json`, `family_lysosomal.json`, `family_rasopathy.json`, `hypotheses.json`, `mechanism_hierarchy.json`, `mechanistic_links.json`, `openai_extracted.json`.

## Summary

- **1411 nodes, 2953 edges, 17 clusters, 61 gaps**
- Edges with at least one source: **2953/2953**
- Evidence items with a verbatim quote: 1963/4149; quotes string-verified against the stored source: **1963/1963**
- Contested edges (with counter-evidence): 76
- OpenAI cross-check: 68 cited sources re-read and stamped; 111 new supporting and 2 new contradicting sources added (contradictions wait for human review)
- Cited sources where the OpenAI reading disagrees with the curators: 8
- Human-reviewed edges: 0
- Dropped by review: 1; dropped as dangling: 0

## Fragments

| File | Nodes | Edges |
|---|---|---|
| `biology.json` | 201 | 332 |
| `community.json` | 200 | 280 |
| `contributions.json` | 0 | 0 |
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
- mechanism: 32

## Edges by type

- has_phenotype: 812
- studies: 252
- variant_in: 214
- works_on: 193
- has_effect: 143
- serves: 124
- covers: 102
- shares_pathway: 101
- similar_protein_fate: 100
- driven_by: 92
- tests: 85
- participates_in: 78
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

- curated: 1391
- inferred: 685
- observational: 403
- clinical: 274
- experimental: 190
- hypothesis: 10

## Problems

None.
### Attribute conflicts (1)

- node `therapy:4-phenylbutyrate` attrs.modality: kept 'chaperone', ignored 'repurposed_drug'

