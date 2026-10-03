# OpenAI extraction: an independent second reading of the literature

Generated 2026-10-03 19:04 UTC by `pipeline/openai/`. Model: **`gpt-6-astra`** (as returned by the API), via Sign in with ChatGPT (plan usage), structured outputs (`json_schema`, strict). Nothing here was typed by hand: every number below is recomputed by `node pipeline/openai/compare.mjs`.

The curated graph was built by agent curation with string-verified quotes. This layer reads the same stored abstracts **independently** with OpenAI, keeps only claims whose quote is a verbatim sentence of the stored abstract, maps them onto graph nodes, and compares. The evidence story becomes: **two independent extractors, verbatim quotes, disagreements flagged for human review.**

## Headline numbers

| | |
|---|---|
| Abstracts processed | **78** (biology 62/62; community 16/587 with abstracts) |
| Claims extracted | 587 |
| Quote-verified (verbatim substring of stored title + abstract) | **587 (100%)**; 0 rejected, none edited |
| Reconciled (both endpoints mapped to an existing node) | 291 (49.6% of verified) |
| Compared with graph edges (after the fixed mapping rules) | 290 |
| **Agreement** on (edge, PMID) pairs both extractors cite | **60/68 (88.2%)** |
| Curated (edge, PMID) pairs for these abstracts re-found independently | 68/255 (26.7%) |
| (a) disagreements on a paper both cite | 8 |
| (b) new supporting sources for existing edges | 111 |
| (d) new contradicting sources, flagged for review | 2 |
| (c) candidate new edges (`status: unverified`, confidence ≤ 0.5) | 57 |
| Synonyms proposed | 36 on 17 nodes |
| Usage limit | The ChatGPT plan limit was reached during reconciliation: 10 abstracts (62 mentions) got the deterministic index only. Rerunning `reconcile.mjs` later completes them from cache. |

## Agreement by relation type

A pair is one graph edge and one PMID. "Agree" means the OpenAI claim has the same polarity as the curators' filing of that PMID on that edge (supporting evidence vs. counter-evidence). Coverage is how many curated pairs for the processed abstracts the model found on its own.

| Edge type | Pairs both cite | Agree | Disagree | Agreement | Curated pairs re-found | New supporting (b) | New contradicting (d) |
|---|---|---|---|---|---|---|---|
| `causes` | 8 | 8 | 0 | 100.0% | 8/9 | 39 | 0 |
| `developed_for` | 9 | 8 | 1 | 88.9% | 9/28 | 2 | 0 |
| `driven_by` | 33 | 26 | 7 | 78.8% | 33/45 | 21 | 0 |
| `has_effect` | 8 | 8 | 0 | 100.0% | 8/35 | 3 | 1 |
| `has_phenotype` | 8 | 8 | 0 | 100.0% | 8/119 | 24 | 1 |
| `participates_in` | 0 | 0 | 0 | n/a | 0/0 | 22 | 0 |
| `targets` | 2 | 2 | 0 | 100.0% | 2/19 | 0 | 0 |
| **all** | **68** | **60** | **8** | **88.2%** | **68/255** | **111** | **2** |

Note: `has_phenotype` pairs come from HPO annotations that cite a PMID (no curator quote); the model reads only the abstract, so phenotypes reported in full texts are not expected to be re-found.

## Disagreements for a biochemist to review

10 items, most important first (a paper both extractors cite but read differently ranks highest; then direct contradictions on high-confidence mechanism and therapy edges). "Curated" is the quote the curators filed for that PMID on the edge, or, when the curators did not cite this PMID, their main supporting quote. In the graph these appear as `cross_checked.agrees: false` stamps (a) or as counter-evidence with `needs_review: true` (d); they do not change an edge's status until a person reviews them.

### 1. `therapy:4-phenylbutyrate|developed_for|disease:SLC6A1`

Both cite PMID:39923323. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. Edge: contested, confidence 0.8, clinical. Claim: Ravicti → *developed_for* → treatment-resistant epilepsy (established, clinical_trial, human).

- Curated (PMID:39923323, contradicts): "Post-treatment EEGs showed a moderate reduction in epileptiform discharges following PBA administration, and patients exhibited improved motor function."
- OpenAI (PMID:39923323): "Our previous work on SLC6A1 missense mutations prompted a clinical trial for Ravicti (NCT04937062), a glycerol formulation of 4-phenylbutyrate (PBA), for treatment-resistant epilepsy."

### 2. `disease:STX1B|driven_by|mech:loss-of-function`

Both cite PMID:33677401. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. Edge: contested, confidence 0.7, experimental. Claim: STX1B loss-of-function variants → *has_effect* → loss-of-function (established, case_series, human).

- Curated (PMID:33677401, contradicts): "The identification of loss-of-function variants in very differently affected individuals suggests that no clear genotype-phenotype correlation can be established."
- OpenAI (PMID:33677401): "RESULTS: We identified four unrelated individuals with pathogenic or likely pathogenic variants in STX1B (one missense and three loss-of-function variants)."

### 3. `disease:STXBP1|driven_by|mech:protein-destabilization`

Both cite PMID:31855252. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. Edge: contested, confidence 0.7, experimental. Claim: STXBP1 encephalopathy → *driven_by* → Impaired mutant protein stability leading to reduced synaptic transmission (suggested, functional_study).

