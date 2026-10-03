# Community & Assets layer: agent report

Output: `data/curated/community.json` (schema v0.1: `{nodes, edges, clusters: [], gaps}`), built 2026-10-03.
It references the biology layer's `disease:<GENE>` and `gene:<GENE>` IDs and does not create them.

## What is in it

| Node type | Count | | Edge type | Count |
|---|---|---|---|---|
| patient_org | 20 | | serves (org → disease) | 23 |
| asset | 19 | | covers (asset → disease) | 27 |
| study (ClinicalTrials.gov) | 18 | | maintains (org/researcher → asset) | 20 |
| therapy | 5 | | studies (study → disease) | 25 |
| grant (NIH RePORTER) | 24 | | tests / developed_for | 6 / 2 |
| researcher | 114 | | about (grant → disease/gene) | 25 |
| | | | funds (grant → researcher) | 31 |
| | | | works_on (researcher → disease/gene) | 121 |
| gaps | 27 | | | |

Per disease, counting edges into `disease:<GENE>`:

| Disease | Gene-specific orgs / umbrella | Assets | Studies obs / interventional | Grants | Researchers |
|---|---|---|---|---|---|
| STXBP1 | 9 / 2 | 12 | 9 / 3 | 8 | 19 |
| SLC6A1 | 6 / 1 | 5 | 2 / 3 | 5 | 22 |
| SYT1 | 1 / 0 | 3 | 2 / 0 | 4 | 20 |
| SNAP25 | 1 / 1 | 3 | 1 / 1 | 1 | 15 |
| VAMP2 | 1 / 0 | 2 | 3 / 0 | 1 | 8 |
| SYT2 | 0 / 1 (MDA, inferred) | 1 | 0 / 1 | 1 | 8 |
| UNC13A | 0 / 0 | 1 | 0 / 0 | 1 | 5 |
| STX1B | 0 / 0 | 0 | 0 / 0 | 0 | 10 |
| STX1A | 0 / 0 | 0 | 0 / 0 | 0 | 4 |
| NSF | 0 / 0 | 0 | 0 / 0 | 0 | 3 |
| CPLX1 | 0 / 0 | 0 | 0 / 0 | 0 | 1 |

## Evidence integrity rules (enforced in code)

- **Website claims**: every quote is string-matched (after whitespace and quote normalisation) against the page stored in `data/raw/community/web/<id>.txt` (or `.html` for link-only evidence). A quote that does not match is dropped. The final build dropped 0 quotes and set `verified: true` on every quote.
- **PubMed / RePORTER / CT.gov quotes** are extracted verbatim from the stored API records:
  - PubMed: the sentence tying the gene to the disorder.
  - RePORTER: the abstract sentence.
  - CT.gov: the eligibility or condition snippet, verified against the raw record.
- **`works_on` from PubMed**: senior (last) author only, papers from 2018 on. A paper counts only if:
  - the gene is a focus (in the title, or in at least 2 abstract sentences while no other slice gene is in the title);
  - a sentence ties the gene to a human disorder (patients, variants, encephalopathy, epilepsy, CMS and similar terms);
  - that sentence does not name another disease context (ALS/FTD, Parkinson's/PD, Alzheimer's, SMA, Shiga toxin `stx1a`, the SNARE acronym "NSF attachment protein", and others);
  - it is not a review, an erratum, or a gene-panel sentence listing 3 or more other genes.
  
  Two PMIDs were excluded by hand, with reasons, in `pipeline/community/pubmed_exclusions.json`.
- **Grant → disease** needs an abstract or title sentence tying the gene to patients or variants. Grants whose titles name another disease (e.g. UNC13A ASO for ALS/FTD, VAMP2 in alpha-synuclein) get **gene-level** `about` edges only.
- **Privacy**: no personal e-mails, phones, addresses or social-media handles. E-mail addresses are redacted from every saved raw file, including PubMed affiliations. SLC6A1 Europe's contact persons, which appear on the Swiss page, were not recorded.

## How to re-run

```bash
cd pipeline/community
python3 fetch_ctgov.py      # ClinicalTrials.gov API v2 -> data/raw/community/ctgov/
python3 fetch_reporter.py   # NIH RePORTER v2, FY2020-2026, >=1.2 s between calls -> data/raw/community/reporter/
python3 fetch_pubmed.py     # E-utilities, <=2 req/s, tool=rare-disease-atlas, no email, 429 backoff -> data/raw/community/pubmed/
python3 fetch_web.py        # org pages in web_sources.json (via=brightdata entries use pipeline/brightdata.py)
python3 bd_discover.py      # optional: Bright Data Google searches for org discovery (cached)
python3 build_community.py  # -> data/curated/community.json + data/raw/community/build_summary.json
python3 fetch_web.py --grep 'regex' --only id1,id2   # search stored pages when curating quotes
```

