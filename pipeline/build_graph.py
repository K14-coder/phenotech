"""Merge curated fragments into data/graph.json, derive mechanism links, and validate evidence.

Inputs:  data/curated/*.json  (each {nodes, edges, clusters, gaps}; see docs/SCHEMA.md)
         data/curated/overrides.json (optional human review decisions, see below)
Outputs: data/graph.json
         data/build/report.md (validation report: what is sourced, verified, dangling or dropped)

overrides.json:
    {
      "drop_nodes": ["node id", ...],
      "drop_edges": ["edge id", ...],
      "node_patches": {"node id": {...fields to replace...}},
      "edge_patches": {"edge id": {...fields to replace..., "review": {"by", "date", "verdict", "note"}}}
    }
An edge whose review verdict is "rejected" is dropped.

Usage: python3 pipeline/build_graph.py [--derive]
  --derive  add computed shares_mechanism links and mechanism clusters even when fragments curate them
"""

import datetime
import json
import pathlib
import sys
from collections import Counter, defaultdict, deque

ROOT = pathlib.Path(__file__).resolve().parent.parent
CURATED = ROOT / "data" / "curated"
OUT_GRAPH = ROOT / "data" / "graph.json"
OUT_REPORT = ROOT / "data" / "build" / "report.md"
CROSSCHECK = ROOT / "data" / "build" / "crosscheck.json"

NODE_TYPES = {
    "disease", "gene", "variant_group", "mechanism", "phenotype", "patient_org", "asset",
    "study", "publication", "researcher", "grant", "therapy",
}
EDGE_TYPES = {
    "causes", "variant_in", "has_effect", "participates_in", "driven_by", "has_phenotype",
    "shares_mechanism", "similar_phenotype", "serves", "maintains", "covers", "studies", "tests",
    "targets", "developed_for", "candidate_for", "part_of", "works_on", "authored", "funds", "about",
    # computed disease-disease links on six mechanistic axes (pipeline/derive/mechsim.py)
    "shares_gene", "shares_pathway", "shares_tissue", "similar_mutation_spectrum", "similar_protein_fate",
    "similar_protein_structure", "shares_pharmacology", "mechanistically_similar",
}
MECHSIM_TYPES = {"shares_gene", "shares_pathway", "shares_tissue", "similar_mutation_spectrum", "similar_protein_fate",
                 "similar_protein_structure", "shares_pharmacology", "mechanistically_similar"}
LEVEL_RANK = {"hypothesis": 1, "inferred": 2, "observational": 3, "experimental": 4, "curated": 5, "clinical": 6}
NEEDS_QUOTE = {"PubMed", "Website"}


def evidence_key(ev):
    return (ev.get("source"), ev.get("ref"), (ev.get("quote") or "")[:200])


def merge_evidence(existing, incoming):
    seen = {evidence_key(e) for e in existing}
    for ev in incoming or []:
        if evidence_key(ev) not in seen:
            existing.append(ev)
            seen.add(evidence_key(ev))
    return existing


def merge_node(base, new, conflicts):
    for field in ("label", "summary"):
        if not base.get(field) and new.get(field):
            base[field] = new[field]
    names = {s.lower(): s for s in base.get("synonyms", [])}
    for s in new.get("synonyms", []):
        names.setdefault(s.lower(), s)
    names.pop((base.get("label") or "").lower(), None)
    if names:
        base["synonyms"] = sorted(names.values(), key=str.lower)
    xrefs = base.setdefault("xrefs", {})
    for db, value in (new.get("xrefs") or {}).items():
        if db not in xrefs:
            xrefs[db] = value
        elif xrefs[db] != value:
            merged = set(xrefs[db] if isinstance(xrefs[db], list) else [xrefs[db]])
            merged |= set(value if isinstance(value, list) else [value])
            xrefs[db] = sorted(merged)
    attrs = base.setdefault("attrs", {})
    for key, value in (new.get("attrs") or {}).items():
        if key not in attrs:
            attrs[key] = value
        elif attrs[key] != value:
            conflicts.append(f"node `{base['id']}` attrs.{key}: kept {attrs[key]!r}, ignored {value!r}")
    base["sources"] = merge_evidence(base.get("sources", []), new.get("sources"))
    return base


