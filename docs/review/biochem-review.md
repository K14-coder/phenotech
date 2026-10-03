# Biochemistry review

Reviewer initials: 

Tick **one** box per item (change `[ ]` to `[x]`) and add a note whenever something is wrong. Skip what you can't get to; unreviewed links stay as they are. Every confirmed link shows "Reviewed by a biochemist" in the app.

- **Confirm**: correct as written.
- **Correct**: basically right, but the explanation, level, confidence or the filing of a source needs changing. Say how in the note.
- **Reject**: wrong or unsupported. It is removed from the atlas.

**Part 1** (7): the independent OpenAI re-reading disagrees with how a source was filed. Who is right?
**Part 2** (2): contradicting sources only the AI found. Does the source really contradict the link?
**Part 3** (50): the links the demo journeys rely on, including the atlas's own hypotheses.

# Part 1: AI re-reading disagrees

## 1. STX1B-related epilepsies → driven by → Loss of function

`disease:STX1B|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.7** · status **contested**

> Published work links STX1B-related disorders to loss of function. Genotype-phenotype split: truncating/LoF milder, SNARE-motif missense more severe. A deletion causing STX1B haploinsufficiency with myoclonic astatic epilepsy. Contradicting or limiting findings are attached as counter-evidence: Loss-of-function variants in very differently affected individuals. V216E, equally severe clinically, increases fusogenicity and release probability. (reported as a gain of function mechanism instead)

- Supports: [PMID:30737342](https://pubmed.ncbi.nlm.nih.gov/30737342/) _(AI re-reading agrees)_ — “More often, we found loss-of-function mutations in benign syndromes, whereas missense variants in the SNARE motif of syntaxin-1B were associated with more severe phenotypes.”
- Supports: [PMID:26818399](https://pubmed.ncbi.nlm.nih.gov/26818399/) — “This deletion results in haploinsufficiency of STX1B and other genes.”
- Supports: [PMID:32572454](https://pubmed.ncbi.nlm.nih.gov/32572454/) _(AI re-reading agrees)_ — “STX1BG226R, causing epileptic encephalopathies, strongly compromises the interaction with Munc18-1 and reduces expression of both proteins, the size of the readily releasable pool of vesicles, and Ca2+-triggered neurotransmitter release when expressed in STX1-null neurons.”
- Contradicts or limits: [PMID:33677401](https://pubmed.ncbi.nlm.nih.gov/33677401/) _(AI re-reading DISAGREES)_ — “The identification of loss-of-function variants in very differently affected individuals suggests that no clear genotype-phenotype correlation can be established.”
- Contradicts or limits: [PMID:32572454](https://pubmed.ncbi.nlm.nih.gov/32572454/) _(AI re-reading agrees)_ — “The mutation STX1BV216E, also causing epileptic encephalopathies, only slightly diminishes Munc18-1 and Munc13 interactions, but leads to enhanced fusogenicity and increased vesicular release probability, also in STX1-null neurons.”
- Contradicts or limits: [PMID:42673765](https://pubmed.ncbi.nlm.nih.gov/42673765/) _(AI re-reading DISAGREES)_ — “FINDINGS: G226R exhibited both gain- and loss-of-function characteristics, with increased miniature excitatory postsynaptic current frequency in networks but not in autapses, and synaptic failure during sustained high-frequency stimulation.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 2. STXBP1-related disorders → driven by → Dominant-negative effect (the altered protein blocks the good one)

`disease:STXBP1|driven_by|mech:dominant-negative`

Level **experimental** · confidence **0.5** · status **contested**

> Published work links STXBP1-related disorders to dominant-negative effect. The aggregation evidence underpinning the dominant-negative reading. Contradicting or limiting findings are attached as counter-evidence: No measurable mutant effect on a wild-type-containing background. The field's own review states the mechanism is not settled.

- Supports: [PMID:27597756](https://pubmed.ncbi.nlm.nih.gov/27597756/) _(AI re-reading agrees)_ — “Here, we used single-molecule analysis, gene-edited cells, and neurons to demonstrate that Munc18-1 EIEE-causing mutants form large polymers that coaggregate wild-type Munc18-1 in vitro and in cells.”
- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) — “Aggregates of mutant Munc18-1 incorporate wild-type Munc18-1, depleting functional Munc18-1 levels beyond hemizygous levels.”
- Supports: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) — “Munc18-1 is essential for neurotransmitter release, and mutations in Munc18-1 have been shown to cause neuronal dysfunction via aggregation and co-aggregation of the wild-type protein, reducing functional Munc18-1 levels well below hemizygous levels.”
- Contradicts or limits: [PMID:29538625](https://pubmed.ncbi.nlm.nih.gov/29538625/) — “Disease-causing STXBP1 variants supported synaptic transmission to a variable extent on a null background, but had no effect when overexpressed on a heterozygous background.”
- Contradicts or limits: [PMID:32643187](https://pubmed.ncbi.nlm.nih.gov/32643187/) _(AI re-reading DISAGREES)_ — “The molecular disease mechanisms underlying STXBP1-linked disorders are yet to be fully understood, but both haploinsufficiency and dominant-negative mechanisms have been proposed.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 3. STXBP1-related disorders → driven by → Haploinsufficiency (one working copy is not enough)

`disease:STXBP1|driven_by|mech:haploinsufficiency`

Level **experimental** · confidence **0.7** · status **contested**

> Published work links STXBP1-related disorders to haploinsufficiency. The original 2008 discovery paper already proposed haploinsufficiency. Isogenic human neurons: one bad copy lowers Munc18-1 and syntaxin-1 and halves release. Contradicting or limiting findings are attached as counter-evidence: Haploinsufficiency alone does not explain patient heterogeneity (Doc2A/B co-depletion).

- Supports: [PMID:18469812](https://pubmed.ncbi.nlm.nih.gov/18469812/) _(AI re-reading agrees)_ — “These findings suggest that haploinsufficiency of STXBP1 causes EIEE.”
- Supports: [PMID:26280581](https://pubmed.ncbi.nlm.nih.gov/26280581/) — “We demonstrated that heterozygous STXBP1 mutations lower the levels of Munc18-1 protein and its binding partner, the t-SNARE-protein Syntaxin-1, by approximately 30% and decrease spontaneous and evoked neurotransmitter release by nearly 50%.”
- Supports: [PMID:29538625](https://pubmed.ncbi.nlm.nih.gov/29538625/) _(AI re-reading agrees)_ — “Together, these cellular studies suggest that impaired protein stability and STXBP1 haploinsufficiency explain STXBP1-encephalopathy and that, therefore, Stxbp1+/- mice provide a valid mouse model.”
- Contradicts or limits: [PMID:38242640](https://pubmed.ncbi.nlm.nih.gov/38242640/) _(AI re-reading DISAGREES)_ — “Although haploinsufficiency is the prevailing disease mechanism, it remains unclear how the reduction in Munc18-1 levels causes synaptic dysfunction in disease as well as how haploinsufficiency alone can account for the significant heterogeneity among patients in terms of the presence, onset and severity of different s…”
- …and 1 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 4. STXBP1-related disorders → driven by → Protein destabilization / misfolding

`disease:STXBP1|driven_by|mech:protein-destabilization`

Level **experimental** · confidence **0.7** · status **contested**

> Published work links STXBP1-related disorders to protein destabilization / misfolding. Seven disease variants, all with severely reduced protein levels. At least five missense variants destabilize and aggregate Munc18-1. Contradicting or limiting findings are attached as counter-evidence: A recessive (homozygous) STXBP1 variant acts by gain of function, against the uniform loss-of-function model. (reported as a gain of function mechanism instead)

- Supports: [PMID:29538625](https://pubmed.ncbi.nlm.nih.gov/29538625/) _(AI re-reading agrees)_ — “All disease variants had severely decreased protein levels.”
- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) _(AI re-reading agrees)_ — “We find that at least five disease-linked missense mutations of Munc18-1 result in destabilization and aggregation of the mutant protein.”
- Supports: [PMID:25284778](https://pubmed.ncbi.nlm.nih.gov/25284778/) _(AI re-reading agrees)_ — “Using neurosecretory cells deficient in Munc18, we show that a disease-linked mutation, C180Y, renders the protein unstable at 37°C.”
- Contradicts or limits: [PMID:31855252](https://pubmed.ncbi.nlm.nih.gov/31855252/) _(AI re-reading DISAGREES)_ — “Hence, the homozygous L446F mutation causes a gain-of-function phenotype regarding release probability and synaptic transmission while having less impact on protein levels than previously reported (heterozygous) mutations.”
- …and 5 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 5. SYT1-related disorders (Baker-Gordon syndrome) → driven by → Gain of function (the protein does too much)

`disease:SYT1|driven_by|mech:gain-of-function`

Level **experimental** · confidence **0.5** · status **contested**

> A minority of published variants in SYT1 act by gain of function, against the mainstream view for this gene. P401L de-clamps spontaneous/asynchronous release instead of only reducing evoked release.

- Supports: [PMID:38321119](https://pubmed.ncbi.nlm.nih.gov/38321119/) _(AI re-reading DISAGREES)_ — “This is a novel cellular phenotype, distinct from what was previously found for other SYT1 disease variants, and points to a role for spontaneous and asynchronous release in SYT1-associated neurodevelopmental disorder.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 6. UNC13A-related disorders → driven by → Gain of function (the protein does too much)

`disease:UNC13A|driven_by|mech:gain-of-function`

Level **experimental** · confidence **0.5** · status **contested**

> Published work links UNC13A-related disorders to gain of function. P814L increases vesicle fusion propensity: dominant gain of function. Contradicting or limiting findings are attached as counter-evidence: Resolves the debate: reduced expression, gain of function and impaired regulation coexist.

- Supports: [PMID:28192369](https://pubmed.ncbi.nlm.nih.gov/28192369/) _(AI re-reading agrees)_ — “Electrophysiological studies in murine neuronal cultures and functional analyses in Caenorhabditis elegans revealed that the UNC13A variant causes a distinct dominant gain of function that is characterized by increased fusion propensity of synaptic vesicles, which leads to increased initial synaptic vesicle release pro…”
- Contradicts or limits: [PMID:41125872](https://pubmed.ncbi.nlm.nih.gov/41125872/) _(AI re-reading DISAGREES)_ — “Using assays with expression of UNC13A variants in mouse hippocampal neurons and in Caenorhabditis elegans, we identify three mechanisms of pathogenicity, including reduction in synaptic strength caused by reduced UNC13A protein expression, increased neurotransmission caused by UNC13A gain-of-function and impaired regu…”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 7. 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) → developed for → SLC6A1-related disorders

`therapy:4-phenylbutyrate|developed_for|disease:SLC6A1`

Level **clinical** · confidence **0.8** · status **contested**

> 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) has been investigated for SLC6A1-related disorders (stage: clinical).

- Supports: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) _(AI re-reading agrees)_ — “Importantly, 4-phenylbutyrate alone increased γ-amino butyric acid transporter 1 expression and suppressed spike wave discharges in heterozygous knockin mice.”
- Supports: [PMID:42157447](https://pubmed.ncbi.nlm.nih.gov/42157447/) _(AI re-reading agrees)_ — “RESULTS: PBA restored GABA uptake and GAT-1 surface expression across all variants, and TUDCA mimicked the effects of PBA.”
- Supports: [PMID:41385967](https://pubmed.ncbi.nlm.nih.gov/41385967/) — “Here, we tested whether PBA can improve neurobehavioral deficits in the Slc6a1+/S295L knock-in mouse model of DEE besides seizure mitigation.”
- Contradicts or limits: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) — “No disease-modifying therapy exists to treat these disorders, and while chemical chaperones have been shown to alleviate neuronal dysfunction caused by missense mutations in Munc18-1, their required high concentrations and potential toxicity necessitate a Munc18-1-targeted therapy.”
- Contradicts or limits: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) _(AI re-reading agrees)_ — “Although the mechanisms of action for 4-phenylbutyrate are still unclear, with multiple possibly being involved, it is likely that 4-phenylbutyrate can facilitate the forward trafficking of the wildtype γ-amino butyric acid transporter 1 regardless of rescuing the mutant γ-amino butyric acid transporter 1, thus increas…”
- Contradicts or limits: [PMID:39923323](https://pubmed.ncbi.nlm.nih.gov/39923323/) _(AI re-reading DISAGREES)_ — “Post-treatment EEGs showed a moderate reduction in epileptiform discharges following PBA administration, and patients exhibited improved motor function.”
- …and 1 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

# Part 2: contradictions found only by the AI

## 8. STX1B-related epilepsies → has phenotype → Febrile seizure (within the age range of 3 months to 6 years)

`disease:STX1B|has_phenotype|phenotype:HP:0002373`

Level **curated** · confidence **0.9** · status **supported**

> HPO annotates Febrile seizure (within the age range of 3 months to 6 years) to OMIM:616172 (STX1B-related disorders). This feature is distinctive (IC 4.28; seen in 179 of 12867 annotated diseases).

- Supports: [PMID:25362483](https://pubmed.ncbi.nlm.nih.gov/25362483/) _(AI re-reading agrees)_
- Supports: [PMID:33677401](https://pubmed.ncbi.nlm.nih.gov/33677401/) — “Febrile seizures occurred in two individuals.”
- Contradicts or limits: [PMID:30737342](https://pubmed.ncbi.nlm.nih.gov/30737342/) — “We discerned 4 different phenotypic groups across the newly identified and previously published patients (49 patients in 23 families): (1) 6 sporadic patients or families (31 affected individuals) with febrile and afebrile seizures with a benign course, generally good drug response, normal development, and without perm…”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 9. STXBP1: Missense variants (single amino-acid changes) → has effect → Dominant-negative effect (the altered protein blocks the good one)

`vg:STXBP1:missense|has_effect|mech:dominant-negative`

Level **experimental** · confidence **0.6** · status **contested**

> Missense variants (single amino-acid changes) in STXBP1 are linked to dominant-negative effect. The aggregation evidence underpinning the dominant-negative reading.

- Supports: [PMID:27597756](https://pubmed.ncbi.nlm.nih.gov/27597756/) — “Here, we used single-molecule analysis, gene-edited cells, and neurons to demonstrate that Munc18-1 EIEE-causing mutants form large polymers that coaggregate wild-type Munc18-1 in vitro and in cells.”
- Contradicts or limits: [PMID:29538625](https://pubmed.ncbi.nlm.nih.gov/29538625/) — “Disease-causing STXBP1 variants supported synaptic transmission to a variable extent on a null background, but had no effect when overexpressed on a heterozygous background.”
- Contradicts or limits: [PMID:32643187](https://pubmed.ncbi.nlm.nih.gov/32643187/) — “The molecular disease mechanisms underlying STXBP1-linked disorders are yet to be fully understood, but both haploinsufficiency and dominant-negative mechanisms have been proposed.”
- Contradicts or limits: [PMID:31855252](https://pubmed.ncbi.nlm.nih.gov/31855252/) — “Hence, the homozygous L446F mutation causes a gain-of-function phenotype regarding release probability and synaptic transmission while having less impact on protein levels than previously reported (heterozygous) mutations.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

# Part 3: links the demo relies on

## 10. SNAP25-related disorders → shares mechanism → CPLX1-related disorders

`disease:SNAP25|shares_mechanism|disease:CPLX1`

Level **curated** · confidence **0.7** · status **supported**

> SNAP25 and CPLX1 act in the same presynaptic process (Synaptic vesicle fusion with the active zone membrane) and their disease variants share at least one molecular effect (Loss of function). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [synaptic-vesicle-fusion](https://www.ebi.ac.uk/QuickGO/term/GO:0031629)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 11. SNAP25-related disorders → shares mechanism → STX1A-related neurodevelopmental disorder

`disease:SNAP25|shares_mechanism|disease:STX1A`

Level **curated** · confidence **0.7** · status **supported**

> SNAP25 and STX1A act in the same presynaptic process (Synaptic vesicle priming) and their disease variants share at least one molecular effect (Loss of function). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [synaptic-vesicle-priming](https://www.ebi.ac.uk/QuickGO/term/GO:0016082)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 12. SNAP25-related disorders → shares mechanism → STX1B-related epilepsies

`disease:SNAP25|shares_mechanism|disease:STX1B`

Level **curated** · confidence **0.7** · status **supported**

> SNAP25 and STX1B act in the same presynaptic process (Ca2+-triggered neurotransmitter exocytosis, Synaptic vesicle fusion with the active zone membrane, Synaptic vesicle priming) and their disease variants share at least one molecular effect (Loss of function). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:33299146](https://pubmed.ncbi.nlm.nih.gov/33299146/) — “Thus, these findings advance the concept of a group of neurodevelopmental disorders that may be termed "SNAREopathies."”
- Supports: [ca-triggered-exocytosis](https://www.ebi.ac.uk/QuickGO/term/GO:0048791)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 13. SNAP25-related disorders → shares mechanism → UNC13A-related disorders

`disease:SNAP25|shares_mechanism|disease:UNC13A`

Level **curated** · confidence **0.7** · status **supported**

> SNAP25 and UNC13A act in the same presynaptic process (Synaptic vesicle priming) and their disease variants share at least one molecular effect (Gain of function, Loss of function). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [synaptic-vesicle-priming](https://www.ebi.ac.uk/QuickGO/term/GO:0016082)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 14. STXBP1-related disorders → shares mechanism → SLC6A1-related disorders

`disease:STXBP1|shares_mechanism|disease:SLC6A1`

Level **experimental** · confidence **0.6** · status **contested**

> Different genes, different pathways, same cell-biological problem: a subset of STXBP1 (Munc18-1) and SLC6A1 (GAT-1) missense variants make a protein that is unstable or misfolded, so it is degraded or stuck in the endoplasmic reticulum rather than working. Both have been rescued by the chemical chaperone 4-phenylbutyrate in laboratory models, and one early-phase trial (NCT04937062) enrols children with either gene on exactly this shared rationale. Important limits are attached as counter-evidence: roughly a third of SLC6A1 loss-of-function missense variants reach the cell surface normally and so cannot be helped by folding correction; no dominant-negative effect was found in SLC6A1; chemical chaperones need high, potentially toxic concentrations; the benefit may come from boosting the healthy copy rather than fixing the mutant; and the only human outcome data is two uncontrolled deletion patients.

- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) — “We find that at least five disease-linked missense mutations of Munc18-1 result in destabilization and aggregation of the mutant protein.”
- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) — “We demonstrate that the three chemical chaperones 4-phenylbutyrate, sorbitol, and trehalose reverse the deficits caused by mutations in Munc18-1 in vitro and in vivo in multiple models, offering a novel strategy for the treatment of varied encephalopathies.”
- Supports: [PMID:34028503](https://pubmed.ncbi.nlm.nih.gov/34028503/) — “The reduced GABA uptake appears to be due to reduced cell surface expression of the variant transporter caused by variant protein misfolding, endoplasmic reticulum retention, and subsequent degradation.”
- Contradicts or limits: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Surface localization was assessed for 86 variants; two-thirds of loss-of-function missense variants prevented GAT-1 from being present on the membrane while GAT-1 was on the surface but with reduced activity for the remaining third.”
- Contradicts or limits: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Surprisingly, recurrent de novo missense variants showed moderate loss-of-function effects that reduced GABA uptake with no evidence for dominant-negative or gain-of-function effects.”
- Contradicts or limits: [PMID:29538625](https://pubmed.ncbi.nlm.nih.gov/29538625/) — “Disease-causing STXBP1 variants supported synaptic transmission to a variable extent on a null background, but had no effect when overexpressed on a heterozygous background.”
- …and 6 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 15. STXBP1-related disorders → shares mechanism → SNAP25-related disorders

`disease:STXBP1|shares_mechanism|disease:SNAP25`

Level **curated** · confidence **0.7** · status **supported**

> STXBP1 and SNAP25 act in the same presynaptic process (Ca2+-triggered neurotransmitter exocytosis, Synaptic vesicle fusion with the active zone membrane, Synaptic vesicle priming) and their disease variants share at least one molecular effect (Dominant-negative effect). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:33299146](https://pubmed.ncbi.nlm.nih.gov/33299146/) — “Thus, these findings advance the concept of a group of neurodevelopmental disorders that may be termed "SNAREopathies."”
- Supports: [ca-triggered-exocytosis](https://www.ebi.ac.uk/QuickGO/term/GO:0048791)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 16. STXBP1-related disorders → shares mechanism → SYT1-related disorders (Baker-Gordon syndrome)

`disease:STXBP1|shares_mechanism|disease:SYT1`

Level **curated** · confidence **0.7** · status **supported**

> STXBP1 and SYT1 act in the same presynaptic process (Ca2+-triggered neurotransmitter exocytosis, Synaptic vesicle fusion with the active zone membrane) and their disease variants share at least one molecular effect (Dominant-negative effect). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [ca-triggered-exocytosis](https://www.ebi.ac.uk/QuickGO/term/GO:0048791)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 17. STXBP1-related disorders → shares mechanism → VAMP2-related disorders

`disease:STXBP1|shares_mechanism|disease:VAMP2`

Level **curated** · confidence **0.7** · status **supported**

> STXBP1 and VAMP2 act in the same presynaptic process (SNARE complex assembly) and their disease variants share at least one molecular effect (Protein destabilization / misfolding). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:33299146](https://pubmed.ncbi.nlm.nih.gov/33299146/) — “Thus, these findings advance the concept of a group of neurodevelopmental disorders that may be termed "SNAREopathies."”
- Supports: [snare-complex-assembly](https://www.ebi.ac.uk/QuickGO/term/GO:0035493)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 18. SYT1-related disorders (Baker-Gordon syndrome) → shares mechanism → SNAP25-related disorders

`disease:SYT1|shares_mechanism|disease:SNAP25`

Level **curated** · confidence **0.7** · status **supported**

> SYT1 and SNAP25 act in the same presynaptic process (Ca2+-triggered neurotransmitter exocytosis, Synaptic vesicle fusion with the active zone membrane) and their disease variants share at least one molecular effect (Dominant-negative effect). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [ca-triggered-exocytosis](https://www.ebi.ac.uk/QuickGO/term/GO:0048791)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 19. VAMP2-related disorders → shares mechanism → STX1A-related neurodevelopmental disorder

`disease:VAMP2|shares_mechanism|disease:STX1A`

Level **curated** · confidence **0.7** · status **supported**

> VAMP2 and STX1A act in the same presynaptic process (SNARE complex assembly) and their disease variants share at least one molecular effect (Loss of function). Reviews group both genes in the same disease family.

- Supports: [PMID:32559416](https://pubmed.ncbi.nlm.nih.gov/32559416/) — “We propose to unify these syndromes, based on etiology and mechanism, as "SNAREopathies." Here, we review the strikingly diverse clinical phenomenology and disease severity and the also remarkably diverse genetic mechanisms.”
- Supports: [PMID:32916768](https://pubmed.ncbi.nlm.nih.gov/32916768/) — “In this review, we focus on disorders of synaptic vesicle fusion caused either by toxic insult to the presynapse or alterations to genes encoding the key proteins that control and regulate fusion: the SNARE proteins (synaptobrevin, syntaxin-1 and SNAP-25), Munc18, Munc13, synaptotagmin, complexin, CSPα, α-synuclein, PR…”
- Supports: [snare-complex-assembly](https://www.ebi.ac.uk/QuickGO/term/GO:0035493)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 20. 3,4-Diaminopyridine (amifampridine) → candidate for → STXBP1-related disorders

`therapy:3-4-diaminopyridine|candidate_for|disease:STXBP1`

Level **hypothesis** · confidence **0.12** · status **unverified**

> HYPOTHESIS, not a finding. The atlas computed this chain: the gene participates in Ca2+-triggered neurotransmitter exocytosis and 3,4-Diaminopyridine (amifampridine) is aimed at that process (no edge says this disease dysregulates it in the direction the drug pushes); and the graph has no developed_for edge and no study testing this therapy class in this disease. The weakest link is the pathway chain plus the contested mechanism: STXBP1 reaches this drug class only through 'the gene participates in Ca2+-triggered exocytosis', while the direction of its own release defect is disputed in the literature. Nobody has tested this.

- Supports: [therapy:3-4-diaminopyridine|targets|mech:ca-triggered-exocytosis](/path?from=disease:STXBP1&to=therapy:3-4-diaminopyridine)
- Supports: [gene:STXBP1|causes|disease:STXBP1](/path?from=disease:STXBP1&to=therapy:3-4-diaminopyridine)
- Supports: [gene:STXBP1|participates_in|mech:ca-triggered-exocytosis](/path?from=disease:STXBP1&to=therapy:3-4-diaminopyridine)

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 21. 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) → candidate for → VAMP2-related disorders

`therapy:4-phenylbutyrate|candidate_for|disease:VAMP2`

Level **hypothesis** · confidence **0.18** · status **unverified**

> HYPOTHESIS, not a finding. The atlas computed this chain: VAMP2-related disorders is linked to Protein destabilization / misfolding by a driven_by edge, and 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) is aimed at that same mechanism; and the graph has no developed_for edge and no study testing this therapy class in this disease. The weakest link is the VAMP2 destabilization edge itself: it is a contested edge resting on one 2025 paper, and that paper's 'stability' defect is a SNARE-complex property, not the degradation-and-rescue event that 4-PBA is known to act on. Nobody has tested this.

- Supports: [therapy:4-phenylbutyrate|targets|mech:protein-destabilization](/path?from=disease:VAMP2&to=therapy:4-phenylbutyrate)
- Supports: [disease:VAMP2|driven_by|mech:protein-destabilization](/path?from=disease:VAMP2&to=therapy:4-phenylbutyrate)
- Contradicts or limits: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Although the mechanisms of action for 4-phenylbutyrate are still unclear, with multiple possibly being involved, it is likely that 4-phenylbutyrate can facilitate the forward trafficking of the wildtype γ-amino butyric acid transporter 1 regardless of rescuing the mutant γ-amino butyric acid transporter 1, thus increas…”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “The neurotransmission deficits we observed parallel the symptomatic heterogeneity of the patients, with some variants displaying a disproportionate augmentation of spontaneous neurotransmitter release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 22. Acetylcholinesterase inhibitors (e.g. pyridostigmine) → candidate for → SNAP25-related disorders

`therapy:acetylcholinesterase-inhibitor-cms|candidate_for|disease:SNAP25`

Level **hypothesis** · confidence **0.14** · status **unverified**

> HYPOTHESIS, not a finding. The atlas computed this chain: the gene participates in Ca2+-triggered neurotransmitter exocytosis and Acetylcholinesterase inhibitors (e.g. pyridostigmine) is aimed at that process (no edge says this disease dysregulates it in the direction the drug pushes); and the graph has no developed_for edge and no study testing this therapy class in this disease. The weakest link is the pathway chain and the phenotype split: the drug argument needs a neuromuscular junction, and whether SNAP25-DEE patients have one has never been measured. Nobody has tested this.

- Supports: [therapy:acetylcholinesterase-inhibitor-cms|targets|mech:ca-triggered-exocytosis](/path?from=disease:SNAP25&to=therapy:acetylcholinesterase-inhibitor-cms)
- Supports: [gene:SNAP25|causes|disease:SNAP25](/path?from=disease:SNAP25&to=therapy:acetylcholinesterase-inhibitor-cms)
- Supports: [gene:SNAP25|participates_in|mech:ca-triggered-exocytosis](/path?from=disease:SNAP25&to=therapy:acetylcholinesterase-inhibitor-cms)
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 23. SLC6A1-related disorders → driven by → GABA reuptake

`disease:SLC6A1|driven_by|mech:gaba-reuptake`

Level **experimental** · confidence **0.5** · status **unverified**

> A 2019 functional study (PMID:31176687) reports that SLC6A1-related disorders involve gaba reuptake. Found by automated extraction with OpenAI; not yet reviewed by a person.

- Supports: [PMID:31176687](https://pubmed.ncbi.nlm.nih.gov/31176687/) — “The mutation also caused reduced GABA uptake in addition to reduced protein expression, leading to reduced GABA clearance, and altered GABAergic signaling in the brain.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 24. SLC6A1-related disorders → driven by → Haploinsufficiency (one working copy is not enough)

`disease:SLC6A1|driven_by|mech:haploinsufficiency`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SLC6A1-related disorders to haploinsufficiency. 213 variants: haploinsufficiency without dominant-negative or gain-of-function effects.

- Supports: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) _(AI re-reading agrees)_ — “Surprisingly, recurrent de novo missense variants showed moderate loss-of-function effects that reduced GABA uptake with no evidence for dominant-negative or gain-of-function effects.”
- Supports: [PMID:41174879](https://pubmed.ncbi.nlm.nih.gov/41174879/) — “SLC6A1 haploinsufficiency has been confirmed as the predominant pathway of SLC6A1-related neurodevelopmental disorder (SLC6A1-NDD); however, the molecular mechanism underlying the variable clinical presentation remains unclear.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 25. SLC6A1-related disorders → driven by → Loss of function

`disease:SLC6A1|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SLC6A1-related disorders to loss of function. Discovery paper: SLC6A1 variants reduce GABA re-uptake in myoclonic-atonic epilepsy.

