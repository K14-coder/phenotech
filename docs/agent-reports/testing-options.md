# Testing options layer ("Don't have a DNA file? Request one"): agent report

Output: `data/curated/testing_options.json`, built 2026-10-04. Raw pages are in `data/raw/testing/`, with one `.txt` per page, `.html` or `.pdf` originals, a `.plain.txt` copy for PDFs, and `_index.json` mapping each slug to its URL and fetch method.

Every item has a `source` with `url`, `quotes[]`, `raw_file` and `retrieved`. Each of the 125 quotes was string-matched against the stored page text, with whitespace and curly quotes normalised. The builder stops if any quote fails to match. I tested it with a made-up quote and it rejected it. No OpenAI calls were made.

The JSON is a standalone file. It is not wired into `pipeline/build_graph.py` or `web/`, so the app still needs a reader for it.

## Counts

| Section | Items |
|---|---|
| 1. Get your data from a test you already had | 10 labs, 4 file-type explainers (VCF, BAM, FASTQ, CRAM), 3 rights entries (EU GDPR Art. 15, UK GDPR Art. 15 + ICO, US HIPAA 45 CFR 164.524 + HHS FAQ 2048 + HHS access guidance + 2014 CLIA/HIPAA rule), 1 request-letter template |
| 2. If you haven't had genetic testing | 12 routes: 5 doctor/counsellor, 4 sponsored no-cost, 3 research |
| 3. Consumer tests: what they can and can't tell you | 4 sourced points (BMJ 2021 Weedon et al., Genet Med 2018 Tandy-Connor et al., FDA DTC page) |
| Raw sources cited | 41 pages; 125 verified quotes |

**Labs:** Labcorp, GeneDx, Ambry Genetics, Blueprint Genetics, Baylor Genetics, CENTOGENE, Revvity Omics, MyOme, Radboudumc Genome Diagnostics, Probably Genetic.
**Regions:** 7 US, 3 EU (Blueprint in Finland, CENTOGENE, Radboudumc in the Netherlands).

**Routes by region and referral:**

| Route | Type | Region | Referral needed |
|---|---|---|---|
| NSGC Find a Genetic Counselor | counsellor | US (+Canada) | no |
| NHS genetic and genomic testing | doctor | UK | yes |
| Genetic Alliance UK: NHS Genetic Services | doctor/counsellor | UK | yes |
| NHS GMS whole genome sequencing, rare disease | doctor | UK | yes |
| European Reference Networks | doctor | EU | yes (patients cannot contact them directly) |
| Behind the Seizure (Labcorp/Invitae, BioMarin) | sponsored | US | yes (clinician orders) |
| Detect LSDs (Labcorp/Invitae) | sponsored | US (+Canada) | yes |
| Other Labcorp/Invitae access programmes | sponsored | US, worldwide (varies) | yes |
| Probably Genetic free testing | sponsored | US only | no (family applies itself) |
| Undiagnosed Diseases Network | research | US | yes (provider recommendation letter) |
| Broad Rare Genomes Project | research | US | no, but must be under a provider's care. **Paused for new families** |
| Genomics England research library (via NHS WGS) | research | UK | yes |

## Choices worth knowing

- **Sponsored programmes:** each entry copies the page's own sponsorship and data-sharing sentences verbatim. For Invitae programmes, that is the sentence saying third parties "may receive de-identified (pseudonymized) patient data". For Probably Genetic, it is the statement that any data passed on is "de-identified and aggregated".
- **Consumer tests:** the task asked for "most consumer DNA tests are genotyping arrays". None of the authoritative sources I fetched says "most". The BMJ paper says "many SNP chip designs, including those used by many direct to consumer companies", so the summary says "Many consumer DNA tests". No consumer companies are named or recommended. The FDA page names one company in its list of authorised tests, but nothing from that list was used.
- **Labcorp and Invitae:** the Labcorp data-release form is Labcorp's (hosted on MNGLabs.Labcorp.com). Invitae's site now carries "© 2026 Labcorp". I found no Invitae-specific raw-data page, so the entry tells families to ask whether the form covers an older Invitae test, rather than claiming that it does.
- **HHS pages:** hhs.gov returns 403 to curl, WebFetch and Bright Data (empty body). The quotes were verified against Internet Archive snapshots of the same hhs.gov URLs, from 2026-05-11 and 2026-03-27. The JSON cites the hhs.gov URL and records the snapshot URL in `source_note`. The US entry is also backed by official text from eCFR and the Federal Register.
- **Letter template:** labelled "General information, not legal advice". It cites the rights generally (HIPAA 45 CFR 164.524; GDPR / UK GDPR Art. 15) and asks for files "where available". It does not claim any lab is obliged to supply a particular format. CRAM is offered as an option in the letter only, because no lab page mentioned it.

