"""Independent verification of data/curated/family_lysosomal.json.

1. Every quote (nodes' sources, edges' evidence and counter_evidence) must occur, after the same Unicode / dash /
   quote / whitespace normalisation, as a substring of the LOCALLY STORED source, located from the evidence itself:
     PubMed  ref PMID:x                         -> data/raw/families/lysosomal/pubmed/x.json (title + abstract)
     ClinicalTrials.gov ref NCTx                -> data/raw/families/lysosomal/ctgov/studies/NCTx.json (full record)
     Website url = DailyMed setid               -> data/raw/families/lysosomal/fda/<slug>.json (openFDA label)
     Website other url                          -> data/raw/families/lysosomal/web/<id>.txt via web/_manifest.json
     GO ref GO:x                                -> data/raw/families/lysosomal/quickgo/terms.json
     UniProt ref <acc>                          -> data/raw/families/lysosomal/uniprot/<SYMBOL>.json
2. PubMed / Website evidence without a quote fails.
3. Every edge endpoint and cluster member must exist in the fragment or in data/graph.json.
Nothing from the curation layer is trusted. --write sets verified=true/false in the fragment. Exit 1 on any failure.
"""
import json
import sys

import lyso_common as L

frag = L.read_json(L.FRAGMENT)
manifest = L.read_json(L.WEB_DIR / "_manifest.json") if (L.WEB_DIR / "_manifest.json").exists() else {}
url2web = {}
for sid, m in manifest.items():
    for u in (m.get("url"), m.get("final_url")):
        if u:
            url2web[u] = sid
setid2fda = {}
for p in L.FDA_DIR.glob("*.json"):
    r = (L.read_json(p).get("results") or [{}])[0]
    if r.get("set_id"):
        setid2fda[r["set_id"]] = p.stem
uniprot = {L.read_json(p)["results"][0]["primaryAccession"] if False else None: None for p in []}
up_text = {}
for p in (L.RAW / "uniprot").glob("*.json"):
    for res in L.read_json(p).get("results", []):
        up_text[res["primaryAccession"]] = " ".join(t.get("value", "") for c in res.get("comments", []) for t in c.get("texts", []) or [])
go_text = " ".join(((r.get("definition") or {}).get("text") or "") for r in L.read_json(L.RAW / "quickgo" / "terms.json")["results"])


def stored(ev):
    ref, src, url = ev.get("ref", ""), ev.get("source"), ev.get("url", "")
    if src == "PubMed":
        return L.pubmed_text(ref.replace("PMID:", "")), f"pubmed/{ref}"
    if src == "ClinicalTrials.gov":
        p = L.CT_DIR / "studies" / f"{ref}.json"
        return (json.dumps(L.read_json(p), ensure_ascii=False) if p.exists() else None), f"ctgov/{ref}"
    if src == "Website" and "dailymed" in url:
        slug = setid2fda.get(url.split("setid=")[-1])
        return (L.label_text(slug) if slug else None), f"fda/{slug}"
    if src == "Website":
        sid = url2web.get(url)
        return (L.web_text(sid) if sid else None), f"web/{sid}"
    if src == "GO":
        return go_text, "quickgo/terms.json"
    if src == "UniProt":
        return up_text.get(ref), f"uniprot/{ref}"
    return None, f"no stored source for {src}"


fails, checked, ok = [], 0, 0
by_src = {}


def visit(ev, where):
    global checked, ok
    q = ev.get("quote")
    if not q:
        if ev.get("source") in ("PubMed", "Website"):
            fails.append((where, ev.get("ref"), "PubMed/Website evidence without a quote"))
        return
    checked += 1
    txt, loc = stored(ev)
    good = bool(txt) and L.norm(q) in L.norm(txt.replace("\\n", " ").replace('\\"', '"'))
    ev["verified"] = good
    by_src.setdefault(ev["source"], [0, 0])[0 if good else 1] += 1
    if good:
        ok += 1
    else:
        fails.append((where, ev.get("ref"), f"quote not found in {loc}: {q[:90]!r}"))


for n in frag["nodes"]:
    for ev in n.get("sources", []) or []:
        visit(ev, f"node {n['id']}")
for e in frag["edges"]:
    for ev in e.get("evidence", []) + e.get("counter_evidence", []):
        visit(ev, f"edge {e['id']}")
ids = {n["id"] for n in frag["nodes"]} | ({n["id"] for n in L.read_json(L.GRAPH)["nodes"]} if L.GRAPH.exists() else set())
dangling = [e["id"] for e in frag["edges"] if e["source"] not in ids or e["target"] not in ids]
bad_members = [(c["id"], m) for c in frag["clusters"] for m in c["members"] if m not in ids]
dup_nodes = len(frag["nodes"]) - len({n["id"] for n in frag["nodes"]})
print(f"quotes checked: {checked}  verified: {ok}  failed: {checked - ok}")
for s, (a, b) in sorted(by_src.items()):
    print(f"  {s:20s} verified {a}, failed {b}")
print(f"edges: {len(frag['edges'])}, dangling endpoints: {len(dangling)}; cluster members missing: {len(bad_members)}; duplicate node ids: {dup_nodes}")
for f in fails[:40]:
    print("  FAIL", *f)
for d in dangling[:20]:
    print("  DANGLING", d)
for b in bad_members[:20]:
    print("  MISSING MEMBER", b)
if "--write" in sys.argv:
    L.write_json(L.FRAGMENT, frag)
    print("wrote verified flags")
sys.exit(1 if (fails or dangling or bad_members or dup_nodes) else 0)
