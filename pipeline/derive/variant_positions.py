"""Genomic positions for every variant in data/derived/variants.json -> data/derived/variant_positions.json

Run:  python3 pipeline/derive/variant_positions.py      (stdlib, offline: reads the stored ClinVar esummary)
Keys (all point to lists of ClinVar accessions in variants.json):
  "GRCh38:<chr>:<pos>:<ref>:<alt>"   exact, VCF-style, for substitutions (SNV/MNV) from the canonical SPDI
  "GRCh37:<chr>:<pos>:<ref>:<alt>"   exact, for substitutions: GRCh37 position from ClinVar's variation_loc,
                                     ref/alt from ClinVar where given, else from the GRCh38 SPDI (same bases)
  "SPDI:GRCh38:<chr>:<pos0>:<del>:<ins>"  indels, ClinVar canonical SPDI (0-based, no anchor base)
  "POS:GRCh38:<chr>:<start>-<stop>" and "POS:GRCh37:<chr>:<start>-<stop>"  position-level fallback
See data/derived/sequences/README.md ("Reading a VCF") for how the UI normalises a VCF line to these keys.
"""
from __future__ import annotations

import glob
from collections import defaultdict

from dcommon import BIO_RAW, DERIVED, TODAY, read_json, write_json

COMP = str.maketrans("ACGTN", "TGCAN")


def main():
    v = read_json(DERIVED / "variants.json")
    wanted = {row[0] for g in v["genes"].values() for row in g["variants"]}
    keys = defaultdict(set)
    per = {}
    for f in sorted(glob.glob(str(BIO_RAW / "clinvar" / "*_esummary_*.json"))):
        res = read_json(f)["result"]
        for u in res["uids"]:
            d = res[u]
            acc = d.get("accession")
            if acc not in wanted or acc in per:
                continue
            rec = {"accession": acc}
            for vs in d.get("variation_set", []):
                spdi = vs.get("canonical_spdi") or ""
                locs = {l["assembly_name"]: l for l in vs.get("variation_loc", []) if l.get("assembly_name")}
                l38, l37 = locs.get("GRCh38"), locs.get("GRCh37")
                if spdi:
                    seq_id, p0, dl, ins = spdi.split(":")
                    chrom = (l38 or {}).get("chr")
                    rec["spdi"] = spdi
                    if chrom:
                        if dl and ins and len(dl) == len(ins):            # substitution
                            keys[f"GRCh38:{chrom}:{int(p0) + 1}:{dl}:{ins}"].add(acc)
                            rec["grch38"] = f"{chrom}:{int(p0) + 1}:{dl}:{ins}"
                            if l37 and l37.get("start") and int(l37["start"]) and \
                                    int(l37["stop"]) - int(l37["start"]) + 1 == len(dl):
                                ref37, alt37 = l37.get("ref") or dl, l37.get("alt") or ins
                                keys[f"GRCh37:{l37['chr']}:{l37['start']}:{ref37}:{alt37}"].add(acc)
                                rec["grch37"] = f"{l37['chr']}:{l37['start']}:{ref37}:{alt37}"
                                if not l37.get("ref"):
                                    rec["grch37_ref_alt_from"] = "GRCh38 SPDI"
                        else:
                            keys[f"SPDI:GRCh38:{chrom}:{p0}:{dl}:{ins}"].add(acc)
                for asm, l in (("GRCh38", l38), ("GRCh37", l37)):
                    if l and l.get("start") and l.get("stop"):
                        keys[f"POS:{asm}:{l['chr']}:{l['start']}-{l['stop']}"].add(acc)
                        rec[f"{asm.lower()}_span"] = f"{l['chr']}:{l['start']}-{l['stop']}"
            per[acc] = rec
    out = {
        "generated": TODAY,
        "source": "stored ClinVar esummary records (data/raw/biology/clinvar/), variation_set[].variation_loc "
                  "and canonical_spdi",
        "key_types": {
            "GRCh38:chr:pos:ref:alt": "exact substitution, VCF-style (1-based)",
            "GRCh37:chr:pos:ref:alt": "exact substitution on GRCh37",
            "SPDI:GRCh38:chr:pos0:del:ins": "indel in ClinVar canonical SPDI form (0-based, no anchor base)",
            "POS:assembly:chr:start-stop": "position-level fallback: the variant's span, any change",
        },
        "counts": {"variants": len(wanted), "with_any_key": sum(1 for a in per if len(per[a]) > 1),
                   "exact_grch38": sum(1 for r in per.values() if "grch38" in r),
                   "exact_grch37": sum(1 for r in per.values() if "grch37" in r),
                   "keys": len(keys)},
        "keys": {k: sorted(a) for k, a in sorted(keys.items())},
        "variants": per,
    }
    size = write_json(DERIVED / "variant_positions.json", out, compact=True)
    print(f"[variant_positions] {out['counts']} ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
