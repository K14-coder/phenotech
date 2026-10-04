"""QuickGO check: which of the 45 deep-disease genes carry GO annotations (incl. descendants) to the
candidate cross-family processes. Used to (a) systematically look for shared processes and (b) attach
GO database evidence to curated edges.

Run:  python3 pipeline/families/cross/quickgo.py
Out:  data/raw/families/cross/quickgo/<UniProt>__<GO>.json   (raw QuickGO annotation search)
      data/raw/families/cross/quickgo_matrix.json            {GO: {SYMBOL: [[goId, evidence, reference], ...]}}
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "families" / "cross"
QG = RAW / "quickgo"
QG.mkdir(parents=True, exist_ok=True)

TERMS = {
    "GO:0000165": "MAPK cascade",
    "GO:0007265": "Ras protein signal transduction",
    "GO:0031929": "TOR signaling",
    "GO:0006914": "autophagy",
    "GO:0007269": "neurotransmitter secretion",
    "GO:0048791": "calcium ion-regulated exocytosis of neurotransmitter",
    "GO:0048167": "regulation of synaptic plasticity",
    "GO:0034976": "response to endoplasmic reticulum stress",
    "GO:0007040": "lysosome organization",
}


def genes():
    g = json.loads((ROOT / "data" / "graph.json").read_text())
    return {n["id"][5:]: n["xrefs"]["UniProt"] for n in g["nodes"] if n["type"] == "gene" and n.get("xrefs", {}).get("UniProt")}


def annotations(acc, go):
    p = QG / f"{acc}__{go.replace(':', '_')}.json"
    if p.exists():
        return json.loads(p.read_text())
    q = urllib.parse.urlencode({"geneProductId": acc, "goId": go, "goUsage": "descendants",
                                "goUsageRelationships": "is_a,part_of,occurs_in", "taxonId": "9606", "limit": 100})
    req = urllib.request.Request(f"https://www.ebi.ac.uk/QuickGO/services/annotation/search?{q}",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    p.write_text(json.dumps(d, indent=1))
    time.sleep(0.2)
    return d


def main():
    out = {}
    for go, name in TERMS.items():
        out[go] = {}
        for sym, acc in sorted(genes().items()):
            res = annotations(acc, go)["results"]
            if res:
                out[go][sym] = sorted({(r["goId"], r["goEvidence"], r.get("reference") or "") for r in res})
        print(f"{go} {name}: {', '.join(sorted(out[go]))}")
    (RAW / "quickgo_matrix.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