- Curated (PMID:31855252, contradicts): "Hence, the homozygous L446F mutation causes a gain-of-function phenotype regarding release probability and synaptic transmission while having less impact on protein levels than previously reported (heterozygous) mutations."
- OpenAI (PMID:31855252): "Impaired mutant protein stability leading to reduced synaptic transmission is considered the main underlying pathogenetic mechanism."

### 4. `disease:SYT1|driven_by|mech:gain-of-function`

Both cite PMID:38321119. Curators filed it as **supporting**; the OpenAI reading reports the **opposite effect class** for this gene. Edge: contested, confidence 0.5, experimental. Claim: Syt1PL → *has_effect* → dominant-negative (established, functional_study, cell).

- Curated (PMID:38321119, supports): "This is a novel cellular phenotype, distinct from what was previously found for other SYT1 disease variants, and points to a role for spontaneous and asynchronous release in SYT1-associated neurodevelopmental disorder."
- OpenAI (PMID:38321119, opposite effect): "Syt1PL acts in a dominant-negative manner supporting a causative role for the mutation in the heterozygous patient."

### 5. `disease:STX1B|driven_by|mech:loss-of-function`

Both cite PMID:42673765. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. **Same sentence, filed differently:** both extractors quote it; the curators treat it as a limiting or mixed finding (counter-evidence), the model as plain support. A reviewer decides which filing fits. Edge: contested, confidence 0.7, experimental. Claim: STX1B G226R → *has_effect* → loss-of-function (established, functional_study, cell).

- Curated (PMID:42673765, contradicts): "FINDINGS: G226R exhibited both gain- and loss-of-function characteristics, with increased miniature excitatory postsynaptic current frequency in networks but not in autapses, and synaptic failure during sustained high-frequency stimulation."
- OpenAI (PMID:42673765): "G226R exhibited both gain- and loss-of-function characteristics, with increased miniature excitatory postsynaptic current frequency in networks but not in autapses, and synaptic failure during sustained high-frequency stimulation."

### 6. `disease:STXBP1|driven_by|mech:haploinsufficiency`

Both cite PMID:38242640. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. **Same sentence, filed differently:** both extractors quote it; the curators treat it as a limiting or mixed finding (counter-evidence), the model as plain support. A reviewer decides which filing fits. Edge: contested, confidence 0.7, experimental. Claim: STXBP1 encephalopathies → *driven_by* → haploinsufficiency (established, functional_study).

- Curated (PMID:38242640, contradicts): "Although haploinsufficiency is the prevailing disease mechanism, it remains unclear how the reduction in Munc18-1 levels causes synaptic dysfunction in disease as well as how haploinsufficiency alone can account for the significant heterogeneity among patients in terms of the presence, onset and severity of different symptoms."
- OpenAI (PMID:38242640): "Although haploinsufficiency is the prevailing disease mechanism, it remains unclear how the reduction in Munc18-1 levels causes synaptic dysfunction in disease as well as how haploinsufficiency alone can account for the significant heterogeneity among patients in terms of the presence, onset and severity of different symptoms."

### 7. `disease:UNC13A|driven_by|mech:gain-of-function`

Both cite PMID:41125872. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. **Same sentence, filed differently:** both extractors quote it; the curators treat it as a limiting or mixed finding (counter-evidence), the model as plain support. A reviewer decides which filing fits. Edge: contested, confidence 0.5, experimental. Claim: UNC13A variants → *has_effect* → gain-of-function (established, functional_study, mouse).

- Curated (PMID:41125872, contradicts): "Using assays with expression of UNC13A variants in mouse hippocampal neurons and in Caenorhabditis elegans, we identify three mechanisms of pathogenicity, including reduction in synaptic strength caused by reduced UNC13A protein expression, increased neurotransmission caused by UNC13A gain-of-function and impaired regulation of neurotransmission by second messenger signalling."
- OpenAI (PMID:41125872): "Using assays with expression of UNC13A variants in mouse hippocampal neurons and in Caenorhabditis elegans, we identify three mechanisms of pathogenicity, including reduction in synaptic strength caused by reduced UNC13A protein expression, increased neurotransmission caused by UNC13A gain-of-function and impaired regulation of neurotransmission by second messenger signalling."

### 8. `disease:STXBP1|driven_by|mech:dominant-negative`

Both cite PMID:32643187. Curators filed it as **contradicting**; the OpenAI reading takes it as **supporting** the edge. **Same sentence, filed differently:** both extractors quote it; the curators treat it as a limiting or mixed finding (counter-evidence), the model as plain support. A reviewer decides which filing fits. Edge: contested, confidence 0.5, experimental. Claim: STXBP1-linked disorders → *driven_by* → dominant-negative mechanisms (speculative, review).

- Curated (PMID:32643187, contradicts): "The molecular disease mechanisms underlying STXBP1-linked disorders are yet to be fully understood, but both haploinsufficiency and dominant-negative mechanisms have been proposed."
- OpenAI (PMID:32643187): "The molecular disease mechanisms underlying STXBP1-linked disorders are yet to be fully understood, but both haploinsufficiency and dominant-negative mechanisms have been proposed."

