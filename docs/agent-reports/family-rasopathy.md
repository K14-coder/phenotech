# Family: RASopathies (family id `rasopathy`)

Twelve genes: PTPN11, SOS1, RAF1, BRAF, KRAS, HRAS, NF1, MAP2K1, SHOC2, CBL, RIT1 and LZTR1. The fragment is
`data/curated/family_rasopathy.json` (`{nodes, edges, clusters, gaps}`, as in `docs/SCHEMA.md`), built 2026-10-03/04.

Every disease and gene node carries `attrs.family = "rasopathy"`, and so do the other nodes and edges this family
created. The fragment reuses the existing ids `mech:gain-of-function`, `mech:loss-of-function`,
`mech:dominant-negative` and the existing phenotype nodes (HP:0001249, HP:0001718); it never re-emits them.

## Counts

| Nodes | n | Edges | n |
|---|---|---|---|
| phenotype (new; 2 more reused) | 115 | has_phenotype | 215 |
| variant_group | 52 | studies | 81 |
| study (ClinicalTrials.gov) | 20 | variant_in | 52 |
| researcher | 14 | serves | 36 |
| disease | 12 | covers | 26 |
| gene | 12 | has_effect | 20 |
| patient_org | 7 | similar_phenotype | 20 |
| therapy | 7 | participates_in | 18 |
| mechanism (4 GO processes + TOR signaling) | 5 | driven_by | 14 |
| asset | 4 | works_on | 15 |
| | | tests | 14 |
| | | causes | 12 |
| | | developed_for | 11 |
| | | targets | 7 |
| | | shares_mechanism | 4 |
| | | maintains | 3 |
| **248** | | **548** | |

There are 4 clusters and 7 gaps. 14 edges are `contested`, carrying 23 counter-evidence items; the other 534 are
`supported`.

By evidence level, the 548 edges are: curated 321, inferred 122, clinical 35, observational 35 and experimental 35.
The evidence cites 77 distinct PMIDs and 20 NCT records, plus 2 FDA labels quoted from openFDA, with DailyMed links.

### Verification results

- **Quotes: 443 checked, 443 verified, 0 failed** (`verify.py --write`). By source:
  - PubMed 173
  - Website 148 (org pages and the FDA labels)
  - ClinicalTrials.gov 105
  - UniProt 12
  - GO 5
- **Needles: 149 curated, 149 resolved.** Each resolves uniquely against the stored sources (`curation.py`).
- **Endpoints:** every edge endpoint and cluster member exists in this fragment or in the other merged fragments. The
  check after the merge also finds **0 endpoints missing** from the fragment plus `data/graph.json`.
- **Schema:** edge ids are deterministic and every relation type is legal. Every edge has evidence and every evidence
  item has a url. All PubMed and Website evidence carries a quote.
- **Merge:** `python3 pipeline/build_graph.py` reports **Problems: None.** All 548 edges merged, with 0 unverified
  quotes on them. The only attribute conflict listed comes from the earlier `4-phenylbutyrate` node, not from this
  family.

### How the integrity is enforced

These mechanisms were adapted from the biology layer:

- **Needles, not quotes.** `curation.py` never stores a hand-typed quote. Each claim stores a needle:
  - for PubMed, `quote_for()` returns the full sentence of the stored abstract that contains the needle;
  - for CT.gov records, FDA labels and web pages, the needle itself must be a substring of the stored text.

  A needle that is missing or ambiguous raises an error.
- **Independent re-check.** `verify.py` re-reads every source from disk and string-matches every quote, without using
  the needles.
- **Stored sources.** PubMed abstracts come from E-utilities XML. Trials come from the CT.gov API v2. Labels come from
  openFDA. Org pages are fetched and stored as text, with e-mail addresses redacted.
- **Database records.** Database evidence (OMIM, Orphanet association types, ClinGen, Gene2Phenotype, ClinVar, GO,
  HPO) is cited as a record without a quote.

## How to re-run

```bash
pipeline/families/rasopathy/run.sh          # everything, in order; cached responses make it fast
# or the offline tail only:
cd pipeline/families/rasopathy && python3 curation.py && python3 build.py && python3 verify.py --write \
  && python3 ../../build_graph.py
```

### Steps and raw output

