"""Assemble data/curated/family_lysosomal.json from the cached sources and curated claims.

Run (after the fetch steps):  python3 pipeline/families/lysosomal/build_fragment.py
Inputs: data/raw/families/lysosomal/{genes,diseases,clinvar_summary,hpo_fragment}.json, quickgo/, fda/, pubmed/,
        ctgov/, web/ (+ pipeline/families/lysosomal/curated_orgs.json), fragments/research.json,
        pipeline/families/lysosomal/curation.py; data/graph.json (to reuse existing node ids, never duplicate them).
Every quote is produced by lyso_common.quote_for() from a stored source; verify.py re-checks them all.
"""
from __future__ import annotations

import re
from collections import defaultdict

import curation as CUR
import lyso_common as L
from lyso_common import FRAGMENT, GENES, GRAPH, RAW, TODAY, edge_id, evidence, read_json, write_json

FAM = "lysosomal"
genes = read_json(RAW / "genes.json")
dis = read_json(RAW / "diseases.json")
cv = read_json(RAW / "clinvar_summary.json")
hpo = read_json(RAW / "hpo_fragment.json")
# existing ids = nodes defined by the OTHER curated fragments (graph.json may already contain this fragment's own
# nodes from an earlier build, which must not count as "existing")
_graph_nodes = [n for f in sorted((L.ROOT / "data" / "curated").glob("*.json")) if f.name not in (FRAGMENT.name, "overrides.json")
                for n in (read_json(f).get("nodes", []) if isinstance(read_json(f), dict) else [])]
graph_ids = {n["id"] for n in _graph_nodes}
graph_label = {n["id"]: n["label"] for n in _graph_nodes}


def label_of(i):
    return (nodes.get(i) or {}).get("label") or graph_label.get(i, i)
nodes: dict[str, dict] = {}
edges: dict[str, dict] = {}
dropped: list[str] = []

DISEASE_META = {
    "GBA1": ("GBA1-related disorders (Gaucher disease)", "Gaucher disease",
             "Deficiency of the enzyme glucocerebrosidase makes a fatty substance (glucosylceramide) build up, mainly in "
             "macrophages: enlarged liver and spleen, low blood counts and bone disease; types 2 and 3 also affect the brain."),
    "GAA": ("GAA-related disorders (Pompe disease)", "Pompe disease",
            "Deficiency of acid alpha-glucosidase makes glycogen build up inside lysosomes of muscle cells, causing muscle "
            "weakness and breathing problems; the infantile form also affects the heart."),
    "GLA": ("GLA-related disorders (Fabry disease)", "Fabry disease",
            "X-linked deficiency of alpha-galactosidase A makes globotriaosylceramide (Gb3) build up in blood vessels, kidney, "
            "heart and nerves: pain crises, kidney failure, heart disease and stroke. Women can be affected too."),
    "HEXA": ("HEXA-related disorders (Tay-Sachs disease)", "Tay-Sachs disease",
             "Deficiency of hexosaminidase A makes GM2 ganglioside build up in nerve cells: infants lose skills and develop "
             "seizures and blindness; later-onset forms progress more slowly."),
    "NPC1": ("NPC1-related disorders (Niemann-Pick disease type C)", "Niemann-Pick disease type C",
             "Loss of the NPC1 cholesterol transporter traps cholesterol and lipids in lysosomes: liver and spleen "
             "enlargement and a progressive neurological disease with ataxia, eye-movement problems and dementia."),
    "SMPD1": ("SMPD1-related disorders (acid sphingomyelinase deficiency, Niemann-Pick A/B)", "acid sphingomyelinase deficiency",
              "Deficiency of acid sphingomyelinase makes sphingomyelin build up: enlarged liver and spleen and lung disease; "
              "the infantile neurovisceral form (type A) also causes rapid neurodegeneration."),
    "IDUA": ("IDUA-related disorders (mucopolysaccharidosis type I: Hurler, Hurler-Scheie, Scheie)", "mucopolysaccharidosis type I",
             "Deficiency of alpha-L-iduronidase makes dermatan and heparan sulfate build up in many organs: coarse facial "
             "features, skeletal disease, heart and airway problems; the severe Hurler form also affects the brain."),
    "IDS": ("IDS-related disorders (mucopolysaccharidosis type II, Hunter syndrome)", "mucopolysaccharidosis type II",
            "X-linked deficiency of iduronate-2-sulfatase makes heparan and dermatan sulfate build up; the neuronopathic "
            "form also causes progressive cognitive decline."),
    "CLN3": ("CLN3-related disorders (CLN3 disease, juvenile Batten disease)", "CLN3 disease",
             "Changes in CLN3, a lysosomal membrane protein of uncertain function, cause childhood vision loss followed by "
             "seizures, cognitive and motor decline (juvenile neuronal ceroid lipofuscinosis); some variants cause retinal "
             "disease only."),
    "TPP1": ("TPP1-related disorders (CLN2 disease)", "CLN2 disease",
             "Deficiency of the lysosomal enzyme tripeptidyl peptidase 1 causes CLN2 disease (late-infantile Batten disease): "
             "language delay, seizures, loss of walking and vision; milder variants cause a recessive ataxia (SCAR7)."),
    "ARSA": ("ARSA-related disorders (metachromatic leukodystrophy)", "metachromatic leukodystrophy",
             "Deficiency of arylsulfatase A makes sulfatides build up and destroys myelin in the brain and nerves, causing "
             "loss of motor and cognitive skills."),
    "GALC": ("GALC-related disorders (Krabbe disease)", "Krabbe disease",
             "Deficiency of galactocerebrosidase leads to toxic psychosine build-up that kills myelin-forming cells; the "
             "infantile form is rapidly fatal."),
}
EXTRA_SYN = {
    "GBA1": ["Gaucher disease", "GD1", "GD2", "GD3", "glucocerebrosidase deficiency"],
    "GAA": ["Pompe disease", "glycogen storage disease type II", "GSD II", "acid maltase deficiency", "IOPD", "LOPD"],
    "GLA": ["Fabry disease", "Anderson-Fabry disease", "alpha-galactosidase A deficiency"],
    "HEXA": ["Tay-Sachs disease", "GM2 gangliosidosis type B", "hexosaminidase A deficiency", "late-onset Tay-Sachs"],
    "NPC1": ["Niemann-Pick disease type C", "NPC", "NP-C"],
    "SMPD1": ["acid sphingomyelinase deficiency", "ASMD", "Niemann-Pick disease type A", "Niemann-Pick disease type B"],
    "IDUA": ["MPS I", "Hurler syndrome", "Hurler-Scheie syndrome", "Scheie syndrome"],
    "IDS": ["MPS II", "Hunter syndrome", "iduronate-2-sulfatase deficiency"],
    "CLN3": ["juvenile Batten disease", "juvenile neuronal ceroid lipofuscinosis", "JNCL", "CLN3 disease"],
    "TPP1": ["CLN2 disease", "late-infantile neuronal ceroid lipofuscinosis", "TPP1 deficiency", "SCAR7"],
    "ARSA": ["metachromatic leukodystrophy", "MLD", "arylsulfatase A deficiency"],
    "GALC": ["Krabbe disease", "globoid cell leukodystrophy", "galactocerebrosidase deficiency"],
}
ENZYME_GENES = ["GBA1", "GAA", "GLA", "HEXA", "SMPD1", "IDUA", "IDS", "TPP1", "ARSA", "GALC"]


