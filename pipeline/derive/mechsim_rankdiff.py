"""Compare two versions of data/derived/mechsim.json: which atlas diseases' closest relatives changed.

Run:  python3 pipeline/derive/mechsim_rankdiff.py OLD.json [NEW.json] [--top 5] [--out docs/...md]
      OLD can be a git revision path, e.g. `git show <rev>:data/derived/mechsim.json > /tmp/old.json`.
Ranks every atlas disease's relatives (atlas diseases only) by the combined score and by each axis, and
reports the top-k lists that changed: entries that entered or left, and moves of 2+ places.
"""
from __future__ import annotations

import json
import sys

AXES = ["combined", "gene", "pathway", "tissue", "mutation", "fate", "structure", "drugs"]


def rankings(path, top):
    d = json.load(open(path))
    P = d["profiles"]
    col = {f: k for k, f in enumerate(d["pair_fields"])}
    atlas = [i for i, p in enumerate(P) if p["kind"] == "atlas"]
    aset = set(atlas)
    score = {a: {} for a in AXES}
    for r in d["pairs"]:
        i, j = r[0], r[1]
        if i in aset and j in aset:
            for a in AXES:
                v = r[col[a]]
                if v is not None:
                    score[a][(i, j)] = score[a][(j, i)] = v
    out = {}
    for a in AXES:
        for i in atlas:
            others = [(score[a][(i, j)], P[j]["gene"]) for j in atlas if j != i and (i, j) in score[a]]
            others.sort(key=lambda x: (-x[0], x[1]))
            out[(a, P[i]["gene"])] = [(g, round(v, 3)) for v, g in others[:top]]
    return out, d["meta"]


def main():
    argv = sys.argv[1:]
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in ("--top", "--out"))]
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 5
    old_path, new_path = args[0], (args[1] if len(args) > 1 else "data/derived/mechsim.json")
    old, om = rankings(old_path, top)
    new, nm = rankings(new_path, top)
    lines = [f"# Mechanistic ranking changes (top {top}, atlas diseases)", "",
             f"- old: `{old_path}` (generated {om.get('generated')}, TM-align pairs {om.get('tmalign_pairs')})",
             f"- new: `{new_path}` (generated {nm.get('generated')}, TM-align pairs {nm.get('tmalign_pairs')})", ""]
    changed = 0
    for a in AXES:
        rows = []
        for key in sorted(k for k in new if k[0] == a):
            o, n = [g for g, _ in old.get(key, [])], [g for g, _ in new[key]]
            if o == n:
                continue
            entered = [g for g in n if g not in o]
            left = [g for g in o if g not in n]
            moved = [f"{g} {o.index(g) + 1}→{n.index(g) + 1}" for g in n if g in o and abs(o.index(g) - n.index(g)) >= 2]
            if not (entered or left or moved):
                continue
            changed += 1
            rows.append(f"| {key[1]} | {', '.join(o)} | {', '.join(n)} | {', '.join(entered) or '–'} | "
                        f"{', '.join(left) or '–'} | {', '.join(moved) or '–'} |")
        lines += [f"## {a}: {len(rows)} diseases changed", ""]
        if rows:
            lines += ["| Disease | Old top | New top | Entered | Left | Moved ≥2 |", "|---|---|---|---|---|---|", *rows]
        lines.append("")
    text = "\n".join(lines)
    if "--out" in sys.argv:
        open(sys.argv[sys.argv.index("--out") + 1], "w").write(text + "\n")
    print(text if len(text) < 20000 else text[:20000] + "\n…")
    print(f"\n{changed} changed top-{top} lists")


if __name__ == "__main__":
    main()
