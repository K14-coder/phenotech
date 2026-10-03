"""Shared helpers for the RASopathy family build (stdlib only).

Reuses pipeline/biology/common.py for HTTP, caching and - importantly - the NCBI
E-utilities throttle: a file lock SHARED ACROSS PROCESSES/AGENTS (<= 2 requests/s),
tool=rare-disease-atlas, no email parameter, exponential backoff on 429/5xx.

All raw responses for this family live under data/raw/families/rasopathy/.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BIO = ROOT / "pipeline" / "biology"
# appended (not prepended) so this family's own scripts win on name clashes; biology modules are
# loaded explicitly by path with load_bio().
if str(BIO) not in sys.path:
    sys.path.append(str(BIO))


def load_bio(name: str):
    """Import pipeline/biology/<name>.py under the module name bio_<name>."""
    key = f"bio_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, BIO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


bio_common = load_bio("common")  # biology helpers: http_get, cached_json, eutils (shared NCBI lock), evidence
sys.modules.setdefault("common", bio_common)  # biology modules do `from common import ...`

RAW = ROOT / "data" / "raw" / "families" / "rasopathy"
RAW.mkdir(parents=True, exist_ok=True)
CURATED = ROOT / "data" / "curated"
OUT_FRAGMENT = CURATED / "family_rasopathy.json"
DOWNLOADS = ROOT / "data" / "raw" / "downloads"
GRAPH = ROOT / "data" / "graph.json"

FAMILY = "rasopathy"
GENES = ["PTPN11", "SOS1", "RAF1", "BRAF", "KRAS", "HRAS", "NF1", "MAP2K1", "SHOC2", "CBL", "RIT1", "LZTR1"]

TODAY = bio_common.TODAY
http_get = bio_common.http_get
cached_json = bio_common.cached_json
cached_text = bio_common.cached_text
eutils = bio_common.eutils          # shared cross-process NCBI throttle
evidence = bio_common.evidence
edge_id = bio_common.edge_id


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def norm(s: str) -> str:
    """Normalisation used for every quote check (same as pipeline/biology/verify_quotes.py)."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"').replace(" ", " ").replace("​", ""))
    return " ".join(s.split())


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def redact_emails(text: str) -> str:
    return EMAIL_RE.sub("[email-redacted]", text)


def slugify(s: str, maxlen: int = 60) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-")


def existing_graph_ids() -> set[str]:
    """Node ids owned by OTHER layers (to reuse, never duplicate): every node in the other curated
    fragments that pipeline/build_graph.py merges into data/graph.json. This family's own fragment is
    excluded, so a rebuild after build_graph.py does not mistake its own nodes for foreign ones."""
    ids = set()
    for p in sorted(CURATED.glob("*.json")):
        if p.name in (OUT_FRAGMENT.name, "overrides.json"):
            continue
        try:
            data = read_json(p)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            ids |= {n["id"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n}
    return ids


def existing_node_types() -> dict[str, str]:
    types = {}
    for p in sorted(CURATED.glob("*.json")):
        if p.name in (OUT_FRAGMENT.name, "overrides.json"):
            continue
        try:
            data = read_json(p)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            types.update({n["id"]: n["type"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n})
    return types
