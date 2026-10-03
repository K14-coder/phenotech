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

## DisMech layer: `dismech/`, `dismech_evidence/`, `dismech_index.json`, `index_extra.json`, `dismech_atlas_links.json`

This layer is **independently curated** mechanism knowledge from
[DisMech](https://dismech.monarchinitiative.org), the Disorder Mechanisms Knowledge Base of the Monarch
Initiative (GitHub `monarch-initiative/dismech`, **BSD-3-Clause**). It is the only part of this folder
that carries curated evidence quotes. It is purely **additive**: `index.json`, `neighbours/` and
`mechanism/` are untouched. Built by `pipeline/derive/dismech.py`
(`uv run --with pyyaml python3 pipeline/derive/dismech.py`, about 15 s), step 8/8 of `run.sh`, from a
shallow clone in `data/raw/downloads/dismech` pinned at commit
`332cbfdc00c4d49d5c9ed8aa45b14abb20e2f1bb` (recorded in `meta.dismech.commit`).

**Attribution (show wherever DisMech content appears):**
> Mechanism pathograph from DisMech, the Disorder Mechanisms Knowledge Base of the Monarch Initiative
> (https://dismech.monarchinitiative.org), BSD-3-Clause. Curated independently of this atlas; evidence
> snippets are quoted verbatim from DisMech.

The same text is in `meta.dismech.attribution_text` and in every shard's `attribution`. The BSD-3 licence text ships alongside these files as `DISMECH_LICENSE.txt`. Each record
also links its source file on GitHub at the pinned commit (`attribution.file_url`) and its DisMech page
(`attribution.page_url`).

| File | Size | Load |
|---|---|---|
| `dismech_index.json` | 0.22 MB | once, with `index.json`: flags "has curated mechanism" in search |
| `index_extra.json` | 0.11 MB | once, concatenated to `index.json` rows: 789 DisMech diseases not in `index.json` |
| `dismech/<bucket>.json` | 64 shards, 30.6 MB total (6.4 MB gzip), max 1.07 MB, median 0.43 MB | lazily: the pathograph of one disease |
| `dismech_evidence/<bucket>.json` | 64 shards, 90.9 MB total (22 MB gzip), max 3.1 MB, median 1.2 MB | lazily, only when a reader opens the evidence |
| `dismech_atlas_links.json` | 63 KB | once, on the 45 deep-atlas disease pages |

**Bucketing is the same `bucket(id) = djb2(id) % 64` as `neighbours/`**, keyed on the MONDO id
(e.g. `MONDO:0012812` STXBP1 encephalopathy → bucket 58). Both shard sets share it, so one id gives one
file in each.

Counts (`meta.dismech.counts`): 3,290 DisMech YAML files → **3,238 records under 3,217 MONDO ids**
(14 MONDO ids carry 2+ DisMech entries, e.g. `MONDO:0014590` has both `SNAP25_Encephalopathy` and
`Congenital_Myasthenic_Syndrome_18`; 52 files have no MONDO term and are listed in
`meta.dismech.no_mondo_files`). 52,680 steps, 22,650 of them mechanism (pathophysiology) steps, and 52,548
causal edges. **143,102 evidence items are carried, holding 143,089 snippets, all re-checked verbatim
against the source YAML**: SUPPORT 141,197, REFUTE 1,590, NO_EVIDENCE 315. The DisMech corpus holds 227,012
evidence items in all. The rest sit in sections this layer does not carry (see Caveats).

### `dismech/<bucket>.json`: the pathograph

```json
{"bucket": 58,
 "attribution": {"source": "DisMech (Monarch Initiative)", "license": "BSD-3-Clause", "commit": "332cbfdc…", "text": "…"},
 "t": {"GO:0099504": "synaptic vesicle cycle", "CL:0000540": "neuron", "HP:0200134": "Epileptic encephalopathy", …},
 "d": {"MONDO:0012812": [ {
   "file": "STXBP1_Encephalopathy.yaml", "name": "STXBP1 Encephalopathy",
   "mondo": "MONDO:0012812", "mondo_label": "developmental and epileptic encephalopathy, 4", "joined_by": "disease_term",
   "category": "Mendelian", "description": "…", "synonyms": […], "parents": ["Neurodevelopmental Disorder", "Epileptic Encephalopathy"],
   "inheritance": [{"name": "Autosomal Dominant (De Novo)", "hp": "HP:0000006"}],
   "steps": [
     {"i": 0, "label": "STXBP1", "sec": "genetic", "type": "gene", "type_basis": "section", "terms": [["HGNC:11444", "gene_term"]]},
     {"i": 1, "label": "STXBP1 Haploinsufficiency and Munc18-1 Deficiency", "sec": "pathophysiology", "type": "cellular",
      "type_basis": "inferred:cell_types", "role": "trigger", "conforms_to": "synaptic_vesicle_cycle#…",
      "terms": [["GO:0099504", "biological_processes", "ABNORMAL"], ["CL:0000540", "cell_types"], ["UBERON:0000955", "locations"]],
      "ev": [3, 0, 0]}, …],
   "edges": [{"s": 0, "t": 1, "link": "contributes_to", "inferred": "gene symbol in root node name (ours, not DisMech)"},
             {"s": 1, "t": 2, "link": "DIRECT"},
             {"s": 1, "t": 3, "link": "INDIRECT_KNOWN_INTERMEDIATES", "intermediate": ["Impaired SNARE-mediated synaptic vesicle fusion."]}, …],
   "chains": [[0, 1, 2, 3, 4, 6], [0, 1, 2, 3, 5, 7], …], "n_paths": 8, "cyclic": false,
   "genes": [{"symbol": "STXBP1", "name": "STXBP1", "hgnc": "HGNC:11444", "association": "Loss-of-Function Mutations",
              "variant_origin": "GERMLINE", "inheritance": ["Autosomal Dominant (De Novo)"], "contributes": true,
              "linked_to_mechanism": "name_match", "ev": [2, 0, 0]}],
   "treatments": [{"name": "Antiseizure Medication", "modality": "SMALL_MOLECULE", "action": {"id": "NCIT:C15986", "label": "Pharmacotherapy"},
                   "agents": [{"id": "CHEBI:6437", "label": "levetiracetam"}, …], "targets": […], "ev": [1, 0, 0]}],
   "hypotheses": [],
   "open_questions": [{"kind": "CONTROVERSY", "status": "OPEN", "prompt": "Is STXBP1 encephalopathy a pure loss-of-dose …", "attaches_to": […], "ev": [2, 0, 0]}],
   "unlinked_phenotypes": [["Epileptic Spasms", "HP:0011097"], ["Tonic Seizures", "HP:0032792"], …],
   "counts": {"steps": 10, "mechanism_steps": 5, "edges": 10, "evidence": 24, "refute": 0, "no_evidence": 0, "genes": 1, "treatments": 3},
   "attribution": {"file_url": "https://github.com/monarch-initiative/dismech/blob/332cbfdc…/kb/disorders/STXBP1_Encephalopathy.yaml",
                   "page_url": "https://dismech.monarchinitiative.org/pages/disorders/STXBP1_Encephalopathy.html"}} ]}}
```

`d[id]` is always a **list**: one record per DisMech file anchored to that MONDO id.

| key | meaning |
|---|---|
| `t` | Shard-local ontology labels (GO, CL, UBERON, HP, CHEBI, HGNC, ECTO…). `steps[].terms` holds `[id, slot, modifier?]`; look the label up here. Links: GO/CL/UBERON/HP via OLS or Monarch, `https://monarchinitiative.org/<id>`. |
| `steps[]` | All pathograph nodes, in **topological order** (Kahn's algorithm; ties broken by type, gene → molecular → cellular → tissue → organism → phenotype, then file order). `i` is the position. |
| `steps[].sec` | Which DisMech section the node comes from: `genetic`, `environmental`, `pathophysiology` (the mechanism steps), `phenotypes`. |
| `steps[].type` | `gene`, `environmental`, `molecular`, `cellular`, `tissue`, `organism`, `phenotype`, or `unspecified`. |
| `steps[].type_basis` | `scale` = DisMech's own `biological_scale` (14,493 steps); `section` = from the section (gene, environment, phenotype); `inferred:<slot>` = ours, from which ontology slots the node fills (gene descriptor on a root node → gene; molecular_functions/chemical_entities → molecular; cell_types → cellular; locations → tissue; 5,523 steps); `none` → `unspecified` (2,634). |
| `steps[].role`, `conforms_to`, `mechanism_confidence` | DisMech's own fields, verbatim. `conforms_to` names a shared DisMech mechanism module (`module#Node`). |
| `steps[].ev` | `[evidence items, refutes, no_evidence]` for the node. The items themselves are in `dismech_evidence/`. |
| `edges[]` | `s` → `t` step indices. `link` is DisMech's `causal_link_type` (`DIRECT`, `INDIRECT_KNOWN_INTERMEDIATES`, `INDIRECT_UNKNOWN_INTERMEDIATES`, `UNKNOWN`), an environmental effect (`TRIGGERS`, `EXACERBATES`…; `predicate: "influences"`), a phenotype `sequela`, or `contributes_to` for gene → mechanism. |
| `edges[].inferred` | Present only on gene → mechanism edges **we** added (407): a contributing gene that DisMech's own rule leaves unlinked is joined to a *root* pathophysiology node whose name contains the gene symbol as a word ("STXBP1 Haploinsufficiency …", "SCN1A Gene Mutation"). Draw them dashed. The other 5,429 gene edges follow DisMech's `graph.py` rule (shared gene descriptor). |
| `chains[]` | Up to 12 root → sink paths as step-index lists, longest first. `n_paths` is the total count (capped at 5,000). `cyclic` marks the 63 records whose graph has a cycle (the extra nodes are appended after the topological part). |
| `genes[]` | DisMech's `genetic` section. `contributes` is false for MODIFIER/BIOMARKER/PROTECTIVE/DISPUTED/UNKNOWN genes (DisMech's own rule). `linked_to_mechanism`: `"dismech"`, `"name_match"` (ours, see above) or `false`. |
| `treatments[]` | `modality` (DisMech `therapeutic_modality`), `action` (NCIT clinical action), `agents` (CHEBI/NCIT drugs), `regimen`, and `targets` (`target_mechanisms`; `step` is the step index when the target is a node). |
| `hypotheses[]`, `open_questions[]` | DisMech `mechanistic_hypotheses` (CANONICAL/EMERGING…) and `discussions` (KNOWLEDGE_GAP, CONTROVERSY, HUMAN_MODEL_MISMATCH…). Contested mechanisms live here, e.g. STXBP1's haploinsufficiency-versus-dominant-negative controversy. |
| `unlinked_phenotypes` | Phenotypes that no causal edge reaches, as `[name, HP id]`. DisMech leaves about half of its phenotypes unconnected. |

### `dismech_evidence/<bucket>.json`: verbatim evidence and long prose

```json
{"bucket": 58, "attribution": {…},
 "refs": {"PMID:18469812": ["De novo mutations in the gene encoding STXBP1 (MUNC18-1) cause early infantile epileptic encephalopathy.",
                            "https://pubmed.ncbi.nlm.nih.gov/18469812/"], …},
 "d": {"MONDO:0012812": [ {"file": "STXBP1_Encephalopathy.yaml",
   "x": {"steps/1": {"description": "De novo heterozygous loss-of-function variants …",
                     "evidence": [{"ref": "PMID:18469812", "supports": "SUPPORT", "source": "HUMAN_CLINICAL",
                                   "snippet": "These findings suggest that haploinsufficiency of STXBP1 causes EIEE.",
                                   "explanation": "Identifies haploinsufficiency as the disease mechanism, the trigger modeled by this node."}, …]},
         "edges/2": {"description": "…"}, "genes/0": {"notes": "…", "evidence": […]},
         "treatments/0": {"description": "…", "evidence": […]}, "open_questions/0": {"rationale": "…", "evidence": […]}, …}} ]}}
```

- `d[id]` is a list **parallel** to `dismech/<b>.json`'s `d[id]`, matched on `file`.
- `x` is keyed by the path of the object in the core record: `steps/<i>`, `edges/<k>`, `genes/<k>`,
  `treatments/<k>`, `treatments/<k>/targets/<j>`, `hypotheses/<k>`, `open_questions/<k>`.
- Each entry holds the object's `evidence` and its long text (`description`, `rationale`, `notes`).

Evidence item fields:

| field | meaning |
|---|---|
| `ref` | DisMech reference, e.g. `PMID:…`, `ORPHA:…`, `DOI:…`, `CGGV:…`, `clinicaltrials:NCT…`, `url:https://…` |
| `supports` | `SUPPORT`, `REFUTE` or `NO_EVIDENCE` (DisMech removed `PARTIAL` in its issue #7439) |
| `snippet` | Exact quote from the source, **byte-identical to the parsed DisMech YAML**. Never edit it. |
| `explanation` | DisMech curator's explanation, verbatim |
| `source` | `HUMAN_CLINICAL`, `MODEL_ORGANISM`, `IN_VITRO`, `COMPUTATIONAL`, `OTHER` (the cited study's type) |
| `directness`, `quote_role` | DisMech's optional axes: `INDIRECT` evidence, or a `BACKGROUND` quote |
| `flag` | For the UI. `refute` (1,590): show as **counter-evidence**. `no_evidence` (315): the reference does not bear on the claim. `indirect` (5,934): DisMech's replacement for the old `PARTIAL`, i.e. supports the claim only through an inference step. |

The URL is `refs[ref][1]`, built from the reference prefix: PubMed, Orphanet, doi.org, ClinicalTrials.gov,
ClinGen validity/dosage, GEO, Europe PMC preprints, WHO ICTRP, NCIt EVS, CIViC and MetaboLights.
`url:` refs use their own URL. Only 4 `STRCHIVE:` refs have no URL. `refs[ref][0]` is DisMech's
`reference_title`.

### `dismech_index.json`: search flag

```json
{"f": ["id","name","mech_steps","steps","evidence","refute","entries","in_index"],
 "rows": [["MONDO:0012812","STXBP1 Encephalopathy",5,10,24,0,1,true], …]}
```

One row per MONDO id (3,217), with counts summed over its entries. A search hit whose id is in this
file gets a "curated mechanism (DisMech)" badge. `in_index` is false for the 789 ids that live in
`index_extra.json`.

### `index_extra.json`: DisMech diseases missing from `index.json`

This file holds 789 DisMech MONDO ids that `index.json` does not have, mostly common, infectious,
toxic and oncologic diseases outside the HPO/gene rare-disease pool. It uses **the same row format and
`f` as `index.json`**, so search can concatenate the rows:

- `name` is the MONDO label from DisMech;
- `syn` holds up to 6 DisMech synonyms and names;
- `omim` and `orpha` come from the MONDO equivalentTo xrefs;
- `genes` are DisMech's contributing genes, with **`gsrc = 3`** (new: "genes from DisMech's curated
  `genetic` section", which can include risk genes for complex diseases);
- `n = 0` and `atlas = 0`.

These rows have no `neighbours/` or `mechanism/` entry. Their page shows the DisMech pathograph and the
links out. `index.json` itself is not rewritten.

### `dismech_atlas_links.json`: DisMech next to the deep atlas

A DisMech record is linked to an atlas `disease:<GENE>` umbrella when its MONDO id equals one of the
umbrella's MONDO xrefs, or one of its `attrs.subtypes[].MONDO` ids. Umbrellas come from
`data/graph.json` and `data/curated/family_*.json`. An obsolete xref is followed to its MONDO
`replaced_by`, which is how `MONDO:0011794` (obsolete) reaches DisMech's Dravet syndrome
`MONDO:0100135`.

The result is 72 links, covering 32 of 45 umbrellas. Each link has a `kind`:

- `single_gene` (36): DisMech's only contributing gene is the umbrella gene;
- `multi_gene_lists_gene` (16): e.g. Dravet, which lists 11 genes with SCN1A first;
- `group_gene_not_listed` (20): a clinical group our node lists as a subtype (Lennox-Gastaut, infantile
  spasms…) whose DisMech entry does not name the gene. **Hide these by default.**

`gene_only` (16) is a separate list of leads, not matches. Each is a non-somatic DisMech disorder,
with at most 3 contributing genes, that names the umbrella gene but matches none of its MONDO ids. Each
is a candidate missing xref on our node: CDKL5 deficiency disorder `MONDO:0100039`, GLUT1 deficiency
syndrome `MONDO:0000188`, Gaucher disease `MONDO:0018150`, Niemann-Pick C `MONDO:0018982`, MLD
`MONDO:0018868`, and others.

On a disease page, show the DisMech pathograph as a second, independently curated view headed
**"DisMech mechanism"**. Never merge its steps into our graph edges, and always show the attribution.

### Caveats

- **Scope of carried evidence.** The layer carries the evidence on the pathograph: steps, causal edges,
  genes, treatments and their targets, hypotheses and discussions. Evidence on unlinked phenotypes,
  diagnosis, prevalence, inheritance, biochemistry, clinical trials, datasets, animal models,
  progression and differentials (83,910 items) stays in DisMech and is reachable through `file_url`.
- **Verbatim, not re-verified.** Snippets are copied unchanged and checked only against DisMech's YAML.
  Whether each quote appears in the cited paper is DisMech's validation (`linkml-reference-validator`),
  not ours.
- **Dangling targets.** 509 `downstream` targets name no node in their own file. These are DisMech
  curation defects, counted and dropped, never guessed.
- **Type is partly ours.** Where DisMech gives no `biological_scale`, `type` is inferred and marked
  `inferred:*`. 2,634 steps stay `unspecified`.
- **The MONDO anchor can be broad or reused.** Some DisMech entries anchor to a grouping term (e.g.
  `SLC6A1-Related_Disorder` on "epilepsy with myoclonic atonic seizures"). 14 ids hold 2+ entries.
- **Pinned commit.** The clone is a snapshot at the commit recorded in `meta.dismech.commit`.
  `run.sh --refresh` pulls the latest.
