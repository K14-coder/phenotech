# Global disease index

Every rare disease with HPO phenotype annotations or a gene association is findable in this
folder, not only the 11 diseases the atlas maps. Typing "huntingtons" now reaches a page for
Huntington disease. That page is honest: it shows the disease's distinctive features, its phenotype
neighbours and how far it sits from the mapped SNAREopathy family. It does not show "No match".

**Caveat, shown on every page:** *phenotype similarity only; no evidence curation; mechanism not
assessed.* Nothing in this folder is a curated claim. Diseases outside the 11 have no evidence
edges, quotes or confidence scores. They have only computed phenotype similarity and links out.

Built by `pipeline/derive/global_index.py`. Run it alone with
`uv run --with numpy --with scipy python3 pipeline/derive/global_index.py` (about 15 s), or as part
of `pipeline/derive/run.sh`.

| File | Size | Load |
|---|---|---|
| `index.json` | 1.6 MB raw | once, for search |
| `neighbours/<bucket>.json` | 64 shards, 14.3 MB total, max 441 KB | lazily, one shard per disease page |
| `meta.json` | 28 KB | once: caveat text, URL templates, threshold, versions, `mechanism` section |
| `mechanism/<bucket>.json` | 64 shards, 6.1 MB total, max 224 KB | lazily: mechanism class, pathways, cluster for one disease |
| `clusters.json` | 0.6 MB | once, for a "mechanism families" view: 225 clusters with labels and members |

Sources:

- MONDO `mondo-base.obo`, release 2026-09-01;
- HPO `phenotype.hpoa` 2026-09-02 and `hp.obo` 2026-09-01;
- `genes_to_disease.txt`.

All four files are in `data/raw/downloads/`, which is gitignored.

## `index.json`: search

```json
{"f": ["id","name","syn","omim","orpha","genes","gsrc","n","atlas"],
 "rows": [["MONDO:0007739","Huntington disease",["HD","Huntington chorea","Huntington's chorea","Huntington's Disease"],"143100","399","HTT",1,58,0], ...]}
```

Each row is an array in the order given by `f`. The file holds 11,456 rows, sorted by name.

| key | meaning |
|---|---|
| `id` | MONDO id. When MONDO has no match it is the native `OMIM:`/`ORPHA:` id (122 rows). |
| `name` | MONDO label, or the HPO/Orphanet name for a native id. |
| `syn` | Up to 4 MONDO **EXACT** synonyms. Abbreviations come first. Case duplicates are dropped, and so are "modifier of"/"susceptibility" variants and synonyms over 60 characters. |
| `omim` | Comma-separated OMIM numbers, e.g. `"143100"`. Empty string if there are none. |
| `orpha` | Comma-separated Orphanet numbers. Empty string if there are none. |
| `genes` | Comma-separated gene symbols. |
| `gsrc` | Where the genes come from. `1` = OMIM/mim2gene MENDELIAN genes. `2` = Orphanet genes only; `genes_to_disease.txt` does not carry Orphanet's association type, so these can include modifier genes. `0` = no gene. POLYGENIC associations are never listed. |
| `n` | Number of distinct annotated HPO phenotype terms (aspect P). Below 5 means there are no neighbours. |
| `atlas` | `"disease:<GENE>"` if this entry is one of the 11 mapped umbrella diseases, otherwise `0`. 14 rows are set. |

How identities merge:

- OMIM and ORPHA ids for the same disease become **one** row through MONDO xrefs carrying
  `source="MONDO:equivalentTo"`.
- An id whose only MONDO match is obsolete follows `replaced_by`. That is how ORPHA:33069 Dravet
  syndrome reaches MONDO:0100135.
- Four ids merge by an exact, unique name match.
- 316 Orphanet ids are listed only in `genes_to_disease.txt`, with no name anywhere. They are left
  out because a row without a name cannot be searched.

`atlas` is set only for the atlas's curated profile entities, or for single-gene entries of a slice
gene. Multi-gene clinical groups never route to a gene page, even if the graph lists them as a
subtype. Examples are GEFS+ and autosomal dominant non-syndromic intellectual disability.

