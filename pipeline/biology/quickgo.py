"""Task 5 (process mechanisms): GO biological-process annotations from QuickGO.

Run:  python3 pipeline/biology/quickgo.py [--refresh]
Needs: data/raw/biology/genes.json, diseases.json
Out:  data/raw/biology/quickgo/*.json (raw), data/raw/biology/go_fragment.json ({nodes, edges})

For every (gene, process) pair we ask QuickGO for human annotations to the GO term OR ANY
DESCENDANT (goUsage=descendants; is_a/part_of/occurs_in). A gene->mechanism `participates_in`
edge is emitted only when at least one annotation exists. Confidence follows the evidence code:
experimental (EXP/IDA/IPI/IMP/IGI/IEP) with a PMID -> 0.9; IBA/TAS/IC/NAS -> 0.8; ISS -> 0.7;
IEA only -> 0.6.
"""
from __future__ import annotations

import sys
import time

from common import RAW, TODAY, cached_json, edge_id, read_json, write_json

REFRESH = "--refresh" in sys.argv
QG = "https://www.ebi.ac.uk/QuickGO/services"
HDR = {"Accept": "application/json"}

PROCESSES = {
    "snare-complex-assembly": {"label": "SNARE complex assembly", "go": "GO:0035493",
                               "query": ["GO:0035493"]},
    "synaptic-vesicle-priming": {"label": "Synaptic vesicle priming", "go": "GO:0016082",
                                 "query": ["GO:0016082"]},
    "ca-triggered-exocytosis": {"label": "Ca2+-triggered neurotransmitter exocytosis",
                                "go": "GO:0048791", "query": ["GO:0048791"]},
    "synaptic-vesicle-fusion": {"label": "Synaptic vesicle fusion with the active zone membrane",
                                "go": "GO:0031629", "query": ["GO:0031629"]},
    "snare-complex-disassembly": {"label": "SNARE complex disassembly", "go": "GO:0035494",
                                  "query": ["GO:0035494"]},
    "gaba-reuptake": {"label": "GABA reuptake", "go": "GO:0051936",
                      "query": ["GO:0051936", "GO:0051939"]},
}
EXPERIMENTAL = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HDA", "HMP", "HGI", "HEP"}
CURATED_OTHER = {"IBA", "TAS", "IC", "NAS", "IKR", "IRD"}


def term_info(go_ids: list[str]) -> dict:
    obj = cached_json(RAW / "quickgo" / "terms.json", f"{QG}/ontology/go/terms/{','.join(go_ids)}",
                      headers=HDR, refresh=REFRESH)
    return {r["id"]: r for r in obj["results"]}


def annotations(acc: str, go: str) -> list[dict]:
    obj = cached_json(RAW / "quickgo" / f"{acc}__{go.replace(':', '_')}.json",
                      f"{QG}/annotation/search",
                      params={"geneProductId": f"UniProtKB:{acc}", "goId": go, "goUsage": "descendants",
                              "taxonId": 9606, "limit": 100},
                      headers=HDR, refresh=REFRESH)
    time.sleep(0.15)
    return obj.get("results", [])


def main() -> None:
    genes = read_json(RAW / "genes.json")
    dis = read_json(RAW / "diseases.json")
    all_terms = sorted({t for p in PROCESSES.values() for t in p["query"]})
    info = term_info(all_terms)
    nodes, edges, table = [], [], {}
    for slug, p in PROCESSES.items():
        t = info.get(p["go"], {})
        nodes.append({
            "id": f"mech:{slug}", "type": "mechanism", "label": p["label"],
            "xrefs": {"GO": p["go"]},
            "summary": (t.get("definition") or {}).get("text"),
            "attrs": {"kind": "process", "go_id": p["go"], "go_name": t.get("name")},
            "sources": [{"source": "GO", "ref": p["go"],
                         "url": f"https://www.ebi.ac.uk/QuickGO/term/{p['go']}",
                         "title": t.get("name"), "kind": "database", "study_type": "database_record",
                         "quote": (t.get("definition") or {}).get("text"),
                         "extracted_by": "database", "retrieved": TODAY}],
        })
    for sym, d in dis.items():
        if not d["include"]:
            continue
        acc = genes[sym].get("uniprot_acc")
        if not acc:
            continue
        for slug, p in PROCESSES.items():
            anns = []
            for q in p["query"]:
                anns += annotations(acc, q)
            anns = [a for a in anns if (a.get("qualifier") or "").startswith(("involved_in", "acts_upstream"))
                    and not (a.get("qualifier") or "").startswith("NOT")]
            if not anns:
                continue
            codes = sorted({a["goEvidence"] for a in anns})
            refs = sorted({a["reference"] for a in anns})
            exp_pmid = [a for a in anns if a["goEvidence"] in EXPERIMENTAL and a["reference"].startswith("PMID:")]
            if exp_pmid:
                conf = 0.9
            elif any(c in CURATED_OTHER for c in codes):
                conf = 0.8
            elif "ISS" in codes or "ISO" in codes or "ISA" in codes:
                conf = 0.7
            else:
                conf = 0.6
            go_hits = sorted({a["goId"] for a in anns})
            table[(sym, slug)] = {"codes": codes, "refs": refs, "go_hits": go_hits}
            ev = [{"source": "GO", "ref": p["go"],
                   "url": f"https://www.ebi.ac.uk/QuickGO/annotations?geneProductId={acc}&goId={p['go']}"
                          f"&goUsage=descendants",
                   "title": f"QuickGO: {len(anns)} annotation(s) of UniProtKB:{acc} ({sym}) to "
                            f"{', '.join(go_hits)}; evidence {', '.join(codes)}",
                   "kind": "database", "study_type": "database_record", "extracted_by": "database",
                   "retrieved": TODAY}]
            for a in exp_pmid[:3]:
                pm = a["reference"].split(":")[1]
                ev.append({"source": "GO", "ref": a["reference"],
                           "url": f"https://pubmed.ncbi.nlm.nih.gov/{pm}/",
                           "title": f"GO annotation {a['goId']} ({a['goEvidence']}, assigned by {a['assignedBy']})",
                           "kind": "database", "study_type": "database_record",
                           "extracted_by": "database", "retrieved": TODAY})
            edges.append({
                "id": edge_id(f"gene:{sym}", "participates_in", f"mech:{slug}"),
                "source": f"gene:{sym}", "target": f"mech:{slug}", "type": "participates_in",
                "label": "takes part in",
                "explanation": (f"Gene Ontology annotates {sym} to {p['label'].lower()} "
                                f"({p['go']} or a more specific child term), evidence codes {', '.join(codes)}."),
                "evidence_level": "curated" if conf >= 0.7 else "inferred",
                "status": "supported", "confidence": conf, "evidence": ev,
                "attrs": {"go_evidence_codes": codes, "go_terms_hit": go_hits},
            })
            print(f"  {sym:7s} -> {slug:26s} codes={codes} conf={conf}")
    write_json(RAW / "go_fragment.json", {"nodes": nodes, "edges": edges})
    print(f"mechanism(process) nodes={len(nodes)} participates_in={len(edges)}")


if __name__ == "__main__":
    main()
