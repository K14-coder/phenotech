# Biology layer: the SNAREopathies (+ one bridge gene)

Slice: disorders of the presynaptic synaptic-vesicle fusion machinery, plus **SLC6A1** as a
tested cross-pathway bridge. Output: `data/curated/biology.json` (`{nodes, edges, clusters, gaps}`,
per `docs/SCHEMA.md`).

Generated 2026-10-03. Source versions: HPO `phenotype.hpoa` 2026-09-02 / `hp.obo`
`hp/releases/2026-09-01`; HGNC, UniProt, Ensembl, Monarch v3, OLS4 (MONDO), Orphadata,
Open Targets v4, ClinVar and QuickGO fetched live on that date; every response is cached
under `data/raw/biology/`.

## What is in the file

| Nodes | n | Edges | n |
|---|---|---|---|
| phenotype | 117 | has_phenotype | 155 |
| variant_group | 43 | variant_in | 43 |
| gene | 11 | has_effect | 32 |
| disease | 11 | driven_by | 25 |
| mechanism | 11 (5 effect + 6 GO process) | participates_in | 21 |
| therapy | 8 | shares_mechanism | 14 |
| | | similar_phenotype | 11 |
| | | causes / developed_for | 11 / 11 |
| | | targets | 9 |
| **201 nodes** | | **332 edges** | |

5 clusters, 7 gaps. Edge status: 285 supported, 31 contested, 16 unverified.
Evidence level: 227 curated, 53 experimental, 32 inferred, 20 clinical.
**27 edges carry `counter_evidence`; 56 evidence items are marked `supports: false`.**

Evidence items by source: PubMed 193, HPO 161, ClinVar 59, GO 36, OMIM 13, Atlas 11,
Orphanet 10, ClinicalTrials.gov 10, Open Targets 8, ClinGen 4. 58 distinct PMIDs.

### Evidence integrity

**Every quote in the file was string-matched against a locally stored copy of its source:
238/238 verified, 0 failures** (`python3 pipeline/biology/verify_quotes.py`).

Two independent mechanisms protect this:

1. `curation.py` never stores a hand-typed quote. Each claim stores a short **needle**, and
   `quote_for()` extracts the full sentence from the stored source file (
   `data/raw/biology/pubmed/<PMID>.json` or `clinicaltrials/<NCT>.json`). A needle that is
   missing or matches more than one sentence raises, so a claim cannot carry text that is not
   in the source. All 96 needles resolve uniquely.
2. `verify_quotes.py` re-reads the sources from disk, knows nothing about the needles, and
   sets `verified` only on an exact normalised-substring match. It exits non-zero on any
   failure, so it can gate a build. `validate.py` separately checks schema conformance
   (ID formats, deterministic edge IDs, legal source→target relation types, enum values,
   dangling references, cluster membership, `evidence` present unless hypothesis):
   **0 errors**.

Gene symbols in PubMed abstracts are sometimes stripped of italics, producing run-together
text ("thecryptic exon"). We fetch our own XML via E-utilities, so our stored text is intact
and our quotes are the real sentences.

### Gene inclusion decisions

All 5 core genes (STXBP1, SYT1, SNAP25, VAMP2, STX1B) and the bridge gene (SLC6A1) are in.
All 5 extended candidates passed the "established Mendelian association" test, but not equally:

| Gene | OMIM causal | Orphanet disease-causing | Gene2Phenotype | ClinGen |
|---|---|---|---|---|
| SYT2 | yes (616040, 619461) | yes (ORPHA:716903, 716908) | definitive | moderate |
| CPLX1 | yes (617976) | yes (ORPHA:86909) | – | – |
| UNC13A | yes (621455/6/7) | yes (ORPHA:716903) | moderate | – |
| NSF | yes (619340) | – | – | – |
| STX1A | **no** | **no** (only "role in the phenotype of" Williams syndrome, "modifying" in CF) | moderate / limited | – |

STX1A is the weakest member and is kept only because Gene2Phenotype rates a neurodevelopmental
disorder as moderate and one case series exists; this is recorded in
`gap:stx1a-mendelian-validity` and in the node's `attrs.gene_disease_validity`.
Contiguous-deletion and susceptibility links (STXBP1 in 9q33.3q34.11 microdeletion, CPLX1 in
Wolf-Hirschhorn, UNC13A in ALS, STX1A in Williams/CF, SLC6A1 in 3p25.3 microdeletion) are
deliberately **excluded from the `causes` edges and from `attrs.subtypes`**: the Orphadata
association type is checked, not just the existence of a link.