**Search recipe** (tested on huntingtons, Huntington's, cystic fibrosis, duchenne, dravet, rett,
angelman, fragile x, marfan, sma):

1. Normalise the query and every name and synonym the same way. Lowercase, delete `'` and `’`
   (delete, don't replace, so "Huntington's" becomes "huntingtons"), then turn every other run of
   non-alphanumerics into one space.
2. Rank matches in this order: exact match, then prefix, then word-prefix (`" " + query` occurs
   inside `" " + label`).
3. Break ties by higher `n`.
4. Also match `genes` and the `omim`/`orpha` numbers, so "STXBP1" or "143100" works.

If `atlas` is not `0`, route to the existing atlas disease page. Otherwise open the global page.

## `neighbours/<bucket>.json`: one disease page

### Shard function (port exactly)

The shard is `bucket = djb2(id) % 64`, with the file at `neighbours/<bucket>.json`. `id` is the row
id string, e.g. `"MONDO:0007739"`. Bucket numbers are decimal and unpadded: `0.json` … `63.json`.

djb2 is the classic version: seed 5381 and `h = h * 33 + charCode`, reduced to an **unsigned 32-bit**
value after every character. The ids are ASCII, so UTF-16 code units and code points agree.

```ts
function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 33) + s.charCodeAt(i)) >>> 0;
  return h;
}
const bucket = (id: string) => djb2(id) % 64;
```

```python
def djb2(s):
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h
```

Test vectors. Python and Node give identical results:

| id | djb2 | bucket |
|---|---|---|
| `MONDO:0007739` (Huntington disease) | 2020644582 | 38 |
| `MONDO:0009061` (cystic fibrosis) | 2020708924 | 60 |
| `MONDO:0010679` (Duchenne muscular dystrophy) | 2021577987 | 3 |

### Shard schema

```json
{"bucket": 38,
 "t": {"HP:0002340": ["Caudate atrophy", 6.12], ...},
 "d": {"MONDO:0007739": {
     "nb":    [["MONDO:0011671", 0.5567, 1.0, ["HP:0002340","HP:0000746","HP:0000751"]], ...],
     "own":   ["HP:0031473", ...],
     "inh":   ["HP:0000006"],
     "atlas": [["disease:UNC13A", 0.1518, 0.8039, false, ["HP:0003324","HP:0002171","HP:0000737"]], ...],
     "far":   true }}}
```

| key | meaning |
|---|---|
| `t` | Shard-local term dictionary: HPO id → `[label, IC]`. Every HPO id in the shard resolves here. Inheritance terms have IC 0 because they are not phenotypes. |
| `nb` | Top 10 phenotype neighbours, each as `[id, score, percentile, shared]`. `score` is the IC-weighted cosine (0–1). `percentile` is the share of the 8,696-disease comparison pool that scores lower against this disease. `shared` holds up to 3 shared terms, most informative first, never an ancestor of a term already listed. A term is **distinctive** when IC ≥ 4.0, the same cut-off as the atlas. Look up the neighbour's name in `index.json`. |
| `own` | The disease's own top 8 most informative annotated phenotypes, with no ancestor/descendant duplicates. |
| `inh` | HPO inheritance terms (aspect I), e.g. HP:0000006 Autosomal dominant. An empty list means none annotated. |
| `atlas` | Similarity to the mapped diseases: the top 3 of the 10 that have an HPO profile (STX1A has none). Each is `[atlas id, cosine, percentile within that atlas disease's background, near, shared]`. `near` is cosine ≥ 0.2454 (see below). |
| `far` | `true` when no atlas disease is `near`. Show `meta.far_text`. |

Only diseases with **≥ 5** annotated terms have an entry: 8,787 of them. For any other row, say
"too few annotated phenotypes to compare" and still show the links. QTL and susceptibility loci can
have their own page but are never listed as anyone's neighbour.

## Mechanism layer: `mechanism/<bucket>.json`, `clusters.json`, `meta.mechanism`

This layer is new, and it is purely **additive**: `index.json` and `neighbours/` keep their format.
It is built by `pipeline/derive/mechanism_index.py`, which runs after `global_index.py`. Use the
**same** `bucket(id)` as for `neighbours/`.

```json
{"bucket": 38,
 "p": {"R-HSA-264642": "Acetylcholine Neurotransmitter Release Cycle", ...},
 "d": {"MONDO:0012812": {
   "mechanisms": [{"class": "mech:loss-of-function", "source": "G2P", "label_verbatim": "loss of function",
                   "url": "https://www.ebi.ac.uk/gene2phenotype/lgd/G2P01128", "confidence": "definitive",
                   "allelic_requirement": "monoallelic_autosomal", "mechanism_support": "inferred",
                   "variant_consequence": "absent gene product", "gene": "STXBP1", "panels": "DD",
                   "joined_by": "MONDO", "record": "G2P01128"},
                  {"class": "mech:haploinsufficiency", "source": "ClinGen dosage",
                   "label_verbatim": "Sufficient Evidence for Haploinsufficiency",
                   "url": "https://search.clinicalgenome.org/kb/gene-dosage/HGNC:11444",
                   "confidence": "HI score 3 (sufficient evidence)", "gene": "STXBP1", "joined_by": "HI disease id"}],
   "validity":   [{"classification": "Definitive", "moi": "AD", "gene": "STXBP1", "url": "https://search.clinicalgenome.org/kb/gene-validity/CGGV:...",
                   "date": "2017-10-20", "gcep": "Epilepsy Gene Curation Expert Panel", "joined_by": "..."}],
   "pathways":   ["R-HSA-264642", "R-HSA-181430"],
   "cluster_id": "MC0005",
   "mechanism_neighbours": [{"id": "MONDO:0014590", "gene": "SNAP25", "shared_pathways": ["R-HSA-112310", ...],
                             "shared_mechanisms": ["mech:loss-of-function"], "gene_edge_weight": 0.468,
                             "phenotype_cosine": 0.053}, ...]}}}
```

Every key is optional. A disease is present only if it has at least one of them.

| key | meaning |
|---|---|
| `p` | Shard-local Reactome names. The URL is `https://reactome.org/content/detail/<id>`. |
| `mechanisms[]` | Curated mechanism records. `class` is our vocabulary (`mech:loss-of-function`, `mech:haploinsufficiency`, `mech:dominant-negative`, `mech:gain-of-function`) or `null`. `label_verbatim` is the source's own words. `url` is the record. `confidence` is G2P's confidence or ClinGen's HI score. `joined_by` says how the record reached this disease. |
| `validity[]` | ClinGen gene–disease validity: classification, mode of inheritance, report URL and the curating panel (GCEP). |
| `pathways[]` | Up to 5 mid-level Reactome pathways of the disease's gene, most-annotated first. Entries with 2–3 genes get a vote across their genes. |
| `cluster_id` | The mechanism cluster (`MC0001`…). Only single-gene diseases whose gene has a mid-level pathway get one. |
| `mechanism_neighbours[]` | Up to 10 diseases in the **same cluster** that share at least one pathway **and** at least one mechanism class, listed with the shared items. Ranked by the gene–gene edge weight, then by phenotype cosine. A disease from the same gene ranks first. |

`clusters.json` has one entry per cluster:

- `id`, `label`, `size`, `small` (fewer than 5 diseases);
- `top_pathways[]` with `id`, `name`, `coverage` and `url`;
- `mechanism_mix`, a count per class plus `unassigned`, and `dominant_mechanism`;
- `distinctive_phenotypes[]` with `hpo`, `name`, `ic` and `coverage`;
- `genes`, the 12 most frequent;
- `members`, the disease ids;
- `rationale` and `evidence_basis`.

The label reads `<top pathway> · <dominant mechanism> · <most distinctive enriched phenotype>`,
e.g. "Glycosphingolipid metabolism · loss of function · cherry red spot of the macula".

### Rules

**Mechanism class.** Curated databases only, and the source label is always kept verbatim.

| Source | Label | Our class |
|---|---|---|
| G2P | "loss of function" | `mech:loss-of-function` |
| G2P | "dominant negative" | `mech:dominant-negative` |
| G2P | "gain of function" | `mech:gain-of-function` |
| G2P | "undetermined" | no class; label kept |
| G2P | any record with confidence "disputed" | no class; label kept |
| G2P | any record with confidence "refuted" | skipped (3 records) |
| ClinGen dosage | HI score 3 or 2 | `mech:haploinsufficiency` |

A ClinGen HI score is attached to the disease ClinGen names (the HI disease id). Otherwise it is
attached only to dominant entries of that gene (autosomal dominant inheritance, or a G2P monoallelic
record), never to recessive ones. Triplosensitivity is not forced into a class.

How a record joins a disease, in order: MONDO id, then a unique OMIM number, then the only
single-gene entry of that gene.

| Source | Joined | Unjoined |
|---|---|---|
| G2P | 3,493 (3,117 by MONDO, 198 by OMIM, 178 by gene) | 355 |
| ClinGen validity | 2,973 | 722 |
| ClinGen HI | 427 genes | 8 genes |

**Pathways.**

- Each gene's lowest-level Reactome pathways (NCBI2Reactome) roll up to their **depth-3 ancestor**,
  counting the top level as 0. For example: Metabolism (0) › Metabolism of lipids (1) › Sphingolipid
  metabolism (2) › Glycosphingolipid metabolism (3), and Signal Transduction (0) › MAPK family
  signaling cascades (1) › MAPK1/MAPK3 signaling (2) › RAF/MAP kinase cascade (3).
- A leaf at depth 2 is kept as itself.
- A pathway with more than 400 human genes is dropped as too broad (e.g. Neutrophil degranulation).
- **Reactome's top-level "Disease" branch is excluded.** It holds mutant-specific copies of normal
  pathways ("Signaling by RAF1 mutants") that re-annotate whole downstream machineries to the
  mutated gene. With it, BRAF clustered with platelet-integrin genes.
- For similarity, each gene's set also includes the depth-2 parents (the "band").

**Clusters.**

- Nodes are **genes**, not diseases. Pathways belong to the gene, and a disease-level graph split
  SCN1A's own allelic diseases across four clusters. Each disease inherits its gene's cluster.
- An edge exists only when two genes share a band pathway. Its weight is
  `0.6 × IDF-weighted pathway Jaccard + 0.4 × phenotype cosine`:
  - IDF is computed over all Reactome human genes;
  - the phenotype cosine compares the genes' centroids of **non-neoplastic** diseases. Tumour and
    somatic entries diluted BRAF's Noonan/CFC profile.
- The graph keeps 15 nearest neighbours per gene and is symmetrised.
- Leiden runs with RBConfiguration, resolution 1.0 and seed 20261003.
- A community holding more than 80 diseases is re-split on its own subgraph, raising the resolution
  ×1.5 per round so splits stay minimal.
- Resolution and weights were chosen by a sweep, reported in `docs/agent-reports/derived.md`.
- A mechanism-class agreement factor (×1.25 for a shared class family, ×0.85 for conflicting
  families) was tested and is **off**: it split the RASopathies further.

Result: 5,426 diseases in 225 clusters. 200 clusters, holding 5,362 diseases, fall in the 5–80
target; 25 are small.

### Sanity checks

These are in `meta.mechanism.sanity_checks`, recomputed on every run.

- **Lysosomal storage: partly.**
  - The sphingolipidoses form **one** cluster: MC0034 "Glycosphingolipid metabolism · loss of
    function · cherry red spot of the macula" (43 diseases, 38 of them lysosomal). It covers
    Gaucher, Krabbe, Fabry, GM1, Tay-Sachs/Sandhoff/AB variant, sialidosis, galactosialidosis,
    Niemann-Pick A/B, Farber and the saposin deficiencies.
  - MPS I/II/IIIA/B/C form a heparan-sulfate cluster (MC0114, 22 diseases). It also contains EXT1/2
    exostoses, which share the heparan-sulfate pathway but not the storage biology.
  - The rest split by substrate pathway, because Reactome organises by substrate, not by organelle:
    - arylsulfatases: ARSA, ARSB, SUMF1;
    - glycogen: GAA;
    - lipoprotein: LIPA, NPC1, NPC2;
    - N-glycosylation: FUCA1;
    - mannosidoses (own cluster);
    - NCLs scattered: PPT1, TPP1, CTSD.
  - 10 diseases have no mid-level pathway and are unclustered (AGA, CLN3, GNPTAB, NAGA).
- **RASopathies: NOT one cluster** (3 clusters):
  - MC0020 "FLT3 Signaling · gain of function · nevus" (50): KRAS, HRAS, NRAS, SOS1 and PTPN11,
    together with PIK3CA/PTEN/AKT. This is RTK–RAS–PI3K.
  - MC0102 "Signaling by FGFR · gain of function · curly hair" (23): BRAF, RAF1, SPRED1/2, MAP2K2 and
    PPP1CB. This is RAF–MEK.
  - MAP2K1 sits in MC0004, Toll-like receptor cascades, because Reactome places MEK1 in every TLR
    cascade.
  - The cause is structural. In Reactome, RAS genes share far more pathways with RTK/PI3K adaptors
    than with RAF/MEK (KRAS–PIK3CA 0.33 against KRAS–BRAF 0.24 edge weight), and Jaccard penalises
    hub genes.
- **Sodium-channel epilepsies: yes.** All 17 diseases of SCN1A, SCN2A, SCN3A, SCN8A and SCN1B are
  in MC0024 "Phase 0 - rapid depolarisation · haploinsufficiency · arrhythmia" (49 diseases). The
  cluster also holds SCN4A, SCN5A and SCN9A, so it is the sodium-channelopathy family.
- **SNARE slice.**
  - MC0005 "Neurotransmitter release cycle · loss of function · hyperreflexia" (64) holds STXBP1,
    SNAP25, SYT1, VAMP2, CPLX1 and the bridge gene SLC6A1.
  - SYT2 is in clathrin-mediated endocytosis (MC0129) and NSF in Golgi traffic (MC0115).
  - STX1B and UNC13A are unclustered. UNC13A has no Reactome annotation at all, and STX1B's only
    pathway was in the excluded Disease branch. STX1A has no single-gene disease entry.

### How the UI should use it

1. Show `mechanisms[]` with the badge `class` and the source's own words (`label_verbatim`),
   linked to `url`.
2. Show `validity[]` as "ClinGen: Definitive (AD)", linked to the report.
3. Show `pathways[]` as Reactome links.
4. Show the cluster label as "mechanism family". Load `clusters.json` once and list the members.
5. Show `mechanism_neighbours[]` as "same mechanism family, shares a pathway and a mechanism class"
   with the shared items.
6. Everything here is **computed** grouping over curated inputs. It is not evidence that two
   diseases respond to the same therapy.

The `atlas` flag can change when family files land. `python3 pipeline/derive/atlas_flags.py`
rewrites only that column of `index.json` from `data/curated/family_*.json`, and it is stdlib and
runs in under a second. It flags MONDO/subtype matches and single-gene entries, never multi-gene
groups, and records itself in `meta.atlas_flags`.

## Method

**Information content (IC).** This is the biology layer's `pipeline/biology/hpo.py`, imported rather
than copied, so a term has the same IC everywhere in the app:

    IC(t) = -ln(diseases annotated to t or a descendant / 12,867)

It is computed over all `phenotype.hpoa` entries, aspect P, with NOT rows dropped.

**Similarity: IC-weighted cosine over ancestor-propagated profiles.**

- Each disease becomes a vector with `w_t = IC(t)` for every term in its propagated set.
- Broad ancestors have IC ≈ 0, so they contribute nothing.
- Unlike Resnik best-match-average, one rare term matched inside a large profile cannot inflate the
  score.
- The weighting exponent was checked on a small benchmark of expected pairs (Huntington disease,
  DMD, CF and Dravet, using unmerged profiles). IC¹ and IC^1.5 tied with 13 expected neighbours in
  the top 10, ahead of IC^0.5 and IC² with 12 each. IC¹ was kept because it is the plain
  IC-weighted cosine.

**Merged diseases are centroids.** An OMIM + ORPHA pair is the mean of its sources' normalised
vectors, not the union of their terms.

- With a union, one source's annotation style dominates. ORPHA:399 adds a block of behavioural
  terms to Huntington disease, and that pulled in an alcohol-related neighbour.
- The centroid moved TBP/SCA17 from outside the top 10 to #4.

**"Near" vs "far" from the mapped family (calibrated).** `near` means cosine ≥ **0.2454**. That is
the *lowest* cosine among the atlas's own 11 curated `similar_phenotype` pairs (SNAP25–SYT2). In
other words, a disease is near if it is at least as similar to a mapped disease as the
least-similar pair the atlas itself links. At this threshold, 8.8% of comparable non-slice diseases
are near at least one mapped disease. The full table is in `meta.method.atlas_threshold.calibration`.

Two alternatives were considered and rejected:

- **Median in-family cosine (0.31).** Only 3.4% of diseases are near, and Dravet syndrome comes out
  "far" from STX1B, which is wrong.
- **Per-atlas-disease 99th percentile.** 6.0% are near. The background is dense in epilepsies and
  sparse in myasthenias, so the same percentile means different things. Dravet came out "far" and
  Duchenne came out "near" SNAP25.

`far` is the only place this folder says anything about mechanism, and it is worded as "most
likely". Phenotype dissimilarity is weak evidence of a different mechanism, not proof.

## Sanity checks

These are recorded in `meta.sanity_checks` and recomputed on every run. Ranks count the whole pool.

| disease | top neighbours (abridged) | expected neighbour ranks | atlas |
|---|---|---|---|
| Huntington disease | HDL2 (JPH3), HDL1 (PRNP), juvenile HD (HTT), SCA17 (TBP), inherited CJD (PRNP), CLN13, SCA48, late-onset PD, CSF1R leukoencephalopathy, PINK1 PD | JPH3 **1**, PRNP **2**, TBP **4**, ATN1/DRPLA **100** | far |
| cystic fibrosis | bronchiectasis + nasal polyposis, SCNN1A bronchiectasis with elevated sweat chloride, PCD 42, pancreatic lipase deficiency, PCD 44, TAP1 MHC-I deficiency, RPGR sinorespiratory, PCD 46, CGD (NCF1), Young syndrome | SCNN1A **2**, PCD42 **3**, Young **10** | far |
| Duchenne muscular dystrophy | dystroglycanopathy (POMGNT2), LGMD2I (FKRP), LGMD2D (SGCA), LGMD2K, LGMD2O, LGMD2E, LGMD2Q, LGMD1H, LGMD2C, DCM 1X (FKTN) | FKRP **2**, SGCA **3**, Becker **18** | far (closest SNAP25 0.237, just under 0.2454) |
| Dravet syndrome | GEFS+, PCDH19 clustering epilepsy, DEE6A (SCN1A), DEE94 (CHD2), GEFS+2 (SCN1A), DEE13 (SCN8A), DEE56, JME, DEE52 (SCN1B), MEI | DEE6A **3**, GEFS+2 **5**, SCN1B **9** | **near** STXBP1 (0.264) and STX1B (0.246) |

Known misses:

- **DRPLA (ATN1) ranks 100th for Huntington disease.** Its HPO profile leans on myoclonic epilepsy
  and ataxia, not on chorea and psychiatric features.
- **Becker muscular dystrophy ranks 18th for Duchenne.** Becker has 22 annotated terms against
  Duchenne's 39, and its milder course shares fewer of the distinctive ones.

Both misses come from the annotations, not the method. They are the reason the caveat is on every
page.

## How the UI should use it

1. **Search.** Load `index.json` once, apply the search recipe above, and send `atlas` hits to the
   existing atlas page.
2. **Global page.** Fetch `neighbours/<bucket(id)>.json` and read `d[id]`. Then show:
   - the name, synonyms, genes (with the `gsrc` note when it is 2) and inheritance;
   - `own` as "most distinctive features", with IC as a quiet hint;
   - `nb` as "diseases that look most alike", each with its 3 shared terms;
   - the `atlas` block: either "closest mapped diseases" with `near` badges, or `meta.far_text`;
   - external links built from `meta.url_templates`: OMIM, Orphanet, Monarch, a ClinicalTrials.gov
     condition search, a NORD site search and a GeneReviews search;
   - the caveat banner, `meta.caveat`, every time.
3. **Never** draw these as graph edges and never give them a confidence score. They are
   lookups, not evidence.