def merge_edge(base, new):
    base["evidence"] = merge_evidence(base.get("evidence", []), new.get("evidence"))
    base["counter_evidence"] = merge_evidence(base.get("counter_evidence", []), new.get("counter_evidence"))
    if LEVEL_RANK.get(new.get("evidence_level"), 0) > LEVEL_RANK.get(base.get("evidence_level"), 0):
        base["evidence_level"] = new["evidence_level"]
    base["confidence"] = max(base.get("confidence", 0), new.get("confidence", 0))
    if not base.get("explanation") and new.get("explanation"):
        base["explanation"] = new["explanation"]
    return base


def apply_node_merges(nodes, edges, clusters, gaps, merges, conflicts):
    """Fold each duplicate node into its canonical node and re-point every reference to it."""
    for old, new in merges.items():
        if old in nodes and new in nodes:
            dup = nodes.pop(old)
            dup["synonyms"] = dup.get("synonyms", []) + [dup["label"]]
            nodes[new] = merge_node(nodes[new], dup, conflicts)
    rename = lambda node_id: merges.get(node_id, node_id)
    merged, id_map = {}, {}
    for e in edges.values():
        e = dict(e, source=rename(e["source"]), target=rename(e["target"]))
        if e["source"] == e["target"]:
            continue
        new_id = f"{e['source']}|{e['type']}|{e['target']}"
        id_map[e["id"]] = new_id
        e["id"] = new_id
        merged[new_id] = merge_edge(merged[new_id], e) if new_id in merged else e
    for c in clusters:
        c["members"] = list(dict.fromkeys(rename(m) for m in c["members"]))
        c["edge_ids"] = list(dict.fromkeys(id_map.get(x, x) for x in c.get("edge_ids", [])))
    for gap in gaps:
        gap["about"] = rename(gap.get("about"))
    return merged, clusters, gaps


def apply_crosscheck(edges, today):
    """Apply the independent OpenAI reading of each paper (data/build/crosscheck.json).

    Evidence the curators already cited gets a cross_checked stamp saying whether the model agreed.
    Papers the curators didn't cite are added: supporting ones as evidence, contradicting ones as
    counter-evidence marked needs_review.
    """
    if not CROSSCHECK.exists():
        return 0, 0, 0
    data = json.loads(CROSSCHECK.read_text())
    by = f"openai:{data.get('model', 'unknown')}"
    checked_on = (data.get("generated_at") or today)[:10]
    marked = added_support = added_contra = 0
    for edge_id, items in data.get("edges", {}).items():
        edge = edges.get(edge_id)
        if not edge:
            continue
        for item in items:
            existing = [
                ev for ev in edge.get("evidence", []) + edge.get("counter_evidence", [])
                if ev.get("ref") == item.get("ref")
            ]
            for ev in existing:
                ev["cross_checked"] = {"by": by, "agrees": bool(item.get("agrees")), "date": checked_on}
            if existing:
                marked += 1
                continue
            new_ev = {
                "source": "PubMed",
                "ref": item["ref"],
                "url": item.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{item['ref'].split(':')[-1]}/",
                "title": item.get("title"),
                "year": item.get("year"),
                "quote": item.get("quote"),
                "kind": "publication",
                "study_type": item.get("study_type"),
                "extracted_by": by,
                "verified": True,
                "retrieved": checked_on,
            }
            if item.get("agrees"):
                edge.setdefault("evidence", []).append(new_ev)
                added_support += 1
            else:
                new_ev["supports"] = False
                new_ev["needs_review"] = True
                edge.setdefault("counter_evidence", []).append(new_ev)
                added_contra += 1
    return marked, added_support, added_contra


def load_fragments():
    fragments = []
    for path in sorted(CURATED.glob("*.json")):
        if path.name == "overrides.json":
            continue
        data = json.loads(path.read_text())
        if isinstance(data, dict) and ("nodes" in data or "edges" in data):
            fragments.append((path.name, data))
    overrides_path = CURATED / "overrides.json"
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    return fragments, overrides


def mechanism_support(nodes, edges):
    """For each disease, the mechanisms it reaches and the edges that support each one."""
    by_type = defaultdict(list)
    for e in edges.values():
        by_type[e["type"]].append(e)
    genes_of_disease = defaultdict(list)
    for e in by_type["causes"]:
        genes_of_disease[e["target"]].append(e)
    vgs_of_gene = defaultdict(list)
    for e in by_type["variant_in"]:
        vgs_of_gene[e["target"]].append(e)
    out = defaultdict(lambda: defaultdict(list))  # disease -> mech -> [supporting edges]

    for e in by_type["driven_by"]:
        out[e["source"]][e["target"]].append([e])
    for disease, cause_edges in genes_of_disease.items():
        for cause in cause_edges:
            gene = cause["source"]
            for e in by_type["participates_in"]:
                if e["source"] == gene:
                    out[disease][e["target"]].append([cause, e])
            for vg_edge in vgs_of_gene.get(gene, []):
                for e in by_type["has_effect"]:
                    if e["source"] == vg_edge["source"]:
                        out[disease][e["target"]].append([cause, vg_edge, e])
    return {
        d: {m: chains for m, chains in mechs.items() if nodes.get(m, {}).get("type") == "mechanism"}
        for d, mechs in out.items()
        if nodes.get(d, {}).get("type") == "disease"
    }


