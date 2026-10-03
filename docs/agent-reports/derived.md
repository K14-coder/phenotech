# Derived data products: agent report

Five derived products built on top of `data/graph.json` (the merged SNAREopathy slice: STXBP1,
SYT1, SNAP25, VAMP2, STX1B, SYT2, CPLX1, UNC13A, STX1A, NSF + the bridge gene SLC6A1).
Generated 2026-10-03. Rebuild everything with:

```bash
./pipeline/derive/run.sh            # cached sources, offline after the first run, well under a minute
./pipeline/derive/run.sh --refresh  # also re-fetch the PubMed / CT.gov records and mondo-base.obo
```

Code: `pipeline/derive/{dcommon,hgvs,variants,modality,hypotheses,beyond_slice,counterexamples,global_index,atlas_flags,mechanism_index,fetch_literature,lit_search}.py`,
`run.sh`. The global index step runs under `uv run --with numpy --with scipy` (the other steps are stdlib).

| File | Size | What it is |
|---|---|---|
| `data/derived/variants.json` | 321 KB | 1,350 ClinVar P/LP variants across the 11 genes + a 2,294-key lookup index |
| `data/derived/variant_lookup_spec.md` | 9.6 KB | the parsing rules and regexes, written to be ported to TypeScript |
| `data/derived/variant_test_cases.json` | 4.6 KB | 20 query → expected-result cases (all 20 pass) |
| `data/curated/modality.json` | 175 KB | 11 diseases x 6 modalities, 27 published rules, 54 quoted citations |
| `data/curated/hypotheses.json` | 41 KB | 5 `candidate_for` edges (SCHEMA fragment) + 1 gap |
| `data/derived/opportunities.json` | 149 KB | node-free: 41 model/assay transfer pairs, 17 rejected candidates, 24 approach-only transfers, 3 near-misses |
| `data/derived/beyond_slice.json` | 54 KB | top 8 phenotype neighbours outside the slice, per disease, out of 10,495 compared |
| `data/derived/counterexamples.json` | 23 KB | 10 places where the clean pattern breaks, each with real edge ids |
| `data/derived/global/index.json` | 1.6 MB | **every** disease with HPO annotations or a gene: 11,456 MONDO-merged rows for search |
| `data/derived/global/neighbours/<0..63>.json` | 14.3 MB in 64 shards (max 441 KB) | per-disease page data for 8,787 diseases: top 10 phenotype neighbours, own distinctive features, inheritance, distance to the 11 |
| `data/derived/global/meta.json` | 11 KB | counts, release versions, URL templates, caveat, threshold calibration, sanity checks |
| `data/derived/global/README.md` | 19 KB | schema, the djb2 shard function with test vectors, search recipe, mechanism layer, UI guidance |
| `data/derived/global/mechanism/<0..63>.json` | 6.1 MB in 64 shards (max 224 KB) | per disease: curated mechanism class (G2P, ClinGen), ClinGen validity, Reactome pathways, mechanism cluster, mechanism neighbours |
| `data/derived/global/clusters.json` | 0.6 MB | 225 mechanism clusters: label, size, top pathways, mechanism mix, distinctive phenotypes, members, rationale |

Nothing outside `pipeline/derive/`, `data/derived/`, `data/curated/{modality,hypotheses}.json`,
`data/raw/derive/` and `data/raw/downloads/mondo-base.obo` (gitignored) was touched. `data/graph.json` was read only. No OpenAI call was made.

## Evidence integrity

Same rules as the rest of the atlas, enforced in code:

- Every literature claim carries a **verbatim quote**. `dcommon.quote_for(ref, needle)` extracts the
  single sentence containing a short needle from the stored source
  (`data/raw/derive/pubmed/<PMID>.json`, fetched by `fetch_literature.py`). A needle that matches
  zero or more than one sentence **raises**, so a quote that is not in the source cannot be stored.
  `dcommon.verify_quote` then re-reads the file and sets `verified` on an exact normalised-substring
  match. `modality.py` exits non-zero if any quote is unverified: **54/54 verified, 0 failures.**
- 60 PubMed records and 5 ClinicalTrials.gov records are stored under `data/raw/derive/`. Every
  search run while curating the rules is logged in `data/raw/derive/search_log.json` (term, date,
  PMIDs returned).
- NCBI etiquette is inherited from `pipeline/biology/common.py`: the same cross-process file-lock
  throttle (< 2 req/s shared with the biology layer), `tool=rare-disease-atlas`, **no email
  parameter**, exponential backoff honouring `Retry-After`.
- No id, PMID or quote is invented. `counterexamples.py` fails the build if any `edge_id` is absent
  from `data/graph.json`; `hypotheses.py` only ever emits ids that already exist.
- Hypotheses are labelled as hypotheses: `evidence_level: "hypothesis"`, `status: "unverified"`,
  confidence ≤ 0.25, and the word HYPOTHESIS opens every explanation.

## 1. Variant lookup (`variants.json`, `variant_lookup_spec.md`, `variant_test_cases.json`)

A family pastes a line from a genetic report and gets the variant, its consequence class and the
graph's variant group.

