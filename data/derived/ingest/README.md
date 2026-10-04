# Ingested open resources: full ClinVar, gnomAD constraint, AlphaMissense, PrimeKG

Built on 2026-10-04 by the scripts in `pipeline/ingest/`. They need no OpenAI and no API keys. Raw files go in `data/raw/downloads/`, which is gitignored.

```bash
python3 pipeline/ingest/clinvar_full.py                 # ~15 s: ClinVar shards + per-gene spectrum
python3 pipeline/ingest/constraint_alphamissense.py     # ~5 s: gnomAD constraint + AlphaMissense
python3 pipeline/ingest/primekg_fetch.py                # streams the 982 MB kg.csv; keeps only drug-disease edges
python3 pipeline/ingest/primekg_benchmark.py [--offlabel]
uv run --with numpy --with scipy python3 pipeline/eval/primekg_eval.py [--offlabel]   # ~10 s
```

Results are in `docs/agent-reports/ingest.md`.

**Not used: GeneCards (genecards.org).** It blocks automated access, and reuse outside academia needs a licence.

## Sources, dates and licences

| Resource | File and URL | Version or date | Licence |
|---|---|---|---|
| ClinVar | `variant_summary.txt.gz` (450,727,547 bytes), https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz | Last-Modified 2026-09-29 02:10 GMT; downloaded 2026-10-04 | Public domain (NCBI). Cite ClinVar. |
| gnomAD constraint | `gnomad.v4.1.constraint_metrics.tsv` (95.5 MB), https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/constraint/gnomad.v4.1.constraint_metrics.tsv | v4.1, 2024-04-18 | CC0 1.0 |
| HGNC (symbol map only) | `hgnc_complete_set.txt`, https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt | 2026-10-04 | CC0 |
| AlphaMissense | `AlphaMissense_gene_hg38.tsv.gz` (253,636 bytes), Zenodo https://zenodo.org/records/10813168; mirror https://storage.googleapis.com/dm_alphamissense/AlphaMissense_gene_hg38.tsv.gz | file dated 2023-09-19 | See the note below |
| PrimeKG | `kg.csv` (Harvard Dataverse doi:10.7910/DVN/IXA7BM, file 6180620, 981,751,236 bytes), streamed and filtered. Also `nodes.tab`, `kg_grouped_diseases*.tab` and `README.txt`. | Dataverse v2, 2022-05-02 | Code: MIT (github.com/mims-harvard/PrimeKG). Dataverse dataset: CC0 1.0. |

**AlphaMissense licence note.** The Zenodo record 10813168 metadata gives the licence as **CC BY 4.0**. The header inside the file still says "Licensed under CC BY-NC-SA 4.0", which were the original 2023 terms. The Google Storage and Zenodo copies are byte-identical. We cite Cheng et al., *Science* 2023, and treat the data as CC BY 4.0 per the current record. If the NC terms are judged to apply, use is limited to non-commercial purposes. The atlas is a non-commercial hackathon project.

**Not downloaded: the AlphaMissense per-variant file.** `AlphaMissense_hg38.tsv.gz` is 643 MB and covers 71M variants. It was skipped because the disk had about 5 GB free. A possible next step is to stream it once and keep scores only for the ClinVar P/LP positions in the shards below (about 70k missense variants). That would give the web VCF checker a per-variant pathogenicity score.

## `clinvar/<bucket>.json`: P/LP variants for every gene, for the VCF checker

**Filter.** A row is kept when:
- `Assembly` is GRCh38 or GRCh37; and
- the germline classification (column `ClinicalSignificance`) is exactly `Pathogenic`, `Likely pathogenic` or `Pathogenic/Likely pathogenic`.

The two assembly rows of one VariationID are merged into one record. Classifications such as "Pathogenic, low penetrance" and "Pathogenic; risk factor" are excluded. Their counts are in `clinvar_meta.json`, and there are about 700 of them.

**Counts.** 9,223,698 rows read, 750,461 rows kept, giving **387,722 variants in 13,292 genes**.
- Exact VCF keys: 352,063 on GRCh38 and 352,052 on GRCh37.
- 158 variants have no gene.
- 871 variants list more than 5 genes (large CNVs) and are not attached to any gene.

**Sharding.** `bucket = djb2(GENE_SYMBOL) % 64`, using the same djb2 as `data/derived/global/README.md`: seed 5381, `h = h*33 + charCode`, unsigned 32-bit after every character. The key is the HGNC symbol exactly as ClinVar writes it, case-sensitive. For example, `STXBP1` goes to bucket 39.