## Excluded, and why

- **Fulgent Genetics:** none of the Fulgent pages I found or fetched (`fulgent_exome`) describes raw-data access, and `/faq` returned 404.
- **PreventionGenetics:** I found no page on raw-data or report access, and `/faq` returned 404.
- **Invitae (as a separate entry):** no current Invitae raw-data page; covered under Labcorp with the caveat above.
- **Baylor Genetics' older form** (`baylor_patient_raw_release`, footer dated 01.13.20): it lists a raw-data fee. I left this out because the newer 2026-05 "Patient Request for Access" form says only that there is "a reasonable, cost-based fee", and the older price may be out of date.
- **Old Blueprint and CENTOGENE PDFs** (raw-data order forms; CENTOGENE US request form V14): they return 404 now. Blueprint's live FAQ and CENTOGENE's 2025 Terms were used instead.
- **Solve-RD:** the project was funded 2018–2022 and is not an open route for families. Also, **solve-rd.eu currently shows injected casino spam** (raw file `solve_rd.txt`), so it should not be linked. ERNs are listed instead.
- **European genetic counsellor directory:**
  - The European Board of Medical Genetics registered-counsellor list names individual people, so I didn't use it, in line with our "professional public information only" convention.
  - Orphanet's expert-centre search (`orpha.net/en/expert-centres`) is a JavaScript app with no fetchable text.
  - The EU route is therefore ERNs only. Orphanet would be a good addition if someone verifies it in a browser.
- **ACMG statement:** the 2015 ACMG DTC position statement abstract (PMID 26681314) has no substantive text in PubMed, so I used the BMJ and Genet Med papers instead.
- **Genetic Alliance UK addresses:** the page lists regional addresses and fax numbers. I didn't copy them because they may be stale; the JSON links to the page.

## Items to re-verify (dates from the pages)

1. **Rare Genomes Project:** check whether enrolment is still paused.
2. **NHS genetic testing page:** last reviewed 01 March 2023, and its "next review due" date (01 March 2026) has passed.
3. **Blueprint raw-data FAQ:** most answers were last modified 14 July 2022, including the statement that raw data within two years costs nothing. The file-format answer was modified 3 September 2025.
4. **Ambry consent form:** footer says v3 07.10.18, though the file is served from a 2026/03 upload path.
5. **Labcorp form:** dated ©2024 (DX_IC_828820-0224). Confirm it is still current and whether it covers Invitae tests.
6. **Revvity form:** effective 04/12/2024.
7. **HHS pages:** FAQ 2048 was last reviewed June 24, 2016, and the access guidance May 30, 2025. Both were read via archive snapshots.
8. **FDA DTC page:** content current as of 12/20/2019.
9. **NHS WGS patient leaflet** (2021) and **HEE "Requesting WGS" page**, which says "Initially, WGS will only be available…". Confirm against the current National Genomic Test Directory.
10. **Behind the Seizure:** the eligibility header says "patients in the US", but the disclaimer says testing is available "in the US and Canada". It is tagged US.
11. **Detect LSDs:** sponsor names appear only as logos, not text, so none are listed.

## How to re-run

```bash
# fetch helper and builder live in the session scratchpad; equivalent steps:
python3 fetch.py slug=url ...        # direct fetch -> data/raw/testing/<slug>.{html|pdf,txt}
python3 fetch.py --bd slug=url ...   # via pipeline/brightdata.py (Web Unlocker)
python3 build.py                     # verifies every quote, writes data/curated/testing_options.json
```

The two scratch scripts weren't copied into `pipeline/` because writes were limited to the three paths in the brief. If the layer needs refreshing, a collaborator can add them as `pipeline/testing_options/`.

**Bright Data usage:** 11 Web Unlocker requests (limit 40). The token was never printed. Five cache entries in `data/raw/brightdata/unlocker/` hold empty bodies: three HHS URLs and the CENTOGENE V14 form from this run, plus an older slc6a1europe.org entry from 2026-10-03. Because `brightdata.fetch()` serves cached results, delete those entries (or call with `use_cache=False`) before trying those URLs again.

**Raw folder size:** about 9.6 MB, mostly the EUR-Lex GDPR HTML and the Labcorp and CENTOGENE PDFs.
