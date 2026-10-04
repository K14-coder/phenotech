# Accuracy evaluation: connectivity and therapy transfer

**Question.** How well is the graph connected, and how accurately can it identify how progress on one
disease could help another?

```bash
python3 pipeline/eval/transfer_eval.py     # stdlib only, ~15 s, offline, no OpenAI
```

- Code: `pipeline/eval/transfer_eval.py` runs the evaluation; `pipeline/eval/transfer_score.py` holds the reusable scorer.
- Output: `data/derived/eval.json`, 71 KB, compact, for the `/method` page.
- Inputs: it reads `data/graph.json` (1,411 nodes, 2,540 edges) and the family files.
- Nothing outside `pipeline/eval/`, `data/derived/eval.json` and this file was written.

## Plain-language summary (for families and judges)

1. The atlas links all 45 diseases in one network. Many of those links, though, run through broad labels such as "loss of function", which about 4 in 10 disease pairs share. Through specific biology, 39 of 45 diseases connect to another disease, and only 11 connect to a disease in a different family.
2. To test whether the atlas can spot how progress on one disease could help another, we hid each of 56 known therapy–disease links, one at a time. Each time, we asked the atlas to rank all 45 diseases for that therapy.
3. Combining shared symptoms with shared specific mechanisms, the atlas put the hidden disease first in 29% of tests and in its top 5 in 73% (random guessing: 2% and 12%). When the therapy already had another known disease to learn from, the top-5 rate rose to 83%.
4. It recovered real cross-disease connections:
   - 4-phenylbutyrate between STXBP1 and SLC6A1, in both directions;
   - MEK inhibitors across the RASopathies;
   - miglustat within the lysosomal diseases, though less sharply.

   But the test is small, and the same literature was used to build both the graph and the test. Read a high rank as a reason to look, not as proof.
5. Every link shows its sources. 2.9% of links carry contradicting evidence, and it is shown, not hidden. An independent AI re-reading of the same papers agreed with the curators on 60 of 68 (88%) readings that both made of the same paper and the same link.

## 1. Connectivity

| Measure | Value |
|---|---|
| Connected components (all edges except the 5 hypotheses) | 28. The giant component holds **1,384 of 1,411 nodes (98.1%) and all 45 diseases**; the other 27 are isolated phenotype nodes with no edge. |
| Diseases sharing an evidence-backed mechanism with another disease (no inferred or hypothesis edges) | any mechanism: **45/45**; a specific (non-generic) mechanism: **39/45 (86.7%)** |
| … with a disease in **another family** | any mechanism: 38/45; specific mechanism: **11/45 (24.4%)** |
| Disease pairs sharing a mechanism | any: 502/990; a generic effect (LoF, HI, GoF, DN): **411/990 (41.5%)**; a specific mechanism: **162/990** |
| Median shortest path between two diseases | full graph: 2 hops (max 4); evidence-backed biology incl. phenotypes: 2 (max 4); mechanisms only: 4 (max 6); **specific mechanisms only: 7 hops, and only 571/990 pairs (57.7%) are connected at all** |
| Computed disease–disease links (`shares_mechanism` + `similar_phenotype`) | 122 edges over 116 pairs. 42/45 diseases have a disease neighbour, and 520/990 pairs are reachable (median 2 hops). |
| Cross-family pairs | **22 of 116**: 20 DEE↔SNARE phenotype similarities, plus SLC6A1–GLA and SLC6A1–NPC1 (protein destabilization). No disease–disease link touches the RASopathies or joins lysosomal to DEE. |
| Specific mechanisms bridging families | protein destabilization (lysosomal + SNARE, 8 diseases); negative regulation of Ras signalling (SYNGAP1–LZTR1); regulation of synaptic plasticity (GRIN2B, SYNGAP1, VAMP2) |
| Therapies known in more than one family | 1: fenfluramine (CDKL5 and SCN1A; STXBP1 and SYNGAP1 through one study) |
| Edges by evidence level | curated 1,389 · observational 403 · inferred 279 · clinical 274 · experimental 190 · hypothesis 5 |
| Edges with counter-evidence | **73/2,540 (2.9%)**; 76 contested. The most contested types are developed_for (29/63), driven_by (16/92), shares_mechanism (9/47) and targets (8/39). |

**Reading.** The graph is well connected. That connectivity is cheap, because the generic effects and shared phenotypes join almost everything. The connectivity that matters for transfer, through specific mechanisms, is good within families and thin between them. Only about a quarter of diseases have a specific, evidence-backed mechanism shared with another family.

`eval.json → connectivity.mechanism_specificity` lists how many diseases reach each of the 31 mechanism nodes. Loss of function reaches 33; GABA reuptake reaches 1.

## 2. Transfer-prediction benchmark

### Design

- **Unit.** A therapy class × disease pair. Duplicate nodes for the same product are merged:
  - aminopyridines, the AAV-STXBP1 nodes and the AAV-SLC6A1 nodes, as in `hypotheses.py`;
  - the four MEK1/2 inhibitors, a class added for this evaluation.
