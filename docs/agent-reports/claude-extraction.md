# Claude extraction: an independent second reading of the literature

Generated 2026-10-04 05:12 UTC by `pipeline/openai/` (READER=claude). Reader: **Claude** (`agent-reading`): a Claude agent read each stored title + abstract **blind to the curated graph**, with the same extraction instructions and JSON schema the OpenAI reader used (`EXTRACT_INSTRUCTIONS`, `CLAIM_SCHEMA` in `extract.mjs`; hash in each cache file). Mentions the deterministic index could not resolve were answered by a Claude agent with the same reconciliation instructions and candidate lists (`reconcile.mjs --dump-pending / --apply-answers`). No API calls are made by these scripts. Verification, reconciliation rules and comparison are the same code as for OpenAI. Nothing here was typed by hand: every number below is recomputed by `READER=claude node pipeline/openai/compare.mjs`.

The curated graph was built by agent curation with string-verified quotes. This layer reads the same stored abstracts **independently** with Claude, keeps only claims whose quote is a verbatim sentence of the stored abstract, maps them onto graph nodes, and compares. The evidence story becomes: **two independent extractors, verbatim quotes, disagreements flagged for human review.**

## Headline numbers

| | |
|---|---|
| Abstracts processed | **256** (dee 47/244; lysosomal 98/960; rasopathy 84/667; cross 27/146 with abstracts) |
| Claims extracted | 1499 |
| Quote-verified (verbatim substring of stored title + abstract) | **1499 (100%)**; 0 rejected, none edited (1 verified quotes span more than one sentence) |
| Reconciled (both endpoints mapped to an existing node) | 780 (52.0% of verified) |
| Compared with graph edges (after the fixed mapping rules) | 765 |
| **Agreement** on (edge, PMID) pairs both extractors cite | **172/179 (96.1%)** |
| Curated (edge, PMID) pairs for these abstracts re-found independently | 179/484 (37.0%) |
| (a) disagreements on a paper both cite | 7 |
| (b) new supporting sources for existing edges | 274 |
| (d) new contradicting sources, flagged for review | 0 |
| (c) candidate new edges (`status: unverified`, confidence ≤ 0.5) | 169 |
| Synonyms proposed | 56 on 46 nodes |

## Agreement by relation type

A pair is one graph edge and one PMID. "Agree" means the Claude claim has the same polarity as the curators' filing of that PMID on that edge (supporting evidence vs. counter-evidence). Coverage is how many curated pairs for the processed abstracts the model found on its own.

| Edge type | Pairs both cite | Agree | Disagree | Agreement | Curated pairs re-found | New supporting (b) | New contradicting (d) |
|---|---|---|---|---|---|---|---|
| `causes` | 21 | 21 | 0 | 100.0% | 21/31 | 103 | 0 |
| `developed_for` | 54 | 49 | 5 | 90.7% | 54/75 | 36 | 0 |
| `driven_by` | 69 | 68 | 1 | 98.6% | 69/96 | 69 | 0 |
| `has_effect` | 7 | 6 | 1 | 85.7% | 7/83 | 3 | 0 |
| `has_phenotype` | 11 | 11 | 0 | 100.0% | 11/122 | 39 | 0 |
| `participates_in` | 14 | 14 | 0 | 100.0% | 14/47 | 20 | 0 |
| `targets` | 3 | 3 | 0 | 100.0% | 3/30 | 4 | 0 |
| **all** | **179** | **172** | **7** | **96.1%** | **179/484** | **274** | **0** |

Note: `has_phenotype` pairs come from HPO annotations that cite a PMID (no curator quote); the model reads only the abstract, so phenotypes reported in full texts are not expected to be re-found.

## Disagreements for a biochemist to review

7 items, most important first (a paper both extractors cite but read differently ranks highest; then direct contradictions on high-confidence mechanism and therapy edges). "Curated" is the quote the curators filed for that PMID on the edge, or, when the curators did not cite this PMID, their main supporting quote. In the graph these appear as `cross_checked.agrees: false` stamps (a) or as counter-evidence with `needs_review: true` (d); they do not change an edge's status until a person reviews them.

### 1. `therapy:quinidine|developed_for|disease:KCNT1`

Both cite PMID:29196578. Curators filed it as **contradicting**; the Claude reading takes it as **supporting** the edge. Edge: contested, confidence 0.65, experimental. Claim: quinidine → *developed_for* → autosomal dominant nocturnal frontal lobe epilepsy (ADNFLE) (established, clinical_trial, human).

- Curated (PMID:29196578, contradicts): "CONCLUSION: Quinidine did not show efficacy in adults and teenagers with ADNFLE."
- Curated (PMID:29196578, contradicts): "Dose-limiting cardiac side effects were observed even in the presence of low measured serum quinidine levels."
- Claude (PMID:29196578): "METHODS: A single-center, inpatient, order-randomized, blinded, placebo-controlled, crossover trial of oral quinidine included 6 patients with severe autosomal dominant nocturnal frontal lobe epilepsy (ADNFLE) due to KCNT1 mutation."

### 2. `therapy:sodium-channel-blockers|developed_for|disease:SCN1A`

Both cite PMID:36314457. Curators filed it as **contradicting**; the Claude reading takes it as **supporting** the edge. Edge: contested, confidence 0.65, experimental. Claim: phenytoin → *developed_for* → Dravet syndrome (established, case_series, human).

- Curated (PMID:36314457, contradicts): "Anti-seizure medications that block sodium channels are generally considered contraindicated in Dravet syndrome."
- Claude (PMID:36314457): "We describe four patients with Dravet syndrome in whom long-term phenytoin therapy reduced seizure frequency and duration."

### 3. `therapy:statins-nf1-cognition|developed_for|disease:NF1`

Both cite PMID:18632543. Curators filed it as **contradicting**; the Claude reading takes it as **supporting** the edge. Edge: contested, confidence 0.4, clinical. Claim: Simvastatin → *developed_for* → neurofibromatosis type 1 (established, clinical_trial, human).

- Curated (PMID:18632543, contradicts): "CONCLUSION: In this 12-week trial, simvastatin did not improve cognitive function in children with NF1."
- Claude (PMID:18632543): "Effect of simvastatin on cognitive functioning in children with neurofibromatosis type 1: a randomized controlled trial."

### 4. `therapy:statins-nf1-cognition|developed_for|disease:NF1`

Both cite PMID:27956565. Curators filed it as **contradicting**; the Claude reading takes it as **supporting** the edge. Edge: contested, confidence 0.4, clinical. Claim: lovastatin → *developed_for* → neurofibromatosis type 1 (established, clinical_trial, human).

- Curated (PMID:27956565, contradicts): "CONCLUSIONS: Lovastatin administered once daily for 16 weeks did not improve visuospatial learning or attention in children with NF1 and is not recommended for amelioration of cognitive deficits in this population."
- Claude (PMID:27956565): "Randomized placebo-controlled study of lovastatin in children with neurofibromatosis type 1."

