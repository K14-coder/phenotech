# Research recommendations

Every atlas disease card (`/disease/<GENE>`, in the detailed view, after "Question 1") now has a
**Research recommendations** section. It names the closest other atlas disease for four questions and says why:

| Category | Question | Score |
|---|---|---|
| Mechanistic | Does the gene break the same way? | 0.30 mutation type + 0.35 molecular consequence (protein fate) + 0.35 3D structure accordance |
| Funding | Do they share a signalling pathway, so the same funders are plausible? | mechsim `pathway` axis (IDF-weighted shared canonical pathways, combined with a STRING interaction) |
| Tissue / delivery | Would a drug reach the same tissue the same way? | mechsim `tissue` axis (symptom-tissue cosine + GTEx expression correlation), plus a rule-based delivery route |
| Symptoms | Do they share distinctive symptoms? | IC-weighted Jaccard of HPO features; shared terms with IC >= 4 are listed |

Everything is computed, so every output is **inferred** (a hypothesis to check), never a fact. Treatment ideas, including
short-term symptom relief suggested by a symptom match, are always framed "to discuss with your clinician".

## How it is computed

`pipeline/derive/research_recs.py` reads the six-axis mechanistic similarity layer (`data/derived/mechsim.json`) and
keeps only the 45 atlas diseases (990 pairs).

**Mechanistic closeness.** Each marker is converted into its percentile among all 17,578 mechsim pairs (atlas and
ion-channel panel). This puts the three markers on one scale. The reference is fixed, so adding a disease never
re-scales the others.

- *Mutation type*: mechsim `mutation` (1 - Jensen-Shannon distance of the ClinVar P/LP variant-type spectra). It is
  missing when a gene has fewer than 10 P/LP variants (CPLX1, NSF, SYT2, ...).
- *Molecular consequence*: mechsim `fate` (cosine of the predicted protein-fate profile: absent, degraded, inactive,
  dominant negative, hyperactive, accumulates).
- *3D structure*: the TM-score between the two protein models, using the larger of the two normalisations, as mechsim
  does. Each disease is represented by an **experimental PDB structure that carries a ClinVar P/LP missense change**
  when one exists. Otherwise it uses the **AlphaFold DB v4 WT model** (residues with pLDDT >= 70). When both diseases
  use WT models, the parent layer's all-vs-all TM-score is reused. Alignments that involve an experimental mutant are
  run here with tmtools and cached in `data/raw/derive/research_recs_tmalign.jsonl`.

When a marker cannot be scored, it is dropped and the remaining weights are renormalised. The record lists the missing
marker in `missing`, and the card says "not scored". No gap is filled with an invented value.

**Funding.** The closest pathway partner is listed with its shared pathways. Human and mouse MSigDB sets that carry the
same name are shown once. The card also lists the partner's funders that the disease itself lacks. Funders come from
NIH RePORTER `grant` nodes linked by `about` edges; the NIH institute is taken from `attrs.agency` or from the project
number (NS → NINDS, DK → NIDDK, HD → NICHD, MH → NIMH, ...). Named `funding_program` assets (AMDA, ArchAngel MLD Trust,
STXBP1 Foundation) linked by `covers` edges also count. Grant coverage in the graph is mostly DEE and SNAREopathy, so
`funders_via_pathway_partners` also lists the missing funders reached through any of the top-10 pathway partners.

**Tissue / delivery** is rule-based and inferred:

- *Lysosomal enzyme* (`is_enzyme` and a lysosomal location): intravenous ERT for body organs. If at least 15% of the
  symptom-tissue profile is brain, the card adds that ERT does not cross the blood-brain barrier, so the brain needs
  intrathecal or ICV enzyme, or AAV9.
- *CNS* (brain is the top symptom tissue or at least 30% of the profile): intrathecal or ICV AAV9, or an intrathecal ASO.
- *Otherwise systemic*: an oral or IV small molecule, or a liver-directed LNP where the liver is a target.

AAV fit comes from `gene.attrs.aav_cds_fits_4_7kb`. When that attribute is absent (the 12 RASopathy genes), it is
computed from `cds_length_bp` against about 4,700 bp, and the source is recorded.

**Symptoms.** The score is the IC-weighted Jaccard over the full HPO annotation sets in `data/raw/comparison/hpo.json`.

**Clusters.** Average linkage on mechanistic closeness, cut where the average closeness is 0.70.

## Mutant structures: what was actually used

`pipeline/derive/research_recs_fetch.py` builds `data/raw/comparison/mutant_structures.json`:

1. **RCSB Search API**: every polymer entity for the 45 atlas UniProt accessions with `entity_poly.rcsb_mutation_count > 0`.
   This gives 849 entities.
2. **RCSB Data API GraphQL** on those entities returns `pdbx_mutation`, chain ids and the UniProt alignment. The result
   is stored in `data/raw/comparison/pdb_mutants.json`. rcsb.org is blocked in the build container, so both calls went
   through the TinyFish fetcher.
3. Each entity's substitutions are matched against **ClinVar P/LP germline missense** changes for the same gene, taken
   from `variant_summary`. They are saved to `data/raw/comparison/clinvar_missense.json`. A match also requires the
   reference residue to agree with the MANE protein. Author numbering is tried first, then the UniProt-alignment
   offset. This is how GBA1 "N370S" (mature numbering) maps to p.Asn409Ser.
