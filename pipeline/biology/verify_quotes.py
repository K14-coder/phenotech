"""Independently verify every quote in data/curated/biology.json against the stored source text.

Run:  python3 pipeline/biology/verify_quotes.py            # report only
      python3 pipeline/biology/verify_quotes.py --write    # set verified=true/false in biology.json
Exit code 1 if any quote fails, so this can gate a build.

A quote passes only if, after Unicode normalisation (NFKC, dash and curly-quote folding,
whitespace collapse) it occurs as a SUBSTRING of the locally stored source text:
  PubMed  -> data/raw/biology/pubmed/<PMID>.json          (title + abstract)
  Trials  -> data/raw/biology/clinicaltrials/<NCT>.json   (titles + summaries + whyStopped)
  GO      -> data/raw/biology/quickgo/terms.json          (term definition)
  UniProt -> data/raw/biology/uniprot/<SYMBOL>.json       (FUNCTION comment)
Nothing is trusted from the curation layer: sources are re-read from disk here.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict

from common import CURATED, RAW, read_json, write_json

WRITE = "--write" in sys.argv


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"'))
    return " ".join(s.split())


def pubmed_text(pmid: str) -> str | None:
    p = RAW / "pubmed" / f"{pmid}.json"
    if not p.exists():
        return None
    r = read_json(p)
    return r["title"] + " " + r["abstract"]


def trial_text(nct: str) -> str | None:
    p = RAW / "clinicaltrials" / f"{nct}.json"
    if not p.exists():
        return None
    ps = read_json(p)["protocolSection"]
    d = ps.get("descriptionModule", {})
    return " ".join([ps["identificationModule"].get("briefTitle", ""),
                     ps["identificationModule"].get("officialTitle", ""),
                     d.get("briefSummary", ""), d.get("detailedDescription", ""),
                     ps["statusModule"].get("whyStopped", "")])


def go_text() -> str:
    p = RAW / "quickgo" / "terms.json"
    if not p.exists():
        return ""
    return " ".join((r.get("definition") or {}).get("text", "") + " " + (r.get("name") or "")
                    for r in read_json(p)["results"])


def uniprot_text() -> str:
    out = []
    for p in sorted((RAW / "uniprot").glob("*.json")):
        for res in read_json(p).get("results", []):
            for c in res.get("comments", []):
                for t in c.get("texts", []) or []:
                    out.append(t.get("value", ""))
    return " ".join(out)


_GO = None
_UP = None


def source_text(ev: dict) -> tuple[str | None, str]:
    """(text, locator-description) for an evidence item, or (None, why) if unavailable."""
    global _GO, _UP
    ref, src = ev.get("ref", ""), ev.get("source")
    if ref.startswith("PMID:") or (src == "PubMed" and ref.isdigit()):
        pmid = ref.replace("PMID:", "")
        t = pubmed_text(pmid)
        return (t, f"pubmed/{pmid}.json") if t else (None, f"MISSING pubmed/{pmid}.json")
    if ref.startswith("NCT"):
        t = trial_text(ref)
        return (t, f"clinicaltrials/{ref}.json") if t else (None, f"MISSING clinicaltrials/{ref}.json")
    if src == "GO":
        if _GO is None:
            _GO = go_text()
        return _GO, "quickgo/terms.json"
    if src == "UniProt":
        if _UP is None:
            _UP = uniprot_text()
        return _UP, "uniprot/*.json"
    return None, f"no stored source for source={src} ref={ref}"


def main() -> None:
    frag = read_json(CURATED / "biology.json")
    checked = passed = failed = skipped = 0
    fails = []
    by_source = defaultdict(lambda: [0, 0])

    def visit(ev: dict, where: str):
        nonlocal checked, passed, failed, skipped
        q = ev.get("quote")
        if not q:
            if ev.get("source") in ("PubMed", "ClinicalTrials.gov"):
                # schema: quote required for PubMed/Website evidence
                fails.append((where, ev.get("ref"), "PubMed/trial evidence without a quote"))
                ev["verified"] = False
                failed += 1
            return
        text, loc = source_text(ev)
        checked += 1
        if text is None:
            skipped += 1
            ev["verified"] = False
            fails.append((where, ev.get("ref"), loc))
            return
        ok = norm(q) in norm(text)
        ev["verified"] = ok
        by_source[ev["source"]][0 if ok else 1] += 1
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append((where, ev.get("ref"), f"quote not in {loc}: {q[:110]!r}"))

    for n in frag["nodes"]:
        for ev in n.get("sources", []) or []:
            visit(ev, f"node {n['id']}")
    for e in frag["edges"]:
        for ev in e.get("evidence", []) or []:
            visit(ev, f"edge {e['id']}")
        for ev in e.get("counter_evidence", []) or []:
            visit(ev, f"edge {e['id']} (counter)")

    print(f"quotes checked: {checked}  verified: {passed}  failed: {failed}  "
          f"unavailable source: {skipped}")
    for s, (ok, bad) in sorted(by_source.items()):
        print(f"  {s:20s} verified {ok}, failed {bad}")
    for where, ref, why in fails:
        print(f"  FAIL {where} [{ref}] {why}")
    if WRITE:
        write_json(CURATED / "biology.json", frag)
        print(f"wrote verified flags into {CURATED / 'biology.json'}")
    sys.exit(1 if (failed or skipped) else 0)


if __name__ == "__main__":
    main()