### 9. `vg:STXBP1:missense|has_effect|mech:dominant-negative`

New source: the OpenAI reading of PMID:31855252 reports the **opposite effect class** for this gene, and the graph has no edge for that effect. Edge: contested, confidence 0.6, experimental. Claim: STXBP1 homozygous L446F mutation → *has_effect* → gain-of-function phenotype regarding release probability and synaptic transmission (established, functional_study, cell).

- Curated (PMID:27597756, supports): "Here, we used single-molecule analysis, gene-edited cells, and neurons to demonstrate that Munc18-1 EIEE-causing mutants form large polymers that coaggregate wild-type Munc18-1 in vitro and in cells."
- OpenAI (PMID:31855252, opposite effect): "Hence, the homozygous L446F mutation causes a gain-of-function phenotype regarding release probability and synaptic transmission while having less impact on protein levels than previously reported (heterozygous) mutations."

### 10. `disease:STX1B|has_phenotype|phenotype:HP:0002373`

New source: the OpenAI reading of PMID:30737342 states the relation does **not** hold (negated). Edge: supported, confidence 0.9, curated. Claim: genetic generalized epilepsy → *has_phenotype* → febrile seizures (established, cohort, human, negated).

- Curated (PMID:25362483, supports): "(no quote: HPO record)"
- OpenAI (PMID:30737342): "We discerned 4 different phenotypic groups across the newly identified and previously published patients (49 patients in 23 families): (1) 6 sporadic patients or families (31 affected individuals) with febrile and afebrile seizures with a benign course, generally good drug response, normal development, and without permanent neurologic deficits; (2) 2 patients with genetic generalized epilepsy without febrile seizures and cognitive deficits; (3) 13 patients or families with intractable seizures, developmental regression after seizure onset and additional neuropsychiatric symptoms; (4) 2 patients with focal epilepsy."

## New supporting sources for existing edges (b)

111 (edge, PMID) pairs where the model found support for an existing edge in a paper the curators did not cite on that edge. `build_graph.py` adds them as evidence with `extracted_by: openai:gpt-6-astra`, `verified: true`.

| Edge type | New supporting sources |
|---|---|
| `causes` | 39 |
| `developed_for` | 2 |
| `driven_by` | 21 |
| `has_effect` | 3 |
| `has_phenotype` | 24 |
| `participates_in` | 22 |

