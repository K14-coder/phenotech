# Family: lysosomal storage disorders

Output: `data/curated/family_lysosomal.json` (one fragment in SCHEMA shape `{nodes, edges, clusters, gaps}`), built
2026-10-04. Scripts: `pipeline/families/lysosomal/`. Raw responses: `data/raw/families/lysosomal/`.

Genes: GBA1, GAA, GLA, HEXA, NPC1, SMPD1, IDUA, IDS, CLN3, TPP1, ARSA, GALC. Every disease and gene node carries
`attrs.family = "lysosomal"`. Ids follow `docs/SCHEMA.md`. Shared nodes are referenced, not redefined:
`mech:protein-destabilization`, `mech:loss-of-function`, existing `phenotype:HP:*` nodes, `disease:SLC6A1`,
`disease:STXBP1` and `therapy:4-phenylbutyrate`.

## Counts

| Nodes | n | Edges | n |
|---|---|---|---|
| phenotype (new; others reused) | 166 | has_phenotype | 213 |
| study (ClinicalTrials.gov) | 62 | studies / tests | 68 / 44 |
| variant_group (ClinVar) | 59 | variant_in / has_effect | 59 / 40 |
| patient_org | 28 | serves | 34 |
| researcher | 27 | works_on | 27 |
| asset (registries, natural history, networks, grants) | 24 | covers / maintains | 29 / 4 |
| therapy | 18 (12 approved, 6 clinical) | developed_for / targets | 21 / 17 |
| disease / gene | 12 / 12 | causes | 12 |
| mechanism | 8 (2 family + 6 GO processes) | driven_by / participates_in | 28 / 18 |
| | | shares_mechanism / similar_phenotype | 29 / 10 |
| **416 nodes** | | **653 edges** | |

The fragment also has 3 clusters and 7 gaps. Edge status: 611 supported, 7 contested, 35 unverified. The unverified
ones are the consequence-class loss-of-function inferences; they are labelled `inferred`. 14 edges carry
`counter_evidence`. 100 distinct PMIDs, 19 FDA labels and 62 trial records back the edges.

## Verification

- **`verify.py`: 594 of 594 quotes verified, 0 failures.** It is independent of the curation code and re-reads each stored source:
  - PubMed: 256 quotes, against `pubmed/<PMID>.json`.
  - Website: 167 quotes. These are FDA labels (from `fda/<slug>.json`, matched by DailyMed set id) and organisation pages (from `web/<id>.txt`).
  - ClinicalTrials.gov: 148 quotes, against `ctgov/studies/<NCT>.json`.
  - UniProt: 12; GO: 6.
- 0 dangling edge endpoints, 0 missing cluster members, 0 duplicate ids.
- No quote is typed by hand. `curation.py` stores short needles, and `lyso_common.quote_for()` returns the single stored sentence containing each needle; it raises if the needle is missing or ambiguous. All 92 needles resolve. Org quotes are checked by `check_orgs.py` (exit 0).
- **`python3 pipeline/build_graph.py`: "Problems: None."** The merged graph has 1,963 of 1,963 quotes verified. One attribute conflict is listed (`therapy:4-phenylbutyrate` modality); it predates this family.
- Source checks that changed the data:
  - **UniProt alias matches.** UniProt's `gene_exact` search returned NAT8 for "GLA" and GET3 for "ARSA" (both are aliases). The fetch now requires the primary gene name.
  - **Susceptibility links excluded.** GBA1's Parkinson disease and Lewy body dementia links are `contributes_to` / "major susceptibility factor", so they are not counted as causal.

## How to re-run

```bash
pipeline/families/lysosomal/run.sh        # all steps; cached responses make it offline-fast
```

Steps, in order:

1. `fetch_biology.py`: HGNC, UniProt, Ensembl MANE CDS, Monarch v3, Orphadata association types, Open Targets G2P/ClinGen.
2. `clinvar.py`: ClinVar P/LP spectrum, using the biology layer's consequence classifier.
3. `hpo.py`: reuses `pipeline/biology/hpo.py` parsing, IC over 12,867 diseases, Resnik BMA with per-disease background percentiles, and the same cross-family test against the SNAREopathy profiles.
4. `fetch_fda.py`: openFDA labels.
5. `fetch_ctgov.py`: ClinicalTrials.gov v2.
6. `fetch_web.py` and `check_orgs.py`: organisation pages and their quote check.
7. `curation.py`: claim needles.
8. `research_groups.py`: senior authors.
9. `build_fragment.py`, then `verify.py --write`, then `pipeline/build_graph.py`.

NCBI calls go through the shared file-lock throttle in `pipeline/biology/common.py` (≤2 req/s, `tool=rare-disease-atlas`, no email param, backoff on 429). Bright Data requests used: **0**; the budgeted wrapper is in `lyso_common.py`. No OpenAI calls were made.

## Five most interesting evidence-backed connections