| Step | What it does |
|---|---|
| `fetch_bio.py` | Gene and disease records: HGNC, UniProt, Ensembl, Monarch (OMIM/Orphanet/ClinGen edges), Orphadata association types, Open Targets |
| `clinvar.py` | ClinVar P/LP germline spectrum. Reuses `classify()` from `pipeline/biology/clinvar.py`. |
| `quickgo.py` | GO process mechanisms: Ras signal transduction GO:0007265, MAPK cascade GO:0000165, ± regulation GO:0046580/GO:0046579, TOR signaling GO:0031929 |
| `hpo.py` | Phenotypes, IC-weighted. Reuses the biology parsers. |
| `discover.py` / `pubmed.py` | Logged PubMed searches; abstracts stored locally |
| `fetch_labels.py` | openFDA labels |
| `fetch_ctgov.py` | 40 logged CT.gov queries |
| `fetch_web.py` | Org pages; Bright Data is opt-in |
| `fetch_authors.py` | PubMed senior authors per gene |
| `build.py` | Assembles the fragment |
| `verify.py` | Re-checks quotes, endpoints and schema |

Raw responses are stored under `data/raw/families/rasopathy/`.

### Rate limits and budget

- **NCBI:** every E-utilities call goes through the shared cross-process file-lock throttle in
  `pipeline/biology/common.py`:
  - at most 2 requests per second;
  - `tool=rare-disease-atlas`;
  - no email parameter;
  - backoff on 429.
- **Bright Data:** 1 Web Unlocker request out of the 150 allowed (`bd_usage.json`).
- **OpenAI:** no calls.

### Method notes

- **Subtypes are germline only.** `ras_subtypes.GERMLINE_OMIM` decides which entities count; `build.py` asserts that
  each one is a Monarch OMIM causal edge.
  - Somatic cancers, mosaic entities and JMML are listed in `attrs.excluded_entities` and kept out of the HPO
    profiles. Examples: KRAS lung cancer, BRAF colorectal cancer, HRAS epidermal nevus, MAP2K1 melorheostosis.
  - `attrs.gene_disease_validity` records ClinGen and Gene2Phenotype, including the ClinGen *Disputed* calls such as
    PTPN11 for Costello syndrome.
- **Phenotype similarity uses a stricter cut-off than the biology layer.** The RASopathies resemble each other by
  design: 62 of 66 pairs passed the biology layer's 95th/99th-percentile rule. This family therefore requires the
  **top 0.1% of both** background distributions, which leaves 20 `similar_phenotype` edges. The strongest pairs, by
  Resnik best-match average, are:
  - RIT1–LZTR1, 2.76
  - KRAS–LZTR1, 2.73
  - BRAF–KRAS, 2.71

  Each disease keeps 14–20 HPO terms, out of 22–133 annotated.
- **Variant groups.** Multi-gene copy-number variants get no mechanism edge. They dominate the ClinVar records for
  SHOC2 (25/32), CBL, HRAS and LZTR1, where 382 records fall in the 22q11.2 region. Truncating variants in
  gain-of-function genes also get no `has_effect` edge.
- **Studies mapped by syndrome.** Some studies enrol by syndrome without naming a gene, for example "any gene causing
  Noonan, Costello or CFC syndrome". Their `studies` edges are `inferred` (confidence 0.55, `via_syndrome`). Edges
  where the record names the gene are `curated` (0.9).
- **Exclusions are respected.** The NCI RASopathy cohort (NCT04888936) explicitly says "excluding NF1", so it has no
  NF1 edge.

## Top 5 evidence-backed connections

### 1. Cross-member drug repurposing: from the NF1 approval to RAF1 and RIT1 heart disease

This is the strongest repurposing case in the atlas: one drug class, approved for one member of the family, is now
being tested in other members.

**Approved in NF1.** Two MEK inhibitors are approved for NF1 plexiform neurofibromas, and the FDA label text is quoted
for both:

- selumetinib, supported by:
  - the SPRINT trial, NCT01362803 (PMID:32187457);
  - the KOMET trial, NCT04924608 (PMID:40473450);
- mirdametinib, supported by the ReNeu trial, NCT03962543 (PMID:39514826).

**Used off-label in other members.** The same drug class has been used off-label for:

- RAF1 hypertrophic cardiomyopathy (HCM):
  - an adult (PMID:38827265);
  - a newborn (PMID:35052347);
  - Raf1 L613V mice rescued by MEK inhibition (PMID:21339642);
- RIT1 HCM, with complete remission (PMID:36184070);
- SOS1 lymphatic disease (PMID:33219052);
- a retrospective comparison of 61 patients, which reported lower mortality and morbidity (PMID:40131150).

**Now in trials.**