- `disease:SLC6A1|driven_by|mech:haploinsufficiency` ← PMID:41174879 (established, cohort): "SLC6A1 haploinsufficiency has been confirmed as the predominant pathway of SLC6A1-related neurodevelopmental disorder (SLC6A1-NDD); however, the molecular mechanism underlying the variable clinical presentation remains unclear."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:34028503 (established, functional_study): "We found that a partial or complete loss-of-function represents a common disease mechanism, although the extent of GABA uptake reduction is variable."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:35911425 (established, functional_study): "Based on functional assays of solute carrier Family 6 Member 1 variants, we conclude that partial or complete loss of γ-amino butyric acid uptake due to reduced membrane γ-amino butyric acid transporter 1 trafficking is the primary aetiology."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:36741049 (established, functional_study): "We systematically examined fifteen hGAT-1 disease variants, all of which dramatically reduced or completely abolished GABA uptake activity."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:38781976 (established, functional_study): "Surprisingly, recurrent de novo missense variants showed moderate loss-of-function effects that reduced GABA uptake with no evidence for dominant-negative or gain-of-function effects."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:41174879 (suggested, animal_model): "We confirm phenotypes in flies expressing SLC6A1 variants consistent with a partial loss-of-function mechanism."
- `disease:SLC6A1|driven_by|mech:loss-of-function` ← PMID:42650175 (established, functional_study): "CONCLUSIONS: GAT-1 p.Ala305Val is a trafficking-impaired, loss-of-function variant whose dysfunction is amenable to two convergent therapeutic axes: pharmacologic correction of folding and trafficking, and augmentation of functional transporter expression."
- `disease:SNAP25|driven_by|mech:loss-of-function` ← PMID:25381298 (established, functional_study): "CONCLUSION: Ile67Asn variant in SNAP25B is pathogenic because it inhibits synaptic vesicle exocytosis."
- `disease:STXBP1|driven_by|mech:dominant-negative` ← PMID:30266908 (established, functional_study): "Aggregates of mutant Munc18-1 incorporate wild-type Munc18-1, depleting functional Munc18-1 levels beyond hemizygous levels."
- `disease:STXBP1|driven_by|mech:dominant-negative` ← PMID:33332765 (established, functional_study): "Munc18-1 is essential for neurotransmitter release, and mutations in Munc18-1 have been shown to cause neuronal dysfunction via aggregation and co-aggregation of the wild-type protein, reducing functional Munc18-1 levels well below hemizygous levels."
- `disease:STXBP1|driven_by|mech:gain-of-function` ← PMID:27597756 (suggested, functional_study): "Munc18-1 heterozygous mutations cause developmental defects and epileptic phenotypes, including infantile epileptic encephalopathy (EIEE), suggestive of a gain of pathological function."
- `disease:STXBP1|driven_by|mech:haploinsufficiency` ← PMID:32643187 (speculative, review): "The molecular disease mechanisms underlying STXBP1-linked disorders are yet to be fully understood, but both haploinsufficiency and dominant-negative mechanisms have been proposed."
- `disease:STXBP1|driven_by|mech:protein-destabilization` ← PMID:18469812 (established, functional_study): "Circular dichroism melting experiments revealed that a mutant form of the protein was significantly thermolabile compared to wild type."
- `disease:STXBP1|driven_by|mech:protein-destabilization` ← PMID:27597756 (established, functional_study): "Surprisingly, Munc18-1 EIEE mutants also form Lewy body-like structures that contain α-synuclein (α-Syn)."
- `disease:STXBP1|driven_by|mech:protein-destabilization` ← PMID:33332765 (established, functional_study): "Munc18-1 is essential for neurotransmitter release, and mutations in Munc18-1 have been shown to cause neuronal dysfunction via aggregation and co-aggregation of the wild-type protein, reducing functional Munc18-1 levels well below hemizygous levels."
- `disease:STXBP1|driven_by|mech:protein-destabilization` ← PMID:38242640 (established, functional_study): "Using biochemical and cell biological readouts on mouse brains, cultured mouse neurons and heterologous cells, we found that the synaptic Munc18-1 interactors Doc2A and Doc2B are unstable in the absence of Munc18-1 and aggregate in the presence of disease-causing Munc18-1 mutants."
- `disease:SYT1|driven_by|mech:dominant-negative` ← PMID:38321119 (established, functional_study): "Syt1PL acts in a dominant-negative manner supporting a causative role for the mutation in the heterozygous patient."
- `disease:SYT1|driven_by|mech:dominant-negative` ← PMID:41438914 (suggested, case_report): "The precise pathogenic mechanism of BAGOS is still unclear, with preliminary data favoring a dominant-negative effect, although a previous case presenting a reciprocal translocation disrupting SYT1 supports haploinsufficiency as a possible mechanism."
- `disease:SYT1|driven_by|mech:dominant-negative` ← PMID:41475766 (established, functional_study): "However, overexpression of BAGOS SYT1 mutants in either WT mouse neurons or hiPSC-derived human neurons, a condition closer to the heterozygotic genotype of patients, revealed a dominant-negative effect of the mutant proteins."
- `disease:SYT2|driven_by|mech:dominant-negative` ← PMID:32776697 (suggested, functional_study): "These variants are thought to have a dominant-negative effect on synaptic vesicle exocytosis, although the precise pathomechanism remains to be elucidated."
- `disease:UNC13A|driven_by|mech:loss-of-function` ← PMID:36737245 (established, review): "In the absence of functional TDP-43, risk variants in UNC13A lead to the inclusion of a cryptic exon in UNC13A messenger RNA, subsequently leading to nonsense mediated decay, with loss of functional protein."
- `gene:NSF|causes|disease:NSF` ← PMID:31675180 (established, case_series): "De novo heterozygous mutations in the NSF gene cause early infantile epileptic encephalopathy."
- `gene:SLC6A1|causes|disease:SLC6A1` ← PMID:31176687 (suggested, case_report): "Mutations in SLC6A1 have been associated mainly with myoclonic atonic epilepsy (MAE) and intellectual disability."
- `gene:SLC6A1|causes|disease:SLC6A1` ← PMID:36741049 (established, case_series): "Mutations in the human γ-aminobutyric acid (GABA) transporter 1 (hGAT-1) can instigate myoclonic-atonic and other generalized epilepsies in the afflicted individuals."
- `gene:SLC6A1|causes|disease:SLC6A1` ← PMID:39923323 (suggested, case_series): "Haploinsufficient deletions of GABA transporter 1 (GAT-1)- encoding SLC6A1, and GABA transporter 3 (GAT-3)-encoding SLC6A11 are implicated in epileptic syndromes."
- …86 more in `data/build/crosscheck.json` (`case: "b"`).

## Candidate new edges (c)

57 edges whose endpoints both exist but which the graph lacks. Written to `data/curated/openai_extracted.json` with `status: "unverified"`, confidence ≤ 0.5, evidence level from the study type (trial → clinical; functional/animal → experimental; case report/series/cohort/review → observational) and a verbatim, string-verified quote per PMID.

