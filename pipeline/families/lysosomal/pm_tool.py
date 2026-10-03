"""Curation helper: PubMed esearch -> efetch (stored under data/raw/families/lysosomal/pubmed/) -> print.

  python3 pm_tool.py search "<term>" [retmax]          # titles of the top hits (records are stored)
  python3 pm_tool.py grep <PMID> "<regex>"              # sentences of a stored abstract matching regex
  python3 pm_tool.py fetch <PMID> [<PMID> ...]
Uses lyso_common (shared NCBI throttle, tool=rare-disease-atlas, no email).
"""
import re
import sys

import lyso_common as L

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "search":
        ids = L.esearch_pubmed(sys.argv[2], retmax=int(sys.argv[3]) if len(sys.argv) > 3 else 6)
        recs = L.fetch_pmids(ids)
        for p in ids:
            r = recs.get(p)
            if r:
                print(f"  {p} {r['year']} {'/'.join(t for t in r['pub_types'] if t in ('Review','Clinical Trial','Randomized Controlled Trial','Case Reports'))} | {r['title'][:150]}")
    elif cmd == "fetch":
        recs = L.fetch_pmids(sys.argv[2:])
        for p, r in recs.items():
            print(f"  {p} {r['year']} | {r['title'][:150]}")
    elif cmd == "grep":
        txt = L.pubmed_text(sys.argv[2])
        rx = re.compile(sys.argv[3], re.I)
        for s in L.sentences(txt or ""):
            if rx.search(s):
                print("  >", s)
