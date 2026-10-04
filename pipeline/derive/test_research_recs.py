"""Test: `research_recs.py --add GENE` on a held-out gene gives the same rankings as a full recompute.

Run:  python3 pipeline/derive/test_research_recs.py [GENE ...]     (default: SCN8A GAA HRAS; ~1 min, offline)
It builds the full state without the held-out gene, adds it incrementally (n new similarities, bisect into the
stored top-k lists), and compares every disease's top-k list in every category with a full build over all
genes. Cluster assignment is reported but not required to match: incremental average-linkage assignment is
greedy and can differ from re-clustering everything (documented in docs/agent-reports/research-recommendations.md).
Nothing is written to data/: the test works on in-memory states.
"""
import copy
import sys

import research_recs as rr


def run(held_out):
    ctx = rr.Context()
    genes = sorted(ctx.prof)
    full = rr.full_state(ctx, genes)
    ok = True
    for g in held_out:
        partial = rr.full_state(ctx, [x for x in genes if x != g])
        inc = rr.add_disease(ctx, copy.deepcopy(partial), g)
        diffs = [(a, c) for a in genes for c in rr.CATEGORIES
                 if [tuple(x) for x in inc["topk"][a][c]] != [tuple(x) for x in full["topk"][a][c]]]
        same_clusters = sorted(map(tuple, inc["clusters"])) == sorted(map(tuple, full["clusters"]))
        print(f"--add {g}: {len(genes) * len(rr.CATEGORIES)} top-{rr.K} lists compared, {len(diffs)} differ"
              f"{' ' + str(diffs[:5]) if diffs else ''}; clusters identical: {same_clusters}")
        ok &= not diffs
    print("PASS" if ok else "FAIL")
    return ok


def test_add_matches_full():
    assert run(["SCN8A"])


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1:] or ["SCN8A", "GAA", "HRAS"]) else 1)