- Supports: [PMID:25865495](https://pubmed.ncbi.nlm.nih.gov/25865495/) _(AI re-reading agrees)_ — “We describe two truncations and four missense alterations, all of which most likely lead to loss of function of GAT-1 and thus reduced GABA re-uptake from the synapse.”
- Supports: [PMID:34028503](https://pubmed.ncbi.nlm.nih.gov/34028503/) — “We found that a partial or complete loss-of-function represents a common disease mechanism, although the extent of GABA uptake reduction is variable.”
- Supports: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Based on functional assays of solute carrier Family 6 Member 1 variants, we conclude that partial or complete loss of γ-amino butyric acid uptake due to reduced membrane γ-amino butyric acid transporter 1 trafficking is the primary aetiology.”
- …and 4 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 26. SLC6A1-related disorders → driven by → Protein destabilization / misfolding

`disease:SLC6A1|driven_by|mech:protein-destabilization`

Level **experimental** · confidence **0.7** · status **contested**

> Published work links SLC6A1-related disorders to protein destabilization / misfolding. 22 variants: misfolding, ER retention and degradation as the shared molecular defect. G234S: protein instability with reduced surface and total protein. Contradicting or limiting findings are attached as counter-evidence: About a third of LoF missense variants traffic normally but transport poorly. Independent confirmation of a surface-expressed, transport-dead class.

- Supports: [PMID:34028503](https://pubmed.ncbi.nlm.nih.gov/34028503/) _(AI re-reading agrees)_ — “The reduced GABA uptake appears to be due to reduced cell surface expression of the variant transporter caused by variant protein misfolding, endoplasmic reticulum retention, and subsequent degradation.”
- Supports: [PMID:31176687](https://pubmed.ncbi.nlm.nih.gov/31176687/) _(AI re-reading agrees)_ — “CONCLUSIONS: This mutation caused instability of the mutant transporter protein, which resulted in reduced cell surface and total protein levels.”
- Supports: [PMID:36741049](https://pubmed.ncbi.nlm.nih.gov/36741049/) _(AI re-reading agrees)_ — “Many of these loss-of-function variants were absent from their regular site of action at the cell surface, due to protein misfolding and/or impaired trafficking machinery (as verified by confocal microscopy and de-glycosylation experiments).”
- Contradicts or limits: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Surface localization was assessed for 86 variants; two-thirds of loss-of-function missense variants prevented GAT-1 from being present on the membrane while GAT-1 was on the surface but with reduced activity for the remaining third.”
- Contradicts or limits: [PMID:36741049](https://pubmed.ncbi.nlm.nih.gov/36741049/) _(AI re-reading agrees)_ — “A modest fraction of the mutants displayed correct targeting to the plasma membrane, but nonetheless rendered the mutated proteins devoid of GABA transport, possibly due to structural alterations in the GABA binding site/translocation pathway.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 27. SNAP25-related disorders → driven by → Dominant-negative effect (the altered protein blocks the good one)

`disease:SNAP25|driven_by|mech:dominant-negative`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SNAP25-related disorders to dominant-negative effect. Direct dominant-negative demonstration with a SNARE-ring stoichiometry model.

- Supports: [PMID:41579375](https://pubmed.ncbi.nlm.nih.gov/41579375/) _(AI re-reading agrees)_ — “I192N is strongly dominant negative in the presence of wild-type SNAP-25, leading to impaired survival and reduced synaptic release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 28. SNAP25-related disorders → driven by → Gain of function (the protein does too much)

`disease:SNAP25|driven_by|mech:gain-of-function`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SNAP25-related disorders to gain of function. One variant augments spontaneous release without changing evoked release.

- Supports: [PMID:33147442](https://pubmed.ncbi.nlm.nih.gov/33147442/) — “Importantly, we identified a single mutation that augments spontaneous release without altering evoked release, suggesting that aberrant spontaneous release is sufficient to cause disease in humans.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 29. SNAP25-related disorders → driven by → Loss of function

`disease:SNAP25|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.5** · status **contested**

> Published work links SNAP25-related disorders to loss of function. Patient-derived human neurons: I67N reduces release and responds to 4-aminopyridine. Contradicting or limiting findings are attached as counter-evidence: V48F shows the opposite phenotype, so the mechanism is variant-specific, not gene-level.

- Supports: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “The I67N variant phenotype could be ameliorated by the clinically approved K+-channel blocker 4-aminopyridine.”
- Supports: [PMID:25381298](https://pubmed.ncbi.nlm.nih.gov/25381298/) — “CONCLUSION: Ile67Asn variant in SNAP25B is pathogenic because it inhibits synaptic vesicle exocytosis.”
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 30. STXBP1-related disorders → driven by → Gain of function (the protein does too much)

`disease:STXBP1|driven_by|mech:gain-of-function`

Level **experimental** · confidence **0.5** · status **contested**

> A minority of published variants in STXBP1 act by gain of function, against the mainstream view for this gene. A recessive (homozygous) STXBP1 variant acts by gain of function, against the uniform loss-of-function model.

- Supports: [PMID:31855252](https://pubmed.ncbi.nlm.nih.gov/31855252/) _(AI re-reading agrees)_ — “Hence, the homozygous L446F mutation causes a gain-of-function phenotype regarding release probability and synaptic transmission while having less impact on protein levels than previously reported (heterozygous) mutations.”
- Supports: [PMID:27597756](https://pubmed.ncbi.nlm.nih.gov/27597756/) — “Munc18-1 heterozygous mutations cause developmental defects and epileptic phenotypes, including infantile epileptic encephalopathy (EIEE), suggestive of a gain of pathological function.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 31. STXBP1-related disorders → driven by → Loss of function

`disease:STXBP1|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.5** · status **unverified**

> A 2026 animal-model study (PMID:41883162) reports that STXBP1-related disorders involve loss of function. Found by automated extraction with OpenAI; not yet reviewed by a person.

- Supports: [PMID:41883162](https://pubmed.ncbi.nlm.nih.gov/41883162/) — “STXBP1-related developmental and epileptic encephalopathy (STXBP1-DEE) is a debilitating genetic epilepsy disorder caused by heterozygous loss-of-function mutations in the STXBP1 gene.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 32. STXBP1-related disorders → driven by → Synaptic vesicle fusion with the active zone membrane

`disease:STXBP1|driven_by|mech:synaptic-vesicle-fusion`

Level **experimental** · confidence **0.5** · status **unverified**

> A 2026 animal-model study (PMID:41714804) reports that STXBP1-related disorders involve synaptic vesicle fusion with the active zone membrane. Found by automated extraction with OpenAI; not yet reviewed by a person.

- Supports: [PMID:41714804](https://pubmed.ncbi.nlm.nih.gov/41714804/) — “In Stxbp1K98Q knock-in mice, the upregulation of STXBP1 K98cr reduces the binding with syntaxin-1B(STX1B), leading to a decreased assembly of soluble NSF attachment protein receptors (SNAREs) in presynaptic active zone and subsequent inhibition vesicle release, thereby promoting epilepsy formation.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 33. SYT1-related disorders (Baker-Gordon syndrome) → driven by → Ca2+-triggered neurotransmitter exocytosis

`disease:SYT1|driven_by|mech:ca-triggered-exocytosis`

Level **experimental** · confidence **0.45** · status **unverified**

> A 2024 functional study (PMID:39481209) suggests that SYT1-related disorders (Baker-Gordon syndrome) involve ca2+-triggered neurotransmitter exocytosis. Found by automated extraction with OpenAI; not yet reviewed by a person.

- Supports: [PMID:39481209](https://pubmed.ncbi.nlm.nih.gov/39481209/) — “Together, this suggests that there is a genotype-function-phenotype relationship in SYT1-associated neurodevelopmental disorder, centring impaired evoked neurotransmitter release as a common pathogenic driver.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 34. SYT1-related disorders (Baker-Gordon syndrome) → driven by → Dominant-negative effect (the altered protein blocks the good one)

`disease:SYT1|driven_by|mech:dominant-negative`

Level **experimental** · confidence **0.8** · status **supported**

> Published work links SYT1-related disorders to dominant-negative effect. First human SYT1 variant, already described as dominant negative. Three patient variants: potent, graded dominant-negative effects.

- Supports: [PMID:25705886](https://pubmed.ncbi.nlm.nih.gov/25705886/) _(AI re-reading agrees)_ — “Together, the clinical features, electrophysiological phenotype, and in vitro neuronal phenotype associated with this dominant negative SYT1 mutation highlight presynaptic mechanisms that mediate human motor control and cognitive development.”
- Supports: [PMID:32362337](https://pubmed.ncbi.nlm.nih.gov/32362337/) _(AI re-reading agrees)_ — “Synaptic transmission was impaired in neurons expressing mutant variants, which demonstrated potent, graded dominant-negative effects.”
- Supports: [PMID:39481209](https://pubmed.ncbi.nlm.nih.gov/39481209/) _(AI re-reading agrees)_ — “FINDINGS: We show that recently identified variants within the facilitatory C2A domain of the protein (L159R, T196K, E209K, E219Q), as well as additional variants in the C2B domain (M303V, S309P, Y365C, G369D), share an underlying pathogenic mechanism, causing a graded and variant-dependent dominant-negative impairment…”
- …and 3 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 35. SYT1-related disorders (Baker-Gordon syndrome) → driven by → Haploinsufficiency (one working copy is not enough)

`disease:SYT1|driven_by|mech:haploinsufficiency`

Level **experimental** · confidence **0.5** · status **contested**

> A minority of published variants in SYT1 act by haploinsufficiency, against the mainstream view for this gene. A structural-variant case argues haploinsufficiency can also cause the disorder. Contradicting or limiting findings are attached as counter-evidence: P401L de-clamps spontaneous/asynchronous release instead of only reducing evoked release. (reported as a gain of function mechanism instead)

- Supports: [PMID:41438914](https://pubmed.ncbi.nlm.nih.gov/41438914/) _(AI re-reading agrees)_ — “The precise pathogenic mechanism of BAGOS is still unclear, with preliminary data favoring a dominant-negative effect, although a previous case presenting a reciprocal translocation disrupting SYT1 supports haploinsufficiency as a possible mechanism.”
- Contradicts or limits: [PMID:38321119](https://pubmed.ncbi.nlm.nih.gov/38321119/) — “This is a novel cellular phenotype, distinct from what was previously found for other SYT1 disease variants, and points to a role for spontaneous and asynchronous release in SYT1-associated neurodevelopmental disorder.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 36. SYT2-related presynaptic congenital myasthenic syndromes → driven by → Dominant-negative effect (the altered protein blocks the good one)

`disease:SYT2|driven_by|mech:dominant-negative`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SYT2-related disorders to dominant-negative effect. Dominant SYT2-CMS proposed to act by a dominant-negative effect on the Ca2+ sensor.

- Supports: [PMID:34037996](https://pubmed.ncbi.nlm.nih.gov/34037996/) _(AI re-reading agrees)_ — “The pathogenesis of the dominant form likely involves a dominant-negative effect due to disruption of the dual function of synaptotagmin as a Ca2+ -sensor and modulator of synaptic vesicle exocytosis.”
- Supports: [PMID:32776697](https://pubmed.ncbi.nlm.nih.gov/32776697/) — “These variants are thought to have a dominant-negative effect on synaptic vesicle exocytosis, although the precise pathomechanism remains to be elucidated.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 37. SYT2-related presynaptic congenital myasthenic syndromes → driven by → Loss of function

`disease:SYT2|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links SYT2-related disorders to loss of function. Biallelic loss of function also causes presynaptic CMS, so the disease is not dominant-only.

- Supports: [PMID:32776697](https://pubmed.ncbi.nlm.nih.gov/32776697/) _(AI re-reading agrees)_ — “Here we report seven patients of five families, with biallelic loss of function variants in SYT2, clinically manifesting with a remarkably consistent phenotype of severe congenital onset hypotonia and weakness, with variable degrees of respiratory involvement.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 38. VAMP2-related disorders → driven by → Gain of function (the protein does too much)

`disease:VAMP2|driven_by|mech:gain-of-function`

Level **experimental** · confidence **0.5** · status **contested**

> A minority of published variants in VAMP2 act by gain of function, against the mainstream view for this gene. Some VAMP2 variants augment spontaneous release rather than only impairing fusion.

- Supports: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “The neurotransmission deficits we observed parallel the symptomatic heterogeneity of the patients, with some variants displaying a disproportionate augmentation of spontaneous neurotransmitter release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 39. VAMP2-related disorders → driven by → Loss of function

`disease:VAMP2|driven_by|mech:loss-of-function`

Level **experimental** · confidence **0.6** · status **supported**

> Published work links VAMP2-related disorders to loss of function. Discovery paper: five de novo VAMP2 variants impairing membrane fusion.

- Supports: [PMID:30929742](https://pubmed.ncbi.nlm.nih.gov/30929742/) — “Here, we report five heterozygous de novo mutations in VAMP2 in unrelated individuals presenting with a neurodevelopmental disorder characterized by axial hypotonia (which had been present since birth), intellectual disability, and autistic features.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 40. VAMP2-related disorders → driven by → Protein destabilization / misfolding

`disease:VAMP2|driven_by|mech:protein-destabilization`

Level **experimental** · confidence **0.5** · status **contested**

> Published work links VAMP2-related disorders to protein destabilization / misfolding. Nine variants differing in SNARE-complex affinity, stability and conformation. Contradicting or limiting findings are attached as counter-evidence: Some VAMP2 variants augment spontaneous release rather than only impairing fusion. (reported as a gain of function mechanism instead)

- Supports: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “Here, we investigated nine synaptobrevin-2 (VAMP2) disease-causing variants and uncovered their specific SNARE complex affinity, stability, and conformational deficits that drive dysregulated neurotransmission.”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “The neurotransmission deficits we observed parallel the symptomatic heterogeneity of the patients, with some variants displaying a disproportionate augmentation of spontaneous neurotransmitter release.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 41. 3,4-Diaminopyridine (amifampridine) → developed for → SYT2-related presynaptic congenital myasthenic syndromes

`therapy:3-4-diaminopyridine|developed_for|disease:SYT2`

Level **clinical** · confidence **0.8** · status **contested**

> 3,4-Diaminopyridine (amifampridine) has been investigated for SYT2-related disorders (stage: clinical).

- Supports: [PMID:26519543](https://pubmed.ncbi.nlm.nih.gov/26519543/) — “Treatment with 3,4-diaminopyridine produced both a clinical benefit and an improvement in neuromuscular transmission.”
- Supports: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) _(AI re-reading agrees)_ — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”
- Contradicts or limits: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) _(AI re-reading agrees)_ — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 42. 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) → developed for → STXBP1-related disorders

`therapy:4-phenylbutyrate|developed_for|disease:STXBP1`

Level **clinical** · confidence **0.8** · status **contested**

> 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) has been investigated for STXBP1-related disorders (stage: clinical).

- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) _(AI re-reading agrees)_ — “We demonstrate that the three chemical chaperones 4-phenylbutyrate, sorbitol, and trehalose reverse the deficits caused by mutations in Munc18-1 in vitro and in vivo in multiple models, offering a novel strategy for the treatment of varied encephalopathies.”
- Supports: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Importantly, 4-phenylbutyrate alone increased γ-amino butyric acid transporter 1 expression and suppressed spike wave discharges in heterozygous knockin mice.”
- Supports: [PMID:42157447](https://pubmed.ncbi.nlm.nih.gov/42157447/) — “RESULTS: PBA restored GABA uptake and GAT-1 surface expression across all variants, and TUDCA mimicked the effects of PBA.”
- Contradicts or limits: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) — “No disease-modifying therapy exists to treat these disorders, and while chemical chaperones have been shown to alleviate neuronal dysfunction caused by missense mutations in Munc18-1, their required high concentrations and potential toxicity necessitate a Munc18-1-targeted therapy.”
- Contradicts or limits: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Although the mechanisms of action for 4-phenylbutyrate are still unclear, with multiple possibly being involved, it is likely that 4-phenylbutyrate can facilitate the forward trafficking of the wildtype γ-amino butyric acid transporter 1 regardless of rescuing the mutant γ-amino butyric acid transporter 1, thus increas…”
- Contradicts or limits: [PMID:39923323](https://pubmed.ncbi.nlm.nih.gov/39923323/) — “Post-treatment EEGs showed a moderate reduction in epileptiform discharges following PBA administration, and patients exhibited improved motor function.”
- …and 1 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 43. scAAV9.P546.SLC6A1 intrathecal gene replacement → developed for → SLC6A1-related disorders

`therapy:aav-slc6a1-gene-replacement|developed_for|disease:SLC6A1`

Level **clinical** · confidence **0.85** · status **supported**

> scAAV9.P546.SLC6A1 intrathecal gene replacement has been investigated for SLC6A1-related disorders (stage: clinical).

- Supports: [NCT07173153](https://clinicaltrials.gov/study/NCT07173153) — “Gene Therapy for SLC6A1 Neurodevelopmental Disorder Phase I/II Intrathecal Gene Delivery Clinical Trial of scAAV9.P546.SLC6A1 for SLC6A1 Neurodevelopmental Disorder This is gene therapy study of an AAV9 vector carrying the SLCA1 gene for SLC6A1 neurodevelopmental disorder.”
- Supports: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Strategies to increase the expression of the wild-type SLC6A1 allele are likely to be beneficial across neurodevelopmental disorders, though the developmental stage and extent of required rescue remain unknown.”
- Supports: [NCT07173153](https://clinicaltrials.gov/study/NCT07173153) — “Confirmation of pathogenic mutation S295L in the SLC6A1 gene”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 44. AAV STXBP1 gene supplementation → developed for → STXBP1-related disorders

`therapy:aav-stxbp1-gene-replacement|developed_for|disease:STXBP1`

Level **clinical** · confidence **0.85** · status **contested**

> AAV STXBP1 gene supplementation has been investigated for STXBP1-related disorders (stage: clinical).

- Supports: [PMID:41883162](https://pubmed.ncbi.nlm.nih.gov/41883162/) _(AI re-reading agrees)_ — “Our AAV-STXBP1 vectors dose dependently rescued disease-associated phenotypes, with ≥44% cortical neuronal transduction needed for phenotypic improvement, setting a potential therapeutic threshold.”
- Supports: [NCT06983158](https://clinicaltrials.gov/study/NCT06983158) — “A Clinical Trial of CAP-002 Gene Therapy in Pediatric Patients With Syntaxin-Binding Protein 1 (STXBP1) Encephalopathy A Phase 1/2a, Open-Label, Multi-Center, Dose-Escalation Trial to Assess Safety, Tolerability, and Efficacy of a Single Dose of CAP-002 Gene Therapy Administered to Pediatric Patients With Syntaxin-Bind…”
- Supports: [NCT06983158](https://clinicaltrials.gov/study/NCT06983158) — “confirmation of a pathogenic or likely pathogenic STXBP1 gene mutation”
- Contradicts or limits: [PMID:41883162](https://pubmed.ncbi.nlm.nih.gov/41883162/) _(AI re-reading agrees)_ — “Currently, there is no clear clinical data or human evidence defining a therapeutic threshold of AAV-mediated STXBP1 expression.”
- Contradicts or limits: [NCT06983158](https://clinicaltrials.gov/study/NCT06983158) — “Stopping rule for study was met”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 45. Acetylcholinesterase inhibitors (e.g. pyridostigmine) → developed for → SYT2-related presynaptic congenital myasthenic syndromes

`therapy:acetylcholinesterase-inhibitor-cms|developed_for|disease:SYT2`

Level **clinical** · confidence **0.8** · status **supported**

> Acetylcholinesterase inhibitors (e.g. pyridostigmine) has been investigated for SYT2-related disorders (stage: clinical).

- Supports: [PMID:32776697](https://pubmed.ncbi.nlm.nih.gov/32776697/) — “Treatment with an acetylcholinesterase inhibitor pursued in three patients showed clinical improvement with increased strength and function.”
- Supports: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) _(AI re-reading agrees)_ — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 46. Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost → developed for → SNAP25-related disorders

`therapy:aminopyridine-presynaptic-boost|developed_for|disease:SNAP25`

Level **clinical** · confidence **0.6** · status **contested**

> Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost has been investigated for SNAP25-related disorders (stage: clinical).

- Supports: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “The I67N variant phenotype could be ameliorated by the clinically approved K+-channel blocker 4-aminopyridine.”
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “Taken together with the phenotypes of previously reported disease-causing SNARE variants, these findings reveal shared patterns of aberrant neurotransmission across different SNAREs, highlighting the necessity for a functional classification of SNAREopathies to develop therapeutic interventions.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 47. Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost → developed for → SYT1-related disorders (Baker-Gordon syndrome)

`therapy:aminopyridine-presynaptic-boost|developed_for|disease:SYT1`

Level **clinical** · confidence **0.8** · status **contested**

> Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost has been investigated for SYT1-related disorders (stage: clinical).

- Supports: [PMID:32906212](https://pubmed.ncbi.nlm.nih.gov/32906212/) — “The clinical response of the patient to 2 years of off-label aminopyridine treatment includes improved emotional and behavioral regulation by parental report, and objective improvement in standardized cognitive measures.”
- Supports: [PMID:32362337](https://pubmed.ncbi.nlm.nih.gov/32362337/) — “These mechanistic studies led to the discovery that a clinically approved K+ channel antagonist is able to rescue the dominant-negative heterozygous phenotype.”
- Supports: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “The I67N variant phenotype could be ameliorated by the clinically approved K+-channel blocker 4-aminopyridine.”
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “Taken together with the phenotypes of previously reported disease-causing SNARE variants, these findings reveal shared patterns of aberrant neurotransmission across different SNAREs, highlighting the necessity for a functional classification of SNAREopathies to develop therapeutic interventions.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 48. Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost → developed for → VAMP2-related disorders

`therapy:aminopyridine-presynaptic-boost|developed_for|disease:VAMP2`

Level **clinical** · confidence **0.6** · status **contested**

> Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost has been investigated for VAMP2-related disorders (stage: clinical).

- Supports: [PMID:32906212](https://pubmed.ncbi.nlm.nih.gov/32906212/) _(AI re-reading agrees)_ — “The clinical response of the patient to 2 years of off-label aminopyridine treatment includes improved emotional and behavioral regulation by parental report, and objective improvement in standardized cognitive measures.”
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “Taken together with the phenotypes of previously reported disease-causing SNARE variants, these findings reveal shared patterns of aberrant neurotransmission across different SNAREs, highlighting the necessity for a functional classification of SNAREopathies to develop therapeutic interventions.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 49. Structure-based pharmacological chaperones for Munc18-1 → developed for → STXBP1-related disorders

`therapy:munc18-1-pharmacological-chaperone|developed_for|disease:STXBP1`

Level **experimental** · confidence **0.6** · status **supported**

> Structure-based pharmacological chaperones for Munc18-1 has been investigated for STXBP1-related disorders (stage: preclinical).

- Supports: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) _(AI re-reading agrees)_ — “Here, we identify two pharmacological chaperones via structure-based drug design, that bind to wild-type and mutant Munc18-1, and revert Munc18-1 aggregation and neuronal dysfunction in vitro and in vivo, providing the first targeted treatment strategy for these severe pediatric encephalopathies.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 50. 3,4-Diaminopyridine (amifampridine) → targets → Ca2+-triggered neurotransmitter exocytosis

`therapy:3-4-diaminopyridine|targets|mech:ca-triggered-exocytosis`

Level **experimental** · confidence **0.8** · status **contested**

> 3,4-Diaminopyridine (amifampridine) is aimed at ca2+-triggered neurotransmitter exocytosis.

- Supports: [PMID:26519543](https://pubmed.ncbi.nlm.nih.gov/26519543/) — “Treatment with 3,4-diaminopyridine produced both a clinical benefit and an improvement in neuromuscular transmission.”
- Supports: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”
- Contradicts or limits: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 51. 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) → targets → GABA reuptake

`therapy:4-phenylbutyrate|targets|mech:gaba-reuptake`

Level **experimental** · confidence **0.5** · status **unverified**

> 4 papers (PMID:35911425, PMID:39923323, PMID:41385967, PMID:41648160) reports that 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) acts on gaba reuptake. Found by automated extraction with OpenAI; not yet reviewed by a person.

- Supports: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “4-Phenylbutyrate increased γ-amino butyric acid uptake in both mouse and human astrocytes and neurons bearing the variants.”
- Supports: [PMID:39923323](https://pubmed.ncbi.nlm.nih.gov/39923323/) — “4-Phenylbutyrate restored GABA uptake, mitigated seizures in SLC6A1 and SLC6A11 microdeletions/3p- syndrome: From cellular models to human patients.”
- Supports: [PMID:41385967](https://pubmed.ncbi.nlm.nih.gov/41385967/) — “We previously showed that 4-phenylbutyrate (PBA), known as a chemical chaperone and histone deacetylase inhibitor, restores GAT-1 function and reduces seizures in both mouse models and humans with SLC6A1 variants.”
- …and 1 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 52. 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) → targets → Protein destabilization / misfolding

`therapy:4-phenylbutyrate|targets|mech:protein-destabilization`

Level **experimental** · confidence **0.8** · status **contested**

> 4-Phenylbutyrate / glycerol phenylbutyrate (chemical chaperone) is aimed at protein destabilization / misfolding.

- Supports: [PMID:30266908](https://pubmed.ncbi.nlm.nih.gov/30266908/) — “We demonstrate that the three chemical chaperones 4-phenylbutyrate, sorbitol, and trehalose reverse the deficits caused by mutations in Munc18-1 in vitro and in vivo in multiple models, offering a novel strategy for the treatment of varied encephalopathies.”
- Supports: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Importantly, 4-phenylbutyrate alone increased γ-amino butyric acid transporter 1 expression and suppressed spike wave discharges in heterozygous knockin mice.”
- Supports: [PMID:42157447](https://pubmed.ncbi.nlm.nih.gov/42157447/) — “RESULTS: PBA restored GABA uptake and GAT-1 surface expression across all variants, and TUDCA mimicked the effects of PBA.”
- Contradicts or limits: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) — “No disease-modifying therapy exists to treat these disorders, and while chemical chaperones have been shown to alleviate neuronal dysfunction caused by missense mutations in Munc18-1, their required high concentrations and potential toxicity necessitate a Munc18-1-targeted therapy.”
- Contradicts or limits: [PMID:35911425](https://pubmed.ncbi.nlm.nih.gov/35911425/) — “Although the mechanisms of action for 4-phenylbutyrate are still unclear, with multiple possibly being involved, it is likely that 4-phenylbutyrate can facilitate the forward trafficking of the wildtype γ-amino butyric acid transporter 1 regardless of rescuing the mutant γ-amino butyric acid transporter 1, thus increas…”
- Contradicts or limits: [PMID:39923323](https://pubmed.ncbi.nlm.nih.gov/39923323/) — “Post-treatment EEGs showed a moderate reduction in epileptiform discharges following PBA administration, and patients exhibited improved motor function.”
- …and 1 more supporting sources in the app

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 53. scAAV9.P546.SLC6A1 intrathecal gene replacement → targets → GABA reuptake

`therapy:aav-slc6a1-gene-replacement|targets|mech:gaba-reuptake`

Level **experimental** · confidence **0.8** · status **supported**

> scAAV9.P546.SLC6A1 intrathecal gene replacement is aimed at gaba reuptake.

- Supports: [NCT07173153](https://clinicaltrials.gov/study/NCT07173153) — “Gene Therapy for SLC6A1 Neurodevelopmental Disorder Phase I/II Intrathecal Gene Delivery Clinical Trial of scAAV9.P546.SLC6A1 for SLC6A1 Neurodevelopmental Disorder This is gene therapy study of an AAV9 vector carrying the SLCA1 gene for SLC6A1 neurodevelopmental disorder.”
- Supports: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Strategies to increase the expression of the wild-type SLC6A1 allele are likely to be beneficial across neurodevelopmental disorders, though the developmental stage and extent of required rescue remain unknown.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 54. scAAV9.P546.SLC6A1 intrathecal gene replacement → targets → Haploinsufficiency (one working copy is not enough)

`therapy:aav-slc6a1-gene-replacement|targets|mech:haploinsufficiency`

Level **experimental** · confidence **0.8** · status **supported**

> scAAV9.P546.SLC6A1 intrathecal gene replacement is aimed at haploinsufficiency.

- Supports: [NCT07173153](https://clinicaltrials.gov/study/NCT07173153) — “Gene Therapy for SLC6A1 Neurodevelopmental Disorder Phase I/II Intrathecal Gene Delivery Clinical Trial of scAAV9.P546.SLC6A1 for SLC6A1 Neurodevelopmental Disorder This is gene therapy study of an AAV9 vector carrying the SLCA1 gene for SLC6A1 neurodevelopmental disorder.”
- Supports: [PMID:38781976](https://pubmed.ncbi.nlm.nih.gov/38781976/) — “Strategies to increase the expression of the wild-type SLC6A1 allele are likely to be beneficial across neurodevelopmental disorders, though the developmental stage and extent of required rescue remain unknown.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 55. AAV STXBP1 gene supplementation → targets → Haploinsufficiency (one working copy is not enough)

`therapy:aav-stxbp1-gene-replacement|targets|mech:haploinsufficiency`

Level **experimental** · confidence **0.8** · status **contested**

> AAV STXBP1 gene supplementation is aimed at haploinsufficiency.

- Supports: [PMID:41883162](https://pubmed.ncbi.nlm.nih.gov/41883162/) — “Our AAV-STXBP1 vectors dose dependently rescued disease-associated phenotypes, with ≥44% cortical neuronal transduction needed for phenotypic improvement, setting a potential therapeutic threshold.”
- Supports: [NCT06983158](https://clinicaltrials.gov/study/NCT06983158) — “A Clinical Trial of CAP-002 Gene Therapy in Pediatric Patients With Syntaxin-Binding Protein 1 (STXBP1) Encephalopathy A Phase 1/2a, Open-Label, Multi-Center, Dose-Escalation Trial to Assess Safety, Tolerability, and Efficacy of a Single Dose of CAP-002 Gene Therapy Administered to Pediatric Patients With Syntaxin-Bind…”
- Contradicts or limits: [PMID:41883162](https://pubmed.ncbi.nlm.nih.gov/41883162/) — “Currently, there is no clear clinical data or human evidence defining a therapeutic threshold of AAV-mediated STXBP1 expression.”
- Contradicts or limits: [NCT06983158](https://clinicaltrials.gov/study/NCT06983158) — “Stopping rule for study was met”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 56. Acetylcholinesterase inhibitors (e.g. pyridostigmine) → targets → Ca2+-triggered neurotransmitter exocytosis

`therapy:acetylcholinesterase-inhibitor-cms|targets|mech:ca-triggered-exocytosis`

Level **experimental** · confidence **0.8** · status **supported**

> Acetylcholinesterase inhibitors (e.g. pyridostigmine) is aimed at ca2+-triggered neurotransmitter exocytosis.

- Supports: [PMID:32776697](https://pubmed.ncbi.nlm.nih.gov/32776697/) — “Treatment with an acetylcholinesterase inhibitor pursued in three patients showed clinical improvement with increased strength and function.”
- Supports: [PMID:32250532](https://pubmed.ncbi.nlm.nih.gov/32250532/) — “These findings were reminiscent, but not identical to those seen in the Lambert-Eaton myasthenic syndrome. 3,4 diaminopyridine and pyridostigmine were effective to ameliorate muscle fatigue, but albuterol was ineffective.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 57. Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost → targets → Ca2+-triggered neurotransmitter exocytosis

`therapy:aminopyridine-presynaptic-boost|targets|mech:ca-triggered-exocytosis`

Level **experimental** · confidence **0.8** · status **contested**

> Aminopyridines (4-AP / 3,4-DAP) as a presynaptic boost is aimed at ca2+-triggered neurotransmitter exocytosis.

- Supports: [PMID:32906212](https://pubmed.ncbi.nlm.nih.gov/32906212/) _(AI re-reading agrees)_ — “The clinical response of the patient to 2 years of off-label aminopyridine treatment includes improved emotional and behavioral regulation by parental report, and objective improvement in standardized cognitive measures.”
- Supports: [PMID:32362337](https://pubmed.ncbi.nlm.nih.gov/32362337/) — “These mechanistic studies led to the discovery that a clinically approved K+ channel antagonist is able to rescue the dominant-negative heterozygous phenotype.”
- Supports: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “The I67N variant phenotype could be ameliorated by the clinically approved K+-channel blocker 4-aminopyridine.”
- Contradicts or limits: [PMID:40181518](https://pubmed.ncbi.nlm.nih.gov/40181518/) — “These phenotypes were distinct from those of human neurons differentiated from hiPSCs originating from a patient carrying the V48F variant, which displayed an increase in spontaneous release.”
- Contradicts or limits: [PMID:41166419](https://pubmed.ncbi.nlm.nih.gov/41166419/) — “Taken together with the phenotypes of previously reported disease-causing SNARE variants, these findings reveal shared patterns of aberrant neurotransmission across different SNAREs, highlighting the necessity for a functional classification of SNAREopathies to develop therapeutic interventions.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 58. Structure-based pharmacological chaperones for Munc18-1 → targets → Protein destabilization / misfolding

`therapy:munc18-1-pharmacological-chaperone|targets|mech:protein-destabilization`

Level **experimental** · confidence **0.6** · status **supported**

> Structure-based pharmacological chaperones for Munc18-1 is aimed at protein destabilization / misfolding.

- Supports: [PMID:33332765](https://pubmed.ncbi.nlm.nih.gov/33332765/) _(AI re-reading agrees)_ — “Here, we identify two pharmacological chaperones via structure-based drug design, that bind to wild-type and mutant Munc18-1, and revert Munc18-1 aggregation and neuronal dysfunction in vitro and in vivo, providing the first targeted treatment strategy for these severe pediatric encephalopathies.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---

## 59. UNC13A cryptic-exon splice-switching ASO → targets → Synaptic vesicle priming

`therapy:unc13a-splice-switching-aso|targets|mech:synaptic-vesicle-priming`

Level **experimental** · confidence **0.6** · status **supported**

> UNC13A cryptic-exon splice-switching ASO is aimed at synaptic vesicle priming.

- Supports: [PMID:38979232](https://pubmed.ncbi.nlm.nih.gov/38979232/) — “Antisense oligonucleotides targeting the UNC13A cryptic exon robustly rescue UNC13A protein levels and restore normal synaptic function, providing a potential new therapeutic approach for ALS and other TDP-43-related disorders.”

- [ ] Confirm  - [ ] Correct  - [ ] Reject

Note: 

---