- MEKinRAS, NCT06555237: phase 2, recruiting.
- Baby MERIT, NCT07817186: phase 3, not yet recruiting.

**In the graph.**

- `disease:NF1|shares_mechanism|disease:RAF1`, contested because pulmonary vascular disease did not respond.
- `disease:NF1|shares_mechanism|disease:RIT1`.
- The trametinib `developed_for` edges, which carry the "dedicated clinical trials are required" counter-evidence.

### 2. Same gene, different mechanism, different trial eligibility: PTPN11

PTPN11 variants act in three different ways:

| Disorder | Effect of the variants | Sources |
|---|---|---|
| Noonan syndrome | Gain of function | PMID:11704759, PMID:16358218 |
| NSML | Catalytically defective and dominant negative | PMID:16377799, PMID:16358218; in vivo PMID:21339643 |
| Metachondromatosis (truncating variants) | Loss of function | PMID:21533187 |

**Therapy follows the mechanism.** Baby MERIT explicitly **excludes "PTPN11 pathogenic/likely pathogenic variants
causing NSML"** while admitting other Noonan genes; this is quoted from the CT.gov record. In mice with NSML-type
mutations, rapamycin reversed HCM (PMID:21339643, PMID:22058153). Human NSML heart tissue advises caution
(PMID:31722741), and the dominant-negative reading is itself contested (PMID:24935154).

The graph has three separate `driven_by` edges, with the mechanism stated per subtype.

### 3. What failed

Targeting RAS upstream of MEK, or repurposing statins, did not work in people:

- **Tipifarnib** blocks RAS farnesylation. Its randomised phase 2 trial in NF1 plexiform neurofibromas did not prolong
  time to progression (PMID:24500418, NCT00021541).
- **Lovastatin** reversed learning deficits in Nf1+/- mice (PMID:16271875). However, simvastatin (PMID:18632543) and
  lovastatin (PMID:27956565, NCT00853580) **did not improve cognition** in randomised trials in children with NF1.
- **The lovastatin/lamotrigine RASopathy trial** (NCT03504501) terminated because of recruitment difficulties.
- **The first MEK-inhibitor trial in Noonan HCM** (binimetinib, NCT01556568) was **withdrawn** before enrolling
  anyone. The record gives the reason as "scientific and business considerations".

All of these appear as counter-evidence on the corresponding `developed_for` edges and as studies.

### 4. Loss of RAS regulation: NF1, LZTR1 and CBL

These three genes encode proteins that normally switch RAS off:

- neurofibromin is a RAS GTPase-activating protein (GAP) (PMID:35066574);
- LZTR1 drives RAS ubiquitination (PMID:30442762, PMID:30442766);
- CBL is an E3 ubiquitin ligase (PMID:20619386).

The CBL discovery paper explicitly likens the disorder to NF1 (PMID:20694012).

LZTR1 is also a second same-gene-different-mechanism case:

| LZTR1 variants | Effect | Source |
|---|---|---|
| Dominant Noonan variants | Hit the Kelch substrate surface and enhance signalling | PMID:30481304 |
| Biallelic variants | Recessive Noonan syndrome | PMID:29469822 |
| Heterozygous loss of function | Schwannomatosis and isolated café-au-lait macules | PMID:39140257 |

Baby MERIT explicitly admits biallelic LZTR1. The relevant items are `cluster:rasopathy-loss-of-ras-regulation`,
`disease:NF1|shares_mechanism|disease:LZTR1` and the corresponding edge for CBL.

### 5. Activating alleles and HCM line up with the MEK-inhibitor evidence

- RAF1 variants in the two HCM hotspots are **kinase-activating**, and 95% of carriers had HCM. RAF1 variants outside
  the hotspots are kinase-impaired (PMID:17603483).
- 70% of RIT1 carriers had HCM (PMID:23791108).

These are exactly the genes with clinical MEK-inhibitor HCM reports, which suggests that allele-level activation, not
just gene membership, predicts who benefits. CFC MEK1 variants are sensitive to MEK inhibition in vitro
(PMID:17981815), but we found no clinical report for them. This is recorded as a gap.

## Community (reduced scope)

### Patient organisations

All 7 are verified with quotes from their own sites:

- RASopathies Network. Its syndromes page lists the genes for each syndrome, so `serves` edges to all 12 genes rest on
  its own quotes.
- Noonan Syndrome Foundation (US).
- Noonan Syndrome Association (UK). It names PTPN11.
- CFC International.
- Children's Tumor Foundation.
- NF Network.
- Nerve Tumours UK.

