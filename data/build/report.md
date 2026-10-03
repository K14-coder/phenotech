# Graph build report

Built 2026-10-03T19:12:52+00:00 from `biology.json`, `community.json`, `hypotheses.json`, `openai_extracted.json`.

## Summary

- **397 nodes, 671 edges, 5 clusters, 35 gaps**
- Edges with at least one source: **671/671**
- Evidence items with a verbatim quote: 705/1022; quotes string-verified against the stored source: **705/705**
- Contested edges (with counter-evidence): 31
- OpenAI cross-check: 68 cited sources re-read and stamped; 111 new supporting and 2 new contradicting sources added (contradictions wait for human review)
- Cited sources where the OpenAI reading disagrees with the curators: 8
- Human-reviewed edges: 0
- Dropped by review: 1; dropped as dangling: 0

## Fragments

| File | Nodes | Edges |
|---|---|---|
| `biology.json` | 201 | 332 |
| `community.json` | 200 | 280 |
| `hypotheses.json` | 0 | 5 |
| `openai_extracted.json` | 17 | 57 |

## Nodes by type

- phenotype: 117
- researcher: 114
- variant_group: 43
- grant: 24
- patient_org: 20
- asset: 19
- study: 18
- disease: 11
- gene: 11
- mechanism: 11
- therapy: 9

## Edges by type

- has_phenotype: 192
- works_on: 121
- variant_in: 43
- has_effect: 40
- driven_by: 31
- funds: 31
- covers: 27
- participates_in: 25
- about: 25
- studies: 25
- serves: 23
- maintains: 20
- shares_mechanism: 14
- causes: 11
- developed_for: 11
- similar_phenotype: 11
- targets: 10
- tests: 6
- candidate_for: 5

## Edges by evidence level

- curated: 308
- observational: 216
- experimental: 79
- inferred: 37
- clinical: 26
- hypothesis: 5

## Problems

None.
### Attribute conflicts (1)

- node `therapy:4-phenylbutyrate` attrs.modality: kept 'chaperone', ignored 'repurposed_drug'

