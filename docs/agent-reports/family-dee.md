# Family "dee": developmental and epileptic encephalopathies (channels, receptors, signalling)

Genes: SCN1A, SCN2A, SCN8A, KCNQ2, KCNT1, CACNA1A, GRIN2B, CDKL5, SYNGAP1, SLC2A1.
Output: `data/curated/family_dee.json` (`{nodes, edges, clusters, gaps}`, SCHEMA v0.1). Every
disease, gene, variant-group, new mechanism and new therapy node carries `attrs.family = "dee"`.

## What is in the file

| Nodes | n | Edges | n |
|---|---|---|---|
| phenotype (new; existing ones reused) | 111 | has_phenotype | 192 |
| variant_group (50 ClinVar + 10 literature-defined GoF/LoF subgroups) | 60 | variant_in / has_effect | 60 / 43 |
| study (ClinicalTrials.gov) | 48 | studies / tests | 78 / 21 |
| grant (NIH RePORTER) | 39 | about / funds | 39 / 41 |
| researcher | 30 | works_on | 30 |
| patient_org | 14 | serves / covers / maintains | 31 / 20 / 8 |
| therapy (13 new + fenfluramine annotated) | 14 | developed_for / targets | 20 / 5 |
| gene / disease | 10 / 10 | causes | 10 |
| mechanism (8 new GO nodes; effect mechanisms reused) | 8 | participates_in / driven_by | 17 / 19 |
| asset | 7 | similar_phenotype (20 cross-family) | 34 |
| **351 nodes** | | **668 edges** | |

5 clusters, 11 gaps. Edge status: 631 supported, 17 contested, 20 unverified. Evidence level: 338 curated,
121 clinical, 81 observational, 66 experimental, 62 inferred. 15 edges carry `counter_evidence`.

## Evidence integrity

- **No hand-typed quotes.** Claims live in `claims_mech.py`, `claims_therapy.py`, `claims_therapy2.py`
  and `claims_family.py` as short *needles*. `curation.py::quote_for()` returns the verbatim
  sentence (or trial eligibility line) from the locally stored source and raises if a needle is
  missing or ambiguous (`python3 curation.py` → `unresolved: 0`).
- **Independent check.** `verify.py` re-reads every stored source and string-matches every quote
  (NFKC, dash/curly-quote folding, whitespace collapse). It covers PubMed abstracts,
  ClinicalTrials.gov records (ours and the community store), openFDA labels, community web pages
  (matched by URL through the page manifest), NIH RePORTER records, GO definitions and UniProt function
  text. It also checks that every edge endpoint and cluster member exists in the fragment or in another
  curated fragment, and that edge ids are deterministic. It sets `verified` and exits 1 on any failure.
  **Result: 659 quotes checked, 659 verified, 0 failed; 0 dangling references** (PubMed 146,
  ClinicalTrials.gov 175, NIH RePORTER 198, Website 122, UniProt 10, GO 8).
- `python3 pipeline/build_graph.py`: **Problems: None.** The only attribute conflict reported is
  `therapy:4-phenylbutyrate` modality, between two other fragments; it is not from this family.
- FDA approvals cite the **openFDA drug label** (stored raw under `data/raw/families/dee/labels/`; the
  evidence URL is the DailyMed SPL page), with source `Website`, a verbatim indication quote and evidence level `clinical`.
- Treatment-direction findings are recorded **exactly as the source states them**. A sentence saying a drug
  class worsened seizures, is contraindicated, or was excluded for a mechanism goes into
  `counter_evidence` on the therapy→disease edge. Where the source splits results by mechanism, the
  edge's `attrs.effect_by_mechanism` says which mechanism the supporting evidence and the
  counter-evidence refer to. No new relation types were introduced.

## How to re-run

```bash
pipeline/families/dee/run.sh            # whole family; cached responses make it offline
pipeline/families/dee/run.sh --refresh  # re-fetch from the APIs
python3 pipeline/build_graph.py         # merge into data/graph.json
```
Steps: `fetch_bio.py` (HGNC, UniProt, Ensembl, Monarch, OLS4, Orphadata, Open Targets) →
`clinvar.py` (E-utilities; the biology classifier is imported unchanged) → `quickgo.py` →
`hpo.py` (biology `hpo.py` helpers imported unchanged) → `pubmed.py` (PubMed efetch, CT.gov v2, openFDA) →
`curation.py` → `community/run.sh` → `build.py` → `verify.py --write`. NCBI traffic uses the shared
cross-process file-lock throttle in `pipeline/biology/common.py` (<2 req/s, tool=rare-disease-atlas, no email).
Raw data: `data/raw/families/dee/`.

## Method notes

- **Diseases** are gene-defined umbrellas. Subtypes are the OMIM entities with a Monarch OMIM causal edge
  plus the Orphanet entities that are "Disease-causing" and gene-specific.
