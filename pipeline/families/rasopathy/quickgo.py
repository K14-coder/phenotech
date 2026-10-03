"""GO biological-process mechanisms for the RASopathy genes (QuickGO), adapted from
pipeline/biology/quickgo.py: for each (gene, process) pair, human annotations to the term OR ANY
DESCENDANT (goUsage=descendants). A participates_in edge needs >= 1 non-NOT annotation.
Confidence by evidence code: experimental + PMID 0.9; IBA/TAS/IC/NAS 0.8; ISS/ISO/ISA 0.7; IEA 0.6.

Run:  python3 pipeline/families/rasopathy/quickgo.py [--refresh]
Out:  data/raw/families/rasopathy/quickgo/*.json, go_fragment.json
"""
from __future__ import annotations

import sys
import time

from ras_common import FAMILY, GENES, RAW, TODAY, cached_json, edge_id, read_json, write_json

REFRESH = "--refresh" in sys.argv
QG = "https://www.ebi.ac.uk/QuickGO/services"
HDR = {"Accept": "application/json"}
PROCESSES = {
    "ras-protein-signal-transduction": {"label": "Ras protein signal transduction", "go": "GO:0007265"},
    "mapk-cascade": {"label": "MAPK cascade", "go": "GO:0000165"},
    "negative-regulation-of-ras-signaling": {"label": "Negative regulation of Ras protein signal transduction",
                                             "go": "GO:0046580"},
    "positive-regulation-of-ras-signaling": {"label": "Positive regulation of Ras protein signal transduction",
                                             "go": "GO:0046579"},
}
EXPERIMENTAL = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HDA", "HMP", "HGI", "HEP"}
CURATED_OTHER = {"IBA", "TAS", "IC", "NAS", "IKR", "IRD"}


def term_info(ids):
    obj = cached_json(RAW / "quickgo" / "terms.json", f"{QG}/ontology/go/terms/{','.join(ids)}", headers=HDR,
                      refresh=REFRESH)
    return {r["id"]: r for r in obj["results"]}


def annotations(acc, go):
    obj = cached_json(RAW / "quickgo" / f"{acc}__{go.replace(':', '_')}.json", f"{QG}/annotation/search",
                      params={"geneProductId": f"UniProtKB:{acc}", "goId": go, "goUsage": "descendants",
                              "taxonId": 9606, "limit": 100}, headers=HDR, refresh=REFRESH)
    time.sleep(0.15)
    return obj.get("results", [])


def main():
    genes = read_json(RAW / "genes.json")
    info = term_info(sorted(p["go"] for p in PROCESSES.values()))
    nodes, edges = [], []
    for slug, p in PROCESSES.items():
        t = info.get(p["go"], {})
        print(f"{p['go']} {t.get('name')!r} obsolete={t.get('isObsolete')}")
        if t.get("isObsolete"):
            continue
        nodes.append({"id": f"mech:{slug}", "type": "mechanism", "label": p["label"], "xrefs": {"GO": p["go"]},
                      "summary": (t.get("definition") or {}).get("text"),
                      "attrs": {"kind": "process", "go_id": p["go"], "go_name": t.get("name"), "family": FAMILY},
                      "sources": [{"source": "GO", "ref": p["go"], "url": f"https://www.ebi.ac.uk/QuickGO/term/{p['go']}",
                                   "title": t.get("name"), "kind": "database", "study_type": "database_record",
                                   "quote": (t.get("definition") or {}).get("text"), "extracted_by": "database",
                                   "retrieved": TODAY}]})
    emitted = {n["id"] for n in nodes}
    for sym in GENES:
        acc = genes[sym].get("uniprot_acc")
        for slug, p in PROCESSES.items():
            if f"mech:{slug}" not in emitted:
                continue
            anns = [a for a in annotations(acc, p["go"])
                    if (a.get("qualifier") or "").startswith(("involved_in", "acts_upstream"))]
            if not anns:
                print(f"  {sym:7s} -- {slug}: none")
                continue
            codes = sorted({a["goEvidence"] for a in anns})
            exp = [a for a in anns if a["goEvidence"] in EXPERIMENTAL and a["reference"].startswith("PMID:")]
            conf = 0.9 if exp else 0.8 if set(codes) & CURATED_OTHER else 0.7 if set(codes) & {"ISS", "ISO", "ISA"} else 0.6
            hits = sorted({a["goId"] for a in anns})
            ev = [{"source": "GO", "ref": p["go"],
                   "url": f"https://www.ebi.ac.uk/QuickGO/annotations?geneProductId={acc}&goId={p['go']}&goUsage=descendants",
                   "title": f"QuickGO: {len(anns)} annotation(s) of UniProtKB:{acc} ({sym}) to {', '.join(hits)}; "
                            f"evidence {', '.join(codes)}",
                   "kind": "database", "study_type": "database_record", "extracted_by": "database", "retrieved": TODAY}]
            for a in exp[:3]:
                ev.append({"source": "GO", "ref": a["reference"],
                           "url": f"https://pubmed.ncbi.nlm.nih.gov/{a['reference'].split(':')[1]}/",
                           "title": f"GO annotation {a['goId']} ({a['goEvidence']}, assigned by {a['assignedBy']})",
                           "kind": "database", "study_type": "database_record", "extracted_by": "database",
                           "retrieved": TODAY})
            edges.append({"id": edge_id(f"gene:{sym}", "participates_in", f"mech:{slug}"),
                          "source": f"gene:{sym}", "target": f"mech:{slug}", "type": "participates_in",
                          "label": "takes part in",
                          "explanation": f"Gene Ontology annotates {sym} to {p['label'].lower()} ({p['go']} or a more "
                                         f"specific child term), evidence codes {', '.join(codes)}.",
                          "evidence_level": "curated" if conf >= 0.7 else "inferred", "status": "supported",
                          "confidence": conf, "evidence": ev,
                          "attrs": {"go_evidence_codes": codes, "go_terms_hit": hits}})
            print(f"  {sym:7s} -> {slug:38s} codes={codes} conf={conf}")
    write_json(RAW / "go_fragment.json", {"nodes": nodes, "edges": edges})
    print(f"process mechanisms={len(nodes)} participates_in={len(edges)}")


if __name__ == "__main__":
    main()
