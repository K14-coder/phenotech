# Mechanistic similarity layer: agent report

Compares gene-defined disorders on six mechanistic axes and links the atlas diseases that are unusually
alike on each one. It covers the 45 atlas diseases plus a channelopathy panel: every Mendelian ion-channel gene in
the global index, 143 more genes, 188 entities and 17,578 pairs.

| Axis | Data | Score |
|---|---|---|
| Same genes | MONDO/OMIM gene sets of each entity's disease entries | Jaccard |
| Same pathway | MSigDB canonical pathways (Reactome, WikiPathways, KEGG, BioCarta, PID), STRING v12 (atlas genes) | IDF-weighted Jaccard combined with the STRING link |
| Same tissue | HPO symptoms over 20 organ anchors; GTEx v10 expression | Symptom cosine and expression correlation, averaged |
| Mutation type | ClinVar P/LP germline variant types (SNV, deletion, duplication, insertion, indel, inversion, repeat, CNV) | 1 − Jensen–Shannon distance |
| Protein fate | ClinVar consequences (null share) plus curated atlas edges and G2P (fate of protein-altering variants) | Cosine over {absent, degraded, inactive, dominant negative, overactive, accumulates} |
| Structure | AlphaFold v4 models (TM-align), RCSB PDB inventory (3,611 entries), Swiss-Prot sequences, Pfam families and clans, UniProt keywords | Weighted mix |
| Shared compounds (extra) | ChEMBL 36 activities ≤ 10 µM, approved-drug names | Jaccard (not in the combined score) |

## Run

```bash
python3 pipeline/derive/mechsim_fetch.py                 # downloads plus small committed extracts in data/raw/comparison/
python3 pipeline/derive/mechsim_fetch.py --pharmacology  # ChEMBL 36
python3 pipeline/derive/mechsim_structure.py --workers 4 # PDB inventory and all-vs-all TM-align (hours; resumable)
python3 pipeline/derive/mechsim.py                       # scores, links, clusters (~3 min)
python3 pipeline/build_graph.py && node web/scripts/sync-data.mjs
```

The bio REST APIs (UniProt, NCBI, EBI, RCSB) are blocked in the cloud sandbox. Bulk files come from GitHub,
HuggingFace and GCS mirrors (see the docstrings). The RCSB Search and Data API, the STRING network and the ChEMBL
drug names were fetched through a web-fetch tool, and the results are kept in `data/raw/comparison/`.

## Outputs

- `data/derived/mechsim.json`: profiles, every pair's scores, and clusters. The `/mechanisms` page reads it.
- `data/curated/mechanistic_links.json`: computed graph edges between atlas diseases, all `inferred` with
  confidence 0.30–0.49. Types: `shares_gene`, `shares_pathway`, `shares_tissue`, `similar_mutation_spectrum`,
  `similar_protein_fate`, `similar_protein_structure`, `shares_pharmacology` and `mechanistically_similar`
  (the combined score). They are hidden on the atlas map until "Mechanistic links" is switched on, and they
  change neither the layout nor node sizes.

## Caveats

- Protein fate for missense variants rests on sparse curated evidence. Treat it as an estimate.
- AlphaFold DB splits proteins over 2,700 residues; only fragment F1 is compared for them.
- Shared compounds are a hypothesis for experts, never a treatment suggestion.
- The graph's `gene:RIT1` UniProt xref is Q9C0K0 (BCL11B). This layer uses the HPA accession Q92963.