- **Phenotypes**: IC over all 12,867 phenotype.hpoa diseases. Up to 20 terms per disease: the top 12 most
  informative non-redundant terms, plus terms shared with similarity partners and the 4 broad hallmarks.
  Nodes already in the atlas are reused.
- **Similarity** uses the Resnik best-match average against a 3,000-disease background (seed 20261003),
  computed for DEE×DEE and DEE×SNAREopathy pairs (155). The threshold is **stricter than the SNARE layer's**:
  ≥99th percentile for *both* diseases. Both families are epilepsy-dense, and the 95/99 rule flagged 72
  of 155 pairs; this rule keeps **34, of which 20 are cross-family**.
- **Variant groups**:
  - ClinVar P/LP groups use the same buckets as biology (truncating, missense, splice, whole-gene and
    contiguous deletions). Contiguous deletions get no mechanism edge.
  - Because ClinVar does not record variant function, gain- and loss-of-function missense subgroups are
    defined from functional papers, with quoted example variants: SCN2A R1882Q vs R853Q; SCN8A R1872W;
    KCNQ2 R201C/H; CACNA1A A713T/V1396M vs G230V/I1357S; GRIN2B P553T.
  - Generic missense groups for genes with both mechanisms get no `has_effect` edge.
- **GO mechanisms**: 9 new process/function nodes from QuickGO with descendant expansion.
  - Cross-family edges from SNARE genes to the new terms are stricter: no IEA-only hits, and no
    "regulation of …" hits. On this rule VAMP2's "regulation of delayed rectifier potassium channel activity"
    and SNAP25's IEA potassium-channel hit were dropped; only VAMP2 → regulation of synaptic plasticity (ISS) remains.

## Top 5 evidence-backed connections

1. **Same symptoms, different mechanisms: KCNT1 ↔ STXBP1** (`similar_phenotype`, Resnik BMA 2.77, ≥99.9th percentile
   for both). Shared distinctive features: generalized tonic seizure, focal motor seizure, epileptic
   encephalopathy, status epilepticus.
   - KCNT1: gain-of-function potassium channel (PMID:23086397). Quinidine, a partial KCNT1 antagonist, has
     case-report support but no efficacy in a randomized crossover trial with cardiac side effects
     (PMID:29196578, as counter-evidence). A KCNT1 ASO reduced seizures in two infants, with
     ventricular enlargement/hydrocephalus reported (PMID:41981306).
   - STXBP1, in the SNARE layer: haploinsufficiency/destabilization, with a chaperone trial.
   - The 2025 DEE precision-therapy review files these under different pathophysiologic categories
     (PMID:40381457, which names chemical chaperones for STXBP1).
2. **SCN1A ↔ STXBP1 and SCN1A ↔ STX1B**: similar profiles (BMA 2.74; 2.51), with different
   effect mechanisms and approved therapies on only one side.
   - SCN1A ↔ STXBP1 shares multifocal discharges, generalized tonic and atonic seizures, and profound ID.
   - SCN1A ↔ STX1B shares febrile seizures, atonic and tonic seizures.
   - SCN1A (Dravet) is NaV1.1 loss of function in inhibitory interneurons (PMID:16921370, 32848094). It has three
     FDA-labelled Dravet drugs (FINTEPLA, DIACOMIT, EPIDIOLEX), plus zorevunersen (phase 3) and ETX101 (phase 1/2).
   - The SNARE partners are presynaptic vesicle-fusion disorders with no approved drug in the atlas.
3. **Sodium channel blockers: recorded evidence splits by mechanism**
   (`cluster:dee-sodium-channel-gof` vs `cluster:dee-sodium-channel-lof`).
   - SCN2A: response in early-onset gain-of-function cases; "rarely effective in epilepsies with later onset …
     and sometimes induced seizure worsening" (PMID:28379373, counter-evidence).
   - SCN8A: gain-of-function carriers responded better (PMID:34431999).
   - SCN1A: rare gain-of-function variants responded (PMID:35696452, 36636894). Counter-evidence for Dravet:
     lamotrigine worsening in 80% (PMID:9596203), "generally considered contraindicated" (PMID:36314457), and
     an SCN8A trial listing "worsening on sodium channel blockers" as a Dravet-like exclusion feature (NCT04873869).
   - KCNQ2, a potassium channel: the same class is reported most effective in loss-of-function groups (PMID:42610455).
4. **Trial design already encodes "same gene, opposite mechanism"** (`cluster:dee-same-gene-opposite-mechanism`).
   - Zorevunersen phase 3 excludes SCN1A gain-of-function variants (NCT06872125).
   - XEN496 (ezogabine) phase 3 excluded KCNQ2 gain-of-function variants and was terminated by sponsor decision (NCT04639310).
   - Relutrigine excludes loss-of-function SCN2A/SCN8A variants (NCT05818553).
   - Elsunersen phase 3 requires a gain-of-function SCN2A variant (NCT07019922).
5. **A therapy crossing genes inside the family**: an Scn8a-lowering ASO extended survival of Scn1a+/−
   Dravet mice as well as SCN8A mice (PMID:31943325). It is encoded as `developed_for` to both SCN8A and
   SCN1A, at the preclinical stage.