def add_node(n):
    if n["id"] in nodes:
        return nodes[n["id"]]
    nodes[n["id"]] = n
    return n


def add_edge(e):
    if not e.get("evidence") and e.get("evidence_level") != "hypothesis":
        dropped.append(f"edge without evidence: {e['id']}")
        return None
    if e["id"] in edges:
        old = edges[e["id"]]
        keys = {(x["ref"], x.get("quote")) for x in old["evidence"]}
        old["evidence"] += [x for x in e["evidence"] if (x["ref"], x.get("quote")) not in keys]
        if e.get("counter_evidence"):
            old.setdefault("counter_evidence", [])
            ck = {(x["ref"], x.get("quote")) for x in old["counter_evidence"]}
            old["counter_evidence"] += [x for x in e["counter_evidence"] if (x["ref"], x.get("quote")) not in ck]
        return old
    if not e.get("counter_evidence"):
        e.pop("counter_evidence", None)
    edges[e["id"]] = e
    return e


def ev_ref(ref: str, needle: str, study_type: str, supports: bool = True) -> dict:
    """Evidence item whose quote is lifted verbatim from the stored source."""
    q = L.quote_for(ref, needle)
    if ref.startswith("PMID:"):
        r = read_json(L.PM_DIR / f"{ref[5:]}.json")
        return evidence("PubMed", ref, r["url"], "publication", extracted_by="agent-curation", title=r["title"],
                        year=r.get("year"), quote=q, study_type=study_type, supports=None if supports else False,
                        verified=False)
    if ref.startswith("FDA:"):
        slug = ref[4:]
        res = read_json(L.FDA_DIR / f"{slug}.json")["results"][0]
        of = res.get("openfda", {})
        brand = (of.get("brand_name") or [slug.upper()])[0]
        generic = (of.get("generic_name") or [""])[0]
        url = f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={res['set_id']}"
        return evidence("Website", url, url, "website", extracted_by="agent-curation",
                        title=f"FDA prescribing information: {brand} ({generic.lower()}), label version {res.get('effective_time')} "
                              f"(retrieved via openFDA drug label API)", quote=q, study_type="database_record",
                        supports=None if supports else False, verified=False)
    if ref.startswith("NCT"):
        rec = read_json(L.CT_DIR / "studies" / f"{ref}.json")["protocolSection"]
        return evidence("ClinicalTrials.gov", ref, f"https://clinicaltrials.gov/study/{ref}", "trial",
                        extracted_by="agent-curation", title=rec["identificationModule"].get("briefTitle"), quote=q,
                        study_type="clinical_trial", supports=None if supports else False, verified=False)
    raise ValueError(ref)


def conf_from(evs, base=0.5):
    pubs = [e for e in evs if e.get("supports", True)]
    return 0.8 if len(pubs) >= 2 else 0.6 if pubs else base


# ============================================================================ genes + diseases + causes
therapy_approved = {g: False for g in GENES}
for t in CUR.THERAPIES:
    if t["stage"] == "approved":
        for g in t["diseases"]:
            if t.get("disease_stage", {}).get(g, "approved") == "approved":
                therapy_approved[g] = True

for sym in GENES:
    g = genes[sym]
    syn = list(dict.fromkeys(g["protein_synonyms_curated"] + g.get("alias_symbol", []) + g.get("prev_symbol", [])
                             + [g.get("protein_name")] + g.get("protein_alt_names", [])))
    xr = {"HGNC": g["hgnc_id"], "NCBIGene": g["entrez_id"], "Ensembl": g["ensembl_gene_id"], "OMIM": g["omim_id"],
          "UniProt": g["uniprot_acc"]}
    if g.get("mane_enst"):
        xr["MANE_Select"] = g["mane_enst"]
    attrs = {"family": FAM, "protein": g.get("protein_name"), "function": g.get("uniprot_function"),
             "protein_length_aa": g.get("protein_length_aa"), "cds_length_bp": g.get("cds_length_bp"),
             "subcellular_location": g.get("subcellular_location"), "is_enzyme": sym in ENZYME_GENES}
    if g.get("cds_length_bp"):
        attrs["aav_cds_fits_4_7kb"] = g["cds_length_bp"] <= 4700
    srcs = [evidence("HGNC", g["hgnc_id"], g["hgnc_url"], "database", title=f"HGNC symbol report: {sym} ({g['name']})",
                     study_type="database_record"),
            evidence("UniProt", g["uniprot_acc"], g["uniprot_url"], "database",
                     title=f"UniProtKB {g['uniprot_entry']} ({g.get('protein_name')})", quote=g.get("uniprot_function"),
                     study_type="database_record", verified=False)]
    add_node({"id": f"gene:{sym}", "type": "gene", "label": sym, "synonyms": [s for s in syn if s and s != sym],
              "xrefs": xr, "summary": g.get("uniprot_function"), "attrs": attrs, "sources": srcs})

    d = dis[sym]
    label, short, summary = DISEASE_META[sym]
    subtypes, omim, orpha, mondo, syns, inh = [], [], [], [], [], []
    for e in d["entities"]:
        causal_omim = [m for m in e["monarch_edges"] if m["primary_knowledge_source"] == "infores:omim"
                       and m["predicate"] == "biolink:causes"]
        orpha_causal = [c for c, a in d["orphanet_associations"].items() if a.get("causal") and c in e["orpha_from_edges"]]
        clingen = [m for m in e["monarch_edges"] if m["primary_knowledge_source"] == "infores:clingen"
                   and m["predicate"] == "biolink:causes"]
        if not causal_omim and not orpha_causal and not clingen:
            continue  # susceptibility (contributes_to) links such as GBA1 -> Parkinson disease are excluded
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
    for c, a in d["orphanet_associations"].items():
        if a.get("causal") and c not in orpha:
            subtypes.append({"name": a["name"], "ORPHA": [c]})
            orpha.append(c)
    excluded = [e["name"] for e in d["entities"] if all(m["predicate"] != "biolink:causes" for m in e["monarch_edges"]
                                                         if m["primary_knowledge_source"] == "infores:omim")
                and any(m["predicate"] == "biolink:contributes_to" for m in e["monarch_edges"])]
    eb = d["established_by"]
    dattrs = {"family": FAM, "gene": sym, "subtypes": subtypes, "inheritance": "; ".join(sorted(set(inh))) or None,
              "approved_treatment": therapy_approved[sym],
              "gene_disease_validity": {"gene2phenotype": eb["g2p_confidence"], "clingen": eb["clingen_classification"],
                                        "omim_causal_edge": eb["omim_causal"],
                                        "orphanet_disease_causing": eb["orphanet_disease_causing"]}}
    if excluded:
        dattrs["excluded_susceptibility_links"] = excluded
    add_node({"id": f"disease:{sym}", "type": "disease", "label": label,
              "synonyms": list(dict.fromkeys(EXTRA_SYN[sym] + syns))[:40],
              "xrefs": {"MONDO": sorted(set(mondo)), "OMIM": sorted(set(omim)), "ORPHA": sorted(set(orpha)),
                        "HGNC": g["hgnc_id"]},
              "summary": summary, "attrs": dattrs,
              "sources": [evidence("Monarch", g["hgnc_id"], f"https://monarchinitiative.org/{g['hgnc_id']}", "database",
                                   title=f"Monarch Initiative gene-to-disease associations for {sym}",
                                   study_type="database_record")]})
    evs = []
    for e in d["entities"]:
        for m in e["monarch_edges"]:
            oo = m.get("original_object") or ""
            if m["primary_knowledge_source"] == "infores:omim" and m["predicate"] == "biolink:causes" and oo.startswith("OMIM:"):
                evs.append(evidence("OMIM", oo, f"https://omim.org/entry/{oo[5:]}", "database",
                                    title=f"OMIM {oo[5:]}: {e['name']} - gene-phenotype relationship with {sym} (via Monarch)",
                                    study_type="database_record"))
    for c, a in d["orphanet_associations"].items():
        if a.get("causal"):
            evs.append(evidence("Orphanet", f"ORPHA:{c}", a["url"], "database",
                                title=f"Orphanet ORPHA:{c} {a['name']}: {sym} - {a['association_type']}",
                                study_type="database_record"))
    for r in d["opentargets"]["evidence"]:
        if r["datasourceId"] == "clingen":
            u = (r.get("urls") or [{}])[0].get("url") or "https://search.clinicalgenome.org/"
            evs.append(evidence("ClinGen", f"ClinGen:{r['disease']['id']}", u, "database",
                                title=f"ClinGen gene-disease validity: {sym} - {r.get('diseaseFromSource')} = "
                                      f"{r.get('confidence')}", study_type="database_record"))
            break
    st_claim = next(c for c in CUR.CLAIMS if c[0] == sym and c[1] == "storage")
    evs.append(ev_ref(st_claim[2], st_claim[3], st_claim[5]))
    add_edge({"id": edge_id(f"gene:{sym}", "causes", f"disease:{sym}"), "source": f"gene:{sym}",
              "target": f"disease:{sym}", "type": "causes", "label": "causes",
              "explanation": (f"Variants in {sym} cause {label}. Curated databases record {len(subtypes)} clinical "
                              f"entities under this umbrella; gene-disease validity is "
                              f"{(eb['g2p_confidence'] or ['n/a'])[0]} in Gene2Phenotype and "
                              f"{(eb['clingen_classification'] or ['n/a'])[0]} in ClinGen."),
              "evidence_level": "clinical", "status": "supported", "confidence": 0.95, "evidence": evs})

