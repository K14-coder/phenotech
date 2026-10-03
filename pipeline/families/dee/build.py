"""Assemble data/curated/family_dee.json from the fetched/cached DEE sources and curated needles.

Run (after fetch_bio, clinvar, quickgo, hpo, pubmed):  python3 pipeline/families/dee/build.py
Then:  python3 pipeline/families/dee/verify.py
"""
from __future__ import annotations

from collections import defaultdict

import curation as CUR
from dee_common import GENES, OUT_FRAGMENT, RAW, TODAY, edge_id, evidence, existing_graph, read_json, write_json

FAMILY = "dee"
DISEASE_META = {
    "SCN1A": ("SCN1A-related disorders (incl. Dravet syndrome)", ["Dravet syndrome", "DEE6A", "GEFS+2", "FHM3", "NaV1.1"]),
    "SCN2A": ("SCN2A-related disorders", ["SCN2A-DEE", "DEE11", "BFNIS", "NaV1.2"]),
    "SCN8A": ("SCN8A-related disorders", ["SCN8A-DEE", "DEE13", "NaV1.6"]),
    "KCNQ2": ("KCNQ2-related disorders", ["KCNQ2-DEE", "DEE7", "self-limited familial neonatal epilepsy", "Kv7.2"]),
    "KCNT1": ("KCNT1-related disorders", ["EIMFS", "epilepsy of infancy with migrating focal seizures", "DEE14", "ADNFLE"]),
    "CACNA1A": ("CACNA1A-related disorders", ["episodic ataxia type 2", "EA2", "FHM1", "SCA6", "DEE42", "CaV2.1"]),
    "GRIN2B": ("GRIN2B-related disorders", ["GRIN2B-NDD", "DEE27", "GluN2B"]),
    "CDKL5": ("CDKL5 deficiency disorder", ["CDD", "DEE2", "CDKL5-related disorders"]),
    "SYNGAP1": ("SYNGAP1-related disorders", ["SYNGAP1-ID", "MRD5", "SynGAP"]),
    "SLC2A1": ("SLC2A1-related disorders (GLUT1 deficiency syndrome)", ["Glut1DS", "GLUT1 deficiency", "G1D", "De Vivo disease"]),
}
VG_GROUPS = {
    "truncating": ("Truncating variants (nonsense, frameshift, start-lost)", ["nonsense", "frameshift", "start_lost"], "truncating"),
    "missense": ("Missense variants (single amino-acid changes)", ["missense"], "missense"),
    "splice": ("Splice-site variants", ["splice", "intronic_or_splice_region"], "splice"),
    "whole-gene-deletion": ("Single-gene deletions / duplications", ["cnv_single_gene", "intragenic_deletion_or_duplication"], "cnv"),
    "contiguous-gene-deletion": ("Larger deletions spanning this gene and its neighbours", ["cnv_multigene"], "cnv"),
}
MIXED_MISSENSE = {"SCN1A", "SCN2A", "SCN8A", "KCNQ2", "CACNA1A", "GRIN2B"}  # mechanism set per subgroup


def ev(ref, needle, study_type, supports=None):
    q = CUR.quote_for(ref, needle)
    m = CUR.meta_for(ref)
    if ref.startswith("NCT"):
        src, kind, title = "ClinicalTrials.gov", "trial", f"{m['title']} [{m.get('status')}" + (f"; {m['why_stopped']}" if m.get("why_stopped") else "") + "]"
    elif ref.startswith("FDA-label:"):
        src, kind, title = "Website", "website", m["title"]
    else:
        src, kind, title = "PubMed", "publication", m["title"]
    return evidence(src, ref, m["url"], kind, extracted_by="agent-curation", title=title, year=m.get("year"),
                    quote=q, study_type=study_type, supports=supports, verified=False)


def conf_from(evs):
    pubs = [e for e in evs if e.get("supports", True) is not False and e["kind"] in ("publication", "trial", "website")]
    return 0.8 if len(pubs) >= 2 else 0.6 if pubs else 0.5