### 5. `therapy:tipifarnib|developed_for|disease:NF1`

Both cite PMID:24500418. Curators filed it as **contradicting**; the Claude reading takes it as **supporting** the edge. Edge: contested, confidence 0.4, clinical. Claim: tipifarnib → *developed_for* → neurofibromatosis type 1 (established, clinical_trial, human).

- Curated (PMID:24500418, contradicts): "CONCLUSIONS: Tipifarnib was well tolerated but did not significantly prolong TTP of PNs compared with placebo."
- Claude (PMID:24500418): "Phase 2 randomized, flexible crossover, double-blinded, placebo-controlled trial of the farnesyltransferase inhibitor tipifarnib in children and young adults with neurofibromatosis type 1 and progressive plexiform neurofibromas."

### 6. `vg:PTPN11:missense|has_effect|mech:gain-of-function`

Both cite PMID:16358218. Curators filed it as **supporting**; the Claude reading reports the **opposite effect class** for this gene. Edge: supported, confidence 0.8, experimental. Claim: PTPN11 Y279C and T468M → *has_effect* → loss of SHP-2 catalytic activity (established, functional_study, in_vitro).

- Curated (PMID:16358218, supports): "Our results document a strict correlation between the identity of the lesion and disease and demonstrate that NS-causative mutations have less potency for promoting SHP-2 gain of function than do leukemia-associated ones."
- Claude (PMID:16358218, opposite effect): "Furthermore, we show that the recurrent LS-causing Y279C and T468M amino acid substitutions engender loss of SHP-2 catalytic activity, identifying a previously unrecognized behavior for this class of missense PTPN11 mutations."

### 7. `disease:PTPN11|driven_by|mech:dominant-negative`

Both cite PMID:16358218. Curators filed it as **supporting**; the Claude reading reports the **opposite effect class** for this gene. Edge: contested, confidence 0.7, experimental. Claim: NS-causative PTPN11 mutations → *has_effect* → SHP-2 gain of function (established, functional_study, in_vitro).

- Curated (PMID:16358218, supports): "Furthermore, we show that the recurrent LS-causing Y279C and T468M amino acid substitutions engender loss of SHP-2 catalytic activity, identifying a previously unrecognized behavior for this class of missense PTPN11 mutations."
- Claude (PMID:16358218, opposite effect): "Our results document a strict correlation between the identity of the lesion and disease and demonstrate that NS-causative mutations have less potency for promoting SHP-2 gain of function than do leukemia-associated ones."

## New supporting sources for existing edges (b)

274 (edge, PMID) pairs where the model found support for an existing edge in a paper the curators did not cite on that edge. `build_graph.py` adds them as evidence with `extracted_by: claude:agent-reading`, `verified: true`.

| Edge type | New supporting sources |
|---|---|
| `causes` | 103 |
| `developed_for` | 36 |
| `driven_by` | 69 |
| `has_effect` | 3 |
| `has_phenotype` | 39 |
| `participates_in` | 20 |
| `targets` | 4 |

- `disease:ARSA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:36811406 (established, review): "Metachromatic leukodystrophy (MLD) is a rare autosomal recessive disorder of sphingolipid metabolism, due to a deficiency of the enzyme arylsulfatase A (ARSA)."
- `disease:CACNA1A|driven_by|mech:loss-of-function` ← PMID:18293354 (suggested, review): "EA2 symptoms are thought to result from disturbed neurotransmission at cerebellar and neuromuscular synapses, caused by loss-of-function of Ca(v)2.1 channels."
- `disease:CDKL5|driven_by|mech:loss-of-function` ← PMID:37917202 (established, review): "Loss-of-function mutations in CDKL5 are associated with a severe neurodevelopmental encephalopathy."
- `disease:CLN3|driven_by|mech:lysosomal-storage` ← PMID:42282513 (established, animal_model): "A pathological hallmark is the accumulation of storage material within neuronal lysosomes resulting from mutations in the CLN3 gene."
- `disease:GAA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:18929906 (established, review): "It is a pan-ethnic autosomal recessive trait characterised by acid alpha-glucosidase deficiency leading to lysosomal glycogen storage."
- `disease:GAA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:25036864 (established, animal_model): "Pompe disease is an inherited lysosomal storage disorder that results from a deficiency in acid α-glucosidase (GAA) activity due to mutations in the GAA gene."
- `disease:GAA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:42131243 (established, review): "Pompe disease is a muscular lysosomal storage disorder characterized by autosomal recessive inheritance and caused by deficiency of the acid alpha-glucosidase (GAA) enzyme."
- `disease:GAA|driven_by|mech:lysosomal-storage` ← PMID:25036864 (established, animal_model): "Pompe disease is characterized by accumulation of lysosomal glycogen primarily in heart and skeletal muscles, which leads to progressive muscle weakness."
- `disease:GAA|driven_by|mech:lysosomal-storage` ← PMID:28130275 (established, review): "In this study, we have examined the involvement of the mTOR pathway in the pathophysiology of a severe muscle wasting condition, Pompe disease, caused by excessive accumulation of lysosomal glycogen."
- `disease:GALC|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:41501923 (established, cohort): "BACKGROUND: Krabbe disease (KD) is a rapidly progressive neurodegenerative disorder caused by β-galactocerebrosidase deficiency."
- `disease:GALC|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:41604001 (established, case_series): "Globoid cell leukodystrophy (GLD) is a progressive neurodegenerative disease caused by galactocerebrosidase deficiency."
- `disease:GBA1|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:17644022 (established, review): "The common mutations found in the lysosomal enzyme deficient in Gaucher disease, beta-glucocerebrosidase, earmark these proteins for destruction by the endoplasmic reticulum-localised protein folding machinery, resulting in enzyme insufficiency, lysosomal glycolipid storage and subsequent pathology."
- `disease:GBA1|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:23622393 (established, review): "Gaucher disease is an autosomal recessive condition due to glucocerebrosidase deficiency responsible for the lysosomal accumulation of glucosylceramide, a complex lipid derived from cell membranes, mainly in macrophages."
- `disease:GBA1|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:27449603 (established, review): "In Gaucher disease (GD), mutant lysosomal acid β-glucocerebrosidase fails to properly hydrolyze its substrate, glucosylceramide, which accumulates in the lysosomes."
- `disease:GBA1|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:39116528 (established, review): "Gaucher disease (GD), an autosomal recessive lysosomal storage disease, results from GBA1 variants causing glucocerebrosidase (GCase) deficiency."
- `disease:GBA1|driven_by|mech:lysosomal-storage` ← PMID:17644022 (established, review): "The common mutations found in the lysosomal enzyme deficient in Gaucher disease, beta-glucocerebrosidase, earmark these proteins for destruction by the endoplasmic reticulum-localised protein folding machinery, resulting in enzyme insufficiency, lysosomal glycolipid storage and subsequent pathology."
- `disease:GBA1|driven_by|mech:lysosomal-storage` ← PMID:27449603 (established, review): "In Gaucher disease (GD), mutant lysosomal acid β-glucocerebrosidase fails to properly hydrolyze its substrate, glucosylceramide, which accumulates in the lysosomes."
- `disease:GBA1|driven_by|mech:lysosomal-storage` ← PMID:38797393 (established, review): "Deficiency in GCase activity (in patients with two defective alleles of GBA1) leads to glucosylceramide storage in lysosomes which in turn results in the development of the Gaucher diseases, a lysosomal storage disorder, while a heterozygous state may be correlated with the GBA1 mutation-associated Parkinson disease."
- `disease:GLA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:27834756 (established, clinical_trial): "Fabry disease is an X-linked lysosomal storage disorder caused by GLA mutations, resulting in α-galactosidase (α-Gal) deficiency and accumulation of lysosomal substrates."
- `disease:GLA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:30875019 (established, review): "Fabry disease is a rare lysosomal disorder characterized by deficient or absent α-galactosidase A activity resulting from mutations in the GLA gene."
- `disease:HEXA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:35145305 (established, case_series): "Tay-Sachs disease (TSD) is an inherited neurological disorder caused by deficiency of hexosaminidase A (HexA)."
- `disease:HEXA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:40430919 (established, review): "Tay-Sachs disease (TSD) is a neurodegenerative disorder caused by a deficiency in β-hexosaminidase A (HexA), which accumulates GM2 gangliosides, primarily in neurons."
- `disease:HEXA|driven_by|mech:lysosomal-enzyme-deficiency` ← PMID:42511849 (established, functional_study): "Tay-Sachs disease is a rare genetic disorder characterized by the accumulation of GM2 ganglioside in neuronal lysosomes due to deficient β-hexosaminidase A (HexA) activity."
- `disease:HEXA|driven_by|mech:lysosomal-storage` ← PMID:41819452 (established, animal_model): "HexA deficiency leads to impaired degradation and accumulation of GM2 ganglioside, causing progressive neurodegeneration in patients."
- `disease:HEXA|driven_by|mech:lysosomal-storage` ← PMID:41947150 (established, animal_model): "Tay-Sachs disease (TSD) is a fatal lysosomal storage disorder caused by mutations in the HEXA gene which impair B-hexosaminidase A activity and result in the toxic accumulation of GM2 gangliosides."
- …249 more in `data/build/crosscheck_claude.json` (`case: "b"`).