# ============================================================================ mechanisms
fam_ev = ev_ref(*CUR.FAMILY_STORAGE_REF, "review")
add_node({"id": "mech:lysosomal-storage", "type": "mechanism", "label": "Lysosomal substrate accumulation (storage)",
          "summary": "Material that the lysosome should break down or export piles up inside it (the 'storage'), "
                     "damaging the cell. The stored material differs by disease: lipids, sugars chains, glycogen or "
                     "cholesterol.",
          "synonyms": ["lysosomal storage", "substrate accumulation"],
          "attrs": {"kind": "process", "family": FAM}, "sources": [fam_ev]})
add_node({"id": "mech:lysosomal-enzyme-deficiency", "type": "mechanism", "label": "Lysosomal enzyme deficiency",
          "summary": "One of the lysosome's digestive enzymes is missing or barely active, so its substrate cannot be "
                     "broken down. A specific kind of loss of function; most lysosomal storage disorders are recessive, "
                     "so both copies are affected.",
          "synonyms": ["enzyme deficiency", "lysosomal hydrolase deficiency"],
          "attrs": {"kind": "effect", "family": FAM}, "sources": [ev_ref(*CUR.FAMILY_PROTEINS_REF, "review")]})
GO_MECH = {"sphingolipid-catabolism": ("GO:0030149", "Sphingolipid breakdown (sphingolipid catabolic process)"),
           "glycosaminoglycan-catabolism": ("GO:0006027", "Glycosaminoglycan breakdown"),
           "glycogen-catabolism": ("GO:0005980", "Glycogen breakdown"),
           "intracellular-cholesterol-transport": ("GO:0032367", "Intracellular cholesterol transport"),
           "lysosome-organization": ("GO:0007040", "Lysosome organization"),
           "lysosomal-protein-catabolism": ("GO:1905146", "Lysosomal protein breakdown")}
go_terms = {r["id"]: r for r in read_json(RAW / "quickgo" / "terms.json")["results"]}
for slug, (go, lab) in GO_MECH.items():
    t = go_terms[go]
    add_node({"id": f"mech:{slug}", "type": "mechanism", "label": lab, "xrefs": {"GO": go},
              "summary": (t.get("definition") or {}).get("text"),
              "attrs": {"kind": "process", "go_id": go, "go_name": t.get("name"), "family": FAM},
              "sources": [evidence("GO", go, f"https://www.ebi.ac.uk/QuickGO/term/{go}", "database", title=t.get("name"),
                                   quote=(t.get("definition") or {}).get("text"), study_type="database_record",
                                   verified=False)]})
EXPERIMENTAL = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP"}
CURATED_OTHER = {"IBA", "TAS", "IC", "NAS"}
for sym in GENES:
    acc = genes[sym]["uniprot_acc"]
    for slug, (go, lab) in GO_MECH.items():
        p = RAW / "quickgo" / f"{acc}__{go.replace(':', '_')}.json"
        if not p.exists():
            continue
        anns = [a for a in read_json(p).get("results", []) if (a.get("qualifier") or "").startswith(("involved_in", "acts_upstream"))]
        if not anns:
            continue
        codes = sorted({a["goEvidence"] for a in anns})
        exp = [a for a in anns if a["goEvidence"] in EXPERIMENTAL and a["reference"].startswith("PMID:")]
        conf = 0.9 if exp else 0.8 if set(codes) & CURATED_OTHER else 0.7 if {"ISS", "ISO", "ISA"} & set(codes) else 0.6
        hits = sorted({a["goId"] for a in anns})
        evs = [evidence("GO", go, f"https://www.ebi.ac.uk/QuickGO/annotations?geneProductId={acc}&goId={go}&goUsage=descendants",
                        "database", title=f"QuickGO: {len(anns)} annotation(s) of UniProtKB:{acc} ({sym}) to {', '.join(hits)}; "
                                          f"evidence {', '.join(codes)}", study_type="database_record")]
        for a in exp[:2]:
            evs.append(evidence("GO", a["reference"], f"https://pubmed.ncbi.nlm.nih.gov/{a['reference'][5:]}/", "database",
                                title=f"GO annotation {a['goId']} ({a['goEvidence']}, assigned by {a['assignedBy']})",
                                study_type="database_record"))
        add_edge({"id": edge_id(f"gene:{sym}", "participates_in", f"mech:{slug}"), "source": f"gene:{sym}",
                  "target": f"mech:{slug}", "type": "participates_in", "label": "takes part in",
                  "explanation": f"Gene Ontology annotates {sym} to {lab.lower()} ({go} or a more specific child term), "
                                 f"evidence codes {', '.join(codes)}.",
                  "evidence_level": "curated" if conf >= 0.7 else "inferred", "status": "supported", "confidence": conf,
                  "evidence": evs, "attrs": {"go_evidence_codes": codes, "go_terms_hit": hits}})

