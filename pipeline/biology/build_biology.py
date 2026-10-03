"""Assemble data/curated/biology.json from every fetched fragment.

Run (after the fetch scripts):  python3 pipeline/biology/build_biology.py
Inputs (all under data/raw/biology/): genes.json, diseases.json, clinvar_summary.json,
        hpo_fragment.json, go_fragment.json, pubmed/*.json, clinicaltrials/*.json
        plus pipeline/biology/curation.py (claims, as needles resolved against those sources)
Output: data/curated/biology.json  {nodes, edges, clusters, gaps}
"""
from __future__ import annotations

from collections import defaultdict

import curation as CUR
from common import (BRIDGE_GENES, CORE_GENES, CURATED, RAW, TODAY, edge_id, evidence,
                    read_json, write_json)

# Umbrella disease labels / plain-language summaries (gene-defined, per docs/SCHEMA.md)
DISEASE_META = {
    "STXBP1": ("STXBP1-related disorders",
               "Severe epilepsy and developmental delay caused by changes in STXBP1, the gene for "
               "Munc18-1. Most children have seizures starting in the first year and significant "
               "developmental disability."),
    "SYT1": ("SYT1-related disorders (Baker-Gordon syndrome)",
             "A developmental disorder caused by changes in SYT1, the calcium sensor that times "
             "neurotransmitter release. Features include low muscle tone, unusual eye movements, "
             "involuntary movements and developmental delay."),
    "SNAP25": ("SNAP25-related disorders",
               "Changes in SNAP25 cause early-onset epilepsy with developmental delay; one reported "
               "variant instead causes a presynaptic congenital myasthenic syndrome with fatigable "
               "muscle weakness."),
    "VAMP2": ("VAMP2-related disorders",
              "Changes in VAMP2 (synaptobrevin-2) cause a neurodevelopmental disorder with low muscle "
              "tone from birth, intellectual disability and autistic features, often with movement "
              "problems."),
    "STX1B": ("STX1B-related epilepsies",
              "Changes in STX1B cause fever-associated epilepsies, from simple febrile seizures to "
              "severe epileptic encephalopathy, including generalized epilepsy with febrile seizures "
              "plus (GEFS+)."),
    "SYT2": ("SYT2-related presynaptic congenital myasthenic syndromes",
             "Changes in SYT2 weaken the signal from nerve to muscle. Children and adults have "
             "fatigable weakness and reduced reflexes; several patients improved on 3,4-diaminopyridine."),
    "CPLX1": ("CPLX1-related disorders",
              "Rare recessive changes in CPLX1 (complexin-1) have been reported in severe infantile "
              "myoclonic epilepsy with intellectual disability. The evidence base is small."),
    "UNC13A": ("UNC13A-related disorders",
               "Changes in UNC13A (Munc13-1) cause neurodevelopmental syndromes with epilepsy, "
               "movement problems and, in recessive truncating cases, fatal myasthenia. Separately, "
               "common UNC13A variants are a susceptibility factor in ALS."),
    "STX1A": ("STX1A-related neurodevelopmental disorder",
              "A recently described disorder with intellectual disability, autism and epilepsy, "
              "reported in a small number of individuals with STX1A variants."),
    "NSF": ("NSF-related developmental and epileptic encephalopathy",
            "A very rare early-infantile epileptic encephalopathy reported with de novo variants in "
            "NSF, the enzyme that recycles the SNARE machinery after each fusion event."),
    "SLC6A1": ("SLC6A1-related disorders",
               "Changes in SLC6A1, the GAT-1 GABA transporter, cause epilepsy with myoclonic-atonic "
               "seizures and, more broadly, developmental delay with or without autism. SLC6A1 is NOT "
               "a SNARE protein: it clears GABA from the synapse after release."),
}
EXTRA_SYNONYMS = {
    "STXBP1": ["DEE4", "EIEE4", "Ohtahara syndrome (STXBP1)", "STXBP1 encephalopathy",
               "Munc18-1 encephalopathy"],
    "SYT1": ["Baker-Gordon syndrome", "BAGOS", "SYT1-associated neurodevelopmental disorder"],
    "SNAP25": ["CMS18", "congenital myasthenic syndrome 18", "SNAP25-DEE", "DEE in SNAP25"],
    "VAMP2": ["NEDHAHM", "synaptobrevin-2-related disorder"],
    "STX1B": ["GEFS+9", "GEFSP9", "fever-associated epilepsy syndrome", "FASES"],
    "SYT2": ["CMS7A", "CMS7B", "congenital myasthenic syndrome 7", "Lambert-Eaton-like syndrome (SYT2)"],
    "CPLX1": ["DEE63", "complexin-1 deficiency"],
    "UNC13A": ["Munc13-1-related disorder"],
    "STX1A": ["syntaxin-1A-related neurodevelopmental disorder"],
    "NSF": ["DEE96"],
    "SLC6A1": ["MAE", "myoclonic-atonic epilepsy", "Doose syndrome (SLC6A1)", "GAT-1 deficiency",
               "epilepsy with myoclonic atonic seizures"],
}
VG_GROUPS = {
    "truncating": ("Truncating variants (nonsense, frameshift, start-lost)",
                   ["nonsense", "frameshift", "start_lost"], "truncating"),
    "missense": ("Missense variants (single amino-acid changes)", ["missense"], "missense"),
    "splice": ("Splice-site variants", ["splice", "intronic_or_splice_region"], "splice"),
    "whole-gene-deletion": ("Single-gene deletions / duplications",
                            ["cnv_single_gene", "intragenic_deletion_or_duplication"], "cnv"),
    "contiguous-gene-deletion": ("Larger deletions spanning this gene and its neighbours",
                                 ["cnv_multigene"], "cnv"),
}
VG_EFFECT = {
    "truncating": "mech:haploinsufficiency",
    "whole-gene-deletion": "mech:haploinsufficiency",
    "splice": "mech:haploinsufficiency",
    "missense": None,   # gene-specific, set from the literature claims below
    # Multi-gene deletions are deliberately given NO has_effect edge: the deleted segment
    # removes several genes, so this gene's own contribution is not isolated by the record.
    "contiguous-gene-deletion": None,
}