| Candidate edge | PMIDs | Level | Confidence | Certainty |
|---|---|---|---|---|
| `disease:CPLX1|has_phenotype|phenotype:HP:0001263` | 28422131 | observational | 0.5 | established |
| `disease:CPLX1|has_phenotype|phenotype:HP:0032794` | 28422131 | observational | 0.5 | established |
| `disease:SLC6A1|driven_by|mech:gaba-reuptake` | 31176687 | experimental | 0.5 | established |
| `disease:SLC6A1|has_phenotype|phenotype:HP:0000750` | 34006619 | observational | 0.5 | established |
| `disease:SLC6A1|has_phenotype|phenotype:HP:0001250` | 31176687, 34006619, 38781976, 41385967, 41893060 | experimental | 0.5 | established |
| `disease:SNAP25|has_phenotype|phenotype:HP:0001249` | 33299146 | observational | 0.5 | established |
| `disease:SNAP25|has_phenotype|phenotype:HP:0001250` | 41769487 | observational | 0.5 | established |
| `disease:SNAP25|has_phenotype|phenotype:HP:0100704` | 33299146 | observational | 0.5 | established |
| `disease:STX1A|driven_by|mech:snare-complex-assembly` | 36564538 | observational | 0.35 | speculative |
| `disease:STX1A|has_phenotype|phenotype:HP:0000729` | 36564538 | observational | 0.5 | established |
| `disease:STX1A|has_phenotype|phenotype:HP:0001249` | 36564538 | observational | 0.5 | established |
| `disease:STX1B|driven_by|mech:haploinsufficiency` | 26818399, 27648472 | observational | 0.45 | suggested |
| `disease:STX1B|has_phenotype|phenotype:HP:0001249` | 26818399 | observational | 0.5 | established |
| `disease:STX1B|has_phenotype|phenotype:HP:0001250` | 30737342 | observational | 0.5 | established |
| `disease:STX1B|has_phenotype|phenotype:HP:0002197` | 30737342 | observational | 0.5 | established |
| `disease:STX1B|has_phenotype|phenotype:HP:0007359` | 30737342, 33677401 | observational | 0.5 | established |
| `disease:STX1B|has_phenotype|phenotype:HP:0200134` | 33677401 | observational | 0.5 | established |
| `disease:STXBP1|driven_by|mech:loss-of-function` | 41883162 | experimental | 0.5 | established |
| `disease:STXBP1|driven_by|mech:synaptic-vesicle-fusion` | 41714804 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0000729` | 29538625 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0001249` | 29538625, 31855252, 33332765, 38242640, 42182245, 42268630 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0001250` | 35190816, 38242640, 42182245 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0001251` | 33332765, 38242640 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0001263` | 29538625, 31855252, 33332765, 38242640, 42182245 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0001337` | 33332765, 38242640 | experimental | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0007359` | 35190816 | observational | 0.5 | established |
| `disease:STXBP1|has_phenotype|phenotype:HP:0100704` | 40767165 | observational | 0.5 | established |
| `disease:SYT1|driven_by|mech:ca-triggered-exocytosis` | 39481209 | experimental | 0.45 | suggested |
| `disease:SYT1|has_phenotype|phenotype:HP:0000729` | 38321119 | observational | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0001249` | 39481209 | observational | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0001252` | 30107533, 41332143, 41756855 | experimental | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0001263` | 30107533, 38321119, 41756855 | experimental | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0001344` | 41756855 | experimental | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0002187` | 25705886 | observational | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0002353` | 30107533, 41332143, 41756855 | experimental | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0011203` | 25705886, 30107533 | observational | 0.5 | established |
| `disease:SYT1|has_phenotype|phenotype:HP:0100716` | 41332143 | observational | 0.5 | established |
| `disease:SYT2|has_phenotype|phenotype:HP:0003473` | 26519543, 32250532 | observational | 0.5 | established |
| `disease:UNC13A|has_phenotype|phenotype:HP:0001249` | 41125872 | observational | 0.5 | established |
| `disease:UNC13A|has_phenotype|phenotype:HP:0001250` | 41125872 | observational | 0.5 | established |
| `disease:UNC13A|has_phenotype|phenotype:HP:0001263` | 41125872 | observational | 0.5 | established |
| `disease:UNC13A|has_phenotype|phenotype:HP:0001337` | 41125872 | observational | 0.5 | established |
| `disease:UNC13A|has_phenotype|phenotype:HP:0100660` | 41125872 | observational | 0.5 | established |
| `gene:STX1A|participates_in|mech:synaptic-vesicle-fusion` | 30929742 | experimental | 0.5 | established |
| `gene:SYT2|participates_in|mech:ca-triggered-exocytosis` | 25192047 | experimental | 0.5 | established |
| `gene:VAMP2|participates_in|mech:ca-triggered-exocytosis` | 30929742 | experimental | 0.5 | established |
| `gene:VAMP2|participates_in|mech:synaptic-vesicle-fusion` | 30929742 | experimental | 0.5 | established |
| `therapy:3-4-diaminopyridine|developed_for|disease:VAMP2` | 32906212 | observational | 0.5 | established |
| `therapy:4-phenylbutyrate|targets|mech:gaba-reuptake` | 35911425, 39923323, 41385967, 41648160 | experimental | 0.5 | established |
| `vg:SLC6A1:missense|has_effect|mech:loss-of-function` | 25865495, 38781976, 41174879, 42650175 | experimental | 0.5 | established |
| `vg:SLC6A1:truncating|has_effect|mech:loss-of-function` | 25865495 | observational | 0.45 | suggested |
| `vg:SNAP25:missense|has_effect|mech:loss-of-function` | 25381298 | experimental | 0.5 | established |
| `vg:STX1B:missense|has_effect|mech:gain-of-function` | 32572454, 42673765 | experimental | 0.5 | established |
| `vg:STX1B:missense|has_effect|mech:loss-of-function` | 42673765 | experimental | 0.5 | established |
| `vg:STXBP1:missense|has_effect|mech:gain-of-function` | 31855252 | experimental | 0.5 | established |
| `vg:STXBP1:missense|has_effect|mech:loss-of-function` | 25284778 | experimental | 0.5 | established |
| `vg:UNC13A:truncating|has_effect|mech:loss-of-function` | 27648472 | observational | 0.45 | suggested |

