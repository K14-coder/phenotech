"""gnomAD v4.1 gene constraint + AlphaMissense gene-level mean pathogenicity (stdlib only, ~10 s).

Inputs (data/raw/downloads/, gitignored):
  gnomad.v4.1.constraint_metrics.tsv
     https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/constraint/gnomad.v4.1.constraint_metrics.tsv
  AlphaMissense_gene_hg38.tsv.gz
     https://storage.googleapis.com/dm_alphamissense/AlphaMissense_gene_hg38.tsv.gz
     (same file as Zenodo record 10813168, https://zenodo.org/records/10813168)
Outputs:
  data/derived/ingest/constraint.json      gene -> [pLI, LOEUF, mis_z, lof_oe, mis_oe, transcript, flags]
  data/derived/ingest/alphamissense_gene.json   gene -> mean AlphaMissense pathogenicity

Transcript choice for constraint, per gene symbol: the Ensembl (ENST) MANE Select row; else the
Ensembl canonical row; else the RefSeq MANE Select row. AlphaMissense's gene file is keyed by Ensembl
transcript (it scores one transcript per gene); the ENST -> symbol map comes from the gnomAD table
(all transcripts, version stripped). Where a symbol has several AlphaMissense transcripts, the one
that is gnomAD's MANE/canonical transcript is preferred.

    python3 pipeline/ingest/constraint_alphamissense.py
"""
from __future__ import annotations

import gzip
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DL = ROOT / "data/raw/downloads"
OUT = ROOT / "data/derived/ingest"


def fnum(x, nd=4):
    try:
        v = float(x)
    except ValueError:
        return None
    if v != v:
        return None
    return round(v, nd)


