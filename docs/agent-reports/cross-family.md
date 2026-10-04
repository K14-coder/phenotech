# Cross-family biology: specific mechanisms that join the four families

**Question.** Only 11 of 45 deep diseases shared a *specific* (non-LoF/HI/GoF/DN) mechanism with a disease in another
family, and the RASopathy LZTR1/RIT1 → MAPK link was missing (`gap:ras-to-mapk-hierarchy`). Which specific,
evidence-backed links exist between the families?

```bash
python3 pipeline/families/cross/fetch.py <PMIDs...>     # stores abstracts (NCBI <= 2 req/s, tool=tasukeru, no email)
python3 pipeline/families/cross/quickgo.py              # GO annotation matrix, 45 genes x 9 candidate terms
python3 pipeline/families/cross/build.py                # writes data/curated/cross_family.json; exits 1 on any unverified quote
python3 pipeline/build_graph.py                         # Problems: None
python3 pipeline/eval/transfer_eval.py
```

- **Output:** `data/curated/cross_family.json`, with 24 edges, 1 new node (`mech:autophagy`, GO:0006914) and 2 gaps.
- **Quotes:** 40 PubMed quotes from 35 PMIDs. Every one is a normalised substring of the stored title and abstract in
  `data/raw/families/cross/pubmed/`. `build.py` checks this and refuses to write otherwise, and an independent re-check
  after the build found 0 failures.
- **GO evidence:** it comes from stored QuickGO searches (`data/raw/families/cross/quickgo/`, which is gitignored; re-run
  `quickgo.py` to recreate it).
- **Endpoints:** every endpoint is an existing atlas node, except `mech:autophagy`.
- **Searches:** all PubMed queries are logged in `data/raw/families/cross/pubmed_searches.json`.
- **Boundaries:** no OpenAI was used. Nothing outside the allowed paths was edited by hand; `data/graph.json`,
  `data/build/report.md` and `data/derived/eval.json` were regenerated.

## Before and after

| Measure (evidence-backed edges only; `transfer_eval.py`) | Before | After |
|---|---|---|
| Diseases linked to **another family** by a specific mechanism | **11/45 (24%)** | **29/45 (64%)** |
| Diseases linked to any other disease by a specific mechanism | 39/45 | 43/45 |
| Disease pairs sharing a specific mechanism | 162/990 | 243/990 |
| Pairs connected through specific mechanisms only | 571/990 (57.7%), median 7 hops | 903/990 (91.2%), median 6 hops |
| Specific mechanisms bridging families | 3 | 7 |

**Newly cross-linked diseases (18):**
- DEE: CACNA1A, CDKL5, KCNQ2, SCN1A;
- lysosomal: CLN3;
- SNARE: SYT1, SYT2;
- RASopathies: BRAF, CBL, HRAS, KRAS, MAP2K1, NF1, PTPN11, RAF1, RIT1, SHOC2, SOS1.

Before this work, only LZTR1 linked the RASopathies to another family; now every one of the 12 does.

**Caveat on the count.** Eight of the RASopathies (BRAF, CBL, KRAS, MAP2K1, RAF1, RIT1, SHOC2 and SOS1) cross
families only through MAPK cascade, which is shared with SYNGAP1. Their cross-family status therefore rests on one
edge, SYNGAP1 → MAPK cascade, though that edge has three independent papers. LZTR1 was already linked to SYNGAP1
through negative regulation of Ras signalling. HRAS, NF1 and PTPN11 have independent second bridges (synaptic
plasticity, and mTOR for NF1).

### Bridging mechanisms now (families · diseases)

| Mechanism | Families | Diseases |
|---|---|---|
| MAPK cascade | DEE + RAS | SYNGAP1 + 12 RASopathies |
| Regulation of synaptic plasticity | all four | GRIN2B, SYNGAP1, VAMP2, **HRAS, NF1, PTPN11, GBA1** |
| TOR (mTOR) signalling (was empty) | DEE + RAS + lysosomal | **SYNGAP1, CDKL5, NF1, NPC1, GBA1, GAA** |
| Protein destabilization / misfolding | DEE + lysosomal + SNARE | GAA, GBA1, GLA, HEXA, NPC1, SLC6A1, STXBP1, VAMP2, **SCN1A, KCNQ2** |
| Ca2+-triggered neurotransmitter exocytosis | DEE + SNARE | STXBP1, SYT1, SYT2, VAMP2, **CACNA1A** |
| Autophagy (new node) | DEE + lysosomal | **CDKL5, CLN3, GAA, GBA1, NPC1** |
| Negative regulation of Ras signalling | DEE + RAS | LZTR1, SYNGAP1 (unchanged) |

## The new links (all `participates_in` unless marked)