def ev_pub(ref: str, needle: str, supports: bool, study_type: str) -> dict:
    """PubMed / trial evidence whose quote is lifted verbatim from the stored source."""
    q = CUR.quote_for(ref, needle)
    m = CUR.meta_for(ref)
    src = "ClinicalTrials.gov" if ref.startswith("NCT") else "PubMed"
    kind = "trial" if ref.startswith("NCT") else "publication"
    title = m["title"]
    if ref.startswith("NCT"):
        title = f"{title} [{m.get('status')}" + (f"; {m['why_stopped']}" if m.get("why_stopped") else "") + "]"
    return evidence(src, ref if ref.startswith("NCT") else ref, m["url"], kind,
                    extracted_by="agent-curation", title=title, year=m.get("year"), quote=q,
                    study_type=study_type, supports=supports, verified=False)


def plain(note: str) -> str:
    """Strip internal curation markers so explanations stay family-readable."""
    for m in ("COUNTER/limit: ", "COUNTER/nuance: ", "COUNTER: ", "COUNTER to ",
              "COUNTER to a ", "COUNTER to 'dominant only': "):
        if note.startswith(m):
            note = note[len(m):]
            return note[0].upper() + note[1:]
    return note


def conf_from_evidence(evs: list[dict], base_db: bool = False) -> float:
    pubs = [e for e in evs if e.get("supports", True) and e["kind"] in ("publication", "trial")]
    if base_db and pubs:
        return 0.92
    if len(pubs) >= 2:
        return 0.8
    if len(pubs) == 1:
        return 0.6
    return 0.5


