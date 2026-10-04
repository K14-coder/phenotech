# Mechanistic ranking changes (top 5, atlas diseases)

- old: `/tmp/claude-0/-home-user-rare-disease-atlas/0e99a843-ac86-5f3b-98bf-30479fd730c9/scratchpad/mechsim_baseline.json` (generated 2026-10-04, TM-align pairs 6902)
- new: `data/derived/mechsim.json` (generated 2026-10-04, TM-align pairs 17578)

## combined: 13 diseases changed

| Disease | Old top | New top | Entered | Left | Moved ≥2 |
|---|---|---|---|---|---|
| ARSA | GALC, SMPD1, HEXA, TPP1, IDUA | GALC, SMPD1, HEXA, IDUA, IDS | IDS | TPP1 | – |
| GALC | ARSA, SMPD1, HEXA, IDUA, TPP1 | ARSA, SMPD1, HEXA, IDUA, IDS | IDS | TPP1 | – |
| GRIN2B | KCNQ2, SCN2A, SNAP25, CPLX1, CACNA1A | KCNQ2, SCN2A, CPLX1, SNAP25, VAMP2 | VAMP2 | CACNA1A | – |
| KRAS | PTPN11, MAP2K1, BRAF, HRAS, SOS1 | PTPN11, HRAS, MAP2K1, BRAF, SOS1 | – | – | HRAS 4→2 |
| MAP2K1 | BRAF, PTPN11, KRAS, CBL, RAF1 | BRAF, RAF1, PTPN11, CBL, KRAS | – | – | RAF1 5→2, KRAS 3→5 |
| NSF | SYT1, SNAP25, STXBP1, VAMP2, CPLX1 | SYT1, SNAP25, STXBP1, VAMP2, HRAS | HRAS | CPLX1 | – |
| PTPN11 | KRAS, MAP2K1, CBL, BRAF, SOS1 | KRAS, MAP2K1, CBL, BRAF, HRAS | HRAS | SOS1 | – |
| SCN2A | SCN1A, KCNQ2, SCN8A, CACNA1A, GRIN2B | SCN1A, KCNQ2, SCN8A, CACNA1A, SLC6A1 | SLC6A1 | GRIN2B | – |
| SHOC2 | KRAS, HRAS, BRAF, SOS1, MAP2K1 | KRAS, BRAF, HRAS, SOS1, RAF1 | RAF1 | MAP2K1 | – |
| SLC6A1 | SLC2A1, CPLX1, SCN2A, VAMP2, SCN1A | SLC2A1, CPLX1, SCN2A, VAMP2, SNAP25 | SNAP25 | SCN1A | – |
| SOS1 | KRAS, RIT1, BRAF, RAF1, MAP2K1 | KRAS, RAF1, BRAF, RIT1, PTPN11 | PTPN11 | MAP2K1 | RAF1 4→2, RIT1 2→4 |
| STXBP1 | CPLX1, STX1B, VAMP2, SLC2A1, STX1A | CPLX1, STX1B, VAMP2, CACNA1A, SLC2A1 | CACNA1A | STX1A | – |
| SYNGAP1 | NF1, CDKL5, SLC6A1, CPLX1, SLC2A1 | NF1, CPLX1, CDKL5, SLC6A1, SLC2A1 | – | – | CPLX1 4→2 |

## gene: 0 diseases changed


## pathway: 0 diseases changed


## tissue: 0 diseases changed


## mutation: 0 diseases changed


## fate: 0 diseases changed


## structure: 0 diseases changed


## drugs: 0 diseases changed



## Why only the combined ranking moved

All 990 atlas-vs-atlas structure pairs were aligned first, so they were already final in the old file. No
per-axis top-5 changed. The combined score averages percentiles taken against all 17,578 pairs. Filling in the
remaining ~10,700 channel-panel structure pairs shifted the structure percentile scale, and that reordered close
calls in the combined ranking.

## Research recommendations (`data/derived/research_recs.json`)

Closest match per category changed for 3 diseases, all on the mechanistic card:

| Disease | Old | New |
|---|---|---|
| KRAS | SOS1 | RIT1 |
| STXBP1 | CPLX1 | STX1B |
| TPP1 | CPLX1 | SMPD1 |

Funding, tissue and symptom matches are unchanged. In the mechanistic top 5, adjacent pairs swapped for
CACNA1A, SCN1A, SCN2A and SLC6A1. In the 5th slot, STX1B gained STXBP1 (from SCN1A), SYT1 gained SYT2 (from ARSA)
and VAMP2 gained KCNQ2 (from GBA1).