- **Cases.** One test case per `developed_for` link of a class that has ≥ 2 known diseases or ≥ 1 `targets` edge: **56 cases over 38 classes**. In 30 cases the therapy has at least one other known disease (the *transfer* subset). In 26 it has none (*rediscovery*: the ranking can only use the therapy's own `targets` edges).
- **Context.** The extended set adds 18 pairs that come only from studies (a study that tests the therapy and studies the disease), for 74 cases in total.
- **Hiding.** For each case, the class's `developed_for` edge(s) to the held-out disease are hidden, along with every study edge that links the class to it.
- **Ranking.** All 45 diseases minus the class's other known diseases are ranked (filtered ranking, about 43 candidates).
- **Ties.** Ties are scored at their expected value, so a scorer that cannot separate the candidates scores exactly at random.
- **Intervals.** 95% intervals come from a bootstrap over therapy classes, because cases of one drug are correlated (2,000 draws, fixed seed).
- **Weights.** All weights were fixed before the first run.

### Scorers

- (b) Phenotype: IC-weighted Jaccard of the `has_phenotype` sets, taking the maximum over the therapy's other known diseases.
- (c) Mechanism: the therapy's `targets` mechanisms that the disease reaches. A mechanism counts if the disease reaches it by `driven_by` (weight 1.0), by gene → variant group → `has_effect` (0.8), or by gene → `participates_in` (0.7). Each match is weighted by its IDF over the 45 diseases, `ln(46/(df+1))`.
- (d) Phenotype + mechanism: (b)/max + (c)/max.
- (e) Mechanism + cluster: (c) plus the IDF of every curated cluster that holds the candidate and one of the therapy's targets or known diseases. Clusters that list a therapy as a member are excluded, because they were curated from that therapy's trials.
- (f) Phenotype + mechanism + cluster: (d) with the cluster term from (e) added.

### Results: all 56 developed_for cases

| Scorer | R@1 | R@3 | R@5 | MRR | Median rank |
|---|---|---|---|---|---|
| (a) random | 0.02 | 0.07 | 0.12 | 0.10 | 22.5 |
| (b) phenotype similarity | 0.15 [0.05–0.27] | 0.39 [0.21–0.56] | 0.46 [0.30–0.61] | 0.30 [0.19–0.39] | 18 [3–23] |
| (c) mechanism, IDF-weighted | 0.24 [0.14–0.33] | 0.46 [0.34–0.56] | 0.59 [0.48–0.69] | 0.40 [0.31–0.48] | 4.5 [4–5.5] |
| **(d) phenotype + mechanism** | **0.29 [0.16–0.44]** | **0.60 [0.45–0.74]** | **0.73 [0.63–0.82]** | **0.49 [0.39–0.59]** | **3.75 [2–5]** |
| (e) mechanism + cluster | 0.22 [0.15–0.30] | 0.57 [0.41–0.72] | 0.70 [0.57–0.81] | 0.44 [0.35–0.51] | 3.5 [2.5–5.5] |
| (f) phenotype + mechanism + cluster | 0.26 [0.14–0.40] | 0.59 [0.43–0.73] | 0.70 [0.57–0.82] | 0.46 [0.36–0.57] | 3 [2–5.5] |
| baseline: same family as the known diseases | 0.10 [0.06–0.15] | 0.30 [0.17–0.44] | 0.42 [0.27–0.56] | 0.26 [0.17–0.34] | 5.5 [4.5–23] |
| baseline: naive "target is a driven_by mechanism" | 0.09 [0.06–0.12] | 0.22 [0.17–0.27] | 0.35 [0.27–0.45] | 0.22 [0.18–0.27] | 15 [5.5–21.5] |
| **current `hypotheses.py` chain rule** | 0.21 [0.12–0.30] | 0.51 [0.35–0.65] | 0.65 [0.51–0.76] | 0.41 [0.31–0.49] | 4.5 [2.5–5.5] |
| current rule without its cluster chain | 0.21 [0.12–0.30] | 0.44 [0.32–0.54] | 0.58 [0.48–0.68] | 0.38 [0.29–0.46] | 4.5 [4–5.5] |
| *(e) with therapy-informed clusters (leaky)* | *0.41* | *0.68* | *0.83* | *0.59* | *2* |

n = 56 for every row; the 2.5–97.5% interval is in brackets.

### Results: transfer subset (n = 30; the therapy has another known disease)

| Scorer | R@1 | R@3 | R@5 | MRR | Median rank |
|---|---|---|---|---|---|
| random | 0.02 | 0.07 | 0.12 | 0.10 | 21.5 |
| (b) phenotype | 0.27 [0.08–0.49] | 0.67 [0.42–0.85] | 0.77 [0.57–0.93] | 0.47 [0.32–0.62] | 3 |
| (c) mechanism | 0.29 [0.13–0.46] | 0.50 [0.29–0.68] | 0.57 [0.37–0.73] | 0.43 [0.26–0.57] | 4.5 |
| **(d) phenotype + mechanism** | **0.40 [0.15–0.67]** | **0.77 [0.52–0.95]** | **0.83 [0.67–0.96]** | **0.60 [0.42–0.78]** | **2** |
| (e) mechanism + cluster | 0.27 [0.16–0.40] | 0.74 [0.49–0.92] | 0.82 [0.62–0.95] | 0.51 [0.38–0.62] | 2.75 |
| (f) all three | 0.33 [0.12–0.61] | 0.77 [0.52–0.95] | 0.83 [0.62–1.00] | 0.56 [0.39–0.75] | 2 |
| same-family baseline | 0.17 | 0.50 | 0.69 | 0.39 | 4.5 |
| current chain rule | 0.27 [0.10–0.43] | 0.58 [0.28–0.79] | 0.65 [0.39–0.83] | 0.45 [0.26–0.58] | 4 |

### Other subsets and checks (all in `eval.json`)

- **Rediscovery subset (n = 26).** Phenotype is at random level, because there is no other disease to compare with.
  - Mechanism (c): MRR 0.37 and R@5 0.61; the current rule: MRR 0.36 and R@5 0.64.
  - This subset is mostly circular. A gene-specific product's `targets` edge (for example "AAV-SLC6A1 targets GABA reuptake") practically names its disease.
- **Extended set (n = 74, incl. study-only pairs).**
  - (d): MRR 0.46 and R@5 0.76; the current rule: 0.40 and 0.62.
  - The RASopathy basket trials make this set easier.
- **Node level (no therapy classes, n = 58).**
  - (d): MRR 0.46 and R@5 0.73; the current rule: 0.40 and 0.65.
  - The scorers come out in the same order.
- **Combination weight (post hoc).** The phenotype weight in phenotype + (mechanism + cluster) was varied over 0.25, 0.5 and 0.75. MRR came out at 0.48, 0.46 and 0.45: stable.
- **Ties.** The current rule leaves a median of **8 diseases tied at the top** (at most 44). (d) leaves a median of 1. The naive rule scores the held-out disease above zero in 28/56 cases; the current rule does so in 47/56 and (d) in 55/56.
- **By family of the held-out disease, MRR of (d) vs the current rule:**

  | Family | (d) | Current rule |
  |---|---|---|
  | DEE | 0.63 | 0.39 |
  | SNARE | 0.72 | 0.49 |
  | Lysosomal | 0.31 | 0.30 |
  | RASopathies | 0.41 | 0.60 |

  The RASopathy row is the only place where the current rule wins. It wins through its cluster chain, which uses the curated "MEK-inhibitor-responsive" cluster, and that cluster lists trametinib and its diseases (leakage).
- **Leakage, measured.** Letting scorer (e) use clusters that list therapies raises MRR from 0.44 to 0.59. Any score that reads those clusters is partly reading the answer.

### Verdict on item 5

(d), phenotype + mechanism, is the best honest scorer. It beats the current chain rule on every metric, in every subset with context, at both class and node level.

| Comparison with the current rule | All 56 cases | Transfer subset |
|---|---|---|
| MRR | 0.49 vs 0.41 (paired difference 95% CI −0.02 to +0.20; P(better) = 0.95) | 0.60 vs 0.45 (CI −0.02 to +0.41) |
| R@5 | 0.73 vs 0.65 | 0.83 vs 0.65 (CI **+0.02 to +0.45**) |

That is consistent but not overwhelming: n is small, and only the transfer R@5 interval excludes zero. The comparison is still conservative, because the current rule gets the benefit of its leaky cluster chain.

The (f) score, which adds clusters, was pre-declared as the default. It scored the same as (d) within noise, so the simpler (d) is recommended. Choosing between two near-equal candidates on the same data is a mild selection effect.

The function is `TransferIndex.rank_candidates()` / `TransferIndex.score("pheno+mech", …)` in `pipeline/eval/transfer_score.py`. The benchmark runs this same code, and `explain()` returns the matched mechanisms (with IDF, chain kind and edge ids), the clusters and the nearest known disease by phenotype.

**How `pipeline/derive/hypotheses.py` could use it (not edited):**

1. Keep the existing chain search and all four safety filters as they are: product transferability, therapy equivalence, already-developed/already-tested, and review rejection. They are gates, not rankers.
2. Replace the sort key `(-CHAIN_WEIGHT, -min confidence, contested)` with the (d) score, computed with the class's known diseases as context.
3. Store `attrs.transfer_score`, `attrs.transfer_rank` and the `explain()` output on each `candidate_for` edge, so the UI can say "ranked 1 of 43 because it shares *protein destabilization* (in 8 of 45 diseases) and its symptoms are closest to STXBP1".
4. Drop the `cluster` chain for clusters that list a therapy as a member, because it is self-confirming.
5. Do not emit `candidate_for` edges from the phenotype term alone, for example for fenfluramine or cannabidiol, which have no `targets` edges. Route those to `opportunities.json` as look-alike leads.
6. The score ranks candidates; it is not a probability. Keep the ≤ 0.25 confidence cap.
7. Re-run `python3 pipeline/eval/transfer_eval.py` after every curation change, and watch the transfer-subset MRR.

What changes in practice: for 4-PBA, the (d) ranking of new candidates puts **VAMP2 first**, which is the existing top hypothesis. It is followed by HEXA, GAA, GLA and GBA1, the lysosomal diseases with chaperone-responsive misfolding. The current rule ties all of them.

## 3. Known-collaboration recovery

Ranks are for scorer (d), among about 43 candidates after removing the other known diseases.

**4-phenylbutyrate (STXBP1 ↔ SLC6A1).**
- Given STXBP1, SLC6A1 ranks **1st of 44**; given SLC6A1, STXBP1 ranks **1st of 44**. The current rule puts both at 4 (tied); phenotype alone gives 4 and 2.
- One worry is circularity. 4-PBA's `targets` edge to *GABA reuptake* is SLC6A1-specific, because it was curated from the SLC6A1 work. With that edge removed (an ablation), both directions still rank 1st.
- What carries the result is protein destabilization, which only 8 diseases reach, plus the two diseases being phenotype neighbours.
- The same score names VAMP2 as the next candidate, which agrees independently with the curated hypothesis file.

**MEK inhibitors across the RASopathies.**
- Leave-one-out: every held-out RASopathy ranks **2nd or 3rd of 36**. The only diseases above it are the two RASopathies not yet linked to a MEK inhibitor, SHOC2 and CBL.
- The stricter test starts from NF1 alone (selumetinib) and asks for the other nine. PTPN11 ranks 1, RAF1 3, MAP2K1 4, BRAF 5, HRAS 6, KRAS 7, SOS1 8 and RIT1 9. The top 5 are all RASopathies, with SHOC2 at 2.
- **LZTR1 ranks 37.** Mechanism alone misses LZTR1, RIT1 and SOS1 (rank 19): in the graph their genes reach *Ras signal transduction* or nothing, never *MAPK cascade*, because the graph has no RAS → MAPK hierarchy. LZTR1 also looks unlike NF1 in phenotype.
- Adding that hierarchy as `participates_in` edges is the single most useful curation fix this evaluation found.

**Miglustat across the lysosomal diseases.**
- Leave-one-out: NPC1 ranks 3, HEXA 3 (study-only), GAA 5, CLN3 8 and GBA1 8, of 41. From GBA1 alone, CLN3 ranks 3, GAA 4, HEXA 7 and NPC1 10, and the top 5 are all lysosomal.
- The graph cannot say *which* lysosomal disease suits a glucosylceramide-synthase inhibitor. "Lysosomal storage" is shared by all 12 (low IDF), and the substrate class is not modelled.
- Phenotype hurts here, because Gaucher's visceral profile and CLN3's neurological one barely overlap.
- Miglustat's links to GAA (as an enzyme stabiliser given with replacement therapy) and to CLN3 rest on different rationales than substrate reduction. A biologist would not expect a single mechanism to recover them.
- This case shows the ceiling: family-level recall is good, and the ordering within the family is weak.

## 4. Agreement with independent sources (stated, not recomputed)

| Check | Result | Scope | Source |
|---|---|---|---|
| OpenAI second reading vs curators, same (edge, PMID) | **60/68 (88.2%)**: causes 8/8, developed_for 8/9, driven_by 26/33, has_effect 8/8, has_phenotype 8/8, targets 2/2. Curated pairs re-found independently: 68/255 (26.7%). | 78 abstracts, SNARE slice only, one model (gpt-6-astra), abstracts only | `docs/agent-reports/openai-extraction.md` |
| Build-time cross-check | 68 cited sources re-read; 8 where the OpenAI reading disagrees (waiting for human review); quotes string-verified 1,963/1,963 | all graph evidence with quotes | `data/build/report.md` |
| DisMech (Monarch) | primary mechanism class agrees for **3/3** diseases compared in depth (STXBP1, Dravet/SCN1A, SNAP25). Disagreements: PMID:25381298 (atlas LoF vs DisMech dominant-negative); DisMech lists STXBP1 under Dravet. 72 MONDO links reach 32/45 umbrellas. | qualitative, 3 diseases; not a rate | `docs/agent-reports/dismech.md` |
| G2P / ClinGen dosage class vs atlas effect mechanisms (computed here) | 38/45 diseases have an external class. **Strict** (the same class on a driven_by edge): 23/38 (60.5%). **Lenient** (variant-group effects count; HI and lysosomal enzyme deficiency count as LoF): **36/38 (94.7%)**. The two real disagreements are below. | 45 diseases, curated external sources | `data/derived/global/mechanism/` |

The two disagreements from the G2P/ClinGen check:
- **CBL**: G2P says gain of function; the atlas says loss of function.
- **SCN8A**: G2P says dominant negative; the atlas has GoF/LoF/HI.

Both are worth a biochemist's look.

## Limitations

- **Small n.** 56 cases from 38 therapy classes, and 30 with context. The intervals are wide, and one drug class (MEK, 6 cases) can move the averages.
- **Circularity.** The same curators built the `targets` and `driven_by` edges, the clusters and the therapy links from overlapping literature.
  - The rediscovery subset is close to tautological.
  - Clusters that list therapies are measurably leaky: +0.15 MRR.
  - The family groupings that make transfer look easy were made by the same people.
  - The 4-PBA ablation is the only case where a leaking edge was removed explicitly.
- **Unknowns count as negatives.** A disease ranked above the held-out one may be an untested opportunity (SHOC2 for MEK inhibitors), not an error.
- **The world is small.** There are 45 diseases in 4 families, so this is a much easier task than open-world repurposing over 11,456 diseases. The same-family baseline already reaches R@5 0.69 in the transfer subset.
- **Coarse inputs.**
  - Phenotype similarity uses at most about 20 curated HPO terms per disease, with exact-term overlap and no ontology propagation.
  - The mechanism vocabulary is 31 nodes connected to diseases, with no RAS → MAPK hierarchy and no lysosomal substrate classes.
- **Mild selection effect.** The recommended scorer (d) was picked post hoc over the pre-declared (f), although the two are equal within noise.
- **Narrow agreement checks.** The OpenAI check covers one family and one model, and only abstracts. DisMech is 3 diseases. Evidence levels are assigned by curators.
- **Data hygiene.** 27 phenotype nodes have no edge, and they make up the 27 small components.

## 5. Richer biological features: multi-feature scorer (added 2026-10-04)

**Question.** Does weighting in genes and gene families, signalling pathways, tissue, symptoms, protein
families and domains, mutation type and molecular consequence beat the phenotype + mechanism scorer (d)?

```bash
python3 pipeline/eval/build_features.py    # ~2 s, offline once the raw downloads exist (URLs in the script)
python3 pipeline/eval/feature_eval.py      # ~60 s, numpy, offline, no OpenAI
```

- Code: `pipeline/eval/build_features.py` (features), `pipeline/eval/feature_eval.py` (benchmark), and `MultiFeatureIndex` / `rank_candidates_multi()` in `pipeline/eval/transfer_score.py` (the existing `TransferIndex` API is unchanged; `transfer_eval.py` output is unchanged).
- Features: `data/derived/features/atlas_features.json` (45 diseases, 376 KB), `gene_families.json` (PANTHER / InterPro / Pfam for 5,168 of the 5,244 genes in the global index), `gene_tissue.json` (HPA tissue specificity for 5,161 genes).
- Raw downloads in `data/raw/downloads/` (gitignored): one UniProt REST stream query (20,431 reviewed human proteins: InterPro, Pfam, PANTHER, GO BP/MF/CC, subcellular location, length), InterPro `entry.list` (entry types), the HPA API tissue-specificity table. Reactome, GO, HPO, G2P and ClinGen files were already there.
- Results: `data/derived/eval_features.json`.

### Features

Each feature is a similarity, normalised per query by its maximum over the candidates. A **context** feature compares the candidate with the therapy's other known diseases (maximum over them), so it is 0 in the 26 rediscovery cases. A **therapy** feature compares the candidate with the therapy's own `targets`. The IDF is `ln((N+1)/(df+1))`, counted globally: over the 20,431 reviewed human proteins for families, domains and GO; over Reactome genes; over HPA genes; and over HPO-annotated diseases. Only the vocabularies that are local to the graph use the 45 diseases.

| Feature (user's category) | Data | Similarity | Coverage (of 45) |
|---|---|---|---|
| `symptoms` (symptoms) | curated HPO phenotypes | IC-weighted Jaccard (old scorer b) | 45 |
| `phenotype_systems` (tissue: anatomy) | HPO terms → the 23 top-level organ systems (children of HP:0000118) in hp.obo | IDF-weighted cosine of IC-weighted system profiles | 45 |
| `tissue` (tissue: expression) | HPA RNA tissue specificity and enriched tissues (nTPM) | cosine of log1p(nTPM) × tissue IDF | 23 (the others are "low tissue specificity", including most lysosomal and RAS genes) |
| `gene_family` (genes) | PANTHER family + InterPro *Family* entries | IDF-weighted cosine | 45 |
| `shared_gene` (genes) | the causal gene | identity | degenerate: no two atlas diseases share a gene. It is reported, and excluded from tuning. |
| `protein_domains` (protein structure) | InterPro Domain / Repeat / Homologous superfamily + Pfam | IDF-weighted cosine | 45 |
| `reactome` (signalling pathway) | Reactome, lowest level plus all ancestors (the shard mid-level pathways are a subset) | IDF-weighted cosine | 41 |
| `go_process` (signalling pathway) | UniProt GO BP, propagated over is_a / part_of | IDF-weighted cosine | 45 |
| `compartment` (extra) | UniProt GO CC, propagated | IDF-weighted cosine | 45 |
| `mutation_type` (mutation type) | ClinVar P/LP spectrum from the variant_group `clinvar_counts`: truncating / missense / in-frame / splice / CNV | 1 − Jensen–Shannon divergence | 45 |
| `molecular_consequence` (molecular consequence) | LoF / HI / DN / GoF / destabilisation from `driven_by` (1.0) and variant-group `has_effect` (0.8), plus G2P / ClinGen classes and the G2P variant consequence | IDF-weighted cosine | 45 (41 with an external class) |
| `mechanism_target` (therapy) | old scorer (c): the therapy's target mechanisms reached over graph chains | sum of IDF | n/a |
| `target_go` (therapy, new) | the GO term of a therapy target mechanism, found in the candidate gene's propagated UniProt GO | sum of GO IDF | n/a |

### Tuning without leakage

- The outer loop holds out **all the cases of one therapy class** at a time (38 folds). Weights are chosen on the other 37 classes only, and then score the held-out class.
- Two tuners were declared before the run:
  - `grid`: every weight in {0, 1}, which is a feature-subset search over 12 features (4,095 settings). The objective is the inner MRR, and ties go to fewer features.
  - `logit`: a conditional-logit ranking model, a softmax over each case's candidates, with weights ≥ 0 and an L2 penalty λ = 1.
- A third, smaller tuner was **added after seeing the first run**, and is labelled as post hoc. `anchored` keeps the old best at weight 1 and adds at most two other features at weight 0.5 (67 settings).
- Untuned references: the old best, and equal weight on all features.
- The ties, filtered ranking and class bootstrap (2,000 draws) are the same as in section 2.

### Results: all 56 developed_for cases

| Scorer | R@1 | R@3 | R@5 [95% CI] | MRR [95% CI] | Transfer subset MRR / R@5 (n = 30) | Rediscovery MRR (n = 26) |
|---|---|---|---|---|---|---|
| random | 0.02 | 0.07 | 0.12 | 0.10 | 0.10 / 0.12 | 0.10 |
| **old best (symptoms + mechanism_target)** | **0.29** | **0.60** | **0.73 [0.63–0.82]** | **0.491 [0.39–0.59]** | **0.599 / 0.83** | 0.367 |
| equal weight, all 12 (untuned) | 0.32 | 0.52 | 0.68 [0.53–0.81] | 0.480 [0.36–0.60] | 0.567 / 0.73 | 0.379 |
| nested grid | 0.26 | 0.56 | 0.71 [0.56–0.82] | 0.457 [0.36–0.56] | 0.538 / 0.80 | 0.363 |
| nested logit | 0.28 | 0.52 | 0.66 [0.51–0.78] | 0.458 [0.35–0.56] | 0.528 / 0.70 | 0.379 |
| nested anchored (post hoc) | 0.29 | 0.58 | 0.73 [0.58–0.85] | 0.485 [0.38–0.59] | 0.587 / 0.83 | 0.367 |
| *grid refit, in-sample (optimistic)* | *0.35* | *0.58* | *0.75* | *0.515* | *0.643 / 0.87* | |
| *anchored refit, in-sample (optimistic)* | *0.32* | *0.61* | *0.76* | *0.510* | *0.625 / 0.90* | |
| single: mechanism_target | 0.24 | 0.46 | 0.59 [0.48–0.69] | 0.402 [0.31–0.48] | 0.431 / 0.57 | 0.367 |
| single: compartment | 0.21 | 0.30 | 0.35 [0.19–0.51] | 0.302 [0.15–0.46] | 0.478 / 0.57 | 0.098 |
| single: symptoms | 0.15 | 0.39 | 0.46 [0.30–0.61] | 0.298 [0.19–0.39] | 0.472 / 0.77 | 0.098 |
| single: reactome | 0.14 | 0.32 | 0.43 [0.25–0.59] | 0.281 [0.16–0.41] | 0.439 / 0.70 | 0.098 |
| single: target_go | 0.19 | 0.29 | 0.33 [0.23–0.44] | 0.279 [0.18–0.37] | 0.337 / 0.38 | **0.212** |
| single: go_process | 0.14 | 0.28 | 0.34 [0.18–0.48] | 0.258 [0.14–0.39] | 0.398 / 0.53 | 0.098 |
| single: protein_domains | 0.16 | 0.25 | 0.31 [0.18–0.45] | 0.256 [0.14–0.38] | 0.393 / 0.48 | 0.098 |
| single: gene_family | 0.14 | 0.23 | 0.27 [0.15–0.39] | 0.231 [0.13–0.34] | 0.347 / 0.41 | 0.098 |
| single: phenotype_systems | 0.12 | 0.21 | 0.32 [0.16–0.49] | 0.228 [0.12–0.34] | 0.341 / 0.50 | 0.098 |
| single: mutation_type | 0.06 | 0.23 | 0.32 [0.18–0.43] | 0.208 [0.13–0.28] | 0.303 / 0.50 | 0.098 |
| single: molecular_consequence | 0.06 | 0.13 | 0.30 [0.17–0.42] | 0.171 [0.13–0.22] | 0.234 / 0.46 | 0.098 |
| single: tissue | 0.02 | 0.12 | 0.18 [0.10–0.29] | 0.123 [0.09–0.16] | 0.144 / 0.24 | 0.098 |
| single: shared_gene | 0.02 | 0.07 | 0.12 | 0.102 | 0.105 / 0.12 | 0.098 |

Paired MRR differences against the old best (95% CI over classes):

| Tuner | All cases | Transfer subset |
|---|---|---|
| nested grid | −0.073 to 0.000 | −0.144 to 0.000 |
| nested logit | −0.078 to +0.008 | −0.171 to −0.004 |
| nested anchored | −0.040 to +0.024 | −0.088 to +0.041 |
| equal weight | −0.062 to +0.040 | −0.139 to +0.069 |

**Tuned weights (refit on all 56 cases; the nested numbers above are the honest estimate).**

- grid: `symptoms`, `mechanism_target`, `phenotype_systems`, `gene_family`, `compartment`, `mutation_type` and `molecular_consequence`, all at 1. Selection frequency in the outer folds: `symptoms`, `mechanism_target` and `mutation_type` 38/38, `phenotype_systems` 35, `molecular_consequence` 34, `gene_family` and `compartment` 33.
- logit:

  | Feature | Weight |
  |---|---|
  | mechanism_target | 3.15 |
  | symptoms | 1.10 |
  | gene_family | 1.08 |
  | mutation_type | 0.98 |
  | target_go | 0.97 |
  | phenotype_systems | 0.85 |
  | tissue | 0.67 |
  | protein_domains | 0.43 |
  | reactome | 0.18 |
  | molecular_consequence | 0.14 |
  | compartment | 0.09 |
  | go_process | 0.09 |

  The weights are stable across folds.
- anchored: the old best + 0.5 `target_go` + 0.5 `mutation_type`, selected in 35/38 folds.

**Ablation (drop one feature, re-run the whole nested procedure; MRR).**

| Dropped | anchored | grid | logit |
|---|---|---|---|
| none | 0.485 | 0.457 | 0.458 |
| mechanism_target | n/a | **0.390** | **0.386** |
| symptoms | n/a | **0.403** | 0.432 |
| mutation_type | 0.457 | 0.440 | 0.456 |
| target_go | 0.472 | 0.471 | 0.465 |
| gene_family | 0.485 | 0.452 | 0.460 |
| phenotype_systems | 0.485 | 0.463 | 0.478 |
| protein_domains / reactome / tissue | 0.485 | 0.457 | 0.459–0.464 |
| go_process | 0.510 | 0.456 | 0.459 |
| compartment | 0.510 | 0.456 | 0.461 |
| molecular_consequence | 0.485 | 0.460 | 0.461 |

Only two features carry the score: removing `mechanism_target` or `symptoms` costs 0.06–0.10 MRR. Every other drop moves MRR by ≤ 0.03, in both directions. Dropping `go_process` or `compartment` *raises* the anchored tuner to 0.510, because the 3 folds that picked them were hurt. That is tuning noise, not a finding, and it was not used to pick anything.

### Verdict

**The richer features do not beat the old best (d) on this benchmark.**

- All three tuners score at or below it under nested CV: 0.457, 0.458 and 0.485 vs 0.491 MRR.
- The in-sample refits look better (0.510–0.515), and that is the overfitting gap a naive tune would have reported.
- `MULTI_WEIGHTS` in `transfer_score.py` is therefore the old best, so `scorer="multi"` ranks identically to `"pheno+mech"`. `ANCHORED_WEIGHTS` is provided as the documented alternative.
- What the new features add:
  - Explanation: `MultiFeatureIndex.explain()` names the nearest known disease per feature.
  - One non-circular signal: `target_go` reaches rediscovery MRR 0.21 vs random 0.10, using UniProt GO rather than curator edges. The curated `mechanism_target` gets 0.37 there, but partly by construction.
  - Untuned equal weighting raises R@1 (0.32 vs 0.29) while lowering R@5.

### Known-collaboration checks (ranks; scorer columns from `eval_features.json`)

| Case | old best | grid refit | logit refit | anchored | notable single features |
|---|---|---|---|---|---|
| 4-PBA: SLC6A1 given STXBP1 | 1 / 44 | 1 | 1 | 1 | tissue 3 (both brain-enriched), molecular_consequence 1 |
| 4-PBA: STXBP1 given SLC6A1 | 1 / 44 | 1 | 1 | 1 | reactome 2, tissue 2 |
| MEK LOO (10 RASopathies) | 2–3 / 36 | 1–4 | 1–5 | 1–3 | reactome 1–3 for every RASopathy except LZTR1 (33); tissue useless (28.5: all low specificity) |
| MEK from NF1 alone: LZTR1 | 37 | 24 | **11** | 25 | phenotype_systems 3 |
| MEK from NF1 alone: RIT1 / SOS1 | 9 / 8 | 21 / 20 | 12 / 9 | 9 / 8 | reactome 12 / 9; symptoms 7 / 2 |
| miglustat LOO: NPC1, HEXA, GAA, CLN3, GBA1 | 3, 3, 5, 8, 8 / 41 | 8, 5, 7, 8, 8 | 7, 4, 6, 8, 8 | 2, 3, 5, 8, 8 | |
| miglustat from GBA1 alone: HEXA / NPC1 | 7 / 10 | **2 / 3** | 3 / 8 | 9 / 7 | molecular_consequence 1 / 2; phenotype_systems 1 / 5 |

**Did substrate- or tissue-level features pick the right lysosomal disease?**

- **Tissue: no.** HPA calls almost every lysosomal gene "low tissue specificity", so the tissue feature is blank for them, and for most RAS genes too.
- **Substrate: partly, and not in a way this benchmark rewards.**
  - From GBA1 alone, Reactome's top 5 are GALC, GLA, SMPD1, ARSA and HEXA, all sphingolipidoses. That is the biologically sensible set for a glucosylceramide-synthase inhibitor.
  - But miglustat's other known diseases are NPC1 (Reactome: cholesterol transport, rank 29), GAA (glycogen) and CLN3. The links to GAA and CLN3 rest on other rationales.
  - Within the 8 lysosomal candidates in leave-one-out, Reactome's mean rank is 6.0, against 4.5 at random. The best single features there are `protein_domains` (4.0), `mutation_type` (4.2) and `molecular_consequence` (4.4), barely better than random.
- The within-family ordering is still the ceiling, as in section 3.

### Honesty notes (overfitting and circularity)

- **n is small.** 56 cases, 38 classes; one class (MEK, 10 cases) dominates several features. The CIs of every tuned row overlap the old best, and the *direction* of the difference is negative for all three tuners.
- **Selection.** Three tuners plus the post-hoc anchored one were tried, and the final weights were picked by the best honest MRR. Picking the old best is the conservative outcome of that selection, not a winner's curse.
- **Circularity.**
  - The new protein, GO, Reactome, HPA and ClinVar features come from external databases, not from the curators, so they are *less* circular than `mechanism_target`. That is probably part of why they score lower.
  - The families themselves are biology-defined: gene-family, Reactome and compartment similarity largely re-derive "same family". The same-family baseline is MRR 0.26.
- **Unknowns count as negatives**, as before. Reactome's sphingolipidosis ranking for miglustat is penalised, because GALC, GLA and SMPD1 are not labelled positives.
- **Coverage gaps.** Reactome is missing for 4 genes; HPA enriched tissues for 22; G2P / ClinGen for 4. Two features are degenerate or near-degenerate: `shared_gene` (constant) and `tissue`.

## 6. Direction-aware matching (added 2026-10-04)

**Question.** The coarse mechanism class ("loss of function") made ranking worse, and similarity puts contraindicated drugs mid-pool. Does encoding *direction* help? A drug that lowers its target's function should suit a disease with too much function (gain of function), and a drug that raises function should suit a disease with too little (loss of function, haploinsufficiency, destabilisation). The opposite pairing should be penalised.

```bash
# downloads (gitignored, ~7 MB): Open Targets drug_mechanism_of_action + drug_molecule parquet, see the script docstring
uv run -q --with pyarrow --with pandas python3 pipeline/ingest/direction_build.py   # data/derived/direction/, ~2 s
uv run -q --with numpy --with scipy python3 pipeline/eval/direction_eval.py         # data/derived/eval_direction.json, ~30 s
```

### Plain summary

1. We labelled which way each rare disease pushes its gene: too little function or too much. We also labelled which way each drug pushes its target: up or down. Then we rewarded drug–disease pairs that point the right way and penalised pairs that point the wrong way.
2. On 1,300 external PrimeKG drug–disease cases the change makes no measurable difference: MRR 0.375 → 0.379, with an interval that includes zero. A drug's target is a gene of the held-out disease in only 8 of 1,300 cases, and none of the 417 contraindications had a usable direction signal, so contraindications do not move.
3. Direction is right where it applies: the labelled pairs agree with real indications 8 of 8 times, and it gets the sodium-channel cases right at the subtype level. But it is too rarely applicable to change rankings. We show it as an explanation and a warning flag, not as part of the score.

### What was built

- **`data/derived/direction/gene_direction.json`** (1.2 MB). It holds 3,461 disease × gene direction calls over 3,244 MONDO ids: LoF 3,010, GoF 198, mixed 51, and 202 with too little evidence.
  - **Sources, weighted:** G2P mechanism class (1.0; 0.6 if the support is "inferred"), ClinGen HI 3 (0.6, or 0.4 when it is a gene-level score copied onto a disease entry), DisMech step labels that name the gene, keyword-classified (0.8 per step, at most 2; the matched label and keyword are kept as the basis; regexes are in the file), and gnomAD LOEUF < 0.35 (0.2). gnomAD only tips the ratio and never sets a direction on its own.
  - **Rule:** a side is called when it has at least twice the other side's weight and at least 0.5.
  - **Also in the file:** the 45 atlas diseases (from `driven_by` and variant-group `has_effect` edges, weighted by evidence level), and per-variant-group sides, for example SCN2A missense-gof vs truncating.
- **`data/derived/direction/drug_direction.json`** (1.0 MB). It covers 2,954 DrugBank drugs, from **ChEMBL mechanism-of-action action types via the Open Targets Platform bulk parquet**. The ChEMBL REST API returned HTTP 500 during the build, and the ChEMBL MCP needed authorisation. 2,867 of those drugs have at least one directed action.
  - Decrease: inhibitor, antagonist, blocker, negative modulator, ASO/RNAi inhibitor, inverse agonist, degrader.
  - Increase: agonist, activator, opener, positive modulator, stabiliser, exogenous protein or gene.
  - Neutral: modulator, binding agent, enzyme, substrate.
  - The 47 curated atlas therapies are classified from modality and summary, with ChEMBL by name as a fallback; 39 get a direction. Each one records its basis. 8 target overrides are documented in the script: the graph's `target_genes` lists the *disease* genes, not the drug's target. For example, the AChE inhibitor targets ACHE (not SYT2), MEK inhibitors target MAP2K1/2, and the SCN8A ASO targets SCN8A.
- **`transfer_score.py`:** new `direction_compat()` and `DirectionIndex(TransferIndex)` (scorer `"pheno+mech+direction"`, `s_direction`, `score_direction(bonus, penalty)`, and `explain()` gains a `direction` block). The existing APIs are unchanged.

**Score.** `base + bonus·[match] − penalty·[mismatch]`, where `base` = phenotype + 0.5·genes + 0.5·pathway_full (the production global scorer).
- *direct* means a drug target is a directed causal gene of the candidate disease.
- *direct+pathway* adds ±0.5 when a target shares a small lowest-level Reactome pathway (≤ 60 genes) with a directed disease gene.
- **Control:** an *undirected* bonus for "drug target is a disease gene" with direction ignored. It separates the value of direction from the value of target identity.

### (a) PrimeKG indications (n = 1,300, pool 256, 95 drug groups, 2,000 drug-group bootstraps)

| Scorer | MRR [CI] | R@1 | R@5 [CI] | R@10 | Δ MRR vs base [CI] |
|---|---|---|---|---|---|
| base (phen + 0.5 genes + 0.5 pathway) | 0.375 [0.25–0.56] | 0.260 | 0.520 [0.39–0.67] | 0.642 | — |
| **nested direction-aware** (variant, bonus, penalty tuned in 5-fold CV) | 0.379 [0.26–0.56] | 0.264 | 0.524 [0.39–0.68] | 0.645 | +0.004 [−0.001, +0.013], P(better) 0.94 |
| nested undirected target bonus (control) | 0.375 [0.25–0.56] | 0.259 | 0.519 | 0.643 | +0.000 [−0.001, +0.002] |
| fixed direct 0.5 / 0.5 | 0.377 | 0.261 | 0.523 | 0.645 | +0.002 [−0.000, +0.005] |
| fixed direct+pathway 0.5 / 0.5 | 0.377 | 0.261 | 0.526 | 0.644 | +0.002 [−0.001, +0.005] |
| penalty only (direct, 0 / 1) | 0.375 | 0.260 | 0.520 | 0.642 | 0.000 |
| *gene-level fallback labels, nested* | *0.377* | *0.264* | *0.522* | *0.642* | *+0.002 [−0.003, +0.012]* |

- **Fold choices.** Bonus 1.0 in all folds; penalty 0.5 in 4 folds and 0.1 in 1. The penalty never fires on a held-out indication.
- **Direction minus the undirected control:** +0.004 [−0.000, +0.012].
- **Coverage, which is the binding limit:**
  - 158 of 257 drugs have a directed ChEMBL action.
  - 68 of 256 pool diseases have a directed gene (167 with the gene-level fallback).
  - But the drug's target is a directed gene of the held-out disease in only **8 of 1,300 cases**, all 8 matches. Examples: testosterone → androgen insensitivity (AR LoF / agonist), diazoxide → familial hyperinsulinism (KCNJ11 LoF / opener), migalastat → Fabry (GLA LoF / stabiliser), ruxolitinib → polycythemia vera (JAK2 GoF / inhibitor).
  - Over all 65,792 drug × pool pairs, 17 are non-zero (15 match, 2 mismatch).
  - The pathway extension reaches 17 held-out cases (16 match, 1 mismatch), but over all pairs it is 117 match vs 96 mismatch. **Pathway-level direction is close to a coin flip**, because "inhibit a neighbour of a LoF gene" has no fixed meaning.

### (b) PrimeKG contraindications (417 pairs; context = all indications)

| Scorer | Mean percentile before → after (0 = top) | Shift toward bottom [CI] | Pairs with a direction signal |
|---|---|---|---|
| direct 0.5 / 0.5 | 0.480 → 0.480 | 0.000 [0, 0] | **0** |
| direct 1 / 1 and the nested refit | 0.480 → 0.480 | 0.000 [0, 0] | 0 |
| direct+pathway 0.5 / 0.5 | 0.480 → 0.479 | −0.002 [−0.007, +0.001] | 2, both "match", so they move *up* |
| gene-level fallback, direct+pathway | 0.480 → 0.479 | −0.001 [−0.010, +0.005] | 8, all "match" |

- **Contraindications do not move toward the bottom.** No contraindicated disease has a drug target among its directed genes.
- PrimeKG contraindications are mostly clinical: hypertension, glaucoma, pregnancy-adjacent and organ-failure states, not "wrong direction on the disease gene".
- The textbook case is missing from PrimeKG: it has no phenytoin, carbamazepine or lamotrigine contraindication for Dravet syndrome. It links Dravet only to cannabidiol and stiripentol, as indications.

### (c) Atlas: sodium-channel cases and the 56-case benchmark

**Contested pairs** (`family_dee.json` counter_evidence). Two levels of labels are compared: gene-level labels from the graph, and variant-group (subtype) labels.

| Therapy → disease | Drug | Gene-level label → compat | Subtype compat |
|---|---|---|---|
| sodium-channel blockers → SCN1A (Dravet) | decrease | LoF → **−1 (mismatch, correct)** | missense-gof +1; truncating / splice / deletion −1 |
| sodium-channel blockers → SCN2A | decrease | mixed → 0 | missense-gof **+1**; missense-lof / truncating −1 |
| sodium-channel blockers → SCN8A | decrease | mixed → 0 | missense-gof **+1**; missense-lof / truncating −1 |
| zorevunersen (SCN1A upregulating ASO) → SCN1A | increase | LoF → +1 | missense-gof −1 (the phase 3 trial excludes GoF: correct) |
| Kv7 openers → KCNQ2 | increase | LoF → +1 | missense-gof −1 (the trial excluded GoF: correct) |
| KCNT1 ASO, quinidine → KCNT1 | decrease | GoF → +1 | missense +1 |
| relutrigine, NBI-921352 → SCN2A / SCN8A | none (no ChEMBL MoA, summary silent) | 0 | — |

- **Subtype level.** There the rule reproduces every curated counter-evidence statement: blockers help GoF and harm LoF, and upregulators exclude GoF.
- **Gene level.** There SCN2A and SCN8A are "mixed", so they are neutral, because one atlas disease node covers both allelic directions.
- **Automated MONDO-level labels miss the GoF subtypes:**
  - SCN2A DEE11 (MONDO:0013388) gets only a gene-level ClinGen HI score: too weak, so no call.
  - SCN8A DEE13 (MONDO:0013801) is "mixed": G2P says dominant negative, DisMech says GoF.
  - Dravet (MONDO:0100135) has no G2P / ClinGen / DisMech entry under the current id. This is the obsolete-id issue already in CLAUDE.md.
- **ChEMBL agrees on the drug side:** phenytoin, carbamazepine, lamotrigine, oxcarbazepine, lacosamide, rufinamide and zonisamide are all BLOCKERs of SCN1A/2A/3A….

**56-case benchmark (eval.md section 2, production `pheno+mech`).**

| Scorer | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|
| pheno+mech (production) | 0.293 | 0.602 | 0.731 | 0.491 |
| + direction, bonus = penalty ∈ {0.25, 0.5, 1} | 0.565 | 0.792 | 0.857 | 0.696 |
| + direction, penalty only 0.5 | 0.293 | 0.602 | 0.731 | 0.491 |
| **+ undirected "target gene = disease gene" bonus 0.5 (leakage control)** | **0.630** | **0.843** | **0.896** | **0.750** |

**This jump is leakage, not direction.**
- The curated therapies' targets are the genes of the diseases they were developed for. In 32 of the 56 cases the held-out disease's gene is a listed target.
- So any target bonus "finds" the hidden disease. The undirected control scores even higher than the direction-aware one.
- Coverage: 22 of 56 held-out cases get a non-zero direction (21 match, 1 mismatch). The penalty never fires on a held-out positive, so it changes nothing.

### Recommendation

1. **Do not add direction to the ranking score.** It is neutral on PrimeKG, with a gain of +0.004 whose interval includes 0, and it is circular on the atlas benchmark.
2. **Use it as a flag next to a candidate.** Show "direction mismatch: this drug lowers SCN1A function; Dravet is SCN1A loss of function (G2P / ClinGen / atlas edges)" as a caution, and "direction match" as an explanation. Use `DirectionIndex.explain()["direction"]` or `direction_compat()`.
   - The flag is reliable when it fires: 8/8 indications match, and the sodium-channel, Kv7 and KCNT1 subtype cases are all correct.
   - It fires only when the drug's target is the disease gene. Keep pathway-level direction out: it is about 55/45.
3. **Apply it at subtype (variant-group) level, not gene level.** One gene-level disease node mixes GoF and LoF in SCN2A, SCN8A, KCNQ2, STXBP1 and CACNA1A. The variant-aware VCF checker is the natural place: missense-gof vs truncating.
4. **Contraindications still need their own field from the label** (ingest.md section 5). Direction does not recover them from PrimeKG.

### Limitations

- Disease direction comes from keyword and class rules. DisMech keywords on gene-named steps can misfire, and the basis text is kept so a reviewer can check. G2P's "dominant negative" is counted as LoF.
- ChEMBL MoA covers mostly approved drugs. 99 of the 257 benchmark drugs have no directed action, mainly corticosteroids, cytotoxics and biologics against non-gene targets.
- The evaluation was designed once and not re-tuned. The gene-level fallback and the pathway variant are reported as sensitivity analyses, not as the primary result.

## 7. AI-reviewed links: hidden vs included (2026-10-04)

The 142 links proposed by the independent Claude reading and accepted by an AI review (`data/curated/claude_reviewed.json`) are hidden from the benchmark by default (`transfer_score._ai_proposed_ai_reviewed`). Sensitivity run: `EVAL_INCLUDE_AI_REVIEWED=1 python3 pipeline/eval/transfer_eval.py` (writes `data/derived/eval.json`; rerun without the variable afterwards).

| Scorer | Hidden (default): n | R@5 | MRR | Included: n | R@5 | MRR |
|---|---|---|---|---|---|---|
| random | 56 | 0.12 | 0.10 | 58 | 0.12 | 0.10 |
| phenotype | 56 | 0.46 | 0.30 | 58 | 0.50 | 0.29 |
| mechanism | 56 | 0.63 | 0.41 | 58 | 0.68 | 0.43 |
| **pheno+mech (site)** | 56 | **0.72** | **0.48** | 58 | **0.79** | **0.50** |
| mech+cluster | 56 | 0.69 | 0.43 | 58 | 0.75 | 0.47 |
| combined | 56 | 0.70 | 0.46 | 58 | 0.79 | 0.48 |
| mech-similarity | 56 | 0.39 | 0.32 | 58 | 0.40 | 0.31 |
| same-family | 56 | 0.42 | 0.26 | 58 | 0.44 | 0.26 |
| naive-driven_by | 56 | 0.35 | 0.22 | 58 | 0.40 | 0.27 |
| hypotheses-rule | 56 | 0.62 | 0.38 | 58 | 0.62 | 0.37 |
| mech+cluster-leaky (control) | 56 | 0.82 | 0.60 | 58 | 0.84 | 0.64 |

Reading: the ranking of methods does not change (pheno+mech and combined stay on top; the leaky control stays above everything). Including the AI-reviewed links adds 2 test cases (mirdametinib → RIT1, miglustat → HEXA; the statin → PTPN11 link merges into an existing class) and new mechanism links (e.g. RAS-pathway `driven_by`), which lift most scorers by 0.04–0.07 top-5. That gain rests on AI-found, AI-reviewed links from the same literature, so the published numbers stay the hidden ones until a person reviews the links. The PrimeKG benchmark uses the global layer, not the curated graph, so it is unaffected (it needs `data/raw/downloads/` to rerun).
