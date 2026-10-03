"""DEE family, step 2: ClinVar pathogenic / likely-pathogenic spectrum per gene (E-utilities).

Classification logic is imported unchanged from pipeline/biology/clinvar.py (classify, GROUPS),
so both families bucket variants identically. NCBI etiquette: the shared cross-process file-lock
throttle in pipeline/biology/common.py (<= 2 req/s), tool=rare-disease-atlas, no email param,
exponential backoff on 429/5xx.

Run:  python3 pipeline/families/dee/clinvar.py [--refresh]
Out:  data/raw/families/dee/clinvar/<GENE>_esearch.json, <GENE>_esummary_<n>.json (raw)
      data/raw/families/dee/clinvar_summary.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from dee_common import GENES, RAW, eutils, read_json, write_json

sys.argv = [a for a in sys.argv]  # keep flags visible to the imported biology module
import clinvar as bio_clinvar  # noqa: E402  (pipeline/biology/clinvar.py: classify + REVIEW_RANK)

REFRESH = "--refresh" in sys.argv
OUT = RAW / "clinvar"
OUT.mkdir(parents=True, exist_ok=True)
BATCH = 200


def esearch(sym):
    path = OUT / f"{sym}_esearch.json"
    if path.exists() and not REFRESH:
        return read_json(path)
    term = f"{sym}[gene] AND (clinsig_pathogenic[prop] OR clinsig_likely_pathogenic[prop])"
    obj = json.loads(eutils("esearch.fcgi", {"db": "clinvar", "term": term, "retmax": 10000, "retmode": "json"}))
    obj["_query"] = term
    write_json(path, obj)
    return obj


def esummary(sym, ids):
    docs = []
    for i in range(0, len(ids), BATCH):
        path = OUT / f"{sym}_esummary_{i // BATCH}.json"
        if path.exists() and not REFRESH:
            obj = read_json(path)
        else:
            obj = json.loads(eutils("esummary.fcgi", {"db": "clinvar", "id": ",".join(ids[i:i + BATCH]),
                                                      "retmode": "json"}))
            write_json(path, obj)
        res = obj.get("result", {})
        docs += [res[u] for u in res.get("uids", [])]
    return docs


def protein_change(doc):
    """p. notation from the ClinVar title, e.g. 'NM_..(SCN2A):c.5645G>A (p.Arg1882Gln)' -> 'Arg1882Gln'."""
    t = doc.get("title") or ""
    if "(p." in t:
        return t.split("(p.")[1].split(")")[0]
    return None


def main():
    summary = {}
    for sym in GENES:
        es = esearch(sym)
        ids = es.get("esearchresult", {}).get("idlist", [])
        count = int(es.get("esearchresult", {}).get("count", 0))
        docs = esummary(sym, ids)
        cats, examples, missense_pc = Counter(), {}, Counter()
        for doc in docs:
            gc = doc.get("germline_classification") or {}
            desc = (gc.get("description") or "")
            if "pathogenic" not in desc.lower() or "conflicting" in desc.lower():
                continue
            c = bio_clinvar.classify(doc, sym)
            cats[c] += 1
            if c == "missense" and protein_change(doc):
                missense_pc[protein_change(doc)] += 1
            rank = bio_clinvar.REVIEW_RANK.get(gc.get("review_status", ""), 0)
            examples.setdefault(c, []).append((rank, doc.get("title"), doc.get("accession"), desc,
                                               gc.get("review_status")))
        ex_out = {}
        for c, lst in examples.items():
            lst.sort(key=lambda x: (-x[0], x[1] or ""))
            ex_out[c] = [{"title": t, "accession": a, "classification": d, "review_status": rs,
                          "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{a.replace('VCV', '').lstrip('0')}/" if a else None}
                         for _, t, a, d, rs in lst[:4]]
        summary[sym] = {
            "query": es.get("_query"), "esearch_count": count, "n_docs": len(docs),
            "n_classified_PLP": sum(cats.values()), "by_consequence": dict(cats.most_common()),
            "missense_protein_changes": dict(missense_pc.most_common()),
            "examples": ex_out,
            "clinvar_search_url": "https://www.ncbi.nlm.nih.gov/clinvar/?term=" +
                                  f"{sym}%5Bgene%5D+AND+(clinsig_pathogenic%5Bprop%5D+OR+clinsig_likely_pathogenic%5Bprop%5D)",
        }
        print(f"[clinvar] {sym}: esearch={count} docs={len(docs)} -> {dict(cats.most_common(8))}")
    write_json(RAW / "clinvar_summary.json", summary)


if __name__ == "__main__":
    main()
