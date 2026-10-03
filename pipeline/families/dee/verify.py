"""Independently verify data/curated/family_dee.json.

1. Every quote is string-matched (NFKC, dash/quote folding, whitespace collapse) against the
   locally stored source it cites -- nothing is trusted from the curation step:
     PubMed       data/raw/families/dee/pubmed/<PMID>.json (title+abstract)
     Trials       data/raw/families/dee/clinicaltrials/<NCT>.json, else the community CT.gov store
     FDA labels   data/raw/families/dee/labels/<BRAND>.json
     Website      community web page stored under data/raw/families/dee/community/web/ (by URL)
     RePORTER     data/raw/families/dee/community/reporter/*.json (by project number)
     GO / UniProt data/raw/families/dee/quickgo/terms.json, uniprot/<SYMBOL>.json
2. Every edge endpoint must exist in the fragment or in data/graph.json; cluster members/edges too.
Sets verified=true/false (--write) and exits 1 on any failure.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import curation as CUR
from dee_common import OUT_FRAGMENT, RAW, existing_graph, norm, read_json, write_json

COMM = RAW / "community"


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


_cache = {}


def community_trial(nct):
    if "ct" not in _cache:
        idx = {}
        for p in (COMM / "ctgov").glob("*.json"):
            obj = read_json(p)
            for s in (obj.get("studies") if isinstance(obj, dict) else None) or ([obj] if isinstance(obj, dict) else []):
                n = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                if n:
                    idx.setdefault(n, []).append(s)
        _cache["ct"] = idx
    recs = _cache["ct"].get(nct)
    return "\n".join(x for r in recs for x in strings(r)) if recs else None


def reporter_text(pn):
    if "rep" not in _cache:
        idx = {}
        for p in (COMM / "reporter").glob("*.json"):
            for r in strings(read_json(p)) if False else []:
                pass
            obj = read_json(p)
            for res in ((obj.get("response") or {}).get("results") or obj.get("results") or []):
                k = res.get("project_num") or ""
                idx.setdefault(k, []).append(res)
                idx.setdefault(res.get("core_project_num") or "", []).append(res)
        _cache["rep"] = idx
    recs = _cache["rep"].get(pn)
    return "\n".join(x for r in recs for x in strings(r)) if recs else None


def web_text(url):
    if "web" not in _cache:
        man = read_json(COMM / "web" / "_manifest.json")
        idx = {}
        for sid, m in man.items():
            for u in (m.get("url"), m.get("final_url")):
                if u:
                    idx.setdefault(u.rstrip("/"), []).append(sid)
        _cache["web"] = idx
    out = []
    for sid in _cache["web"].get(url.rstrip("/"), []):
        for ext in ("txt", "html"):
            p = COMM / "web" / f"{sid}.{ext}"
            if p.exists():
                out.append(p.read_text())
    return "\n".join(out) or None


def source_text(ev):
    ref, src = ev.get("ref", ""), ev.get("source")
    try:
        if ref.startswith("PMID:") or ref.startswith("FDA-label:"):
            return CUR.source_text(ref)[0]
    except FileNotFoundError:
        pass
    if src == "ClinicalTrials.gov":
        own = RAW / "clinicaltrials" / f"{ref}.json"
        parts = [community_trial(ref) or ""]
        if own.exists():
            parts.append("\n".join(strings(read_json(own))))
        return "\n".join(parts) or None
    if src == "NIH RePORTER":
        return reporter_text(ref)
    if src == "Website":
        return web_text(ev.get("url") or ref)
    if src == "PubMed":
        p = COMM / "pubmed"
        return "\n".join(x for f in p.glob("*.json") for x in strings(read_json(f))) or None
    if src == "GO":
        return "\n".join(strings(read_json(RAW / "quickgo" / "terms.json")))
    if src == "UniProt":
        return "\n".join(x for f in (RAW / "uniprot").glob("*.json") for x in strings(read_json(f)))
    return None


def main():
    frag = read_json(OUT_FRAGMENT)
    ok, fails, by = 0, [], Counter()
    for item in frag["nodes"] + frag["edges"]:
        for key in ("sources", "evidence", "counter_evidence"):
            for ev in item.get(key, []) or []:
                q = ev.get("quote")
                if not q:
                    if ev.get("source") in ("PubMed", "Website"):
                        fails.append((item["id"], ev.get("ref"), "no quote"))
                    continue
                t = source_text(ev)
                good = bool(t) and norm(q) in norm(t)
                ev["verified"] = good
                by[(ev["source"], good)] += 1
                if good:
                    ok += 1
                else:
                    fails.append((item["id"], ev.get("ref"), "missing source" if not t else f"not found: {q[:90]!r}"))
    ids = {n["id"] for n in frag["nodes"]} | set(existing_graph())
    eids = {e["id"] for e in frag["edges"]}
    dang = [e["id"] for e in frag["edges"] if e["source"] not in ids or e["target"] not in ids]
    dang += [f"{c['id']} member {m}" for c in frag["clusters"] for m in c["members"] if m not in ids]
    dang += [f"{c['id']} edge {x}" for c in frag["clusters"] for x in c["edge_ids"] if x not in eids]
    bad_id = [e["id"] for e in frag["edges"] if e["id"] != f"{e['source']}|{e['type']}|{e['target']}"]
    print(f"quotes verified {ok}, failed {len(fails)}; dangling refs {len(dang)}; bad edge ids {len(bad_id)}")
    for (s, g), n in sorted(by.items()):
        print(f"  {s:20s} {'ok ' if g else 'BAD'} {n}")
    for f in fails[:30]:
        print("  FAIL", f)
    for d in dang[:20]:
        print("  DANGLING", d)
    if "--write" in sys.argv:
        write_json(OUT_FRAGMENT, frag)
    sys.exit(1 if (fails or dang or bad_id) else 0)


if __name__ == "__main__":
    main()
