"""Verifier for pipeline/families/lysosomal/curated_orgs.json (stdlib only).

Checks, for every org and asset:
  * every evidence / serves_evidence / covers_evidence quote: lyso_common.norm(quote) is a substring of
    lyso_common.norm(data/raw/families/lysosomal/web/<src>.txt)
  * every src is in web/_manifest.json with status 200 and its .txt exists
  * maintained_by only lists org ids defined in the same file
  * ids are unique lowercase slugs with the right prefix; serves/covers genes belong to the family and
    each has at least one quote; asset kind is one of the allowed kinds
  * xrefs.NCT (if any) literally appears in a stored page the record cites
  * no e-mail address in any quote (privacy)

Prints every failure and exits 1 if there is any; exits 0 otherwise.

Usage: python3 pipeline/families/lysosomal/check_orgs.py
"""
from __future__ import annotations

import re
import sys

import lyso_common as lc

CURATED = lc.HERE / "curated_orgs.json"
MANIFEST = lc.WEB_DIR / "_manifest.json"
KINDS = {"registry", "natural_history_study", "biobank", "research_network", "data_platform", "funding_program"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NCT = re.compile(r"^NCT\d{8}$")


def main() -> int:
    data = lc.read_json(CURATED)
    manifest = lc.read_json(MANIFEST)
    fails: list[str] = []
    texts: dict[str, str | None] = {}
    n_quotes = 0

    def page(src: str) -> str | None:
        if src not in texts:
            m = manifest.get(src)
            if not m:
                fails.append(f"src {src!r}: not in _manifest.json")
                texts[src] = None
            elif m.get("status") != 200:
                fails.append(f"src {src!r}: manifest status {m.get('status')} (need 200)")
                texts[src] = None
            else:
                raw = lc.web_text(src)
                if raw is None:
                    fails.append(f"src {src!r}: {src}.txt missing")
                texts[src] = lc.norm(raw) if raw is not None else None
        return texts[src]

    def check_quotes(rid: str, where: str, evs) -> int:
        nonlocal n_quotes
        if not isinstance(evs, list) or not evs:
            fails.append(f"{rid} {where}: no evidence quotes")
            return 0
        ok = 0
        for e in evs:
            src, quote = e.get("src"), e.get("quote") or ""
            n_quotes += 1
            if lc.EMAIL_RE.search(quote):
                fails.append(f"{rid} {where} [{src}]: quote contains an e-mail address")
            if len(lc.norm(quote)) < 12:
                fails.append(f"{rid} {where} [{src}]: quote too short to be meaningful: {quote!r}")
            t = page(src)
            if t is None:
                fails.append(f"{rid} {where}: unusable src {src!r}")
                continue
            if lc.norm(quote) not in t:
                fails.append(f"{rid} {where} [{src}]: quote not found in stored page: {quote[:140]!r}")
                continue
            ok += 1
        return ok

    orgs, assets = data.get("orgs", []), data.get("assets", [])
    org_ids = {o.get("id") for o in orgs}
    seen: set[str] = set()

    def check_id(rid: str, prefix: str) -> None:
        if not rid or not rid.startswith(prefix) or not SLUG.match(rid[len(prefix):]):
            fails.append(f"{rid!r}: id must be {prefix}<lowercase-slug>")
        if rid in seen:
            fails.append(f"{rid}: duplicate id")
        seen.add(rid)

    def check_genes(rid: str, field: str, genes, ev_map) -> None:
        if not isinstance(ev_map, dict):
            fails.append(f"{rid} {field}_evidence: must be an object")
            ev_map = {}
        for g in genes:
            if g not in lc.GENES:
                fails.append(f"{rid} {field}: {g!r} is not a lysosomal-family gene")
            if g not in ev_map:
                fails.append(f"{rid} {field}: {g} has no {field}_evidence")
        for g, evs in ev_map.items():
            if g not in genes:
                fails.append(f"{rid} {field}_evidence: {g} not listed in {field}")
            check_quotes(rid, f"{field}_evidence[{g}]", evs)

    for o in orgs:
        rid = o.get("id")
        check_id(rid, "org:")
        for k in ("label", "url", "summary", "scope", "country"):
            if not o.get(k):
                fails.append(f"{rid}: missing {k}")
        if not str(o.get("url", "")).startswith("https://"):
            fails.append(f"{rid}: url must be https://")
        check_quotes(rid, "evidence", o.get("evidence"))
        check_genes(rid, "serves", o.get("serves") or [], o.get("serves_evidence") or {})

    for a in assets:
        rid = a.get("id")
        check_id(rid, "asset:")
        for k in ("label", "url", "access"):
            if not a.get(k):
                fails.append(f"{rid}: missing {k}")
        if not str(a.get("url", "")).startswith("https://"):
            fails.append(f"{rid}: url must be https://")
        if a.get("kind") not in KINDS:
            fails.append(f"{rid}: kind {a.get('kind')!r} not in {sorted(KINDS)}")
        for m in a.get("maintained_by") or []:
            if m not in org_ids:
                fails.append(f"{rid}: maintained_by {m!r} is not an org defined in curated_orgs.json")
        check_quotes(rid, "evidence", a.get("evidence"))
        check_genes(rid, "covers", a.get("covers") or [], a.get("covers_evidence") or {})
        nct = (a.get("xrefs") or {}).get("NCT")
        if nct is not None:
            cited = {e.get("src") for e in a.get("evidence", [])}
            for evs in (a.get("covers_evidence") or {}).values():
                cited |= {e.get("src") for e in evs}
            if not NCT.match(nct):
                fails.append(f"{rid}: malformed NCT id {nct!r}")
            elif not any((page(s) or "").find(nct) >= 0 for s in cited):
                fails.append(f"{rid}: {nct} does not appear in any stored page it cites")

    for g in data.get("search_log", {}):
        if g not in lc.GENES:
            fails.append(f"search_log: {g!r} is not a lysosomal-family gene")
    for g in data.get("not_found", {}):
        if g not in lc.GENES:
            fails.append(f"not_found: {g!r} is not a lysosomal-family gene")

    for f in fails:
        print("FAIL", f)
    per_gene = {g: sorted({o["id"] for o in orgs if g in (o.get("serves") or [])}) for g in lc.GENES}
    per_gene_a = {g: sorted({a["id"] for a in assets if g in (a.get("covers") or [])}) for g in lc.GENES}
    print(f"{len(orgs)} orgs, {len(assets)} assets, {n_quotes} quotes checked; {len(fails)} failure(s)")
    for g in lc.GENES:
        print(f"  {g:6} orgs={len(per_gene[g])} assets={len(per_gene_a[g])}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
