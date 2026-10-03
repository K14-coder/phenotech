# DisMech ingest: agent report

This report covers the ingest of the Monarch Initiative's DisMech (Disorder Mechanisms Knowledge Base)
into the global disease index. DisMech gives about 3,200 diseases an expert-curated mechanism
"pathograph" (a causal graph from gene to phenotype), with verbatim evidence quotes.

- Generated: 2026-10-04.
- Source: https://github.com/monarch-initiative/dismech (BSD-3-Clause), shallow clone in
  `data/raw/downloads/dismech` (gitignored).
- Pinned commit: `332cbfdc00c4d49d5c9ed8aa45b14abb20e2f1bb`.

```bash
uv run --with pyyaml python3 pipeline/derive/dismech.py   # ~15 s; step 8/8 of pipeline/derive/run.sh
```

Code is in `pipeline/derive/dismech.py` (stdlib + pyyaml). `run.sh` clones DisMech if it is missing,
and `--refresh` pulls the latest. Schema and UI guidance are in `data/derived/global/README.md`, in the
"DisMech layer" section.

## Outputs

| File | Size | What it is |
|---|---|---|
| `data/derived/global/dismech/<0..63>.json` | 30.6 MB in 64 shards (6.4 MB gzip). Max 1.07 MB / 219 KB gz, median 433 KB / 92 KB gz, min 27 KB | The pathograph per MONDO id: ordered steps, edges, chains, genes, treatments, hypotheses, open questions, counts, attribution |
| `data/derived/global/dismech_evidence/<0..63>.json` | 90.9 MB in 64 shards (22.1 MB gzip). Max 3.1 MB / 759 KB gz, median 1.24 MB / 302 KB gz | Every carried evidence item verbatim, plus long prose (descriptions, rationales, notes) and a shard-level `refs` map `{ref: [title, url]}` |
| `data/derived/global/dismech_index.json` | 222 KB | 3,217 rows: MONDO id, name, mechanism steps, steps, evidence, refutes, entries, `in_index` |
| `data/derived/global/index_extra.json` | 111 KB | 789 DisMech MONDO ids that `index.json` lacks, in `index.json`'s own row format (`gsrc = 3`) |
| `data/derived/global/dismech_atlas_links.json` | 63 KB | 72 MONDO links to 32 of 45 atlas umbrellas, plus 16 gene-only leads |
| `data/derived/global/meta.json` → `dismech` | — | Commit, attribution text, all counts, shard sizes, the 52 files without MONDO, and examples of dangling targets |

Both shard sets use the **same `djb2(id) % 64`** as `neighbours/` and `mechanism/`, keyed on the MONDO
id.

**Why two shard sets.** A single shard set came to 128 MB (max 4.4 MB per shard), which is too heavy
for a page load. The pathograph (`dismech/`) is enough to draw the mechanism and badge each node with
its evidence count (`ev: [items, refutes, no_evidence]`). The quotes (`dismech_evidence/`) are fetched
only when a reader opens a node. The detail record is keyed by the object's path in the core record
(`steps/3`, `edges/5`, `treatments/2/targets/0`…).

**Not modified:** `index.json`, `neighbours/`, `mechanism/`, `web/`, `data/curated/`. The two runs in
this session each read `index.json` and wrote only new files and `meta.dismech`. Another agent rewrote
`index.json`, `meta.json` and the README at 00:29 while this ran. Its changes are intact: the README
section was appended and the meta section is set by key.

I made one line of change outside the new files. `global_index.py` rebuilds `meta.json` and kept only
the `mechanism` and `atlas_flags` sections, so `"dismech"` is now added to that preserved-keys tuple.
Without it, a standalone `global_index.py` run would silently drop `meta.dismech`.

## Counts

