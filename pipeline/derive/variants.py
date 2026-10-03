"""Product 1: variant lookup -> data/derived/variants.json (+ variant_test_cases.json check).

Run:  python3 pipeline/derive/variants.py
In:   data/raw/biology/clinvar/<GENE>_esummary_<n>.json (stored ClinVar esummary, P/LP query only)
      data/graph.json (variant_group nodes)
Out:  data/derived/variants.json            per-gene variant table + lookup index (compact JSON)
      data/derived/variant_test_cases.json  15-20 query -> expected-result cases (checked here)

Consequences are re-derived from each record (molecular_consequence_list, then the title's p./c.
notation, then obj_type) with the same parser the UI will use (hgvs.py). The variant_group is the
graph node for that consequence class: nonsense/frameshift/start-lost -> truncating, splice ->
splice, missense -> missense, single-gene copy-number change -> whole-gene-deletion, multi-gene
copy-number change -> contiguous-gene-deletion; inframe/synonymous/other -> no group.
"""
from __future__ import annotations

import glob
import re
from collections import Counter, defaultdict

import hgvs
from dcommon import BIO_RAW, DERIVED, SLICE_GENES, TODAY, Graph, read_json, write_json

STARS = {"practice guideline": 4, "reviewed by expert panel": 3,
         "criteria provided, multiple submitters, no conflicts": 2,
         "criteria provided, single submitter": 1, "criteria provided, conflicting classifications": 1,
         "no assertion criteria provided": 0}
MC_PRIORITY = [("nonsense", "nonsense"), ("frameshift", "frameshift"), ("splice donor", "splice"),
               ("splice acceptor", "splice"), ("initiator", "start_lost"), ("stop lost", "other"),
               ("missense", "missense"), ("inframe", "inframe_indel"), ("synonymous", "synonymous")]
FIELDS = ["accession", "url", "hgvs", "p", "protein_change", "consequence", "classification", "stars",
          "n_submissions", "variant_group"]
CONSEQ_ORDER = ["nonsense", "frameshift", "splice", "missense", "inframe_indel", "cnv", "synonymous", "other"]


def record_consequence(doc: dict):
    """-> (consequence, vg_kind) where vg_kind is a key of hgvs.VG_SLUG or None."""
    otype = (doc.get("obj_type") or "").lower()
    genes = [g.get("symbol") for g in doc.get("genes") or []]
    title = doc.get("title") or ""
    if "copy number" in otype:
        return "cnv", ("cnv_multi" if len(genes) > 1 else "cnv_single")
    mcs = [m.lower() for m in doc.get("molecular_consequence_list") or []]
    for key, cons in MC_PRIORITY:
        if any(key in m for m in mcs):
            if cons == "start_lost":
                return "other", "start_lost"
            return cons, (cons if cons in hgvs.VG_SLUG else None)
    p = hgvs.normalize_p(title)
    c = hgvs.normalize_c(title)
    cls = hgvs.classify_p(p) if p else None
    if (not cls or cls[1] == "unknown") and c:
        cls = hgvs.classify_c(c)
    if cls and cls[1] != "unknown":
        cons = cls[0]
        if "start-lost" in cls[2]:
            return "other", "start_lost"
        return cons, (cons if cons in hgvs.VG_SLUG else None)
    if otype in ("deletion", "duplication") and not c:
        return "cnv", ("cnv_multi" if len(genes) > 1 else "cnv_single")
    if any("intron" in m for m in mcs):
        return "splice", "splice"   # intronic P/LP records: grouped with splice (biology-layer convention)
    return "other", None


def c_position(c):
    m = re.match(r"c\.([-*]?)(\d+)", c or "")
    if not m:
        return 10 ** 9
    return int(m.group(2)) * (-1 if m.group(1) == "-" else 1) + (10 ** 6 if m.group(1) == "*" else 0)


