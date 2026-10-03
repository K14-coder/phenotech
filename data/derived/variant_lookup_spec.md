# Variant lookup: parsing rules for the UI port

A family pastes one line from a genetic report. The app finds the variant among ClinVar's
pathogenic/likely-pathogenic (P/LP) records for the 11 slice genes, or, when it is not there, says
what kind of change the notation describes. The reference implementation is
`pipeline/derive/hgvs.py`. `data/derived/variant_test_cases.json` holds 20 cases that the Python
code passes (`python3 pipeline/derive/variants.py`); the TypeScript port must pass the same cases.

**Scope, to show in the UI:** the table holds only ClinVar P/LP germline records (1,350 records,
retrieved 2026-10-03). A miss means "not among ClinVar's P/LP records for this gene". It does not
mean benign, wrong or not real. VUS and benign records were never downloaded.

## Data: `data/derived/variants.json` (compact JSON, about 320 KB)

```
meta                 scope note, stars legend, QA note
fields               ["accession","url","hgvs","p","protein_change","consequence",
                      "classification","stars","n_submissions","variant_group"]
transcript_to_gene   {"NM_001032221": "STXBP1", "NM_003165": "STXBP1", ...}  (no version suffix)
variant_groups       every vg:<GENE>:<slug> node id in data/graph.json
genes[GENE]          n, by_consequence, null_like_share, recurrent_residues[], most_reported[],
                     variants: rows, each an array in `fields` order
index                "c:<GENE>:<c.>" | "p:<GENE>:<protein>" | "iso:<GENE>:<protein>" -> [row numbers]
```

- `hgvs` is the ClinVar title, e.g. `NM_001032221.6(STXBP1):c.1162C>T (p.Arg388Ter)`. For copy-number
  records it is a genomic description.
- `p` is the canonical 1-letter protein change taken from the title (`R388*`).
- `protein_change` is ClinVar's own list, which numbers the change on every isoform (`R388*, R352*, R374*, R385*`).
- `n_submissions` counts the submitted records (SCVs) behind the variant. Use it as a rough
  "how often reported" signal; it is not a patient count.
- `stars` is the ClinVar review status as 0–4 stars.
- `consequence` is one of `nonsense | frameshift | splice | missense | inframe_indel | cnv | synonymous | other`.
  Start-lost appears as `other` but its `variant_group` is the truncating group, following the biology layer.
- `variant_group` is the graph node, or `null` for inframe, synonymous and other changes. To get the
  mechanism, follow the node's `has_effect` edges in `graph.json` (e.g. truncating → haploinsufficiency).

## Step 1: find the gene

Try these in order. The first hit wins.

1. Transcript with gene: `RE_TX_GENE = /\b(N[MC]_\d+(?:\.\d+)?)\s*\(\s*([A-Za-z0-9-]+)\s*\)/i`.
   This gives the transcript and the gene.
2. Transcript alone: `RE_TX = /\b(N[MC]_\d+(?:\.\d+)?)\b/i`. Strip `.version`, then look the
   accession up in `transcript_to_gene`.
3. Symbol: uppercase the text, then scan `RE_GENE_TOKEN = /\b([A-Z][A-Z0-9]{1,9}(?:-AS1)?)\b/g`
   for one of the 11 slice genes.
4. No slice gene found: take the first token that is not a protein change (step 3 below), not a
   pure `ACGT` string and not in `{CNV, DEL, DUP, MANE, HGVS, ACMG, VUS, NM, NC}`. Treat it as a
   **non-slice gene**. The result is `status = "gene_not_in_atlas"`; stop here.
5. Still nothing: there is no gene, so search all 11 genes. If a hit is found, warn
   "gene inferred from the match".

## Step 2: c. notation

```
RE_C = /\bc\.\s*((?:[-*]?\d+(?:[+-]\d+)?)(?:_(?:[-*]?\d+(?:[+-]\d+)?))?)\s*([ACGTacgt]>[ACGTacgt]|delins[ACGTacgt]+|del[ACGTacgt]*|dup[ACGTacgt]*|ins[ACGTacgt]+|inv)/
```

Canonical form is `c.` + position (kept as typed, e.g. `1029+1`, `128_130`, `-15`, `*20`) + change:

- substitutions in upper case: `C>T`;
- `del`, `dup`, `ins`, `delins` in lower case, with any bases after them in upper case.

Examples: `c.1162 C>T` becomes `c.1162C>T`, and `c.128_130delctg` becomes `c.128_130delCTG`.

Key: `c:<GENE>:<canonical>`. ClinVar titles omit deleted bases (`c.128_130del`). A typed
`c.128_130delCTG` therefore misses on the exact key. The port can retry once with the bases
after `del` or `dup` stripped.

## Step 3: protein notation

Try the 3-letter form first, then the 1-letter form. If neither matches, uppercase any token
shaped like `r388x` and try again.

```
AA3  = Ala Arg Asn Asp Cys Gln Glu Gly His Ile Leu Lys Met Phe Pro Ser Thr Trp Tyr Val Sec Pyl Ter  (case-insensitive)
RE_P3 = /(?:\b[pP]\.\s*\(?\s*|\b)(AA3)(\d+)(?:_(AA3)(\d+))?(AA3|\*|X|=|\?|fs[A-Za-z*]*\d*|del(?:ins[A-Za-z*]+)?|dup|ins[A-Za-z*]+|[A-Z][a-z]{2}fs\S*)/i
RE_P1 = /(?:\b[pP]\.\s*\(?\s*|(?<![A-Za-z0-9.]))([ACDEFGHIKLMNPQRSTVWY])(\d+)(?:_([ACDEFGHIKLMNPQRSTVWY])(\d+))?([ACDEFGHIKLMNPQRSTVWY*X=?](?:fs\*?\d*)?|fs\*?\d*|del(?:ins[A-Z*]+)?|dup|ins[A-Z*]+)(?![A-Za-z0-9])/
```