def hgnc_maps():
    """ENSG -> current HGNC symbol, and previous symbol -> current (unique only). gnomAD v4.1 uses
    GENCODE v39 names (e.g. GBA, not GBA1); our atlas uses current HGNC symbols."""
    ens, prev, seen = {}, {}, {}
    p = DL / "hgnc_complete_set.txt"
    if not p.exists():
        return ens, prev
    with open(p) as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        ix = {h: i for i, h in enumerate(hdr)}
        for line in fh:
            r = line.rstrip("\n").split("\t")
            if r[ix["status"]] != "Approved":
                continue
            sym = r[ix["symbol"]]
            e = r[ix["ensembl_gene_id"]] if len(r) > ix["ensembl_gene_id"] else ""
            if e:
                ens[e] = sym
            for ps in r[ix["prev_symbol"]].strip('"').split("|"):
                if ps:
                    seen[ps] = seen.get(ps, 0) + 1
                    prev[ps] = sym
    prev = {k: v for k, v in prev.items() if seen[k] == 1}
    return ens, prev


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ens2sym, prev2sym = hgnc_maps()
    approved = set(ens2sym.values())
    renamed = {}
    best = {}            # symbol -> (rank, row)
    enst2sym = {}
    pref_tx = {}         # symbol -> preferred ENST
    with open(DL / "gnomad.v4.1.constraint_metrics.tsv") as fh:
        hdr = fh.readline().rstrip("\n").split("\t")
        ix = {h: i for i, h in enumerate(hdr)}
        for line in fh:
            r = line.rstrip("\n").split("\t")
            g, tx = r[ix["gene"]], r[ix["transcript"]]
            gid = r[ix["gene_id"]]
            cur = ens2sym.get(gid) or (prev2sym.get(g) if g not in approved else None)
            if cur and cur != g:
                renamed[g] = cur
                g = cur
            elif g in renamed:
                g = renamed[g]
            if tx.startswith("ENST"):
                enst2sym.setdefault(tx.split(".")[0], g)
            mane = r[ix["mane_select"]] == "true"
            canon = r[ix["canonical"]] == "true"
            if tx.startswith("ENST") and mane:
                rank = 0
            elif tx.startswith("ENST") and canon:
                rank = 1
            elif mane:
                rank = 2
            else:
                continue
            if g not in best or rank < best[g][0]:
                best[g] = (rank, r)
            if tx.startswith("ENST") and rank <= 1 and (g not in pref_tx or rank == 0):
                pref_tx[g] = tx.split(".")[0]
    genes = {}
    for g, (rank, r) in best.items():
        genes[g] = [fnum(r[ix["lof.pLI"]]), fnum(r[ix["lof.oe_ci.upper"]], 3), fnum(r[ix["mis.z_score"]], 3),
                    fnum(r[ix["lof.oe"]], 3), fnum(r[ix["mis.oe"]], 3), r[ix["transcript"]],
                    r[ix["constraint_flags"]] if r[ix["constraint_flags"]] not in ("[]", "NA", "") else ""]
    n_pli = sum(1 for v in genes.values() if v[0] is not None)
    (OUT / "constraint.json").write_text(json.dumps({
        "source": "gnomAD v4.1 constraint metrics, https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/constraint/gnomad.v4.1.constraint_metrics.tsv",
        "licence": "gnomAD data: CC0 1.0 (no restrictions)",
        "f": ["pLI", "LOEUF", "mis_z", "lof_oe", "mis_oe", "transcript", "flags"],
        "transcript_rule": "Ensembl MANE Select, else Ensembl canonical, else RefSeq MANE Select",
        "symbol_rule": "gnomAD gene symbols re-keyed to the current HGNC approved symbol via HGNC ensembl_gene_id (RefSeq rows via the same gnomAD symbol, or a unique HGNC previous symbol), e.g. GBA -> GBA1",
        "renamed_symbols": len(renamed),
        "haploinsufficiency_hint": "pLI >= 0.9 or LOEUF < 0.6 suggests intolerance to loss of function (supports haploinsufficiency for dominant disease); it is a population signal, not a disease mechanism call",
        "counts": {"genes": len(genes), "with_pLI": n_pli,
                   "pLI_ge_0.9": sum(1 for v in genes.values() if v[0] is not None and v[0] >= 0.9),
                   "LOEUF_lt_0.6": sum(1 for v in genes.values() if v[1] is not None and v[1] < 0.6)},
        "genes": dict(sorted(genes.items()))}, separators=(",", ":")))

    am = {}
    unmapped = 0
    total = 0
    with gzip.open(DL / "AlphaMissense_gene_hg38.tsv.gz", "rt") as fh:
        for line in fh:
            if line.startswith("#") or line.startswith("transcript_id"):
                continue
            tx, v = line.rstrip("\n").split("\t")
            total += 1
            t0 = tx.split(".")[0]
            g = enst2sym.get(t0)
            if not g:
                unmapped += 1
                continue
            preferred = pref_tx.get(g) == t0
            if g not in am or (preferred and not am[g][2]):
                am[g] = [round(float(v), 4), tx, preferred]
    (OUT / "alphamissense_gene.json").write_text(json.dumps({
        "source": "AlphaMissense_gene_hg38.tsv.gz (Cheng et al., Science 2023), https://zenodo.org/records/10813168 ; mirror https://storage.googleapis.com/dm_alphamissense/AlphaMissense_gene_hg38.tsv.gz",
        "licence": "Zenodo record 10813168 metadata: CC BY 4.0. The file header still reads 'Licensed under CC BY-NC-SA 4.0' (the 2023 terms); see data/derived/ingest/README.md",
        "f": ["mean_am_pathogenicity", "transcript", "is_gnomad_mane_or_canonical"],
        "note": "mean predicted pathogenicity over all possible missense substitutions in the transcript; higher = missense changes more often damaging (structural/functional intolerance)",
        "counts": {"transcripts_in_file": total, "genes": len(am), "unmapped_transcripts": unmapped},
        "genes": dict(sorted(am.items()))}, separators=(",", ":")))
    print("constraint genes", len(genes), "with pLI", n_pli, "| AlphaMissense genes", len(am), "of", total, "unmapped", unmapped)


if __name__ == "__main__":
    main()
