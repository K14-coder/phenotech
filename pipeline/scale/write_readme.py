"""Render data/derived/scale/README.md from the built files (counts are never typed by hand)."""
from __future__ import annotations

import collections
import json

from common import BD_LOG, OUT, read_json, today


def main():
    U = read_json(OUT / "universe.json")
    T = read_json(OUT / "trials.json")
    O = read_json(OUT / "orgs.json")
    A = read_json(OUT / "assets.json")
    V = read_json(OUT / "spotcheck" / "verdicts.json", {})
    ds = U["diseases"]
    n_all = len(ds)
    concept = {k: (d.get("mondo") or k) for k, d in ds.items()}

    t_any = set(T["diseases"])
    t_name = {k for k, v in T["diseases"].items() if v["by_name"]["n"]}
    t_active = {k for k, v in T["diseases"].items() if v["by_name"]["active"] or v["by_gene"]["active"]}
    o_any = set(O["by_disease"])
    o_dir = set()
    o_src = collections.defaultdict(set)
    for o in O["orgs"]:
        for d in o["diseases"]:
            for e in [d["evidence"]] + d["also"]:
                o_src[e["source"]].add(d["id"])
    a_any = set(A["by_disease"])
    a_reg = {k for k, v in A["by_disease"].items()}
    allthree = t_any & o_any & a_any
    anyof = t_any | o_any | a_any

    bd = [json.loads(l) for l in BD_LOG.read_text().splitlines() if l.strip()] if BD_LOG.exists() else []
    bdc = collections.Counter((r["kind"], r["ok"]) for r in bd)

    def pct(x):
        return f"{x} ({100 * x / n_all:.1f}%)"

    def verdict(key, label=None):
        v = V.get(key) or {}
        c = v.get("correct", v.get("correct_gene_level"))
        return f"{c}/{v.get('n')}" if c is not None else "n/a"

    lines = []
    w = lines.append
    w("# Breadth layer: trials, patient organisations and registries for every monogenic disease")
    w("")
    w(f"Built {today()} by `pipeline/scale/` (stdlib Python, re-runnable, raw data cached in `data/raw/scale/`). "
      "Everything here is **`extracted_by: \"automated\"`**: each link carries its source record URL, a verbatim "
      "quote and the name of the matching rule that produced it. Precision beats recall: rules were tightened "
      "until the 30-link spot-checks below came back clean enough to show families, and every remaining error "
      "pattern is listed.")
    w("")
    w("## Coverage")
    w("")
    w(f"Universe: **{n_all} monogenic diseases** ({U['meta']['counts']['omim']} OMIM + {U['meta']['counts']['orpha']} "
      f"ORPHA ids; {U['meta']['counts']['genes']} genes; {U['meta']['counts']['with_mondo']} mapped to MONDO).")
    w("")
    w("| | diseases (native OMIM/ORPHA ids) |")
    w("|---|---|")
    w(f"| >= 1 trial (any rule) | {pct(len(t_any))} |")
    w(f"| >= 1 trial matched by disease name/synonym | {pct(len(t_name))} |")
    w(f"| >= 1 recruiting/active trial | {pct(len(t_active))} |")
    w(f"| >= 1 patient organisation | {pct(len(o_any))} |")
    w(f"| >= 1 registry / data platform | {pct(len(a_any))} |")
    w(f"| all three | {pct(len(allthree))} |")
    w(f"| at least one of the three | {pct(len(anyof))} |")
    w("")
    w(f"Distinct MONDO concepts with >= 1 trial / org / registry: {len({concept[k] for k in t_any})} / "
      f"{len({concept[k] for k in o_any})} / {len({concept[k] for k in a_any})}.")
    w("")
    w("Organisations by source (diseases reached): " + ", ".join(f"{k} {len(v)}" for k, v in sorted(o_src.items(), key=lambda x: -len(x[1]))) + ".")
    w(f"Org nodes: {O['meta']['counts']['orgs']} ({O['meta']['counts']['org_disease_links']} org-disease links; "
      f"{O['meta']['counts']['reused_graph_ids']} reuse an existing `org:` id from `data/graph.json`).")
    w(f"Trials: {T['meta']['source']['studies_in_pool']} unique CT.gov studies fetched; "
      f"{T['meta']['counts']['studies_referenced']} referenced in the output; {T['meta']['counts']['genes_with_trial']} genes have a gene-matched study.")
    w("Assets: " + ", ".join(f"`{k}` {v}" for k, v in list(A["meta"]["counts"]["per_asset"].items())[:6]) +
      f", plus {max(0, len(A['meta']['counts']['per_asset']) - 6)} more IAMRARE registries.")
    w("")
    w("## Files")
    w("")
    w("All ids are native: `OMIM:<n>` / `ORPHA:<n>` (plus `mondo` where `data/derived/global/index.json` maps them) "
      "and HGNC symbols. Join to the global index by `mondo` (several native ids can share one MONDO concept, so "
      "union them on a MONDO page).")
    w("")
    w("### `universe.json`")
    w("`{meta, diseases: {<id>: {id, name, genes[], gene_rules{SYMBOL: rule}, mondo, synonyms[], n_hpo}}, genes: {SYMBOL: [disease ids]}}`")
    w("- OMIM rows: HPO `genes_to_disease.txt` `association_type == MENDELIAN`.")
    w("- ORPHA rows: the HPO file flattens every Orphanet association to UNKNOWN, so the type is recovered from Orphanet "
      "product6 (`en_product6.xml`, cached in `data/raw/scale/orphanet/`); only *Disease-causing germline mutation(s) ...* with status *Assessed* is kept "
      f"(dropped: {', '.join(f'{v} {k}' for k, v in list(U['meta']['dropped_rows'].items())[:5])}, ...).")
    w("")
    w("### `trials.json`")
    w("```")
    w("{ meta,")
    w("  studies:  { NCTxxxxxxxx: {title, status, type, phases[], start, enrollment, sponsor, conditions[], url} },")
    w("  diseases: { <id>: { name, mondo, genes[],")
    w("              by_name: {n, by_type{}, by_status{}, active},   # studies matched by disease name/synonym")
    w("              by_gene: {n, by_type{}, by_status{}, active},   # studies matched only via a causal gene symbol")
    w("              top: [ {nct, rule, quote, url, via_gene?} ]  ,  # <= 8: name matches, interventional, recruiting, newest first")
    w("              ctgov_search } },")
    w("  genes:    { SYMBOL: {n, by_type, by_status, active, diseases[], top[]} } }")
    w("```")
    w("`quote` is the verbatim condition / keyword / brief-title string that matched; `rule` is one of "
      "`name_in_conditions|name_in_keywords|name_in_title|gene_in_conditions|gene_in_keywords|gene_in_title`.")
    w("")
    w("### `orgs.json`")
    w("```")
    w("{ meta, by_disease: {<id>: [org ids]},")
    w("  orgs: [ { id: 'org:<slug>', name, url, website, directory_profile, country, nord_member, sources[],")
    w("            directory_records: [{source, url, record, profile, quote}], reused_graph_id, extracted_by,")
    w("            diseases: [ {id, name, mondo, evidence: {source, url, quote, rule, matched?, context?}, also: [...], n_evidence} ] } ] }")
    w("```")
    w("### `assets.json`")
    w("```")
    w("{ meta, by_disease: {<id>: [asset ids]},")
    w("  assets: [ { id, name, kind, url, program?, listed_at?, disease_label?, extracted_by,")
    w("              diseases: [ {id, name, evidence{url, quote, rule}} | {gene, ids[], names[], evidence{url, quote, rule}} ] } ] }")
    w("```")
    w("### `spotcheck/`")
    w("`<source>.json`: the 30 random links (seed 7) per source that were judged by hand; `verdicts.json` holds the verdicts and the error notes.")
    w("")
    w("## Matching rules and observed precision")
    w("")
    w("Precision = links judged true out of 30 random links (seed 7) read by hand against the quoted record. "
      "Samples were drawn after the final rule set unless noted.")
    w("")
    w("| Source | Rule (rule names appear in the data) | Precision |")
    w("|---|---|---|")
    w(f"| CT.gov, disease name | `name_in_conditions/keywords/title`: name or synonym, token-normalised, as a whole phrase; longest span wins; no hyphen-glued or gene-context hits ('Ataxia Telangiectasia Mutated'); no digit-free abbreviations, no generic single words, no ambiguous synonyms; non-Orphanet diseases with > 300 hits dropped (breast cancer, Alzheimer, T2D ...) | {verdict('trials_name')} (post-fix sample; first build {V.get('trials_name_first_build', {}).get('correct')}/30) |")
    w(f"| CT.gov, gene symbol | `gene_in_*`: case-sensitive symbol with a gene context (bare symbol, or mutation/variant/related/deficiency... within 3 words); no oncology studies, no common-disease studies, no drug/biomarker/SNP contexts, no acronyms spelled out in the study (HBB = Helping Babies Breathe), symbol stoplist | {verdict('trials_gene')} at gene level (first build: {V.get('trials_gene_first_build', {}).get('correct')}/30) |")
    w(f"| Orgs from trials | sponsor/collaborator class OTHER + keyword (foundation, association ...), minus universities/hospitals/companies/funders/professional bodies/cancer charities; focused trials only (<= 3 disease concepts); org listed in a directory or name shares a distinctive token with the disease; gene-via links only for gene-named orgs | {verdict('org_clinicaltrials.gov')} (intermediate rules: {V.get('org_clinicaltrials.gov_intermediate', {}).get('correct')}/30) |")
    w(f"| Global Genes Global Advocacy Alliance | `dir_text_name` (name in org name / mission text), `dir_text_gene` | {verdict('org_globalgenes')} |")
    w(f"| NORD Organizational Database | `dir_disease_field_name` (whole 'Related Rare Diseases' entry = disease name/synonym), `dir_text_*` on the org name | {verdict('org_nord')} |")
    w(f"| EURORDIS members | `dir_disease_field_name` on the 'Disease:' entries (Orphanet names), `dir_text_*` | {verdict('org_eurordis')} |")
    w(f"| Genetic Alliance UK | `dir_text_name` / `dir_text_gene` on the member name (the directory lists names and websites only) | {verdict('org_geneticalliance_uk')} |")
    w(f"| Web search (Bright Data SERP) | `serp_page_mentions_name|gene`: non-news/social/hospital/university/journal/portal/lab/pharma domain, org-like title or domain, fetched page self-describes as an org and contains the name (or the gene in a gene context); quote = that page sentence | {verdict('org_serp')} (first filters: {V.get('org_serp_first', {}).get('correct')}/30) |")
    w(f"| Simons Searchlight | `list_item_gene`: gene line on 'Genetic Disorders We Study' -> all diseases of the gene | {verdict('asset_simons')} at gene level |")
    w(f"| CoRDS | `list_item_exact_name` (whole list line = name/synonym), `list_item_gene` | {verdict('asset_cords')} |")
    w(f"| NORD IAMRARE | per registry: label/registry name -> `list_item_exact_name`, `list_item_name_phrase`, `list_item_gene` | {verdict('asset_iamrare')} |")
    w(f"| Citizen Health | partner list items -> `list_item_exact_name`, `list_item_gene` | {verdict('asset_citizen')} at gene level |")
    w("")
    w("Gene-level links (any rule containing `gene`) are true for the gene but are credited to every disease of that "
      "gene (except somatic, cancer-named and >= 10-gene umbrella entities), so for multi-disease genes the specific disease "
      "may be a sibling phenotype (CACNA1C -> Brugada 3 via Simons). The UI must word them as *'mentions / studies <GENE>'*.")
    w("")
    w("## Bright Data usage")
    w("")
    w(f"Live requests: **{len(bd)}** of the 1,200 budget: SERP {bdc[('serp', True)]} ok + {bdc[('serp', False)]} failed, "
      f"Web Unlocker {bdc[('unlocker', True)]} ok + {bdc[('unlocker', False)]} failed (log: `data/raw/scale/brightdata_usage.jsonl`; "
      "responses cached in `data/raw/scale/brightdata/`, so re-runs are free). Used for: directory discovery searches, "
      "Global Genes (Cloudflare) JSON pages, NORD listing pages, the RARE-X page, the SERP stage and fallback fetches of org pages "
      "that block plain requests. EURORDIS, Genetic Alliance UK, Simons Searchlight, CoRDS, IAMRARE, Citizen Health, "
      "ClinicalTrials.gov and Orphanet were fetched directly.")
    w("")
    w("## How the UI should use this (disease page for any monogenic disease)")
    w("")
    w("1. Resolve the page's ids: the native OMIM/ORPHA ids of the MONDO concept (global index) -> union "
      "`trials.diseases[id]`, `orgs.by_disease[id]`, `assets.by_disease[id]`; dedupe NCT ids and org ids.")
    w("2. **Patient groups**: list org name + link (`url`), source badges (`sources`), and on expand the evidence quote with "
      "its link. Label every item **'automated match'** and show the rule in plain words: *'listed by NORD for <disease>'*, "
      "*'names <GENE> in its name'*, *'collaborator on NCT...'*, *'found by web search; page mentions <disease>'*. "
      "Rank directory field matches first, then name, trial, search and gene matches.")
    w("3. **Trials**: show `by_name` counts (by status / type) and `top` studies (title, status, phase, sponsor from `studies`), "
      "linking `https://clinicaltrials.gov/study/<NCT>`; show gene-matched studies (`via_gene`) in a separate "
      "*'Trials mentioning <GENE>'* group; always offer `ctgov_search` as the 'see all' link.")
    w("4. **Registries**: list assets with kind + link; for gene-level links say *'<Asset> enrols people with <GENE> variants'*.")
    w("5. Never merge these into curated deep-layer edges without review. Show an empty state with the CT.gov / NORD search "
      "links when nothing matched.")
    w("")
    w("## Re-run")
    w("```")
    w("cd pipeline/scale")
    w("python3 build_universe.py      # universe.json (+ Orphanet product6 download, once)")
    w("python3 fetch_ctgov.py         # ~14.9k CT.gov queries, 4 parallel, resumable (about 25 min cold)")
    w("python3 discover.py            # directory URL discovery (Bright Data SERP, cached)")
    w("python3 fetch_directories.py   # Global Genes, NORD, EURORDIS, Genetic Alliance UK (cached)")
    w("python3 build_trials.py        # trials.json + _trial_orgs.json")
    w("python3 build_orgs.py          # orgs.json (directories + trials [+ SERP if present])")
    w("python3 serp_orgs.py           # up to 300 Bright Data searches for diseases without an org -> _serp_orgs.json")
    w("python3 build_orgs.py          # merge SERP orgs")
    w("python3 assets.py              # assets.json")
    w("python3 spotcheck.py <source>  # draw a 30-link sample; verdicts are recorded in spotcheck/verdicts.json")
    w("python3 write_readme.py")
    w("```")
    w("")
    w("## Caveats")
    w("")
    w("- **Trials**: the CT.gov pool is the union of ~14.9k query result pages (100 per query; up to 1,000 when a query "
      "kept matching), so counts for very large diseases can be lower bounds. Name matching is literal: numbered OMIM "
      "subtypes ('... 96') rarely appear in trial records, so most of them only get gene-level trials. Multi-condition "
      "registries (e.g. CoRDS NCT, NBIA, NCL registries) legitimately list hundreds of diseases and appear as matches.")
    w("- **Gene-level matches** are true for the gene, not necessarily for the specific sibling disease (see above). "
      "Somatic and cancer studies are excluded from gene matching entirely, so hereditary cancer syndromes only get trials by name.")
    w("- **Directories describe themselves**: NORD's ODB includes broad bodies (American Heart Association, professional "
      "societies) and the occasional registry. They are correct per the directory but are not disease-specific groups. "
      "`nord_member` marks NORD members. Global Genes and Genetic Alliance UK have no structured disease field, so their "
      "links come from org names and mission text.")
    w("- **Web search** precision is the lowest of the sources: the result is a page that mentions the disease on an "
      "org-like site, not a verified organisation profile. Treat these as leads.")
    w("- **Synonyms** come from MONDO (via the global index) and Orphanet. A wrong synonym upstream becomes a wrong match "
      "(guarded by the ambiguity, sub-phrase, hyphen and eponym rules).")
    w("- Not done in this pass: NORD org profile pages (websites for NORD-only orgs point to the NORD profile), "
      "RARE-X communities (JavaScript-rendered), Orphanet's own patient-org directory (JavaScript-rendered), and "
      "non-English directory text.")
    w("- Privacy: e-mail addresses are redacted from every stored page; no personal contact details are recorded.")
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print("README written;", len(t_any), len(o_any), len(a_any), len(bd))


if __name__ == "__main__":
    main()
