"""Assemble data/curated/family_rasopathy.json (one fragment, docs/SCHEMA.md shape).

Inputs: data/raw/families/rasopathy/{genes,diseases,clinvar_summary,hpo_fragment,go_fragment}.json,
        pubmed/, clinicaltrials/, fda/, web/, quickgo/, authors/ + curation.py + ras_subtypes.py
Reuses existing graph ids (mechanisms, phenotypes, researchers) instead of duplicating nodes.
Run:  python3 pipeline/families/rasopathy/build.py
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import curation as CUR
from ras_common import (FAMILY, GENES, OUT_FRAGMENT, RAW, TODAY, edge_id, evidence, existing_graph_ids, read_json,
                        slugify, write_json)
from ras_subtypes import GERMLINE_OMIM, SYNDROME_KEYS, orpha_gene_specific

EXISTING = existing_graph_ids()
nodes: dict[str, dict] = {}
edges: dict[str, dict] = {}

LABEL = {
    "PTPN11": ("PTPN11-related disorders",
               "Changes in PTPN11 (SHP2) are the most common cause of Noonan syndrome (short stature, heart defects, "
               "typical facial features). Different PTPN11 changes cause Noonan syndrome with multiple lentigines "
               "(formerly LEOPARD syndrome) or, when the gene copy is lost, metachondromatosis."),
    "SOS1": ("SOS1-related disorders", "Activating SOS1 changes cause Noonan syndrome, often with skin and hair "
             "features and normal development; a different SOS1 change causes hereditary gingival fibromatosis."),
    "RAF1": ("RAF1-related disorders", "Activating RAF1 changes cause Noonan syndrome (and NSML) with a very high rate "
             "of hypertrophic cardiomyopathy; other RAF1 changes are linked to dilated cardiomyopathy."),
    "BRAF": ("BRAF-related RASopathies (cardiofaciocutaneous syndrome)", "Germline BRAF changes mostly cause "
             "cardiofaciocutaneous (CFC) syndrome: heart defects, skin and hair changes and developmental delay; some "
             "cause Noonan syndrome or NSML."),
    "KRAS": ("KRAS-related RASopathies", "Germline KRAS changes cause Noonan syndrome or cardiofaciocutaneous "
             "syndrome; the same gene is a common cancer driver when changed in tumours."),
    "HRAS": ("HRAS-related disorders (Costello syndrome)", "Germline activating HRAS changes cause Costello syndrome: "
             "feeding problems, loose skin, heart disease, developmental delay and a raised tumour risk."),
    "NF1": ("NF1-related disorders (neurofibromatosis type 1)", "Loss of one NF1 copy causes neurofibromatosis type 1: "
            "cafe-au-lait spots, nerve-sheath tumours (neurofibromas, plexiform neurofibromas) and learning "
            "difficulties. Two MEK inhibitors are approved for plexiform neurofibromas."),
    "MAP2K1": ("MAP2K1-related disorders (cardiofaciocutaneous syndrome 3)", "Germline MAP2K1 (MEK1) changes cause "
               "cardiofaciocutaneous syndrome."),
    "SHOC2": ("SHOC2-related disorders (Mazzanti syndrome)", "A recurrent SHOC2 change causes Noonan syndrome-like "
              "disorder with loose anagen hair (Mazzanti syndrome)."),
    "CBL": ("CBL-related disorder", "Germline CBL changes cause a Noonan syndrome-like disorder with a predisposition "
            "to juvenile myelomonocytic leukaemia."),
    "RIT1": ("RIT1-related Noonan syndrome", "Activating RIT1 changes cause Noonan syndrome with a high rate of "
             "hypertrophic cardiomyopathy."),
    "LZTR1": ("LZTR1-related disorders", "LZTR1 changes cause dominant or recessive Noonan syndrome, and loss of one "
              "LZTR1 copy predisposes to schwannomatosis or isolated cafe-au-lait spots."),
}
SYN = {"PTPN11": ["Noonan syndrome 1", "NS1", "LEOPARD syndrome 1", "NSML", "metachondromatosis"],
       "SOS1": ["Noonan syndrome 4", "NS4", "gingival fibromatosis 1"], "RAF1": ["Noonan syndrome 5", "NS5", "LEOPARD syndrome 2"],
       "BRAF": ["CFC1", "cardiofaciocutaneous syndrome 1", "Noonan syndrome 7", "LEOPARD syndrome 3"],
       "KRAS": ["Noonan syndrome 3", "NS3", "CFC2"], "HRAS": ["Costello syndrome", "faciocutaneoskeletal syndrome"],
       "NF1": ["neurofibromatosis type 1", "von Recklinghausen disease", "NF1", "neurofibromatosis-Noonan syndrome", "Watson syndrome"],
       "MAP2K1": ["CFC3", "cardiofaciocutaneous syndrome 3", "MEK1"], "SHOC2": ["Mazzanti syndrome", "NSLAH1", "Noonan-like syndrome with loose anagen hair"],
       "CBL": ["NSLL", "Noonan syndrome-like disorder with or without juvenile myelomonocytic leukemia"],
       "RIT1": ["Noonan syndrome 8", "NS8"], "LZTR1": ["Noonan syndrome 10", "Noonan syndrome 2", "schwannomatosis 2"]}
GOF_GENES = ["PTPN11", "SOS1", "RAF1", "BRAF", "KRAS", "HRAS", "MAP2K1", "SHOC2", "RIT1"]
LOF_REG_GENES = ["NF1", "LZTR1", "CBL"]


def add_node(n):
    if n["id"] in EXISTING:          # reuse, never duplicate nodes that other layers own
        return
    nodes[n["id"]] = {k: v for k, v in n.items() if v not in (None, [], {})}


def add_edge(e):
    e = {k: v for k, v in e.items() if v not in (None, [], {}) or k in ("evidence",)}
    if e["id"] in edges:
        old = edges[e["id"]]
        for k in ("evidence", "counter_evidence"):
            old.setdefault(k, [])
            old[k] += [x for x in e.get(k, []) if x not in old[k]]
        old["confidence"] = max(old["confidence"], e["confidence"])
        return
    edges[e["id"]] = e


def ev(ref, needle, supports=True, study_type=None, title_extra=None):
    q = CUR.quote_for(ref, needle)
    m = CUR.meta_for(ref)
    if ref.startswith("PMID:"):
        return evidence("PubMed", ref, m["url"], "publication", extracted_by="agent-curation", title=m["title"],
                        year=m.get("year"), quote=q, study_type=study_type, supports=supports, verified=False)
    if ref.startswith("NCT"):
        t = f"{m['title']} [{m['status']}" + (f"; {m['why_stopped']}" if m.get("why_stopped") else "") + "]"
        return evidence("ClinicalTrials.gov", ref, m["url"], "trial", extracted_by="agent-curation", title=t,
                        year=m.get("year"), quote=q, study_type=study_type or "clinical_trial", supports=supports,
                        verified=False)
    if ref.startswith("FDA:"):
        return evidence("Website", m["url"], m["url"], "website", extracted_by="agent-curation", title=m["title"],
                        year=m.get("year"), quote=q, study_type="database_record", supports=supports, verified=False)
    return evidence("Website", m["url"], m["url"], "website", extracted_by="agent-curation", title=title_extra,
                    quote=q, supports=supports, verified=False, retrieved=m.get("retrieved"))


def conf_from(evs, base_db=False):
    pubs = [e for e in evs if e.get("supports", True) and e["kind"] in ("publication", "trial", "website")]
    if base_db and pubs:
        return 0.92
    return 0.8 if len(pubs) >= 2 else 0.6 if pubs else 0.5


def main():
    genes = read_json(RAW / "genes.json")
    dis = read_json(RAW / "diseases.json")
    cv = read_json(RAW / "clinvar_summary.json")
    hpo = read_json(RAW / "hpo_fragment.json")
    go = read_json(RAW / "go_fragment.json")

    # ------------------------------------------------------------ genes
    for s in GENES:
        g = genes[s]
        syn = list(dict.fromkeys(g["protein_synonyms_curated"] + g.get("alias_symbol", []) + g.get("prev_symbol", [])
                                 + [g.get("protein_name")] + g.get("protein_alt_names", [])))
        xr = {"HGNC": g["hgnc_id"], "NCBIGene": g["entrez_id"], "Ensembl": g["ensembl_gene_id"], "OMIM": g["omim_id"],
              "UniProt": g.get("uniprot_acc"), "MANE_Select": g.get("mane_enst")}
        srcs = [evidence("HGNC", g["hgnc_id"], g["hgnc_url"], "database", title=f"HGNC symbol report: {s} ({g['name']})",
                         study_type="database_record"),
                evidence("UniProt", g["uniprot_acc"], g["uniprot_url"], "database",
                         title=f"UniProtKB {g['uniprot_entry']} ({g.get('protein_name')})", quote=g.get("uniprot_function"),
                         study_type="database_record", verified=False)]
        add_node({"id": f"gene:{s}", "type": "gene", "label": s, "synonyms": [x for x in syn if x],
                  "xrefs": {k: v for k, v in xr.items() if v}, "summary": g.get("uniprot_function"),
                  "attrs": {"protein": g.get("protein_name"), "function": g.get("uniprot_function"),
                            "protein_length_aa": g.get("protein_length_aa"), "cds_length_bp": g.get("cds_length_bp"),
                            "family": FAMILY, "pathway_role": ("negative regulator of RAS" if s in LOF_REG_GENES
                                                               else "RAS/MAPK signal transducer or activator")},
                  "sources": srcs})

    # ------------------------------------------------------------ diseases + causes
    syndrome_genes = defaultdict(set)
    for s in GENES:
        d = dis[s]
        omim_causal = {}
        for e in d["entities"]:
            for m in e["monarch_edges"]:
                oo = m.get("original_object") or ""
                if m["primary_knowledge_source"] == "infores:omim" and oo.startswith("OMIM:"):
                    omim_causal[oo[5:]] = e
        missing = [o for o in GERMLINE_OMIM[s] if o not in omim_causal]
        assert not missing, f"{s}: curated OMIM ids not in Monarch OMIM causal edges: {missing}"
        subtypes, mondo, inh, syns = [], [], [], []
        for o in GERMLINE_OMIM[s]:
            e = omim_causal[o]
            st = {"name": e["name"], "MONDO": e["mondo"], "OMIM": o}
            orc = [c for c in e["orpha_from_edges"] if (d["orphanet_associations"].get(c) or {}).get("causal")]
            if orc:
                st["ORPHA"] = orc
            if e.get("inheritance"):
                st["inheritance"] = e["inheritance"]
                inh.append(e["inheritance"])
            subtypes.append(st)
            mondo.append(e["mondo"])
            syns += e["synonyms"][:6]
        for c in orpha_gene_specific(d):
            if not any(c in (st.get("ORPHA") or []) for st in subtypes):
                subtypes.append({"name": d["orphanet_associations"][c]["name"], "ORPHA": [c]})
        excluded = sorted({f"{e['name']} (OMIM:{o})" for o, e in omim_causal.items() if o not in GERMLINE_OMIM[s]})
        orpha_germline = sorted(c for c, a in d["orphanet_associations"].items()
                                if (a.get("association_type") or "").startswith("Disease-causing germline"))
        g2p = sorted({(r.get("diseaseFromSource"), (r.get("confidence") or "").lower()) for r in d["opentargets"]["evidence"]
                      if r["datasourceId"] == "gene2phenotype"})
        cg = sorted({(r.get("diseaseFromSource"), r.get("confidence")) for r in d["opentargets"]["evidence"]
                     if r["datasourceId"] == "clingen"})
        names = " ".join(st["name"].lower() for st in subtypes)
        for key, pat in [("noonan", r"\bnoonan syndrome \d"), ("nsml", r"leopard|multiple lentigines"),
                         ("cfc", r"cardiofaciocutaneous"), ("costello", r"costello"), ("nf1", r"neurofibromatosis type 1"),
                         ("noonan_like", r"noonan syndrome-like|cbl-related")]:
            if re.search(pat, names):
                syndrome_genes[key].add(s)
        if any(e["mondo"] == "MONDO:0021060" for e in d["entities"]):
            syndrome_genes["rasopathy"].add(s)       # ClinGen RASopathy curation (Monarch edge to MONDO:0021060)
        label, summary = LABEL[s]
        add_node({"id": f"disease:{s}", "type": "disease", "label": label,
                  "synonyms": list(dict.fromkeys(SYN[s] + syns))[:30],
                  "xrefs": {"MONDO": sorted(set(mondo)), "OMIM": GERMLINE_OMIM[s],
                            "ORPHA": sorted({c for st in subtypes for c in st.get("ORPHA", [])}),
                            "HGNC": genes[s]["hgnc_id"]},
                  "summary": summary,
                  "attrs": {"subtypes": subtypes, "inheritance": "; ".join(sorted(set(inh))) or None, "gene": s,
                            "family": FAMILY, "approved_treatment": s == "NF1",
                            "approved_treatment_note": ("selumetinib and mirdametinib (FDA) for plexiform neurofibromas"
                                                        if s == "NF1" else None),
                            "excluded_entities": excluded,
                            "gene_disease_validity": {"gene2phenotype": [f"{a}: {b}" for a, b in g2p],
                                                      "clingen": [f"{a}: {b}" for a, b in cg]}},
                  "sources": [evidence("Monarch", genes[s]["hgnc_id"], f"https://monarchinitiative.org/{genes[s]['hgnc_id']}",
                                       "database", title=f"Monarch Initiative gene-to-disease associations for {s}",
                                       study_type="database_record")]})
        evs = []
        for o in GERMLINE_OMIM[s]:
            evs.append(evidence("OMIM", f"OMIM:{o}", f"https://omim.org/entry/{o}", "database",
                                title=f"OMIM {o}: {omim_causal[o]['name']} - causal gene {s} (via Monarch)",
                                study_type="database_record"))
        for c in orpha_germline:
            a = d["orphanet_associations"][c]
            evs.append(evidence("Orphanet", f"ORPHA:{c}", a["url"], "database",
                                title=f"Orphanet ORPHA:{c} {a['name']}: {s} - {a['association_type']}",
                                study_type="database_record"))
        for name, conf in g2p:
            if conf in ("definitive", "strong", "moderate"):
                evs.append(evidence("OpenTargets", f"G2P:{s}:{slugify(name)}",
                                    f"https://platform.opentargets.org/target/{genes[s]['ensembl_gene_id']}", "database",
                                    title=f"Gene2Phenotype: {s} - {name} ({conf})", study_type="database_record"))
        for name, conf in cg:
            if conf in ("Definitive", "Strong", "Moderate"):
                evs.append(evidence("ClinGen", f"ClinGen:{s}:{slugify(name)}", "https://search.clinicalgenome.org/kb/genes/"
                                    + genes[s]["hgnc_id"], "database", title=f"ClinGen gene-disease validity: {s} - {name} = {conf}",
                                    study_type="database_record"))
        disc = [c for c in CUR.MECH if c[0] == s and c[4] is True and c[5] in ("case_series", "cohort")]
        if disc:
            evs.append(ev(disc[0][2], disc[0][3], True, disc[0][5]))
        add_edge({"id": edge_id(f"gene:{s}", "causes", f"disease:{s}"), "source": f"gene:{s}", "target": f"disease:{s}",
                  "type": "causes", "label": "causes",
                  "explanation": (f"Germline variants in {s} cause {label}: OMIM records {len(GERMLINE_OMIM[s])} germline "
                                  f"entit{'y' if len(GERMLINE_OMIM[s]) == 1 else 'ies'} under this umbrella"
                                  + (f", and ClinGen rates {'; '.join(f'{a} {b}' for a, b in cg if b in ('Definitive', 'Strong', 'Moderate'))}"
                                     if any(b in ('Definitive', 'Strong', 'Moderate') for _, b in cg) else "")
                                  + ". Somatic cancer associations of the same gene are deliberately excluded."),
                  "evidence_level": "clinical", "status": "supported", "confidence": conf_from(evs, base_db=True),
                  "evidence": evs, "attrs": {"family": FAMILY}})

    # ------------------------------------------------------------ mechanisms
    for n in go["nodes"]:
        add_node(n)
    for e in go["edges"]:
        add_edge(e)
    tor = read_json(RAW / "quickgo" / "terms_GO_0031929.json")["results"][0]
    add_node({"id": "mech:tor-signaling", "type": "mechanism", "label": "TOR (mTOR) signaling", "xrefs": {"GO": tor["id"]},
              "summary": tor["definition"]["text"], "attrs": {"kind": "process", "go_id": tor["id"], "go_name": tor["name"],
                                                              "family": FAMILY},
              "sources": [{"source": "GO", "ref": tor["id"], "url": f"https://www.ebi.ac.uk/QuickGO/term/{tor['id']}",
                           "title": tor["name"], "kind": "database", "study_type": "database_record",
                           "quote": tor["definition"]["text"], "extracted_by": "database", "retrieved": TODAY}]})
    for m in ("gain-of-function", "loss-of-function", "dominant-negative"):
        assert f"mech:{m}" in EXISTING, f"expected existing mech:{m} in data/graph.json"

    # orphanet mechanism annotations, e.g. "Disease-causing germline mutation(s) (gain of function) in"
    orpha_mech = defaultdict(list)
    for s in GENES:
        for c, a in dis[s]["orphanet_associations"].items():
            at = a.get("association_type") or ""
            for key, slug in (("(gain of function)", "gain-of-function"), ("(loss of function)", "loss-of-function")):
                if at.startswith("Disease-causing germline") and key in at:
                    orpha_mech[(s, slug)].append(evidence("Orphanet", f"ORPHA:{c}", a["url"], "database",
                                                          title=f"Orphanet ORPHA:{c} {a['name']}: {s} - {at}",
                                                          study_type="database_record"))
    by = defaultdict(list)
    for c in CUR.MECH:
        by[(c[0], c[1])].append(c)
    for (s, slug), cl in by.items():
        pro = [c for c in cl if c[4] is True]
        con = [c for c in cl if c[4] is False]
        evs = [ev(c[2], c[3], True, c[5]) for c in pro] + orpha_mech.get((s, slug), [])
        cevs = [ev(c[2], c[3], False, c[5]) for c in con]
        subt = sorted({c[7] for c in cl})
        expl = (f"Published work links {s}-related disorders ({'; '.join(subt)}) to "
                f"{'gain of function' if slug == 'gain-of-function' else 'loss of function' if slug == 'loss-of-function' else 'a dominant-negative effect'}. "
                + " ".join(c[6] for c in pro[:2]))
        if con:
            expl += " Limiting or contradicting findings are attached as counter-evidence: " + " ".join(c[6] for c in con[:2])
        if orpha_mech.get((s, slug)):
            expl += " Orphanet's curated gene-disease record also annotates this mechanism."
        add_edge({"id": edge_id(f"disease:{s}", "driven_by", f"mech:{slug}"), "source": f"disease:{s}",
                  "target": f"mech:{slug}", "type": "driven_by", "label": "driven by", "explanation": expl,
                  "evidence_level": "curated" if orpha_mech.get((s, slug)) else "experimental",
                  "status": "contested" if con else "supported",
                  "confidence": round(max(0.5, conf_from(evs) - (0.1 if con else 0)) + (0.1 if orpha_mech.get((s, slug)) else 0), 2),
                  "evidence": evs, "counter_evidence": cevs,
                  "attrs": {"applies_to_subtypes": subt, "n_supporting_publications": len(pro),
                            "n_counter_publications": len(con), "family": FAMILY}})
    # Orphanet-only mechanism edges (e.g. HRAS Costello GoF is also published above)
    for (s, slug), evs in orpha_mech.items():
        eid = edge_id(f"disease:{s}", "driven_by", f"mech:{slug}")
        if eid not in edges:
            add_edge({"id": eid, "source": f"disease:{s}", "target": f"mech:{slug}", "type": "driven_by",
                      "label": "driven by", "explanation": f"Orphanet's curated gene-disease record annotates {s} "
                      f"variants as {slug.replace('-', ' ')} for this disorder.", "evidence_level": "curated",
                      "status": "supported", "confidence": 0.7, "evidence": evs, "attrs": {"family": FAMILY}})

    # ------------------------------------------------------------ variant groups (ClinVar)
    VG = {"truncating": ("Truncating variants (nonsense, frameshift, start-lost)", ["nonsense", "frameshift", "start_lost"], "truncating"),
          "missense": ("Missense variants (single amino-acid changes)", ["missense"], "missense"),
          "inframe": ("In-frame insertions/deletions/duplications", ["inframe_indel"], "mixed"),
          "splice": ("Splice-site variants", ["splice", "intronic_or_splice_region"], "splice"),
          "whole-gene-deletion": ("Single-gene deletions / duplications", ["cnv_single_gene", "intragenic_deletion_or_duplication"], "cnv"),
          "contiguous-gene-deletion": ("Larger deletions/duplications spanning this gene and its neighbours", ["cnv_multigene"], "cnv")}
    LOF_TRUNC = {"NF1": ["truncating", "splice", "whole-gene-deletion", "missense"], "LZTR1": ["truncating", "splice", "missense"],
                 "PTPN11": ["truncating", "splice"], "CBL": ["missense"]}
    for s in GENES:
        c = cv[s]
        for slug, (lab, cats, cons) in VG.items():
            counts = {k: c["by_consequence"].get(k, 0) for k in cats if c["by_consequence"].get(k)}
            total = sum(counts.values())
            if not total:
                continue
            ex = [f"{e['title']} [{e['accession']}; {e['classification']}; {e['review_status']}]"
                  for k in cats for e in c["examples"].get(k, [])[:2]]
            vid = f"vg:{s}:{slug}"
            dbev = evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                            title=f"ClinVar esearch/esummary for {s} (P/LP; {c['esearch_count']} records)",
                            study_type="database_record")
            add_node({"id": vid, "type": "variant_group", "label": f"{s}: {lab}",
                      "attrs": {"gene": s, "consequence": cons, "example_variants": ex[:4], "clinvar_counts": counts,
                                "clinvar_total_in_group": total, "clinvar_gene_total_PLP": c["n_classified_PLP"], "family": FAMILY},
                      "summary": (f"{total} of {c['n_classified_PLP']} pathogenic or likely-pathogenic ClinVar records for "
                                  f"{s} fall in this group."
                                  + (" These copy-number changes cover more than one gene, so no mechanism edge is drawn."
                                     if slug == "contiguous-gene-deletion" else "")),
                      "sources": [dbev]})
            add_edge({"id": edge_id(vid, "variant_in", f"gene:{s}"), "source": vid, "target": f"gene:{s}",
                      "type": "variant_in", "label": "variants in",
                      "explanation": f"These {total} ClinVar pathogenic/likely-pathogenic records are variants in {s}.",
                      "evidence_level": "curated", "status": "supported", "confidence": 0.9, "evidence": [dbev]})
            targets = []
            if slug == "missense" and s in GOF_GENES:
                targets.append("gain-of-function")
                if s == "PTPN11":
                    targets.append("dominant-negative")
            if slug in LOF_TRUNC.get(s, []):
                targets.append("loss-of-function")
            for t in targets:
                cl = by.get((s, t), [])
                pro = [x for x in cl if x[4] is True]
                con = [x for x in cl if x[4] is False]
                evs = [ev(x[2], x[3], True, x[5]) for x in pro] + orpha_mech.get((s, t), [])
                cevs = [ev(x[2], x[3], False, x[5]) for x in con]
                if not evs:
                    continue
                note = {("PTPN11", "dominant-negative"): " Only the NSML-causing subset (e.g. Y279C, T468M) acts this way; "
                        "most PTPN11 missense variants are activating (Noonan syndrome).",
                        ("PTPN11", "gain-of-function"): " Applies to Noonan-causing missense variants, not the NSML subset.",
                        ("PTPN11", "loss-of-function"): " Truncating/splice PTPN11 variants cause metachondromatosis, "
                        "a different disease from Noonan syndrome."}.get((s, t), "")
                add_edge({"id": edge_id(vid, "has_effect", f"mech:{t}"), "source": vid, "target": f"mech:{t}",
                          "type": "has_effect", "label": "has effect",
                          "explanation": f"{lab} in {s} are linked to {t.replace('-', ' ')}." + note,
                          "evidence_level": "experimental", "status": "contested" if cevs else "supported",
                          "confidence": round(conf_from(evs) - (0.1 if cevs else 0), 2), "evidence": evs,
                          "counter_evidence": cevs, "attrs": {"family": FAMILY}})

    # ------------------------------------------------------------ phenotypes (HPO)
    for n in hpo["nodes"]:
        add_node(n)
    for e in hpo["edges"]:
        add_edge(e)

    # ------------------------------------------------------------ therapies
    for t in CUR.THERAPIES:
        tid = f"therapy:{t['slug']}"
        node_src = [ev(*x[:4]) for x in t.get("node_sources", [])]
        first = next(iter(t["developed_for"].values()))
        node_src += [ev(*x[:4]) for x in first["evidence"][:2]] + [ev(*x[:4]) for x in t.get("general", [])]
        add_node({"id": tid, "type": "therapy", "label": t["label"], "synonyms": t["synonyms"], "summary": t["summary"],
                  "attrs": {"modality": t["modality"], "stage": t["stage"], "family": FAMILY,
                            "target_diseases": [f"disease:{g}" for g in t["developed_for"]]},
                  "sources": node_src})
        for mech, evl in t["targets"].items():
            evs = [ev(*x[:4]) for x in evl]
            add_edge({"id": edge_id(tid, "targets", f"mech:{mech}"), "source": tid, "target": f"mech:{mech}",
                      "type": "targets", "label": "targets",
                      "explanation": f"{t['label']} acts on {mech.replace('-', ' ')} (see quoted source).",
                      "evidence_level": "clinical" if t["stage"] in ("approved",) else "experimental",
                      "status": "supported", "confidence": 0.85 if t["stage"] == "approved" else 0.7, "evidence": evs,
                      "attrs": {"family": FAMILY}})
        gcounter = [ev(*x[:4]) for x in t.get("general_counter", [])]
        for g, d in t["developed_for"].items():
            evs = [ev(*x[:4]) for x in d["evidence"]]
            cevs = [ev(*x[:4]) for x in d["counter"]] + gcounter
            lvl = d["level"]
            conf = 0.95 if d.get("approved") else {"clinical": 0.75, "observational": 0.6, "experimental": 0.55}[lvl]
            if t["slug"] in ("statins-nf1-cognition", "tipifarnib"):
                conf = 0.4
            expl = {"selumetinib": "FDA-approved for symptomatic, inoperable plexiform neurofibromas in NF1 (label quoted), "
                                   "backed by the SPRINT phase 2 and KOMET phase 3 trials. Limits (no significant adult "
                                   "quality-of-life difference; toxicity-related discontinuations) are attached.",
                    "mirdametinib": "FDA-approved for symptomatic plexiform neurofibromas in NF1 (label quoted), based on the "
                                    "ReNeu phase 2b trial.",
                    "binimetinib": "Tested in a completed phase 2 trial in NF1 plexiform neurofibromas.",
                    "rapamycin-nsml": "Reversed hypertrophic cardiomyopathy in mice with NSML-type PTPN11 mutations "
                                      "(preclinical only); human heart tissue data advise caution.",
                    "statins-nf1-cognition": "Rescued learning in Nf1+/- mice, but two randomised trials in children with "
                                             "NF1 found no cognitive benefit: a documented failed repurposing.",
                    "tipifarnib": "A randomised placebo-controlled phase 2 trial in NF1 plexiform neurofibromas did not "
                                  "meet its endpoint: blocking RAS farnesylation failed."}.get(t["slug"])
            if t["slug"] == "trametinib":
                expl = ({"RAF1": "Off-label use of the cancer MEK inhibitor for RAF1-associated hypertrophic cardiomyopathy "
                                 "(case reports; MEK inhibition also rescued Raf1 L613V mice). Cross-member repurposing of "
                                 "the drug class approved for NF1. It did not reverse pulmonary vascular disease in one infant.",
                         "RIT1": "Off-label MEK inhibition led to complete remission of hypertrophic cardiomyopathy in a "
                                 "child with RIT1-related Noonan syndrome (case report).",
                         "SOS1": "Off-label MEK inhibition resolved a severe lymphatic disorder in a patient with SOS1 "
                                 "Noonan syndrome (case report).",
                         "PTPN11": "Registered phase 3 trial (Baby MERIT, not yet recruiting) enrols infants with any "
                                   "Noonan, Costello or CFC gene, but explicitly EXCLUDES NSML-causing PTPN11 variants, "
                                   "which reduce SHP2 catalytic activity.",
                         "LZTR1": "Registered phase 3 trial (Baby MERIT) explicitly admits biallelic LZTR1 (recessive "
                                  "Noonan syndrome)."}[g]
                        + " No completed randomised trial yet; the need for one is attached as counter-evidence.")
            add_edge({"id": edge_id(tid, "developed_for", f"disease:{g}"), "source": tid, "target": f"disease:{g}",
                      "type": "developed_for", "label": "approved for" if d.get("approved") else "developed for",
                      "explanation": expl, "evidence_level": lvl, "status": "contested" if cevs else "supported",
                      "confidence": conf, "evidence": evs, "counter_evidence": cevs,
                      "attrs": {"stage": "approved" if d.get("approved") else t["stage"], "family": FAMILY}})

    # ------------------------------------------------------------ studies
    ctdir = RAW / "clinicaltrials"
    for nct, cfg in CUR.STUDIES.items():
        ps = read_json(ctdir / f"{nct}.json")["protocolSection"]
        im, st, dm = ps["identificationModule"], ps["statusModule"], ps.get("designModule", {})
        sp = ps.get("sponsorCollaboratorsModule", {})
        url = f"https://clinicaltrials.gov/study/{nct}"
        base = evidence("ClinicalTrials.gov", nct, url, "trial", title=im.get("briefTitle"),
                        study_type="clinical_trial" if dm.get("studyType") == "INTERVENTIONAL" else "database_record")
        attrs = {"status": st.get("overallStatus"), "study_type": (dm.get("studyType") or "").lower() or None,
                 "phase": "/".join(dm.get("phases") or []) or None, "start": (st.get("startDateStruct") or {}).get("date"),
                 "sponsor": sp.get("leadSponsor", {}).get("name"),
                 "collaborators": [c["name"] for c in sp.get("collaborators", [])] or None,
                 "enrollment": (dm.get("enrollmentInfo") or {}).get("count"),
                 "interventions": [i.get("name") for i in ps.get("armsInterventionsModule", {}).get("interventions", [])] or None,
                 "conditions": ps.get("conditionsModule", {}).get("conditions"), "why_stopped": st.get("whyStopped"),
                 "url": url, "family": FAMILY, "atlas_role": cfg["kind"],
                 "eligibility_note": cfg.get("notes", {}).get("_all")}
        add_node({"id": f"study:{nct}", "type": "study", "label": im.get("briefTitle"), "xrefs": {"NCT": nct},
                  "summary": (ps.get("descriptionModule", {}).get("briefSummary") or "")[:300] or None,
                  "attrs": {k: v for k, v in attrs.items() if v not in (None, [], "")}, "sources": [base]})
        linked = set()
        for g, needle in cfg.get("genes", {}).items():
            e = ev(nct, needle, True, base["study_type"])
            note = cfg.get("notes", {}).get(g, "")
            add_edge({"id": edge_id(f"study:{nct}", "studies", f"disease:{g}"), "source": f"study:{nct}",
                      "target": f"disease:{g}", "type": "studies", "label": "enrols / studies",
                      "explanation": f"{nct} names {g} (or its disorder) in its record, as quoted. {note}".strip(),
                      "evidence_level": "curated", "status": "supported", "confidence": 0.9, "evidence": [e],
                      "attrs": {"gene_named_in_record": True, "family": FAMILY}})
            linked.add(g)
        for key, needle in cfg.get("syndromes", {}).items():
            for g in sorted(syndrome_genes[key] if key != "rasopathy" else syndrome_genes["rasopathy"]):
                if g in linked:
                    continue
                e = ev(nct, needle, True, base["study_type"])
                add_edge({"id": edge_id(f"study:{nct}", "studies", f"disease:{g}"), "source": f"study:{nct}",
                          "target": f"disease:{g}", "type": "studies", "label": "eligible (by syndrome)",
                          "explanation": (f"{nct} enrols by syndrome ({key}), quoted; the record does not name {g}. "
                                          f"{g} is linked because OMIM/ClinGen record it as a cause of that syndrome "
                                          f"(see the gene's causes edge)."),
                          "evidence_level": "inferred", "status": "supported", "confidence": 0.55, "evidence": [e],
                          "attrs": {"gene_named_in_record": False, "via_syndrome": key, "family": FAMILY}})
                linked.add(g)
        for tslug in cfg["tests"]:
            ivs = [i.get("name") for i in ps.get("armsInterventionsModule", {}).get("interventions", [])]
            add_edge({"id": edge_id(f"study:{nct}", "tests", f"therapy:{tslug}"), "source": f"study:{nct}",
                      "target": f"therapy:{tslug}", "type": "tests", "label": "tests",
                      "explanation": f"{nct} lists {', '.join(ivs[:3])} as intervention(s).",
                      "evidence_level": "clinical" if dm.get("studyType") == "INTERVENTIONAL" else "curated",
                      "status": "supported", "confidence": 0.9,
                      "evidence": [dict(base, quote=ivs[0], extracted_by="database", verified=False)] if ivs else [base],
                      "attrs": {"family": FAMILY}})

    # ------------------------------------------------------------ orgs & assets
    def list_genes(key):
        return CUR.RASNET_LIST_GENES[key]
    for k, (ref, needle) in CUR.RASNET_GENES.items():
        q = CUR.quote_for(ref, needle)
        for g in CUR.RASNET_LIST_GENES[k]:
            assert re.search(rf"\b{g}\b", q), (k, g)
    for o in CUR.ORGS:
        evs = [ev(r, n, title_extra=o["label"]) for r, n in o["evidence"]]
        add_node({"id": o["id"], "type": "patient_org", "label": o["label"], "summary": o["evidence"][0][1][:300],
                  "attrs": {"url": o["url"], "country": o.get("country"), "scope": o.get("scope"), "family": FAMILY},
                  "sources": evs})
        targets = {}
        for key in o.get("serves_lists", []):
            for g in list_genes(key):
                targets.setdefault(g, ("list", key))
        for key in o.get("serves_syndromes", []):
            for g in sorted(syndrome_genes[key]):
                targets.setdefault(g, ("syndrome", key))
        if o.get("schwannomatosis"):
            targets.setdefault("LZTR1", ("schwannomatosis", None))
        for g, (how, key) in sorted(targets.items()):
            sev = list(evs)
            if how == "list":
                sev.append(ev(*CUR.RASNET_GENES[key], title_extra="RASopathies Network syndrome gene list"))
                lvl, conf = o["level"], o["confidence"]
                expl = f"{o['label']} serves people with RASopathies, and its own syndrome page lists {g} as a gene for {key.upper() if key != 'noonan' else 'Noonan syndrome'}."
            elif g in o.get("named_genes", {}):
                sev.append(ev(*o["named_genes"][g], title_extra=o["label"]))
                lvl, conf = "observational", 0.85
                expl = f"{o['label']} serves people with Noonan syndrome and names {g} on its own site."
            elif how == "schwannomatosis":
                lvl, conf = "inferred", 0.5
                expl = (f"{o['label']} states it covers schwannomatosis; LZTR1-related schwannomatosis (OMIM 615670) is "
                        f"one subtype of the LZTR1 umbrella, so this is an inferred link.")
            else:
                if key in CUR.RASNET_GENES and g in CUR.RASNET_LIST_GENES.get(key, []):
                    sev.append(ev(*CUR.RASNET_GENES[key], title_extra="RASopathies Network syndrome gene list"))
                lvl, conf = "inferred", 0.6
                expl = (f"{o['label']} serves people with {key.replace('_', '-')} syndrome(s); {g} is one of the genes "
                        f"that cause it (OMIM/ClinGen, and the RASopathies Network gene list where quoted). The org's "
                        f"own page does not name the gene.")
            add_edge({"id": edge_id(o["id"], "serves", f"disease:{g}"), "source": o["id"], "target": f"disease:{g}",
                      "type": "serves", "label": "serves", "explanation": expl, "evidence_level": lvl,
                      "status": "supported", "confidence": conf, "evidence": sev, "attrs": {"family": FAMILY}})
    for a in CUR.ASSETS:
        evs = [ev(r, n, title_extra=a["label"]) for r, n in a["evidence"]]
        add_node({"id": a["id"], "type": "asset", "label": a["label"], "xrefs": a.get("xrefs"), "summary": a["evidence"][0][1][:300],
                  "attrs": {"kind": a["kind"], "url": a["url"], "status": a.get("status"), "family": FAMILY}, "sources": evs})
        cov = {g: None for g in a.get("covers", [])}
        for k in a.get("covers_lists", []):
            for g in list_genes(k):
                cov.setdefault(g, k)
        for k in a.get("covers_syndromes", []):
            for g in sorted(syndrome_genes[k]):
                cov.setdefault(g, k)
        for g, k in sorted(cov.items()):
            sev = list(evs) + ([ev(*CUR.RASNET_GENES[k], title_extra="RASopathies Network syndrome gene list")]
                               if k in CUR.RASNET_GENES and g in CUR.RASNET_LIST_GENES.get(k, []) else [])
            add_edge({"id": edge_id(a["id"], "covers", f"disease:{g}"), "source": a["id"], "target": f"disease:{g}",
                      "type": "covers", "label": "covers",
                      "explanation": (f"{a['label']} covers people with {g}-related disorders" +
                                      (f" (via the {k} syndrome mapping; the page does not name the gene)." if k else ", per the quoted page.")),
                      "evidence_level": "observational" if not k else "inferred", "status": "supported",
                      "confidence": 0.85 if not k else 0.6, "evidence": sev, "attrs": {"family": FAMILY}})
        for org in a.get("maintained_by", []):
            mev = evs + [ev(r, n) for r, n in a.get("maintainer_evidence", [])]
            add_edge({"id": edge_id(org, "maintains", a["id"]), "source": org, "target": a["id"], "type": "maintains",
                      "label": "runs", "explanation": f"{org.split(':')[1].replace('-', ' ').title()} runs {a['label']}, per the quoted source(s).",
                      "evidence_level": "observational", "status": "supported", "confidence": 0.85, "evidence": mev,
                      "attrs": {"family": FAMILY}})

    # ------------------------------------------------------------ research groups (PubMed senior authors)
    ras_rx = re.compile(r"(Noonan|RASopath|Costello|cardio-?facio-?cutaneous|\bCFC\b|LEOPARD|lentigines|loose anagen|"
                        r"Mazzanti|metachondromatosis|schwannomatosis|neurofibromatosis|gingival fibromatosis|"
                        r"cardiomyopathy|JMML|juvenile myelomonocytic)", re.I)
    inst_rx = re.compile(r"(Universit|Hospital|Institut|Istituto|Instituto|College|Center|Centre|School|Klinik|Clinic|"
                         r"Ospedale|Hôpital|Hopital|Foundation|Fondazione|IRCCS|Inserm|Children|Sanit|Medical|Research|"
                         r"National Laborator)", re.I)
    groups_out = {}
    for s in GENES:
        es = read_json(RAW / "authors" / f"{s}.esearch.json")
        grx = re.compile(rf"\b{s}\b")
        tally = defaultdict(list)
        for pmid in es["ids"]:
            p = RAW / "pubmed" / f"{pmid}.json"
            if not p.exists():
                continue
            r = read_json(p)
            if any("Review" in t or "Erratum" in t for t in r["pub_types"]) or not r.get("last_author"):
                continue
            sents = [r["title"]] + [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", r["abstract"]) if x.strip()]
            if not grx.search(r["title"]) and sum(1 for x in sents[1:] if grx.search(x)) < 2:
                continue
            quote = next((x for x in sents if grx.search(x) and ras_rx.search(x)), None)
            la = r["last_author"]
            aff = la.get("affiliation") or ""
            if not quote or not la.get("last") or not aff:
                continue
            parts = [" ".join(x.split()).strip(" .;") for x in re.split(r"[,;]", aff.replace("[email-redacted]", "")) if x.strip(" .;\xa0")]
            sub = re.compile(r"^(Department|Dept|Division|Section|Unit|Laboratory of|Clinic for|School of|Faculty of)\b", re.I)
            inst = ""
            for tier in (r"Universit", r"Istituto|Instituto|Institut|Hospital|Hôpital|Ospedale|IRCCS|Inserm|National Laborator|Fondazione|Foundation|Medical Center|Medical Centre",
                         r"."):
                inst = next((x for x in parts if re.search(tier, x, re.I) and not sub.match(x)), "")
                if inst:
                    break
            inst = inst or (parts[0] if parts else "")
            m_u = re.search(r"([A-Z][\w'\-]*(?: [A-Z][\w'\-]*)* University(?! of)|University of [A-Z][\w'\-]*(?: [A-Z][\w'\-]*)*)", inst)
            if m_u:
                inst = m_u.group(1)   # canonical university name, so one person is not split by sub-unit wording
            # within one gene's paper set, a senior author is keyed by surname + first initial (institution
            # strings vary between papers); the most frequent institution names the node
            key = (la["last"].lower(), (la.get("fore") or "")[:1].lower())
            tally[key].append({"pmid": pmid, "title": r["title"], "year": r["year"], "quote": quote, "inst": inst,
                               "fore": la.get("fore") or "", "last": la["last"], "orcid": la.get("orcid")})
        ranked = sorted(tally.items(), key=lambda kv: (-len(kv[1]), -max(x["year"] or 0 for x in kv[1])))
        chosen = [(k, v) for k, v in ranked if len(v) >= 2][:5]
        groups_out[s] = [(f"{v[0]['fore']} {v[0]['last']}", Counter(x["inst"] for x in v).most_common(1)[0][0], len(v))
                         for k, v in chosen]
        for (last, fi), papers in chosen:
            p0 = papers[0]
            inst_name = Counter(x["inst"] for x in papers).most_common(1)[0][0]
            inst_slug = slugify(inst_name, 50)
            p0 = dict(p0, inst=inst_name)
            rid = f"researcher:{slugify(p0['fore'] + ' ' + p0['last'], 50)}--{inst_slug}"
            orcid = next((x["orcid"] for x in papers if x.get("orcid")), None)
            if orcid:
                orcid = re.sub(r"^https?://orcid.org/", "", orcid)
            add_node({"id": rid, "type": "researcher", "label": f"{p0['fore']} {p0['last']}".strip(),
                      "attrs": {"affiliation": p0["inst"], "orcid": orcid,
                                "url": f"https://orcid.org/{orcid}" if orcid else "https://pubmed.ncbi.nlm.nih.gov/?term="
                                       + "+OR+".join(sorted(x["pmid"] for x in papers)[:20]),
                                "identity_basis": "PubMed last-author name + institution" + ("; ORCID from PubMed" if orcid else ""),
                                "family": FAMILY}})
            evs = [evidence("PubMed", f"PMID:{x['pmid']}", f"https://pubmed.ncbi.nlm.nih.gov/{x['pmid']}/", "publication",
                            extracted_by="database", title=x["title"], year=x["year"], quote=x["quote"], verified=False)
                   for x in papers[:4]]
            add_edge({"id": edge_id(rid, "works_on", f"disease:{s}"), "source": rid, "target": f"disease:{s}",
                      "type": "works_on", "label": "works on",
                      "explanation": f"Senior (last) author on {len(papers)} papers since 2018 that focus on {s} in a germline RASopathy context.",
                      "evidence_level": "observational", "status": "supported", "confidence": 0.75 if len(papers) >= 3 else 0.65,
                      "evidence": evs, "attrs": {"n_papers": len(papers), "family": FAMILY}})
    write_json(RAW / "research_groups.json", groups_out)

    # ------------------------------------------------------------ cross-member shares_mechanism
    for a, b, lab, evl, basis in CUR.SHARES:
        evs = [ev(*x) for x in evl if x[2]]
        cevs = [ev(*x) for x in evl if not x[2]]
        add_edge({"id": edge_id(f"disease:{a}", "shares_mechanism", f"disease:{b}"), "source": f"disease:{a}",
                  "target": f"disease:{b}", "type": "shares_mechanism", "label": lab,
                  "explanation": ({"RAF1": "Different genes, one pathway, one drug class: NF1 plexiform neurofibromas are driven "
                                           "by elevated RAS-MAPK signalling and respond to MEK inhibitors (approved); RAF1 "
                                           "hypertrophic cardiomyopathy is driven by enhanced MEK-ERK activity and has "
                                           "responded to the MEK inhibitor trametinib in case reports and in Raf1 mice. Pulmonary "
                                           "vascular disease did not respond in one infant (counter-evidence).",
                                   "RIT1": "NF1 tumours and RIT1 Noonan cardiomyopathy share RAS/MAPK overactivation; the "
                                           "MEK-inhibitor class approved for NF1 resolved RIT1-associated HCM in a case report.",
                                   "CBL": "Both genes encode RAS 'off-switches' (neurofibromin, a RAS GAP; CBL, an E3 ubiquitin "
                                          "ligase); losing them leaves RAS signalling on, and the CBL discovery paper explicitly "
                                          "likens the disorder to NF1.",
                                   "LZTR1": "Both genes encode RAS 'off-switches' (neurofibromin, a RAS GAP; LZTR1, which tags "
                                            "RAS for ubiquitination); loss of either increases RAS signalling and both predispose "
                                            "to nerve-sheath tumours (neurofibromas / schwannomas)."}[b]),
                  "evidence_level": "experimental", "status": "contested" if cevs else "supported", "confidence": 0.6,
                  "evidence": evs, "counter_evidence": cevs,
                  "attrs": {"basis": basis, "shared_processes": ["mech:mapk-cascade"] if "MEK" in lab else ["mech:ras-protein-signal-transduction"],
                            "shared_effects": ["mech:gain-of-function"] if "MEK" in lab else ["mech:loss-of-function"],
                            "family": FAMILY}})

    # ------------------------------------------------------------ clusters
    def eids(pred):
        return sorted(e["id"] for e in edges.values() if pred(e))
    fam_ev = [ev(r, n, True, "review") for r, n in CUR.FAMILY]
    mek_members = ["disease:NF1", "disease:RAF1", "disease:RIT1", "disease:SOS1", "disease:PTPN11", "disease:LZTR1",
                   "therapy:selumetinib", "therapy:mirdametinib", "therapy:trametinib", "therapy:binimetinib", "mech:mapk-cascade"]
    clusters = [
        {"id": "cluster:rasopathy-family", "label": "RASopathies: one signalling pathway turned up", "basis": "pathway",
         "members": [f"disease:{g}" for g in GENES] + [f"gene:{g}" for g in GENES] + ["mech:ras-protein-signal-transduction", "mech:mapk-cascade"],
         "rationale": ("Twelve genes, many diagnoses (Noonan syndrome, NSML, Costello, cardiofaciocutaneous syndrome, "
                       "neurofibromatosis type 1, Mazzanti syndrome, CBL syndrome), one pathway: each gene encodes a "
                       "component or regulator of RAS/MAPK signalling and the vast majority of disease variants increase "
                       "signalling (PMID:19467855, PMID:23875798, PMID:29924299, PMID:38929714); ClinGen curated the gene set "
                       "(PMID:30311384). Shared pathway means shared drug targets: MEK inhibitors approved for NF1 are being "
                       "repurposed across the family."),
         "edge_ids": eids(lambda e: e["type"] in ("participates_in", "similar_phenotype", "shares_mechanism", "causes")
                          and (e.get("attrs") or {}).get("family", FAMILY) == FAMILY and e["id"].split("|")[0] in
                          {f"gene:{g}" for g in GENES} | {f"disease:{g}" for g in GENES}),
         "evidence": fam_ev},
        {"id": "cluster:rasopathy-mek-inhibitor-responsive", "label": "MEK-inhibitor-responsive RAS/MAPK overactivation",
         "basis": "mechanism", "members": mek_members,
         "rationale": ("Diseases where blocking MEK has been approved (NF1 plexiform neurofibromas: selumetinib, mirdametinib), "
                       "used off-label with reported benefit (RAF1 and RIT1 hypertrophic cardiomyopathy, SOS1 lymphatic disease) "
                       "or is being trialled (MEKinRAS phase 2; Baby MERIT phase 3, which admits Noonan/Costello/CFC genes "
                       "including recessive LZTR1 but excludes NSML-type PTPN11). CFC MEK1 variants are MEK-inhibitor-sensitive "
                       "in vitro (PMID:17981815) but no clinical report was found. Limits: case-level evidence, one withdrawn "
                       "2012 trial, and no completed randomised trial outside NF1."),
         "edge_ids": eids(lambda e: e["type"] in ("developed_for", "targets", "tests") and any(
             e["id"].startswith(f"therapy:{x}") or e["target"] == f"therapy:{x}" for x in ("selumetinib", "mirdametinib", "trametinib", "binimetinib")))
                     + eids(lambda e: e["type"] == "shares_mechanism" and "MEK" in (e.get("label") or ""))},
        {"id": "cluster:rasopathy-loss-of-ras-regulation", "label": "Loss of RAS regulation (NF1, LZTR1, CBL)", "basis": "mechanism",
         "members": ["disease:NF1", "disease:LZTR1", "disease:CBL", "gene:NF1", "gene:LZTR1", "gene:CBL", "mech:loss-of-function",
                     "mech:negative-regulation-of-ras-signaling"],
         "rationale": ("Most RASopathy genes are activated accelerators; these three are lost brakes. Neurofibromin is a RAS "
                       "GTPase-activating protein (PMID:35066574), LZTR1 tags RAS for ubiquitination and removal from the "
                       "membrane (PMID:30442762, PMID:30442766) and CBL ubiquitylates receptors (PMID:20619386). Loss-of-function "
                       "variants (truncating, splice, deletions) dominate their ClinVar spectra, and tumour predisposition "
                       "via a second hit is shared (NF1 neurofibromas, LZTR1 schwannomas, CBL JMML)."),
         "edge_ids": eids(lambda e: (e["type"] in ("driven_by", "has_effect") and e["target"] == "mech:loss-of-function"
                                     and any(f":{g}" in e["source"] for g in LOF_REG_GENES))
                          or (e["type"] == "shares_mechanism" and "regulation" in (e.get("label") or "")))},
        {"id": "cluster:rasopathy-same-gene-different-mechanism", "label": "Same gene, different mechanism (PTPN11, LZTR1, RAF1)",
         "basis": "mechanism",
         "members": ["disease:PTPN11", "disease:LZTR1", "disease:RAF1", "mech:gain-of-function", "mech:dominant-negative",
                     "mech:loss-of-function", "therapy:rapamycin-nsml", "therapy:trametinib", "mech:tor-signaling"],
         "rationale": ("PTPN11 Noonan variants activate SHP2 (PMID:11704759) whereas NSML variants are catalytically defective "
                       "and dominant negative (PMID:16377799) and truncating variants cause metachondromatosis (PMID:21533187). "
                       "Therapy follows mechanism: NSML-type PTPN11 is excluded from the infant MEK-inhibitor trial "
                       "(NCT07817186) and responded to mTOR inhibition in mice (PMID:21339643), with human-tissue caution "
                       "(PMID:31722741). LZTR1 dominant variants hit substrate recognition while recessive and schwannomatosis "
                       "alleles are loss of function (PMID:30481304, PMID:39140257). RAF1 HCM-hotspot variants are "
                       "kinase-activating while others are kinase impaired (PMID:17603483)."),
         "edge_ids": eids(lambda e: e["source"] in ("disease:PTPN11", "disease:LZTR1", "disease:RAF1", "vg:PTPN11:missense",
                                                    "vg:PTPN11:truncating", "therapy:rapamycin-nsml")
                          and e["type"] in ("driven_by", "has_effect", "developed_for", "targets"))
                     + eids(lambda e: e["id"] in ("therapy:trametinib|developed_for|disease:PTPN11",
                                                  "study:NCT07817186|studies|disease:PTPN11"))},
    ]
    for c in clusters:
        c.pop("evidence", None)

    # ------------------------------------------------------------ gaps
    srch = read_json(RAW / "pubmed_searches.json")
    ct_files = sorted(p.stem for p in (RAW / "ctgov").glob("*.json"))
    pm = lambda pat: [f"PubMed esearch: {x['term']} ({x['count']} hits, {x['date']})" for x in srch if re.search(pat, x["term"], re.I)]  # noqa: E731
    ct = lambda pat: [f"ClinicalTrials.gov API v2: {f}" for f in ct_files if re.search(pat, f, re.I)]  # noqa: E731
    gaps = [
        {"id": "gap:rasopathy-mek-noonan-efficacy", "about": "disease:RAF1",
         "question": "Does MEK inhibition improve outcomes in Noonan-spectrum hypertrophic cardiomyopathy or lymphatic disease, beyond case reports?",
         "what_is_missing": ["No completed randomised or controlled trial outside NF1: MEKinRAS (NCT06555237, phase 2) is recruiting and Baby MERIT (NCT07817186, phase 3) is not yet recruiting.",
                             "The first MEK-inhibitor trial in Noonan HCM (binimetinib/MEK162, NCT01556568) was withdrawn 'due to scientific and business considerations' with 0 enrolled.",
                             "Clinical evidence is case reports/series and one retrospective 61-patient comparison (PMID:40131150) whose abstract does not break results down by gene.",
                             "Pulmonary vascular disease did not respond in a RAF1 infant (PMID:35052347)."],
         "searched": pm(r"trametinib|MEK|Andelfinger") + ct(r"trametinib|rasopath|noonan"),
         "how_to_find_out": "Follow MEKinRAS and Baby MERIT results; ask the RAS-CM natural-history study (NCT07344480) for external-control data stratified by gene (RAF1, RIT1, PTPN11, LZTR1)."},
        {"id": "gap:rasopathy-nsml-therapy", "about": "disease:PTPN11",
         "question": "What treatment fits NSML-type (catalytically impaired) PTPN11 hypertrophic cardiomyopathy?",
         "what_is_missing": ["NSML-causing PTPN11 variants are explicitly excluded from the MEK-inhibitor infant trial (NCT07817186).",
                             "mTOR inhibition (rapamycin) is preclinical only (PMID:21339643, PMID:22058153); human NSML heart tissue showed attenuated, not enhanced, mTORC1 activity (PMID:31722741).",
                             "Whether NSML mutants behave as loss or gain of function in cardiomyocytes is itself contested (PMID:24935154)."],
         "searched": pm(r"LEOPARD|rapamycin") + ct(r"leopard|lentigines"),
         "how_to_find_out": "Patient-derived cardiomyocyte studies comparing MEK and mTOR inhibition in NSML versus Noonan PTPN11 genotypes; a registry arm for NSML-HCM outcomes."},
        {"id": "gap:rasopathy-cfc-costello-mek", "about": "disease:MAP2K1",
         "question": "Is MEK inhibition used or tested in cardiofaciocutaneous (BRAF, MAP2K1, KRAS) or Costello (HRAS) syndrome?",
         "what_is_missing": ["CFC MEK1 variants are sensitive to a tool MEK inhibitor in vitro (PMID:17981815), but our searches found no clinical report or trial specific to CFC or Costello syndrome.",
                             "Baby MERIT (NCT07817186) admits Noonan, Costello or CFC genes, so the first prospective data may come from it."],
         "searched": pm(r"Costello|cardiofaciocutaneous|cardio-facio") + ct(r"costello|cardio"),
         "how_to_find_out": "Ask CFC International and Costello family networks about compassionate-use cases; check conference abstracts (RASopathies symposia), which the atlas does not index."},
        {"id": "gap:rasopathy-costello-patient-org", "about": "disease:HRAS",
         "question": "Which patient organisation serves Costello syndrome (HRAS)?",
         "what_is_missing": ["costellokids.org (Costello Syndrome Family Network) returned no readable text, directly or via Bright Data Web Unlocker; costellokids.org.uk did not respond.",
                             "No Costello-specific organisation could be verified with a quote, so only the RASopathies Network (which lists HRAS) is linked."],
         "searched": ["Direct fetch https://costellokids.org/ and https://www.costellokids.org.uk/ (2026-10-03)",
                      "Bright Data Web Unlocker https://costellokids.org/ (1 request)", "RASopathies Network syndromes page"],
         "how_to_find_out": "Re-fetch with a JavaScript-rendering browser, or ask the RASopathies Network for the Costello family-network contact."},
        {"id": "gap:rasopathy-cognition", "about": "disease:NF1",
         "question": "Is there any pathway-targeted treatment for learning and attention problems in NF1 or other RASopathies?",
         "what_is_missing": ["Statins rescued Nf1+/- mice (PMID:16271875) but failed in two randomised trials in children (PMID:18632543, PMID:27956565).",
                             "A lovastatin/lamotrigine RASopathy trial (NCT03504501) terminated for recruitment difficulties.",
                             "No MEK-inhibitor cognition trial was found in our ClinicalTrials.gov searches."],
         "searched": pm(r"statin") + ct(r"lovastatin|simvastatin"),
         "how_to_find_out": "Check the NF Clinical Trials Consortium and CTF pipeline for neurocognitive endpoints in ongoing MEK-inhibitor trials."},
        {"id": "gap:rasopathy-variant-level-mechanism", "about": "mech:gain-of-function",
         "question": "Which individual variants are activating, catalytically impaired or loss of function?",
         "what_is_missing": ["Variant groups are ClinVar consequence classes; PTPN11 missense variants include both activating (Noonan) and catalytically impaired (NSML) alleles, and RAF1 includes kinase-activating and kinase-impaired alleles (PMID:17603483).",
                             "LZTR1 has dominant (Kelch-surface) and recessive/loss-of-function classes (PMID:30481304).",
                             "Multi-gene CNVs dominate SHOC2, CBL, HRAS and LZTR1 (22q11.2) ClinVar records and get no mechanism edge."],
         "searched": ["ClinVar esearch/esummary per gene (data/raw/families/rasopathy/clinvar/)"] + pm(r"LEOPARD|LZTR1|RAF1"),
         "how_to_find_out": "Link ClinVar VCVs to published functional readouts (phosphatase activity, ERK activation, RAS ubiquitination) in a variant-level table; ClinGen RASopathy VCEP specifications (PMID:40496714) are the natural home."},
        {"id": "gap:rasopathy-shoc2-cbl-hras-trials", "about": "disease:SHOC2",
         "question": "Is any interventional study open to SHOC2-, CBL- or HRAS-related disorders specifically?",
         "what_is_missing": ["ClinicalTrials.gov term searches returned 1 SHOC2 record and no SHOC2-, CBL- or Costello-specific interventional trial; CBL appears mainly in leukaemia (JMML) trials, which are out of scope here.",
                             "These genes are covered only by multi-gene observational cohorts (NCT04888936; NCT04395495)."],
         "searched": ct(r"shoc2|costello|leopard|loose-anagen|metachondromatosis"),
         "how_to_find_out": "Ask the NCI RASopathy cohort (NCT04888936) and RASopathies Network which patients are trial-eligible in the MEK-inhibitor HCM trials."},
    ]

    frag = {"nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
            "edges": sorted(edges.values(), key=lambda e: (e["type"], e["id"])), "clusters": clusters, "gaps": gaps}
    write_json(OUT_FRAGMENT, frag)
    print("nodes", Counter(n["type"] for n in frag["nodes"]))
    print("edges", Counter(e["type"] for e in frag["edges"]))
    print(f"clusters {len(clusters)}, gaps {len(gaps)}; research groups:")
    for s, g in groups_out.items():
        print(f"  {s}: {g}")
    print(f"wrote {OUT_FRAGMENT}")


if __name__ == "__main__":
    main()