Canonical form is 1-letter. `Ter`, `X` and `*` all become `*`. A frameshift is cut to `fs`.

| Typed | Canonical |
|---|---|
| `p.Arg388Ter`, `p.(Arg388*)`, `Arg388X`, `p.R388*`, `R388X`, `r388x` | `R388*` |
| `p.Arg397SerfsTer37`, `R397Sfs*37`, `p.Arg397fs` | `R397fs` |
| `p.Val241del` | `V241del` |
| `p.Leu12=` | `L12=` |
| `p.Ile67Asn`, `I67N` | `I67N` |

Look-up order:

1. `c:` key.
2. `p:` key. This is the protein numbered on the ClinVar title transcript.
3. `iso:` key. This is the same protein change numbered on another isoform. A hit here must warn:
   "matched only through another isoform's numbering; confirm the transcript."

## Warnings to show with a match

- **Transcript differs.** The typed transcript (without version) is not the one in the record's
  `hgvs`. Warn that numbering can differ between transcripts. Example:
  `NM_003165.6(STXBP1):c.1162C>T` matches the record titled `NM_001032221.6`.
- **c. and p. disagree.** Both were typed, the `c.` matched, but the record's `p` differs from the
  typed protein. Ask the family to check the report.
- **Several matches.** ClinVar sometimes has both an HGVS record and an OMIM-allele record for
  one change, e.g. SNAP25 V48F. Show all of them.

## Fallback when the variant is not in ClinVar P/LP

Classify the typed notation by pattern alone. The protein notation takes priority. Use the `c.`
notation only when there is no protein notation or the protein notation is inconclusive.

**From the protein notation (`classify_p`):**

| Pattern | consequence | certainty |
|---|---|---|
| ends in `fs` | frameshift | certain |
| `M1?` or `M1<x>` (start codon) | other (start-lost, group = truncating) | likely |
| contains `del`, `dup`, `ins` or `delins`, and creates `*` | nonsense | likely |
| contains `del`, `dup`, `ins` or `delins` otherwise | inframe_indel | certain |
| ends in `=` | synonymous | certain |
| ends in `*` | nonsense | certain |
| `[A-Z]\d+[A-Z]` | missense | certain |

**From the c. notation (`classify_c`).** Split each position into base, intronic offset and
prefix (`-` or `*`), then apply the rules in order:

1. All positions are in the UTR (`-n` or `*n`): other (UTR).
2. Any intronic offset of ±1 or ±2: **splice** (likely).
3. Intronic offsets, all within ±10: **splice** (possible).
4. Deeper intronic offsets: other (unknown).
5. Exonic substitution at c.1, c.2 or c.3: other (start-lost, group = truncating).
6. Any other exonic substitution: **other (unknown)**. Missense, nonsense and silent cannot be
   told apart from `c.` alone, so prompt the family to look for the `p.` on the report.
7. `del`, `dup`, `ins` or `delins`: compute the net length change. Deleted span = end − start + 1;
   `dup` adds the span; `ins` adds the number of inserted bases; `delins` = inserted − span.
   A multiple of 3 is **inframe_indel**; anything else is **frameshift**.

**Copy-number wording, when there is no `c.` or `p.` notation:**

```
RE_CNV = /(copy[- ]number|\bcnv\b|micro(?:deletion|duplication)|\bdeletion\b|\bduplication\b|\bdel\(|\bdup\(|\)x[0-4]\b|\bx[0134]\b|whole[- ]gene|exons?\s*\d+(?:\s*[-–]\s*\d+)?\s*(?:del|dup))/i
```

This gives `cnv`, group = `whole-gene-deletion`. The UI must add that a larger deletion can remove
neighbouring genes too: the `contiguous-gene-deletion` group exists for that, but the notation
alone cannot tell which case applies.

**Mapping the fallback consequence to a group:**

| consequence | group |
|---|---|
| nonsense, frameshift, start-lost | truncating |
| splice | splice |
| missense | missense |
| cnv | whole-gene-deletion |
| inframe_indel, synonymous, other | none |

Use the group only if `vg:<GENE>:<slug>` is listed in `variant_groups`; otherwise set it to `null`.
The fallback status is `not_in_clinvar_plp` when a gene is known, and `not_found_no_gene` when it
is not. Always show: "The type shown is read from the notation only".

## Result shape (as returned by `lookup()`)

```
{ query: {raw, gene, gene_source, transcript, c, p, cnv, non_slice_gene},
  status: "clinvar_match" | "not_in_clinvar_plp" | "not_found_no_gene" | "gene_not_in_atlas" | "unparsed",
  match_on?: "c" | "p" | "isoform",
  matches: [ {gene, accession, url, hgvs, p, protein_change, consequence, classification, stars,
              n_submissions, variant_group} ],
  fallback: null | {consequence, certainty, note, variant_group},
  warnings: string[] }
```

## Known limits

- No reference sequence is bundled, so an exonic `c.` substitution typed without its `p.`
  cannot be turned into a protein change.
- Genomic (`g.`, `NC_`) and cytoband notations are recognised only as copy-number wording. They
  are not matched to coordinates.
- `meta.qa_differences_vs_graph_group_counts` lists where these per-record groups differ from the
  `clinvar_counts` on the graph's variant_group nodes. The biology classifier puts some small
  indels annotated to two overlapping genes into the multi-gene CNV group. Example: SLC6A1 has 73
  truncating records here versus 60 on the node. The lookup uses the per-record consequence,
  which is the correct one for a family.