## Community layer (sub-agent, `pipeline/families/dee/community/`)

Built from cached pages and records; its own `verify_community.py` also string-matches every quote, and
`verify.py` re-checks it. Bright Data: 11 of 150 requests (2 SERP errors).

| Disease | serves | covers | studies | works_on |
|---|---|---|---|---|
| SCN1A | 4 | 1 | 16 | 3 |
| SCN2A | 3 | 3 | 9 | 3 |
| SCN8A | 3 | 2 | 5 | 3 |
| KCNQ2 | 3 | 2 | 6 | 3 |
| KCNT1 | 2 | 2 | 6 | 3 |
| CACNA1A | 3 | 2 | 5 | 3 |
| GRIN2B | 4 | 2 | 5 | 3 |
| CDKL5 | 5 | 1 | 10 | 3 |
| SYNGAP1 | 2 | 4 | 6 | 3 |
| SLC2A1 | 2 | 1 | 10 | 3 |

**Cross-family assets.** Existing SNAREopathy nodes, now linked to DEE diseases with fresh quotes from fetched pages:
- `asset:simons-searchlight` covers SCN1A, SCN2A, GRIN2B and SYNGAP1. It already covered STXBP1, SLC6A1, SNAP25 and VAMP2.
  Its CACNA1A, CDKL5 and SLC2A1 pages returned 404 and were not used.
- `asset:endd-stxbp1-syngap1-center` covers SYNGAP1: one natural history study spans STXBP1 and SYNGAP1.
- `asset:citizen-health` covers 6 DEE genes.
- The umbrella groups `org:dee-p-connections` (8 DEE genes) and `org:rare-epilepsy-network` (9) serve DEE genes.

Researchers come from RePORTER/PubMed (≤3 per gene), with professional information only.

## Notes for reviewers

- **Fenfluramine stage.** `therapy:fenfluramine` is owned by `community.json` with `stage: "clinical"`,
  but the stored FDA label (FINTEPLA) gives an approved indication for seizures in Dravet syndrome and LGS.
  This fragment did not edit `community.json`. It re-emits the node with a new `attrs.approvals` key and the label quote
  as a source, which adds no conflicting attribute. The stage should be changed to `"approved"` via
  `data/curated/overrides.json` by whoever owns that file.
- Approvals for Dravet drugs are **syndrome-level**; the `developed_for` edges point to `disease:SCN1A`
  because Dravet syndrome is its main subtype. This is stated in each edge explanation and in `gap:dee-syndrome-vs-gene-indications`.
- Therapies with stored, verified-able sources but **no edges in this build**: memantine, L-serine and radiprodil (GRIN2B),
  the ketogenic diet and triheptanoin (SLC2A1), and 4-aminopyridine for episodic ataxia type 2 (CACNA1A). They are recorded in
  `gap:dee-grin2b-cacna1a-slc2a1-therapies`. CT.gov `tests` edges pointing at these not-yet-created
  therapy nodes are dropped by `build.py` (17 edges, listed in its output).

## Gaps

- `gap:dee-missense-function-map`: Which ClinVar missense variants in SCN1A/SCN2A/SCN8A/KCNQ2/CACNA1A/GRIN2B are gain- vs loss-of-function?
- `gap:dee-syngap1-therapy`: Is there a trial-stage or approved therapy for SYNGAP1-related disorders?
- `gap:dee-grin2b-cacna1a-slc2a1-therapies`: Mechanism-matched therapies for GRIN2B (memantine, L-serine, radiprodil), SLC2A1 (ketogenic diet, triheptanoin) and CACNA1A were identified in the sources but not encoded in this build.
- `gap:dee-syndrome-vs-gene-indications`: Do Dravet syndrome approvals (fenfluramine, stiripentol, cannabidiol) apply equally to SCN1A-positive and SCN1A-negative patients?
- `gap:dee-scn8a-community`: What patient organisations, registries, trials and research groups exist for SCN8A-related disorders, beyond those verified here?
- `gap:dee-kcnq2-community`: What patient organisations, registries, trials and research groups exist for KCNQ2-related disorders, beyond those verified here?
- `gap:dee-kcnt1-community`: What patient organisations, registries, trials and research groups exist for KCNT1-related disorders, beyond those verified here?
- `gap:dee-cacna1a-community`: What patient organisations, registries, trials and research groups exist for CACNA1A-related disorders, beyond those verified here?
- `gap:dee-cdkl5-community`: What patient organisations, registries, trials and research groups exist for CDKL5-related disorders, beyond those verified here?
- `gap:dee-syngap1-community`: What patient organisations, registries, trials and research groups exist for SYNGAP1-related disorders, beyond those verified here?
- `gap:dee-slc2a1-community`: What patient organisations, registries, trials and research groups exist for SLC2A1-related disorders, beyond those verified here?

Each gap lists the exact searches run (`searched`) and how to find out.