# ============================================================================ driven_by
MECH_ID = {"storage": "mech:lysosomal-storage", "enzyme-deficiency": "mech:lysosomal-enzyme-deficiency",
           "destabilization": "mech:protein-destabilization", "loss-of-function": "mech:loss-of-function"}
MECH_WORD = {"storage": "lysosomal substrate accumulation", "enzyme-deficiency": "lysosomal enzyme deficiency",
             "destabilization": "protein destabilization / misfolding", "loss-of-function": "loss of function"}
by = defaultdict(list)
for c in CUR.CLAIMS:
    by[(c[0], c[1])].append(c)
counter_by = defaultdict(list)
for c in CUR.COUNTER:
    counter_by[(c[0], c[1])].append(c)
for (sym, m), cl in by.items():
    evs = [ev_ref(c[2], c[3], c[5]) for c in cl]
    cevs = [ev_ref(c[2], c[3], c[4], supports=False) for c in counter_by.get((sym, m), [])]
    expl = f"Published work links {sym}-related disorders to {MECH_WORD[m]}. " + " ".join(c[6] for c in cl[:2])
    if cevs:
        expl += " Limiting findings are attached as counter-evidence: " + " ".join(c[5] for c in counter_by[(sym, m)])
    lvl = "experimental" if m == "destabilization" else "curated"
    conf = conf_from(evs)
    if m in ("storage", "enzyme-deficiency"):
        conf = 0.85 if len(evs) >= 2 else 0.8   # textbook mechanism, restated by independent reviews + curated databases
    if cevs:
        conf = max(0.5, conf - 0.1)
    add_edge({"id": edge_id(f"disease:{sym}", "driven_by", MECH_ID[m]), "source": f"disease:{sym}",
              "target": MECH_ID[m], "type": "driven_by", "label": "driven by", "explanation": expl.strip(),
              "evidence_level": lvl, "status": "contested" if cevs else "supported", "confidence": round(conf, 2),
              "evidence": evs, "counter_evidence": cevs,
              "attrs": {"n_supporting_publications": len(evs), "n_counter": len(cevs)}})

# ============================================================================ variant groups (ClinVar)
VG = {"truncating": ("Truncating variants (nonsense, frameshift, start-lost)", ["nonsense", "frameshift", "start_lost"], "truncating"),
      "missense": ("Missense variants (single amino-acid changes)", ["missense"], "missense"),
      "splice": ("Splice-site variants", ["splice", "intronic_or_splice_region"], "splice"),
      "whole-gene-deletion": ("Single-gene deletions / duplications", ["cnv_single_gene", "intragenic_deletion_or_duplication"], "cnv"),
      "contiguous-gene-deletion": ("Larger deletions spanning this gene and its neighbours", ["cnv_multigene"], "cnv")}
misfold_genes = {c[0] for c in CUR.CLAIMS if c[1] == "destabilization"}
for sym in GENES:
    c = cv[sym]
    for slug, (lab, cats, cons) in VG.items():
        counts = {k: c["by_consequence"].get(k, 0) for k in cats if c["by_consequence"].get(k)}
        total = sum(counts.values())
        if not total:
            continue
        ex = [f"{e['title']} [{e['accession']}; {e['classification']}; {e['review_status']}]"
              for k in cats for e in c["examples"].get(k, [])[:2]]
        vid = f"vg:{sym}:{slug}"
        cv_ev = evidence("ClinVar", c["query"], c["clinvar_search_url"], "database",
                         title=f"ClinVar esearch/esummary for {sym} (P/LP; {c['esearch_count']} records)", study_type="database_record")
        add_node({"id": vid, "type": "variant_group", "label": f"{sym}: {lab}",
                  "attrs": {"gene": sym, "consequence": cons, "example_variants": ex[:4], "clinvar_counts": counts,
                            "clinvar_total_in_group": total, "clinvar_gene_total_PLP": c["n_classified_PLP"], "family": FAM},
                  "summary": f"{total} of {c['n_classified_PLP']} pathogenic or likely-pathogenic ClinVar records for {sym} "
                             f"fall in this group." + (" These copy-number changes cover more than one gene, so no mechanism "
                                                       "edge is drawn from them." if slug == "contiguous-gene-deletion" else ""),
                  "sources": [cv_ev]})
        add_edge({"id": edge_id(vid, "variant_in", f"gene:{sym}"), "source": vid, "target": f"gene:{sym}",
                  "type": "variant_in", "label": "variants in",
                  "explanation": f"These {total} ClinVar pathogenic/likely-pathogenic records are variants in {sym}.",
                  "evidence_level": "curated", "status": "supported", "confidence": 0.9, "evidence": [cv_ev]})
        if slug in ("truncating", "splice", "whole-gene-deletion"):
            add_edge({"id": edge_id(vid, "has_effect", "mech:loss-of-function"), "source": vid, "target": "mech:loss-of-function",
                      "type": "has_effect", "label": "has effect",
                      "explanation": f"{lab} in {sym} are expected to remove the protein's function. {sym}-related disorders "
                                     f"are recessive (or X-linked), so disease needs both copies (or the single X copy) to "
                                     f"be affected. Inferred from the variant consequence class, not from a gene-specific paper.",
                      "evidence_level": "inferred", "status": "unverified", "confidence": 0.45,
                      "evidence": [dict(cv_ev, title=f"{total} {cons} P/LP records in {sym}; loss of function inferred "
                                                      f"from consequence class")]})
        if slug == "missense" and sym in misfold_genes:
            cl = by[(sym, "destabilization")]
            evs = [ev_ref(x[2], x[3], x[5]) for x in cl]
            add_edge({"id": edge_id(vid, "has_effect", "mech:protein-destabilization"), "source": vid,
                      "target": "mech:protein-destabilization", "type": "has_effect", "label": "has effect",
                      "explanation": f"Many {sym} missense variants make a protein that misfolds and is held back or degraded "
                                     f"in the endoplasmic reticulum. {cl[0][6]}",
                      "evidence_level": "experimental", "status": "supported", "confidence": round(conf_from(evs), 2),
                      "evidence": evs})

# ============================================================================ phenotypes
for n in hpo["nodes"]:
    if n["id"] not in graph_ids:
        add_node(n)
