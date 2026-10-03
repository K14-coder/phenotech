"""ClinVar pathogenic / likely-pathogenic variant spectrum per lysosomal gene (NCBI E-utilities).

Same method as pipeline/biology/clinvar.py (whose classifier is reused): esearch + esummary,
classified by molecular_consequence_list; multi-gene CNVs kept separate from single-gene changes.
NCBI etiquette: shared cross-process <= 2 req/s throttle, tool=rare-disease-atlas, no email, backoff.
Run:  python3 pipeline/families/lysosomal/clinvar.py [--refresh]
Out:  data/raw/families/lysosomal/clinvar/<GENE>_esearch.json, <GENE>_esummary_<n>.json
      data/raw/families/lysosomal/clinvar_summary.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from lyso_common import GENES, RAW, eutils, read_json, write_json

REFRESH = "--refresh" in sys.argv
OUT = RAW / "clinvar"
OUT.mkdir(parents=True, exist_ok=True)
BATCH = 200
REVIEW_RANK = {"practice guideline": 4, "reviewed by expert panel": 3,
               "criteria provided, multiple submitters, no conflicts": 2,
               "criteria provided, single submitter": 1}

# consequence classifier copied verbatim from pipeline/biology/clinvar.py (same classes as the SNARE layer)
def classify(doc: dict, sym: str) -> str:
    otype = (doc.get("obj_type") or "").lower()
    genes = [g.get("symbol") for g in doc.get("genes", []) or []]
    mcs = [m.lower() for m in doc.get("molecular_consequence_list", []) or []]
    if "copy number" in otype or (otype in ("deletion", "duplication") and len(genes) > 1):
        return "cnv_multigene" if len(genes) != 1 else "cnv_single_gene"
    if len(genes) > 1 and otype in ("deletion", "duplication", "complex", "inversion", "translocation"):
        return "cnv_multigene"
    if any("nonsense" in m for m in mcs):
        return "nonsense"
    if any("frameshift" in m for m in mcs):
        return "frameshift"
    if any(("splice donor" in m) or ("splice acceptor" in m) for m in mcs):
        return "splice"
    if any(("initiator codon" in m) or ("start lost" in m) or ("initiatior" in m) for m in mcs):
        return "start_lost"
    if any("stop lost" in m for m in mcs):
        return "stop_lost"
    if any("missense" in m for m in mcs):
        return "missense"
    if any(("inframe" in m) for m in mcs):
        return "inframe_indel"
    if any("synonymous" in m for m in mcs):
        return "synonymous"
    if any("intron" in m for m in mcs):
        return "intronic_or_splice_region"
    if any("utr" in m for m in mcs):
        return "utr"
    if otype in ("deletion", "duplication") and len(genes) == 1:
        return "intragenic_deletion_or_duplication"
    return "other_or_unannotated"



def esearch(sym: str) -> dict:
    path = OUT / f"{sym}_esearch.json"
    if path.exists() and not REFRESH:
        return read_json(path)
    term = f"{sym}[gene] AND (clinsig_pathogenic[prop] OR clinsig_likely_pathogenic[prop])"
    obj = json.loads(eutils("esearch.fcgi", {"db": "clinvar", "term": term, "retmax": 10000, "retmode": "json"}))
    obj["_query"] = term
    write_json(path, obj)
    return obj


def esummary(sym: str, ids: list[str]) -> list[dict]:
    docs = []
    for i in range(0, len(ids), BATCH):
        n = i // BATCH
        path = OUT / f"{sym}_esummary_{n}.json"
        if path.exists() and not REFRESH:
            obj = read_json(path)
        else:
            obj = json.loads(eutils("esummary.fcgi", {"db": "clinvar", "id": ",".join(ids[i:i + BATCH]),
                                                       "retmode": "json"}))
            write_json(path, obj)
        res = obj.get("result", {})
        for uid in res.get("uids", []):
            docs.append(res[uid])
    return docs


def main() -> None:
    summary = {}
    for sym in GENES:
        es = esearch(sym)
        ids = es.get("esearchresult", {}).get("idlist", [])
        count = int(es.get("esearchresult", {}).get("count", 0))
        docs = esummary(sym, ids)
        cats, examples = Counter(), {}
        for doc in docs:
            gc = doc.get("germline_classification") or {}
            desc = gc.get("description") or ""
            if "pathogenic" not in desc.lower() or "conflicting" in desc.lower():
                continue
            # a P/LP record must actually name this gene (esearch [gene] can match neighbours in large CNVs)
            c = classify(doc, sym)
            cats[c] += 1
            rank = REVIEW_RANK.get(gc.get("review_status", ""), 0)
            examples.setdefault(c, []).append((rank, doc.get("title"), doc.get("accession"), desc,
                                               gc.get("review_status")))
        ex_out = {}
        for c, lst in examples.items():
            lst.sort(key=lambda x: (-x[0], x[1] or ""))
            ex_out[c] = [{"title": t, "accession": a, "classification": d, "review_status": rs,
                          "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{a.replace('VCV', '').lstrip('0')}/"
                          if a else None} for _, t, a, d, rs in lst[:4]]
        summary[sym] = {"query": es.get("_query"), "esearch_count": count, "n_docs": len(docs),
                        "n_classified_PLP": sum(cats.values()), "by_consequence": dict(cats.most_common()),
                        "examples": ex_out,
                        "clinvar_search_url": "https://www.ncbi.nlm.nih.gov/clinvar/?term=" +
                        f"{sym}%5Bgene%5D+AND+(clinsig_pathogenic%5Bprop%5D+OR+clinsig_likely_pathogenic%5Bprop%5D)"}
        print(f"[clinvar] {sym}: esearch={count} docs={len(docs)} -> {dict(cats.most_common())}", flush=True)
    write_json(RAW / "clinvar_summary.json", summary)


if __name__ == "__main__":
    main()