- Source: the stored ClinVar esummary files in `data/raw/biology/clinvar/` (the biology layer's
  P/LP-only query). Per variant: `accession`, `url`, `hgvs` (the ClinVar title), `p` (canonical
  1-letter protein change), `protein_change` (ClinVar's per-isoform list), `consequence`
  (normalised to nonsense / frameshift / splice / missense / inframe_indel / cnv / synonymous /
  other), `classification`, review `stars`, `n_submissions`, and the matching `vg:<GENE>:...` node.
- Rows are stored as arrays with a shared `fields` header, so nothing is duplicated: 1,350 variants
  in 321 KB.
- The index has three key kinds: `c:<GENE>:<c.>`, `p:<GENE>:<protein>` and `iso:<GENE>:<protein>`
  (the same change as numbered on another isoform — a match there warns the user to confirm the
  transcript).
- Per gene it also carries `by_consequence`, `null_like_share`, `recurrent_residues` (residues with
  ≥ 2 distinct pathogenic alleles, e.g. STXBP1 R406/G544/R551, SLC6A1 G75/A357) and `most_reported`.
  The modality screen reads these.

**How the UI should use it.** Load once (321 KB, gzips well), port `hgvs.py` from the spec, and run
the lookup client-side. Show the scope note from `meta.scope_note` on every miss: *not in ClinVar's
P/LP records* is not *benign* and not *not real*. On a hit, link `url` straight to ClinVar and link
`variant_group` into the graph so the family can walk variant → group → mechanism. On a miss, show
the fallback consequence with its `certainty` and the sentence "the type shown is read from the
notation only".

Worked examples: `STXBP1 c.1162C>T p.Arg388*`, `R388X` and `NM_003165.6(STXBP1):c.1162C>T` all
resolve to VCV000006730 (the last one with a transcript warning, because ClinVar's title uses
NM_001032221.6). `SLC6A1 p.Ser295Leu` — the variant in the n=1 AAV9 trial — is a **miss**: it is not
among ClinVar's P/LP records, so it falls back to "missense → `vg:SLC6A1:missense`".

`meta.qa_differences_vs_graph_group_counts` records 9 genes where the per-record consequence here
differs from the `clinvar_counts` on the graph's variant_group nodes (biggest: SLC6A1 truncating 73
here vs 60 on the node, because the biology classifier routes some small indels annotated to two
overlapping genes into the multi-gene CNV group). The lookup deliberately uses the per-record
consequence, which is the right one for a family reading their own report.

## 2. Modality fit (`data/curated/modality.json`)

Marked **"draft rule set; awaiting expert review"** at the top, with a `not_advice` paragraph. It is
a screen for a biotech scout and for patient-group leaders, not advice.

- 6 modalities: AAV gene replacement; ASO/siRNA knockdown (total or allele-specific); transcript
  upregulation (TANGO/NMD- or uORF-targeting ASO, or CRISPRa); chemical/pharmacological chaperone;
  symptomatic pathway small molecule (3,4-DAP, 4-AP, cholinesterase inhibitors); gene editing.
- **27 rules, published inside the file** (`rules[]`), each with an id, its condition in words, the
  fit it votes for, a one-sentence rationale and its citations. The engine fires the rules that
  apply and takes the **worst** fit any rule voted — one blocking rule is never averaged away.
- Gene-level checks, taken from the graph where possible, are in `assessments[d].checks`:
  AAV packaging (`cds_length_bp`, `aav_cds_fits_4_7kb`); the ClinVar variant-class mix with
  `allele_specific_plausible` and the recurrent residues; `minority_mechanisms` and
  `contested_mechanisms` (from `attrs.minority_mechanism` and edge status on `driven_by`);
  target tissue (CNS vs CNS + neuromuscular junction, derived from myasthenic subtypes and
  neuromuscular HPO terms); published overexpression data; existing programmes with their trial
  status; and `stopped_programmes` (the terminated STXBP1 AAV trial).
- Output per disease × modality: `{fit, reasons[], caveats[], citation_ids[], graph_edge_ids{},
  rules_fired[], open_questions_for_expert[]}`. Quotes live once in the top-level `citations` map,
  so 196 citation links cost 54 stored quotes.
- Distribution: 2 good, 48 conditional, 16 poor. The conservative aggregation is deliberate: in this
  slice almost every gene has at least one variant class pointing the other way. The two "good" are
  **3,4-DAP/cholinesterase inhibitors for SYT2** (an existing, evidence-backed option) and
  **ASO knockdown for UNC13A** (documented, non-minority gain of function).
- `R-VAL-1` caps every modality at *conditional* for a gene whose validity or mechanism is recorded
  as a gap (STX1A, NSF, CPLX1), so a thin gene can never score "good".

**How the UI should use it.** One row per modality on the disease page, colour by `fit`, and make
`rules_fired` expandable — the point of this product is that a scout can see *why*, disagree with a
named rule, and still trust the rest. Render `open_questions_for_expert` as the "what we'd ask an
expert" block, and put the `status` and `not_advice` strings somewhere unmissable. There is room for
a rare-disease advisor's checklist later: `meta.expert_review_checklist` says what it should record.

## 3. Hypotheses (`data/curated/hypotheses.json` + `data/derived/opportunities.json`)

The search: a therapy T `targets` a mechanism M; a disease D is linked to M; there is **no**
`developed_for` T→D and **no** study that both `tests` T and `studies` D. Chain kinds, strongest
first: `driven_by` (D→M directly), `variant_group` (causes + variant_in + has_effect), `pathway`
(causes + participates_in), `cluster` (a curated cluster already groups T and D). The pathway and
cluster chains are included because **no `driven_by` edge in this graph points at a GO process**, so
without them every process-targeting drug — the aminopyridines, the cholinesterase inhibitors —
would be invisible. They are scored lowest and named as the weakest link.

