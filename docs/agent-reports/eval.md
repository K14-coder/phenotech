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