**1. RAS → MAPK, which resolves `gap:ras-to-mapk-hierarchy` at gene level.**

| Edge | Evidence (PMID) | Level / confidence |
|---|---|---|
| LZTR1 → MAPK cascade | 30442766 (LZTR1 loss enhances MAPK activity), 30481304 (dominant NS mutations enhance RAS-MAPK signalling through a larger RAS pool), 31337872 (LZTR1 degrades RAS, inhibiting ERK) | experimental, 0.85 |
| RIT1 → MAPK cascade | 25959749 (increased MEK-ERK signalling), 23791108 (enhanced ELK1 transactivation), 30872527 (pathogenic RIT1/LZTR1 mutations block RIT1 degradation) | experimental, 0.85 |
| RIT1 → Ras protein signal transduction | GO:0007265 (IDA, IBA) + 23791108 | curated, 0.9 |
| SOS1 → MAPK cascade | 17143285, 17143282 (NS mutants enhance RAS and ERK activation) | experimental, 0.85 |
| CBL → MAPK cascade | 20694012 (constitutive ERK phosphorylation), 25178484 (enhanced ERK phosphorylation, aberrant EGFR trafficking) | experimental, 0.8 |

No `part_of` edge was added between Ras signal transduction and the MAPK cascade. GO has no such path, and the
gene-level edges carry the link without inventing a hierarchy. The gap entry in `mechanism_hierarchy.json` (not ours to
edit) can now be closed or marked "answered by cross_family.json".

**2. SYNGAP1 (DEE) ↔ RASopathies.**

| Edge | Evidence | Level / confidence |
|---|---|---|
| SYNGAP1 → MAPK cascade | 12427827 (raised basal ERK2 in SynGAP+/− mice), 16537406 (ERK activation up in knockout neurons), 29940508 (MEK/ERK hyperphosphorylation in Syngap1+/− mice) | experimental, 0.85 |
| SYNGAP1 → mTOR signalling | 24391850 (SynGAP regulates translation through ERK, mTOR, Rheb) | experimental, 0.6 |

The same papers state limits, and the edge explanation repeats them:
- SynGAP's role in LTP likely involves targets other than ERK (12427827).
- A MEK inhibitor normalised basal transmission but not the LTP deficit (29940508).

**3. mTOR signalling (the node existed but had no genes).**

| Edge | Evidence | Confidence |
|---|---|---|
| NF1 → mTOR | 15937108 | 0.65 |
| CDKL5 → mTOR | 30288694, 23236174 (two mouse models) | 0.75 |
| NPC1 → mTOR | 33308480, 31548609 | 0.8 |
| GBA1 → mTOR | 31519738 (iPSC neurons) | 0.6 |
| GAA → mTOR | 28130275 | 0.6 |

**4. Synaptic plasticity.**

| Edge | Evidence | Confidence |
|---|---|---|
| PTPN11 → regulation of synaptic plasticity | 25383899, 30837304 | 0.8 |
| NF1 → regulation of synaptic plasticity | 18984165 | 0.6 |
| HRAS → regulation of synaptic plasticity | 20937865, 28455524 | 0.75 |
| GBA1 → regulation of synaptic plasticity | 39562000 | 0.5 |

- HRAS: 28455524 also reports that LTP was unaffected, so the plasticity change in HRAS mice is in LTD.
- GBA1: the evidence is a heterozygous L444P Parkinson-risk mouse, not Gaucher disease.

**5. Neurotransmitter release.**
- **CACNA1A → Ca2+-triggered neurotransmitter exocytosis** (20631222, 18293354; 0.75). CaV2.1 supplies the trigger
  Ca2+. Gain-of-function S218L knock-in mice release more transmitter, and loss-of-function leaner mice release less.
  GO does not annotate CACNA1A to GO:0048791, so this edge is literature-only.

**6. Misfolding (`has_effect`), which extends the chaperone bridge into the DEE.**
- **vg:SCN1A:missense → protein destabilization** (19402159, 25576396; 0.75). Folding-defective NaV1.1 mutants can be
  rescued by low temperature, interacting proteins or phenytoin. This applies to a subset of missense variants.
- **vg:KCNQ2:missense-lof → protein destabilization** (34020651; 0.55). One variant, W344R, misfolds during
  translation.

**7. Autophagy (new node `mech:autophagy`, GO:0006914).**
- **CDKL5 → autophagy** (42779792, 37917202; 0.7). CDKL5 drives selective autophagy of protein aggregates, and
  CDKL5-deficient brains accumulate insoluble aggregates.
- **GBA1, NPC1, GAA, CLN3 → autophagy.** Each has a GO annotation (IMP, IGI, IMP and ISS/IEA respectively) plus a
  quoted paper (31519738, 31548609, 28130275, 34964690). These are curated, at 0.9, 0.9, 0.9 and 0.8.

