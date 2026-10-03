"""Draw the precision spot-check samples (30 random links per source, seed 7) and print them compactly for
manual review. Samples are saved to data/derived/scale/spotcheck/<source>.json; the manual verdicts are recorded
in data/derived/scale/spotcheck/verdicts.json and summarised in README.md.

Usage: python3 spotcheck.py <source>     sources: trials_name trials_gene org_<source> asset_<id-suffix>
"""
from __future__ import annotations

import json
import random
import sys

from common import OUT, write_json

N = 30


def population(src: str):
    if src.startswith("trials_"):
        t = json.load(open(OUT / "trials.json"))
        pop = []
        for did, d in t["diseases"].items():
            for e in d["top"]:
                if (src == "trials_name") == e["rule"].startswith("name"):
                    s = t["studies"][e["nct"]]
                    pop.append({"disease": did, "disease_name": d["name"], "genes": d["genes"], "nct": e["nct"],
                                "rule": e["rule"], "quote": e["quote"], "via_gene": e.get("via_gene"),
                                "title": s["title"], "conditions": s["conditions"][:5]})
        return pop
    if src.startswith("org_"):
        o = json.load(open(OUT / "orgs.json"))
        want = src[4:]
        pop = []
        for org in o["orgs"]:
            for d in org["diseases"]:
                for e in [d["evidence"]] + d["also"]:
                    if e["source"] == want:
                        pop.append({"org": org["name"], "org_id": org["id"], "url": org["url"], "disease": d["id"],
                                    "disease_name": d["name"], "rule": e["rule"], "quote": e["quote"][:300],
                                    "evidence_url": e["url"], "context": e.get("context")})
                        break
        return pop
    if src.startswith("asset_"):
        a = json.load(open(OUT / "assets.json"))
        want = src[6:]
        pop = []
        for asset in a["assets"]:
            if not asset["id"].startswith("asset:" + want):
                continue
            for l in asset["diseases"]:
                pop.append({"asset": asset["name"], "disease": l.get("id") or l.get("gene"),
                            "disease_name": l.get("name") or "; ".join(l.get("names", [])[:3]),
                            "rule": l["evidence"]["rule"], "quote": l["evidence"]["quote"][:200]})
        return pop
    raise SystemExit(f"unknown source {src}")


def main():
    src = sys.argv[1]
    pop = population(src)
    rnd = random.Random(7)
    sample = rnd.sample(pop, min(N, len(pop)))
    write_json(OUT / "spotcheck" / f"{src}.json", {"source": src, "population": len(pop), "sample": sample}, indent=1)
    print(f"{src}: population {len(pop)}, sample {len(sample)}")
    for i, s in enumerate(sample, 1):
        if src.startswith("trials"):
            print(f"{i:2}. [{s['disease_name'][:55]}|{','.join(s['genes'][:2])}] {s['rule']} via={s['via_gene']} "
                  f"Q='{s['quote'][:70]}' T='{s['title'][:90]}' C={s['conditions'][:3]}")
        elif src.startswith("org"):
            print(f"{i:2}. [{s['disease_name'][:50]}] <- {s['org'][:50]} | {s['rule']} | Q='{s['quote'][:150]}'"
                  + (f" | ctx='{s['context'][:80]}'" if s.get("context") else ""))
        else:
            print(f"{i:2}. [{s['disease_name'][:70]}] {s['rule']} Q='{s['quote'][:80]}'")


if __name__ == "__main__":
    main()