| | |
|---|---|
| DisMech disorder YAML files | **3,290** |
| Records ingested (anchored to a MONDO `disease_term`) | **3,238**, under **3,217 MONDO ids**. 14 ids carry 2+ entries, e.g. `MONDO:0014590` holds both SNAP25-DEE and CMS18 |
| Skipped: no MONDO term, no exactMatch mapping | 52 (toxins, pain, "ageing", some gene-named DisMech-only concepts). Listed in `meta.dismech.no_mondo_files` |
| Already in `index.json` / added via `index_extra.json` | 2,428 / 789 |
| Steps (pathograph nodes) | **52,680**: 22,650 mechanism (pathophysiology) steps, 24,168 phenotype, 5,003 gene, 954 environmental |
| Step type | 8,264 cellular, 5,505 molecular, 3,861 tissue, 2,291 organism, 2,634 unspecified |
| Step type basis | 14,493 from DisMech `biological_scale`, 30,030 from the section, 5,523 inferred by us, 2,634 none |
| Causal edges | **52,548**: 5,429 gene → mechanism by DisMech's rule and 407 added by us (name match, flagged) |
| Dangling `downstream` targets (DisMech defects, dropped) | 509 |
| Records with at least one causal chain / with a cycle | 3,183 / 63. The longest chain has a median of 6 steps (max 15) |
| **Evidence items carried** | **143,102**, holding **143,089 snippets** (13 items have no snippet). **All 143,089 were re-checked verbatim against the parsed source YAML: 0 mismatches** |
| supports | **SUPPORT 141,197 · REFUTE 1,590 · NO_EVIDENCE 315** |
| UI flags | `refute` 1,590 (counter-evidence), `no_evidence` 315, `indirect` 5,934 (DisMech's replacement for the retired `PARTIAL`) |
| Records with at least one refuting item | 714. Most refutes: Alzheimer disease 25, Brugada syndrome 21, familial nonmedullary thyroid carcinoma 19, inclusion body myositis 15, CANVAS 14 |
| Whole DisMech corpus (all sections) | 227,012 evidence items, 226,979 snippets. SUPPORT 224,393 · REFUTE 2,022 · NO_EVIDENCE 597 |
| Reference types carried | PMID 130,220 · ORPHA 5,081 · url 3,671 · DOI 2,701 · CGGV 974 · clinicaltrials 262 · PPR 110 · others < 30. Only 4 `STRCHIVE:` refs have no URL |
| Genes / treatments | 7,240 gene records / 13,829 treatments |

## Schema mapping (DisMech LinkML → our records)

The DisMech schema is in `src/dismech/schema/dismech.yaml`, where the `Disease` class is the root.
Edges are built by `src/dismech/graph.py`. I read the schema and 10 diverse disorders: STXBP1
encephalopathy, Dravet syndrome, SNAP25 encephalopathy, CMS18, Gaucher, Asthma, attenuated MPS I (no
MONDO), adult-onset SMA (has refutes), Alzheimer disease and Arsenic poisoning (environmental).

| DisMech | Ours |
|---|---|
| `disease_term.term.id` (MONDO) | the shard key `mondo`. `mappings.mondo_mappings` with `skos:exactMatch` is the fallback (used 0 times) |
| `name`, `synonyms`, `parents`, `category`, `categories`, `classifications`, `inheritance[]` | record fields of the same names. `classifications` descriptors are simplified to `{id,label}` |
| `pathophysiology[]` (node: `name`, `description`, `biological_scale`, `role`, `conforms_to`, `cell_types`/`biological_processes`/`molecular_functions`/`locations`/`chemical_entities`/`genes`… as `{preferred_term, term:{id,label}, modifier}`, `evidence[]`, `downstream[]`) | `steps[]` with `sec:"pathophysiology"`. Ontology terms go to `[id, slot, modifier]` and labels to the shard dict `t` |
| `downstream[]` `{target (bare name, verbatim match), causal_link_type, intermediate_mechanisms, description, evidence}` | `edges[]` `{s, t, link, intermediate}`. Description and evidence go to the detail shard |
| `phenotypes[]` (`phenotype_term` HP, `frequency`, `sequelae[]`) | `steps[]` of type `phenotype` when an edge reaches them. Otherwise `unlinked_phenotypes` as `[name, HP]` |
| `environmental[].influences_mechanisms[]` (`environmental_effect`) | `steps[]` of type `environmental` + edges with `predicate:"influences"` |
| `genetic[]` (`gene_term` hgnc, `association`, `relationship_type`, `variant_origin`, `gene_disease_validity`) | `genes[]`. `hgnc` is normalised to `HGNC:`. `contributes` and the gene → mechanism link follow DisMech's `graph.py` |
| `treatments[]` (`therapeutic_modality`, `treatment_term` NCIT + `therapeutic_agent` CHEBI/NCIT, `regimen_term`, `target_mechanisms[]`) | `treatments[]` `{modality, action, agents, regimen, targets}` |
| `mechanistic_hypotheses[]`, `discussions[]` (KNOWLEDGE_GAP / CONTROVERSY / HUMAN_MODEL_MISMATCH / EMERGING_HYPOTHESIS) | `hypotheses[]`, `open_questions[]`. Contested mechanisms live here |
| `EvidenceItem` `{reference, reference_title, supports, evidence_source, snippet, explanation, directness, quote_role}` | `{ref, supports, source, snippet, explanation, directness?, quote_role?, flag?}`. Title and URL go in shard `refs[ref]` |

How DisMech's evidence model maps onto ours:

| DisMech | Ours (SCHEMA.md) |
|---|---|
| `supports: SUPPORT` | evidence |
| `supports: REFUTE` | our `counter_evidence` |
| `snippet` | our verbatim quote |
| `evidence_source` | close to our `evidence_level`: HUMAN_CLINICAL ~ clinical, MODEL_ORGANISM / IN_VITRO ~ experimental, COMPUTATIONAL ~ inferred |

DisMech has no per-claim confidence score. None was invented.

## Example (STXBP1 encephalopathy, `MONDO:0012812`, bucket 58)

The record has 10 steps, 10 edges and 24 evidence items, with 0 refutes. Its main chain:

**STXBP1** (gene, HGNC:11444)
→ *STXBP1 haploinsufficiency and Munc18-1 deficiency* (GO:0099504 synaptic vesicle cycle, ABNORMAL; neuron)
→ *Impaired syntaxin-1 chaperoning and SNARE-mediated vesicle fusion* (GO:0099502, GO:0016079, DECREASED)
→ *Reduced neurotransmitter release* (GO:0007269 DECREASED; glutamatergic and GABAergic neurons)
→ *Cortical E/I imbalance and seizures* → **Epilepsy** (HP:0200134), and
→ *Impaired synaptic network development* → **Severe global developmental delay**, **Autistic behaviour**,
**Movement disorder**.

The gene → trigger edge is one of ours: the gene symbol appears in the root node's name. DisMech itself
leaves `STXBP1` unlinked because the node carries no gene descriptor, so the edge is drawn dashed. An
example evidence item on the trigger:

`PMID:18469812` SUPPORT HUMAN_CLINICAL: "These findings suggest that haploinsufficiency of STXBP1 causes
EIEE."

A refute example: on adult-onset autosomal dominant SMA, `steps/2`, PMID:24252306, MODEL_ORGANISM. Its
DisMech explanation says the evidence "directly refutes a simple aggregate-causes-degeneration reading".

## Atlas cross-links (`dismech_atlas_links.json`)

The join rule matches the atlas's MONDO xrefs, including `attrs.subtypes[].MONDO`, and follows obsolete
→ `replaced_by`. That gives 72 links over 32 of 45 umbrellas:

- **36 `single_gene`**: STXBP1, SNAP25 (×2), SYT1, SYT2 (CMS7), STX1B, CPLX1, VAMP2, UNC13A (×2),
  SLC6A1, KCNQ2, KCNT1 (×2), SCN2A, SCN8A, GRIN2B (×2), SYNGAP1, CACNA1A (SCA6), CBL, NF1 (×2), RAF1
  (DCM 1NN), GAA (×3), GALC, HEXA, IDS, IDUA, CLN3, TPP1, SMPD1 (×2), GLA;
- **16 `multi_gene_lists_gene`**: Dravet → SCN1A and SCN2A, GEFS+, Costello (HRAS + NRAS), benign
  familial infantile epilepsy, EIMFS…;
- **20 `group_gene_not_listed`**: clinical groups our nodes list as subtypes (Lennox-Gastaut,
  infantile spasms, undetermined EOEE…) whose DisMech entry does not name the gene. Hide these on gene
  pages.

The 13 umbrellas with no MONDO link are ARSA, BRAF, GBA1, KRAS, LZTR1, MAP2K1, NPC1, NSF, PTPN11, RIT1,
SHOC2, SOS1 and STX1A. DisMech curates most of them at the **grouping** level (Gaucher disease
`MONDO:0018150`, Niemann-Pick C `MONDO:0018982`, MLD `MONDO:0018868`, cardiofaciocutaneous syndrome,
Noonan syndrome with multiple lentigines), while our xrefs name the numbered subtypes. Those 16 cases
are listed under `gene_only` as leads. The same list flags CDKL5 deficiency disorder `MONDO:0100039`
and GLUT1 deficiency syndrome `MONDO:0000188`, which look like **missing xrefs on our CDKL5 and SLC2A1
nodes**. They need a person to check them before anything in `data/curated/` changes.

## DisMech vs our atlas: STXBP1, Dravet/SCN1A, SNAP25

### STXBP1 (DisMech `STXBP1_Encephalopathy`, MONDO:0012812)

The two sources share 3 PMIDs: 18469812, 29538625 and 30266908.

**Agreements**

- **Haploinsufficiency is the main mechanism.** DisMech's trigger node quotes the 2008 discovery paper
  (PMID:18469812). Our `disease:STXBP1 → mech:haploinsufficiency` edge rests on the same paper plus
  26280581, 29538625 and 32643187.
- **Destabilised missense variants converge on loss of dose.** DisMech cites the thermolabile mutant
  from PMID:18469812. Our `vg:STXBP1:missense → mech:protein-destabilization` is supported at 0.8.
- **The dominant-negative question is open in both.** DisMech records a CONTROVERSY (OPEN):
  "haploinsufficiency vs dominant-negative". It cites PMID:30266908 (aggregates co-deplete wild-type
  Munc18-1) against PMID:29538625 (instability plus haploinsufficiency explain the disease). We mark
  both `haploinsufficiency` and `dominant-negative` as *contested* with counter-evidence, citing the
  same two papers. The two curations reach the same verdict independently.

**Differences**

- **Gain of function.** We carry a contested GoF edge (PMID:31855252, a recessive homozygous variant)
  and an unverified OpenAI-extracted LoF edge (PMID:41883162). DisMech has neither.
- **Downstream mechanism.** DisMech continues the chain past the synapse: reduced release, then cortical
  E/I imbalance and seizures, and impaired network development, then ID, autism and movement disorder.
  It also states that ID severity does not track seizure severity (PMID:26865513). Our mechanism nodes
  stop at GO processes, and we do not model this seizure/cognition dissociation.
- **GO terms.** The biology overlaps but no GO id is identical:
  - DisMech: GO:0099504, GO:0099502, GO:0016079, GO:0007269, GO:0007268;
  - ours: GO:0035493 (SNARE complex assembly), GO:0048791, GO:0031629, GO:0016082 (priming).
  DisMech does not annotate Munc18-1's priming role.

### Dravet syndrome / SCN1A (DisMech `Dravet_syndrome`, MONDO:0100135)

The link reaches our `disease:SCN1A` only through the obsolete xref MONDO:0011794 → `replaced_by`. The
two sources share 2 PMIDs: 32848094 and 35696452.

**Agreements**

- **Heterozygous SCN1A loss of function is the cause.** DisMech says this explicitly (PMID:21463282;
  ClinGen Definitive, AD). We have `mech:loss-of-function` (0.8) and `mech:haploinsufficiency` (0.6).
- **Gain of function is a different disease.** DisMech's EMERGING_HYPOTHESIS "opposite-direction
  disease" attributes GoF to FHM3 and early-infantile DEE, not to Dravet (PMID:35696452). Our GoF edge
  ("a minority of variants", PMID:35696452, 36636894) sits on the **SCN1A umbrella**, which includes
  DEE6B and FHM3, not on Dravet. The two are consistent once scoped, but a Dravet page must not inherit
  the umbrella's GoF edge.

**DisMech adds, and we lack**

- the cell-type locus: Nav1.1 loss in GABAergic, parvalbumin-positive interneurons, leading to E/I
  imbalance;
- an astrocyte Ca²⁺ dysregulation node (PMID:36610382);
- a SUDEP chain: postictal serotonergic dysfunction → impaired CO₂ chemoreception → hypoventilation →
  SUDEP (PMID:37160367, 30756391). Fenfluramine's possible serotonergic SUDEP effect is posed as an open
  question;
- 7 open questions in all, including a human-model mismatch on Scn1a+/- mouse background effects.

**Disagreements**

- **Gene scope.** DisMech's Dravet lists 11 genes: SCN1A first, plus SCN1B, SCN2A, GABRA1, GABRG2,
  PCDH19, **STXBP1**, HCN1, SCN9A (candidate), and CHD2 and DEPDC5 (modifiers). Our atlas has no
  STXBP1 → Dravet link. DisMech's "Rare Pathogenic Mutations" claim for STXBP1 in Dravet is a lead to
  check before any SNARE → Dravet bridge is drawn.
- **Identity.** Our SCN1A and SCN2A nodes still carry the obsolete Dravet id MONDO:0011794. The global
  index already resolves it to MONDO:0100135, so adding MONDO:0100135 to the xrefs is recommended.

### SNAP25 (two DisMech entries on MONDO:0014590: `Congenital_Myasthenic_Syndrome_18` and `SNAP25_Encephalopathy`)

**Agreements**

- **Dominant-negative.** The DisMech CMS18 entry's trigger is "Dominant-Negative Disruption of the
  SNARE Complex". It cites PMID:25381298 and PMID:29355968: co-transfected wild-type plus I67N exocytoses
  at the mutant-only rate. Our `disease:SNAP25 → mech:dominant-negative` (0.6) agrees, from a different
  paper (PMID:41579375).
- **Gain of function in part.** We carry GoF at 0.6 (PMID:33147442, augmented spontaneous release).
  DisMech raises GoF features only inside an open question (PMID:38411501: lower fusion energy barrier,
  higher release probability) and not in the chain.

**Disagreements**

- **PMID:25381298 is read two ways.** Our `vg:SNAP25:missense → mech:loss-of-function` edge cites it
  (OpenAI-extracted, *unverified*), while DisMech reads the same paper as **dominant-negative**. Our LoF
  edge should be reviewed. The co-transfection result argues for dominant-negative over simple loss of
  function.
- **Haploinsufficiency.** Our truncating and splice → haploinsufficiency edges are inferred (0.45,
  unverified). DisMech's SNAP25-DEE entry asserts no mechanism class: it leaves LoF vs dominant-negative
  vs GoF as an open KNOWLEDGE_GAP.

**Identity**

- DisMech uses MONDO:0014590 for both a CMS18 entry and a SNAP25-DEE entry. The DEE entry lists "CMS18
  (formerly)" and DEE117 as synonyms, and DisMech asks whether the two are one disorder. Our SNAP25 node
  labels the id "congenital myasthenic syndrome 18" only.
- The DisMech chain covers both the neuromuscular arm (reduced evoked quantal release, then fatigable
  weakness) and the CNS arm (cortical hyperexcitability, ataxia, ID). We do not model that split.

**Overall.** On the SNARE slice the two curations agree on the primary mechanism class every time. They
differ in two ways. DisMech carries the causal chain down to phenotypes (and to SUDEP), with explicit
open questions. Our atlas is more granular about variant-class mechanisms and minority GoF claims.
DisMech is the better source for "how the mechanism produces the symptoms"; ours is better for "which
variants do what".

## Caveats

- **Carried evidence is scoped to the pathograph.** That means steps, edges, genes, treatments and
  their targets, hypotheses and discussions: 143,102 items. The other 83,910 corpus items stay in
  DisMech, reachable through `attribution.file_url`. They sit on unlinked phenotypes, diagnosis,
  prevalence, inheritance, biochemistry, trials, datasets, models and differentials.
- **Snippets are copied exactly as the YAML parser returns them.** Folded `>-` scalars join lines with
  single spaces, which is how DisMech's own validator reads them. They are checked only against DisMech.
  Whether each quote really appears in the cited paper rests on DisMech's reference validator, not on
  us.
- **Chain order is a topological sort, not a DisMech field.** Step `type` is ours where DisMech gives no
  `biological_scale` (`type_basis: inferred:*`). The 407 name-match gene edges are ours and marked
  `inferred`.
- **DisMech's own defects are counted, not fixed.** 509 dangling causal targets and 63 cyclic graphs.
  About half of DisMech phenotypes have no incoming causal edge; they go to `unlinked_phenotypes`.
- **MONDO anchors can be groupings or shared.** Examples: SLC6A1-related disorder anchored on "epilepsy
  with myoclonic atonic seizures", and two entries on MONDO:0014590. `index_extra.json` genes
  (`gsrc 3`) include risk genes for complex diseases (e.g. PCSK9 for abdominal aortic aneurysm), so
  search matches on them are weaker than OMIM `gsrc 1`.
- **Sizes.** The evidence shards are large (max 3.1 MB raw, 759 KB gzip). Serve them compressed and
  fetch them only on demand.

## Attribution text

For the UI, on every DisMech panel and in tooltips:

> Mechanism pathograph from DisMech, the Disorder Mechanisms Knowledge Base of the Monarch Initiative
> (https://dismech.monarchinitiative.org), BSD-3-Clause. Curated independently of this atlas; evidence
> snippets are quoted verbatim from DisMech.

Link each record's `attribution.page_url` (the DisMech page) and `attribution.file_url` (the YAML on
GitHub at the pinned commit).

For the project README, under data sources:

> **DisMech** (Monarch Initiative), https://github.com/monarch-initiative/dismech, BSD-3-Clause:
> expert-curated disease-mechanism pathographs with verbatim, referenced evidence for 3,217 MONDO
> diseases, pinned at commit `332cbfdc00c4d49d5c9ed8aa45b14abb20e2f1bb`, by the DisMech contributors
> (Monarch Initiative). Redistributed under the BSD 3-Clause licence, which requires keeping its
> copyright notice, conditions and disclaimer (see `data/raw/downloads/dismech/LICENSE`).

Note: at this commit DisMech's `LICENSE` file still carries the template line "Copyright (c) 2025 My
Name". The full BSD-3 text now ships next to the derived files as
`data/derived/global/DISMECH_LICENSE.txt`. The copyright holder should be credited as "the DisMech
contributors / Monarch Initiative" until upstream fixes the placeholder. Nobody has asked them yet.