for e in hpo["edges"]:
    add_edge(e)

# ============================================================================ therapies
for t in CUR.THERAPIES:
    tid = f"therapy:{t['slug']}"
    ev_pairs = [(r, ev_ref(r, n, s)) for r, n, s in t["evidence"]]
    evs = [ev for _, ev in ev_pairs]
    cevs = [ev_ref(r, n, s, supports=False) for r, n, s in t.get("counter", [])]
    notes = [ev_ref(r, n, s) for r, n, s in t.get("node_notes", [])]
    attrs = {"modality": t["modality"], "stage": t["stage"], "approach": t["approach"], "family": FAM,
             "target_genes": t["diseases"]}
    if t.get("reaches_cns") is not None:
        attrs["reaches_cns"] = t["reaches_cns"]
    if t.get("disease_stage"):
        attrs["stage_by_disease"] = {g: t["disease_stage"].get(g, t["stage"]) for g in t["diseases"]}
    if notes:
        attrs["limitations"] = [x["quote"] for x in notes]
    if tid in graph_ids:
        dropped.append(f"therapy id already exists, reused without redefining: {tid}")
    else:
        add_node({"id": tid, "type": "therapy", "label": t["label"], "synonyms": t["synonyms"], "summary": t["summary"],
                  "attrs": attrs, "sources": evs[:3] + notes + cevs[:1]})
    for m in t["targets"]:
        add_edge({"id": edge_id(tid, "targets", m), "source": tid, "target": m, "type": "targets", "label": "targets",
                  "explanation": f"{t['label']} acts on {label_of(m).lower()}: {t['approach']}."
                                 + (" Its mechanism is debated; see counter-evidence." if cevs else ""),
                  "evidence_level": "clinical" if t["stage"] in ("approved", "clinical") else "experimental",
                  "status": "contested" if cevs else "supported", "confidence": round(conf_from(evs), 2),
                  "evidence": evs, "counter_evidence": cevs})
    for g in t["diseases"]:
        rel_refs = t.get("per_disease", {}).get(g)
        rel = [ev for r, ev in ev_pairs if r in rel_refs] if rel_refs else evs
        rel = [e for e in rel if not (e["ref"].startswith("http") and False)]
        stage = t.get("disease_stage", {}).get(g, t["stage"])
        scope = ""
        if t.get("reaches_cns") is False:
            scope = " It does not reach the brain, so it does not treat neurological disease."
        add_edge({"id": edge_id(tid, "developed_for", f"disease:{g}"), "source": tid, "target": f"disease:{g}",
                  "type": "developed_for", "label": "approved for" if stage == "approved" else "developed for",
                  "explanation": f"{t['label']} is {'approved' if stage == 'approved' else 'in clinical testing'} for "
                                 f"{DISEASE_META[g][1]} (stage: {stage}).{scope}",
                  "evidence_level": "clinical", "status": "supported",
                  "confidence": 0.95 if stage == "approved" else round(conf_from(rel), 2),
                  "evidence": rel, "attrs": {"stage": stage, "reaches_cns": t.get("reaches_cns")}})

# ============================================================================ shares_mechanism
proc_of, eff_of = defaultdict(set), defaultdict(set)
for e in edges.values():
    if e["type"] == "participates_in" and e["confidence"] >= 0.7:
        proc_of[e["source"].split(":")[1]].add(e["target"])
    if e["type"] == "driven_by":
        eff_of[e["source"].split(":")[1]].add(e["target"])
fam_ev2 = ev_ref(*CUR.FAMILY_REF, "review")
for i, a in enumerate(GENES):
    for b in GENES[i + 1:]:
        sp = proc_of[a] & proc_of[b]
        se = eff_of[a] & eff_of[b]
        if not sp or "mech:lysosomal-storage" not in se:
            continue
        evs = [fam_ev2, fam_ev] + [evidence("GO", nodes[p]["xrefs"]["GO"], f"https://www.ebi.ac.uk/QuickGO/term/{nodes[p]['xrefs']['GO']}",
                                             "database", title=f"Both {a} and {b} are annotated to {nodes[p]['label']}",
                                             study_type="database_record") for p in sorted(sp)]
        pl = ", ".join(nodes[p]["label"].lower() for p in sorted(sp))
        el = ", ".join(label_of(m).split(" (")[0].lower() for m in sorted(se))
        add_edge({"id": edge_id(f"disease:{a}", "shares_mechanism", f"disease:{b}"), "source": f"disease:{a}",
                  "target": f"disease:{b}", "type": "shares_mechanism", "label": "shares mechanism",
                  "explanation": f"{a} and {b} encode lysosomal proteins working in the same process ({pl}), and both "
                                 f"disorders are driven by {el}.",
                  "evidence_level": "curated", "status": "supported", "confidence": 0.7, "evidence": evs,
                  "attrs": {"shared_processes": sorted(sp), "shared_effects": sorted(se), "basis": "lysosomal pathway"}})
# chaperone-responsive misfolding across different pathways (inside the family)
misfold = sorted(misfold_genes, key=GENES.index)
for i, a in enumerate(misfold):
    for b in misfold[i + 1:]:
        eid = edge_id(f"disease:{a}", "shares_mechanism", f"disease:{b}")
        ea = edges[edge_id(f"disease:{a}", "driven_by", "mech:protein-destabilization")]
        eb_ = edges[edge_id(f"disease:{b}", "driven_by", "mech:protein-destabilization")]
        evs = ea["evidence"][:1] + eb_["evidence"][:1]
        if eid in edges:
            edges[eid]["attrs"]["shared_effects"] = sorted(set(edges[eid]["attrs"]["shared_effects"]) | {"mech:protein-destabilization"})
            edges[eid]["evidence"] += [x for x in evs if x not in edges[eid]["evidence"]]
            edges[eid]["explanation"] += " Both also have misfolded missense variants that small molecules can partly rescue."
            continue
        add_edge({"id": eid, "source": f"disease:{a}", "target": f"disease:{b}", "type": "shares_mechanism",
                  "label": "shared misfolding mechanism",
                  "explanation": f"Different pathways, same cell-biological problem: a subset of {a} and {b} missense variants "
                                 f"make a protein that misfolds and is held back or degraded in the endoplasmic reticulum, and "
                                 f"small molecules that stabilize the protein have been tested for both. The atlas inferred this "
                                 f"by combining the linked evidence; no single study compared them.",
                  "evidence_level": "inferred", "status": "supported", "confidence": 0.45, "evidence": evs,
                  "counter_evidence": ea.get("counter_evidence", [])[:1] + eb_.get("counter_evidence", [])[:1],
                  "attrs": {"shared_effects": ["mech:protein-destabilization"], "shared_processes": [],
                            "basis": "protein misfolding / chaperone approach"}})