## The most interesting evidence-backed connections

**1. One trial already treats two unrelated genes as one mechanism — STXBP1 and SLC6A1.**
`disease:STXBP1|shares_mechanism|disease:SLC6A1` (contested, 0.6). A subset of Munc18-1 and
GAT-1 missense variants both produce an unstable/misfolded protein that is degraded or stuck in
the ER (PMID:30266908, PMID:29538625; PMID:34028503, PMID:31176687, PMID:36741049), both are
rescued by 4-phenylbutyrate in models (PMID:30266908; PMID:35911425, PMID:42157447,
PMID:42650175), and **NCT04937062 enrols children with either gene on exactly this rationale**.
SLC6A1 is not a SNARE protein and sits in a different pathway (GABA reuptake, GO:0051936) —
this is the "different genes, different pathways, shared mechanism" edge. It is marked
*contested* with 9 contradicting items; see "shakiest claims".

**2. The HPO similarity computation independently recovers the bridge.**
`disease:STXBP1|similar_phenotype|disease:SLC6A1` sits in the top 1% of SLC6A1's background
distribution, and the shared **distinctive** feature is *Atonic seizure* (IC 5.0) while the
shared features that look obvious — hypotonia, developmental delay, intellectual disability —
are all **broad** (IC 1.3–1.5). STX1B pairs with SLC6A1 the same way (atonic seizure + absence
seizure). So a mechanistic bridge found in the literature and a phenotype bridge computed from
HPO point at the same pair, by different routes.

**3. The same gene can cause brain disease or a treatable muscle disease — and the muscle
version has drugs today.** SYT2, SNAP25 and UNC13A all appear under
`Autosomal recessive congenital myasthenic syndrome due to defective synaptic vesicles
exocytosis` (ORPHA:716903). For SYT2, 3,4-diaminopyridine gave clinical benefit and improved
neuromuscular transmission (PMID:26519543), and 3,4-DAP plus pyridostigmine worked in a
recessive patient (PMID:32250532) — while **albuterol did not** (same paper, same patient).
Clinically this is the most actionable finding in the slice: a family with a presynaptic CMS in
one of these genes should be assessed for an existing drug, not only for future gene therapy.
`cluster:presynaptic-nmj-treatable` collects it.

**4. The phenotype-similarity metric puts NSF — a one-paper gene — next to STXBP1 and UNC13A
on high-IC EEG features.** `UNC13A|similar_phenotype|NSF` is the strongest pair in the slice
(Resnik BMA 2.50, >99.9th percentile), and the shared features are specific, not generic:
*EEG with burst suppression* (IC 5.4), *primary microcephaly* (IC 4.6), *profound intellectual
disability* (IC 4.6), *tonic seizure* (IC 4.4). NSF has only one Mendelian report
(PMID:31675180) with mechanism inferred from a *Drosophila* eye assay, so this is a concrete
pointer for a biochemist: if NSF really phenocopies the fusion-machinery genes, the
dominant-negative claim deserves a proper neuronal test.

**5. Gene-level mechanism labels are unsafe for choosing a therapy, and the literature says so
explicitly.** Several genes carry *opposite* variant effects: SNAP25 I67N reduces release and
responds to 4-aminopyridine while V48F increases spontaneous release (PMID:40181518); STX1B
G226R reduces the releasable pool while V216E increases fusogenicity (PMID:32572454), and
patient iPSC neurons show G226R to be mixed gain/loss (PMID:42673765); UNC13A has three
coexisting mechanisms (PMID:41125872). PMID:41166419 states the consequence — these disorders
need a *functional* classification. We encode this as `attrs.minority_mechanism` on 5
`driven_by` edges and as `gap:variant-level-mechanism-map`.

Bonus: **the first STXBP1 gene-therapy trial was terminated.** NCT06983158 (CAP-002) is
`TERMINATED`, reason "Stopping rule for study was met", and the same sponsor's natural-history
study NCT05462054 was withdrawn. The preclinical threshold paper also states no human evidence
defines a therapeutic threshold (PMID:41883162). Both are attached as counter-evidence so the
graph does not present STXBP1 AAV as a live option.

## Clusters

