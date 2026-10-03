"""ClinVar pathogenic / likely-pathogenic germline spectrum per RASopathy gene (NCBI E-utilities).
Adapted from pipeline/biology/clinvar.py; classification logic is reused from that module.

Run:  python3 pipeline/families/rasopathy/clinvar.py [--refresh]
NCBI etiquette: shared cross-process throttle (<= 2 req/s, pipeline/biology/common.py file lock),
tool=rare-disease-atlas, no email param, exponential backoff on 429/5xx.
Out:  data/raw/families/rasopathy/clinvar/<GENE>_esearch.json, <GENE>_esummary_<n>.json
      data/raw/families/rasopathy/clinvar_summary.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from ras_common import GENES, RAW, eutils, load_bio, read_json, write_json

bio_clinvar = load_bio("clinvar")  # reuse classify() + REVIEW_RANK from the biology layer

REFRESH = "--refresh" in sys.argv
OUT = RAW / "clinvar"
OUT.mkdir(parents=True, exist_ok=True)
BATCH = 400


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


def main():
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
            c = bio_clinvar.classify(doc, sym)
            cats[c] += 1
            rank = bio_clinvar.REVIEW_RANK.get(gc.get("review_status", ""), 0)
            traits = sorted({t.get("trait_name") for t in (gc.get("trait_set") or []) if t.get("trait_name")})
            examples.setdefault(c, []).append((rank, doc.get("title"), doc.get("accession"), desc,
                                               gc.get("review_status"), traits[:3]))
        ex_out = {}
        for c, lst in examples.items():
            lst.sort(key=lambda x: (-x[0], x[1] or ""))
            ex_out[c] = [{"title": t, "accession": a, "classification": d, "review_status": rs, "traits": tr,
                          "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{a.replace('VCV', '').lstrip('0')}/"
                          if a else None} for _, t, a, d, rs, tr in lst[:4]]
        summary[sym] = {
            "query": es.get("_query"), "esearch_count": count, "n_docs": len(docs),
            "n_classified_PLP": sum(cats.values()), "by_consequence": dict(cats.most_common()),
            "examples": ex_out,
            "clinvar_search_url": "https://www.ncbi.nlm.nih.gov/clinvar/?term=" +
                                  f"{sym}%5Bgene%5D+AND+(clinsig_pathogenic%5Bprop%5D+OR+clinsig_likely_pathogenic%5Bprop%5D)"}
        print(f"[clinvar] {sym}: esearch={count} docs={len(docs)} -> {dict(cats.most_common())}")
    write_json(RAW / "clinvar_summary.json", summary)


if __name__ == "__main__":
    main()
