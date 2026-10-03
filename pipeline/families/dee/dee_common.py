"""Shared helpers for the DEE family build (developmental and epileptic encephalopathies:
channels, receptors and signalling). Stdlib only.

Reuses pipeline/biology/common.py for HTTP, caching and the NCBI E-utilities throttle: a file
lock SHARED ACROSS PROCESSES / AGENTS (<= 2 requests/s), tool=rare-disease-atlas, no email
parameter, exponential backoff on 429/5xx.

Every raw response for this family lives under data/raw/families/dee/.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "biology"))

import common as bio_common  # noqa: E402

RAW = ROOT / "data" / "raw" / "families" / "dee"
RAW.mkdir(parents=True, exist_ok=True)
CURATED = ROOT / "data" / "curated"
OUT_FRAGMENT = CURATED / "family_dee.json"
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
GRAPH = ROOT / "data" / "graph.json"
BIO_RAW = ROOT / "data" / "raw" / "biology"

FAMILY = "dee"
GENES = ["SCN1A", "SCN2A", "SCN8A", "KCNQ2", "KCNT1", "CACNA1A", "GRIN2B", "CDKL5", "SYNGAP1", "SLC2A1"]
SNARE_GENES = ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B", "SYT2", "CPLX1", "UNC13A", "STX1A",
               "NSF", "SLC6A1"]

TODAY = bio_common.TODAY
http_get = bio_common.http_get
cached_json = bio_common.cached_json
cached_text = bio_common.cached_text
eutils = bio_common.eutils          # shared cross-process NCBI throttle, tool=rare-disease-atlas
evidence = bio_common.evidence
edge_id = bio_common.edge_id


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def norm(s: str) -> str:
    """Normalisation used for every quote check (same as pipeline/biology/verify_quotes.py,
    plus non-breaking / zero-width spaces)."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
          .replace(" ", " ").replace("​", ""))
    return " ".join(s.split())


def existing_graph() -> dict:
    """Node id -> node from every OTHER curated fragment (data/curated/*.json except ours).

    Reads the fragments rather than data/graph.json, because graph.json may already contain this
    family's own nodes from an earlier build."""
    out = {}
    for p in sorted(CURATED.glob("*.json")):
        if p.name in (OUT_FRAGMENT.name, "overrides.json"):
            continue
        d = read_json(p)
        if isinstance(d, dict):
            for n in d.get("nodes", []):
                out.setdefault(n["id"], n)
    return out