When an org page does not name the gene, the org-to-gene links are `inferred` (0.5–0.6).

### Assets

- **NF Registry.** Run by CTF (Children's Tumor Foundation); its record on ClinicalTrials.gov is NCT01885767.
- **CITIZEN CFC Syndrome Registry.** Run by CFC International.
- **RASopathies Network contact registry.** The network says it is still building it.
- **PATRAS / EURAS registry.** Known only from the RASopathies Network page.

### Studies

There are 20 study nodes:

- **10 MEK-inhibitor studies:**
  - in NF1: SPRINT, KOMET, the NCI adult phase 2, the NF1 low-grade glioma phase 3, ReNeu, binimetinib and trametinib;
  - in Noonan-spectrum HCM: MEKinRAS, Baby MERIT and the withdrawn MEK162 trial.
- **4 failed or terminated trials:** tipifarnib, two statin trials and the simvastatin trial in Noonan syndrome.
- **6 natural history studies, registries and biorepositories:**
  - the NCI RASopathy cohort;
  - RAS-CM (natural history of RASopathy cardiomyopathy);
  - the Cincinnati RASopathy biorepository;
  - the NCI NF1 natural history study;
  - the NF Registry;
  - the WashU NF1 registry.

### Research groups

Groups are senior authors with at least 2 gene-focused papers since 2018, among the top 80 papers by relevance. 14
researchers are listed, with professional information only. Yoko Aoki (Tohoku University) bridges RIT1 and LZTR1.

| Gene | Groups |
|---|---|
| NF1 | Gutmann, Messiaen, Brems, Reid, Melis |
| LZTR1 | Smith (Manchester), Cyganek (Göttingen), Aoki (Tohoku) |
| HRAS | Flex (ISS), Rauen (UC Davis), Rosenberger (Hamburg-Eppendorf) |
| SHOC2 | Simanshu, Rodriguez-Viciana |
| SOS1 | Green (Stanford) |
| RIT1 | Aoki (Tohoku) |

Six genes have none at this threshold: PTPN11, RAF1, BRAF, KRAS, MAP2K1 and CBL. Their papers are spread across many
single-paper senior authors. This is a precision-over-recall choice, not an absence of groups.

## Gaps (7, each with the exact searches run)

1. **`gap:rasopathy-mek-noonan-efficacy`.** No completed controlled trial of MEK inhibition exists outside NF1. The
   2012 MEK162 trial was withdrawn, and the 61-patient comparison is not broken down by gene.
2. **`gap:rasopathy-nsml-therapy`.** NSML-type PTPN11 variants are excluded from the MEK trial, and rapamycin evidence
   is preclinical only, with a human-tissue caution.
3. **`gap:rasopathy-cfc-costello-mek`.** There is in-vitro evidence only for CFC MEK1 variants. No clinical report or
   trial was found for CFC or Costello syndrome specifically.
4. **`gap:rasopathy-costello-patient-org`.** costellokids.org returned no readable text, either directly or through
   Bright Data, and the .org.uk site did not respond. HRAS is served only through the RASopathies Network.
5. **`gap:rasopathy-cognition`.** The statin trials failed. No MEK-inhibitor cognition trial was found.
6. **`gap:rasopathy-variant-level-mechanism`.**
   - Our ClinVar groups are consequence classes. They do not separate activating from catalytically impaired missense
     variants (PTPN11 and RAF1) or the LZTR1 classes.
   - Multi-gene copy-number variants dominate several genes.
7. **`gap:rasopathy-shoc2-cbl-hras-trials`.** No gene-specific interventional study was found for SHOC2, CBL or
   Costello syndrome.

## Caveats

- **Missing GO annotations.** QuickGO has no annotations for CBL or RIT1 to the four RAS/MAPK processes. NF1 is not
  annotated to "negative regulation of Ras protein signal transduction". The graph shows these as missing rather than
  inferring them.
- **Contested labels.** The MAP2K1 gain-of-function edge is contested on purpose: CFC MEK1 variants still need RAF to
  phosphorylate them (PMID:17981815). The selumetinib→NF1 edge is approved but also `contested`, because the KOMET
  quality-of-life difference was not significant and some children stopped treatment for toxicity. These limits are
  shown, not hidden.
- **Parallel agents.** Other agents edited their own fragments while this ran. The final `build_graph.py` merged 8
  fragment files, including `family_dee` and `family_lysosomal`, with **Problems: None**. The other families' numbers are
  outside this report.