# cross-family: lysosomal misfolding <-> SLC6A1 (SNAREopathy layer's bridge gene) - only if that node exists
slc_ev = [ev_ref(r, n, s) for r, n, s, _ in [(a, b, d, c) for a, b, c, d in CUR.SLC6A1_BRIDGE]]
slc_cev = [ev_ref(r, n, s, supports=False) for r, n, s, _ in [(a, b, d, c) for a, b, c, d in CUR.SLC6A1_BRIDGE_COUNTER]]
if "disease:SLC6A1" in graph_ids:
    for sym, why in (("NPC1", "NPC1 and GAT-1 are both multi-pass membrane proteins whose common missense variants are "
                               "retained in the endoplasmic reticulum and degraded; proteostasis drugs (arimoclomol for NPC1, "
                               "4-phenylbutyrate for GAT-1) are being used to push more of the protein through."),
                     ("GLA", "a subset of GLA (alpha-galactosidase A) and SLC6A1 (GAT-1) missense variants misfold and are "
                             "held in the endoplasmic reticulum; a pharmacological chaperone (migalastat) is approved for "
                             "amenable GLA variants and a chemical chaperone (4-phenylbutyrate) restored GAT-1 in models.")):
        ea = edges[edge_id(f"disease:{sym}", "driven_by", "mech:protein-destabilization")]
        add_edge({"id": edge_id(f"disease:{sym}", "shares_mechanism", "disease:SLC6A1"), "source": f"disease:{sym}",
                  "target": "disease:SLC6A1", "type": "shares_mechanism", "label": "shared misfolding mechanism (cross-family)",
                  "explanation": f"Different disease families, same cell-biological problem: {why} The atlas inferred this by "
                                 f"combining the linked evidence; no study compared them directly. Limits are attached as "
                                 f"counter-evidence (about a third of SLC6A1 loss-of-function missense variants reach the "
                                 f"surface and are outside a chaperone's reach).",
                  "evidence_level": "inferred", "status": "supported", "confidence": 0.4,
                  "evidence": ea["evidence"][:2] + slc_ev,
                  "counter_evidence": ea.get("counter_evidence", [])[:1] + slc_cev,
                  "attrs": {"shared_effects": ["mech:protein-destabilization"], "shared_processes": [],
                            "basis": "protein misfolding / chaperone approach", "cross_family": ["lysosomal", "snareopathy"]}})

# ============================================================================ studies (ClinicalTrials.gov)
DIS_RX = {"GBA1": r"gaucher", "GAA": r"pompe|glycogen storage disease,? type ii|acid maltase",
          "GLA": r"fabry", "HEXA": r"tay[- ]?sachs|gm2", "NPC1": r"niemann.?pick (disease)?,? ?(type )?c\b|\bnp-?c\b|\bnpc1?\b",
          "SMPD1": r"sphingomyelinase|niemann.?pick (disease)?,? ?(type )?(a|b|a/b)\b",
          "IDUA": r"mucopolysaccharidosis,? (type )?(i|1)\b|\bmps ?(i|1)\b|hurler|scheie",
          "IDS": r"mucopolysaccharidosis,? (type )?(ii|2)\b|\bmps ?(ii|2)\b|hunter",
          "CLN3": r"cln3|juvenile neuronal ceroid|juvenile batten", "TPP1": r"cln2|late.infantile neuronal ceroid|tripeptidyl",
          "ARSA": r"metachromatic", "GALC": r"krabbe|globoid"}
PHASE_RANK = {"PHASE3": 4, "PHASE2": 3, "PHASE1": 2, "EARLY_PHASE1": 1, "PHASE4": 3}
therapy_rx = {f"therapy:{t['slug']}": [re.compile(r"(?<![a-z])" + re.escape(m)) for m in t["match"]] for t in CUR.THERAPIES}
studies_by_gene = defaultdict(dict)
for f in sorted((L.CT_DIR / "search").glob("*.json")):
    gene = f.name.split("__")[0]
    for s in read_json(f)["studies"]:
        studies_by_gene[gene][s["protocolSection"]["identificationModule"]["nctId"]] = s
selected_studies = defaultdict(list)
for gene, studs in studies_by_gene.items():
    rx = re.compile(DIS_RX[gene], re.I)
    cands = []
    for nct, s in studs.items():
        ps = s["protocolSection"]
        conds = ps.get("conditionsModule", {}).get("conditions", []) or []
        cmatch = [c for c in conds if rx.search(c)]
        if not cmatch:
            continue
        dm = ps.get("designModule", {})
        stype = (dm.get("studyType") or "").lower()
        ivs = [i.get("name") or "" for i in ps.get("armsInterventionsModule", {}).get("interventions", []) or []]
        tmatch = sorted({tid for tid, rxs in therapy_rx.items() for iv in ivs if any(r.search(iv.lower()) for r in rxs)})
        title = ps["identificationModule"].get("briefTitle", "")
        status = ps.get("statusModule", {}).get("overallStatus")
        if status in ("WITHDRAWN",):
            continue
        start = (ps.get("statusModule", {}).get("startDateStruct") or {}).get("date") or ""
        prank = max([PHASE_RANK.get(p, 0) for p in dm.get("phases") or []] or [0])
        reg = bool(re.search(r"registry|natural history|outcome survey", title, re.I))
        cands.append({"nct": nct, "s": s, "cond": cmatch[0], "type": stype, "ivs": ivs, "tm": tmatch, "prank": prank,
                      "start": start, "reg": reg, "title": title, "status": status})
    inter = sorted([c for c in cands if c["type"] == "interventional"],
                   key=lambda c: (-bool(c["tm"]), -c["prank"], c["status"] not in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"),
                                  "".join(reversed(c["start"])) and -int((c["start"] or "0")[:4])))[:4]
    obs = sorted([c for c in cands if c["type"] == "observational" and c["reg"]],
                 key=lambda c: (c["status"] not in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"),
                                -int((c["start"] or "0")[:4])))[:2]
    selected_studies[gene] = inter + obs