Two filters stop nonsense:

- **Product transferability.** A gene-specific product (an AAV vector, a gene-targeted ASO, a
  chaperone designed against one protein's structure) cannot be handed to another gene. 24 such
  matches became `approach_transfer_not_product` entries in `opportunities.json` instead of edges.
- **Therapy equivalence.** Amifampridine, 3,4-DAP and the aminopyridine class are one class;
  the AAV products had duplicate nodes. "Already addressed" is tested over the whole class, so
  **3,4-DAP → SNAP25 is correctly rejected, not emitted**: the rejection record names
  `therapy:aminopyridine-presynaptic-boost|developed_for|disease:SNAP25` *and* NCT02562066, whose
  eligibility quote is "Genetically confirmed CMS of several types, explicitly including SYT2 and
  SNAP25B deficiency". 17 candidates were rejected this way.

5 hypotheses survived (max 6; quality over count). All are `candidate_for`, `hypothesis`,
`unverified`, confidence ≤ 0.25, with `attrs.caveats[]`, `attrs.test{what_to_test,
existing_assay_or_model, what_result_would_change_the_plan}` and `attrs.weakest_link`.

| conf | hypothesis | chain | weakest link |
|---|---|---|---|
| 0.18 | **4-PBA for VAMP2** | `driven_by` | the VAMP2 destabilization edge itself: contested, one 2025 paper, and its "stability" defect is a SNARE-complex property, not the degradation-and-rescue event 4-PBA is known to act on |
| 0.14 | **Cholinesterase inhibitors for the SNAP25 myasthenic presentation** | `pathway` | the drug argument needs a neuromuscular junction, and whether SNAP25-DEE patients have one has never been measured (`gap:snap25-cms-vs-dee`) |
| 0.12 | **Aminopyridines for STXBP1 variants that reduce release** | `pathway` | pathway-only chain plus a contested mechanism: the direction of STXBP1's own release defect is disputed |
| 0.12 | **Aminopyridines for the loss-of-function end of STX1B epilepsy** | `pathway` | the gene's variants point both ways, so only a variant-level hypothesis survives |
| 0.06 | **Aminopyridines for the UNC13A presynaptic myasthenic presentation** | `cluster` | UNC13A reaches the drug class only through the curated presynaptic-NMJ cluster; no mechanism edge connects it to Ca2+-triggered exocytosis |

**The three checks the brief asked for, answered:**

1. **Is 4-PBA defensible for VAMP2?** Yes, as a hypothesis, and it is the strongest one here — it is
   the only candidate whose chain is `driven_by` on both ends. VAMP2 does carry a protein-
   destabilization edge (PMID:41166419) and 4-PBA does target that mechanism. But the edge is
   contested, only 7 of 35 pathogenic VAMP2 records are missense, synaptobrevin-2 is natively
   unstructured outside the SNARE complex (PMID:29949059) so "destabilization" may not be the same
   event 4-PBA acts on, and some VAMP2 variants *increase* spontaneous release. Not a treatment
   suggestion; a bench experiment with a named negative control.
2. **3,4-DAP for SNAP25?** **Not a gap.** The completed amifampridine CMS trial already lists
   SNAP25B deficiency in its eligibility criteria. The search rejects it and records why. What
   remains open is the *cholinesterase inhibitor* arm and, more usefully, whether SNAP25-DEE
   patients have subclinical neuromuscular involvement at all.
3. **3,4-DAP for UNC13A?** A genuine gap, and the weakest chain in the file. UNC13A is **not** in
   the amifampridine eligibility list, and the recessive truncating presentation is a presynaptic
   failure with a depleted readily releasable pool (PMID:27648472). But UNC13A links to vesicle
   *priming* in the graph, not to the drugs' target mechanism, and three mechanisms coexist in this
   gene including gain of function (PMID:41125872).

One candidate was **rejected on review** and is kept visible in
`opportunities.json → computed_candidates_rejected_on_review`: cholinesterase inhibitors for SYT1.
It passes the graph search and should be thrown out — SYT2, not SYT1, is the neuromuscular-junction
isoform. It is the worked example of a computed candidate a clinician should reject.

**Assay / model transfer** (`opportunities.json`, node-free by design so it cannot be mistaken for a
finding): two diseases linked to the same **effect** mechanism, one with a model/assay/biobank/
outcome-measure asset and one with none. 41 pairs, 29 where both chains are `driven_by`. Every
source is STXBP1 — the only disease in the slice with model assets — so the concrete read is:
the Xue-lab haploinsufficient and InnoSer floxed-null mice, the COMBINEDBrain biorepository and the
S-COMB outcome-measure consortium are the reusable infrastructure, and VAMP2 (destabilization,
gain-of-function, loss-of-function), SYT1 and SNAP25 (dominant-negative) are the diseases with a
matching mechanism and `gap:<GENE>:models` still open.

## 4. Beyond the slice (`data/derived/beyond_slice.json`)

Labelled **"phenotype similarity only; mechanism not assessed"**.

`beyond_slice.py` imports `pipeline/biology/hpo.py` (`parse_obo`, `ancestors_fn`, `parse_hpoa`, the
IC thresholds) rather than copying it, so the IC method is identical: IC over all 12,867
`phenotype.hpoa` diseases, aspect P, NOT rows dropped, full `is_a` propagation. Each slice
umbrella's profile is the union of its OMIM/ORPHA subtype annotations (from the biology layer's
`hpo_stats.json`), compared by Resnik best-match-average against every HPO disease.