def main():
    g = Graph()
    vg_nodes = {nid: n for nid, n in g.nodes.items() if n["type"] == "variant_group"}
    genes_out, index = {}, defaultdict(list)
    tx2gene = {}
    qa = {}
    for gene in SLICE_GENES:
        docs = []
        for f in sorted(glob.glob(str(BIO_RAW / "clinvar" / f"{gene}_esummary_*.json"))):
            res = read_json(f)["result"]
            docs += [res[u] for u in res["uids"]]
        rows = []
        cons_counts = Counter()
        for d in docs:
            gc = d.get("germline_classification") or {}
            desc = gc.get("description") or ""
            if "pathogenic" not in desc.lower() or "conflicting" in desc.lower():
                continue
            title = d.get("title") or ""
            mt = re.match(r"(N[MC]_\d+)\.\d+\(", title)
            if mt and mt.group(1).startswith("NM_"):
                tx2gene[mt.group(1)] = gene
            cons, kind = record_consequence(d)
            slug = hgvs.VG_SLUG.get(kind) if kind else None
            vg = f"vg:{gene}:{slug}" if slug and f"vg:{gene}:{slug}" in vg_nodes else None
            cons_counts[cons] += 1
            acc = d.get("accession")
            vid = acc.replace("VCV", "").lstrip("0")
            rows.append({
                "accession": acc, "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{vid}/",
                "hgvs": title, "p": hgvs.normalize_p(title), "protein_change": d.get("protein_change") or "",
                "consequence": cons, "classification": desc, "stars": STARS.get(gc.get("review_status"), 0),
                "n_submissions": len((d.get("supporting_submissions") or {}).get("scv") or []),
                "variant_group": vg, "_c": hgvs.normalize_c(title)})
        rows.sort(key=lambda r: (CONSEQ_ORDER.index(r["consequence"]), c_position(r["_c"]), r["accession"]))
        for i, r in enumerate(rows):
            if r["_c"]:
                index[f"c:{gene}:{r['_c']}"].append(i)
            if r["p"]:
                index[f"p:{gene}:{r['p']}"].append(i)
            for alias in (r["protein_change"] or "").split(","):
                a = hgvs.normalize_p(alias.strip())
                if a and a != r["p"]:
                    index[f"iso:{gene}:{a}"].append(i)
        # recurrent residues: protein positions with >= 2 distinct P/LP alleles
        by_res = defaultdict(list)
        for r in rows:
            m = re.match(r"([A-Z])(\d+)", r["p"] or "")
            if m and r["consequence"] in ("missense", "nonsense"):
                by_res[m.group(1) + m.group(2)].append(r["p"])
        recurrent_res = sorted(((k, v) for k, v in by_res.items() if len(v) >= 2), key=lambda kv: (-len(kv[1]), kv[0]))
        top_reported = sorted((r for r in rows if r["p"]), key=lambda r: -r["n_submissions"])[:5]
        # QA against the biology layer's per-group counts on the graph
        mine = Counter(r["variant_group"] for r in rows if r["variant_group"])
        theirs = {nid: n["attrs"].get("clinvar_total_in_group", 0) for nid, n in vg_nodes.items()
                  if n["attrs"].get("gene") == gene}
        qa[gene] = {vg: {"this_file": mine.get(vg, 0), "graph_attrs": theirs.get(vg, 0)}
                    for vg in sorted(set(mine) | set(theirs)) if mine.get(vg, 0) != theirs.get(vg, 0)}
        genes_out[gene] = {
            "n": len(rows),
            "by_consequence": {k: cons_counts[k] for k in CONSEQ_ORDER if cons_counts[k]},
            "null_like_share": round(sum(cons_counts[k] for k in ("nonsense", "frameshift", "splice")) / max(1, len(rows)), 3),
            "recurrent_residues": [{"residue": k, "alleles": sorted(set(v))} for k, v in recurrent_res[:8]],
            "most_reported": [{"p": r["p"], "accession": r["accession"], "n_submissions": r["n_submissions"]}
                              for r in top_reported],
            "variants": [[r[f] for f in FIELDS] for r in rows],
        }
    data = {
        "meta": {
            "generated": TODAY,
            "source": "ClinVar esummary records stored by pipeline/biology/clinvar.py "
                      "(query: <GENE>[gene] AND (clinsig_pathogenic[prop] OR clinsig_likely_pathogenic[prop]))",
            "scope_note": "Only pathogenic / likely-pathogenic germline records are included. A miss means "
                          "'not among ClinVar P/LP records for this gene', NOT 'benign' and NOT 'not real'.",
            "url_template": "https://www.ncbi.nlm.nih.gov/clinvar/variation/<numeric id>/",
            "stars": "ClinVar review stars: 4 practice guideline, 3 expert panel, 2 multiple submitters no "
                     "conflicts, 1 single submitter, 0 no assertion criteria",
            "index_keys": "c:<GENE>:<c.>, p:<GENE>:<1-letter protein>, iso:<GENE>:<protein as numbered on "
                          "another isoform> -> row numbers in genes[GENE].variants",
            "spec": "data/derived/variant_lookup_spec.md",
            "qa_differences_vs_graph_group_counts": qa,
        },
        "fields": FIELDS,
        "transcript_to_gene": dict(sorted(tx2gene.items())),
        "variant_groups": sorted(vg_nodes),
        "genes": genes_out,
        "index": dict(sorted(index.items())),
    }
    size = write_json(DERIVED / "variants.json", data, compact=True)
    n = sum(v["n"] for v in genes_out.values())
    print(f"[variants] {n} P/LP variants, {len(index)} index keys, {size / 1024:.0f} KB")
    for gene, v in genes_out.items():
        print(f"  {gene:7s} n={v['n']:4d} {v['by_consequence']} recurrent={[x['residue'] for x in v['recurrent_residues'][:4]]}")
    if any(qa.values()):
        print("  QA: group counts that differ from the graph's variant_group attrs (see meta):")
        for gene, d in qa.items():
            for vg, x in d.items():
                print(f"    {vg}: here {x['this_file']} vs graph {x['graph_attrs']}")
    check_cases(data)


def check_cases(data):
    path = DERIVED / "variant_test_cases.json"
    if not path.exists():
        print("  (no test cases yet)")
        return
    cases = read_json(path)["cases"]
    bad = 0
    for case in cases:
        r = hgvs.lookup(case["query"], data)
        exp = case["expected"]
        got = {"status": r["status"]}
        if r["matches"]:
            got["gene"] = r["matches"][0]["gene"]
            got["accession"] = r["matches"][0]["accession"]
            got["consequence"] = r["matches"][0]["consequence"]
            got["variant_group"] = r["matches"][0]["variant_group"]
        if r["fallback"]:
            got["consequence"] = r["fallback"]["consequence"]
            got["variant_group"] = r["fallback"]["variant_group"]
        diffs = {k: (v, got.get(k)) for k, v in exp.items() if k in got or k in ("accession", "gene")
                 if got.get(k) != v}
        if diffs:
            bad += 1
            print(f"  FAIL {case['query']!r}: {diffs}  warnings={r['warnings']}")
    print(f"[variants] test cases: {len(cases) - bad}/{len(cases)} pass")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