Everything is stdlib Python. Curation inputs:
- `curated_orgs.json`: orgs and assets, each with quotes;
- `study_curation.json`: which slice diseases each NCT really enrols, with eligibility snippets, excluded NCTs and therapy definitions;
- `search_log.json`: the exact searches run, which feed `gaps[].searched`.

## Top reusable assets (what can be shared)

1. **Simons Searchlight**: an online registry, natural history study and biorepository that covers **STXBP1, SLC6A1, SNAP25 and VAMP2** (NCT01238250, recruiting, about 100k target enrolment). Sources: SLC6A1 Connect registry page; simonssearchlight.org gene pages; the STXBP1 Foundation STARR page ("You may have been in other studies about STXBP1 such as Citizen Health, Simons Searchlight, or RARE-X").
2. **Phenylbutyrate shared protocol, NCT04937062**: one STXBP1/SLC6A1 arm ("Diagnosed with STXBP1-E or SLC6A1-NDD"). Weill Cornell sponsors it, with STXBP1 Foundation, SLC6A1 Connect, Children's Hospital Colorado and the Penn Orphan Disease Center as collaborators. A follow-on fully remote SLC6A1 trial is NCT07847918 (Scripps, Phase 2, recruiting). This is the clearest existing cross-gene trial design.
3. **Amifampridine for genetically confirmed CMS, NCT02562066**: a completed Phase 3 by Catalyst. Eligibility explicitly includes "SYT2 deficiency,SNAP25B deficiency". It is the only interventional record for SYT2 and the only CMS-type trial touching SNAP25.
4. **COMBINEDBrain shared infrastructure**: a biorepository with STXBP1 and SLC6A1 samples, plus the PAG Matrix natural-history portals ("CombinedBrain and Across Matrix have teamed up to provide a platform for a SLC6A1 Natural History Study"). The consortium spans more than 130 rare neurological disorder communities.
5. **CMDIR (Congenital Muscle Disease International Registry)**: its gene list includes **SNAP25, SYT2 and UNC13A**. It is the only registry found for SYT2 and UNC13A.
6. **STXBP1 Foundation stack**:
   - STARR natural history study (= NCT06555965; 5 US sites, led by Ingo Helbig at CHOP per ENDD);
   - S-COMB outcome-measure and biomarker consortium, which advises STARR and ESCO;
   - grants program;
   - Stxbp1 floxed-null mouse available via the InnoSer CRO;
   - Xue lab haploinsufficient mice;
   - ENDD (Penn/CHOP) models "readily be shared".
   
   ESCO adds a European registry and natural history study (NCT06625112; its site shows 181 people in the registry and 28 in the natural history study). Heidelberg runs a separate STXBP1 registry.
7. **Epilepsy-dyskinesia registry and survey at Boston Children's** (NCT06967727, NCT06585605): eligibility gene lists include **STXBP1 and VAMP2**. This is the only registry-type study naming VAMP2 apart from Simons Searchlight.
8. **Citizen Health** (STXBP1, SLC6A1) and **RARE-X** (SNAP25 Data Collection Program; STXBP1): medical-record and patient-reported data platforms.

## Network overlap (bridges across 2 or more slice diseases)

**Multi-gene studies**, flagged with `attrs.multi_gene_slice`:

| Study | Diseases |
|---|---|
| NCT01238250 | STXBP1, SLC6A1, SNAP25, VAMP2 |
| NCT04937062 | STXBP1, SLC6A1 |
| NCT06967727 | STXBP1, VAMP2 |
| NCT06585605 | STXBP1, VAMP2 |
| NCT02562066 | SYT2, SNAP25 |

**Sponsors and collaborators across diseases:**
- Boston Children's Hospital (3 studies, 4 diseases);
- Weill Cornell, STXBP1 Foundation, SLC6A1 Connect and Children's Hospital Colorado (all on the STXBP1+SLC6A1 trial);
- Catalyst Pharmaceuticals (SYT2+SNAP25).