Excluded as "inside the slice": the slice's own entities and any disease whose
`genes_to_disease.txt` genes include a slice gene (this removes the multi-gene CMS and GEFS+
groupings), plus diseases with fewer than 5 annotated terms (BMA over-rewards tiny profiles) and
QTL/susceptibility loci. **10,495 diseases compared.** Output per disease: top 8 outside neighbours
with name, id, gene(s), score, percentile and the top 3 shared *distinctive* terms with their IC.

The results are biologically legible, which is the point of showing how the atlas would grow:
SNAP25's nearest outside neighbour is another presynaptic congenital myasthenic syndrome (MYO9A,
CMS24); SYT2's are axonal CMT and distal SMA, sharing *decreased compound muscle action potential
amplitude* (IC 6.37); STXBP1's is GNAO1 DEE17, sharing *EEG with burst suppression* (IC 5.44).
STX1A has no HPO-annotated entity at all, so it returns an explicit note instead of neighbours.

**How the UI should use it.** A "nearest diseases outside this slice" panel, with the label shown
next to the score, the three shared distinctive terms as the explanation, and a clear statement that
a high score is a reason to look, not evidence of a shared cause.

## 5. Counterexamples (`data/derived/counterexamples.json`)

10 items, 54 edge references, all resolving against `data/graph.json` (the build fails otherwise).
Each is `{title, plain_language, why_it_matters, edge_ids[], edges[]}`, where `edges[]` carries each
edge's type, status, evidence level, confidence and counter-evidence count so the UI can show the
strength without a second lookup. `plain_language` is written for a parent.

