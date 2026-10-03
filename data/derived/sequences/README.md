# Reference sequences for the 45 deep-atlas genes

This folder holds the reference sequence for each of the 45 deep-atlas genes (the `disease:<GENE>`
nodes in `data/graph.json`), plus synthetic example files for testing the sequence/VCF checker. The
reference is the **MANE Select** transcript, fetched from the Ensembl REST API by
`pipeline/derive/sequences.py`. Re-run it with `--refresh` to re-fetch. Ensembl responses are
cached in `data/raw/downloads/ensembl_seq/` (gitignored).

## `<GENE>.json`

```json
{"gene": "STXBP1", "assembly": "GRCh38", "ensembl_gene": "ENSG00000136854",
 "transcript": "ENST00000373299.5", "refseq": "NM_001032221.6", "mane": "MANE_Select",
 "strand": 1, "chrom": "9", "cds_length": 1785, "protein_length": 594,
 "exons": [{"number": 1, "id": "ENSE...", "chrom": "9", "start": 127612277, "end": 127612440, "strand": 1,
            "cds_start": 1, "cds_end": 37, "coding_genomic_start": 127612404, "coding_genomic_end": 127612440}, ...],
 "grch37": {"available": true, "transcript": "ENST00000373299.1", "chrom": "9", "strand": 1,
            "exons": [... same fields on GRCh37 ...], "method": "same Ensembl transcript on grch37.rest.ensembl.org"},
 "cds": "ATGGCCCCCATT...", "protein": "MAPIGLKAVVGE..."}
```

How to read the exon fields:

- **Order.** Exons are listed in transcript order, 5′ to 3′.
- **`cds_start` / `cds_end`.** These are positions in c. numbering, so `c.1` is the A of the ATG.
  They are `null` for an exon that is UTR only.
- **`coding_genomic_start` / `coding_genomic_end`.** These are the genomic span of the coding part
  of the exon.
- **Converting a genomic position to c.** Find the exon whose coding span contains the position.
  - Plus strand: `c = cds_start + (pos − coding_genomic_start)`.
  - Minus strand: `c = cds_start + (coding_genomic_end − pos)`.
  - On the minus strand, also complement the bases.
- **Intronic positions.** These need the nearest exon edge, written as `c.N+d` or `c.N−d`.

GRCh37 coordinates:

- All 45 genes have them.
- For 37 genes, the same Ensembl transcript exists on GRCh37 with the same CDS length.
- For 8 genes, there is no matching GRCh37 transcript: SCN1A, CDKL5, CLN3, BRAF, SCN8A, LZTR1 and
  SYNGAP1, plus IDUA, whose old transcript has a different CDS. For these, each GRCh38 exon was
  projected with Ensembl `/map/human/GRCh38/.../GRCh37` and kept only if every exon maps as one
  block of the same length.
- `grch37.method` says which route each gene took.

Built-in check: STXBP1 `c.1162` maps through these tables to GRCh38 9:127675855 and GRCh37
9:130438134. Both match ClinVar VCV000006730, and the reference base at both is C, fetched from the
genome.

`index.json` lists each gene with its transcript, RefSeq id, chromosome, strand, CDS and protein
lengths, exon count and file name.

## Variant genomic positions: `data/derived/variant_positions.json`

Built by `pipeline/derive/variant_positions.py`, offline, from the stored ClinVar esummary records.
`variants.json` is not changed. It covers the 1,348 ClinVar P/LP variants of the 11 SNARE-slice
genes. Every key points to a list of accessions in `variants.json`:

| key | when |
|---|---|
| `GRCh38:<chr>:<pos>:<ref>:<alt>` | Substitutions (SNV/MNV), taken from ClinVar's canonical SPDI. 555 variants. |
| `GRCh37:<chr>:<pos>:<ref>:<alt>` | The same substitutions on GRCh37. The position comes from ClinVar's GRCh37 `variation_loc`. Ref/alt come from ClinVar where given, otherwise from the GRCh38 SPDI; `grch37_ref_alt_from` flags those. |
| `SPDI:GRCh38:<chr>:<pos0>:<del>:<ins>` | Indels, in ClinVar's canonical SPDI form: 0-based, with no anchor base. |
| `POS:<assembly>:<chr>:<start>-<stop>` | Position-level fallback for anything else (CNVs, indels on GRCh37). |

## Reading a VCF (rules for the checker)

**1. Detect the assembly.** Take the first rule that fires:

1. **`##reference=` header.** It contains `GRCh38`, `hg38` or `GCA_000001405.15` → GRCh38. It
   contains `GRCh37`, `hg19`, `b37` or `GCA_000001405.1` → GRCh37.
2. **`##contig=<ID=...,length=...>` lengths.** Compare against the two assemblies. Chromosome 9 is
   138,394,717 on GRCh38 and 141,213,431 on GRCh37; chromosome 17 is 83,257,441 and 81,195,210;
   chromosome 1 is 248,956,422 and 249,250,621. Also accept `assembly=` inside the contig line.
3. **Ask the user.** Never guess silently. If a file states one assembly but its contig lengths
   match the other, show both and ask.

**2. Normalise each line.**

- Strip a `chr` prefix, and map `MT` to `M`.
- Split multi-allelic `ALT` into one record per allele.
- **Substitution** (`len(REF) == len(ALT)`): look up `<asm>:<chr>:<POS>:<REF>:<ALT>`.
- **Indel:** drop the shared leading anchor base, then look up
  `SPDI:GRCh38:<chr>:<POS>:<rest of REF>:<rest of ALT>`. After dropping one anchor base, the VCF's
  1-based POS equals SPDI's 0-based position.
  - SPDI is fully justified while callers left-align, so an indel inside a repeat may miss. If it
    does, fall back to `POS:` keys overlapping the span, and say the match is position-only.
- **No exact key:** map the position to c. notation with the exon tables above, and run the
  pattern fallback from `variant_lookup_spec.md`.

**3. Warn on every result.** "ClinVar P/LP only; not a diagnosis."

## Examples (`examples/`, SYNTHETIC, not real people)

Every file says **"SYNTHETIC EXAMPLE – not a real person"**: in the FASTA header line, or in a
`##comment` line in the VCFs.

| File | What it is |
|---|---|
| `STXBP1_reference_no_change.fasta` | The MANE CDS of STXBP1, unchanged. |
| `STXBP1_c.1162C>T_p.Arg388Ter.fasta` | The STXBP1 CDS with c.1162C>T (ClinVar VCV000006730, Pathogenic; present in `variants.json`). The script asserts that the reference base is C before editing. |
| `SCN2A_c.468G>C_p.Lys156Asn.fasta` | The SCN2A CDS with c.468G>C (ClinVar VCV003343696, Pathogenic missense on the MANE RefSeq NM_001040142.2). **SCN2A is not in `variants.json`**, which covers only the 11 SNARE-slice genes, so this variant was chosen from ClinVar directly: the best-reviewed Pathogenic missense SNV, cached as `data/raw/downloads/clinvar_SCN2A_*.json`. |
| `STXBP1_c.1162C>T_GRCh38.vcf` | VCF 4.2 with `##reference`, `##contig` (chromosome 9 length from Ensembl) and two lines: the variant at 9:127675855 C>T, and a benign-looking off-target SNV deep in STXBP1 intron 1 (9:127614440). The off-target line's REF comes from the genome, and the script asserts it is not in the atlas's ClinVar P/LP set. |
| `STXBP1_c.1162C>T_GRCh37.vcf` | The same variant on GRCh37: 9:130438134 C>T. |