## Synonyms added

36 names on 17 nodes. A synonym is proposed only when the OpenAI reconciliation step judged the mention to be **another name for exactly that node** ("same", not a narrower or descriptive mention), the id came from the mention's candidate list, and the mention appears literally in the abstract. They are node stubs (id, type, label, synonyms) that the merge step unions.

| Node | Synonym | PMID(s) | Model's justification |
|---|---|---|---|
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | synaptic vesicle release | 18469812, 41756855 | Synaptic vesicle release denotes vesicle fusion with the presynaptic membrane to release neurotransmitter. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | exocytotic release of neurotransmitters | 25003006 | Exocytotic neurotransmitter release describes synaptic vesicle fusion with the presynaptic membrane, without specifying calcium triggering. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | presynaptic membrane-fusion | 26280581 | Presynaptic membrane fusion here denotes synaptic vesicle fusion with the presynaptic membrane. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | fusion of synaptic vesicles | 30929742 | Describes synaptic vesicle membrane fusion that releases neurotransmitters. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | vesicular exocytosis | 30929742 | In this VAMP2 neurotransmission context, vesicular exocytosis denotes synaptic vesicle fusion. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | synaptic vesicle fusion | 32250532, 32916768 | Synaptic vesicle fusion is the named membrane-fusion process. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | vesicle release | 41714804 | In this presynaptic SNARE context, vesicle release denotes synaptic vesicle fusion and cargo release. |
| `mech:synaptic-vesicle-fusion` (Synaptic vesicle fusion with the active zone membrane) | SV fusion | 41889907 | SV fusion abbreviates synaptic vesicle fusion in this synaptic context. |
| `gene:SNAP25` (SNAP25) | SNAP25B | 25381298 | SNAP25B is the B protein isoform encoded by SNAP25. |
| `mech:ca-triggered-exocytosis` (Ca2+-triggered neurotransmitter exocytosis) | Ca(2+)-triggered exocytosis | 25381298 | The sentence explicitly describes calcium-triggered exocytosis at a presynaptic terminal. |
| `mech:ca-triggered-exocytosis` (Ca2+-triggered neurotransmitter exocytosis) | activity-dependent neurotransmitter release | 30929742 | Activity-dependent vesicular neurotransmitter release denotes calcium-triggered exocytosis in this context. |
| `phenotype:HP:0002187` (Profound intellectual disability) | profound cognitive impairment | 25705886 | Profound cognitive impairment is equivalent here to profound intellectual disability. |
| `phenotype:HP:0011170` (Generalized myoclonic-atonic seizure) | myoclonic-atonic seizures | 25865495 | Myoclonic-atonic seizures is an equivalent clinical term for generalized myoclonic-atonic seizures. |
| `mech:gain-of-function` (Gain of function (the protein does too much)) | gain of pathological function | 27597756 | Gain of pathological function is an alternative description of gain of function. |
| `phenotype:HP:0001263` (Global developmental delay) | developmental delay | 29538625, 31176687, 31855252, 32738165, 33332765, 33677401, 38242640, 38321119, 38781976, 40181518, 41125872, 41174879, 41385967, 42182245 | Developmental delay is an alternative clinical designation for the listed global developmental delay phenotype. |
| `phenotype:HP:0001263` (Global developmental delay) | developmental delays | 41893060 | Developmental delays is an equivalent clinical expression for global developmental delay in this context. |
| `phenotype:HP:0000729` (Autistic behavior) | autistic features | 29538625, 30929742 | Autistic features is an equivalent clinical expression for autistic behavior. |
| `phenotype:HP:0000729` (Autistic behavior) | autism | 32738165, 34028503, 36564538, 38781976 | Autism is an alternative term associated with this HPO autistic behavior phenotype. |
| `phenotype:HP:0000729` (Autistic behavior) | autistic tendencies | 32906212 | Autistic tendencies is an equivalent clinical expression for autistic behavior. |
| `phenotype:HP:0000729` (Autistic behavior) | autism spectrum disorder | 34006619, 40181518, 41174879 | Autism spectrum disorder corresponds to the autistic behavior phenotype term. |
| `phenotype:HP:0000729` (Autistic behavior) | autistic symptoms | 38321119 | Autistic symptoms is an equivalent clinical description of autistic behavior. |
| `mech:protein-destabilization` (Protein destabilization / misfolding) | impaired protein stability | 29538625 | Impaired protein stability directly denotes protein destabilization. |
| `mech:protein-destabilization` (Protein destabilization / misfolding) | folding-deficient | 36741049 | Folding deficiency is an equivalent description of protein misfolding. |
| `mech:protein-destabilization` (Protein destabilization / misfolding) | protein folding deficits | 36741049 | Protein folding deficits are an equivalent description of protein misfolding. |
| `phenotype:HP:0001250` (Seizure) | epileptic seizures | 30107533 | Epileptic seizures are equivalent to the seizure term, despite being negated here. |
| `phenotype:HP:0002353` (EEG abnormality) | EEG disturbance | 30107533 | EEG disturbance is an equivalent expression for EEG abnormality. |
| `phenotype:HP:0002353` (EEG abnormality) | electroencephalography abnormalities | 30929742 | Electroencephalography abnormalities is the expanded equivalent of EEG abnormality. |
| `phenotype:HP:0007359` (Focal-onset seizure) | focal epilepsy | 30737342, 33677401 | Focal epilepsy is an equivalent clinical description of the focal-onset seizure phenotype. |
| `phenotype:HP:0100704` (Cerebral visual impairment) | central visual impairment | 30929742 | Central visual impairment is an alternative term for cerebral visual impairment. |
| `phenotype:HP:0100704` (Cerebral visual impairment) | cortical visual impairment | 40767165 | Cortical visual impairment is an alternative name for cerebral visual impairment. |
| `phenotype:HP:0003473` (Fatigable weakness) | muscle fatigue | 32250532 | Muscle fatigue in this myasthenic context denotes fatigable weakness. |
| `mech:snare-complex-assembly` (SNARE complex assembly) | SNARE complex formation | 32572454 | SNARE complex formation is synonymous with SNARE complex assembly. |
| `mech:gaba-reuptake` (GABA reuptake) | γ-amino butyric acid uptake | 35911425 | γ-Amino butyric acid uptake by neurons and astrocytes is GABA reuptake. |
| `mech:gaba-reuptake` (GABA reuptake) | GABA uptake | 39923323 | GABA uptake by these transporters denotes the GABA reuptake process. |
| `phenotype:HP:0100660` (Dyskinesia) | dyskinetic movements | 41125872 | Dyskinetic movements is an equivalent clinical expression for dyskinesia. |
| `phenotype:HP:0100660` (Dyskinesia) | hyperkinetic movements | 41756855 | Hyperkinetic movements denotes abnormal involuntary movements, clinically described as dyskinesia. |

