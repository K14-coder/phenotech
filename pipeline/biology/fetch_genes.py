"""Task 1: gene records from HGNC REST, UniProt REST and Ensembl REST.

Run:  python3 pipeline/biology/fetch_genes.py [--refresh]
Out:  data/raw/biology/hgnc/<SYMBOL>.json, uniprot/<SYMBOL>.json, ensembl/<ENST>.json
      data/raw/biology/genes.json  (normalised records used by build_biology.py)
"""
from __future__ import annotations

import sys

from common import ALL_GENES, RAW, cached_json, write_json

REFRESH = "--refresh" in sys.argv

# Common protein names / colloquial synonyms (added on top of HGNC aliases).
# These are standard protein names; UniProt alternative names are merged in too.
PROTEIN_SYNONYMS = {
    "STXBP1": ["Munc18-1", "Munc18a", "nSec1", "rbSec1"],
    "SYT1": ["synaptotagmin-1", "Syt1"],
    "SNAP25": ["SNAP-25", "synaptosomal-associated protein 25"],
    "VAMP2": ["synaptobrevin-2", "VAMP-2"],
    "STX1B": ["syntaxin-1B"],
    "SYT2": ["synaptotagmin-2"],
    "CPLX1": ["complexin-1"],
    "UNC13A": ["Munc13-1"],
    "STX1A": ["syntaxin-1A", "HPC-1"],
    "NSF": ["N-ethylmaleimide-sensitive factor", "vesicle-fusing ATPase"],
    "SLC6A1": ["GAT-1", "GAT1", "GABA transporter 1"],
}


def hgnc(symbol: str) -> dict:
    obj = cached_json(RAW / "hgnc" / f"{symbol}.json",
                      f"https://rest.genenames.org/fetch/symbol/{symbol}",
                      headers={"Accept": "application/json"}, refresh=REFRESH)
    docs = obj["response"]["docs"]
    assert len(docs) == 1, f"HGNC returned {len(docs)} docs for {symbol}"
    return docs[0]


def uniprot(symbol: str) -> dict | None:
    obj = cached_json(RAW / "uniprot" / f"{symbol}.json",
                      "https://rest.uniprot.org/uniprotkb/search",
                      params={"query": f"gene_exact:{symbol} AND organism_id:9606 AND reviewed:true",
                              "format": "json"},
                      refresh=REFRESH)
    res = obj.get("results", [])
    # gene_exact also matches aliases (e.g. "RIT1" is an alias of BCL11B): require the entry's PRIMARY gene name
    # to be the HGNC symbol.
    primary = [r for r in res if any((g.get("geneName") or {}).get("value") == symbol for g in r.get("genes", []))]
    if not primary:
        print(f"  ! no UniProt entry with primary gene name {symbol} (results: "
              f"{[r['primaryAccession'] for r in res]})")
        return None
    return primary[0]


def ensembl_cds(enst: str) -> dict | None:
    enst = enst.split(".")[0]
    try:
        return cached_json(RAW / "ensembl" / f"{enst}.cds.json",
                           f"https://rest.ensembl.org/sequence/id/{enst}",
                           params={"type": "cds"}, headers={"Content-Type": "application/json",
                                                            "Accept": "application/json"},
                           refresh=REFRESH)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Ensembl CDS fetch failed for {enst}: {e}")
        return None


def uniprot_function(entry: dict) -> str | None:
    for c in entry.get("comments", []):
        if c.get("commentType") == "FUNCTION":
            texts = c.get("texts", [])
            if texts:
                return texts[0]["value"]
    return None


def uniprot_names(entry: dict) -> tuple[str | None, list[str]]:
    pd = entry.get("proteinDescription", {})
    rec = pd.get("recommendedName", {}).get("fullName", {}).get("value")
    alts = []
    for a in pd.get("alternativeNames", []) or []:
        v = a.get("fullName", {}).get("value")
        if v:
            alts.append(v)
        for s in a.get("shortNames", []) or []:
            alts.append(s.get("value"))
    for s in pd.get("recommendedName", {}).get("shortNames", []) or []:
        alts.append(s.get("value"))
    return rec, [x for x in alts if x]


def main() -> None:
    out = {}
    for sym in ALL_GENES:
        print(f"[genes] {sym}")
        h = hgnc(sym)
        u = uniprot(sym)
        rec = {
            "symbol": h["symbol"],
            "hgnc_id": h["hgnc_id"],
            "name": h["name"],
            "alias_symbol": h.get("alias_symbol", []),
            "prev_symbol": h.get("prev_symbol", []),
            "entrez_id": h.get("entrez_id"),
            "omim_id": h.get("omim_id", []),
            "ensembl_gene_id": h.get("ensembl_gene_id"),
            "uniprot_ids_hgnc": h.get("uniprot_ids", []),
            "mane_select": h.get("mane_select", []),
            "hgnc_url": f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{h['hgnc_id']}",
        }
        if u:
            rec_name, alts = uniprot_names(u)
            rec.update({
                "uniprot_acc": u["primaryAccession"],
                "uniprot_entry": u.get("uniProtkbId"),
                "protein_name": rec_name,
                "protein_alt_names": alts,
                "protein_length_aa": u.get("sequence", {}).get("length"),
                "uniprot_function": uniprot_function(u),
                "uniprot_url": f"https://www.uniprot.org/uniprotkb/{u['primaryAccession']}/entry",
            })
        # CDS length from the MANE Select Ensembl transcript
        enst = next((m for m in rec["mane_select"] if m.startswith("ENST")), None)
        if enst:
            cds = ensembl_cds(enst)
            if cds and cds.get("seq"):
                seq = cds["seq"]
                rec["mane_enst"] = enst
                rec["cds_length_bp"] = len(seq)
                rec["cds_includes_stop"] = seq[-3:].upper() in ("TAA", "TAG", "TGA")
                rec["ensembl_cds_url"] = f"https://rest.ensembl.org/sequence/id/{enst.split('.')[0]}?type=cds"
        rec["protein_synonyms_curated"] = PROTEIN_SYNONYMS.get(sym, [])
        out[sym] = rec
        print(f"   {rec['hgnc_id']} OMIM={rec['omim_id']} aa={rec.get('protein_length_aa')} "
              f"cds={rec.get('cds_length_bp')} acc={rec.get('uniprot_acc')}")
    write_json(RAW / "genes.json", out)
    print(f"wrote {RAW / 'genes.json'}")


if __name__ == "__main__":
    main()
