"""DEE family, step 3: GO process / function mechanisms from QuickGO (same method as
pipeline/biology/quickgo.py: human annotations to the term OR ANY DESCENDANT; a participates_in
edge only when >= 1 positive annotation exists; confidence by evidence code).

Also checks cross-family links in both directions:
  * the 10 DEE genes against the SNAREopathy process terms already in the graph, and
  * the 11 SNAREopathy genes against the new DEE terms.

Run:  python3 pipeline/families/dee/quickgo.py [--refresh]
Out:  data/raw/families/dee/quickgo/*.json (raw), data/raw/families/dee/go_fragment.json
"""
from __future__ import annotations

import sys
import time

from dee_common import BIO_RAW, GENES, RAW, SNARE_GENES, TODAY, cached_json, edge_id, read_json, write_json

REFRESH = "--refresh" in sys.argv
QG = "https://www.ebi.ac.uk/QuickGO/services"
HDR = {"Accept": "application/json"}

# New mechanism nodes created by this family (slug -> GO term). kind = "process" per SCHEMA
# (molecular-function terms are used where the function itself is the disease-relevant mechanism).
NEW_TERMS = {
    "voltage-gated-sodium-channel-activity": ("Voltage-gated sodium channel activity", "GO:0005248"),
    "potassium-channel-activity": ("Potassium channel activity", "GO:0005267"),
    "voltage-gated-calcium-channel-activity": ("Voltage-gated calcium channel activity", "GO:0005245"),
    "nmda-receptor-activity": ("NMDA glutamate receptor activity", "GO:0004972"),
    "action-potential": ("Action potential (neuronal firing)", "GO:0001508"),
    "regulation-of-synaptic-plasticity": ("Regulation of synaptic plasticity", "GO:0048167"),
    "negative-regulation-of-ras-signaling": ("Negative regulation of Ras protein signal transduction", "GO:0046580"),
    "glucose-transmembrane-transport": ("Glucose transmembrane transport", "GO:1904659"),
    "protein-serine-threonine-kinase-activity": ("Protein serine/threonine kinase activity", "GO:0004674"),
}
# Existing SNAREopathy process nodes (already in data/graph.json; reused, never re-emitted)
EXISTING_TERMS = {
    "snare-complex-assembly": ("SNARE complex assembly", "GO:0035493"),
    "synaptic-vesicle-priming": ("Synaptic vesicle priming", "GO:0016082"),
    "ca-triggered-exocytosis": ("Ca2+-triggered neurotransmitter exocytosis", "GO:0048791"),
    "synaptic-vesicle-fusion": ("Synaptic vesicle fusion with the active zone membrane", "GO:0031629"),
    "snare-complex-disassembly": ("SNARE complex disassembly", "GO:0035494"),
    "gaba-reuptake": ("GABA reuptake", "GO:0051936"),
}
EXPERIMENTAL = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HDA", "HMP", "HGI", "HEP"}
CURATED_OTHER = {"IBA", "TAS", "IC", "NAS", "IKR", "IRD"}


def term_info(go_ids):
    obj = cached_json(RAW / "quickgo" / "terms.json", f"{QG}/ontology/go/terms/{','.join(go_ids)}",
                      headers=HDR, refresh=REFRESH)
    return {r["id"]: r for r in obj["results"]}


def annotations(acc, go):
    path = RAW / "quickgo" / f"{acc}__{go.replace(':', '_')}.json"
    fresh = REFRESH or not path.exists()
    obj = cached_json(path, f"{QG}/annotation/search",
                      params={"geneProductId": f"UniProtKB:{acc}", "goId": go, "goUsage": "descendants",
                              "taxonId": 9606, "limit": 100}, headers=HDR, refresh=REFRESH)
    if fresh:
        time.sleep(0.12)
    return obj.get("results", [])