def derive_shared_mechanism_edges(nodes, edges, today):
    support = mechanism_support(nodes, edges)
    diseases = sorted(support)
    derived = []
    for i, a in enumerate(diseases):
        for b in diseases[i + 1:]:
            shared = sorted(set(support[a]) & set(support[b]))
            if not shared:
                continue
            edge_id = f"{a}|shares_mechanism|{b}"
            reverse_id = f"{b}|shares_mechanism|{a}"
            if edge_id in edges or reverse_id in edges:
                continue
            evidence, weakest = [], 1.0
            for mech in shared:
                for disease in (a, b):
                    chain = max(support[disease][mech], key=lambda c: min(x.get("confidence", 0) for x in c))
                    weakest = min(weakest, min(x.get("confidence", 0) for x in chain))
                    for supporting in chain:
                        evidence.append({
                            "source": "Atlas",
                            "ref": supporting["id"],
                            "url": f"/path?from={disease}&to={mech}",
                            "title": supporting.get("explanation", supporting["id"]),
                            "kind": "computed",
                            "extracted_by": "computed",
                            "retrieved": today,
                        })
            kinds = {nodes[m].get("attrs", {}).get("kind") for m in shared}
            labels = ", ".join(nodes[m]["label"] for m in shared)
            derived.append({
                "id": edge_id,
                "source": a,
                "target": b,
                "type": "shares_mechanism",
                "label": "shares mechanism with",
                "explanation": (
                    f"{nodes[a]['label']} and {nodes[b]['label']} both involve: {labels}. "
                    "The atlas inferred this by combining the linked evidence; no single study compared them directly."
                ),
                "evidence_level": "inferred",
                "status": "supported",
                "confidence": round(0.3 + 0.19 * weakest, 2),
                "evidence": merge_evidence([], evidence),
                "attrs": {
                    "shared": shared,
                    "basis": "both" if kinds >= {"effect", "process"} else (kinds.pop() if len(kinds) == 1 else "mixed"),
                },
            })
    return derived


def derive_clusters(nodes, edges, existing):
    """Add one cluster per effect mechanism that two or more diseases share, unless one exists."""
    support = mechanism_support(nodes, edges)
    covered = {frozenset(c["members"]) for c in existing}
    members_by_mech = defaultdict(set)
    for disease, mechs in support.items():
        for mech in mechs:
            members_by_mech[mech].add(disease)
    clusters = []
    for mech, members in sorted(members_by_mech.items()):
        if len(members) < 2 or nodes[mech].get("attrs", {}).get("kind") != "effect":
            continue
        if frozenset(members) in covered:
            continue
        edge_ids = sorted({x["id"] for d in members for chain in support[d][mech] for x in chain})
        clusters.append({
            "id": f"cluster:{mech.split(':', 1)[1]}",
            "label": nodes[mech]["label"],
            "basis": "mechanism",
            "members": sorted(members),
            "rationale": f"These diseases share the same molecular effect: {nodes[mech]['label']}.",
            "edge_ids": edge_ids,
        })
    return clusters


def betweenness(nodes, edges):
    """Brandes betweenness on the undirected graph, ignoring publication nodes; 0–100 percentile."""
    ids = [n for n, v in nodes.items() if v["type"] != "publication"]
    keep = set(ids)
    adj = defaultdict(set)
    for e in edges.values():
        if e["source"] in keep and e["target"] in keep:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])
    score = dict.fromkeys(ids, 0.0)
    for s in ids:
        stack, preds = [], defaultdict(list)
        sigma, dist = defaultdict(float), {}
        sigma[s], dist[s] = 1.0, 0
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj[v]:
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                score[w] += delta[w]
    ranked = sorted(ids, key=lambda n: score[n])
    return {n: round(100 * i / max(1, len(ranked) - 1)) for i, n in enumerate(ranked)}