1. **A misfolding bridge across families: NPC1 and GLA to SLC6A1.** Both are `shares_mechanism` edges, inferred, confidence 0.4, with counter-evidence attached.
   - **NPC1 side.** The most common NPC1 variant (I1061T) makes an unstable protein destroyed by ER-associated degradation (PMID:24891511). Arimoclomol, which "amplifies the heat shock response to target NPC protein misfolding" (PMID:34418116), is FDA-approved with miglustat.
   - **SLC6A1 side.** GAT-1 variants misfold and are retained in the ER (PMID:34028503), and 4-phenylbutyrate restored surface GAT-1 (PMID:42157447). This is the SNAREopathy layer's existing chaperone bridge.
   - **GLA side.** Migalastat is the approved pharmacological chaperone for amenable GLA variants (GALAFOLD label; PMID:27834756).
   - **Limits, kept visible.** The Miplyffa label says arimoclomol's mechanism in NPC is "unknown". About a third of SLC6A1 loss-of-function missense variants reach the cell surface, so a chaperone cannot help them (PMID:38781976).
   - `cluster:lysosomal-chaperone-responsive-misfolding` groups GLA, GBA1 (ambroxol), HEXA (pyrimethamine), NPC1, GAA, STXBP1 and SLC6A1.
2. **Approved enzymes treat the body, not the brain, and the labels say so.**
   - The current Cerezyme label covers only "non-central nervous system (CNS) manifestations" of type 1 or 3 Gaucher disease. Xenpozyme (ASMD) has the same wording, and laronidase "does not cross the blood-brain barrier" (PMID:15895714).
   - The brain-first diseases are reached only by workarounds:
     - enzyme infused into the brain ventricles (cerliponase alfa for CLN2; NEJM PMID:29688815, label);
     - gene-corrected stem cells (atidarsagene autotemcel for MLD; Lenmeldy label, EMA approval PMID:36811406);
     - early stem-cell transplant (Krabbe);
     - a transferrin-receptor fusion enzyme (pabinafusp alfa for MPS II);
     - small molecules that cross the barrier (miglustat, ambroxol).
   - See `cluster:lysosomal-bbb-barrier`.
3. **Approved versus unapproved.** 9 of the 12 diseases have an approved therapy (`attrs.approved_treatment`). The three without one are Tay-Sachs (HEXA), CLN3 and Krabbe (GALC), and all three are dominated by brain disease. A CLN3 study states "No disease-modifying treatments are currently available" (PMID:40924969). The SNAREopathies have no approved disease-specific drug at all, so this family is the reference point for what a mature therapy landscape looks like.
4. **Miglustat is one approved drug spanning four diseases with four roles.**
   - Substrate reduction for type 1 Gaucher disease (ZAVESCA label).
   - The approved drug for neurological NPC (PMID:24338084); it crosses the blood-brain barrier (PMID:17689147).
   - An *enzyme stabilizer* for cipaglucosidase alfa in Pompe disease (OPFOLDA label).
   - An open-label study in CLN3 disease (PMID:40924969).
   - Levacetylleucine adds another within-family bridge: it improved ataxia in an NPC randomised trial (PMID:38294974) and is in a GM2/Tay-Sachs trial (NCT03759665).
5. **Phenotype similarity recovers the textbook groupings without being told them.** IC-weighted Resnik BMA, using the same thresholds as the SNAREopathy layer, links:
   - MPS I and MPS II (top pair, BMA 2.65);
   - MLD and Krabbe (leukodystrophies);
   - Gaucher disease and ASMD, and NPC and ASMD (the old "Niemann-Pick" grouping);
   - CLN3 and CLN2 (neuronal ceroid lipofuscinoses).

   **No cross-family phenotype edge passes the threshold.** The near misses are recorded in a gap, not drawn: TPP1–STXBP1, GAA–SYT2 (two causes of neuromuscular weakness) and GALC–UNC13A all sit in the top 5% of both backgrounds but not the top 1% of either.

## Clusters

- `cluster:lysosomal-family` (basis: pathway): "Lysosomal storage disorders: one organelle, many enzymes".
- `cluster:lysosomal-chaperone-responsive-misfolding` (basis: mechanism).
- `cluster:lysosomal-bbb-barrier` (basis: mechanism).

## Gaps (each lists the searches run)

- `gap:lysosomal-no-approved-therapy`: HEXA, CLN3 and GALC.
- `gap:lysosomal-cns-forms-untreated`: neuronopathic Gaucher, ASMD type A, Hurler and neuronopathic MPS II. Pabinafusp alfa and levacetylleucine approvals could not be verified from a fetched label, so both are recorded as `clinical`.
- `gap:lysosomal-chaperone-amenability-map`: only GLA has a variant-level amenability test.
- `gap:lysosomal-cln3-function`: CLN3 has no enzyme or loss-of-function mechanism edge.
- `gap:lysosomal-cross-family-phenotype`: the near misses above.
- `gap:lysosomal-gba1-parkinson`: the susceptibility links that were excluded.
- `gap:lysosomal-community-coverage`:
  - CLN2 has only one organisation;
  - several CLN3 organisations name only "Batten disease" (their `serves` edges are marked `inferred`, 0.6);
  - no registry page was verified for Gaucher, Fabry, Tay-Sachs, MPS II or MLD (ClinicalTrials.gov registry studies are used instead);
  - no research group met the threshold for Gaucher, MPS I or MPS II;
  - NIH RePORTER was not searched for this family.

## Caveats

- Research groups use a simple rule: senior author on at least 2 of the 80 most recent title-matched papers. A few institution slugs are department-level (e.g. `bone-marrow-transplantation-unit`).
- Study selection: per disease, up to 4 interventional studies (preferring ones that test a therapy node, then by phase) and up to 2 registry or natural-history studies. Each study links to its disease through a verbatim condition string.
- FDA labels are cited as `source: "Website"` with the DailyMed URL, because the schema has no FDA source value.