4. **Coordinates** come from the LiteFold/PDB mirror on Hugging Face when the entry is mirrored (BRAF, CBL, HRAS, KRAS,
   PTPN11). For the other entries, the mmCIF was fetched once from files.rcsb.org through the fetcher and cached as an
   atom_site-only file in `data/raw/downloads/research_recs/`, which is not in git. That covers GBA1, SHOC2, SLC2A1
   and SYT1.
5. One representative is chosen per gene. The rule prefers entries with coordinates, then the fewest extra engineered
   mutations, then the widest UniProt coverage. It must have at least 30 CA atoms and the mutant residue must be
   visible in the coordinates.

Result: **9 genes use an experimental mutant structure**:

| Gene | PDB entity | Mutation |
|---|---|---|
| BRAF | 4EHG_1 | V600E |
| CBL | 5J3X_1 | Y371F |
| GBA1 | 3KE0_1 | N370S = p.N409S |
| HRAS | 1AGP_1 | G12D |
| KRAS | 4DSN_1 | G12D |
| PTPN11 | 4GWF_1 | Y279C |
| SHOC2 | 7TXH_2 | M173I |
| SLC2A1 | 4PYP_1 | E329Q, plus engineered N45T |
| SYT1 | 6U41_1 | D304G |

RAF1 has 7 disease-mutant entities, but all of them are 11-residue peptides bound to 14-3-3, so RAF1 uses its WT
model. The other 35 genes use the WT AlphaFold model, recorded as
`mutant_model: "not available (WT model used; no structure predictor in this environment)"`. There is no GPU, so
AlphaFold and ColabFold cannot run, and no offline side-chain repacker was used, so no mutant model was faked. When more
than half of a gene's P/LP variants are predicted to leave no stable protein, the card says so: the structure marker
then describes the protein made by the missense minority.

Some matched substitutions were engineered for mechanistic studies but are also listed as P/LP in ClinVar, for example
SLC2A1 E329Q (a conformation-locking mutant) and CBL Y371F. They count under the rule, and the card names the PDB entry
so a reader can judge.

## Incremental update (`--add GENE`)

`data/raw/derive/research_recs_state.json` stores, for each disease, the cached features (pathways, HPO terms with IC,
structure model, delivery, funders), the pair scores, the sorted top-10 list per category and the clusters.
`--add GENE` works as follows:

1. Compute the new disease's features and its n pair scores. This reads mechsim rows and runs TM-align only for a pair
   that involves an experimental mutant and is not yet cached.
2. Take the new disease's own top-k with `heapq.nsmallest`, which is O(n log k).
3. Insert the new disease into each stored top-k list with `bisect.insort` and truncate. That is n × O(log k).
4. Join the cluster with the highest average linkage at or above 0.70, or start a new cluster.

Ties are broken by gene name and scores are rounded, so the incremental and full builds produce identical lists.

`python3 pipeline/derive/test_research_recs.py` holds out SCN8A, GAA and HRAS in turn. For each one it runs a full
build without the gene, adds it back incrementally, and compares all 180 top-10 lists with a full recompute.
**Result: 0 differences for all three (PASS).** The same check through the CLI (`--exclude SCN8A`, then `--add SCN8A`)
produced byte-identical `best` and `top` blocks.

Cluster membership does not have to match. Greedy average-linkage assignment can differ from re-clustering everything:
it matched for HRAS, but not for SCN8A or GAA. Re-run the full build to re-cluster.

## Rerun

```bash
python3 pipeline/derive/research_recs_fetch.py   # only if pdb_mutants.json or ClinVar changed (needs data/raw/downloads/mechsim/clinvar_subset.tsv)
python3 pipeline/derive/research_recs.py         # full build (< 1 s with the TM cache; ~2.5 min cold)
python3 pipeline/derive/test_research_recs.py    # --add == full recompute
node web/scripts/sync-data.mjs
```

If `mechsim.json` is regenerated (for example after the WT all-vs-all TM-align finishes), rerun `research_recs.py`.
Scores are read at run time and nothing is hard-coded.

## Caveats

- The TM-score uses the larger of the two normalisations, as mechsim does. A small protein (CPLX1 at 134 aa, VAMP2 at
  116 aa) therefore looks structurally closer to a big one than a size-symmetric score would make it.
- An experimental mutant structure is usually a fragment, such as the KRAS G-domain or the BRAF kinase domain. Comparing
  it with a partner's full-length AlphaFold model measures how well the fragment fits the partner. It is not a
  whole-protein comparison.
- Percentiles reflect the whole mechsim panel. A "64%" fate percentile can still be a raw cosine of 0.95, because most
  pairs share the null-dominated fate profile.
- Clusters follow mechanism, not disease family. For example, KCNT1 (gain of function) groups with the RAS genes, and
  CPLX1 (recessive null) groups with the lysosomal enzymes.
- Funder lists only reflect what the atlas has curated: 63 NIH grants and 3 named programmes. Funding-closeness
  partners often have no funder record yet.
- Renormalising over the available markers can favour a partner whose mutation marker is missing. A gene with fewer
  than 10 ClinVar P/LP variants is then ranked on fate and structure alone. STXBP1 → CPLX1 is an example, and the
  card shows "not scored".
- Delivery routes are a coarse rule table, not a modality assessment. See `data/curated/modality.json` for that.