### Systematic GO check (`quickgo_matrix.json`, 45 genes × 9 terms, descendants included)

| GO term | Genes annotated |
|---|---|
| MAPK cascade | BRAF, HRAS, KRAS, MAP2K1, NF1, RAF1 (not LZTR1, RIT1, SOS1, SYNGAP1 or CBL, hence the literature edges) |
| TOR signalling | none |
| Autophagy | CLN3, GAA, GBA1, NPC1 |
| Neurotransmitter secretion | 9 SNARE-family genes, but no DEE gene |
| Regulation of synaptic plasticity | GRIN2B, SYNGAP1, VAMP2, CLN3 (IEA/ISS only, not added) |
| Response to ER stress | none of the 45 |

GO alone therefore produces almost no cross-family links. The bridges come from the functional literature.

## Effect on the transfer benchmark (56 developed_for cases)

| Scorer | R@5 before → after | MRR before → after |
|---|---|---|
| (c) Mechanism | 0.59 → **0.63** | 0.40 → 0.41 |
| (d) Phenotype + mechanism (recommended) | 0.73 → 0.73 | 0.49 → 0.48 |
| (f) Combined | 0.70 → 0.70 | 0.46 → 0.46 |
| Transfer subset (c) | 0.57 → **0.66** | 0.43 → 0.44 |
| hypotheses.py chain rule | 0.65 → 0.62 | 0.41 → 0.38 |

All changes are well inside the bootstrap intervals.

**What changed, case by case.**
- **MEK inhibitors:** the mechanism scorer now ranks LZTR1, RIT1 and SOS1 at 2.5, up from 19. This is the intended fix:
  the MEK target now reaches them.
- **Cost of the larger tie set:**
  - NF1, PTPN11 and RAF1 drop from 1.5 to 2.5, because SYNGAP1 and CBL now tie with them on MAPK.
  - The aminopyridine cases move from 2.0 to 2.5, because CACNA1A now ties on exocytosis.
- **Rapamycin for NSML (PTPN11):** it falls from 23 to 26, because six diseases now reach mTOR and PTPN11 does not. The
  only PTPN11–mTOR evidence in the atlas is PMID 21339643, the same paper the rapamycin `developed_for` edge rests on.
  Adding PTPN11 → mTOR from that paper would leak the answer into the benchmark, so it was deliberately left out.

**Reading.** The benchmark is built around therapies whose targets are mostly family-specific, so cross-family links
cannot raise it much. The new links mostly add plausible candidates in other families, for example SYNGAP1 for MEK
inhibitors. With no known `developed_for` edge, those count as misses. A cross-family "hit" can only be scored once a
therapy is actually tested across families. Treat SYNGAP1 ↔ MEK/statin and CDKL5/NPC1 ↔ mTOR as hypotheses to look at,
not findings.

## What remains unproven or missing

- **Still not cross-linked (16):**
  - DEE: KCNT1, SCN2A, SCN8A, SLC2A1;
  - lysosomal: ARSA, GALC, IDS, IDUA, SMPD1, TPP1;
  - SNARE: CPLX1, NSF, SNAP25, STX1A, STX1B, UNC13A.

  SNAP25 and STX1B have GO edges to Ca2+-triggered exocytosis (and so would join CACNA1A). Those edges are IEA-only and
  are correctly marked `inferred`, which excludes them from the evidence-backed count. They were not upgraded.
- **ER stress / UPR:** no annotation for any of the 45 genes, and no abstract we checked shows UPR activation in DEE or
  SNARE patient cells. Recorded as `gap:cross-er-stress`.
- **RASopathy excitability and calcium:**
  - NF1 loss reduces HCN current and raises interneuron excitability (25917366, 35589737).
  - SHP2 Noonan mutants enhance cardiomyocyte Ca2+ oscillations (16461457).

  Neither maps onto an existing mechanism node, so no edge was added. Recorded as `gap:cross-rasopathy-calcium-excitability`.
- **Lysosomal ↔ SNARE vesicle trafficking:** searches for CLN3/TPP1 together with synaptic-vesicle, SNARE or
  neurotransmitter-release terms found yeast Btn1 and PPT1/CLN1 papers only. PPT1 is not an atlas disease. Nothing was
  quotable for the atlas genes.
- **Model systems:** most new edges come from mouse or cell models, not patients. CDKL5 → autophagy rests partly on a
  2026 paper and a viral-autophagy paper. KCNQ2 misfolding is shown for one variant. GBA1 plasticity comes from a
  Parkinson-risk heterozygote.
- **Hypotheses:** `pipeline/derive/run.sh` was not re-run, so `hypotheses.json` does not yet use these links (see the
  TODO follow-up).
