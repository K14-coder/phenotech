"""Full ClinVar P/LP ingest for every gene (stdlib only, ~3-5 min).

Input : data/raw/downloads/variant_summary.txt.gz
        https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz
Output: data/derived/ingest/clinvar/<bucket>.json   (bucket = djb2(gene symbol) % 64)
        data/derived/ingest/clinvar_gene_spectrum.json
        data/derived/ingest/clinvar_meta.json

Kept rows: Assembly GRCh38 or GRCh37 and germline classification (column ClinicalSignificance)
exactly "Pathogenic", "Likely pathogenic" or "Pathogenic/Likely pathogenic". The two assembly rows of
one VariationID are merged into one record. See data/derived/ingest/README.md for the schema.

    python3 pipeline/ingest/clinvar_full.py
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import re
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "data/raw/downloads/variant_summary.txt.gz"
OUT = ROOT / "data/derived/ingest"
NB = 64
KEEP = {"Pathogenic": "P", "Likely pathogenic": "LP", "Pathogenic/Likely pathogenic": "PLP"}
STARS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, conflicting classifications": 1,
    "criteria provided, single submitter": 1,
}
DROP_PHENO = {"MedGen:C3661900", "MedGen:CN169374", "MedGen:CN517202"}  # not provided / not specified
MAX_GENES = 5          # variants listing more genes (large CNVs) are not attached to genes
MAX_ALLELE = 100       # longer VCF alleles are abbreviated (see README)

TYPE_CODE = {
    "single nucleotide variant": "snv", "Deletion": "del", "Duplication": "dup", "Insertion": "ins",
    "Indel": "indel", "copy number loss": "cnv_loss", "copy number gain": "cnv_gain",
    "Microsatellite": "str", "Inversion": "inv", "Translocation": "trans", "Complex": "complex",
    "Tandem duplication": "dup", "Variation": "other", "fusion": "fusion",
}
SPECTRUM_OF = {
    "nonsense": "nonsense", "frameshift": "frameshift",
    "splice_canonical": "splice", "splice_region": "splice",
    "missense": "missense",
    "inframe_del": "inframe", "inframe_ins": "inframe", "inframe_dup": "inframe", "inframe_delins": "inframe",
    "cnv_loss": "cnv", "cnv_gain": "cnv", "exon_cnv": "cnv",
}
SPECTRUM_KEYS = ["nonsense", "frameshift", "splice", "missense", "inframe", "cnv", "other"]

AA = "Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val|Sec|Pyl|Xaa"
RE_P = re.compile(r"\((p\.[^)]*)\)\s*$")
RE_MISSENSE = re.compile(rf"^p\.\(?({AA})(\d+)({AA})\)?$")
RE_NONSENSE = re.compile(rf"^p\.\(?({AA})(\d+)(Ter|\*)\)?$")
RE_SYN = re.compile(rf"^p\.\(?({AA})(\d+)=\)?$")
RE_START = re.compile(r"^p\.\(?Met1(\?|[A-Z][a-z]{2}|del|ext)")
RE_INTRON = re.compile(r"c\.[-*]?\d+([+-])(\d+)")
RE_HGVS = re.compile(r"^([^(:\s]+)(?:\(([^)]+)\))?:(\S+)")


def djb2(s: str) -> int:
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def bucket(sym: str) -> int:
    return djb2(sym) % NB


def consequence(name: str, vtype: str, prot: str) -> str:
    """Molecular consequence from the ClinVar Name (HGVS) and Type. Rule order matters."""
    if vtype in ("copy number loss",):
        return "cnv_loss"
    if vtype in ("copy number gain",):
        return "cnv_gain"
    if name.startswith("GRCh") or re.search(r"\)x\d", name):
        return "cnv_loss" if re.search(r"\)x[01]\b", name) else ("cnv_gain" if re.search(r"\)x[3-9]", name) else "cnv_loss")
    m = RE_HGVS.match(name)
    cpart = m.group(3) if m else name
    if prot:
        p = prot
        if "fs" in p:
            return "frameshift"
        if RE_START.match(p):
            return "start_lost"
        if "ext" in p:
            return "stop_lost"
        if RE_NONSENSE.match(p):
            return "nonsense"
        if RE_MISSENSE.match(p):
            return "missense"
        if RE_SYN.match(p) or p in ("p.=", "p.(=)"):
            # synonymous P/LP variants are nearly always splice-acting; check the c. position
            mi = RE_INTRON.search(cpart)
            return "splice_region" if mi else "synonymous"
        if re.search(r"(Ter|\*)\)?$", p) and ("delins" in p or "ins" in p or "dup" in p):
            return "nonsense"
        if "delins" in p:
            return "inframe_delins"
        if "dup" in p:
            return "inframe_dup"
        if "ins" in p:
            return "inframe_ins"
        if "del" in p:
            return "inframe_del"
        if p in ("p.0", "p.0?", "p.?"):
            return "exon_cnv" if "?" in cpart or "_" in cpart else "other"
        return "other"
    # no protein change given
    if not cpart.startswith(("c.", "m.", "n.", "g.")):
        return "repeat" if vtype == "Microsatellite" else "other"
    if cpart.startswith("m."):
        return "mitochondrial"
    if cpart.startswith("n."):
        return "noncoding"
    if "(?_" in cpart or "_?)" in cpart or re.search(r"\(\d+[+-]1_\d+-1\)", cpart):
        return "exon_cnv"     # exon-level deletion/duplication with uncertain breakpoints
    mi = RE_INTRON.search(cpart)
    if mi:
        off = int(mi.group(2))
        return "splice_canonical" if off <= 2 else ("splice_region" if off <= 8 else "intronic")
    if vtype == "Microsatellite":
        return "repeat"   # repeat expansions etc.; Microsatellite-typed indels with a p. change or splice offset are classified above
    if cpart.startswith("c.-"):
        return "utr5"
    if cpart.startswith("c.*"):
        return "utr3"
    if vtype in ("Deletion", "Duplication") and re.search(r"c\.\d+_\d+(del|dup)$", cpart):
        return "exon_cnv"
    return "other"


def vcf_key(row, ix):
    chrom, pos, ref, alt = row[ix["Chromosome"]], row[ix["PositionVCF"]], row[ix["ReferenceAlleleVCF"]], row[ix["AlternateAlleleVCF"]]
    if not pos or pos in ("-1", "na") or ref in ("na", "-", "") or alt in ("na", "-", ""):
        return ""
    if len(ref) + len(alt) > MAX_ALLELE:
        return f"{chrom}:{pos}:~{len(ref)}>{len(alt)}"
    return f"{chrom}:{pos}:{ref}:{alt}"


def main():
    t0 = time.time()
    with gzip.open(SRC, "rt", encoding="utf-8", errors="replace") as fh:
        hdr = fh.readline().lstrip("#").rstrip("\n").split("\t")
        ix = {h: i for i, h in enumerate(hdr)}
        recs: dict[int, dict] = {}
        n = kept = 0
        near = Counter()
        for line in fh:
            n += 1
            row = line.rstrip("\n").split("\t")
            cs = row[ix["ClinicalSignificance"]]
            if cs not in KEEP:
                if cs.startswith(("Pathogenic", "Likely pathogenic")):
                    near[cs] += 1
                continue
            asm = row[ix["Assembly"]]
            if asm not in ("GRCh38", "GRCh37"):
                continue
            kept += 1
            vid = int(row[ix["VariationID"]])
            r = recs.get(vid)
            if r is None:
                name = row[ix["Name"]]
                pm = RE_P.search(name)
                prot = pm.group(1) if pm else ""
                hm = RE_HGVS.match(name)
                hg = (hm.group(1), hm.group(3)) if hm else ("", name)  # (transcript, c./g. part); protein stripped
                vtype = row[ix["Type"]]
                genes = [g for g in row[ix["GeneSymbol"]].split(";") if g and g != "-"]
                ph = []
                for grp in row[ix["PhenotypeIDS"]].split("|"):
                    for x in grp.split(","):
                        x = x.strip()
                        if not x or x in DROP_PHENO:
                            continue
                        if x.startswith("MONDO:MONDO:"):
                            x = x[6:]
                        if x.startswith(("MedGen:", "OMIM:", "MONDO:")) and x not in ph:
                            ph.append(x)
                r = recs[vid] = {
                    "genes": genes, "hg": hg, "p": prot, "t": TYPE_CODE.get(vtype, "other"),
                    "mc": consequence(name, vtype, prot), "cls": KEEP[cs],
                    "st": STARS.get(row[ix["ReviewStatus"]], 0), "g38": "", "g37": "", "ph": ph,
                }
            k = vcf_key(row, ix)
            if asm == "GRCh38":
                r["g38"] = k
            else:
                r["g37"] = k
            if n % 2000000 == 0:
                print(f"  {n:,} rows, {len(recs):,} variants, {time.time()-t0:.0f}s", file=sys.stderr, flush=True)

    print(f"rows {n:,}; kept assembly rows {kept:,}; variants {len(recs):,}", file=sys.stderr)

    shards = defaultdict(dict)       # bucket -> gene -> {"ph": [...], "v": [...]}
    spectrum = defaultdict(Counter)
    mc_all = Counter()
    multi_skipped = 0
    phidx: dict[str, dict] = {}
    txidx: dict[str, dict] = {}
    for vid, r in sorted(recs.items()):
        mc_all[r["mc"]] += 1
        if not r["genes"]:
            continue
        if len(r["genes"]) > MAX_GENES:
            multi_skipped += 1
            continue
        for g in r["genes"]:
            spectrum[g][SPECTRUM_OF.get(r["mc"], "other")] += 1
            spectrum[g]["_" + r["mc"]] += 1
            ge = shards[bucket(g)].setdefault(g, {"tx": [], "ph": [], "v": []})
            txx = txidx.setdefault(g, {})
            if r["hg"][0] not in txx:
                txx[r["hg"][0]] = len(ge["tx"])
                ge["tx"].append(r["hg"][0])
            phx = phidx.setdefault(g, {})
            phi = []
            for x in r["ph"]:
                if x not in phx:
                    phx[x] = len(ge["ph"])
                    ge["ph"].append(x)
                phi.append(phx[x])
            ge["v"].append([vid, txx[r["hg"][0]], r["hg"][1], r["p"], r["t"], r["mc"], r["cls"], r["st"], r["g38"], r["g37"], phi])

    fields = ["vid", "tx", "hgvs", "protein", "type", "consequence", "class", "stars", "grch38", "grch37", "pheno"]
    (OUT / "clinvar").mkdir(parents=True, exist_ok=True)
    sizes = []
    for b in range(NB):
        genes = shards.get(b, {})
        doc = {"bucket": b, "f": fields, "g": {g: genes[g] for g in sorted(genes)}}
        p = OUT / "clinvar" / f"{b}.json"
        p.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
        sizes.append(p.stat().st_size)

    spec = {}
    for g, c in spectrum.items():
        tot = sum(c[k] for k in SPECTRUM_KEYS)
        spec[g] = {"n": tot,
                   "c": {k: c[k] for k in SPECTRUM_KEYS if c[k]},
                   "f": {k: round(c[k] / tot, 4) for k in SPECTRUM_KEYS if c[k]},
                   "detail": {k[1:]: v for k, v in sorted(c.items()) if k.startswith("_")}}
    src_date = time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(SRC)))
    meta = {
        "source": "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz",
        "source_last_modified": "2026-09-29 (HTTP Last-Modified: Tue, 29 Sep 2026 02:10:09 GMT)",
        "downloaded": src_date,
        "rows_read": n, "assembly_rows_kept": kept, "variants": len(recs),
        "variants_without_gene": sum(1 for r in recs.values() if not r["genes"]),
        "variants_over_max_genes_not_attached": multi_skipped, "max_genes": MAX_GENES,
        "genes": len(spec), "consequence_counts": dict(mc_all.most_common()),
        "near_miss_classifications_excluded": dict(near.most_common(15)),
        "with_grch38_vcf": sum(1 for r in recs.values() if r["g38"] and "~" not in r["g38"]),
        "with_grch37_vcf": sum(1 for r in recs.values() if r["g37"] and "~" not in r["g37"]),
        "shard_bytes_total": sum(sizes), "shard_bytes_max": max(sizes), "shard_bytes_min": min(sizes),
    }
    (OUT / "clinvar_gene_spectrum.json").write_text(json.dumps(
        {"source": meta["source"], "source_last_modified": meta["source_last_modified"],
         "keys": SPECTRUM_KEYS, "note": "counts of unique P/LP VariationIDs per gene; f = fraction of n; detail = fine consequence codes",
         "genes": dict(sorted(spec.items()))}, separators=(",", ":")))
    (OUT / "clinvar_meta.json").write_text(json.dumps(meta, indent=1))
    # per-gene DNA change types ("t": substitution, deletion, inversion, ...) from the shards just written
    import clinvar_types
    clinvar_types.main()
    print(json.dumps(meta, indent=1))
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