Not proposed despite a "same" judgement (hygiene rules in `reconcile.mjs`): "fever-associated epilepsy syndromes" → `disease:STX1B` (only a plural/spelling variant of an existing name); "Febrile seizures" → `phenotype:HP:0002373` (only a plural/spelling variant of an existing name); "exocytosis of synaptic vesicles from nerve terminals" → `mech:synaptic-vesicle-fusion` (long descriptive phrase); "re-uptake of GABA from the synapse" → `mech:gaba-reuptake` (long descriptive phrase); "3,4-diaminopyridine" → `therapy:3-4-diaminopyridine` (only a plural/spelling variant of an existing name); "destabilization" → `mech:protein-destabilization` (single generic word); "4-phenylbutyrate" → `therapy:4-phenylbutyrate` (only a plural/spelling variant of an existing name); "3,4 diaminopyridine" → `therapy:3-4-diaminopyridine` (only a plural/spelling variant of an existing name); "exocytosis of synaptic vesicles in the presynapse" → `mech:synaptic-vesicle-fusion` (long descriptive phrase); "Epilepsy" → `disease:STX1B` (generic disease name without the gene); "fusion" → `mech:synaptic-vesicle-fusion` (single generic word); "intellectual disabilities" → `phenotype:HP:0001249` (only a plural/spelling variant of an existing name); "Aminopyridine treatment" → `therapy:aminopyridine-presynaptic-boost` (descriptive phrase, not a name); "language disorder/speech delay" → `phenotype:HP:0000750` (descriptive phrase, not a name); "seizures" → `phenotype:HP:0001250` (only a plural/spelling variant of an existing name); "reuptake of GABA into presynaptic neurons and glia" → `mech:gaba-reuptake` (descriptive phrase, not a name); "CMS" → `disease:SYT2` (generic disease name without the gene); "simple febrile seizures" → `phenotype:HP:0011171` (only a plural/spelling variant of an existing name); "focal-onset seizures" → `phenotype:HP:0007359` (only a plural/spelling variant of an existing name); "neurodevelopmental disorder with or without epilepsy" → `disease:STX1A` (generic disease name without the gene); "Antisense oligonucleotides targeting the UNC13A cryptic exon" → `therapy:unc13a-splice-switching-aso` (long descriptive phrase); "neurodevelopmental disorder" → `disease:SYT1` (generic disease name without the gene); "Haploinsufficient" → `mech:haploinsufficiency` (single generic word); "seizures of different types" → `phenotype:HP:0001250` (descriptive phrase, not a name); "self-injurious behaviors" → `phenotype:HP:0100716` (only a plural/spelling variant of an existing name); "EEG abnormalities" → `phenotype:HP:0002353` (only a plural/spelling variant of an existing name); "4-phenylbutyrate (PBA)" → `therapy:4-phenylbutyrate` (descriptive phrase, not a name); "Baker-Gordon syndrome (BAGOS)" → `disease:SYT1` (descriptive phrase, not a name); "assembly of soluble NSF attachment protein receptors (SNAREs)" → `mech:snare-complex-assembly` (descriptive phrase, not a name); "rare neurodevelopmental disorder" → `disease:SYT1` (generic disease name without the gene).

## Reconciliation

804 distinct mentions (per abstract and type): 269 resolved by the deterministic index, 248 by the OpenAI step, 266 unresolved (no matching node, or the model answered "none"), 0 generic ("patients", "neurons"…) skipped, 13 gene symbols outside the slice. OpenAI picks outside the candidate list rejected: 0.