```json
{"bucket": 39,
 "f": ["vid","tx","hgvs","protein","type","consequence","class","stars","grch38","grch37","pheno"],
 "g": {"STXBP1": {
    "tx": ["NM_001032221.6", "", "NM_001374309.2", "NM_003165.6", "NC_000009.12", "NC_000009.11"],
    "ph": ["MONDO:0012812", "MedGen:C2677326", "OMIM:612164", ...],
    "v": [[6726, 0, "c.1631G>A", "p.Gly544Asp", "snv", "missense", "P", 2,
           "9:127682489:G:A", "9:130444768:G:A", [0, 1, 2, 3, 4]], ...]}}}
```

| field | meaning |
|---|---|
| `vid` | ClinVar VariationID. The record is at `https://www.ncbi.nlm.nih.gov/clinvar/variation/<vid>/`. |
| `tx` | Index into the gene's `tx` list, which holds the transcript or sequence accession from the ClinVar Name. `""` means the Name had no accession, as for cytogenetic CNV names. |
| `hgvs` | The c./g./m./n. part of the ClinVar Name. For CNVs without an accession it is the whole Name. The protein part is in `protein`. |
| `protein` | The ClinVar protein change, in 3-letter code, e.g. `p.Arg388Ter`. `""` if none. |
| `type` | The ClinVar Type, coded: `snv`, `del`, `dup`, `ins`, `indel`, `cnv_loss`, `cnv_gain`, `str` (Microsatellite), `inv`, `trans`, `complex`, `fusion`, `other`. |
| `consequence` | Molecular consequence derived from the Name and Type (rules below). |
| `class` | `P`, `LP` or `PLP` (Pathogenic/Likely pathogenic). |
| `stars` | Review stars: 4 practice guideline; 3 expert panel; 2 multiple submitters with no conflicts; 1 single submitter or conflicting; 0 no criteria. |
| `grch38`, `grch37` | `chr:pos:ref:alt` from the VCF-style columns (`PositionVCF`, `ReferenceAlleleVCF`, `AlternateAlleleVCF`), 1-based. `""` if ClinVar gives no VCF allele, which is the case for most CNVs. If ref plus alt is longer than 100 bases, the key is abbreviated to `chr:pos:~<reflen>><altlen>` and is not an exact key. |
| `pheno` | Indices into the gene's `ph` list. It holds MONDO, MedGen and OMIM phenotype ids from `PhenotypeIDS`. "not provided" and "not specified" are dropped. MONDO ids join directly to `data/derived/global/index.json`. |

**Consequence rules**, applied in order:
1. CNV types, or a cytogenetic `GRCh..` Name, give `cnv_loss` or `cnv_gain`.
2. Then the protein change decides:
   - `fs` gives `frameshift`;
   - `p.Met1…` gives `start_lost`;
   - `ext` gives `stop_lost`;
   - `p.Xxx123Ter` gives `nonsense`;
   - `p.Xxx123Yyy` gives `missense`;
   - `p.Xxx123=` gives `synonymous`, or `splice_region` if the c. change is intronic;
   - an insertion or delins ending in `Ter` gives `nonsense`;
   - other insertions, deletions, delins and dups give `inframe_ins`, `inframe_del`, `inframe_delins` and `inframe_dup`.
3. Without a protein change:
   - uncertain-breakpoint or exon-span deletions and duplications, e.g. `c.(?_-30)_(*1_?)del`, give `exon_cnv`;
   - an intronic offset of ±1 or ±2 gives `splice_canonical`;
   - an offset of 3 to 8 gives `splice_region`;
   - a deeper offset gives `intronic`;
   - Microsatellite gives `repeat`;
   - `c.-` gives `utr5`, `c.*` gives `utr3`, `m.` gives `mitochondrial` and `n.` gives `noncoding`.
4. Anything else is `other`.

Counts: frameshift 132k, nonsense 84k, missense 71k, splice_canonical 46k, exon_cnv 16k and cnv_loss 10k. The full table is in `clinvar_meta.json`.

**Sizes.**
- 64 shards, **44.6 MB raw in total, 10.8 MB gzipped**.
- The largest shard, bucket 27 with TTN's 6,092 variants, is 1.47 MB. The smallest is 0.28 MB.
- `sync-data.mjs` copies only top-level `data/derived/*.json`. These shards are **not** deployed until someone adds a `copyTree` for `data/derived/ingest/clinvar`.
- How the web VCF checker can use them: to look up a gene, load `clinvar/<djb2(gene)%64>.json` and match `grch38`/`grch37` exactly. This works for every gene, not only the 45. It works the same way as `variant_positions.json` does for the atlas genes.

## `clinvar_gene_spectrum.json`: per-gene mutation spectrum, all 13,292 genes

```json
{"keys": ["nonsense","frameshift","splice","missense","inframe","cnv","other"],
 "genes": {"STXBP1": {"n": 452, "c": {"nonsense": 65, "frameshift": 108, ...},
                      "f": {"nonsense": 0.1438, ...}, "detail": {"splice_canonical": 74, "exon_cnv": 17, ...}}}}
```