| Cluster | Basis | Why it is useful |
|---|---|---|
| `cluster:dose-and-stability` | mechanism | Too little working protein, whether by lost copy or unstable protein. Shared therapeutic logic: raise the working protein. Contains the STXBP1↔SLC6A1 bridge. |
| `cluster:dominant-negative-fusion-block` | mechanism | The altered protein jams the machine, so adding a healthy copy may not suffice. STXBP1's membership is contested on purpose. |
| `cluster:release-timing-and-clamping` | mechanism | Variants that cause excessive or un-clamped release — where release-boosting drugs could *harm*. |
| `cluster:presynaptic-nmj-treatable` | mechanism | The drug-responsive neuromuscular presentation (SYT2, SNAP25, UNC13A). |
| `cluster:snareopathy-family` | pathway | The family framing itself, justified by 7 quoted reviews (PMID:32559416 coins "SNAREopathies"; PMID:33299146, 36564538, 32916768, 32738165, 35095745, 41166419). |

## How to re-run

Everything is stdlib Python 3 and re-runnable; cached responses make a second run offline.
Add `--refresh` to any fetch step to re-hit the APIs.

```bash
cd pipeline/biology
./run_all.sh              # whole layer, in order (add --refresh to re-fetch)
```

Or step by step (each writes its raw responses under `data/raw/biology/`):

```bash
# large HPO files -> data/raw/downloads/ (gitignored)
BASE=https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download
curl -sSL -o ../../data/raw/downloads/phenotype.hpoa      $BASE/phenotype.hpoa
curl -sSL -o ../../data/raw/downloads/hp.obo              $BASE/hp.obo
curl -sSL -o ../../data/raw/downloads/genes_to_disease.txt $BASE/genes_to_disease.txt

python3 fetch_genes.py        # HGNC REST + UniProt REST + Ensembl CDS (MANE Select)
python3 fetch_diseases.py     # Monarch v3 + OLS4/MONDO + Orphadata + Open Targets GraphQL
python3 hpo.py                # IC over all 12,867 hpoa diseases; phenotypes + similarity
python3 clinvar.py            # ClinVar P/LP spectrum via E-utilities (throttled)
python3 quickgo.py            # GO biological-process mechanisms
python3 pubmed.py             # efetch abstracts + CT.gov records for every curated claim
python3 curation.py           # (check) resolve all 96 needles, print the quotes
python3 build_biology.py      # assemble data/curated/biology.json
python3 verify_quotes.py --write   # string-match every quote, set verified=true
python3 validate.py           # schema conformance (0 errors expected)
```

Helpers: `python3 pubmed.py 12345678 …` fetches specific PMIDs;
`python3 pubmed.py --search "<term>"` runs an esearch and prints titles.

NCBI etiquette is enforced in `common.py`: a **file-lock throttle shared across processes**
caps all E-utilities traffic at <2 requests/second, every call carries
`tool=rare-disease-atlas`, **no email parameter is ever sent**, and 429/5xx retries use
exponential backoff honouring `Retry-After`.

## Method notes

**Phenotypes and information content.** IC is computed over **all 12,867 diseases** in
`phenotype.hpoa` (aspect `P`, `NOT`-qualified rows dropped, obsolete/alt IDs remapped), with
full `is_a` ancestor propagation: `IC(t) = -ln(n_diseases annotated to t or any descendant /
12,867)`. Each phenotype node carries `attrs.ic`, `attrs.n_diseases` and a `specificity` label
(`distinctive` ≥ 4.0, `broad` < 2.0, else `intermediate`).

*Profile entities per umbrella*: every OMIM entity with a Monarch OMIM causal edge, plus every
Orphanet entity that is both "Disease-causing" **and gene-specific** (exactly one associated
gene). Multi-gene clinical groups like GEFS+ (13 genes) and the presynaptic-CMS groups are
excluded from profiles so that similarity is not inflated by other genes' phenotypes.

*Readability trimming* (as asked): per disease we keep the top 12 most informative terms, after
dropping any term that is an ancestor or descendant of a kept term, plus the terms shared with
any similarity partner, plus the 4 classic broad hallmarks (seizure, intellectual disability,
developmental delay, hypotonia) when directly annotated — so that broad-vs-distinctive contrast
stays visible. Cap 20/disease: **8–20 kept per disease** out of 8–140 annotated.

*Similarity*: Resnik best-match-average over direct annotations. Rather than a hand-picked
cut-off, each disease gets its own **background distribution** (BMA against a fixed random
sample of 3,000 non-slice diseases, seed 20261003); an edge is emitted only if the pair is
≥95th percentile for **both** diseases and ≥99th for at least one. 11 of 45 pairs qualify.
IC-weighted Jaccard is also stored. Explanations name which shared features are DISTINCTIVE
and which are BROAD, with their IC values.

