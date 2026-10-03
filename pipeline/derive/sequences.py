"""Reference sequences (MANE Select) for every deep-atlas gene, plus 3 SYNTHETIC example FASTA files.

Run:  python3 pipeline/derive/sequences.py [--refresh]
In:   data/graph.json (disease:<GENE> nodes), data/derived/variants.json (ClinVar P/LP variants),
      Ensembl REST (rest.ensembl.org; responses cached in data/raw/downloads/ensembl_seq/)
Out:  data/derived/sequences/<GENE>.json, index.json, examples/*.fasta (schema: sequences/README.md)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

from dcommon import DERIVED, DOWNLOADS, TODAY, Graph, read_json, write_json

OUT = DERIVED / "sequences"
CACHE = DOWNLOADS / "ensembl_seq"
REST = "https://rest.ensembl.org"
REFRESH = "--refresh" in sys.argv
COMP = str.maketrans("ACGTN", "TGCAN")


REST37 = "https://grch37.rest.ensembl.org"


def get(path, accept="application/json", base=REST):
    tag = "" if base == REST else "grch37_"
    key = CACHE / (tag + re.sub(r"[^A-Za-z0-9]+", "_", path) + (".json" if "json" in accept else ".txt"))
    if key.exists() and not REFRESH:
        return key.read_text()
    for attempt in range(6):
        req = urllib.request.Request(base + path, headers={"Content-Type": accept, "Accept": accept,
                                                           "User-Agent": "rare-disease-atlas/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode()
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                continue
            raise
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(body)
    time.sleep(0.1)  # Ensembl asks for <= 15 requests/s
    return body


def exon_table(tx):
    strand = tx["strand"]
    tl_start, tl_end = tx["Translation"]["start"], tx["Translation"]["end"]
    exons = sorted(tx["Exon"], key=lambda e: e["start"] * strand)
    pos, out = 0, []
    for n, e in enumerate(exons, 1):
        s, t = max(e["start"], tl_start), min(e["end"], tl_end)
        rec = {"number": n, "id": e["id"], "chrom": tx["seq_region_name"], "start": e["start"], "end": e["end"],
               "strand": strand}
        if s <= t:
            rec.update({"cds_start": pos + 1, "cds_end": pos + t - s + 1,
                        "coding_genomic_start": s, "coding_genomic_end": t})
            pos += t - s + 1
        else:
            rec.update({"cds_start": None, "cds_end": None, "note": "non-coding (UTR-only) exon"})
        out.append(rec)
    return out, pos


def grch37(tx_id, cds_len):
    """Same transcript on GRCh37 (grch37.rest.ensembl.org). Kept only if the CDS length matches."""
    try:
        t = json.loads(get(f"/lookup/id/{tx_id}?expand=1", base=REST37))
    except Exception as ex:  # noqa: BLE001
        return {"available": False, "note": f"GRCh37 lookup failed: {ex}"}
    if "Translation" not in t:
        return {"available": False, "note": "no translation on GRCh37"}
    ex, ln = exon_table(t)
    if ln != cds_len:
        return {"available": False, "note": f"GRCh37 version {t.get('version')} has CDS {ln} bp, not {cds_len}; "
                                            "not used to avoid wrong c. mapping"}
    return {"available": True, "transcript": f"{t['id']}.{t.get('version')}", "chrom": t["seq_region_name"],
            "strand": t["strand"], "exons": ex}


def map_exons_to_37(exons):
    """Fallback: project each GRCh38 exon with Ensembl /map (assembly mapping). Kept only if every exon
    maps as one block of identical length on the same chromosome."""
    out = []
    for e in exons:
        r = json.loads(get(f"/map/human/GRCh38/{e['chrom']}:{e['start']}..{e['end']}:{e['strand']}/GRCh37"))
        m = r.get("mappings", [])
        if len(m) != 1 or (m[0]["mapped"]["end"] - m[0]["mapped"]["start"]) != (e["end"] - e["start"]):
            return None
        d = m[0]["mapped"]
        shift = d["start"] - e["start"] if d["strand"] == e["strand"] else None
        if shift is None:
            return None
        x = dict(e, chrom=d["seq_region_name"], start=d["start"], end=d["end"])
        if e.get("coding_genomic_start"):
            x["coding_genomic_start"] = e["coding_genomic_start"] + shift
            x["coding_genomic_end"] = e["coding_genomic_end"] + shift
        out.append(x)
    return out


def build(gene):
    look = json.loads(get(f"/lookup/symbol/homo_sapiens/{gene}?expand=1;mane=1"))
    tx = next((t for t in look["Transcript"] if any(m.get("type") == "MANE_Select" for m in t.get("MANE", []))), None)
    if not tx:
        return None
    mane = next(m for m in tx["MANE"] if m["type"] == "MANE_Select")
    cds = get(f"/sequence/id/{tx['id']}?type=cds", "text/plain").strip()
    prot = get(f"/sequence/id/{tx['id']}?type=protein", "text/plain").strip()
    strand = tx["strand"]
    tl_start, tl_end = tx["Translation"]["start"], tx["Translation"]["end"]
    out, pos = exon_table(tx)
    assert pos == len(cds), (gene, pos, len(cds))
    g37 = grch37(tx["id"], len(cds))
    if not g37["available"]:
        mapped = map_exons_to_37(out)
        g37 = ({"available": True, "transcript": None, "chrom": mapped[0]["chrom"], "strand": strand,
                "exons": mapped, "method": "GRCh38 exons projected with Ensembl /map (no matching GRCh37 transcript: "
                                           + g37["note"] + ")"} if mapped else dict(g37, method="none"))
    else:
        g37["method"] = "same Ensembl transcript on grch37.rest.ensembl.org"
    assert len(cds) == 3 * (len(prot) + 1) or len(cds) == 3 * len(prot), (gene, len(cds), len(prot))
    return {"gene": gene, "assembly": "GRCh38", "ensembl_gene": look["id"], "transcript": f"{tx['id']}.{tx['version']}",
            "refseq": mane.get("refseq_match"), "mane": "MANE_Select", "strand": strand,
            "chrom": tx["seq_region_name"], "cds_length": len(cds), "protein_length": len(prot),
            "exons": out, "grch37": g37, "cds": cds, "protein": prot,
            "source": f"{REST}/lookup/id/{tx['id']}", "retrieved": TODAY}


def clinvar_missense(gene, ref_nm):
    """Best-reviewed ClinVar pathogenic missense SNV on the MANE RefSeq transcript (same P/LP query as
    pipeline/biology/clinvar.py). Responses cached in data/raw/downloads/clinvar_<gene>_*.json."""
    from dcommon import eutils
    es_path, sm_path = DOWNLOADS / f"clinvar_{gene}_esearch.json", DOWNLOADS / f"clinvar_{gene}_esummary.json"
    if not es_path.exists() or REFRESH:
        es_path.write_text(eutils("esearch.fcgi", {"db": "clinvar", "retmode": "json", "retmax": 200,
                                                   "term": f"{gene}[gene] AND clinsig_pathogenic[prop]"}).decode())
    ids = json.loads(es_path.read_text())["esearchresult"]["idlist"]
    if not sm_path.exists() or REFRESH:
        sm_path.write_text(eutils("esummary.fcgi", {"db": "clinvar", "retmode": "json",
                                                    "id": ",".join(ids)}).decode())
    res = json.loads(sm_path.read_text())["result"]
    rank = {"practice guideline": 4, "reviewed by expert panel": 3,
            "criteria provided, multiple submitters, no conflicts": 2}
    best = None
    for u in res["uids"]:
        d = res[u]
        gc = d.get("germline_classification") or {}
        if gc.get("description") != "Pathogenic" or "missense variant" not in d.get("molecular_consequence_list", []):
            continue
        if not d["title"].startswith(ref_nm) or not re.search(r"c\.\d+[ACGT]>[ACGT] \(p\.", d["title"]):
            continue
        score = (rank.get(gc.get("review_status"), 0), len((d.get("supporting_submissions") or {}).get("scv") or []))
        if best is None or score > best[0]:
            best = (score, {"hgvs": d["title"], "accession": d["accession"], "classification": gc["description"],
                            "review": gc.get("review_status")})
    return best[1]


def c_to_genomic(exons, c_pos):
    """c. position (coding, 1-based) -> genomic position, using the cds_start/coding_genomic_* table."""
    for e in exons:
        if e.get("cds_start") and e["cds_start"] <= c_pos <= e["cds_end"]:
            off = c_pos - e["cds_start"]
            return e["coding_genomic_start"] + off if e["strand"] == 1 else e["coding_genomic_end"] - off
    raise ValueError(c_pos)


def vcf_examples(stx):
    """Two SYNTHETIC VCFs (GRCh38, GRCh37) carrying STXBP1 c.1162C>T, cross-checked against ClinVar."""
    vp = read_json(DERIVED / "variant_positions.json")["variants"]["VCV000006730"]
    hdr_note = "##comment=SYNTHETIC EXAMPLE – not a real person. Built from the reference genome and ClinVar VCV000006730 for testing the atlas variant checker."
    out = []
    for asm, exons, base, ref_url in (
            ("GRCh38", stx["exons"], REST, "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/"),
            ("GRCh37", stx["grch37"]["exons"], REST37, "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.1_GRCh37/")):
        chrom = exons[0]["chrom"]
        pos = c_to_genomic(exons, 1162)
        cv = vp["grch38" if asm == "GRCh38" else "grch37"].split(":")
        assert int(cv[1]) == pos, (asm, pos, cv)          # exon table and ClinVar agree
        refb = get(f"/sequence/region/human/{chrom}:{pos}..{pos}:1", "text/plain", base=base).strip()
        assert refb == cv[2] == "C", (asm, refb, cv)
        length = json.loads(get(f"/info/assembly/homo_sapiens/{chrom}", base=base))["length"]
        lines = ["##fileformat=VCFv4.2", f"##fileDate={TODAY.replace('-', '')}", hdr_note,
                 f"##reference={asm} ({ref_url})", f"##contig=<ID={chrom},length={length},assembly={asm}>",
                 '##INFO=<ID=GENE,Number=1,Type=String,Description="Gene symbol">',
                 '##INFO=<ID=NOTE,Number=1,Type=String,Description="Why this synthetic line is here">',
                 '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
                 "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSYNTHETIC_EXAMPLE"]
        lines.append(f"{chrom}\t{pos}\t.\tC\tT\t50\tPASS\tGENE=STXBP1;NOTE=STXBP1_c.1162C>T_p.Arg388Ter_ClinVar_VCV000006730\tGT\t0/1")
        if asm == "GRCh38":   # benign-looking off-target line: deep in STXBP1 intron 1, 2,000 bp after exon 1
            opos = exons[0]["end"] + 2000
            ob = get(f"/sequence/region/human/{chrom}:{opos}..{opos}:1", "text/plain", base=base).strip()
            alt = {"A": "G", "G": "A", "C": "T", "T": "C"}[ob]
            allkeys = read_json(DERIVED / "variant_positions.json")["keys"]
            assert f"GRCh38:{chrom}:{opos}:{ob}:{alt}" not in allkeys and \
                not any(k.startswith(f"POS:GRCh38:{chrom}:{opos}-") for k in allkeys)
            lines.append(f"{chrom}\t{opos}\t.\t{ob}\t{alt}\t50\tPASS\tGENE=STXBP1;NOTE=synthetic_intronic_off_target_not_in_atlas_ClinVar_PLP_set\tGT\t0/1")
            lines.sort(key=lambda l: (not l.startswith("#"), int(l.split("\t")[1]) if not l.startswith("#") else 0))
        fn = f"STXBP1_c.1162C>T_{asm}.vcf"
        (OUT / "examples" / fn).write_text("\n".join(lines) + "\n")
        out.append(fn)
    return out


def wrap(s, n=60):
    return "\n".join(s[i:i + n] for i in range(0, len(s), n))


def edit(cds, c_notation):
    m = re.fullmatch(r"c\.(\d+)([ACGT])>([ACGT])", c_notation)
    pos, ref, alt = int(m.group(1)), m.group(2), m.group(3)
    assert cds[pos - 1] == ref, f"reference mismatch at {c_notation}: CDS has {cds[pos - 1]}"
    return cds[:pos - 1] + alt + cds[pos:]


def main():
    g = Graph()
    genes = sorted(n["id"].split(":", 1)[1] for n in g.nodes.values()
                   if n["type"] == "disease" and n["id"].startswith("disease:"))
    index, sizes = [], {}
    for gene in genes:
        rec = build(gene)
        if not rec:
            print(f"  ! no MANE Select for {gene}")
            continue
        sizes[gene] = write_json(OUT / f"{gene}.json", rec)
        index.append({k: rec[k] for k in ("gene", "transcript", "refseq", "chrom", "strand", "cds_length",
                                          "protein_length")} | {"n_exons": len(rec["exons"]), "file": f"{gene}.json"})
    write_json(OUT / "index.json", {"generated": TODAY, "assembly": "GRCh38", "transcript_set": "MANE Select",
                                    "source": "Ensembl REST", "genes": index})
    # ---- synthetic examples
    v = read_json(DERIVED / "variants.json")
    F = v["fields"]

    def find(gene, pred):
        for row in v["genes"][gene]["variants"]:
            r = dict(zip(F, row))
            if pred(r):
                return r
    ex_dir = OUT / "examples"
    ex_dir.mkdir(parents=True, exist_ok=True)
    stx = read_json(OUT / "STXBP1.json")
    scn = read_json(OUT / "SCN2A.json") if (OUT / "SCN2A.json").exists() else None
    hdr = "SYNTHETIC EXAMPLE – not a real person"
    r1 = find("STXBP1", lambda r: "c.1162C>T" in r["hgvs"])
    tx1 = r1["hgvs"].split("(")[0]
    examples = [("STXBP1_reference_no_change.fasta",
                 f">{hdr} | STXBP1 {stx['transcript']} ({stx['refseq']}) CDS | no change from reference",
                 stx["cds"])]
    assert tx1.split(".")[0] == stx["refseq"].split(".")[0], (tx1, stx["refseq"])
    examples.append(("STXBP1_c.1162C>T_p.Arg388Ter.fasta",
                     f">{hdr} | STXBP1 {stx['transcript']} ({stx['refseq']}) CDS | c.1162C>T p.Arg388Ter | "
                     f"ClinVar {r1['accession']} ({r1['classification']})", edit(stx["cds"], "c.1162C>T")))
    if scn:
        ref_nm = scn["refseq"].split(".")[0]
        r2 = find("SCN2A", lambda r: r["consequence"] == "missense" and r["hgvs"].startswith(ref_nm)
                  and re.search(r"c\.\d+[ACGT]>[ACGT]", r["hgvs"])) if "SCN2A" in v["genes"] else None
        if r2 is None:   # variants.json covers only the 11 SNARE-slice genes: use ClinVar directly (cached)
            r2 = clinvar_missense("SCN2A", ref_nm)
        c2 = re.search(r"c\.\d+[ACGT]>[ACGT]", r2["hgvs"]).group(0)
        p2 = re.search(r"\(p\.[^)]+\)", r2["hgvs"]).group(0)[1:-1]
        examples.append((f"SCN2A_{c2}_{p2}.fasta",
                         f">{hdr} | SCN2A {scn['transcript']} ({scn['refseq']}) CDS | {c2} {p2} | "
                         f"ClinVar {r2['accession']} ({r2['classification']})", edit(scn["cds"], c2)))
    for fn, h, seq in examples:
        (ex_dir / fn).write_text(h + "\n" + wrap(seq) + "\n")
    examples += [(fn, None, None) for fn in vcf_examples(stx)]
    print(f"[sequences] {len(index)}/{len(genes)} genes; {sum(sizes.values()) / 1024:.0f} KB; examples: "
          + ", ".join(e[0] for e in examples))


if __name__ == "__main__":
    main()
