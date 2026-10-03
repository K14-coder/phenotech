"""Re-set the global index's `atlas` flag for every mapped umbrella disease (cheap; safe to re-run).

Run:  python3 pipeline/derive/atlas_flags.py      (stdlib; well under a second)
Reads data/curated/family_*.json (read-only; written by the family agents, which land later), plus
the base flags computed by global_index.py (data/raw/downloads/global_entries.json), and rewrites
only the `atlas` column of data/derived/global/index.json. Nothing else is recomputed, so this can be
run every time a family file lands without rebuilding the neighbour or mechanism shards.

A row gets `atlas = "disease:<GENE>"` when, for a `disease:<GENE>` node in a family file:
  * the row's MONDO id is in the node's xrefs or in attrs.subtypes[].MONDO, or
  * one of the row's OMIM / ORPHA numbers is in those xrefs and the row is single-gene for GENE
    (or has no gene), or
  * the row is single-gene for GENE from OMIM's Mendelian list (gsrc 1).
Multi-gene clinical groups are never flagged, so a family umbrella cannot capture a grouping.
"""
from __future__ import annotations

import glob
import re

from dcommon import CURATED, DOWNLOADS, TODAY, read_json, write_json

from pathlib import Path

GLOBAL = Path(__file__).resolve().parents[2] / "data" / "derived" / "global"


def _ids(value, prefix):
    out = set()
    for v in (value if isinstance(value, list) else [value]):
        if v is None:
            continue
        v = str(v)
        v = re.sub(r"^(Orphanet|ORPHA|ORPHANET):", "", v) if prefix == "ORPHA" else v
        v = re.sub(r"^OMIM:", "", v) if prefix == "OMIM" else v
        if prefix == "MONDO" and not v.startswith("MONDO:"):
            continue
        out.add(v)
    return out


def umbrellas():
    """{GENE: {"MONDO": set, "OMIM": set, "ORPHA": set, "file": str}} from data/curated/family_*.json."""
    out = {}
    for f in sorted(glob.glob(str(CURATED / "family_*.json"))):
        try:
            frag = read_json(f)
        except Exception as ex:  # a half-written file must not break the index
            print(f"[atlas_flags] skipped {f}: {ex}")
            continue
        for n in frag.get("nodes", []):
            if n.get("type") != "disease" or not str(n.get("id", "")).startswith("disease:"):
                continue
            gene = n["id"].split(":", 1)[1]
            u = out.setdefault(gene, {"MONDO": set(), "OMIM": set(), "ORPHA": set(), "file": Path(f).name})
            xr = n.get("xrefs", {}) or {}
            for k in ("MONDO", "OMIM", "ORPHA"):
                u[k] |= _ids(xr.get(k), k)
            for st in (n.get("attrs", {}) or {}).get("subtypes", []) or []:
                for k in ("MONDO", "OMIM", "ORPHA"):
                    u[k] |= _ids(st.get(k), k)
    return out


def main():
    path = GLOBAL / "index.json"
    if not path.exists():
        print("[atlas_flags] no index.json yet")
        return
    idx = read_json(path)
    f = idx["f"]
    col = {k: i for i, k in enumerate(f)}
    base = {}
    ent = DOWNLOADS / "global_entries.json"
    if ent.exists():
        base = {k: v.get("atlas") for k, v in read_json(ent)["entries"].items()}
    fams = umbrellas()
    added = 0
    for r in idx["rows"]:
        rid = r[col["id"]]
        flag = base.get(rid, r[col["atlas"]] or None) or None
        genes = [g for g in (r[col["genes"]] or "").split(",") if g]
        omim = set((r[col["omim"]] or "").split(",")) - {""}
        orpha = set((r[col["orpha"]] or "").split(",")) - {""}
        if not flag:
            for gene, u in fams.items():
                single = genes == [gene]
                if rid in u["MONDO"] or ((omim & u["OMIM"] or orpha & u["ORPHA"]) and (single or not genes)) \
                        or (single and r[col["gsrc"]] == 1):
                    flag = f"disease:{gene}"
                    added += 1
                    break
        r[col["atlas"]] = flag or 0
    write_json(path, idx, compact=True)
    meta_path = GLOBAL / "meta.json"
    if meta_path.exists():
        meta = read_json(meta_path)
        meta["atlas_flags"] = {
            "generated": TODAY,
            "family_files": sorted({u["file"] for u in fams.values()}),
            "family_umbrellas": sorted(f"disease:{g}" for g in fams),
            "rows_flagged_total": sum(1 for r in idx["rows"] if r[col["atlas"]]),
            "rows_added_from_families": added,
            "rule": "MONDO xref/subtype match, or OMIM/ORPHA match on a single-gene row, or single-gene "
                    "OMIM-Mendelian row for the umbrella's gene; multi-gene groups never flagged",
        }
        meta.setdefault("counts", {})["in_atlas"] = meta["atlas_flags"]["rows_flagged_total"]
        write_json(meta_path, meta)
    print(f"[atlas_flags] {len(fams)} family umbrellas; {added} rows added; "
          f"{sum(1 for r in idx['rows'] if r[col['atlas']])} rows flagged in total")


if __name__ == "__main__":
    main()