**Variant groups.** ClinVar esearch + esummary per gene, classified by
`molecular_consequence_list`. Single-gene and **multi-gene deletions are separate groups**:
the contiguous-gene group gets a `variant_in` edge but deliberately **no `has_effect` edge**,
because the deleted segment removes several genes (CPLX1's 155 records are 153 multi-gene CNVs,
mostly Wolf-Hirschhorn region — treating these as CPLX1 loss-of-function evidence would be
wrong). Truncating/splice/deletion→haploinsufficiency edges without a gene-specific paper are
marked `evidence_level: inferred`, `status: unverified`, confidence 0.45.

**Mechanisms.** 5 effect mechanisms (haploinsufficiency, protein destabilization,
dominant-negative, gain of function, loss of function) and 6 GO processes from QuickGO with
descendant expansion (`goUsage=descendants`), confidence scaled by GO evidence code
(experimental+PMID 0.9 → IEA-only 0.6). Claims with `supports="minority"` support their own
mechanism edge while being attached as counter-evidence on the gene's mainstream mechanism —
that is how both sides of the STXBP1, SYT1, STX1B, VAMP2 debates appear in the graph without a
`driven_by` edge that has only contradicting evidence.

## Open questions a biochemist should review

1. **Is the STXBP1↔SLC6A1 bridge mechanistically real, or two separate proteostasis stories
   joined by one convenient drug?** Munc18-1 is a cytosolic chaperone that *aggregates*;
   GAT-1 is a polytopic membrane transporter *retained in the ER*. Both are "destabilization",
   but the cell-biological route differs. Does 4-PBA act on the mutant at all, or mainly on
   wild-type trafficking (PMID:35911425 says this is unresolved)?
2. **Which variants are folding-correctable?** ~1/3 of SLC6A1 LoF missense variants reach the
   surface with reduced transport (PMID:38781976) and are outside any chaperone's reach, and
   Munc18-1 G544D resists a rescue that works in pure haploinsufficiency (PMID:38242640). The
   functional classifications exist — can existing cohorts be re-analysed by variant class?
3. **STXBP1: haploinsufficiency or dominant-negative?** PMID:27597756 shows mutant polymers
   co-aggregating wild-type Munc18-1; PMID:29538625 finds no effect on a heterozygous
   background. Which is right determines whether gene supplementation can work at all — and the
   first AAV trial was just terminated.
4. **Is NSF genuinely in this family?** Its phenotype profile is the closest match to UNC13A in
   the slice, but the only mechanism evidence is a *Drosophila* eye assay.
5. **CPLX1**: complexin is a fusion *clamp*, so recessive loss should de-clamp spontaneous
   release — but no functional study of patient variants exists. Does the phenotype fit a
   clamping defect or a priming defect?
6. **SNAP25 CMS vs DEE**: OMIM calls 616330 a congenital myasthenic syndrome while ClinGen
   rates SNAP25 Definitive for DEE. Do SNAP25-DEE patients have subclinical neuromuscular
   involvement (i.e. is repetitive nerve stimulation worth doing, and 3,4-DAP worth trying)?
7. **AAV packaging**: `attrs.cds_length_bp` and `aav_cds_fits_4_7kb` are on every gene node.
   UNC13A (5,112 bp CDS) does not fit a standard AAV; everything else does. Is that the real
   constraint for a Munc13-1 strategy, or is dose/regulation the bigger problem?

## Gaps recorded in the file

`gap:stx1a-mendelian-validity`, `gap:cplx1-functional-evidence`, `gap:nsf-functional-evidence`,
`gap:syt1-stx1b-therapy` (no therapy evidence found at all for STX1B, CPLX1, STX1A, NSF),
`gap:bridge-human-efficacy`, `gap:variant-level-mechanism-map`, `gap:snap25-cms-vs-dee`.
Each lists what is missing, exactly what was searched, and how to find out.

## Files written by this layer

```
pipeline/biology/{common,fetch_genes,fetch_diseases,hpo,clinvar,quickgo,pubmed,
                 curation,build_biology,verify_quotes,validate}.py  run_all.sh
data/raw/biology/{genes,diseases,clinvar_summary,hpo_fragment,hpo_stats,go_fragment}.json
data/raw/biology/{hgnc,uniprot,ensembl,monarch,ols4,orphadata,opentargets,clinvar,quickgo}/
data/raw/biology/pubmed/<PMID>.json          (62 abstracts)
data/raw/biology/clinicaltrials/<NCT>.json   (5 trial records)
data/raw/downloads/{phenotype.hpoa,hp.obo,genes_to_disease.txt}   (gitignored)
data/curated/biology.json
```
