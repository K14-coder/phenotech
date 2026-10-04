"""Per-gene DNA change types (ClinVar "Type") for the P/LP germline variants in the committed shards.

    python3 pipeline/ingest/clinvar_types.py      # stdlib, offline, ~5 s

Reads data/derived/ingest/clinvar/<bucket>.json (field 4 of each variant = TYPE_CODE from clinvar_full.py)
and adds, per gene, "t": {type code: count} to data/derived/ingest/clinvar_gene_spectrum.json. The
existing "c" spectrum is the molecular consequence (missense, frameshift, ...); "t" is the kind of DNA
change itself: substitution, deletion, duplication, insertion, indel, inversion, translocation,
copy-number loss or gain, repeat (microsatellite), complex. clinvar_full.py writes the same field on a
full rerun.
"""
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
IN = ROOT / "data/derived/ingest/clinvar"
SPEC = ROOT / "data/derived/ingest/clinvar_gene_spectrum.json"
TYPE_LABELS = {
    "snv": "single-letter substitution", "del": "deletion", "dup": "duplication", "ins": "insertion",
    "indel": "deletion-insertion (indel)", "inv": "inversion", "trans": "translocation",
    "cnv_loss": "copy-number loss", "cnv_gain": "copy-number gain", "str": "repeat expansion or contraction",
    "complex": "complex rearrangement", "fusion": "gene fusion", "other": "other",
}


def main():
    per = {}
    for f in sorted(IN.glob("*.json")):
        for gene, ge in json.loads(f.read_text())["g"].items():
            per[gene] = dict(Counter(v[4] for v in ge.get("v", [])))
    spec = json.loads(SPEC.read_text())
    hit = 0
    for gene, g in spec["genes"].items():
        if gene in per:
            g["t"] = per[gene]
            hit += 1
    spec["type_keys"] = TYPE_LABELS
    spec["type_note"] = ("t = ClinVar variant Type (kind of DNA change) per P/LP germline variant; "
                         "c = molecular consequence for the protein")
    SPEC.write_text(json.dumps(spec, separators=(",", ":"), ensure_ascii=False))
    tot = Counter()
    for t in per.values():
        tot.update(t)
    print(f"genes with types: {hit}/{len(spec['genes'])}; totals {dict(tot.most_common())}")


if __name__ == "__main__":
    main()