| Method | Mentions |
|---|---|
| openai:none | 204 |
| openai:instance | 149 |
| exact | 142 |
| openai:same | 99 |
| unresolved(no-llm-answer) | 62 |
| gene-rule | 46 |
| label-containment | 28 |
| variant-rule(gene-level) | 25 |
| variant-rule | 22 |
| not-in-graph | 13 |
| skipped(model-only phenotype) | 8 |
| exact+context | 3 |
| variant-rule(gene-level)+context | 3 |

**One entity, several nodes (for the curators).** These names are shared by two nodes of the same type in the curated graph, so claims about them cannot reconcile to one stable node. Merging or cross-linking them is a curation decision:

- "3,4-DAP" (therapy): `therapy:3-4-diaminopyridine`, `therapy:amifampridine`
- "amifampridine" (therapy): `therapy:3-4-diaminopyridine`, `therapy:amifampridine`
- "CAP-002" (therapy): `therapy:aav-stxbp1-gene-replacement`, `therapy:cap-002`

Claims dropped by the mapping rules (endpoints resolved but not comparable):

- multi-gene deletion: no mechanism edge by design: 1

Mapping rules (fixed, in `compare.mjs`): `causes` is lifted from a variant class to its gene; a gene or gene-level variant claim about an effect becomes `disease:<GENE> driven_by`; a variant-class effect is compared on `vg:… has_effect` and, as the curators do, also on the disease's `driven_by` edge; `has_phenotype` claims seen only in animal or cell models are not compared; "opposite effect class" means gain of function versus loss of function, haploinsufficiency, dominant-negative or destabilization of the same gene, and is flagged only where the graph lacks the claimed effect or the curators cite the same paper.

## Negative findings with no edge

Negated claims whose relation is not in the graph (nothing to contradict, kept for context):

- `disease:SYT1|has_phenotype|phenotype:HP:0001250` (PMID:30107533): "Absence of epileptic seizures and normal orbitofrontal head circumference are important negative features."
- `vg:SLC6A1:missense|has_effect|mech:dominant-negative` (PMID:38781976): "Surprisingly, recurrent de novo missense variants showed moderate loss-of-function effects that reduced GABA uptake with no evidence for dominant-negative or gain-of-function effects."
- `vg:SLC6A1:missense|has_effect|mech:gain-of-function` (PMID:38781976): "Surprisingly, recurrent de novo missense variants showed moderate loss-of-function effects that reduced GABA uptake with no evidence for dominant-negative or gain-of-function effects."
- `disease:SLC6A1|has_phenotype|phenotype:HP:0100704` (PMID:40767165): "A retrospective chart review of 85 patients found cortical visual impairment in 44%, most commonly in 8p (54%) and STXBP1 (50%); no cases were seen in SLC6A1."

## Usage consumed

| Step | Requests OK | Failed | Input tokens | Output tokens (reasoning) | Summed request time |
|---|---|---|---|---|---|
| extract | 78 | 0 | 111,580 | 74,403 (6,437) | 54.8 min |
| reconcile | 65 | 2 | 349,984 | 20,135 (1,156) | 17.5 min |
| **total** | **143** | **2** | **461,564** | **94,538** | **72.3 min** |

All requests used the ChatGPT-plan path (`authMode: "chatgpt"`); `OPENAI_API_KEY` was never used. Models seen: `gpt-6-astra`. Structured mode: json_schema. At most 2 requests were in flight.
**Stopped early:** reconcile: usage_limit (The ChatGPT plan or this app's usage limit was reached. Review usage and limits at https://chatgpt.com/settings/usage [subscription_sharing_usage_limit_exceeded]). Finished work is cached; rerun the same command to continue.
Failures: reconcile 42214744: usage_limit; reconcile 41438914: usage_limit.

## How to re-run

```bash
node integrations/openai/cli.mjs status          # signed in, plan usage ENABLED
node pipeline/openai/extract.mjs                 # biology abstracts (cached per PMID: reruns are free)
node pipeline/openai/extract.mjs --set community --limit 50   # more community abstracts, priority order
node pipeline/openai/reconcile.mjs               # deterministic index + one batched OpenAI call per abstract (cached)
node pipeline/openai/compare.mjs                 # no calls: crosscheck.json, openai_extracted.json, this report
python3 pipeline/build_graph.py                  # applies crosscheck.json and merges the fragment
```

`extract.mjs --verify-only` re-verifies every cached quote without calling the model. `reconcile.mjs --no-llm` runs the deterministic index only. Caches: `data/raw/openai/extractions/<PMID>.json` (model, generated_at, raw response, usage), `data/raw/openai/reconcile/<PMID>.json` (request payload, raw response, per-mention decisions). Every request is logged in `data/raw/openai/usage_log.jsonl`.

## Caveats

- Only title + abstract were sent. Investigators are not extracted by the model (no author list is sent); researcher nodes come from PubMed author metadata in the community layer.
- The model sees the abstract only; curators sometimes filed a PMID from a specific sentence with a narrower meaning. A disagreement is a prompt to look, not a verdict.
- Candidate edges and synonyms are proposals: `status: "unverified"`, `attrs.needs_review: true`, confidence ≤ 0.5.
- Run on a personal ChatGPT Plus plan (see risk 5 in `docs/openai-integration.md`): the batch was kept small and cached.