for gene, sel in selected_studies.items():
    for c in sel:
        nct, ps = c["nct"], c["s"]["protocolSection"]
        im, stm, dm = ps["identificationModule"], ps.get("statusModule", {}), ps.get("designModule", {})
        sp = ps.get("sponsorCollaboratorsModule", {})
        url = f"https://clinicaltrials.gov/study/{nct}"
        base = {"source": "ClinicalTrials.gov", "ref": nct, "url": url, "title": im.get("briefTitle"), "kind": "trial",
                "study_type": "clinical_trial" if c["type"] == "interventional" else "database_record",
                "extracted_by": "database", "retrieved": TODAY}
        sid = f"study:{nct}"
        if sid not in graph_ids:
            attrs = {"status": stm.get("overallStatus"), "study_type": c["type"] or None,
                     "phase": "/".join(dm.get("phases") or []) or None, "start": c["start"] or None,
                     "sponsor": sp.get("leadSponsor", {}).get("name"), "enrollment": (dm.get("enrollmentInfo") or {}).get("count"),
                     "interventions": c["ivs"] or None, "conditions": ps.get("conditionsModule", {}).get("conditions"),
                     "url": url, "family": FAM}
            add_node({"id": sid, "type": "study", "label": im.get("briefTitle"), "xrefs": {"NCT": nct},
                      "summary": (ps.get("descriptionModule", {}).get("briefSummary") or "")[:300] or None,
                      "attrs": {k: v for k, v in attrs.items() if v not in (None, [], "")}, "sources": [dict(base)]})
        add_edge({"id": edge_id(sid, "studies", f"disease:{gene}"), "source": sid, "target": f"disease:{gene}",
                  "type": "studies", "label": "enrols / studies",
                  "explanation": f"{nct} lists '{c['cond']}' among its conditions, so it enrols or studies people with "
                                 f"{DISEASE_META[gene][1]}.",
                  "evidence_level": "curated", "status": "supported", "confidence": 0.9,
                  "evidence": [dict(base, quote=c["cond"], verified=False)]})
        for tid in c["tm"]:
            iv = next(iv for iv in c["ivs"] if any(r.search(iv.lower()) for r in therapy_rx[tid]))
            add_edge({"id": edge_id(sid, "tests", tid), "source": sid, "target": tid, "type": "tests", "label": "tests",
                      "explanation": f"{nct} lists '{iv}' as an intervention.",
                      "evidence_level": "clinical" if c["type"] == "interventional" else "curated", "status": "supported",
                      "confidence": 0.9, "evidence": [dict(base, quote=iv, verified=False)]})
        if c["type"] == "observational" and c["reg"]:
            kind = "registry" if re.search(r"registry|outcome survey", c["title"], re.I) else "natural_history_study"
            aid = f"asset:{L.slugify(nct.lower() + '-' + c['title'], 60)}"
            add_node({"id": aid, "type": "asset", "label": c["title"], "xrefs": {"NCT": nct},
                      "summary": (ps.get("descriptionModule", {}).get("briefSummary") or "")[:300] or None,
                      "attrs": {"kind": kind, "url": url, "status": stm.get("overallStatus"), "family": FAM,
                                "sponsor": sp.get("leadSponsor", {}).get("name")},
                      "sources": [dict(base, quote=c["title"], verified=False)]})
            add_edge({"id": edge_id(aid, "covers", f"disease:{gene}"), "source": aid, "target": f"disease:{gene}",
                      "type": "covers", "label": "covers",
                      "explanation": f"This {kind.replace('_', ' ')} ({nct}) collects data on people with {DISEASE_META[gene][1]}.",
                      "evidence_level": "curated", "status": "supported", "confidence": 0.85,
                      "evidence": [dict(base, quote=c["cond"], verified=False)]})

# ============================================================================ community fragments (orgs, research)
orgs_path = L.HERE / "curated_orgs.json"
if orgs_path.exists():
    cur = read_json(orgs_path)
    manifest = read_json(L.WEB_DIR / "_manifest.json") if (L.WEB_DIR / "_manifest.json").exists() else {}

    def web_ev(e, title):
        m = manifest.get(e["src"], {})
        txt = L.web_text(e["src"]) or ""
        if m.get("status") != 200 or L.norm(e["quote"]) not in L.norm(txt):
            dropped.append(f"web quote not verified: {e['src']}: {e['quote'][:60]}")
            return None
        u = m.get("final_url") or m["url"]
        return evidence("Website", u, u, "website", extracted_by="agent-curation", title=title, quote=e["quote"],
                        verified=False, retrieved=m.get("retrieved", TODAY))
    SKIP_ORGS = {"org:university-of-rochester-batten-center"}   # a clinical research centre, not a patient organisation
    UMBRELLA = {("org:bdsra-foundation", "CLN3"), ("org:batten-disease-family-association", "CLN3"),
                ("org:mps-society-uk", "GLA")}   # their pages name the umbrella condition, not CLN3 / Fabry specifically
    for o in cur.get("orgs", []):
        if o["id"] in SKIP_ORGS:
            dropped.append(f"org skipped (not a patient organisation): {o['id']}")
            continue
        evs = [x for x in (web_ev(e, o["label"]) for e in o["evidence"]) if x]
        if not evs:
            dropped.append(f"org without verified evidence: {o['id']}")
            continue
        if o["id"] not in graph_ids:
            add_node({"id": o["id"], "type": "patient_org", "label": o["label"], "summary": o.get("summary"),
                      "attrs": {"url": o["url"], "country": o.get("country"), "scope": o.get("scope"), "family": FAM},
                      "sources": evs})
        for g in o["serves"]:
            sev = [x for x in (web_ev(e, o["label"]) for e in o.get("serves_evidence", {}).get(g, [])) if x] or evs
            add_edge({"id": edge_id(o["id"], "serves", f"disease:{g}"), "source": o["id"], "target": f"disease:{g}",
                      "type": "serves", "label": "serves",
                      "explanation": (f"{o['label']} states on its own website that it serves people with {DISEASE_META[g][1]}."
                                      if (o["id"], g) not in UMBRELLA else
                                      f"{o['label']} serves an umbrella community (its page names the broader condition, "
                                      f"e.g. 'Batten disease'), which includes {DISEASE_META[g][1]}; the page does not name it specifically."),
                      "evidence_level": "observational" if (o["id"], g) not in UMBRELLA else "inferred",
                      "status": "supported", "confidence": 0.9 if (o["id"], g) not in UMBRELLA else 0.6, "evidence": sev})
    for a in cur.get("assets", []):
        evs = [x for x in (web_ev(e, a["label"]) for e in a["evidence"]) if x]
        if not evs:
            dropped.append(f"asset without verified evidence: {a['id']}")
            continue
        if a["id"] not in graph_ids:
            add_node({"id": a["id"], "type": "asset", "label": a["label"], "xrefs": a.get("xrefs") or None,
                      "summary": evs[0]["quote"][:300],
                      "attrs": {k: v for k, v in {"kind": a["kind"], "url": a.get("url"), "access": a.get("access"),
                                                  "status": a.get("status"), "family": FAM}.items() if v},
                      "sources": evs})
        for g in a.get("covers", []):
            cev = [x for x in (web_ev(e, a["label"]) for e in a.get("covers_evidence", {}).get(g, [])) if x] or evs
            add_edge({"id": edge_id(a["id"], "covers", f"disease:{g}"), "source": a["id"], "target": f"disease:{g}",
                      "type": "covers", "label": "covers",
                      "explanation": f"{a['label']} includes people with {DISEASE_META[g][1]}, according to the cited page.",
                      "evidence_level": "observational", "status": "supported", "confidence": 0.85, "evidence": cev})
        for org in a.get("maintained_by", []):
            if org in nodes or org in graph_ids:
                add_edge({"id": edge_id(org, "maintains", a["id"]), "source": org, "target": a["id"], "type": "maintains",
                          "label": "runs / partners on",
                          "explanation": f"{org} runs or partners on {a['label']}, according to the cited page.",
                          "evidence_level": "observational", "status": "supported", "confidence": 0.8, "evidence": evs})
    for n in nodes.values():
        if n["type"] in ("patient_org", "asset"):
            n["attrs"] = {k: v for k, v in n["attrs"].items() if v is not None}
            if n.get("xrefs") is None:
                n.pop("xrefs", None)