def main() -> None:
    genes = read_json(RAW / "genes.json")
    dis = read_json(RAW / "diseases.json")
    cv = read_json(RAW / "clinvar_summary.json")
    hpo = read_json(RAW / "hpo_fragment.json")
    go = read_json(RAW / "go_fragment.json")

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(n):
        nodes[n["id"]] = n

    def add_edge(e):
        if e["id"] in edges:  # merge evidence on duplicate edge ids
            old = edges[e["id"]]
            old["evidence"] += [x for x in e["evidence"] if x not in old["evidence"]]
            old.setdefault("counter_evidence", [])
            old["counter_evidence"] += [x for x in e.get("counter_evidence", [])
                                        if x not in old["counter_evidence"]]
            return
        edges[e["id"]] = e

    included = [s for s, d in dis.items() if d["include"]]

    # ---------------------------------------------------------------- genes
    for sym in included:
        g = genes[sym]
        syn = list(dict.fromkeys(g["protein_synonyms_curated"] + g.get("alias_symbol", [])
                                 + g.get("prev_symbol", []) + [g.get("protein_name")]
                                 + g.get("protein_alt_names", [])))
        xr = {"HGNC": g["hgnc_id"], "NCBIGene": g["entrez_id"], "Ensembl": g["ensembl_gene_id"]}
        if g.get("omim_id"):
            xr["OMIM"] = g["omim_id"]
        if g.get("uniprot_acc"):
            xr["UniProt"] = g["uniprot_acc"]
        if g.get("mane_enst"):
            xr["MANE_Select"] = g["mane_enst"]
        attrs = {"protein": g.get("protein_name"), "function": g.get("uniprot_function"),
                 "protein_length_aa": g.get("protein_length_aa"),
                 "cds_length_bp": g.get("cds_length_bp"),
                 "tier": dis[sym]["tier"],
                 "is_snare_machinery": sym not in BRIDGE_GENES}
        if g.get("cds_length_bp"):
            attrs["aav_cds_fits_4_7kb"] = g["cds_length_bp"] <= 4700
        srcs = [evidence("HGNC", g["hgnc_id"], g["hgnc_url"], "database",
                         title=f"HGNC symbol report: {sym} ({g['name']})",
                         study_type="database_record")]
        if g.get("uniprot_acc"):
            srcs.append(evidence("UniProt", g["uniprot_acc"], g["uniprot_url"], "database",
                                 title=f"UniProtKB {g['uniprot_entry']} ({g.get('protein_name')})",
                                 quote=g.get("uniprot_function"), study_type="database_record"))
        if g.get("ensembl_cds_url"):
            srcs.append(evidence("Monarch" if False else "OpenTargets", g["mane_enst"],
                                 g["ensembl_cds_url"], "database",
                                 title=f"Ensembl REST CDS for MANE Select {g['mane_enst']}: "
                                       f"{g['cds_length_bp']} bp", study_type="database_record"))
        add_node({"id": f"gene:{sym}", "type": "gene", "label": sym,
                  "synonyms": [s for s in syn if s], "xrefs": xr,
                  "summary": g.get("uniprot_function"), "attrs": attrs, "sources": srcs})

    # ---------------------------------------------------------------- diseases + causes edges
    for sym in included:
        d = dis[sym]
        label, summary = DISEASE_META[sym]
        subtypes, omim, orpha, mondo, syns, inh = [], [], [], [], [], []
        for e in d["entities"]:
            srcs = {m["primary_knowledge_source"] for m in e["monarch_edges"]}
            orpha_causal = [c for c, a in d.get("orphanet_associations", {}).items()
                            if a.get("causal") and c in e["orpha_from_edges"]]
            if "infores:omim" not in srcs and not orpha_causal:
                continue  # skip contiguous-deletion / modifier / susceptibility links
            st = {"name": e["name"], "MONDO": e["mondo"]}
            if e["omim_from_edges"]:
                st["OMIM"] = e["omim_from_edges"]
                omim += e["omim_from_edges"]
            if orpha_causal:
                st["ORPHA"] = orpha_causal
                orpha += orpha_causal
            if e.get("inheritance"):
                st["inheritance"] = e["inheritance"]
                inh.append(e["inheritance"])
            subtypes.append(st)
            mondo.append(e["mondo"])
            syns += e["synonyms"]
        # Orphanet gene-specific entities that Monarch did not map to a MONDO term
        for c, a in d.get("orphanet_associations", {}).items():
            if a.get("causal") and c not in orpha:
                subtypes.append({"name": a["name"], "ORPHA": [c]})
                orpha.append(c)
                syns.append(a["name"])
        xr = {"MONDO": sorted(set(mondo)), "OMIM": sorted(set(omim)), "ORPHA": sorted(set(orpha)),
              "HGNC": genes[sym]["hgnc_id"]}
        eb = d["established_by"]
        node_srcs = [evidence("Monarch", f"HGNC:{genes[sym]['hgnc_id'].split(':')[1]}",
                              f"https://monarchinitiative.org/{genes[sym]['hgnc_id']}", "database",
                              title=f"Monarch Initiative gene-to-disease associations for {sym}",
                              study_type="database_record")]
        add_node({"id": f"disease:{sym}", "type": "disease", "label": label,
                  "synonyms": list(dict.fromkeys(EXTRA_SYNONYMS.get(sym, []) + syns))[:40],
                  "xrefs": xr, "summary": summary,
                  "attrs": {"subtypes": subtypes,
                            "inheritance": "; ".join(sorted(set(inh))) or None,
                            "gene": sym, "tier": d["tier"],
                            "approved_treatment": False,
                            "gene_disease_validity": {
                                "gene2phenotype": eb["g2p_confidence"],
                                "clingen": eb["clingen_classification"],
                                "omim_causal_edge": eb["omim_causal"],
                                "orphanet_disease_causing": eb["orphanet_disease_causing"]}},
                  "sources": node_srcs})

        # ---- causes edge (database evidence)
        evs = []
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                oo = m.get("original_object") or ""
                if m["primary_knowledge_source"] == "infores:omim" and oo.startswith("OMIM:"):
                    mim = oo.split(":")[1]
                    evs.append(evidence("OMIM", oo, f"https://omim.org/entry/{mim}", "database",
                                        title=f"OMIM {mim}: {e['name']} - gene-phenotype relationship "
                                              f"with {sym} (via Monarch {m['predicate']})",
                                        study_type="database_record"))
        for c, a in d.get("orphanet_associations", {}).items():
            if a.get("causal"):
                evs.append(evidence("Orphanet", f"ORPHA:{c}", a["url"], "database",
                                    title=f"Orphanet ORPHA:{c} {a['name']}: {sym} - "
                                          f"{a['association_type']} (Assessed)",
                                    study_type="database_record"))
        for r in d["opentargets"]["evidence"]:
            if r["datasourceId"] == "gene2phenotype" and (r.get("confidence") or "").lower() in (
                    "definitive", "strong", "moderate"):
                evs.append(evidence("OpenTargets", f"G2P:{r['disease']['id']}",
                                    f"https://platform.opentargets.org/evidence/"
                                    f"{genes[sym]['ensembl_gene_id']}/{r['disease']['id']}", "database",
                                    title=f"Gene2Phenotype: {sym} - {r.get('diseaseFromSource')} "
                                          f"({r['confidence']}, {', '.join(r.get('allelicRequirements') or [])})",
                                    study_type="database_record"))
                break
        for r in d["opentargets"]["evidence"]:
            if r["datasourceId"] == "clingen":
                u = (r.get("urls") or [{}])[0].get("url") or "https://search.clinicalgenome.org/"
                evs.append(evidence("ClinGen", f"ClinGen:{r['disease']['id']}", u, "database",
                                    title=f"ClinGen gene-disease validity: {sym} - "
                                          f"{r.get('diseaseFromSource')} = {r.get('confidence')} "
                                          f"({r.get('studyId')})", study_type="database_record"))
                break
        # discovery publication, where we curated one
        disc = [c for c in CUR.DISEASE_MECHANISM_CLAIMS if c[0] == sym and c[4] is True
                and c[5] in ("case_series", "case_report", "cohort")]
        if disc:
            c = disc[0]
            evs.append(ev_pub(c[2], c[3], True, c[5]))
        n_sub = len(subtypes)
        add_edge({"id": edge_id(f"gene:{sym}", "causes", f"disease:{sym}"),
                  "source": f"gene:{sym}", "target": f"disease:{sym}", "type": "causes",
                  "label": "causes",
                  "explanation": (f"Variants in {sym} cause {label}. Curated databases record "
                                  f"{n_sub} clinical entit{'y' if n_sub == 1 else 'ies'} under this "
                                  f"umbrella" +
                                  (f"; gene-disease validity is {eb['g2p_confidence'][0]} in "
                                   f"Gene2Phenotype" if eb["g2p_confidence"] else "") +
                                  (f" and {eb['clingen_classification'][0]} in ClinGen"
                                   if eb["clingen_classification"] else "") + "."),
                  "evidence_level": "clinical", "status": "supported",
                  "confidence": conf_from_evidence(evs, base_db=True),
                  "evidence": evs})

    # ---------------------------------------------------------------- effect mechanism nodes
    for slug, label, summary in [(a, b, c) for a, b, c in CUR.EFFECT_MECHANISMS]:
        add_node({"id": f"mech:{slug}", "type": "mechanism", "label": label, "summary": summary,
                  "attrs": {"kind": "effect"},
                  "sources": [evidence("Atlas", "docs/SCHEMA.md",
                                       "https://github.com/obophenotype/human-phenotype-ontology",
                                       "expert", extracted_by="agent-curation",
                                       title="Effect-mechanism vocabulary used by this atlas layer")]})
    # process mechanism nodes + participates_in edges from QuickGO
    for n in go["nodes"]:
        add_node(n)
    for e in go["edges"]:
        add_edge(e)
    # phenotype nodes + has_phenotype / similar_phenotype edges
    for n in hpo["nodes"]:
        add_node(n)
    for e in hpo["edges"]:
        add_edge(e)

    # ---------------------------------------------------------------- disease -> mechanism (driven_by)
    claims_by = defaultdict(list)
    for c in CUR.DISEASE_MECHANISM_CLAIMS:
        claims_by[(c[0], c[1])].append(c)   # full tuple: (gene, mech, ref, needle, supports, type, note)
    # the gene's mainstream mechanism = the one with the most plainly-supporting claims
    dominant_mech = {}
    for sym in included:
        cands = [(sum(1 for c in cl if c[2] is True), slug)
                 for (s2, slug), cl in claims_by.items() if s2 == sym]
        if cands:
            dominant_mech[sym] = max(cands)[1]
    minority_against = defaultdict(list)   # (sym, dominant_slug) -> counter evidence items
    for (sym, slug), cl in claims_by.items():
        if sym not in included:
            continue
        for c in cl:
            if c[4] == "minority" and dominant_mech.get(sym) and dominant_mech[sym] != slug:
                minority_against[(sym, dominant_mech[sym])].append(
                    (ev_pub(c[2], c[3], False, c[5]),
                     f"{c[6]} (reported as a {nodes['mech:' + slug]['label'].split(' (')[0].lower()} "
                     f"mechanism instead)"))
    for (sym, slug), cl in claims_by.items():
        if sym not in included:
            continue
        pro = [c for c in cl if c[4] is True or c[4] == "minority"]
        con = [c for c in cl if c[4] is False]
        minority_only = bool(pro) and all(c[4] == "minority" for c in pro)
        evs = [ev_pub(c[2], c[3], True, c[5]) for c in pro]
        cevs = [ev_pub(c[2], c[3], False, c[5]) for c in con]
        for ev, note in minority_against.get((sym, slug), []):
            if ev not in cevs:
                cevs.append(ev)
                con = con + [(sym, slug, ev["ref"], "", False, "", note)]
        mech_label = nodes[f"mech:{slug}"]["label"]
        lvl = "experimental"
        status = "contested" if (con or minority_only) else "supported"
        conf = conf_from_evidence(evs)
        if con and pro:
            conf = max(0.5, conf - 0.1)
        if minority_only:
            conf = min(conf, 0.5)
        if not pro:
            continue   # never emit a driven_by edge that has no supporting source
        expl = (f"Published work links {sym}-related disorders to {mech_label.split(' (')[0].lower()}. "
                + " ".join(plain(c[6]) for c in pro[:2]))
        if minority_only:
            expl = (f"A minority of published variants in {sym} act by "
                    f"{mech_label.split(' (')[0].lower()}, against the mainstream view for this gene. "
                    + " ".join(plain(c[6]) for c in pro[:2]))
        if con:
            expl += (" Contradicting or limiting findings are attached as counter-evidence: "
                     + " ".join(plain(c[6]) for c in con[:2]))
        add_edge({"id": edge_id(f"disease:{sym}", "driven_by", f"mech:{slug}"),
                  "source": f"disease:{sym}", "target": f"mech:{slug}", "type": "driven_by",
                  "label": "driven by", "explanation": expl.strip(),
                  "evidence_level": lvl, "status": status, "confidence": round(conf, 2),
                  "evidence": evs, "counter_evidence": cevs,
                  "attrs": {"n_supporting_publications": len(pro),
                            "n_counter_publications": len(con),
                            "minority_mechanism": minority_only}})

    # ---------------------------------------------------------------- variant groups (ClinVar)
    missense_effect = {}
    for sym in included:
        for slug in ("dominant-negative", "gain-of-function", "protein-destabilization"):
            key = (sym, slug)
            if key in claims_by and any(c[4] is True for c in claims_by[key]):
                missense_effect.setdefault(sym, []).append(f"mech:{slug}")
    for sym in included:
        c = cv.get(sym)
        if not c:
            continue
        for slug, (label, cats, consequence) in VG_GROUPS.items():
            counts = {k: c["by_consequence"].get(k, 0) for k in cats if c["by_consequence"].get(k)}
            total = sum(counts.values())
            if not total:
                continue
            ex = []
            for k in cats:
                for e in c["examples"].get(k, [])[:2]:
                    ex.append(f"{e['title']} [{e['accession']}; {e['classification']}; {e['review_status']}]")
            vid = f"vg:{sym}:{slug}"
            add_node({"id": vid, "type": "variant_group",
                      "label": f"{sym}: {label}",
                      "attrs": {"gene": sym, "consequence": consequence,
                                "example_variants": ex[:4], "clinvar_counts": counts,
                                "clinvar_total_in_group": total,
                                "clinvar_gene_total_PLP": c["n_classified_PLP"]},
                      "summary": (f"{total} of {c['n_classified_PLP']} pathogenic or likely-pathogenic "
                                  f"ClinVar records for {sym} fall in this group."
                                  + (" These are copy-number changes covering more than one gene, so "
                                     "the share of the phenotype due to this gene alone cannot be read "
                                     "off the record; no mechanism edge is drawn from them."
                                     if slug == "contiguous-gene-deletion" else "")),
                      "sources": [evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                                           title=f"ClinVar esearch/esummary for {sym} "
                                                 f"(P/LP; {c['esearch_count']} records)",
                                           study_type="database_record")]})
            add_edge({"id": edge_id(vid, "variant_in", f"gene:{sym}"),
                      "source": vid, "target": f"gene:{sym}", "type": "variant_in",
                      "label": "variants in",
                      "explanation": f"These {total} ClinVar pathogenic/likely-pathogenic records "
                                     f"are variants in {sym}.",
                      "evidence_level": "curated", "status": "supported", "confidence": 0.9,
                      "evidence": [evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                                            title=f"ClinVar records for {sym} by molecular consequence",
                                            study_type="database_record")]})
            # variant_group -> effect mechanism
            targets = []
            if slug == "missense":
                targets = missense_effect.get(sym, [])
            elif VG_EFFECT[slug]:
                targets = [VG_EFFECT[slug]]
            for t in targets:
                mech_slug = t.split(":")[1]
                cl = claims_by.get((sym, mech_slug), [])
                pro = [x for x in cl if x[4] is True]
                con = [x for x in cl if x[4] is False]
                evs = [ev_pub(x[2], x[3], True, x[5]) for x in pro]
                cevs = [ev_pub(x[2], x[3], False, x[5]) for x in con]
                if not evs:
                    # truncating/deletion -> haploinsufficiency with no gene-specific paper:
                    # keep it, but as an inference from the consequence class.
                    evs = [evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                                    title=f"{total} {consequence} P/LP records in {sym}; "
                                          f"loss of one functional copy inferred from consequence class",
                                    study_type="database_record")]
                    lvl, conf, status = "inferred", 0.45, "unverified"
                else:
                    lvl = "experimental"
                    conf = conf_from_evidence(evs)
                    status = "contested" if con else "supported"
                add_edge({"id": edge_id(vid, "has_effect", t),
                          "source": vid, "target": t, "type": "has_effect",
                          "label": "has effect",
                          "explanation": (f"{label} in {sym} are linked to "
                                          f"{nodes[t]['label'].split(' (')[0].lower()}."
                                          + (" " + plain(pro[0][6]) if pro else
                                             " No gene-specific functional paper is attached: this is "
                                             "inferred from the variant consequence class.")),
                          "evidence_level": lvl, "status": status, "confidence": round(conf, 2),
                          "evidence": evs, "counter_evidence": cevs})

    # ---------------------------------------------------------------- family framing publications
    family_ev = []
    for ref, needle, gs, note in CUR.FAMILY_CLAIMS:
        family_ev.append((ref, needle, gs, note, ev_pub(ref, needle, True, "review")))

    # ---------------------------------------------------------------- shares_mechanism edges
    # (a) within the SNARE machinery: pairs that share a process mechanism AND an effect mechanism
    proc_of = defaultdict(set)
    eff_of = defaultdict(set)
    for e in edges.values():
        if e["type"] == "participates_in":
            proc_of[e["source"].split(":")[1]].add(e["target"])
        # only plainly-supported effects count for shares_mechanism, not minority mechanisms
        if e["type"] == "driven_by" and not (e.get("attrs") or {}).get("minority_mechanism"):
            eff_of[e["source"].split(":")[1]].add(e["target"])
    snare = [s for s in included if s not in BRIDGE_GENES]
    for i, a in enumerate(snare):
        for b in snare[i + 1:]:
            shared_proc = proc_of[a] & proc_of[b]
            shared_eff = eff_of[a] & eff_of[b]
            if not (shared_proc and shared_eff):
                continue
            fam = [f for f in family_ev if a in f[2] and b in f[2]]
            if not fam:
                continue
            evs = [f[4] for f in fam[:2]]
            evs += [evidence("GO", sorted(shared_proc)[0].split(":", 1)[1],
                             f"https://www.ebi.ac.uk/QuickGO/term/"
                             f"{nodes[sorted(shared_proc)[0]]['xrefs']['GO']}", "database",
                             title=f"Shared GO process annotations: "
                                   f"{', '.join(nodes[p]['label'] for p in sorted(shared_proc))}",
                             study_type="database_record")]
            pl = ", ".join(nodes[p]["label"] for p in sorted(shared_proc))
            el = ", ".join(nodes[p]["label"].split(" (")[0] for p in sorted(shared_eff))
            add_edge({"id": edge_id(f"disease:{a}", "shares_mechanism", f"disease:{b}"),
                      "source": f"disease:{a}", "target": f"disease:{b}", "type": "shares_mechanism",
                      "label": "shares mechanism",
                      "explanation": (f"{a} and {b} act in the same presynaptic process ({pl}) and "
                                      f"their disease variants share at least one molecular effect "
                                      f"({el}). Reviews group both genes in the same disease family."),
                      "evidence_level": "curated", "status": "supported", "confidence": 0.7,
                      "evidence": evs,
                      "attrs": {"shared_processes": sorted(shared_proc),
                                "shared_effects": sorted(shared_eff), "basis": "SNAREopathy family"}})

    # (b) the bridge: STXBP1 <-> SLC6A1 via protein destabilization + chaperone approach
    pro = [c for c in CUR.BRIDGE_CLAIMS if c[2]]
    con = [c for c in CUR.BRIDGE_CLAIMS if not c[2]]
    bevs = [ev_pub(*c[:2], True, c[3]) for c in pro]
    bcevs = [ev_pub(*c[:2], False, c[3]) for c in con]
    add_edge({
        "id": edge_id("disease:STXBP1", "shares_mechanism", "disease:SLC6A1"),
        "source": "disease:STXBP1", "target": "disease:SLC6A1", "type": "shares_mechanism",
        "label": "shared destabilization mechanism (contested)",
        "explanation": (
            "Different genes, different pathways, same cell-biological problem: a subset of STXBP1 "
            "(Munc18-1) and SLC6A1 (GAT-1) missense variants make a protein that is unstable or "
            "misfolded, so it is degraded or stuck in the endoplasmic reticulum rather than working. "
            "Both have been rescued by the chemical chaperone 4-phenylbutyrate in laboratory models, "
            "and one early-phase trial (NCT04937062) enrols children with either gene on exactly this "
            "shared rationale. Important limits are attached as counter-evidence: roughly a third of "
            "SLC6A1 loss-of-function missense variants reach the cell surface normally and so cannot "
            "be helped by folding correction; no dominant-negative effect was found in SLC6A1; "
            "chemical chaperones need high, potentially toxic concentrations; the benefit may come "
            "from boosting the healthy copy rather than fixing the mutant; and the only human outcome "
            "data is two uncontrolled deletion patients."),
        "evidence_level": "experimental", "status": "contested", "confidence": 0.6,
        "evidence": bevs, "counter_evidence": bcevs,
        "attrs": {"shared_effects": ["mech:protein-destabilization"],
                  "shared_processes": [], "basis": "protein destabilization / proteostasis",
                  "bridges_outside_slice": True,
                  "verdict": "partly holds: the destabilization mechanism and the chaperone approach "
                             "are documented for both genes and are being tested in one trial, but "
                             "a substantial variant class in SLC6A1 is not folding-correctable and "
                             "no human efficacy data exists for either gene"}})

    # ---------------------------------------------------------------- therapies
    for t in CUR.THERAPIES:
        tid = f"therapy:{t['slug']}"
        evs = [ev_pub(*e) for e in t["evidence"]]
        cevs = [ev_pub(*e) for e in t["counter"]]
        attrs = {"modality": t["modality"], "stage": t["stage"],
                 "target_genes": [g for g in t["diseases"] if g in included]}
        if t.get("trials"):
            trials = []
            for n in t["trials"]:
                m = CUR.meta_for(n)
                trials.append({"nct": n, "status": m["status"], "phases": m["phases"],
                               "sponsor": m["sponsor"], "why_stopped": m.get("why_stopped"),
                               "url": m["url"]})
            attrs["trials"] = trials
        if t.get("caveat"):
            attrs["caveat"] = t["caveat"]
        add_node({"id": tid, "type": "therapy", "label": t["label"], "synonyms": t["synonyms"],
                  "summary": t["summary"], "attrs": attrs, "sources": evs[:2] + cevs[:1]})
        for m in t["mechanisms"]:
            if m not in nodes:
                continue
            add_edge({"id": edge_id(tid, "targets", m), "source": tid, "target": m, "type": "targets",
                      "label": "targets",
                      "explanation": f"{t['label']} is aimed at {nodes[m]['label'].split(' (')[0].lower()}.",
                      "evidence_level": "experimental" if t["stage"] in ("preclinical", "clinical") else "hypothesis",
                      "status": "contested" if cevs else "supported",
                      "confidence": round(conf_from_evidence(evs), 2),
                      "evidence": evs, "counter_evidence": cevs})
        for sym in t["diseases"]:
            if sym not in included:
                continue
            rel = [e for e in evs if sym.lower() in (e.get("title") or "").lower()] or evs
            add_edge({"id": edge_id(tid, "developed_for", f"disease:{sym}"), "source": tid,
                      "target": f"disease:{sym}", "type": "developed_for",
                      "label": "developed for",
                      "explanation": (f"{t['label']} has been investigated for {sym}-related disorders "
                                      f"(stage: {t['stage']})."),
                      "evidence_level": "clinical" if t["stage"] in ("clinical", "approved") else "experimental",
                      "status": "contested" if cevs else "supported",
                      "confidence": round(conf_from_evidence(rel), 2),
                      "evidence": rel, "counter_evidence": cevs})

    # ---------------------------------------------------------------- clusters
    def eids(pred):
        return sorted(e["id"] for e in edges.values() if pred(e))

    def members_with(mech):
        return sorted({e["source"] for e in edges.values()
                       if e["type"] == "driven_by" and e["target"] == mech and e["evidence"]})

    clusters = []
    hap = sorted(set(members_with("mech:haploinsufficiency")) |
                 set(members_with("mech:protein-destabilization")))
    clusters.append({
        "id": "cluster:dose-and-stability", "label": "Too little working protein: haploinsufficiency and destabilized protein",
        "basis": "mechanism", "members": hap + ["mech:haploinsufficiency", "mech:protein-destabilization"],
        "rationale": ("In these disorders the cell ends up with too little usable protein, either "
                      "because one gene copy is lost (haploinsufficiency) or because the variant "
                      "protein is unstable, degraded or stuck in the endoplasmic reticulum. The "
                      "therapeutic logic is the same for both routes: raise the amount of working "
                      "protein, by gene supplementation or by helping the protein fold. This is the "
                      "cluster that links STXBP1 to SLC6A1 across two unrelated pathways."),
        "edge_ids": eids(lambda e: e["type"] == "driven_by" and e["target"] in
                         ("mech:haploinsufficiency", "mech:protein-destabilization")) +
                    eids(lambda e: e["type"] == "shares_mechanism" and
                         "mech:protein-destabilization" in (e["attrs"].get("shared_effects") or [])),
    })
    dn = members_with("mech:dominant-negative")
    clusters.append({
        "id": "cluster:dominant-negative-fusion-block", "label": "Dominant-negative block of vesicle fusion",
        "basis": "mechanism", "members": dn + ["mech:dominant-negative", "mech:snare-complex-assembly"],
        "rationale": ("Here the altered protein is still present and jams the fusion machine it "
                      "belongs to, so the result is worse than simply having half the normal amount. "
                      "This matters therapeutically: adding a healthy gene copy may not be enough if "
                      "the bad protein keeps interfering, so these variants may need silencing or "
                      "allele-specific approaches instead. For STXBP1 the dominant-negative reading "
                      "is contested, and both sides are attached to the edges."),
        "edge_ids": eids(lambda e: e["type"] == "driven_by" and e["target"] == "mech:dominant-negative"),
    })
    gof = members_with("mech:gain-of-function")
    clusters.append({
        "id": "cluster:release-timing-and-clamping", "label": "Too much or badly timed release: Ca2+ sensing and clamping defects",
        "basis": "mechanism",
        "members": gof + ["mech:gain-of-function", "mech:ca-triggered-exocytosis"],
        "rationale": ("A separate group of variants does not reduce release but makes it excessive, "
                      "poorly timed, or un-clamped at rest: vesicles fuse when they should not. "
                      "Drugs that push more release (aminopyridines) are a poor fit here and could "
                      "make things worse, which is why several groups argue for classifying these "
                      "disorders by variant function rather than by gene."),
        "edge_ids": eids(lambda e: e["type"] == "driven_by" and e["target"] == "mech:gain-of-function") +
                    eids(lambda e: e["type"] == "participates_in" and e["target"] == "mech:ca-triggered-exocytosis"),
    })
    nmj = sorted({f"disease:{s}" for s in ("SYT2", "SNAP25", "UNC13A") if s in included})
    clusters.append({
        "id": "cluster:presynaptic-nmj-treatable", "label": "Presynaptic neuromuscular-junction failure (drug-responsive)",
        "basis": "mechanism", "members": nmj + ["therapy:3-4-diaminopyridine",
                                                "therapy:acetylcholinesterase-inhibitor-cms"],
        "rationale": ("The same genes that cause brain disease can also cause fatigable muscle "
                      "weakness when the failing synapse is the neuromuscular junction. That version "
                      "is partly treatable today with 3,4-diaminopyridine and cholinesterase "
                      "inhibitors. This is the most actionable cluster in the slice: it means a "
                      "family with a presynaptic congenital myasthenic syndrome in SYT2, SNAP25 or "
                      "UNC13A should be assessed for an existing drug, not only for future gene therapy."),
        "edge_ids": eids(lambda e: e["type"] in ("developed_for", "targets") and
                         e["source"] in ("therapy:3-4-diaminopyridine",
                                         "therapy:acetylcholinesterase-inhibitor-cms")),
    })
    clusters.append({
        "id": "cluster:snareopathy-family", "label": "SNAREopathies: one presynaptic fusion machine, many diagnoses",
        "basis": "pathway",
        "members": sorted([f"disease:{s}" for s in included if s not in BRIDGE_GENES] +
                          [f"gene:{s}" for s in included if s not in BRIDGE_GENES]),
        "rationale": ("Every gene here encodes a part of the machine that fuses a synaptic vesicle "
                      "with the nerve-cell membrane, or a protein that regulates it. Patients receive "
                      "very different diagnoses (epileptic encephalopathy, febrile-seizure epilepsy, "
                      "a movement disorder, a myasthenic syndrome), but reviews argue these are one "
                      "disease family, so research assets and trial designs may be shareable."),
        "edge_ids": eids(lambda e: e["type"] in ("participates_in", "shares_mechanism")),
    })

    # ---------------------------------------------------------------- gaps
    gaps = [
        {"id": "gap:stx1a-mendelian-validity",
         "about": "STX1A as a Mendelian disease gene",
         "question": "Is STX1A an established Mendelian disease gene, and under which entity?",
         "what_is_missing": [
             "No OMIM gene-phenotype entry: Monarch returns no OMIM causal edge for STX1A.",
             "Orphanet links STX1A only as 'Role in the phenotype of' Williams syndrome (a "
             "contiguous-gene deletion) and 'Modifying germline mutation in' cystic fibrosis.",
             "Gene2Phenotype confidence is moderate for a neurodevelopmental disorder with epilepsy "
             "and limited without epilepsy; ClinGen has no classification.",
             "No HPO annotations exist for any STX1A-specific entity, so it has no phenotype profile "
             "and cannot enter the phenotype-similarity comparison."],
         "searched": ["Monarch v3 CausalGeneToDiseaseAssociation + CorrelatedGeneToDiseaseAssociation",
                      "Orphadata rd-associated-genes for ORPHA:904 and ORPHA:586",
                      "Open Targets gene2phenotype / clingen / orphanet / genomics_england evidence",
                      "HPO phenotype.hpoa (2026-09-02) database_id column", "PubMed (PMID:36564538)"],
         "how_to_find_out": "One peer-reviewed case series (PMID:36564538, eight individuals) exists "
                            "and calls this a SNAREopathy. A ClinGen gene-curation expert panel "
                            "classification, or a second independent cohort with functional data, "
                            "would settle it. We keep STX1A in the graph with gene_disease_validity "
                            "recorded as G2P moderate / ClinGen absent."},
        {"id": "gap:cplx1-functional-evidence",
         "about": "CPLX1 disease mechanism",
         "question": "What is the molecular mechanism of CPLX1-related disease in human neurons?",
         "what_is_missing": [
             "No functional study of patient CPLX1 variants in neurons was found.",
             "The mechanism rests on the discovery paper's own cautious wording about loss of "
             "complexin-1 function.",
             "ClinGen and Gene2Phenotype have no classification for CPLX1."],
         "searched": ["PubMed via MCP (CPLX1 complexin-1 variant/function/neuron queries)",
                      "Open Targets gene2phenotype / clingen", "QuickGO annotations for O14810"],
         "how_to_find_out": "Patient-derived or knock-in neurons measuring spontaneous versus evoked "
                            "release would show whether CPLX1 variants de-clamp spontaneous release "
                            "(as complexin's clamping role predicts) or reduce evoked release."},
        {"id": "gap:nsf-functional-evidence",
         "about": "NSF mechanism",
         "question": "Do NSF variants act by a dominant-negative effect in neurons?",
         "what_is_missing": [
             "The dominant-negative claim comes from a Drosophila eye-development assay, not neurons.",
             "No electrophysiology in mammalian neurons or patient-derived cells was found.",
             "Only one Mendelian NSF report exists (PMID:31675180)."],
         "searched": ["PubMed via MCP (NSF epileptic encephalopathy / function queries)",
                      "Open Targets (only Genomics England amber for DEE96)", "ClinVar (18 P/LP records)"],
         "how_to_find_out": "Express the patient variants in Nsf-null or wild-type mammalian neurons "
                            "and measure SNARE-complex turnover and release. NSF is a recycling ATPase, "
                            "so a dominant-negative effect is plausible but unproven."},
        {"id": "gap:syt1-stx1b-therapy",
         "about": "Therapies for SYT1, STX1B, CPLX1, STX1A and NSF",
         "question": "Is any therapeutic approach under investigation for these five genes?",
         "what_is_missing": [
             "No AAV, ASO, chaperone, gene-editing or repurposed-drug programme was found for STX1B, "
             "CPLX1, STX1A or NSF.",
             "For SYT1 the only therapeutic signal is the K+-channel antagonist rescue reported inside "
             "a mechanism paper (PMID:32362337); no trial or dedicated therapy paper was found."],
         "searched": ["PubMed via MCP (gene + gene therapy / AAV / ASO / chaperone / drug queries)",
                      "ClinicalTrials.gov API v2 (per-gene condition and intervention searches)"],
         "how_to_find_out": "Check with the relevant patient foundations and recent conference "
                            "abstracts, which the atlas does not index. Absence here means absence "
                            "from PubMed and ClinicalTrials.gov as searched, not absence of work."},
        {"id": "gap:bridge-human-efficacy",
         "about": "The STXBP1 / SLC6A1 chaperone bridge",
         "question": "Does 4-phenylbutyrate help patients, and does it correct the mutant protein or "
                     "boost the healthy copy?",
         "what_is_missing": [
             "No completed trial with posted efficacy results: NCT04937062 (STXBP1 + SLC6A1) is early "
             "phase 1 and its primary endpoints are safety and tolerability; NCT07847918 tests the "
             "feasibility of a remote trial design.",
             "The only human outcome data found is two uncontrolled patients with 3p deletions "
             "(PMID:39923323), who have no misfolded protein to correct.",
             "Whether the drug acts on the mutant or on wild-type trafficking is unresolved by the "
             "proponents' own statement (PMID:35911425).",
             "No study stratifies response by variant class (ER-retained versus surface-expressed), "
             "which is the prediction that would test the mechanism."],
         "searched": ["PubMed via MCP (phenylbutyrate / chaperone + STXBP1 / SLC6A1)",
                      "ClinicalTrials.gov API v2 (NCT04937062, NCT07847918, NCT07173153, NCT06983158)"],
         "how_to_find_out": "A trial or n-of-1 series that reports outcomes separately for "
                            "ER-retained versus surface-expressed variants. The functional "
                            "classifications already exist (PMID:34028503, PMID:38781976), so "
                            "existing cohorts could be re-analysed by variant class."},
        {"id": "gap:variant-level-mechanism-map",
         "about": "Which variant has which effect",
         "question": "Can each pathogenic variant be assigned to a mechanism class, rather than each gene?",
         "what_is_missing": [
             "Our variant_group nodes are consequence classes from ClinVar, not functional classes.",
             "Published functional data covers only tens of variants per gene, against 495 P/LP "
             "ClinVar records for STXBP1 and 243 for SLC6A1.",
             "Several genes show opposite effects for different variants (SNAP25 I67N versus V48F; "
             "STX1B G226R versus V216E; UNC13A dominant versus recessive), so gene-level mechanism "
             "labels are unsafe for choosing a therapy."],
         "searched": ["ClinVar esearch/esummary per gene (molecular_consequence_list)",
                      "PubMed functional studies per gene"],
         "how_to_find_out": "Link each ClinVar VCV to published functional readouts (surface "
                            "expression, protein level, evoked and spontaneous release) in a "
                            "variant-level table. The field is explicitly calling for this "
                            "(PMID:41166419)."},
        {"id": "gap:snap25-cms-vs-dee",
         "about": "SNAP25 phenotype split",
         "question": "Why does one SNAP25 variant cause a myasthenic syndrome while others cause "
                     "epileptic encephalopathy?",
         "what_is_missing": [
             "OMIM 616330 is 'congenital myasthenic syndrome 18', but ClinGen classifies SNAP25 as "
             "Definitive for genetic developmental and epileptic encephalopathy. The umbrella covers "
             "both, and HPO annotations exist only for the myasthenic entity.",
             "No study compares neuromuscular-junction and central phenotypes for the same variant set."],
         "searched": ["Monarch v3 entities for MONDO:0014590 and MONDO:0700466",
                      "HPO phenotype.hpoa (OMIM:616330 only)",
                      "Open Targets ClinGen and Genomics England evidence", "PubMed (PMID:33299146, 25381298, 40181518)"],
         "how_to_find_out": "A cohort reporting neuromuscular testing (repetitive nerve stimulation) "
                            "in SNAP25-DEE patients would show whether subclinical neuromuscular "
                            "involvement is common and therefore drug-addressable."},
    ]

    # ---------------------------------------------------------------- write
    frag = {"nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
            "edges": sorted(edges.values(), key=lambda e: (e["type"], e["id"])),
            "clusters": clusters, "gaps": gaps}
    write_json(CURATED / "biology.json", frag)
    bt = defaultdict(int)
    for n in frag["nodes"]:
        bt[n["type"]] += 1
    be = defaultdict(int)
    for e in frag["edges"]:
        be[e["type"]] += 1
    print(f"nodes {len(frag['nodes'])}: {dict(bt)}")
    print(f"edges {len(frag['edges'])}: {dict(be)}")
    print(f"clusters {len(clusters)}, gaps {len(gaps)}")
    nq = sum(1 for e in frag["edges"] for x in e["evidence"] + e.get("counter_evidence", []) if x.get("quote"))
    print(f"quoted evidence items on edges: {nq}")
    print(f"wrote {CURATED / 'biology.json'} (generated {TODAY})")


if __name__ == "__main__":
    main()
