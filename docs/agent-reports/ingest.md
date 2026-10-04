# Ingest report: full ClinVar, gnomAD constraint, AlphaMissense and PrimeKG, with an external benchmark of the factors

**Question.** We can strengthen the atlas factors:
- genes involved;
- signalling pathway;
- tissue;
- symptoms;
- protein structure and families;
- mutation type;
- molecular consequence.

Which of them actually help recognise that a drug for one rare disease suits another? This report measures that on an external benchmark, not on our own curated cases.

```bash
python3 pipeline/ingest/clinvar_full.py && python3 pipeline/ingest/constraint_alphamissense.py
python3 pipeline/ingest/primekg_fetch.py && python3 pipeline/ingest/primekg_benchmark.py && python3 pipeline/ingest/primekg_benchmark.py --offlabel
uv run --with numpy --with scipy python3 pipeline/eval/primekg_eval.py            # ~10 s
uv run --with numpy --with scipy python3 pipeline/eval/primekg_eval.py --offlabel
```

**Where things were written.** Code is in `pipeline/ingest/` (5 scripts) and `pipeline/eval/primekg_eval.py`, which is new. No existing file was edited: the `transfer_score.py` / `transfer_eval.py` / `feature_eval.py` APIs and outputs are unchanged. Data is in `data/derived/ingest/`; the schemas, licences and sizes are in its `README.md`. Raw files are in `data/raw/downloads/` (gitignored). No OpenAI was used.

**GeneCards (genecards.org) is not used.** It blocks automated access, and reuse outside academia needs a licence. Every resource here is open: public domain, CC0, CC BY 4.0 or MIT.

## 1. Datasets ingested