The 10: opposite-effect variants in SNAP25 (plus SYT1's minority mechanisms); STX1B pointing both
ways with one variant doing both; the terminated STXBP1 gene-therapy trial; STXBP1's unsettled
mechanism; the contested STXBP1↔SLC6A1 bridge; NSF in the dominant-negative cluster on the strength
of a fly-eye assay; UNC13A's 5,112 bp CDS not fitting a standard AAV; CPLX1's 151-of-155 pathogenic
records being multi-gene deletions (and STX1A's 153 of 161); phenotype similarity edges with an
empty list of shared distinctive features; and the 16 `has_effect` edges where "broken copy means
missing protein" is `inferred`/`unverified` at confidence 0.45.

**How the UI should use it.** This is the honesty surface. Put it where a visitor who has just read
an encouraging mechanism story will see it — a "where this breaks" section on the disease page and a
standalone page — and link each item's `edge_ids` into the evidence drawer.

## 6. Global disease index (`data/derived/global/`)

The problem: a judge typed "huntingtons" and hit "No match". Now every disease with HPO phenotype
annotations or a gene association is findable. A disease outside the 11 gets an honest page, not a
dead end: its own distinctive features, its phenotype neighbours, how far it sits from the mapped
family, and external links. Every page carries the caveat *"phenotype similarity only; no evidence
curation; mechanism not assessed"*. The full schema is in `data/derived/global/README.md`.

**Identity (MONDO 2026-09-01, `mondo-base.obo`, downloaded into the gitignored `data/raw/downloads/`).**

- OMIM and ORPHA ids merge into one row through MONDO xrefs carrying
  `source="MONDO:equivalentTo"`. That accounts for 14,380 source ids.
- 2 ids follow an obsolete term's `replaced_by` (this is how Dravet syndrome merges).
- 4 merge by a unique exact-name match.
- 122 rows keep a native OMIM/ORPHA id.
- 316 Orphanet ids appear only in `genes_to_disease.txt` with no name anywhere, so they are dropped:
  a row without a name cannot be searched.

Result: 11,456 rows. "Huntington disease", "Huntington's chorea", OMIM:143100 and ORPHA:399 are one
entry, MONDO:0007739. Each row keeps up to 4 EXACT synonyms, abbreviations first (HD, CF, DMD), with
"modifier of"/"susceptibility" variants dropped.

Genes are the OMIM MENDELIAN genes when there are any. Otherwise they are Orphanet genes, flagged
`gsrc: 2` because the file does not say whether they are causal or modifier. POLYGENIC associations
are never listed, which turns cystic fibrosis's 20-gene list into `CFTR`.

`atlas` is set on 14 rows. It is restricted to the curated profile entities and single-gene entries,
so multi-gene clinical groups (GEFS+, autosomal dominant non-syndromic intellectual disability)
never route to a gene page.

**Similarity: IC-weighted cosine over ancestor-propagated profiles.**

- IC is imported from `pipeline/biology/hpo.py`, so a term has the same IC everywhere in the app.
- Merged diseases are the **centroid** of their sources' normalised vectors.
- Neighbours are drawn from the 8,696 diseases with ≥ 5 terms, excluding QTL and susceptibility
  loci.

The method was fixed twice before shipping, both times because of the Huntington check:

1. **Merging.** Union-merging let ORPHA:399's block of behavioural terms pull an alcohol-related
   disease (Marchiafava-Bignami) into Huntington's top 4. The centroid removed it and moved SCA17
   (TBP) from outside the top 10 to #4.
2. **The "far" threshold.** Per-atlas-disease 99th percentiles called Dravet "far" from STX1B and
   Duchenne "near" SNAP25. Both are wrong, because the background is dense in epilepsies and sparse
   in myasthenias. The shipped threshold is absolute and calibrated on the atlas's own data:
   cosine ≥ **0.2454**, the lowest cosine among its 11 curated `similar_phenotype` pairs
   (SNAP25–SYT2). At that threshold, 8.8% of comparable non-slice diseases are near at least one
   mapped disease; the rest get the flag "different mechanism family, most likely".

**Sanity checks** (recomputed into `meta.sanity_checks` on every run):

- **Huntington disease.**
  - Top 10: HDL2 (JPH3), HDL1 (PRNP), juvenile HD, SCA17 (TBP), inherited CJD (PRNP), CLN13, SCA48,
    late-onset PD, CSF1R leukoencephalopathy, PINK1 PD.
  - Ranks: JPH3 #1, PRNP #2, TBP #4. **DRPLA (ATN1) is only #100**: its HPO profile leans on
    myoclonic epilepsy and ataxia, not on chorea and psychiatric features.
  - Far from the atlas.
- **Cystic fibrosis.**
  - Top 10: bronchiectasis with nasal polyposis, SCNN1A pseudo-CF (#2), PCD 42 (#3), pancreatic
    lipase deficiency, PCD 44, TAP1 MHC-I deficiency, RPGR sinorespiratory disease, PCD 46,
    CGD (NCF1), Young syndrome (#10).
  - Far from the atlas.
- **Duchenne muscular dystrophy.**
  - Top 10: dystroglycanopathies and limb-girdle muscular dystrophies (FKRP #2, SGCA #3).
  - **Becker is only #18**: it has 22 annotated terms against Duchenne's 39.
  - Far from the atlas; the closest is SNAP25 at 0.237, just under the threshold.
- **Dravet syndrome.**
  - Top 10: GEFS+, PCDH19 epilepsy, DEE6A (SCN1A, #3), CHD2 DEE, GEFS+2 (SCN1A, #5), SCN8A DEE,
    YWHAG DEE, JME, DEE52 (SCN1B, #9), myoclonic epilepsy in infancy.
  - **Near** STXBP1 (0.264) and STX1B (0.246), the expected family link.

**Shard function** (the UI must port it exactly): `bucket = djb2(id) % 64`, with the file at
`neighbours/<bucket>.json`. djb2 has seed 5381, `h = h * 33 + charCode`, and is reduced to an
unsigned 32-bit value after every character. In TypeScript:
`h = (Math.imul(h, 33) + s.charCodeAt(i)) >>> 0`.

Test vectors, identical in Python and Node:

| id | djb2 | bucket |
|---|---|---|
| `MONDO:0007739` | 2020644582 | 38 |
| `MONDO:0009061` | 2020708924 | 60 |
| `MONDO:0010679` | 2021577987 | 3 |

**How the UI should use it.**

1. Load `index.json` once for search. Use the normalisation in the README: delete apostrophes, so
   "Huntington's" becomes "huntingtons". With it, every query tested resolves: huntingtons, cystic
   fibrosis, duchenne, dravet, rett, angelman, fragile x, marfan, sma.
2. Send `atlas` hits to the existing atlas pages.
3. For any other disease, fetch one shard and render the page from it.
4. Build the external links from `meta.url_templates`: OMIM, Orphanet, Monarch/MONDO, a
   ClinicalTrials.gov condition search, a NORD site search and a GeneReviews search.
5. Never draw these neighbours as graph edges, and never give them a confidence.

**Update 2026-10-04: all 45 deep-atlas diseases.** The `atlas` block in `neighbours/` and the
`far` flag now cover every `disease:<GENE>` node in `data/graph.json`: the SNARE slice and the DEE,
lysosomal and RASopathy families, 45 in total. File formats are unchanged.

The threshold was recalibrated over all 75 curated `similar_phenotype` pairs, and it stays at
**0.2454**.

- **Literal rule rejected.** The weakest pair alone is NPC1–ARSA at 0.1287. It is one of four
  lysosomal pairs (NPC1–ARSA, HEXA–CLN3, GBA1–GLA, TPP1–GALC) that link visceral and neurological
  subtypes, and as a threshold it would call 74% of all diseases "near".
- **Rule now used: a trimmed minimum.** Take the weakest pair after dropping the lowest 5% of pairs
  (4 of 75). That is SNAP25–SYT2, 0.2454.
- **Effect.** 23.2% of comparable diseases are now near at least one mapped disease, up from 8.8%,
  because there are 45 targets including the DEE family.
- **Where it is recorded.** `meta.method.atlas_threshold.calibration` holds the trimmed pairs and
  the literal minimum.

The four checks now:

| Disease | Result | Closest mapped diseases (cosine) |
|---|---|---|
| Huntington disease | **near** | CACNA1A 0.277, KCNT1 0.273, SLC2A1 0.268 |
| Cystic fibrosis | **far** | top IDS 0.176 |
| Duchenne muscular dystrophy | **near** | GAA/Pompe 0.308; SNAP25 0.237 and SYT2 0.233 stay below the threshold |
| Dravet syndrome | **near** | SCN1A 0.642, SCN2A 0.527, KCNQ2 0.373 |

These results show the ceiling of phenotype-only matching. Huntington becomes "near" through broad
neurodegenerative and movement features shared with the DEE family. It is a phenotype match, not a
mechanism one, which is exactly what the caveat says.

## 7. Mechanism layer at scale (`data/derived/global/mechanism/`, `clusters.json`)

Every monogenic disease in the global index now carries:

- its curated mechanism class;
- its ClinGen validity;
- its mid-level Reactome pathways;
- a mechanism cluster, so the atlas can group diseases by MECHANISM, not only by symptoms.

The data is additive. `index.json` and `neighbours/` keep their formats, the new data sits in the
documented `mechanism/<bucket>.json` slot (same djb2 bucketing), and the full schema is in
`data/derived/global/README.md`.

**Sources** (downloaded into the gitignored `data/raw/downloads/`):

- G2P, all panels (3,851 records);
- ClinGen gene–disease validity and dosage (both files created 2026-10-03);
- Reactome NCBI2Reactome (lowest level), with its pathway names and hierarchy.

**Mechanism class (curated only).** Every value keeps the source label verbatim and the record URL.

| Source | Label | Our class |
|---|---|---|
| G2P | loss of function | `mech:loss-of-function` |
| G2P | dominant negative | `mech:dominant-negative` |
| G2P | gain of function | `mech:gain-of-function` |
| G2P | undetermined | no class |
| G2P | confidence "disputed" | no class |
| G2P | confidence "refuted" | skipped |
| ClinGen | HI score 3 or 2 | `mech:haploinsufficiency` |

A ClinGen HI score goes to the HI disease ClinGen names, or else only to dominant entries of that
gene.

| Measure | Count |
|---|---|
| Diseases with a mechanism class | **2,648** (loss of function 2,088, haploinsufficiency 695, gain of function 172, dominant negative 107) |
| Diseases with any mechanism record | 3,469 |
| Diseases with ClinGen validity | 2,260 |
| G2P records joined | 3,493 (MONDO 3,117, OMIM 198, gene 178) |
| G2P records unjoined | 355 |

**Pathways.**

- Lowest-level Reactome pathways roll up to their depth-3 ancestor (top level = 0); a depth-2 leaf is
  kept as is.
- Pathways with more than 400 human genes are dropped.
- The Disease branch is excluded.
- At most 5 pathways are shown per gene.
- **5,986 diseases have a pathway**, from 3,962 genes.

**Clusters.**

- The graph is gene-level. An edge requires a shared pathway, from the depth-3 set plus the depth-2
  parents.
- Weight = 0.6 × IDF-weighted pathway Jaccard + 0.4 × phenotype cosine of the genes' non-neoplastic
  disease centroids.
- 15 nearest neighbours per gene, then Leiden (resolution 1.0). Communities over 80 diseases are
  re-split with a gently rising resolution.
- **5,426 diseases clustered into 225 clusters. 200 clusters (5,362 diseases) fall in the 5–80
  target; 25 are smaller.**

Four fixes were needed to get here. Each was forced by a sanity check:

1. **Disease-level nodes → gene-level nodes.** With diseases as nodes, SCN1A's own allelic diseases
   landed in four clusters.
2. **Pathway size counted over all human genes, plus IDF weighting.** Generic bins such as
   "Neutrophil degranulation" had been grouping lysosomal enzymes with unrelated genes.
3. **Reactome Disease branch excluded.** "Signaling by RAF1 mutants" put BRAF with platelet
   integrin genes.
4. **Phenotype centroids without tumour entries.** BRAF's and KRAS's cancer entries diluted their
   Noonan profile.

The sweep (sanity counts are "largest share in one cluster / clustered", then number of clusters):

| Pathway weight | Resolution | Diseases in 5–80 clusters | Lysosomal | RAS | Sodium | SNARE |
|---|---|---|---|---|---|---|
| 0.75 | 1.0 | 5,357 | 31/83, 13 | 11/24, 4 | 17/17, 1 | 6/10, 3 |
| **0.6 (chosen)** | **1.0** | **5,362** | **38/83, 12** | **11/24, 3** | **17/17, 1** | **6/10, 3** |
| 0.6, class agreement ×1.25/×0.85 | 1.0 | 5,350 | 38/83, 13 | 11/24, 4 | 17/17, 1 | 6/10, 3 |

In the earlier sweep, before the Disease-branch fix, resolutions 2 and 4 were worse than 1.0 on every
check.

### Sanity checks (verbatim)

**1. Lysosomal storage: 83/93 clustered. Partly together.**

- **MC0034 · size 43 · "Glycosphingolipid metabolism · loss of function · cherry red spot of the
  macula"** holds 38 lysosomal diseases:
  - ASAH1: Farber lipogranulomatosis; SMA-progressive myoclonic epilepsy;
  - CTSA: galactosialidosis and 2 others;
  - GALC: 3 Krabbe forms;
  - GBA1: Gaucher types I/II/III, perinatal lethal, and ophthalmoplegia-calcification;
  - GLA: Fabry;
  - GLB1: GM1 types 1/2/3; MPS 4B;
  - GM2A: Tay-Sachs AB variant;
  - HEXA: Tay-Sachs, 4 forms;
  - HEXB: Sandhoff, 4 forms;
  - NEU1: 4 sialidoses;
  - PSAP: 4 saposin deficiencies;
  - SMPD1: Niemann-Pick A, B and chronic neurovisceral.
- **MC0114 · size 22 · "Heparan sulfate/heparin (HS-GAG) metabolism · loss of function · heparan
  sulfate excretion in urine"** holds 11: IDUA (Hurler, Hurler-Scheie, Scheie), IDS (3 MPS2 forms),
  SGSH, NAGLU, HGSNAT (MPS3A/B/C, plus RP73 and CMT2V). It also contains EXT1/EXT2 exostoses.
- **The rest split by substrate pathway:**
  - MC0127 arylsulfatases (ARSA, ARSB, SUMF1; 5);
  - MC0118 fatty acyl-CoA (PPT1; 5);
  - MC0153 UPR (TPP1; 5);
  - MC0038 plasma lipoprotein remodelling (LIPA, NPC1, NPC2; 4);
  - MC0095 MHC-II antigen presentation (CTSD; 4);
  - MC0190 lysosomal oligosaccharide catabolism (MAN2B1, MANBA; 4);
  - MC0044 glycosaminoglycan metabolism (GALNS, GNS, GUSB; 3);
  - MC0063 glycogen (GAA; 2);
  - MC0002 N-glycosylation (FUCA1);
  - MC0134 (LAMP2 Danon).
- **Unclustered (no mid-level pathway): 10.** AGA, CLN3 ×4, GNPTAB ×2, NAGA ×3.

**2. RASopathies: 24/24 clustered, but NOT one cluster.**

- **MC0020 · size 50 · "FLT3 Signaling · gain of function · nevus"** holds 11: HRAS (Costello, wooly
  hair nevus, phakomatosis pigmentokeratotica), KRAS (NS3, CFC2, brain AVM, Toriello-Lacassie-Droste),
  PTPN11 (LEOPARD 1, metachondromatosis) and SOS1 (NS4, gingival fibromatosis 1). They sit with
  PIK3CA, PTEN and AKT1/2.
- **MC0102 · size 23 · "Signaling by FGFR · gain of function · curly hair"** holds 11: BRAF (NS7,
  LEOPARD 3, CFC-related, and 6 tumour entries) and RAF1 (NS5, LEOPARD 2, DCM 1NN). They sit with
  SPRED1/2, MAP2K2 and PPP1CB.
- **MC0004 · size 66 · "Toll-like Receptor Cascades · loss of function · abnormal leukocyte
  morphology"** holds MAP2K1 (CFC3, melorheostosis).

Why: in Reactome the RAS genes share far more pathways with RTK/PI3K adaptors than with RAF/MEK
(edge weight KRAS–PIK3CA 0.33 vs KRAS–BRAF 0.24), and Jaccard penalises hub genes. Reactome also
places MEK1 in every Toll-like receptor cascade. A class-agreement factor (all of these are gain of
function) made it worse, so I did not force it. The honest reading is two mechanism-coherent halves,
RTK–RAS(–PI3K) and RAF–MEK, both labelled gain of function. The RASopathy family file
(`family_rasopathies.json`) is the right place to assert the clinical grouping.

**3. Sodium-channel epilepsies: 17/17 in ONE cluster.**

- **MC0024 · size 49 · "Phase 0 - rapid depolarisation · haploinsufficiency · arrhythmia".**
- SCN1A: DEE6A, DEE6B, GEFS+2, FHM3.
- SCN1B: GEFS+1, DEE52, Brugada 5, AF13.
- SCN2A: BFIS3, EA9, DEE11.
- SCN3A: DEE62, FFEVF4.
- SCN8A: BFIS5, DEE13, familial myoclonus 2, cognitive impairment ± ataxia.
- The cluster also holds SCN4A, SCN5A, SCN9A, SCN11A and FGF13/14, so it is the whole
  sodium-channelopathy family.

**4. The SNARE slice: 10/14 clustered.**

- **MC0005 · size 64 · "Neurotransmitter release cycle · loss of function · hyperreflexia"** holds
  STXBP1 DEE4, SNAP25 CMS18, SYT1, VAMP2, CPLX1 DEE63, **and the bridge gene SLC6A1**. The
  mechanism layer independently puts the atlas's core family and its bridge together.
- SYT2 (3 CMS entries) is in MC0129 clathrin-mediated endocytosis.
- NSF DEE96 is in MC0115 intra-Golgi/retrograde traffic.
- **Unclustered:** STX1B (its only Reactome pathway is in the excluded Disease branch) and UNC13A ×3
  (no Reactome annotation at all). STX1A has no single-gene disease entry.

**Family flags.** `pipeline/derive/atlas_flags.py` rewrites only the `atlas` column of `index.json`
from `data/curated/family_*.json`. It is stdlib, runs in under a second, and also runs at the end of
`global_index.py`. Tonight: 0 family files, 14 rows flagged. Re-run it whenever a family lands.

## Disease grouping for guided search: `groups.json`

This file is new and additive; `index.json` is unchanged. It is built by
`pipeline/derive/groups.py` from MONDO `is_a`. It contains:

- `head_of`: maps a row id to its family head's id;
- `groups[head]`: the head's `name`, `genes`, `n_members`, and `members[]` with `id`, `name`,
  `distinction` and `basis`;
- `similar_names_different_conditions[]`.

**Rule.** A row's head is the nearest `is_a` ancestor that is itself an index row and passes the
filters, chosen in this order:

1. The ancestor whose core name is contained in the child's. The core name drops generic words such
   as disease, syndrome, type and form.
2. Otherwise, the lowest ancestor with at least 2 index rows beneath it.

An ancestor never qualifies if it is:

- a blocklisted generic class ("hereditary disease", "neurodegenerative disease", "epilepsy", …);
- above more than 60 index rows;
- fewer than 3 `is_a` steps from the MONDO root.

Chains collapse to a single level. `distinction` is the child's name minus the head's words, with
the gene added (e.g. "juvenile (HTT)", "type 3 (KRAS)").

`similar_names_different_conditions` lists rows that contain every core word of the head's name but
are **not** under it in MONDO. For example, the Huntington disease-like disorders appear under
Huntington disease this way.

Result: 3,218 of 11,456 rows have a head, in 755 groups.

**UI.** Run search as before, map every hit through `head_of`, and de-duplicate. Show the heads,
with the exact name match first. Then show "Which type?" with the members and their distinctions,
and "Similar names, different conditions" with the similar-name rows.

**Reference sequences.** Files are in `data/derived/sequences/`: 45 MANE Select genes with CDS,
protein, RefSeq and exon tables on GRCh38 and GRCh37, `variant_positions.json` for VCF matching, and
5 synthetic example files. The schema and the VCF assembly-detection rules are in
`data/derived/sequences/README.md`.

## Open questions for a biochemist

New ones this layer raises (the biology layer's seven still stand):

1. **Is VAMP2 "destabilization" the same event as Munc18-1 aggregation or GAT-1 ER retention?**
   Synaptobrevin-2 is natively unstructured outside the SNARE complex, so its "stability" defect may
   be a complex-formation property. Does 4-phenylbutyrate change VAMP2 variant protein level or
   SNARE-complex formation at all? No experiment reports it. This is the pivot for the top hypothesis.
2. **Do SNAP25-DEE patients have subclinical neuromuscular involvement?** One repetitive-nerve-
   stimulation study in a SNAP25-DEE cohort would either open a symptomatic option for a group that
   has none, or retire two of these hypotheses.
3. **Can the slice's variants be sorted into release-up and release-down classes?** Every
   aminopyridine hypothesis here, and the modality screen's `R-SX-3` and `R-KD-1b` rules, depend on
   it. The assays exist (SNAP25 and STX1B iPSC neurons, worm and mouse neuron panels); the
   classification does not (`gap:variant-level-mechanism-map`).
4. **Does a targetable upregulation element exist in any of these genes?** TANGO-style ASOs need a
   non-productive splicing event and uORF blockers need a uORF; a uORF result has already failed to
   reproduce independently (PMID:39759875). Without a named element, "transcript upregulation" stays
   conditional for all 11 diseases, and that is currently the honest answer.
5. **What is the acceptable upper bound on protein level for each of these genes?** Overexpression
   data exist for SNAP25, Munc18-1 and GAT-1 and all three are unfavourable, yet no human threshold
   is defined for any gene in the slice — including the one whose AAV trial was stopped.
6. **Would stabilising complexin-1 even be desirable?** CPLX1 is a fusion *clamp*, so the usual
   "more working protein is better" logic may invert. No functional study of patient variants exists.
7. **Is the UNC13A ALS cryptic-exon ASO usable here at all?** It raises UNC13A rather than lowering
   it, and nothing says the TDP-43-dependent cryptic exon is even used in Mendelian UNC13A patients.

## Known weaknesses of this layer

- The modality screen is a **rule table, not a model**. Its fits are only as good as the mechanism
  edges underneath, and 48 of 66 cells are "conditional" because that is what contested mechanism
  edges honestly produce. Two of the three thin genes (STX1A, NSF, CPLX1) are capped by rule, not
  judged on merit.
- Three of five hypotheses rest on a `pathway` or `cluster` chain, which says the gene participates
  in a process, not that the disease dysregulates it in the direction the drug pushes. Each one says
  so in `attrs.weakest_link`.
- The modality rules' general citations are mostly from other genes (SCN1A, SCN2A, COL6A1): they
  support "this is what the approach does", never "this works for this disease".
- `beyond_slice.json` scores phenotype only. The two filters (≥ 5 terms, no QTL/susceptibility loci)
  are methodological choices made to stop obvious artefacts; they are recorded in
  `meta.excluded_rule` and would change the neighbour lists if revisited.
- The global index scores phenotype only, and its quality is bounded by the HPO annotations:
  DRPLA (ATN1) ranks #100 for Huntington disease and Becker ranks #18 for Duchenne, because their
  annotation profiles diverge from the clinical picture. 122 rows have no MONDO id, 316 nameless
  gene-only Orphanet ids are left out, and Orphanet gene lists (`gsrc: 2`) may include modifiers.
  The "far" flag is phenotype evidence about mechanism, which is weak, and it is worded "most
  likely" for that reason.
- The mechanism clusters are computed groupings over curated inputs, not curated families:
  - RASopathies split into RTK–RAS–PI3K and RAF–MEK halves, with MAP2K1 in a TLR cluster;
  - lysosomal diseases group by substrate pathway, not by organelle;
  - genes without a usable Reactome pathway (UNC13A, STX1B, CLN3, AGA, NAGA, GNPTAB) stay
    unclustered;
  - 355 G2P and 722 ClinGen validity records could not be joined to an index row;
  - G2P `joined_by: gene` (178 records) is the weakest join.
- `data/curated/hypotheses.json` is merged into `data/graph.json` by the next
  `python3 pipeline/build_graph.py` run (the 5 `candidate_for` edges are already in the current
  build). `data/curated/modality.json` contributes no nodes or edges and is read directly.