`n` counts the gene's unique P/LP VariationIDs, `c` gives counts and `f` gives fractions of `n`.

How the consequences map to the keys:
- `splice` = splice_canonical + splice_region;
- `inframe` = the four inframe codes;
- `cnv` = cnv_loss + cnv_gain + exon_cnv;
- `other` = start/stop lost, synonymous, intronic, UTR, repeat, noncoding and other.

`detail` keeps the fine codes. File size: 2.06 MB, 0.26 MB gzipped.

## `constraint.json`: gnomAD v4.1 gene constraint

```json
{"f": ["pLI","LOEUF","mis_z","lof_oe","mis_oe","transcript","flags"],
 "genes": {"STXBP1": [1.0, 0.099, 5.847, 0.038, 0.434, "ENST00000373299", ""], ...}}
```

**Coverage.** 18,140 genes, 17,885 of them with pLI. 3,141 have pLI ≥ 0.9 and 3,872 have LOEUF < 0.6.

**Transcript.** One row per gene, chosen in this order: the Ensembl MANE Select row, else the Ensembl canonical row, else the RefSeq MANE Select row.

**Symbols.** gnomAD uses GENCODE v39 names. These are re-keyed to the current HGNC symbol through the HGNC `ensembl_gene_id`; 315 symbols were renamed, e.g. GBA becomes GBA1.

**Reading it.** pLI ≥ 0.9 or LOEUF < 0.6 means the gene does not tolerate loss of function in the population. That supports, but does not prove, haploinsufficiency for a dominant disease.

**Size.** 1.11 MB (0.34 MB gzipped).

## `alphamissense_gene.json`: AlphaMissense mean pathogenicity per gene

```json
{"f": ["mean_am_pathogenicity","transcript","is_gnomad_mane_or_canonical"],
 "genes": {"STXBP1": [0.6828, "ENST00000373299.4", true], ...}}
```

**Coverage.** 19,233 transcripts in the file map to 17,297 genes. The symbol for each ENST comes from the gnomAD transcript table, with the version stripped. 1,849 transcripts did not map, because their ENSTs are retired in GENCODE v39.

**Reading it.** The value is the mean predicted pathogenicity over every possible missense change in the transcript. A high value means missense changes are mostly damaging: the protein is structurally or functionally intolerant.

**Size.** 0.74 MB (0.19 MB gzipped).

## `primekg_benchmark.json` / `primekg_benchmark_offlabel.json`: external therapy-transfer benchmark

**Mapping to MONDO.** PrimeKG disease nodes come in two forms:
- `MONDO`: the id is a bare MONDO number, e.g. `5044` becomes `MONDO:0005044`.
- `MONDO_grouped`: an underscore-joined list of MONDO numbers that PrimeKG merged because their names were near-identical, e.g. `1200_1134_15512` becomes MONDO:0001200, MONDO:0001134 and MONDO:0015512.

A node is mapped to the global-index rows whose id is one of its MONDO ids, as an exact match.

**A child-term fallback was tried and switched off** (`MAX_CHILDREN = 0`). It mapped a parent term to its direct is_a children in the index, which raised coverage from 711 to 1,032 nodes. But it chained generic parents such as "dermatitis", "injury" and "infectious disease" into unrelated diseases. It also made the same disease appear under two names, as with gastric cancer and gastric neoplasm, which leaked the answer.

Nodes that share an index row are merged into one unit. With exact mapping this merges none.

**Eligibility.** A node is eligible when it maps to at least one index row with a gene: OMIM Mendelian or Orphanet, i.e. monogenic or rare.

| | primary (positives = `indication`) | extended (`indication` + `off-label use`) |
|---|---|---|
| PrimeKG disease nodes with drug edges | 2,054 | 2,054 |
| mapped to the index (exact) / eligible | 711 / 461 | 711 / 461 |
| drugs with ≥ 2 eligible indications | **257** | 314 |
| candidate pool (eligible diseases that are indications of those drugs) | **256** | 305 |
| leave-one-out cases | **1,300** | 1,756 |
| contraindication pairs inside the pool | 418 | 653 |

**Schema.**
- `pool`: the unit keys.
- `nodes[key]`: `name`, `primekg_nodes`, `mondo`, `index_ids`, `via` and `genes`.
- `drugs[DrugBank id]`: `name`, `indication`, `contraindication` and `offlabel`, each a list of pool keys.

Sizes: 224 KB and 243 KB.

## `primekg_eval.json` / `primekg_eval_offlabel.json`

Per-factor and combined results: MRR and recall@1/3/5/10 with 95% drug-group bootstrap intervals. Each file also holds the paired differences against phenotype alone, nested-CV choices, logit weights, a drop-one ablation, the no-shared-gene and specific-drug subsets, the contraindication check and coverage. About 22 KB each. Read them with `docs/agent-reports/ingest.md`.
