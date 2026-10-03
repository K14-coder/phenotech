"""Write docs/review/biochem-review.md: the links a biochemist should check, most important first.

Sections: where the OpenAI re-reading disagrees with the curators, contradictions only the AI found,
then the links the demo journeys rely on. The reviewer ticks one box per item; pipeline/apply_review.py
turns the ticks into review records in data/curated/overrides.json.

Usage: python3 pipeline/review_sheet.py
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "review" / "biochem-review.md"
DEMO_DISEASES = {"disease:STXBP1", "disease:SLC6A1", "disease:VAMP2", "disease:SYT2", "disease:SNAP25", "disease:SYT1"}
DEMO_TYPES = {"shares_mechanism", "driven_by", "developed_for", "targets", "candidate_for"}


def quote_line(prefix, ev):
    quote = " ".join((ev.get("quote") or "").split())
    if len(quote) > 320:
        quote = quote[:320] + "…"
    stamp = ""
    if ev.get("cross_checked"):
        stamp = " _(AI re-reading agrees)_" if ev["cross_checked"]["agrees"] else " _(AI re-reading DISAGREES)_"
    return f"- {prefix}: [{ev.get('ref')}]({ev.get('url')}){stamp}" + (f" — “{quote}”" if quote else "")


def block(i, e, nodes, boxes):
    lines = [
        f"## {i}. {nodes[e['source']]['label']} → {e['type'].replace('_', ' ')} → {nodes[e['target']]['label']}",
        "",
        f"`{e['id']}`",
        "",
        f"Level **{e['evidence_level']}** · confidence **{e['confidence']}** · status **{e['status']}**",
        "",
        f"> {e['explanation']}",
        "",
    ]
    lines += [quote_line("Supports", ev) for ev in e.get("evidence", [])[:3]]
    lines += [quote_line("Contradicts or limits", ev) for ev in e.get("counter_evidence", [])[:3]]
    hidden = len(e.get("evidence", [])) - 3
    if hidden > 0:
        lines.append(f"- …and {hidden} more supporting sources in the app")
    return lines + ["", boxes, "", "Note: ", "", "---", ""]


def main():
    if OUT.exists() and re.search(r"\[[xX]\]\s*(Confirm|Correct|Reject)", OUT.read_text()) and "--force" not in sys.argv:
        sys.exit(f"{OUT.relative_to(ROOT)} already has ticked boxes. Run pipeline/apply_review.py first, or pass --force.")
    g = json.loads((ROOT / "data" / "graph.json").read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    edges = g["edges"]
    reviewed = {e["id"] for e in edges if e.get("review")}

    disagreements = [
        e for e in edges
        if e["id"] not in reviewed
        and any(ev.get("cross_checked", {}).get("agrees") is False for ev in e.get("evidence", []) + e.get("counter_evidence", []))
    ]
    ai_contradictions = [
        e for e in edges
        if e["id"] not in reviewed and e not in disagreements
        and any(ev.get("needs_review") for ev in e.get("counter_evidence", []))
    ]
    seen = {e["id"] for e in disagreements + ai_contradictions}
    demo = [
        e for e in edges
        if e["id"] not in reviewed and e["id"] not in seen and e["type"] in DEMO_TYPES
        and ({e["source"], e["target"]} & DEMO_DISEASES or e["type"] == "targets")
    ]
    order = {t: i for i, t in enumerate(["shares_mechanism", "candidate_for", "driven_by", "developed_for", "targets"])}
    demo.sort(key=lambda e: (order[e["type"]], e["id"]))

    boxes = "- [ ] Confirm  - [ ] Correct  - [ ] Reject"
    out = [
        "# Biochemistry review",
        "",
        "Reviewer initials: ",
        "",
        "Tick **one** box per item (change `[ ]` to `[x]`) and add a note whenever something is wrong. "
        "Skip what you can't get to; unreviewed links stay as they are. Every confirmed link shows "
        "\"Reviewed by a biochemist\" in the app.",
        "",
        "- **Confirm**: correct as written.",
        "- **Correct**: basically right, but the explanation, level, confidence or the filing of a source needs changing. Say how in the note.",
        "- **Reject**: wrong or unsupported. It is removed from the atlas.",
        "",
        f"**Part 1** ({len(disagreements)}): the independent OpenAI re-reading disagrees with how a source was filed. Who is right?",
        f"**Part 2** ({len(ai_contradictions)}): contradicting sources only the AI found. Does the source really contradict the link?",
        f"**Part 3** ({len(demo)}): the links the demo journeys rely on, including the atlas's own hypotheses.",
        "",
        "# Part 1: AI re-reading disagrees",
        "",
    ]
    i = 0
    for e in disagreements:
        i += 1
        out += block(i, e, nodes, boxes)
    out += ["# Part 2: contradictions found only by the AI", ""]
    for e in ai_contradictions:
        i += 1
        out += block(i, e, nodes, boxes)
    out += ["# Part 3: links the demo relies on", ""]
    for e in demo:
        i += 1
        out += block(i, e, nodes, boxes)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out))
    print(f"{len(disagreements)} disagreements, {len(ai_contradictions)} AI-only contradictions, {len(demo)} demo links -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