## Candidate new edges (c)

169 edges whose endpoints both exist but which the graph lacks. Written to `data/build/claude_candidate_edges.json` for review and **not merged into the graph** until a person accepts them, each with `status: "unverified"`, confidence ≤ 0.5, evidence level from the study type (trial → clinical; functional/animal → experimental; case report/series/cohort/review → observational) and a verbatim, string-verified quote per PMID.

| Candidate edge | PMIDs | Level | Confidence | Certainty |
|---|---|---|---|---|
| `disease:ARSA|has_phenotype|phenotype:HP:0002333` | 40577679 | observational | 0.5 | established |
| `disease:BRAF|driven_by|mech:ras-protein-signal-transduction` | 18456719 | observational | 0.5 | established |
| `disease:CACNA1A|driven_by|mech:voltage-gated-calcium-channel-activity` | 20631222 | experimental | 0.45 | suggested |
| `disease:CACNA1A|has_phenotype|phenotype:HP:0001250` | 20631222 | observational | 0.5 | established |
| `disease:CACNA1A|has_phenotype|phenotype:HP:0001251` | 20631222 | observational | 0.5 | established |
| `disease:CACNA1A|has_phenotype|phenotype:HP:0002181` | 20631222 | observational | 0.5 | established |
| `disease:CBL|driven_by|mech:ras-protein-signal-transduction` | 20619386 | experimental | 0.5 | established |
| `disease:CBL|has_phenotype|phenotype:HP:0001263` | 20694012 | observational | 0.5 | established |
| `disease:CBL|has_phenotype|phenotype:HP:0001510` | 20694012 | observational | 0.5 | established |
| `disease:CDKL5|driven_by|mech:autophagy` | 42779792 | experimental | 0.5 | established |
| `disease:CDKL5|has_phenotype|phenotype:HP:0000717` | 30288694 | observational | 0.5 | established |
| `disease:CDKL5|has_phenotype|phenotype:HP:0001250` | 35429480, 35997111 | observational | 0.5 | established |
| `disease:CDKL5|has_phenotype|phenotype:HP:0001263` | 30288694 | observational | 0.5 | established |
| `disease:CDKL5|has_phenotype|phenotype:HP:0011344` | 35429480 | observational | 0.5 | established |
| `disease:CLN3|has_phenotype|phenotype:HP:0002180` | 40924969 | observational | 0.5 | established |
| `disease:GAA|driven_by|mech:tor-signaling` | 28130275 | experimental | 0.5 | established |
| `disease:GAA|has_phenotype|phenotype:HP:0001639` | 18929906 | observational | 0.5 | established |
| `disease:GALC|has_phenotype|phenotype:HP:0002069` | 41278553 | observational | 0.5 | established |
| `disease:GBA1|driven_by|mech:autophagy` | 31519738 | observational | 0.5 | established |
| `disease:GBA1|driven_by|mech:tor-signaling` | 31519738 | experimental | 0.5 | established |
| `disease:GBA1|has_phenotype|phenotype:HP:0001744` | 23622393, 28218669 | observational | 0.5 | established |
| `disease:GBA1|has_phenotype|phenotype:HP:0002180` | 23622393, 31519738 | observational | 0.5 | established |
| `disease:GBA1|has_phenotype|phenotype:HP:0002240` | 28218669 | observational | 0.5 | established |
| `disease:GLA|has_phenotype|phenotype:HP:0000093` | 21092187 | observational | 0.5 | established |
| `disease:GRIN2B|driven_by|mech:nmda-receptor-activity` | 31213567 | experimental | 0.5 | established |
| `disease:GRIN2B|has_phenotype|phenotype:HP:0000717` | 28377535 | observational | 0.5 | established |
| `disease:GRIN2B|has_phenotype|phenotype:HP:0001249` | 28377535 | observational | 0.5 | established |
| `disease:GRIN2B|has_phenotype|phenotype:HP:0001252` | 28377535 | observational | 0.5 | established |
| `disease:GRIN2B|has_phenotype|phenotype:HP:0002059` | 28377535 | observational | 0.5 | established |
| `disease:GRIN2B|has_phenotype|phenotype:HP:0100704` | 28377535 | observational | 0.5 | established |
| `disease:HEXA|driven_by|mech:autophagy` | 41460292 | experimental | 0.5 | established |
| `disease:HEXA|driven_by|mech:loss-of-function` | 39759878 | experimental | 0.5 | established |
| `disease:HEXA|has_phenotype|phenotype:HP:0001251` | 30524313, 42511849 | experimental | 0.5 | established |
| `disease:HEXA|has_phenotype|phenotype:HP:0001263` | 42511849 | experimental | 0.5 | established |
| `disease:HEXA|has_phenotype|phenotype:HP:0001272` | 40266357 | observational | 0.5 | established |
| `disease:HEXA|has_phenotype|phenotype:HP:0002180` | 41819452 | experimental | 0.5 | established |
| `disease:HRAS|driven_by|mech:autophagy` | 34508588 | experimental | 0.5 | established |
| `disease:HRAS|driven_by|mech:glucose-transmembrane-transport` | 34508588 | experimental | 0.5 | established |
| `disease:HRAS|driven_by|mech:ras-protein-signal-transduction` | 20694012, 34612139, 35764878, 42026675 | experimental | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0000280` | 16170316 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0000486` | 34612139 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0000508` | 34612139 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0000639` | 34612139 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0001263` | 35764878 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0001510` | 34508588 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0006536` | 35764878 | observational | 0.5 | established |
| `disease:HRAS|has_phenotype|phenotype:HP:0011968` | 35764878 | observational | 0.5 | established |
| `disease:IDUA|has_phenotype|phenotype:HP:0000280` | 32188113 | observational | 0.5 | established |
| `disease:IDUA|has_phenotype|phenotype:HP:0002104` | 17011223 | observational | 0.5 | established |
| `disease:KCNQ2|driven_by|mech:protein-destabilization` | 34020651 | observational | 0.45 | suggested |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0001249` | 24318194 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0001250` | 24318194 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0001263` | 25880994, 27602407 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0001336` | 28139826 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0002133` | 25880994 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0006808` | 28139826 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0010841` | 25880994, 28139826 | observational | 0.5 | established |
| `disease:KCNQ2|has_phenotype|phenotype:HP:0011203` | 28139826 | observational | 0.5 | established |
| `disease:KCNT1|has_phenotype|phenotype:HP:0001250` | 41981306 | observational | 0.5 | established |
| `disease:KRAS|driven_by|mech:ras-protein-signal-transduction` | 16474405 | experimental | 0.45 | suggested |
| `disease:KRAS|has_phenotype|phenotype:HP:0004322` | 16474405 | observational | 0.5 | established |
| `disease:LZTR1|driven_by|mech:dominant-negative` | 39352760 | experimental | 0.5 | established |
| `disease:LZTR1|driven_by|mech:haploinsufficiency` | 30442762 | experimental | 0.5 | established |
| `disease:LZTR1|driven_by|mech:mapk-cascade` | 30481304 | experimental | 0.5 | established |
| `disease:LZTR1|driven_by|mech:ras-protein-signal-transduction` | 38333672 | observational | 0.5 | established |
| `disease:LZTR1|has_phenotype|phenotype:HP:0001249` | 30368668 | observational | 0.5 | established |
| `disease:LZTR1|has_phenotype|phenotype:HP:0001631` | 30368668 | observational | 0.5 | established |
| `disease:LZTR1|has_phenotype|phenotype:HP:0001639` | 30368668, 32623905, 38333672, 39003740 | observational | 0.5 | established |
| `disease:LZTR1|has_phenotype|phenotype:HP:0004322` | 30368668 | observational | 0.5 | established |
| `disease:LZTR1|has_phenotype|phenotype:HP:0009588` | 29909380 | observational | 0.5 | established |
| `disease:NF1|driven_by|mech:ras-protein-signal-transduction` | 15937108, 20694012, 24500418 | observational | 0.5 | established |
| `disease:NF1|driven_by|mech:tor-signaling` | 15937108 | experimental | 0.5 | established |
| `disease:NF1|has_phenotype|phenotype:HP:0001263` | 34346503 | observational | 0.5 | established |
| `disease:NF1|has_phenotype|phenotype:HP:0007018` | 16271875 | observational | 0.5 | established |
| `disease:NPC1|driven_by|mech:intracellular-cholesterol-transport` | 20525256 | observational | 0.5 | established |
| `disease:NPC1|driven_by|mech:tor-signaling` | 31548609 | experimental | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0000365` | 41895381 | experimental | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0000623` | 20525256 | observational | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0001250` | 20525256 | observational | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0001251` | 20525256 | observational | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0001433` | 20525256 | observational | 0.5 | established |
| `disease:NPC1|has_phenotype|phenotype:HP:0002344` | 24338084 | observational | 0.5 | established |
| `disease:PTPN11|driven_by|mech:tor-signaling` | 22058153, 31722741 | experimental | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0000316` | 16377799, 32164556 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0000767` | 32164556 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0001003` | 16377799 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0001510` | 16377799 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0001639` | 11704759, 22058153 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0001642` | 11704759, 16377799, 22058153 | observational | 0.5 | established |
| `disease:PTPN11|has_phenotype|phenotype:HP:0004322` | 11704759, 32164556 | observational | 0.5 | established |
| `disease:RAF1|driven_by|mech:positive-regulation-of-ras-signaling` | 17603483 | observational | 0.5 | established |
| `disease:RAF1|driven_by|mech:protein-serine-threonine-kinase-activity` | 17603483, 21339642 | experimental | 0.5 | established |
| `disease:RIT1|driven_by|mech:ras-protein-signal-transduction` | 25959749, 41388936 | experimental | 0.5 | established |
| `disease:RIT1|has_phenotype|phenotype:HP:0000476` | 25959749 | observational | 0.45 | suggested |
| `disease:RIT1|has_phenotype|phenotype:HP:0001004` | 25959749 | observational | 0.5 | established |
| `disease:SCN1A|driven_by|mech:protein-destabilization` | 25576396 | experimental | 0.5 | established |
| `disease:SCN1A|driven_by|mech:voltage-gated-sodium-channel-activity` | 16921370 | experimental | 0.45 | suggested |
| `disease:SCN1A|has_phenotype|phenotype:HP:0001250` | 11359211, 28538134, 31862249 | clinical | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0002069` | 11359211 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0002104` | 35696452 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0002121` | 11359211 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0002133` | 36314457 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0007281` | 11359211 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0007359` | 36636894 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0020221` | 11359211 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0032792` | 35696452 | observational | 0.5 | established |
| `disease:SCN1A|has_phenotype|phenotype:HP:0032794` | 11359211, 9596203 | observational | 0.5 | established |
| `disease:SCN2A|has_phenotype|phenotype:HP:0001250` | 38148154 | observational | 0.5 | established |
| `disease:SCN2A|has_phenotype|phenotype:HP:0012469` | 38148154 | observational | 0.5 | established |
| `disease:SCN8A|driven_by|mech:voltage-gated-sodium-channel-activity` | 29726066 | experimental | 0.5 | established |
| `disease:SCN8A|has_phenotype|phenotype:HP:0001250` | 31943325 | observational | 0.5 | established |
| `disease:SCN8A|has_phenotype|phenotype:HP:0001263` | 31943325 | observational | 0.5 | established |
| `disease:SCN8A|has_phenotype|phenotype:HP:0002121` | 34431999 | observational | 0.5 | established |
| `disease:SCN8A|has_phenotype|phenotype:HP:0010864` | 34431999 | observational | 0.5 | established |
| `disease:SCN8A|has_phenotype|phenotype:HP:0011198` | 34431999 | observational | 0.5 | established |
| `disease:SHOC2|driven_by|mech:mapk-cascade` | 19684605 | experimental | 0.5 | established |
| `disease:SLC2A1|has_phenotype|phenotype:HP:0000252` | 9462754 | observational | 0.5 | established |
| `disease:SMPD1|driven_by|mech:loss-of-function` | 42587127 | experimental | 0.5 | established |
| `disease:SMPD1|driven_by|mech:regulation-of-synaptic-plasticity` | 40609755 | experimental | 0.5 | established |
| `disease:SMPD1|has_phenotype|phenotype:HP:0001510` | 40236726 | observational | 0.5 | established |
| `disease:SMPD1|has_phenotype|phenotype:HP:0002180` | 40236726, 42587127 | experimental | 0.5 | established |
| `disease:SOS1|driven_by|mech:mapk-cascade` | 17143282 | observational | 0.5 | established |
| `disease:SOS1|driven_by|mech:ras-protein-signal-transduction` | 17143282 | experimental | 0.5 | established |
| `disease:SOS1|has_phenotype|phenotype:HP:0010310` | 33219052 | observational | 0.5 | established |
| `disease:SYNGAP1|has_phenotype|phenotype:HP:0000717` | 23161826 | observational | 0.5 | established |
| `disease:SYNGAP1|has_phenotype|phenotype:HP:0001251` | 23161826 | observational | 0.5 | established |
| `disease:SYNGAP1|has_phenotype|phenotype:HP:0002197` | 23161826 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0000546` | 35772852 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0000618` | 27491216, 35772852 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0000726` | 27491216, 29688815 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0001250` | 42175674 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0002059` | 42175674 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0002333` | 27491216 | observational | 0.5 | established |
| `disease:TPP1|has_phenotype|phenotype:HP:0002361` | 42175674 | observational | 0.5 | established |
| `gene:KCNT1|participates_in|mech:action-potential` | 41981306 | observational | 0.5 | established |
| `gene:LZTR1|participates_in|mech:autophagy` | 31337872 | experimental | 0.35 | speculative |
| `gene:NF1|participates_in|mech:negative-regulation-of-ras-signaling` | 15937108, 16271875, 34346503, 35066574, 35188187 | observational | 0.5 | established |
| `gene:PTPN11|participates_in|mech:positive-regulation-of-ras-signaling` | 16474405, 34346503 | observational | 0.5 | established |
| `gene:PTPN11|participates_in|mech:tor-signaling` | 22058153 | observational | 0.5 | established |
| `gene:SOS1|participates_in|mech:positive-regulation-of-ras-signaling` | 17143282, 17143285, 17586837 | observational | 0.5 | established |
| `gene:SYNGAP1|participates_in|mech:ras-protein-signal-transduction` | 12427827, 29940508 | experimental | 0.5 | established |
| `therapy:ambroxol|targets|mech:autophagy` | 38797393 | observational | 0.5 | established |
| `therapy:hsct-krabbe|developed_for|disease:ARSA` | 42764516 | observational | 0.5 | established |
| `therapy:kv7-openers|targets|mech:loss-of-function` | 27602407 | observational | 0.35 | speculative |
| `therapy:migalastat|targets|mech:lysosomal-storage` | 30875019 | observational | 0.5 | established |
| `therapy:miglustat|developed_for|disease:HEXA` | 30524313 | observational | 0.5 | established |
| `therapy:mirdametinib|developed_for|disease:RIT1` | 41388936 | experimental | 0.5 | established |
| `therapy:olipudase-alfa|targets|mech:sphingolipid-catabolism` | 39669638 | observational | 0.5 | established |
| `therapy:sodium-channel-blockers|targets|mech:action-potential` | 38148154 | experimental | 0.5 | established |
| `therapy:sodium-channel-blockers|targets|mech:gain-of-function` | 34431999, 36636894 | observational | 0.5 | established |
| `therapy:sodium-channel-blockers|targets|mech:protein-destabilization` | 25576396 | experimental | 0.5 | established |
| `therapy:statins-nf1-cognition|developed_for|disease:PTPN11` | 25383899 | experimental | 0.5 | established |
| `therapy:statins-nf1-cognition|targets|mech:mapk-cascade` | 16271875 | experimental | 0.5 | established |
| `therapy:statins-nf1-cognition|targets|mech:regulation-of-synaptic-plasticity` | 16271875 | experimental | 0.5 | established |
| `therapy:zorevunersen|targets|mech:voltage-gated-sodium-channel-activity` | 41780062 | clinical | 0.5 | established |
| `vg:CACNA1A:missense|has_effect|mech:gain-of-function` | 31468518 | experimental | 0.5 | established |
| `vg:CACNA1A:missense|has_effect|mech:loss-of-function` | 31468518 | experimental | 0.5 | established |
| `vg:KCNQ2:missense|has_effect|mech:gain-of-function` | 25740509, 28139826 | experimental | 0.5 | established |
| `vg:KCNQ2:missense|has_effect|mech:loss-of-function` | 24318194, 34020651 | experimental | 0.5 | established |
| `vg:KCNQ2:missense|has_effect|mech:protein-destabilization` | 34020651 | experimental | 0.45 | suggested |
| `vg:LZTR1:missense|has_effect|mech:protein-destabilization` | 39140257 | experimental | 0.5 | established |
| `vg:PTPN11:missense|has_effect|mech:loss-of-function` | 16358218, 22058153 | experimental | 0.5 | established |
| `vg:SCN1A:missense|has_effect|mech:loss-of-function` | 19402159, 25576396 | experimental | 0.5 | established |
| `vg:SCN2A:missense|has_effect|mech:gain-of-function` | 28256214, 38148154 | experimental | 0.5 | established |
| `vg:SCN2A:missense|has_effect|mech:loss-of-function` | 38148154, 41642117 | experimental | 0.5 | established |
| `vg:SCN8A:missense|has_effect|mech:gain-of-function` | 30615093 | experimental | 0.5 | established |
| `vg:SCN8A:missense|has_effect|mech:loss-of-function` | 30615093 | experimental | 0.5 | established |
| `vg:SLC2A1:truncating|has_effect|mech:loss-of-function` | 9462754 | observational | 0.5 | established |
| `vg:SYNGAP1:truncating|has_effect|mech:loss-of-function` | 23161826 | experimental | 0.35 | speculative |

## Synonyms added

56 names on 46 nodes. A synonym is proposed only when the Claude reconciliation step judged the mention to be **another name for exactly that node** ("same", not a narrower or descriptive mention), the id came from the mention's candidate list, and the mention appears literally in the abstract. They are node stubs (id, type, label, synonyms) that the merge step unions.

| Node | Synonym | PMID(s) | Model's justification |
|---|---|---|---|
| `phenotype:HP:0002069` (Bilateral tonic-clonic seizure) | tonic-clonic seizures | 11359211 | generalized tonic-clonic = bilateral tonic-clonic seizure |
| `phenotype:HP:0002069` (Bilateral tonic-clonic seizure) | Generalized tonic-clonic seizures | 41278553 | generalized tonic-clonic = bilateral tonic-clonic seizure |
| `phenotype:HP:0001263` (Global developmental delay) | developmental delay | 23086397, 31943325, 42511849, 16439621, 20694012, 34346503, 35764878 | Developmental delay |
| `phenotype:HP:0001263` (Global developmental delay) | delayed development | 9462754 | Delayed development |
| `phenotype:HP:0001263` (Global developmental delay) | developmental retardation | 30288694 | developmental retardation = developmental delay |
| `phenotype:HP:0010841` (Multifocal epileptiform discharges) | multifocal epileptiform abnormalities | 25880994 | Multifocal epileptiform abnormalities = discharges |
| `phenotype:HP:0010851` (EEG with burst suppression) | burst-suppression pattern | 25880994 | Burst-suppression EEG |
| `phenotype:HP:0010851` (EEG with burst suppression) | burst suppression | 27602407 | EEG burst suppression |
| `therapy:sodium-channel-blockers` (Sodium channel blocking anti-seizure medicines (class)) | drugs acting on sodium channels | 25880994 | Sodium channel-acting drugs (CBZ, PHT) class |
| `therapy:sodium-channel-blockers` (Sodium channel blocking anti-seizure medicines (class)) | sodium-channel blockers | 25880994, 28379373, 34431999, 36636894 | Sodium-channel blockers class |
| `therapy:sodium-channel-blockers` (Sodium channel blocking anti-seizure medicines (class)) | sodium channel blocker | 42610455 | sodium channel blocker class |
| `therapy:kv7-openers` (Kv7 potassium channel openers (ezogabine / retigabine, XEN496)) | EZO | 27602407 | EZO = ezogabine |
| `phenotype:HP:0006808` (Cerebral hypomyelination) | hypomyelination | 28139826 | Cerebral hypomyelination |
| `phenotype:HP:0012736` (Profound global developmental delay) | profound developmental delay | 28139826 | Profound global developmental delay |
| `phenotype:HP:0100704` (Cerebral visual impairment) | cortical visual impairment | 28377535 | Cortical/cerebral visual impairment |
| `phenotype:HP:0002059` (Cerebral atrophy) | cerebral volume loss | 28377535 | Cerebral volume loss = cerebral atrophy |
| `phenotype:HP:0011198` (EEG with generalized epileptiform discharges) | generalized epileptiform discharges | 34431999 | Generalized epileptiform discharges |
| `phenotype:HP:0011344` (Severe global developmental delay) | severe global developmental impairment | 35429480 | Severe global developmental delay |
| `phenotype:HP:0002104` (Apnea) | apnoeas | 35696452 | Apnoeas = Apnea |
| `therapy:kcnt1-aso` (KCNT1-targeting antisense oligonucleotide (knockdown)) | ASO-based gene silencing | 36173683 | KCNT1 ASO gene silencing |
| `phenotype:HP:0011972` (Hypoglycorrhachia) | hypoglycorrachia | 9462754 | Hypoglycorrhachia (spelling variant) |
| `phenotype:HP:0001639` (Hypertrophic cardiomyopathy) | Cardiac hypertrophy | 18929906 | cardiac hypertrophy of infantile Pompe = HCM |
| `phenotype:HP:0001071` (Angiokeratoma corporis diffusum) | angiokeratoma | 21092187 | Fabry angiokeratoma is angiokeratoma corporis diffusum |
| `phenotype:HP:0002180` (Neurodegeneration) | nervous system degeneration | 23622393 | Nervous system degeneration = neurodegeneration |
| `phenotype:HP:0002344` (Progressive neurologic deterioration) | progressive neurological symptoms | 24338084 | progressive neurologic deterioration |
| `phenotype:HP:0002333` (Motor deterioration) | loss of motor function | 27491216 | Loss of motor function = motor deterioration |
| `therapy:cerliponase-alfa` (Cerliponase alfa (intraventricular enzyme replacement for CLN2)) | intraventricular ERT | 27491216 | Intraventricular ERT for CLN2 = cerliponase alfa |
| `therapy:migalastat` (Migalastat (pharmacological chaperone)) | Oral migalastat | 30875019 | same drug |
| `phenotype:HP:0000618` (Blindness) | blinding | 35772852 | blinding = blindness |
| `therapy:ambroxol` (Ambroxol (repurposed pharmacological chaperone for glucocerebrosidase)) | High-dose ambroxol | 39116528 | ambroxol (high dose) |
| `phenotype:HP:0001510` (Growth delay) | growth failure | 40236726 | growth failure = growth delay |
| `phenotype:HP:0001510` (Growth delay) | Retardation of growth | 16377799 | Retardation of growth = growth delay |
| `phenotype:HP:0001510` (Growth delay) | impaired growth | 20694012 | Impaired growth = growth delay |
| `therapy:miglustat` (Miglustat (substrate reduction; also an enzyme stabilizer)) | Oral Miglustat | 40924969 | oral miglustat |
| `phenotype:HP:0000529` (Progressive visual loss) | progressive vision loss | 41199165 | Progressive visual loss |
| `disease:NPC1` (NPC1-related disorders (Niemann-Pick disease type C)) | Niemann-Pick C1 | 41895381 | Niemann-Pick C1 |
| `phenotype:HP:0002361` (Psychomotor deterioration) | psychomotor regression | 42175674 | Psychomotor regression = psychomotor deterioration |
| `therapy:fabry-enzyme-replacement` (Enzyme replacement for Fabry disease (agalsidase beta, pegunigalsidase alfa)) | recombinant α-galactosidase-A | 42622346 | recombinant alpha-Gal A ERT |
| `phenotype:HP:0000280` (Coarse facial features) | coarse face | 16170316 | Coarse face = coarse facial features |
| `phenotype:HP:0007018` (Attention deficit hyperactivity disorder) | attention deficits | 16271875 | Attention deficits = attention deficit (ADHD term) |
| `phenotype:HP:0001003` (Multiple lentigines) | Lentigines | 16377799 | Lentigines of LEOPARD = multiple lentigines |
| `phenotype:HP:0000316` (Hypertelorism) | Ocular hypertelorism | 16377799 | Ocular hypertelorism = Hypertelorism |
| `phenotype:HP:0001642` (Pulmonic stenosis) | Pulmonic valvular stenosis | 16377799 | Pulmonic valvular stenosis = Pulmonic stenosis |
| `phenotype:HP:0001642` (Pulmonic stenosis) | pulmonary valve stenosis | 22058153, 36184070 | pulmonary valve stenosis = pulmonic stenosis |
| `phenotype:HP:0005701` (Multiple enchondromatosis) | enchondromatosis | 21533187 | enchondromatosis = multiple enchondromatosis |
| `mech:tor-signaling` (TOR (mTOR) signaling) | mTOR pathway | 31722741, 15937108 | mTOR pathway |
| `mech:negative-regulation-of-ras-signaling` (Negative regulation of Ras protein signal transduction) | negatively controlling RAS signaling | 34346503 | negative regulation of RAS signaling |
| `mech:positive-regulation-of-ras-signaling` (Positive regulation of Ras protein signal transduction) | positive regulator of RAS signaling | 34346503 | positive regulation of RAS signaling |
| `mech:mapk-cascade` (MAPK cascade) | RAS-MAPK pathway | 35605646 | RAS-MAPK pathway |
| `mech:regulation-of-synaptic-plasticity` (Regulation of synaptic plasticity) | synaptic plasticity | 12427827 | Synaptic plasticity regulated by SynGAP |
| `mech:ca-triggered-exocytosis` (Ca2+-triggered neurotransmitter exocytosis) | synaptic neurotransmitter release | 18293354 | Ca-channel-mediated neurotransmitter release |
| `mech:ca-triggered-exocytosis` (Ca2+-triggered neurotransmitter exocytosis) | neurotransmitter release | 20631222 | Ca-channel-mediated neurotransmitter release |
| `mech:protein-destabilization` (Protein destabilization / misfolding) | folding-defective | 19402159 | Folding defect = misfolding |
| `phenotype:HP:0001250` (Seizure) | susceptibility to seizures | 20631222 | seizures |
| `phenotype:HP:0000476` (Cystic hygroma) | nuchal hygroma | 25959749 | nuchal hygroma = cystic hygroma |
| `mech:lysosomal-protein-catabolism` (Lysosomal protein breakdown) | lysosomal proteolysis | 33308480 | lysosomal proteolysis |

Not proposed despite a "same" judgement (hygiene rules in `reconcile.mjs`): "clonic seizures" → `phenotype:HP:0020221` (only a plural/spelling variant of an existing name); "epileptic spasms" → `phenotype:HP:0011097` (only a plural/spelling variant of an existing name); "cannabidiol" → `therapy:cannabidiol` (only a plural/spelling variant of an existing name); "seizures" → `phenotype:HP:0001250` (only a plural/spelling variant of an existing name); "absence seizures" → `phenotype:HP:0002121` (only a plural/spelling variant of an existing name); "tonic seizures" → `phenotype:HP:0032792` (only a plural/spelling variant of an existing name); "sodium channel blocker treatment" → `therapy:sodium-channel-blockers` (descriptive phrase, not a name); "Antisense oligonucleotide therapy" → `therapy:kcnt1-aso` (descriptive phrase, not a name); "gene-silencing antisense oligonucleotide (ASO)" → `therapy:kcnt1-aso` (descriptive phrase, not a name); "elsunersen" → `therapy:elsunersen` (only a plural/spelling variant of an existing name); "zorevunersen" → `therapy:zorevunersen` (only a plural/spelling variant of an existing name); "KCNT1-targeting antisense oligonucleotide" → `therapy:kcnt1-aso` (only a plural/spelling variant of an existing name); "SCB" → `therapy:sodium-channel-blockers` (only a plural/spelling variant of an existing name); "Myoclonic seizures" → `phenotype:HP:0032794` (only a plural/spelling variant of an existing name); "laronidase" → `therapy:laronidase` (only a plural/spelling variant of an existing name); "mucopolysaccharidosis I" → `disease:IDUA` (only a plural/spelling variant of an existing name); "Miglustat" → `therapy:miglustat` (only a plural/spelling variant of an existing name); "Niemann-Pick type C disease" → `disease:NPC1` (generic disease name without the gene); "Pompe's disease" → `disease:GAA` (generic disease name without the gene); "Niemann-Pick C disease" → `disease:NPC1` (generic disease name without the gene); "Pyrimethamine" → `therapy:pyrimethamine` (only a plural/spelling variant of an existing name); "enzyme replacement therapy using recombinant human α-galactosidase A" → `therapy:fabry-enzyme-replacement` (descriptive phrase, not a name); "Enzyme replacement therapy" → `therapy:gaucher-enzyme-replacement` (descriptive phrase, not a name); "eliglustat" → `therapy:eliglustat` (only a plural/spelling variant of an existing name); "GD" → `disease:GBA1` (generic disease name without the gene); "Juvenile NCL" → `disease:CLN3` (generic disease name without the gene); "hematopoietic stem cell transplantation" → `therapy:hsct-krabbe` (descriptive phrase, not a name); "migalastat" → `therapy:migalastat` (only a plural/spelling variant of an existing name); "cerliponase alfa" → `therapy:cerliponase-alfa` (only a plural/spelling variant of an existing name); "enzyme replacement therapy (ERT)" → `therapy:pompe-enzyme-replacement` (descriptive phrase, not a name); "pabinafusp alfa" → `therapy:pabinafusp-alfa` (only a plural/spelling variant of an existing name); "mucopolysaccharidosis II" → `disease:IDS` (generic disease name without the gene); "arimoclomol" → `therapy:arimoclomol` (only a plural/spelling variant of an existing name); "Lentiviral haematopoietic stem-cell gene therapy" → `therapy:atidarsagene-autotemcel` (descriptive phrase, not a name); "atidarsagene autotemcel" → `therapy:atidarsagene-autotemcel` (only a plural/spelling variant of an existing name); "olipudase alfa" → `therapy:olipudase-alfa` (only a plural/spelling variant of an existing name); "Gaucher diseases" → `disease:GBA1` (only a plural/spelling variant of an existing name); "Ambroxol" → `therapy:ambroxol` (only a plural/spelling variant of an existing name); "high-dose ambroxol therapy" → `therapy:ambroxol` (descriptive phrase, not a name); "enzyme replacement therapy" → `therapy:olipudase-alfa` (descriptive phrase, not a name); "Metachromatic leukodystrophy (MLD)" → `disease:ARSA` (descriptive phrase, not a name); "hematopoietic stem cell gene therapy" → `therapy:atidarsagene-autotemcel` (descriptive phrase, not a name); "gait disturbances" → `phenotype:HP:0001288` (only a plural/spelling variant of an existing name); "Krabbe disease (KD)" → `disease:GALC` (descriptive phrase, not a name); "Tay-Sachs" → `disease:HEXA` (generic disease name without the gene); "Niemann-Pick disease type C (NPC)" → `disease:NPC1` (descriptive phrase, not a name); "Pompe" → `disease:GAA` (generic disease name without the gene); "Tay-Sachs disease (TSD)" → `disease:HEXA` (descriptive phrase, not a name); "hypertrophic cardiomyopathy (HCM)" → `phenotype:HP:0001639` (descriptive phrase, not a name); "statin" → `therapy:statins-nf1-cognition` (only a plural/spelling variant of an existing name); "Noonan syndrome-like phenotype" → `disease:CBL` (generic disease name without the gene); "CBL" → `disease:CBL` (generic disease name without the gene); "juvenile myelomonocytic leukemia (JMML)" → `phenotype:HP:0012209` (descriptive phrase, not a name); "rapamycin" → `therapy:rapamycin-nsml` (only a plural/spelling variant of an existing name); "mTOR" → `mech:tor-signaling` (single generic word); "mTOR signaling" → `mech:tor-signaling` (only a plural/spelling variant of an existing name); "tipifarnib" → `therapy:tipifarnib` (only a plural/spelling variant of an existing name); "Neurofibromatosis type 1 (NF1)" → `disease:NF1` (descriptive phrase, not a name); "selumetinib" → `therapy:selumetinib` (only a plural/spelling variant of an existing name); "intellectual disabilities" → `phenotype:HP:0001249` (only a plural/spelling variant of an existing name); "RAS/MAPK pathway" → `mech:mapk-cascade` (descriptive phrase, not a name); "CS" → `disease:HRAS` (generic disease name without the gene); "inhibition of the RAS/MAPK signaling" → `mech:negative-regulation-of-ras-signaling` (descriptive phrase, not a name); "café-au-lait maculae (CALM)" → `phenotype:HP:0000957` (descriptive phrase, not a name); "trametinib" → `therapy:trametinib` (only a plural/spelling variant of an existing name); "Neurofibromatosis 1 (NF1)" → `disease:NF1` (descriptive phrase, not a name); "Costello syndrome (CS)" → `disease:HRAS` (descriptive phrase, not a name); "Noonan Syndrome" → `disease:RIT1` (generic disease name without the gene); "Mirdametinib" → `therapy:mirdametinib` (only a plural/spelling variant of an existing name); "ERK/MAPK signaling" → `mech:mapk-cascade` (descriptive phrase, not a name); "neurofibromatosis type I" → `disease:NF1` (generic disease name without the gene); "Gaucher's disease" → `disease:GBA1` (generic disease name without the gene); "Niemann-Pick type C" → `disease:NPC1` (generic disease name without the gene).

## Reconciliation

2082 distinct mentions (per abstract and type): 771 resolved by the deterministic index, 627 by the Claude step, 647 unresolved (no matching node, or the model answered "none"), 0 generic ("patients", "neurons"…) skipped, 37 gene symbols outside the slice. Claude picks outside the candidate list rejected: 0.

| Method | Mentions |
|---|---|
| claude:none | 647 |
| exact | 439 |
| claude:instance | 401 |
| claude:same | 226 |
| variant-rule(gene-level) | 83 |
| gene-rule | 78 |
| exact+context | 69 |
| label-containment | 46 |
| variant-rule | 39 |
| not-in-graph | 37 |
| variant-rule(gene-level)+context | 12 |
| variant-rule+context | 5 |

**One entity, several nodes (for the curators).** These names are shared by two nodes of the same type in the curated graph, so claims about them cannot reconcile to one stable node. Merging or cross-linking them is a curation decision:

- "HBSCI" (gene): `gene:SCN1A`, `gene:SCN2A`
- "EEG with spike-wave complexes" (phenotype): `phenotype:HP:0010849`, `phenotype:HP:0010850`

Claims dropped by the mapping rules (endpoints resolved but not comparable):

- gene and gene-defined disease differ: 15

Mapping rules (fixed, in `compare.mjs`): `causes` is lifted from a variant class to its gene; a gene or gene-level variant claim about an effect becomes `disease:<GENE> driven_by`; a variant-class effect is compared on `vg:… has_effect` and, as the curators do, also on the disease's `driven_by` edge; `has_phenotype` claims seen only in animal or cell models are not compared; "opposite effect class" means gain of function versus loss of function, haploinsufficiency, dominant-negative or destabilization of the same gene, and is flagged only where the graph lacks the claimed effect or the curators cite the same paper.

## Negative findings with no edge

Negated claims whose relation is not in the graph (nothing to contradict, kept for context):

- `disease:KCNQ2|has_phenotype|phenotype:HP:0001250` (PMID:28139826): "SIGNIFICANCE: Heterozygous KCNQ2 R201C and R201H gain-of-function variants present with profound neonatal encephalopathy in the absence of neonatal seizures."
- `disease:SCN8A|has_phenotype|phenotype:HP:0001250` (PMID:29726066): "We now report a novel heterozygous SCN8A variant, p.Pro1719Arg, in a small pedigree with five family members affected with autosomal dominant upper limb isolated myoclonus without seizures or cognitive impairment."
- `therapy:fenfluramine|targets|mech:voltage-gated-sodium-channel-activity` (PMID:41515912): "Additionally, pharmacological agents such as fenfluramine, stiripentol, and cannabidiol, although not acting directly on sodium channels, represent recognized therapeutic options for SCN1A-related Dravet syndrome."
- `therapy:stiripentol|targets|mech:voltage-gated-sodium-channel-activity` (PMID:41515912): "Additionally, pharmacological agents such as fenfluramine, stiripentol, and cannabidiol, although not acting directly on sodium channels, represent recognized therapeutic options for SCN1A-related Dravet syndrome."
- `therapy:cannabidiol|targets|mech:voltage-gated-sodium-channel-activity` (PMID:41515912): "Additionally, pharmacological agents such as fenfluramine, stiripentol, and cannabidiol, although not acting directly on sodium channels, represent recognized therapeutic options for SCN1A-related Dravet syndrome."
- `disease:LZTR1|driven_by|mech:protein-destabilization` (PMID:30481304): "Here we show that dominant NS-causing LZTR1 mutations do not affect significantly protein stability and subcellular localization."
- `disease:LZTR1|driven_by|mech:mapk-cascade` (PMID:30481304): "We provide the first evidence that these mutations, but not the missense changes occurring as biallelic mutations in recessive NS, enhance stimulus-dependent RAS-MAPK signaling, which is triggered, at least in part, by an increased RAS protein pool."
- `therapy:mirdametinib|targets|mech:regulation-of-synaptic-plasticity` (PMID:29940508): "Chronic administration of PD-0325901 normalized basal synaptic responses, but did not reverse LTP deficit."

## How to re-run

```bash
READER=claude node pipeline/openai/extract.mjs           # no calls: stamp provenance + verify every quote
READER=claude node pipeline/openai/reconcile.mjs --dump-pending pending.json   # mentions the index cannot resolve
READER=claude node pipeline/openai/reconcile.mjs --apply-answers answers.json  # agent answers, same accept rules
READER=claude node pipeline/openai/compare.mjs           # crosscheck_claude.json, claude_extracted.json, this report
python3 pipeline/build_graph.py                          # applies both readers' crosscheck files
```

Caches: `data/raw/claude/extractions/<PMID>.json` (claims, source file, input and instructions hashes), `data/raw/claude/reconcile/<PMID>.json` (payload and answers).

## Caveats

- Claude reads the abstract only, like the OpenAI reader. A disagreement is a prompt to look, not a verdict.
- The curated graph was itself built by agents (some of them Claude). The reading here was done blind to it, but it is the same model family, so agreement with Claude-curated edges is weaker evidence than agreement between different models.
- Only abstracts the curated graph cites were read; candidate edges and synonyms are proposals (`status: "unverified"`, `attrs.needs_review: true`, confidence ≤ 0.5).

