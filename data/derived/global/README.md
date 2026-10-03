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
| `meta.json` | 11 KB | once: caveat text, URL templates, threshold, versions |

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
