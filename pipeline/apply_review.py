"""Turn the ticked boxes in docs/review/biochem-review.md into review records in data/curated/overrides.json.

Confirm and Correct add a review record to the edge; Reject also removes the edge from the atlas.
Corrections described in notes still need applying by hand (edge_patches in overrides.json).

Usage: python3 pipeline/apply_review.py && python3 pipeline/build_graph.py
"""

import datetime
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEET = ROOT / "docs" / "review" / "biochem-review.md"
OVERRIDES = ROOT / "data" / "curated" / "overrides.json"
VERDICTS = {"confirm": "confirmed", "correct": "corrected", "reject": "rejected"}


def main():
    text = SHEET.read_text()
    initials = (re.search(r"^Reviewer initials:\s*(\S.*)$", text, re.M) or [None, "biochemist"])[1].strip()
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    patches = overrides.setdefault("edge_patches", {})
    today = datetime.date.today().isoformat()
    counts = {v: 0 for v in VERDICTS.values()}

    for chunk in text.split("\n---"):
        edge_id = re.search(r"^`([^`]+\|[^`]+\|[^`]+)`$", chunk, re.M)
        ticked = re.findall(r"\[[xX]\]\s*(Confirm|Correct|Reject)", chunk)
        if not edge_id or len(ticked) != 1:
            continue
        verdict = VERDICTS[ticked[0].lower()]
        note = (re.search(r"^Note:[ \t]*(.*)$", chunk, re.M) or [None, ""])[1].strip()
        review = {"by": f"human:{initials}", "date": today, "verdict": verdict}
        if note:
            review["note"] = note
        patches.setdefault(edge_id[1], {})["review"] = review
        counts[verdict] += 1

    OVERRIDES.write_text(json.dumps(overrides, indent=2, ensure_ascii=False) + "\n")
    print(", ".join(f"{n} {v}" for v, n in counts.items()), f"-> {OVERRIDES}")
    corrected = [k for k, v in patches.items() if v.get("review", {}).get("verdict") == "corrected"]
    if corrected:
        print("Corrections to apply by hand (see the notes):")
        for edge_id in corrected:
            print(f"  {edge_id}: {patches[edge_id]['review'].get('note', '(no note)')}")


if __name__ == "__main__":
    main()