| Dataset | Content | Size |
|---|---|---|
| `clinvar/<djb2(symbol)%64>.json` | **387,722 P/LP variants in 13,292 genes** from the full ClinVar `variant_summary` (Last-Modified 2026-09-29). Each record has: VariationID, transcript + HGVS, protein change, type, derived molecular consequence, class, review stars, GRCh38 and GRCh37 `chr:pos:ref:alt`, and MONDO/MedGen/OMIM phenotype ids. 352k variants have an exact VCF key on each assembly. | 64 shards, **44.6 MB raw / 10.8 MB gzipped**, max 1.47 MB (TTN's bucket), min 0.28 MB |
| `clinvar_gene_spectrum.json` | Per-gene counts and fractions of nonsense, frameshift, splice, missense, in-frame, CNV and other, for all 13,292 genes, plus fine-grained codes | 2.06 MB (0.26 MB gz) |
| `constraint.json` | gnomAD v4.1: pLI, LOEUF, missense Z, o/e. The MANE Select transcript is used where available. Symbols are re-keyed to current HGNC (GBA → GBA1). 18,140 genes. | 1.11 MB (0.34 MB gz) |
| `alphamissense_gene.json` | AlphaMissense mean pathogenicity per gene, 17,297 genes. Licence: CC BY 4.0 per the Zenodo record; the file header still carries the 2023 NC-SA wording (see README). The 643 MB per-variant file is documented as a next step. | 0.74 MB (0.19 MB gz) |
| `primekg_benchmark.json` | PrimeKG (MIT code, CC0 data) drug→disease edges mapped to MONDO, with leave-one-out cases | 224 KB |

**For the web VCF checker.** It can now check any gene, not only the 45. It loads `clinvar/<djb2(GENE)%64>.json`, using the same djb2 as the global index, and matches `grch38` or `grch37` exactly. These shards are not yet copied by `web/scripts/sync-data.mjs`, which copies only top-level `data/derived/*.json`. One `copyTree` line is needed.

## 2. The PrimeKG benchmark

**Mapping.** PrimeKG disease nodes are MONDO terms. A `MONDO_grouped` node is an underscore-joined list of MONDO numbers. We map a node by exact MONDO id to our global index. A node is eligible if one of its index rows has a gene (OMIM Mendelian or Orphanet), i.e. it is monogenic or rare.
- 711 of the 2,054 PrimeKG disease nodes that have drug edges map to the index; 461 are eligible.
- A child-term fallback was tried and switched off. It mapped 1,032 nodes, but it chained generic parents such as "dermatitis" and "injury" into unrelated units. It also put the same disease in the pool twice under two names (gastric cancer and gastric neoplasm), which made the task trivially easy.

**Cases.** A drug enters the benchmark if it has `indication` edges to two or more eligible diseases.
- That gives **257 drugs, a candidate pool of 256 diseases and 1,300 leave-one-out cases**: 23 times as many cases as our 56-case curated benchmark, with a 6× larger candidate pool.
- The extended variant adds `off-label use` as positives: 314 drugs, 305 diseases and 1,756 cases.
- These labels are external. They come from DrugBank and DrugCentral through PrimeKG, so nothing in them was curated by us.

**Protocol.** It is the same as eval.md sections 2 and 5:
- Hide one (drug, disease) pair. Use the drug's other indicated diseases as context.
- Rank the whole pool minus the context and the drug's off-label diseases (filtered ranking).
- A feature's score for a candidate is its maximum similarity to any context disease, normalised per case.
- Ties count at their expected value.

**Bootstrap and folds are over drug groups.** Drugs whose indication lists overlap with Jaccard ≥ 0.5 form one group. For example, the eight systemic corticosteroids share about 40 indications and form one group. There are 95 groups for 257 drugs. Correlated drugs never fall on both sides of a split. The intervals are therefore honest, and wide.

**Combinations** were tuned by nested 5-fold CV over drug groups:
- `grid`: an exhaustive search over every {0,1} subset of the 12 features (4,095 settings).
- `logit`: a non-negative conditional-logit model.
- `anchored`: phenotype at weight 1, plus at most two other features at 0.25 or 0.5. It mirrors eval.md and is likewise labelled post hoc: it was added after the first run.

**Features.** Each covers one of the user's factors. Coverage is out of the 256 pool diseases.

| Feature | Factor | Data | Coverage |
|---|---|---|---|
| phenotype | symptoms | HPO IC-weighted cosine, ancestor-propagated (`phenotype.hpoa`, as in the global index) | 208 |
| genes | genes involved | Jaccard of the causal genes | 256 |
| mechanism | molecular consequence | IDF cosine of G2P/ClinGen classes (`global/mechanism`) + gnomAD tokens (LoF-intolerant, LoF-tolerant, missense-constrained) | 226 |
| constraint | molecular consequence | gnomAD pLI / LOEUF / missense Z, continuous similarity | 235 |
| pathway_mid | signalling pathway | Reactome mid-level (depth-3) pathways from `global/mechanism` | 191 |
| pathway_full | signalling pathway | Reactome lowest level + ancestors (NCBI2Reactome) | 246 |
| gene_family | protein families | PANTHER + InterPro Family (`features/gene_families.json`) | 255 |
| protein_domain | protein structure | InterPro domains / superfamilies + Pfam | 254 |
| tissue | tissue | HPA tissue-enriched nTPM (`features/gene_tissue.json`) | 201 |
| mutation_spectrum | mutation type | full-ClinVar spectrum, 1 − Jensen–Shannon divergence | 248 |
| alphamissense | protein structure / consequence | 1 − difference in gene mean pathogenicity | 237 |
| structure_tm | protein structure | AlphaFold TM-align from `data/derived/mechsim.json`. It covers only about 220 genes (channels and atlas genes), so it is mostly blank here. | **52** |

## 3. Results (primary benchmark, n = 1,300 cases, 256 candidates)

95% intervals come from the drug-group bootstrap (2,000 draws). The Δ column is the paired difference in MRR against phenotype alone. The last two columns are:
- **No-shared-gene**: MRR on the 644 cases where the held-out disease shares no gene with any context disease. This is the real cross-gene transfer test.
- **Extended**: MRR on the indication + off-label benchmark (n = 1,756).

| Scorer | R@1 | R@3 | R@5 [CI] | R@10 | MRR [CI] | Δ MRR vs phenotype [CI] | No-shared-gene MRR | Extended MRR |
|---|---|---|---|---|---|---|---|---|
| random | 0.00 | 0.01 | 0.02 | 0.04 | 0.025 | −0.30 | 0.025 | 0.021 |
| **phenotype (symptoms)** | 0.24 | 0.37 | 0.44 [0.27–0.61] | 0.50 | **0.324 [0.19–0.51]** | — | **0.268** | 0.274 |
| genes involved | 0.23 | 0.37 | 0.40 [0.28–0.52] | 0.46 | 0.314 [0.21–0.42] | −0.009 [−0.16, +0.15] | 0.015 | 0.267 |
| pathway_full (Reactome, full) | 0.22 | 0.34 | 0.39 [0.27–0.50] | 0.43 | 0.306 [0.22–0.40] | −0.017 [−0.17, +0.13] | 0.065 | 0.259 |
| gene_family | 0.18 | 0.33 | 0.35 [0.25–0.45] | 0.44 | 0.274 [0.19–0.38] | −0.049 [−0.18, +0.07] | 0.044 | 0.232 |
| pathway_mid (Reactome, depth 3) | 0.20 | 0.25 | 0.31 [0.17–0.45] | 0.33 | 0.248 [0.13–0.36] | −0.076 [−0.25, +0.11] | 0.055 | 0.223 |
| protein_domain | 0.13 | 0.30 | 0.36 [0.28–0.46] | 0.43 | 0.243 [0.18–0.32] | −0.081 [−0.28, +0.08] | 0.048 | 0.217 |
| constraint (gnomAD) | 0.11 | 0.17 | 0.21 [0.14–0.28] | 0.24 | 0.161 [0.11–0.22] | −0.163 [−0.31, −0.04] | 0.020 | 0.146 |
| tissue (HPA) | 0.09 | 0.11 | 0.15 [0.06–0.27] | 0.20 | 0.130 [0.06–0.22] | −0.193 [−0.42, −0.00] | 0.028 | 0.096 |
| mutation_spectrum (ClinVar) | 0.08 | 0.10 | 0.11 [0.06–0.21] | 0.23 | 0.118 [0.07–0.20] | −0.205 [−0.39, −0.07] | 0.037 | 0.111 |
| alphamissense | 0.03 | 0.04 | 0.06 [0.03–0.13] | 0.08 | 0.054 [0.03–0.10] | −0.269 | 0.028 | 0.057 |
| mechanism class (G2P/ClinGen + constraint tokens) | 0.01 | 0.02 | 0.04 [0.03–0.05] | 0.08 | 0.040 [0.03–0.05] | −0.284 | 0.024 | 0.033 |
| structure_tm (AlphaFold) | 0.01 | 0.02 | 0.03 | 0.06 | 0.035 | −0.288 | 0.022 | 0.036 |
| equal weight, all 12 | 0.26 | 0.38 | 0.43 [0.32–0.55] | 0.48 | 0.340 [0.23–0.45] | +0.016 [−0.14, +0.19] | 0.065 | 0.296 |
| nested grid | | | 0.39 [0.30–0.53] | | 0.293 [0.21–0.42] | −0.030 [−0.14, +0.06] | 0.080 | 0.257 |
| nested logit | 0.26 | 0.35 | 0.48 [0.36–0.66] | 0.62 | 0.356 [0.24–0.53] | +0.032 [−0.02, +0.09] | 0.190 | 0.272 |
| **nested anchored (post hoc)** | | | **0.49 [0.37–0.65]** | | **0.374 [0.25–0.56]** | **+0.051 [+0.005, +0.104]** | 0.221 | 0.280 (+0.006 [−0.05, +0.06]) |
| phenotype + genes | 0.21 | 0.43 | 0.53 [0.39–0.68] | **0.65** | 0.355 [0.25–0.50] | +0.031 [−0.06, +0.13] | 0.162 | 0.298 |
| phenotype + pathway_full | 0.26 | 0.35 | 0.49 [0.37–0.65] | 0.60 | 0.359 [0.24–0.54] | +0.036 [−0.01, +0.08] | 0.205 | 0.299 |
| phenotype + genes + pathway_full + gene_family | 0.27 | 0.41 | 0.53 [0.39–0.67] | 0.59 | 0.377 [0.25–0.50] | +0.054 [−0.10, +0.23] | 0.103 | 0.317 |
| phenotype + mechanism class | 0.17 | 0.27 | 0.31 | 0.36 | 0.237 [0.15–0.35] | **−0.086 [−0.19, −0.02]** | 0.141 | 0.205 |
| *grid refit, in-sample (optimistic)* | *0.28* | *0.42* | *0.50* | *0.59* | *0.383* | | | *0.327* |
| *logit refit, in-sample (optimistic)* | *0.27* | *0.43* | *0.53* | *0.62* | *0.389* | | | *0.310* |

**Tuned choices.**
- **Anchored, all five folds.** Phenotype 1 + genes 0.5 + protein_domain 0.5 (3 folds) or pathway_mid 0.5 (2 folds). The refit is phenotype 1, genes 0.5, protein_domain 0.5.
- **Logit refit.** Phenotype 3.49, pathway_full 1.57, protein_domain 0.85, pathway_mid 0.85, gene_family 0.79, tissue 0.56, genes 0.51. Mechanism, constraint, mutation_spectrum, AlphaMissense and structure_tm all get **0**.
- **Grid.** It picks phenotype in 5/5 folds and pathway_full in 4/5. The rest of each subset is unstable: one fold picked 7 features. That instability is why the nested grid scores below phenotype alone.

**Ablation (drop one feature from the nested grid; MRR 0.293 with all).** Dropping pathway_full gives 0.288 and dropping phenotype 0.298. Every drop moves MRR by 0.015 or less, in both directions. That is tuning noise.

**Specific drugs (≤ 5 eligible indications; 461 cases).** MRR:

| Scorer | MRR |
|---|---|
| phenotype | 0.374 |
| genes | 0.355 |
| gene_family | 0.355 |
| pathway_full | 0.332 |
| equal weight | 0.400 |
| nested grid | 0.414 |
| nested logit | **0.455** |

The ordering is the same as on all cases.

**Contraindication check ("should rank low").**
- **Setup.** The context is all of the drug's indications. There are 417 contraindicated pool diseases for primary-benchmark drugs (651 in the extended set).
- **Measure.** The mean percentile of each disease among the candidates (0 = top), compared with held-out indications under the same scorer.
- **Results:**

  | Scorer | Contraindications | Held-out indications |
  |---|---|---|
  | phenotype | 0.45 | 0.29 |
  | pathway_full | 0.53 | 0.20 |
  | logit refit | 0.48 | 0.11 |
  | equal weight | 0.55 | 0.21 |
  | mechanism class | 0.56 | 0.42 |

- **Reading.** Every useful scorer separates indications from contraindications. But contraindicated diseases land in the middle, not at the bottom. Phenotype puts them slightly above the middle (0.45), because a drug's contraindications are often clinically adjacent to its indications.
- **So:** none of these similarity factors should be read as a safety signal. Contraindications have to be shown as their own field, from the source label.

## 4. Which factors help (answer to the question)

1. **Symptoms (phenotype) is the backbone.** It is the best single factor overall (MRR 0.32). It is the only factor that works when the diseases share no gene: 0.27 against 0.025 at random. Every other factor is at most 0.065 there. This agrees with eval.md.
2. **Genes involved are a strong but narrow signal.** Half of the held-out diseases (656/1,300) share a gene with one of the drug's other diseases, e.g. allelic disorders or cancer-predisposition genes. There, "same gene" is nearly decisive: the genes feature alone reaches MRR 0.31. But it is useless and slightly harmful when no gene is shared (0.015), because it promotes the wrong same-gene candidates. Used as a **bonus at half weight** on top of phenotype, it gives the best R@5 and R@10 (0.53 and 0.65 for phenotype + genes).
3. **Signalling pathway (Reactome, full hierarchy) and protein family/domain help a little.** Alone they are close to phenotype (0.24–0.31). Most of that comes from the same-gene and same-family cases: across genes they reach only 0.04–0.065, which is above random but small. Added at half weight to phenotype, they give +0.03 to +0.05 MRR. The full Reactome hierarchy beats the mid-level shard pathways (0.31 vs 0.25), because 65 pool diseases have no mid-level pathway.
4. **Tissue, mutation spectrum and gnomAD constraint are weak** (MRR 0.12–0.16). They score above random only because they are proxies for gene identity: identical genes get identical values. Across genes they reach 0.02–0.04, essentially random. Logit gives mutation spectrum and constraint weight 0.
5. **Mechanism class (G2P/ClinGen LoF/DN/GoF/HI + LoF-intolerance) does not help, and it hurts phenotype** (−0.086 MRR, interval below zero). The classes are too coarse: most monogenic diseases are "loss of function". Note what this does *not* contradict. eval.md's mechanism term matches the therapy's own curated target mechanism. That signal does not exist in PrimeKG, and it is a different and much more specific thing.
6. **AlphaMissense gene means and AlphaFold TM-scores do not help in this form.** A gene-level average says how missense-intolerant a protein is, not what it does. The mechsim TM-scores cover only 52 of 256 pool diseases. These are better kept as per-variant and explanation features (the VCF checker; "similar fold") than as ranking factors.

**Best combination.** The best honest result is **phenotype 1.0 + genes 0.5 + one of protein_domain / pathway 0.5**: nested-anchored MRR 0.374 [0.25–0.56] and R@5 0.49. That is +0.051 MRR over phenotype alone, with an interval of +0.005 to +0.104 and P(better) = 0.99.
- **Caveats.** The anchored tuner is post hoc (added after the first run), as in eval.md. On the extended benchmark (indication + off-label) its gain shrinks to +0.006 [−0.05, +0.06]. Treat it as a small, plausible gain, not an established one.
- **Larger tuners overfit.** The nested grid (0.293) does worse than phenotype alone. Nested logit gains +0.03, with an interval crossing 0. The in-sample refits (0.38–0.39) show the overfitting gap a naive tune would report.

## 5. Recommendation for the production scorer

1. **Keep the eval.md (d) scorer for the 45 atlas diseases.** That is phenotype + the therapy's curated target mechanism (`TransferIndex.score("pheno+mech")`). Nothing here contradicts it, and PrimeKG has no equivalent of the curated target term.
2. **For transfer across the 11k-disease global index, where there are no curated targets**, score:

   `score = phenotype/max + 0.5 · genes/max + 0.5 · pathway_full/max`

   where the pathway term is the full Reactome hierarchy, or protein_domain, which is equivalent within noise. Show "same gene" as an explicit reason in the UI, because it is the single most decisive and most explainable signal.
3. **Do not add the coarse mechanism class, gnomAD constraint, tissue, mutation spectrum or AlphaMissense to the ranking score.** Show them as explanations on disease pages instead:
   - "LoF-intolerant (LOEUF 0.10): consistent with haploinsufficiency";
   - "mostly truncating variants";
   - "tissue-enriched in brain".

   They add context, and in this benchmark they do not add ranking accuracy.
4. **Treat contraindications separately.** Similarity puts them mid-pool, not low, so they need their own field from the source label.
5. **Use the new data where it clearly does help:**
   - The ClinVar shards let the VCF checker cover every gene. They need one sync line in `web/scripts/sync-data.mjs`.
   - The spectrum and constraint files can feed mutation-type and haploinsufficiency text for all 13k and 18k genes.
   - The PrimeKG benchmark should become the regression test for any future scorer change. It is external, has 1,300 cases and runs in about 10 s.

## Limitations

- **Unknowns count as negatives.** A pool disease ranked above the held-out one may be an untested opportunity, not an error.
- **Drug groups dominate the variance.** There are 95 groups, and the corticosteroid and oncology groups carry many cases; the intervals are wide for that reason. The macro average per drug group, in `primekg_eval.json` (`rr_macro_group`), gives the same ordering.
- **PrimeKG indications lean towards oncology and immunology.** Many "rare" pool entries are familial cancers or inflammatory syndromes, where the same broad drugs (corticosteroids, cytotoxics) are indicated. Rare-disease-specific drugs are a minority. The specific-drug subset (461 cases) gives the same ordering.
- **Exact MONDO mapping only.** Of the 2,054 PrimeKG nodes with drug edges, 1,343 stay unmapped: mostly common or grouping terms outside our rare-disease index.
- **Post hoc choices.** The anchored tuner, the switched-off child mapping and the extended benchmark were all decided after the first run. Each is reported, and the primary benchmark was not re-tuned to favour any feature.
- **Features take the maximum over the context.** A drug with many indications (corticosteroids, about 40) gets broad context, which inflates every similarity feature.
- **Coverage gaps.** Phenotype is missing for 48 of 256 pool diseases (mostly cancers without HPO annotations), and structure_tm for 204.

## 6. Applied: production similar-disease index (follow-up)

`pipeline/ingest/similar_index.py` applies the recommended scorer, `phen + 0.5·genes + 0.5·full Reactome`, to every
global-index disease that has HPO annotations: 10,690 diseases, with 10 neighbours each. Each neighbour carries:
- the score and its three raw component scores;
- up to 3 shared symptoms that are characteristic of both diseases (ranking rule below);
- "same gene" genes;
- up to 2 shared pathway names, with generic pathways left out (rule below).

| File | Size |
|---|---|
| `data/derived/global/similar/<djb2(MONDO)%64>.json` | 14.0 MB raw / 3.4 MB gzipped (max shard 427 KB) |
| `data/derived/global/gene_factors.json` (5,191 genes: constraint label, ClinVar dominant type, AlphaMissense label; explanation only) | 695 KB / 97 KB gzipped |

Both files are documented in `data/derived/global/README.md`.

Note for whoever deploys: `sync-data.mjs` copies all of `data/derived/global/`, so these files will be deployed, adding about 14 MB raw.

**Reason quality (second pass; display only, so scores and rankings are unchanged).**

*Symptoms.* Shared symptoms used to be simply the rarest shared terms. That gave "Limited knee extension" and
"Tibial torsion" as the reasons for Dravet–GEFS+. Now each shared term is weighted by IC × how characteristic it is in each disease:
- 1.0 if HPO marks it frequent or very frequent (≥ 30%);
- 0.5 if occasional;
- 0.8 if it has no frequency but is among the disease's top 30 terms by IC, else 0.4.

Musculoskeletal terms are weighted ×0.3 unless both diseases are mainly musculoskeletal.

*Pathways.* Generic Reactome pathways are dropped from the reasons: more than 300 genes, or a named generic pathway such
as Generic Transcription Pathway, Metabolism of proteins or Signal Transduction. They stay in the score, as in the benchmark.

New example reasons:
- **Dravet → GEFS+:** febrile seizure; generalized absence seizure; generalized myoclonic seizure.
- **Huntington → SCA48:** chorea; depression; extrapyramidal signs. The generic transcription pathway reason is gone.
- **Tay-Sachs → infantile Sandhoff:** cherry red spot of the macula; abnormal thalamic MRI signal; developmental regression.