**Orgs and assets serving 2 or more diseases:** Simons Searchlight (4), CMDIR (3), DEE-P Connections (3, inferred from partner links), COMBINEDBrain (2), COMBINEDBrain biorepository (2), Citizen Health (2), RARE-X (2).

**Researchers** (`attrs.bridges_diseases`):

| Researcher | Diseases | Evidence |
|---|---|---|
| Ege Kavalali, Vanderbilt | SNAP25, SYT1, VAMP2 | R01NS134128 plus PMIDs 42661025, 41756855, 41166419 |
| Zachary M. Grinspan, Weill Cornell | STXBP1, SLC6A1 | PMID 42447769, the phenylbutyrate report |
| Scott Demarest, U. Colorado | STXBP1, SLC6A1 | PMID 40767165, CVI across NDDs |
| J. (Troy) Littleton, MIT | SYT1, SYT2 | R01NS040296: "mutations in human Syt1 and Syt2" |
| Konrad Platzer, Leipzig | SNAP25, STX1A | PMIDs 33299146, 36564538 |
| Fei Xiao, Chongqing | STX1B, STXBP1 | |

**Name disambiguation:**
- Same name means the same node only with an exact name **and** institution match, or a shared ORCID. ORCIDs come from PubMed author records. RePORTER PIs were linked to PubMed authors only by exact name + institution.
- "Ege Kavalali" (Vanderbilt) and "Ege T Kavalali" (UT Southwestern) were **not merged**. He probably moved, but affiliations differ and there is no shared ORCID. Both nodes carry `possible_same_person_as`. The same applies to Jeremy Dittman (Yale vs Weill Cornell).
- Ingo Helbig was merged across "CHILDREN'S HOSP OF PHILADELPHIA" (RePORTER) and "Children's Hospital of Philadelphia" (PubMed) by an institution alias.

**Website-only signals, not edges:**
- The STXBP1 Foundation SAB includes Ingo Helbig (CHOP), Matthijs Verhage (VU Amsterdam) and Jose Rizo-Rey (UT Southwestern).
- The Snap25 Foundation SAB lists Baris Alten, Jacqueline Burré and Wendy Chung.
- The COMBINEDBrain SAB includes Mingshan Xue and Hannah Stamberger.

## Gaps (27 records in `gaps`, each with the exact searches run)

- **No gene-specific patient organisation**: STX1B, SYT2, CPLX1, UNC13A, STX1A, NSF.
  - SYT2 has only an inferred umbrella: MDA covers presynaptic CMS, but its page does not name SYT2.
  - Searches covered web and Bright Data Google, NORD and Global Genes, the DEE-P partner list, Citizen Health communities, the COMBINEDBrain PAG list, Simons Searchlight genes, the STXBP1 Foundation partners and the CMDIR gene list.
- **No registry or natural history study**: STX1B, CPLX1, STX1A, NSF.
- **No interventional trial**: SYT1, VAMP2, STX1B, CPLX1, UNC13A, STX1A, NSF. The only UNC13A-directed trial (NCT07674667, TRCN-1023) is in ALS and is recorded as adjacent, not linked.
- **No verified model asset**: every disease except STXBP1. MGI/JAX, hPSCreg and EBiSC were **not** systematically searched in this pass.
  - The VAMP2 MRC project mentions a mouse with a human mutation.
  - A CPLX1 patient iPSC line paper exists (PMID 38110787, KAIMRCi003A/B) but is not yet an asset node.

## Caveats and next steps

- Orphanet pages are JavaScript-rendered and returned no text even via Bright Data, so the Orphanet directory was not usable.
- globalgenes.org returned 403 to the direct fetcher but worked via Bright Data.
- Bright Data use: 28 searches (6 transient SERP errors) and 11 unlocker fetches. Snippets were used only for discovery; every claim was quoted from the fetched page.
- Researcher selection uses the top 15 senior authors per gene, so recall for STXBP1 and SLC6A1 is deliberately limited in favour of precision.
- Not found or not resolvable:
  - SLC6A1 Europe's own domain (slc6a1europe.org) and vzw-gen.be did not resolve, so the alliance is an asset sourced from SLC6A1 Switzerland's page;
  - the national STXBP1 groups in Brazil and Slovakia were not added (no resolvable site, or no STXBP1 quote).
- Next: add MGI/JAX alleles and the CPLX1 iPSC line as `animal_model` / `cell_model` assets, and add SAB membership edges once the schema has a researcher→org relation.