def validate(nodes, edges):
    problems = defaultdict(list)
    for n in nodes.values():
        if n.get("type") not in NODE_TYPES:
            problems["unknown node type"].append(f"`{n['id']}` ({n.get('type')})")
        if not n.get("label"):
            problems["node without label"].append(f"`{n['id']}`")
    for e in edges.values():
        if e["type"] not in EDGE_TYPES:
            problems["unknown edge type (kept)"].append(f"`{e['id']}`")
        if not e.get("evidence") and e.get("evidence_level") != "hypothesis":
            problems["edge without evidence"].append(f"`{e['id']}`")
        if not 0 <= e.get("confidence", -1) <= 1:
            problems["confidence outside 0–1"].append(f"`{e['id']}`")
        for ev in e.get("evidence", []) + e.get("counter_evidence", []):
            if ev.get("source") in NEEDS_QUOTE and not ev.get("quote"):
                problems["PubMed/Website evidence without a quote"].append(f"`{e['id']}` ← {ev.get('ref')}")
            if not ev.get("url"):
                problems["evidence without a url"].append(f"`{e['id']}` ← {ev.get('ref')}")
    return problems


def main():
    today = datetime.date.today().isoformat()
    fragments, overrides = load_fragments()
    nodes, edges, clusters, gaps, conflicts = {}, {}, [], [], []
    per_fragment = []

    for name, data in fragments:
        per_fragment.append((name, len(data.get("nodes", [])), len(data.get("edges", []))))
        for n in data.get("nodes", []):
            nodes[n["id"]] = merge_node(nodes[n["id"]], n, conflicts) if n["id"] in nodes else json.loads(json.dumps(n))
        for e in data.get("edges", []):
            e = json.loads(json.dumps(e))
            e["id"] = e.get("id") or f"{e['source']}|{e['type']}|{e['target']}"
            edges[e["id"]] = merge_edge(edges[e["id"]], e) if e["id"] in edges else e
        clusters.extend(data.get("clusters", []))
        gaps.extend(data.get("gaps", []))

    # Duplicate nodes from different layers (e.g. a drug under its brand and generic name)
    merges = overrides.get("merge_nodes", {})
    if merges:
        edges, clusters, gaps = apply_node_merges(nodes, edges, clusters, gaps, merges, conflicts)

    # Human review decisions
    for node_id in overrides.get("drop_nodes", []):
        nodes.pop(node_id, None)
    for node_id, patch in overrides.get("node_patches", {}).items():
        if node_id in nodes:
            nodes[node_id].update({k: v for k, v in patch.items() if not k.startswith("_")})
    rejected = set(overrides.get("drop_edges", []))
    for edge_id, patch in overrides.get("edge_patches", {}).items():
        if edge_id in edges:
            edges[edge_id].update(patch)
            if patch.get("review", {}).get("verdict") == "rejected":
                rejected.add(edge_id)
    for edge_id in rejected:
        edges.pop(edge_id, None)

    # Referential integrity
    dangling = [e for e in edges.values() if e["source"] not in nodes or e["target"] not in nodes]
    for e in dangling:
        edges.pop(e["id"])

    marked, added_support, added_contra = apply_crosscheck(edges, today)

    # Status follows the evidence: reviewed counter-evidence makes an edge contested. Contradictions
    # that only the OpenAI cross-check found wait for human review first.
    for e in edges.values():
        if not e.get("counter_evidence"):
            e.pop("counter_evidence", None)
        elif e.get("status") == "supported" and any(not ev.get("needs_review") for ev in e["counter_evidence"]):
            e["status"] = "contested"
        e.setdefault("status", "unverified")

    # Derived links and clusters fill in only when no fragment curated them, because nearly every
    # disease here has some variant with each effect, and deriving anyway would link everything.
    if "--derive" in sys.argv or not any(e["type"] == "shares_mechanism" for e in edges.values()):
        for e in derive_shared_mechanism_edges(nodes, edges, today):
            edges[e["id"]] = e
    if "--derive" in sys.argv or not clusters:
        clusters = clusters + derive_clusters(nodes, edges, clusters)

    seen_cluster_ids = set()
    merged_clusters = []
    for c in clusters:
        if c["id"] not in seen_cluster_ids:
            c["members"] = [m for m in c["members"] if m in nodes]
            c["edge_ids"] = [x for x in c.get("edge_ids", []) if x in edges]
            merged_clusters.append(c)
            seen_cluster_ids.add(c["id"])

    # computed mechanistic-similarity links are an optional overlay: they must not change node sizes
    curated_edges = {k: e for k, e in edges.items() if e["type"] not in MECHSIM_TYPES}
    for node_id, value in betweenness(nodes, curated_edges).items():
        nodes[node_id].setdefault("attrs", {})["centrality"] = value

    source_dates = defaultdict(set)
    for item in list(edges.values()) + list(nodes.values()):
        for ev in item.get("evidence", []) + item.get("counter_evidence", []) + item.get("sources", []):
            if ev.get("source") and ev.get("retrieved"):
                source_dates[ev["source"]].add(ev["retrieved"])

    graph = {
        "meta": {
            "version": "0.1",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "slice": "SNAREopathies (synaptic vesicle fusion disorders) and mechanism bridges",
            "sources": [
                {"name": name, "version_or_date": f"retrieved {min(dates)} to {max(dates)}" if len(dates) > 1 else f"retrieved {min(dates)}", "url": ""}
                for name, dates in sorted(source_dates.items())
            ],
        },
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["id"])),
        "edges": sorted(edges.values(), key=lambda e: e["id"]),
        "clusters": merged_clusters,
        "gaps": gaps,
    }
    OUT_GRAPH.write_text(json.dumps(graph, indent=1, ensure_ascii=False))

    # Report
    problems = validate(nodes, edges)
    all_evidence = [ev for e in edges.values() for ev in e.get("evidence", [])]
    quoted = [ev for ev in all_evidence if ev.get("quote")]
    verified = [ev for ev in quoted if ev.get("verified")]
    sourced = [e for e in edges.values() if e.get("evidence")]
    lines = [
        "# Graph build report",
        "",
        f"Built {graph['meta']['generated_at']} from {', '.join(f'`{n}`' for n, _, _ in per_fragment) or 'no fragments'}.",
        "",
        "## Summary",
        "",
        f"- **{len(nodes)} nodes, {len(edges)} edges, {len(merged_clusters)} clusters, {len(gaps)} gaps**",
        f"- Edges with at least one source: **{len(sourced)}/{len(edges)}**",
        f"- Evidence items with a verbatim quote: {len(quoted)}/{len(all_evidence)}; quotes string-verified against the stored source: **{len(verified)}/{len(quoted)}**",
        f"- Contested edges (with counter-evidence): {sum(1 for e in edges.values() if e['status'] == 'contested')}",
        f"- OpenAI cross-check: {marked} cited sources re-read and stamped; {added_support} new supporting and "
        f"{added_contra} new contradicting sources added (contradictions wait for human review)",
        f"- Cited sources where the OpenAI reading disagrees with the curators: "
        f"{sum(1 for e in edges.values() for ev in e.get('evidence', []) + e.get('counter_evidence', []) if ev.get('cross_checked', {}).get('agrees') is False)}",
        f"- Human-reviewed edges: {sum(1 for e in edges.values() if e.get('review'))}",
        f"- Dropped by review: {len(rejected)}; dropped as dangling: {len(dangling)}",
        "",
        "## Fragments",
        "",
        "| File | Nodes | Edges |",
        "|---|---|---|",
        *[f"| `{n}` | {nn} | {ne} |" for n, nn, ne in per_fragment],
        "",
        "## Nodes by type",
        "",
        *[f"- {t}: {c}" for t, c in Counter(n["type"] for n in nodes.values()).most_common()],
        "",
        "## Edges by type",
        "",
        *[f"- {t}: {c}" for t, c in Counter(e["type"] for e in edges.values()).most_common()],
        "",
        "## Edges by evidence level",
        "",
        *[f"- {t}: {c}" for t, c in Counter(e.get("evidence_level") for e in edges.values()).most_common()],
        "",
        "## Problems",
        "",
    ]
    if not problems and not dangling:
        lines.append("None.")
    for kind, items in problems.items():
        lines += [f"### {kind} ({len(items)})", "", *[f"- {i}" for i in items[:40]], ""]
    if dangling:
        lines += [f"### Dangling edges dropped ({len(dangling)})", "", *[f"- `{e['id']}`" for e in dangling[:40]], ""]
    if conflicts:
        lines += [f"### Attribute conflicts ({len(conflicts)})", "", *[f"- {c}" for c in conflicts[:40]], ""]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines) + "\n")

    print(f"{len(nodes)} nodes, {len(edges)} edges, {len(merged_clusters)} clusters, {len(gaps)} gaps")
    print(f"sourced edges {len(sourced)}/{len(edges)}, verified quotes {len(verified)}/{len(quoted)}")
    print(f"wrote {OUT_GRAPH.relative_to(ROOT)} and {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