def edge_for(sym, acc, slug, label, go, anns):
    codes = sorted({a["goEvidence"] for a in anns})
    exp_pmid = [a for a in anns if a["goEvidence"] in EXPERIMENTAL and a["reference"].startswith("PMID:")]
    if exp_pmid:
        conf = 0.9
    elif any(c in CURATED_OTHER for c in codes):
        conf = 0.8
    elif {"ISS", "ISO", "ISA"} & set(codes):
        conf = 0.7
    else:
        conf = 0.6
    hits = sorted({a["goId"] for a in anns})
    ev = [{"source": "GO", "ref": go,
           "url": f"https://www.ebi.ac.uk/QuickGO/annotations?geneProductId={acc}&goId={go}&goUsage=descendants",
           "title": f"QuickGO: {len(anns)} annotation(s) of UniProtKB:{acc} ({sym}) to {', '.join(hits)}; "
                    f"evidence {', '.join(codes)}",
           "kind": "database", "study_type": "database_record", "extracted_by": "database", "retrieved": TODAY}]
    for a in exp_pmid[:3]:
        pm = a["reference"].split(":")[1]
        ev.append({"source": "GO", "ref": a["reference"], "url": f"https://pubmed.ncbi.nlm.nih.gov/{pm}/",
                   "title": f"GO annotation {a['goId']} ({a['goEvidence']}, assigned by {a['assignedBy']})",
                   "kind": "database", "study_type": "database_record", "extracted_by": "database",
                   "retrieved": TODAY})
    return {"id": edge_id(f"gene:{sym}", "participates_in", f"mech:{slug}"),
            "source": f"gene:{sym}", "target": f"mech:{slug}", "type": "participates_in",
            "label": "takes part in",
            "explanation": (f"Gene Ontology annotates {sym} to {label.lower()} ({go} or a more specific "
                            f"child term), evidence codes {', '.join(codes)}."),
            "evidence_level": "curated" if conf >= 0.7 else "inferred", "status": "supported",
            "confidence": conf, "evidence": ev, "attrs": {"go_evidence_codes": codes, "go_terms_hit": hits}}


def main():
    genes = read_json(RAW / "genes.json")
    bio_genes = read_json(BIO_RAW / "genes.json")
    info = term_info(sorted({t[1] for t in NEW_TERMS.values()}))
    nodes, edges = [], []
    for slug, (label, go) in NEW_TERMS.items():
        t = info.get(go, {})
        defin = (t.get("definition") or {}).get("text")
        nodes.append({"id": f"mech:{slug}", "type": "mechanism", "label": label, "xrefs": {"GO": go},
                      "summary": defin,
                      "attrs": {"kind": "process", "go_id": go, "go_name": t.get("name"), "go_aspect": t.get("aspect"),
                                "family": "dee"},
                      "sources": [{"source": "GO", "ref": go, "url": f"https://www.ebi.ac.uk/QuickGO/term/{go}",
                                   "title": t.get("name"), "kind": "database", "study_type": "database_record",
                                   "quote": defin, "extracted_by": "database", "retrieved": TODAY}]})
    table = []
    # DEE genes x (new + existing SNARE terms)
    for sym in GENES:
        acc = genes[sym]["uniprot_acc"]
        for slug, (label, go) in list(NEW_TERMS.items()) + list(EXISTING_TERMS.items()):
            anns = [a for a in annotations(acc, go)
                    if (a.get("qualifier") or "").startswith(("involved_in", "acts_upstream", "enables", "contributes_to"))]
            if anns:
                edges.append(edge_for(sym, acc, slug, label, go, anns))
                table.append((sym, slug, edges[-1]["confidence"], slug in EXISTING_TERMS))
    # SNARE genes x new DEE terms (cross-family)
    for sym in SNARE_GENES:
        acc = bio_genes.get(sym, {}).get("uniprot_acc")
        if not acc:
            continue
        for slug, (label, go) in NEW_TERMS.items():
            anns = [a for a in annotations(acc, go)
                    if (a.get("qualifier") or "").startswith(("involved_in", "acts_upstream", "enables", "contributes_to"))]
            if anns:
                e = edge_for(sym, acc, slug, label, go, anns)
                e["attrs"]["cross_family"] = True
                edges.append(e)
                table.append((sym, slug, e["confidence"], True))
    for row in table:
        print("  %-8s -> %-42s conf=%.1f %s" % (row[0], row[1], row[2], "CROSS-FAMILY" if row[3] else ""))
    write_json(RAW / "go_fragment.json", {"nodes": nodes, "edges": edges})
    print(f"mechanism(process) nodes={len(nodes)} participates_in={len(edges)}")


if __name__ == "__main__":
    main()