research = RAW / "fragments" / "research.json"
if research.exists():
    rf = read_json(research)
    for n in rf["nodes"]:
        if n["id"] not in graph_ids:
            add_node(n)
    for e in rf["edges"]:
        add_edge(e)

# ============================================================================ clusters
def eids(pred):
    return sorted(e["id"] for e in edges.values() if pred(e))


approved_by_g = defaultdict(list)
for t in CUR.THERAPIES:
    for g in t["diseases"]:
        approved_by_g[g].append(t)
misfold_dis = [f"disease:{g}" for g in misfold]
clusters = [
    {"id": "cluster:lysosomal-family", "label": "Lysosomal storage disorders: one organelle, many enzymes", "basis": "pathway",
     "members": [f"disease:{g}" for g in GENES] + [f"gene:{g}" for g in GENES] +
                ["mech:lysosomal-storage", "mech:lysosomal-enzyme-deficiency"] + [f"mech:{s}" for s in GO_MECH],
     "rationale": "All twelve genes encode lysosomal proteins: ten digestive enzymes and two membrane proteins (NPC1, "
                  "CLN3). Whatever the gene, the end result is the same: undigested material piles up in the lysosome "
                  "(PMID:30275469). The diagnoses look very different (an enlarged spleen in Gaucher disease, kidney and "
                  "heart disease in Fabry disease, muscle weakness in Pompe disease, childhood dementia in CLN2 disease) but "
                  "the treatment logic is shared: replace the enzyme, reduce the substrate, or help a misfolded enzyme fold. "
                  "Within the family, sub-pathways (sphingolipid, glycosaminoglycan, glycogen, cholesterol) group the "
                  "diseases further.",
     "edge_ids": eids(lambda e: e["type"] in ("driven_by", "participates_in") and e["target"] in
                      ("mech:lysosomal-storage", "mech:lysosomal-enzyme-deficiency", *[f"mech:{s}" for s in GO_MECH])) +
                 eids(lambda e: e["type"] == "shares_mechanism" and (e.get("attrs") or {}).get("basis") == "lysosomal pathway")},
    {"id": "cluster:lysosomal-chaperone-responsive-misfolding",
     "label": "Chaperone-responsive misfolded proteins (lysosomal and beyond)", "basis": "mechanism",
     "members": misfold_dis + ["mech:protein-destabilization", "therapy:migalastat", "therapy:ambroxol",
                               "therapy:pyrimethamine", "therapy:arimoclomol", "disease:SLC6A1", "disease:STXBP1",
                               "therapy:4-phenylbutyrate"],
     "rationale": "In these disorders many missense variants still make a protein that could work, but it misfolds and is "
                  "held back or destroyed in the endoplasmic reticulum. A small molecule that stabilizes the protein can let "
                  "part of it through: migalastat is approved for amenable GLA variants, ambroxol (GBA1) and pyrimethamine "
                  "(HEXA) have reached patients, arimoclomol is approved for NPC though its label says its mechanism is "
                  "unknown, and a chaperone stabilized mutant GAA in mice. The same logic, with a different drug "
                  "(4-phenylbutyrate), is being tested in two SNAREopathy-layer disorders, SLC6A1 and STXBP1. The shared "
                  "limit: only variants that fold 'nearly right' respond (the migalastat amenability assay), so the variant, "
                  "not the gene, decides who can benefit.",
     "edge_ids": eids(lambda e: e["target"] == "mech:protein-destabilization" and e["type"] in ("driven_by", "has_effect", "targets")
                      and (e["source"] in misfold_dis or e["source"].startswith(("therapy:", "vg:")))) +
                 eids(lambda e: e["type"] == "shares_mechanism" and "mech:protein-destabilization" in (e.get("attrs") or {}).get("shared_effects", []))},
    {"id": "cluster:lysosomal-bbb-barrier",
     "label": "Neurological forms where intravenous enzyme replacement can't cross the blood-brain barrier", "basis": "mechanism",
     "members": [f"disease:{g}" for g in ("GBA1", "SMPD1", "IDUA", "IDS", "NPC1", "TPP1", "ARSA", "GALC", "HEXA", "CLN3")] +
                ["therapy:gaucher-enzyme-replacement", "therapy:olipudase-alfa", "therapy:laronidase", "therapy:idursulfase",
                 "therapy:pabinafusp-alfa", "therapy:cerliponase-alfa", "therapy:atidarsagene-autotemcel", "therapy:hsct-krabbe",
                 "therapy:aav-hexa-hexb-gene-therapy", "therapy:miglustat", "therapy:ambroxol"],
     "rationale": "Infused enzymes are large proteins that do not cross the blood-brain barrier (PMID:33304924), so the "
                  "approved intravenous enzymes treat the body but not the brain: the current Cerezyme label is limited to "
                  "non-CNS manifestations of type 1 or 3 Gaucher disease, the Xenpozyme label to non-CNS manifestations of "
                  "ASMD, and laronidase does not cross into the brain in Hurler syndrome. The diseases that are mainly "
                  "neurological are treated only by approaches that get around the barrier: enzyme infused into the brain "
                  "ventricles (cerliponase alfa, CLN2), gene-corrected blood stem cells (atidarsagene autotemcel, MLD), early "
                  "stem-cell transplantation (Krabbe), an enzyme fused to a transferrin-receptor antibody (pabinafusp alfa, "
                  "MPS II), spinal-fluid AAV (Tay-Sachs), or small molecules that cross the barrier (miglustat, ambroxol). "
                  "Tay-Sachs, CLN3 and Krabbe disease still have no approved disease-modifying therapy.",
     "edge_ids": eids(lambda e: e["type"] == "developed_for" and e["source"] in (
         "therapy:gaucher-enzyme-replacement", "therapy:olipudase-alfa", "therapy:laronidase", "therapy:idursulfase",
         "therapy:pabinafusp-alfa", "therapy:cerliponase-alfa", "therapy:atidarsagene-autotemcel", "therapy:hsct-krabbe",
         "therapy:aav-hexa-hexb-gene-therapy", "therapy:miglustat", "therapy:ambroxol"))},
]

# ============================================================================ gaps
gaps = read_json(L.HERE / "gaps.json") if (L.HERE / "gaps.json").exists() else []

frag = {"nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
        "edges": sorted(edges.values(), key=lambda e: (e["type"], e["id"])), "clusters": clusters, "gaps": gaps}
write_json(FRAGMENT, frag)
from collections import Counter  # noqa: E402
print("nodes", len(frag["nodes"]), dict(Counter(n["type"] for n in frag["nodes"])))
print("edges", len(frag["edges"]), dict(Counter(e["type"] for e in frag["edges"])))
print("clusters", len(clusters), "gaps", len(gaps))
print("studies per disease:", {g: len(v) for g, v in selected_studies.items()})
for d in dropped:
    print("  note:", d)
