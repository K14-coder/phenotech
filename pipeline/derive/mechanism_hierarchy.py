"""GO hierarchy between existing mechanism nodes -> data/curated/mechanism_hierarchy.json (SCHEMA fragment)

Run:  python3 pipeline/derive/mechanism_hierarchy.py     (stdlib; then python3 pipeline/build_graph.py)
In:   data/raw/downloads/go-basic.obo (current.geneontology.org/ontology/go-basic.obo), data/graph.json
Rule: for every pair of GO-backed mech: nodes (attrs.go_id), emit ONE `part_of` edge child -> ancestor
      when GO has a directed path from the child's term to the ancestor's term of at most MAX_STEPS steps
      over is_a, part_of, regulates, positively_regulates or negatively_regulates (the shortest path is
      kept and written out in the explanation). One intermediate GO term may be added as a new mech:
      node only when it is the single term that joins two existing mechanisms (it never was, this run).
      Edges stay inside the existing mechanism nodes; no other node is created.
"""
from __future__ import annotations

import re
from collections import deque

from dcommon import CURATED, DOWNLOADS, TODAY, Graph, write_json

MAX_STEPS = 3
RELS = {"is_a", "part_of", "regulates", "positively_regulates", "negatively_regulates"}


def parse_go():
    terms, cur, version = {}, None, None
    for line in (DOWNLOADS / "go-basic.obo").read_text().splitlines():
        if line.startswith("data-version:"):
            version = line.split(": ", 1)[1]
        if line == "[Term]":
            cur = {"rel": []}
            continue
        if line.startswith("["):
            cur = None
            continue
        if cur is None:
            continue
        if line.startswith("id: "):
            cur["id"] = line[4:]
            terms[cur["id"]] = cur
        elif line.startswith("name: "):
            cur["name"] = line[6:]
        elif line.startswith("is_a: "):
            cur["rel"].append(("is_a", line[6:].split()[0]))
        elif line.startswith("relationship: "):
            r, t = line[14:].split()[:2]
            if r in RELS:
                cur["rel"].append((r, t))
        elif line == "is_obsolete: true":
            cur["obsolete"] = True
    return terms, version


def main():
    terms, version = parse_go()
    g = Graph()
    mech = {}
    for n in g.nodes.values():
        go = (n.get("attrs") or {}).get("go_id")
        if n["type"] == "mechanism" and go and go in terms and not terms[go].get("obsolete"):
            mech[go] = n["id"]
    edges, unreachable = [], []
    for go, mid in sorted(mech.items()):
        dq, seen, found = deque([(go, [])]), {go}, {}
        while dq:
            t, path = dq.popleft()
            if len(path) >= MAX_STEPS:
                continue
            for r, p in terms.get(t, {}).get("rel", []):
                np_ = path + [(r, p)]
                if p in mech and p != go and p not in found:
                    found[p] = np_
                if p not in seen:
                    seen.add(p)
                    dq.append((p, np_))
        for tgt_go, path in found.items():
            steps = [terms[go]["name"]] + [f"{r.replace('_', ' ')} {terms[p]['name']} ({p})" for r, p in path]
            chain = " → ".join(steps)
            src, tgt = mid, mech[tgt_go]
            edges.append({
                "id": f"{src}|part_of|{tgt}", "source": src, "target": tgt, "type": "part_of",
                "label": "is part of / regulates (GO hierarchy)",
                "explanation": (f"In the Gene Ontology, {g.nodes[src]['label']} ({go}) leads to "
                                f"{g.nodes[tgt]['label']} ({tgt_go}) in {len(path)} step(s): {chain}."),
                "evidence_level": "curated", "status": "supported", "confidence": 0.9 if len(path) == 1 else 0.85,
                "evidence": [{"source": "GO", "ref": go, "url": f"https://www.ebi.ac.uk/QuickGO/term/{go}",
                              "title": f"GO {version}: {terms[go]['name']} → {terms[tgt_go]['name']}",
                              "kind": "database", "study_type": "database_record", "extracted_by": "database",
                              "retrieved": TODAY}],
                "attrs": {"go_path": [{"relation": r, "term": p, "name": terms[p]["name"]} for r, p in path],
                          "steps": len(path), "go_release": version},
            })
    frag = {"nodes": [], "edges": sorted(edges, key=lambda e: e["id"]), "clusters": [], "gaps": [{
        "id": "gap:ras-to-mapk-hierarchy",
        "about": "mech:ras-protein-signal-transduction / mech:mapk-cascade",
        "question": "Should Ras signalling reach the MAPK cascade in the graph, so RAS-pathway genes (LZTR1, RIT1, "
                    "SOS1) connect to MEK-inhibitor targets?",
        "what_is_missing": ["GO has no is_a / part_of / regulates path of <= 3 steps between 'Ras protein signal "
                            "transduction' (GO:0007265) and 'MAPK cascade' (GO:0000165): they are siblings, two "
                            "steps each below 'intracellular signal transduction'",
                            "Reactome (NCBI2Reactome) has no pathway annotation at all for LZTR1 or RIT1"],
        "searched": [f"go-basic.obo {version}, all paths <= {MAX_STEPS} steps between the GO-backed mechanism nodes",
                     "Reactome NCBI2Reactome.txt for LZTR1 (8216) and RIT1 (6016)"],
        "how_to_find_out": "Curate gene-level participates_in edges from the RASopathy literature (e.g. LZTR1 "
                           "-> MAPK cascade with a quoted functional paper), or accept a Reactome-sourced "
                           "RAS -> RAF/MAP kinase cascade link as a separate, labelled relation.",
    }]}
    write_json(CURATED / "mechanism_hierarchy.json", frag)
    print(f"[mechanism_hierarchy] GO {version}: {len(mech)} GO-backed mechanisms, {len(edges)} part_of edges")
    for e in edges:
        print(f"  {e['source']} -> {e['target']}  ({e['attrs']['steps']} step)")


if __name__ == "__main__":
    main()