def main():
    genes, dis = read_json(RAW / "genes.json"), read_json(RAW / "diseases.json")
    cv, hpo, go = read_json(RAW / "clinvar_summary.json"), read_json(RAW / "hpo_fragment.json"), read_json(RAW / "go_fragment.json")
    existing = existing_graph()
    nodes, edges = {}, {}

    def add_node(n):
        if n["id"] in existing and not n.get("_force"):
            return
        n.pop("_force", None)
        nodes[n["id"]] = n

    def add_edge(e):
        if not e.get("counter_evidence"):
            e.pop("counter_evidence", None)
        edges[e["id"]] = e

    # ---------------- genes
    for sym in GENES:
        g = genes[sym]
        syn = list(dict.fromkeys(g["protein_synonyms_curated"] + g.get("alias_symbol", []) + g.get("prev_symbol", [])
                                 + [g.get("protein_name")] + g.get("protein_alt_names", [])))
        xr = {"HGNC": g["hgnc_id"], "NCBIGene": g["entrez_id"], "Ensembl": g["ensembl_gene_id"], "OMIM": g.get("omim_id"),
              "UniProt": g.get("uniprot_acc"), "MANE_Select": g.get("mane_enst")}
        srcs = [evidence("HGNC", g["hgnc_id"], g["hgnc_url"], "database", title=f"HGNC symbol report: {sym} ({g['name']})",
                         study_type="database_record"),
                evidence("UniProt", g["uniprot_acc"], g["uniprot_url"], "database",
                         title=f"UniProtKB {g['uniprot_entry']} ({g.get('protein_name')})", quote=g.get("uniprot_function"),
                         study_type="database_record", verified=False)]
        add_node({"id": f"gene:{sym}", "type": "gene", "label": sym, "synonyms": [s for s in syn if s],
                  "xrefs": {k: v for k, v in xr.items() if v}, "summary": g.get("uniprot_function"),
                  "attrs": {"protein": g.get("protein_name"), "function": g.get("uniprot_function"),
                            "protein_length_aa": g.get("protein_length_aa"), "cds_length_bp": g.get("cds_length_bp"),
                            "aav_cds_fits_4_7kb": (g.get("cds_length_bp") or 99999) <= 4700, "family": FAMILY},
                  "sources": srcs})

    # ---------------- diseases + causes
    for sym in GENES:
        d = dis[sym]
        label, extra_syn = DISEASE_META[sym]
        subtypes, omim, orpha, mondo, syns, inh = [], [], [], [], [], []
        for e in d["entities"]:
            srcs = {m["primary_knowledge_source"] for m in e["monarch_edges"]}
            oc = [c for c, a in d["orphanet_associations"].items() if a.get("causal") and c in e["orpha_from_edges"]]
            if "infores:omim" not in srcs and not oc:
                continue
            st = {"name": e["name"], "MONDO": e["mondo"]}
            if e["omim_from_edges"]:
                st["OMIM"] = e["omim_from_edges"]
                omim += e["omim_from_edges"]
            if oc:
                st["ORPHA"] = oc
                orpha += oc
            if e.get("inheritance"):
                st["inheritance"] = e["inheritance"]
                inh.append(e["inheritance"])
            subtypes.append(st)
            mondo.append(e["mondo"])
            syns += e["synonyms"]
        for c, a in d["orphanet_associations"].items():
            if a.get("causal") and a.get("n_genes_associated") == 1 and c not in orpha:
                subtypes.append({"name": a["name"], "ORPHA": [c]})
                orpha.append(c)
        eb = d["established_by"]
        add_node({"id": f"disease:{sym}", "type": "disease", "label": label,
                  "synonyms": list(dict.fromkeys(extra_syn + syns))[:40],
                  "xrefs": {"MONDO": sorted(set(mondo)), "OMIM": sorted(set(omim)), "ORPHA": sorted(set(orpha)),
                            "HGNC": genes[sym]["hgnc_id"]},
                  "summary": f"Gene-defined umbrella for conditions caused by variants in {sym} ({len(subtypes)} curated clinical entities in OMIM/Orphanet).",
                  "attrs": {"subtypes": subtypes, "inheritance": "; ".join(sorted(set(inh))) or None, "gene": sym,
                            "family": FAMILY, "gene_disease_validity": {"gene2phenotype": eb["g2p_confidence"],
                                                                       "clingen": eb["clingen_classification"],
                                                                       "omim_causal_edge": eb["omim_causal"]}},
                  "sources": [evidence("Monarch", genes[sym]["hgnc_id"], f"https://monarchinitiative.org/{genes[sym]['hgnc_id']}",
                                       "database", title=f"Monarch gene-to-disease associations for {sym}",
                                       study_type="database_record")]})
        evs = []
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                oo = m.get("original_object") or ""
                if m["primary_knowledge_source"] == "infores:omim" and oo.startswith("OMIM:"):
                    evs.append(evidence("OMIM", oo, f"https://omim.org/entry/{oo[5:]}", "database",
                                        title=f"OMIM {oo[5:]}: {e['name']} ({sym})", study_type="database_record"))
        for c, a in d["orphanet_associations"].items():
            if a.get("causal") and a.get("n_genes_associated") == 1:
                evs.append(evidence("Orphanet", f"ORPHA:{c}", a["url"], "database",
                                    title=f"Orphanet ORPHA:{c} {a['name']}: {sym} - {a['association_type']}",
                                    study_type="database_record"))
        evs = list({x["ref"]: x for x in evs}.values())[:8]
        ref, nd = CUR.DISCOVERY[sym]
        evs.append(ev(ref, nd, "case_series"))
        add_edge({"id": edge_id(f"gene:{sym}", "causes", f"disease:{sym}"), "source": f"gene:{sym}",
                  "target": f"disease:{sym}", "type": "causes", "label": "causes",
                  "explanation": f"Variants in {sym} cause {label}; {len(subtypes)} curated clinical entities sit under this umbrella.",
                  "evidence_level": "clinical", "status": "supported", "confidence": 0.92, "evidence": evs})

    # ---------------- GO process mechanisms, phenotypes
    for n in go["nodes"] + hpo["nodes"]:
        add_node(n)
    for e in go["edges"] + hpo["edges"]:
        add_edge(e)

    # ---------------- driven_by
    claims = defaultdict(list)
    for c in CUR.DISEASE_MECHANISM_CLAIMS:
        claims[(c[0], c[1])].append(c)
    mainstream = {}
    for sym in GENES:
        cands = [(sum(1 for c in cl if c[4] is True), slug) for (s, slug), cl in claims.items() if s == sym]
        mainstream[sym] = max(cands)[1]
    for (sym, slug), cl in claims.items():
        pro = [c for c in cl if c[4] in (True, "minority")]
        con = [c for c in cl if c[4] is False]
        minority = all(c[4] == "minority" for c in pro)
        evs = [ev(c[2], c[3], c[5], True) for c in pro]
        cevs = [ev(c[2], c[3], c[5], False) for c in con]
        if not minority and slug == mainstream[sym]:
            cevs += [ev(c[2], c[3], c[5], False) for (s2, sl2), cl2 in claims.items() if s2 == sym
                     for c in cl2 if c[4] == "minority"]
        name = slug.replace("-", " ")
        expl = (f"Published work links {sym}-related disorders to {name}." if not minority else
                f"A minority of published {sym} variants act by {name}, unlike the gene's mainstream mechanism.")
        if cevs:
            expl += " Findings on other variant mechanisms in this gene are attached as counter-evidence."
        conf = conf_from(evs)
        add_edge({"id": edge_id(f"disease:{sym}", "driven_by", f"mech:{slug}"), "source": f"disease:{sym}",
                  "target": f"mech:{slug}", "type": "driven_by", "label": "driven by", "explanation": expl,
                  "evidence_level": "experimental", "status": "contested" if (cevs or minority) else "supported",
                  "confidence": round(min(conf, 0.5) if minority else conf, 2), "evidence": evs, "counter_evidence": cevs,
                  "attrs": {"minority_mechanism": minority, "family": FAMILY}})

    # ---------------- variant groups (ClinVar) + literature subgroups
    hap_claims = {s for (s, sl) in claims if sl == "haploinsufficiency"}
    for sym in GENES:
        c = cv[sym]
        for slug, (lab, cats, cons) in VG_GROUPS.items():
            counts = {k: c["by_consequence"].get(k, 0) for k in cats if c["by_consequence"].get(k)}
            total = sum(counts.values())
            if not total:
                continue
            ex = [f"{x['title']} [{x['accession']}; {x['classification']}]" for k in cats for x in c["examples"].get(k, [])[:2]]
            vid = f"vg:{sym}:{slug}"
            cvev = evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                            title=f"ClinVar P/LP records for {sym} ({c['esearch_count']} records)", study_type="database_record")
            add_node({"id": vid, "type": "variant_group", "label": f"{sym}: {lab}",
                      "summary": f"{total} of {c['n_classified_PLP']} pathogenic/likely-pathogenic ClinVar records for {sym} fall in this group.",
                      "attrs": {"gene": sym, "consequence": cons, "example_variants": ex[:4], "clinvar_counts": counts,
                                "clinvar_total_in_group": total, "family": FAMILY}, "sources": [cvev]})
            add_edge({"id": edge_id(vid, "variant_in", f"gene:{sym}"), "source": vid, "target": f"gene:{sym}",
                      "type": "variant_in", "label": "variants in", "explanation": f"{total} ClinVar P/LP records in {sym}.",
                      "evidence_level": "curated", "status": "supported", "confidence": 0.9, "evidence": [cvev]})
            tgt, evs, lvl, conf, st = None, None, None, None, None
            if slug in ("truncating", "splice", "whole-gene-deletion"):
                tgt = "mech:haploinsufficiency"
                if sym in hap_claims:
                    evs = [ev(x[2], x[3], x[5], True) for x in claims[(sym, "haploinsufficiency")]]
                    lvl, conf, st = "experimental", conf_from(evs), "supported"
                else:
                    evs = [dict(cvev, title=f"{total} {cons} P/LP records in {sym}; loss of one copy inferred from consequence class")]
                    lvl, conf, st = "inferred", 0.45, "unverified"
            elif slug == "missense" and sym not in MIXED_MISSENSE:
                m = mainstream[sym]
                if m != "haploinsufficiency":
                    tgt, evs = f"mech:{m}", [ev(x[2], x[3], x[5], True) for x in claims[(sym, m)] if x[4] is True]
                    lvl, conf, st = "experimental", conf_from(evs), "supported"
            if tgt and evs:
                add_edge({"id": edge_id(vid, "has_effect", tgt), "source": vid, "target": tgt, "type": "has_effect",
                          "label": "has effect", "explanation": f"{lab} in {sym} are linked to {tgt[5:].replace('-', ' ')}.",
                          "evidence_level": lvl, "status": st, "confidence": round(conf, 2), "evidence": evs})
    for v in CUR.VARIANT_SUBGROUPS:
        sym, vid = v["gene"], f"vg:{v['gene']}:{v['slug']}"
        evs = [ev(r, n, "functional_study", True) for r, n in v["evidence"]]
        add_node({"id": vid, "type": "variant_group", "label": v["label"],
                  "summary": "Literature-defined functional subgroup of missense variants (ClinVar does not record variant function).",
                  "attrs": {"gene": sym, "consequence": "missense", "example_variants": v["examples"], "family": FAMILY,
                            "defined_by": "functional studies (PubMed)"}, "sources": evs[:1]})
        add_edge({"id": edge_id(vid, "variant_in", f"gene:{sym}"), "source": vid, "target": f"gene:{sym}", "type": "variant_in",
                  "label": "variants in", "explanation": f"Functionally characterised {sym} missense variants.",
                  "evidence_level": "experimental", "status": "supported", "confidence": conf_from(evs), "evidence": evs})
        add_edge({"id": edge_id(vid, "has_effect", f"mech:{v['mech']}"), "source": vid, "target": f"mech:{v['mech']}",
                  "type": "has_effect", "label": "has effect",
                  "explanation": f"Functional studies report {v['mech'].replace('-', ' ')} for this {sym} variant subgroup.",
                  "evidence_level": "experimental", "status": "supported", "confidence": conf_from(evs), "evidence": evs})

    # ---------------- therapies
    for t in CUR.THERAPIES:
        tid = f"therapy:{t['slug']}"
        if t.get("existing"):
            # annotate the existing node with new keys only (no conflicting attrs)
            ap = [{"agency": a["agency"], "label": a["label"], "source_ref": a["ref"]} for a in t.get("approvals", [])]
            nodes[tid] = {"id": tid, "type": "therapy", "label": t["label"], "attrs": {"approvals": ap},
                          "sources": [ev(a["ref"], "is indicated for the treatment of seizures associated with Dravet syndrome (DS)", "database_record")
                                      for a in t.get("approvals", [])]}
        else:
            add_node({"id": tid, "type": "therapy", "label": t["label"], "synonyms": t.get("synonyms", []),
                      "summary": t["summary"],
                      "attrs": {"modality": t["modality"], "stage": t["stage"], "family": FAMILY,
                                "target_genes": sorted(t["diseases"])},
                      "sources": [ev(*x) for x in t.get("node_evidence", [])]})
        for mech, mevs in t.get("targets", []):
            evs = [ev(*x, True) for x in mevs]
            add_edge({"id": edge_id(tid, "targets", mech), "source": tid, "target": mech, "type": "targets", "label": "targets",
                      "explanation": f"{t['label']} acts on {mech[5:].replace('-', ' ')}, as stated in the cited source.",
                      "evidence_level": "experimental", "status": "supported", "confidence": conf_from(evs), "evidence": evs})
        for sym, d in t["diseases"].items():
            evs = [ev(*x, True) for x in d["evidence"]]
            cevs = [ev(*x, False) for x in d.get("counter", [])]
            clinical = any(e["kind"] in ("trial", "website") or e.get("study_type") == "clinical_trial" for e in evs)
            approved = any(e["ref"].startswith("FDA-label:") for e in evs)
            attrs = {"family": FAMILY}
            if d.get("effect_by_mechanism"):
                attrs["effect_by_mechanism"] = d["effect_by_mechanism"]
            if approved:
                attrs["regulatory_status"] = "FDA-labelled indication"
            conf = 0.95 if approved else conf_from(evs)
            if cevs:
                conf = round(max(0.4, conf - 0.15), 2)
            add_edge({"id": edge_id(tid, "developed_for", f"disease:{sym}"), "source": tid, "target": f"disease:{sym}",
                      "type": "developed_for", "label": "developed for", "explanation": d["note"],
                      "evidence_level": "clinical" if clinical else "experimental",
                      "status": "contested" if cevs else "supported", "confidence": conf,
                      "evidence": evs, "counter_evidence": cevs, "attrs": attrs})

    # ---------------- family framing evidence on a cluster-backing edge set
    fam_ev = [ev(r, n, "review", True) for r, n in CUR.FAMILY_CLAIMS]

    # ---------------- community fragment (sub-agent), merged only if present
    comm_path = RAW / "community" / "community_fragment.json"
    comm_gaps = []
    if comm_path.exists():
        comm = read_json(comm_path)
        for n in comm.get("nodes", []):
            add_node(n)
        for e in comm.get("edges", []):
            add_edge(e)
        comm_gaps = comm.get("gaps", [])

    # drop edges whose endpoints exist nowhere
    known = set(nodes) | set(existing)
    dropped = [k for k, e in edges.items() if e["source"] not in known or e["target"] not in known]
    for k in dropped:
        edges.pop(k)

    # ---------------- clusters
    def eids(pred):
        return sorted(k for k, e in edges.items() if pred(e))

    cross = [e for e in edges.values() if e["type"] == "similar_phenotype" and (e.get("attrs") or {}).get("cross_family")]
    clusters = [
        {"id": "cluster:dee-channel-receptor-signalling-family", "label": "Ion-channel, receptor and signalling DEEs",
         "basis": "pathway", "members": [f"disease:{s}" for s in GENES],
         "rationale": "Ten genes whose disorders are developmental and epileptic encephalopathies (ILAE 2022, PMID:35503712) "
                      "and which a 2025 review groups by pathophysiologic category (channelopathies, receptor dysfunction, "
                      "synaptic signalling; PMID:40381457).",
         "edge_ids": eids(lambda e: e["type"] in ("causes", "participates_in") and e["source"][5:] in GENES)},
        {"id": "cluster:dee-sodium-channel-gof", "label": "Sodium-channel gain of function: sodium channel blockers reported to help",
         "basis": "mechanism",
         "members": ["disease:SCN2A", "disease:SCN8A", "disease:SCN1A", "vg:SCN2A:missense-gof", "vg:SCN8A:missense-gof",
                     "vg:SCN1A:missense-gof", "mech:gain-of-function", "therapy:sodium-channel-blockers"],
         "rationale": "Gain-of-function SCN2A, SCN8A and (rare) SCN1A variants; the sources report response to sodium channel "
                      "blockers (PMID:28379373, 34431999, 35696452).",
         "edge_ids": eids(lambda e: e["target"] == "mech:gain-of-function" and e["source"].split(":")[1] in ("SCN1A", "SCN2A", "SCN8A"))
                     + eids(lambda e: e["source"] == "therapy:sodium-channel-blockers")},
        {"id": "cluster:dee-sodium-channel-lof", "label": "Sodium-channel loss of function: sodium channel blockers reported to worsen",
         "basis": "mechanism",
         "members": ["disease:SCN1A", "disease:SCN2A", "disease:SCN8A", "vg:SCN2A:missense-lof", "vg:SCN8A:missense-lof",
                     "mech:loss-of-function", "mech:haploinsufficiency", "therapy:sodium-channel-blockers"],
         "rationale": "Loss-of-function SCN1A (Dravet), later-onset SCN2A and SCN8A LoF; sources describe sodium channel blockers as "
                      "worsening or contraindicated (PMID:9596203, 36314457, 28379373, 41515912). Recorded as counter-evidence.",
         "edge_ids": eids(lambda e: e["target"] in ("mech:loss-of-function", "mech:haploinsufficiency") and e["source"].split(":")[1] in ("SCN1A", "SCN2A", "SCN8A"))},
        {"id": "cluster:dee-same-gene-opposite-mechanism", "label": "Same gene, opposite mechanisms",
         "basis": "mechanism",
         "members": ["disease:SCN2A", "disease:SCN8A", "disease:KCNQ2", "disease:CACNA1A", "disease:GRIN2B",
                     "mech:gain-of-function", "mech:loss-of-function"],
         "rationale": "Genes where both gain- and loss-of-function variants cause disease; trial eligibility criteria already "
                      "split by mechanism (NCT06872125, NCT04639310, NCT05818553, NCT07019922).",
         "edge_ids": eids(lambda e: e["type"] == "driven_by" and e["source"].split(":")[1] in ("SCN2A", "SCN8A", "KCNQ2", "CACNA1A", "GRIN2B"))},
        {"id": "cluster:dee-snare-shared-symptoms", "label": "Shared symptoms with the SNAREopathies, different mechanisms",
         "basis": "phenotype", "members": sorted({x for e in cross for x in (e["source"], e["target"])}),
         "rationale": "HPO profiles of these DEE and SNAREopathy disorders are in the top 1% of similarity for both diseases, "
                      "while their molecular mechanisms differ (ion channels/receptors/signalling vs presynaptic vesicle fusion).",
         "edge_ids": sorted(e["id"] for e in cross)},
    ]
    clusters[0]["rationale"] += " Quotes: " + " | ".join(f"{x['ref']}: \"{x['quote']}\"" for x in fam_ev[:4])

    gaps = [
        {"id": "gap:dee-missense-function-map", "about": "disease:SCN2A",
         "question": "Which ClinVar missense variants in SCN1A/SCN2A/SCN8A/KCNQ2/CACNA1A/GRIN2B are gain- vs loss-of-function?",
         "what_is_missing": ["ClinVar records do not carry variant function; only literature-defined example subgroups are encoded"],
         "searched": ["ClinVar esearch '<GENE>[gene] AND (clinsig_pathogenic[prop] OR clinsig_likely_pathogenic[prop])'",
                      "PubMed: 'SCN2A[ti] AND autism AND (opposing OR loss-of-function) AND NaV1.2'",
                      "PubMed: 'SCN8A loss-of-function intellectual disability without epilepsy'"],
         "how_to_find_out": "Join ClinVar with published functional datasets (patch-clamp / MAVE) per variant."},
        {"id": "gap:dee-syngap1-therapy", "about": "disease:SYNGAP1",
         "question": "Is there a trial-stage or approved therapy for SYNGAP1-related disorders?",
         "what_is_missing": ["No SYNGAP1 therapy evidence was curated; a 2025 review mentions Ras-Raf-MEK-ERK inhibitors only in general terms"],
         "searched": ["PubMed: 'developmental and epileptic encephalopathies precision therapy ion channel gain of function loss of function review'"],
         "how_to_find_out": "Search ClinicalTrials.gov and PubMed for SYNGAP1 interventional studies."},
        {"id": "gap:dee-grin2b-cacna1a-slc2a1-therapies", "about": "disease:GRIN2B",
         "question": "Mechanism-matched therapies for GRIN2B (memantine, L-serine, radiprodil), SLC2A1 (ketogenic diet, triheptanoin) and CACNA1A were identified in the sources but not encoded in this build.",
         "what_is_missing": ["Sources are stored (PMIDs 41489401, 31213567, 38380699, 28533163, 32913944, 35441706, 38725190, 21734179; NCT05818943, NCT04646447, NCT03181399) but no therapy edges were emitted"],
         "searched": ["PubMed: 'memantine GRIN2B gain-of-function'", "PubMed: 'L-serine loss-of-function GRIN2B'", "PubMed: 'radiprodil GRIN'",
                      "PubMed: 'Glut1 deficiency syndrome ketogenic diet consensus recommendations Klepper'",
                      "PubMed: 'triheptanoin Glut1 deficiency randomized'", "PubMed: '4-aminopyridine episodic ataxia type 2 randomized'"],
         "how_to_find_out": "Add curated needles for these stored sources in a follow-up build."},
        {"id": "gap:dee-syndrome-vs-gene-indications", "about": "disease:SCN1A",
         "question": "Do Dravet syndrome approvals (fenfluramine, stiripentol, cannabidiol) apply equally to SCN1A-positive and SCN1A-negative patients?",
         "what_is_missing": ["FDA labels and pivotal trials enrol by syndrome, not by SCN1A variant mechanism"],
         "searched": ["openFDA labels FINTEPLA, DIACOMIT, EPIDIOLEX", "NCT02682927, NCT02091375 eligibility"],
         "how_to_find_out": "Subgroup analyses of pivotal trials by SCN1A status."},
    ]
    if not comm_path.exists():
        gaps.append({"id": "gap:dee-community-layer", "about": "disease:SCN1A",
                     "question": "Patient organisations, registries, trials and researchers for the 10 DEE genes are not yet merged.",
                     "what_is_missing": ["community_fragment.json was not produced; raw pages and CT.gov records are stored under data/raw/families/dee/community/"],
                     "searched": ["ClinicalTrials.gov API v2 per gene and syndrome", "Org websites (Dravet Syndrome Foundation, FamilieSCN2A, KCNQ2 Cure, IFCR, SynGAP Research Fund, Glut1 Deficiency Foundation, ...)",
                                  "Simons Searchlight gene pages"],
                     "how_to_find_out": "Run a community build with quote verification over the stored pages."})
    gaps += comm_gaps

    out = {"nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
           "edges": sorted(edges.values(), key=lambda e: e["id"]), "clusters": clusters, "gaps": gaps}
    write_json(OUT_FRAGMENT, out)
    print(f"wrote {OUT_FRAGMENT}: {len(nodes)} nodes, {len(edges)} edges, {len(clusters)} clusters, {len(gaps)} gaps; "
          f"dropped dangling {len(dropped)}: {dropped[:5]}")


if __name__ == "__main__":
    main()
