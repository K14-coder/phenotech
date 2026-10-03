"""Global disease index: every disease with HPO annotations or a gene association becomes findable.

Run:  uv run --with numpy --with scipy python3 pipeline/derive/global_index.py
In:   data/raw/downloads/mondo-base.obo        (MONDO release: names, EXACT synonyms, equivalentTo xrefs)
      data/raw/downloads/{phenotype.hpoa, hp.obo, genes_to_disease.txt}
      data/raw/biology/hpo_stats.json          (profile entities of the 11 atlas umbrella diseases)
      data/graph.json                          (disease nodes -> MONDO xrefs, for in_atlas)
Out:  data/derived/global/index.json           search index, one row per disease (compact arrays)
      data/derived/global/neighbours/<b>.json  64 shards, b = djb2(MONDO id) % 64
      data/derived/global/meta.json            counts, versions, URL templates, caveat, calibration
      (README.md in the same folder documents the schema, the hash and how the UI should use it)

Method
  Identity: OMIM and ORPHA ids are merged into ONE entry through MONDO's xrefs that carry
    source="MONDO:equivalentTo" (exact matches only). An id MONDO does not map keeps its native id.
  IC: exactly pipeline/biology/hpo.py (imported): IC(t) = -ln(n diseases annotated to t or a
    descendant / N) over all phenotype.hpoa entries, aspect P, NOT rows dropped, is_a propagation.
  Similarity: IC-weighted cosine over ancestor-propagated profiles. Each disease is the vector
    w_t = IC(t) over every term in its propagated set; cosine = sum_shared IC^2 / (|a| |b|).
    Unlike Resnik BMA this does not reward one rare term matched inside a large profile, and broad
    ancestors (IC ~ 0) contribute nothing by construction.
  Neighbours: diseases with >= 5 annotated phenotype terms; QTL / susceptibility loci are never
    listed as neighbours. Percentile = share of the comparison pool scoring lower than this pair,
    within the query disease's own row.
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict

import numpy as np
import scipy.sparse as sp

from dcommon import BIO_RAW, DOWNLOADS, ROOT, SLICE_GENES, TODAY, Graph, read_json, write_json

sys.path.append(str(ROOT / "pipeline" / "biology"))
import hpo  # noqa: E402  (biology layer: parse_obo, ancestors_fn, parse_hpoa, IC thresholds)

OUT = ROOT / "data" / "derived" / "global"
SHARDS = OUT / "neighbours"
MONDO_OBO = DOWNLOADS / "mondo-base.obo"
N_BUCKETS = 64
MIN_TERMS = 5
TOP_NEIGHBOURS = 10
TOP_OWN = 8
TOP_SHARED = 3
TOP_ATLAS = 3
MAX_SYNONYMS = 4
EXCLUDE_AS_NEIGHBOUR = re.compile(r"\bQTL|susceptibility", re.I)
CAVEAT = "phenotype similarity only; no evidence curation; mechanism not assessed"
# Reproducible sanity checks recorded in meta.json: the rank of clinically expected neighbours.
SANITY = {
    "MONDO:0007739": ["MONDO:0011671", "MONDO:0011299", "MONDO:0011781", "MONDO:0007435"],  # HD: JPH3, PRNP, TBP, ATN1
    "MONDO:0009061": ["MONDO:0013087", "MONDO:0032872", "MONDO:0010220"],  # CF: SCNN1A, PCD42, Young syndrome
    "MONDO:0010679": ["MONDO:0010311", "MONDO:0011968", "MONDO:0011787"],  # DMD: Becker, SGCA, FKRP
    "MONDO:0100135": ["MONDO:0100079", "MONDO:0011461", "MONDO:0033361"],  # Dravet: DEE6A, GEFS+2, SCN1B
}
FAR_TEXT = ("No phenotype overlap with any of the mapped deep-atlas diseases reaches the calibrated threshold: "
            "different mechanism family, most likely (phenotype similarity only; mechanism not assessed).")


def djb2(s: str) -> int:
    """Classic djb2 (h = h*33 + c, seed 5381) kept to unsigned 32 bits after every step.
    TypeScript: let h = 5381; for (const ch of s) h = (Math.imul(h, 33) + ch.charCodeAt(0)) >>> 0;"""
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def bucket(disease_id: str) -> int:
    return djb2(disease_id) % N_BUCKETS


def parse_mondo():
    terms, cur, version = {}, None, None
    with MONDO_OBO.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("data-version:"):
                version = line.split(": ", 1)[1]
            if line == "[Term]":
                cur = {"syn": [], "xref": [], "obsolete": False}
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = None
                continue
            if cur is None:
                continue
            if not line:
                if "id" in cur:
                    terms[cur["id"]] = cur
                cur = None
                continue
            k, _, v = line.partition(": ")
            if k == "id":
                cur["id"] = v
            elif k == "name":
                cur["name"] = v
            elif k == "synonym":
                m = re.match(r'"((?:[^"\\]|\\.)*)"\s+(\w+)(?:\s+(\w+))?', v)
                if m and m.group(2) == "EXACT":
                    cur["syn"].append((m.group(1).replace('\\"', '"'), m.group(3) or ""))
            elif k == "xref":
                m = re.match(r"(\S+)(?:\s+\{(.*)\})?", v)
                q = (m.group(2) or "") if m else ""
                if m and "MONDO:equivalentTo" in q:
                    cur["xref"].append(m.group(1))
                elif m and "MONDO:obsoleteEquivalent" in q:
                    cur.setdefault("xref_obsolete", []).append(m.group(1))
            elif k == "replaced_by":
                cur["replaced_by"] = v
            elif k == "is_obsolete" and v == "true":
                cur["obsolete"] = True
    if cur and "id" in cur:
        terms[cur["id"]] = cur
    return terms, version


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def pick_synonyms(name: str, syns):
    """Up to 4 EXACT synonyms that add search value: case-insensitive duplicates of the name or of
    each other are dropped; abbreviations are kept first (HD, CF, DMD are what people type)."""
    seen = {name.lower()}
    abbr, rest = [], []
    for text, kind in syns:
        if text.lower() in seen:
            continue
        if len(text) > 60 or (re.search(r"modifier|susceptib", text, re.I)
                              and not re.search(r"modifier|susceptib", name, re.I)):
            continue
        seen.add(text.lower())
        (abbr if kind == "ABBREVIATION" else rest).append(text)
    rest.sort(key=lambda s: (len(s), s))
    return (abbr[:2] + rest)[:MAX_SYNONYMS]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    SHARDS.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- HPO (biology layer parsers)
    hterms, alt_map, hpo_version = hpo.parse_obo()
    anc = hpo.ancestors_fn(hterms)
    rows, hpoa_version = hpo.parse_hpoa(alt_map, hterms)
    direct_raw, inh_raw, raw_name = defaultdict(set), defaultdict(set), {}
    for r in rows:
        if r["qualifier"] == "NOT":
            continue
        raw_name.setdefault(r["database_id"], r["disease_name"])
        if r["aspect"] == "P":
            direct_raw[r["database_id"]].add(r["hpo_id"])
        elif r["aspect"] == "I":
            inh_raw[r["database_id"]].add(r["hpo_id"])
    prop_raw = {d: frozenset().union(*(anc(t) for t in ts)) for d, ts in direct_raw.items()}
    n_ic = len(direct_raw)
    counts = defaultdict(int)
    for ps in prop_raw.values():
        for t in ps:
            counts[t] += 1
    ic = {t: -math.log(c / n_ic) for t, c in counts.items()}

    genes_raw = defaultdict(set)
    for line in (DOWNLOADS / "genes_to_disease.txt").read_text().splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 4 and f[1]:
            genes_raw[f[3]].add((f[1], f[2]))

    # ---------------------------------------------------------------- MONDO identity
    mondo, mondo_version = parse_mondo()
    xmap = {}
    for mid, t in mondo.items():
        if t["obsolete"] or not mid.startswith("MONDO:"):
            continue
        for x in t["xref"]:
            if x.startswith("OMIM:") or x.startswith("Orphanet:"):
                xmap.setdefault(x.replace("Orphanet:", "ORPHA:"), mid)
    how_mapped = {x: "equivalentTo" for x in xmap}
    # an id whose only MONDO match is an OBSOLETE term follows that term's replaced_by
    # (e.g. ORPHA:33069 Dravet syndrome -> obsolete MONDO:0011794 -> MONDO:0100135)
    for mid, t in mondo.items():
        tgt = t.get("replaced_by")
        if not (t["obsolete"] and tgt and tgt in mondo and not mondo[tgt]["obsolete"]):
            continue
        for x in t["xref"] + t.get("xref_obsolete", []):
            if x.startswith(("OMIM:", "Orphanet:")):
                key = x.replace("Orphanet:", "ORPHA:")
                if key not in xmap:
                    xmap[key], how_mapped[key] = tgt, "obsolete_replaced_by"
    raw_ids = set(direct_raw) | set(genes_raw) | set(inh_raw)
    raw_ids = {d for d in raw_ids if d.startswith(("OMIM:", "ORPHA:"))}   # DECIPHER ids are left out
    # last resort: the source's disease name equals exactly ONE live MONDO name or EXACT synonym
    by_name = defaultdict(set)
    for mid, t in mondo.items():
        if t["obsolete"] or not mid.startswith("MONDO:"):
            continue
        for label in [t.get("name", "")] + [x for x, _k in t["syn"]]:
            if label:
                by_name[norm(label)].add(mid)
    for d in raw_ids:
        if d not in xmap and d in raw_name:
            cands = by_name.get(norm(raw_name[d]), set())
            if len(cands) == 1:
                xmap[d], how_mapped[d] = next(iter(cands)), "exact_name"
    groups = defaultdict(set)
    for d in raw_ids:
        groups[xmap.get(d, d)].add(d)
    mapped_counts = defaultdict(int)
    for d in raw_ids:
        mapped_counts[how_mapped.get(d, "unmapped")] += 1
    n_unmapped = sum(1 for k in groups if not k.startswith("MONDO:"))

    # ---------------------------------------------------------------- atlas mapping
    g = Graph()
    profiles = read_json(BIO_RAW / "hpo_stats.json")["profiles"]
    # every deep-atlas disease in the graph (all families), not only the original 11. The original
    # 11 keep the biology layer's curated profile entities; the others use their OMIM/ORPHA xrefs and
    # subtypes that carry HPO annotations.
    ATLAS = sorted(n_["id"].split(":", 1)[1] for n_ in g.nodes.values()
                   if n_["type"] == "disease" and n_["id"].startswith("disease:"))
    for sym in ATLAS:
        if sym in profiles:
            continue
        dn = g.nodes[f"disease:{sym}"]
        ents = set()
        for src in [dn.get("xrefs", {}) or {}] + list((dn.get("attrs", {}) or {}).get("subtypes", []) or []):
            for k_, pre in (("OMIM", "OMIM:"), ("ORPHA", "ORPHA:")):
                v_ = src.get(k_)
                for x_ in ([v_] if isinstance(v_, str) else (v_ or [])):
                    x_ = str(x_).replace("Orphanet:", "").replace("ORPHA:", "").replace("OMIM:", "")
                    ents.add(pre + x_)
        ents = sorted(ents)
        profiles[sym] = {"entities": ents, "annotated_entities": [e for e in ents if direct_raw.get(e)]}
    atlas_of = {}
    for sym in ATLAS:
        dn = g.nodes.get(f"disease:{sym}", {})
        mids = list(dn.get("xrefs", {}).get("MONDO", []) or [])
        mids += [s.get("MONDO") for s in dn.get("attrs", {}).get("subtypes", []) if s.get("MONDO")]
        for m in mids:
            for mm in (m if isinstance(m, list) else [m]):
                atlas_of[mm] = f"disease:{sym}"
        for e in profiles.get(sym, {}).get("entities", []):
            atlas_of[xmap.get(e, e)] = f"disease:{sym}"
    slice_set = set(ATLAS)
    profile_keys = {xmap.get(e, e) for p_ in profiles.values() for e in p_.get("entities", [])}
    subtype_name = {}
    for sym in ATLAS:
        for st in g.nodes.get(f"disease:{sym}", {}).get("attrs", {}).get("subtypes", []):
            for k_, pre in (("OMIM", "OMIM:"), ("ORPHA", "ORPHA:")):
                for v_ in ([st.get(k_)] if isinstance(st.get(k_), str) else (st.get(k_) or [])):
                    if v_ and st.get("name"):
                        subtype_name[v_ if str(v_).startswith(pre) else f"{pre}{v_}"] = st["name"]

    def atlas_ok(key, ids, sym):
        """in_atlas only for the curated profile entities or single-gene entries of that slice gene, so
        multi-gene clinical groups (GEFS+, non-syndromic ID) never land on a gene-specific atlas page."""
        if key in profile_keys:
            return True
        mend = {s_ for d in ids for s_, a in genes_raw.get(d, ()) if a == "MENDELIAN"}
        orph = {s_ for d in ids for s_, a in genes_raw.get(d, ()) if a == "UNKNOWN"}
        gene_set = mend or orph
        return gene_set == {sym}

    for key, ids in groups.items():
        sym = atlas_of.get(key, "disease:").split(":")[1]
        if key in atlas_of and not atlas_ok(key, ids, sym):
            del atlas_of[key]
        mendelian = {s_ for d in ids for s_, a in genes_raw.get(d, ()) if a == "MENDELIAN"}
        if key not in atlas_of and len(mendelian) == 1 and mendelian <= slice_set:
            atlas_of[key] = f"disease:{next(iter(mendelian))}"

    # ---------------------------------------------------------------- entries
    entries, dropped_no_name = {}, 0
    for key, ids in groups.items():
        mt = mondo.get(key)
        direct = set().union(*(direct_raw.get(d, set()) for d in ids))
        inh = set().union(*(inh_raw.get(d, set()) for d in ids))
        # OMIM/mim2gene MENDELIAN genes when present; otherwise Orphanet genes (genes_to_disease.txt does
        # not carry Orphanet's association type, so these may include modifiers); POLYGENIC never.
        mend = sorted({s for d in ids for s, a in genes_raw.get(d, ()) if a == "MENDELIAN"})
        orph = sorted({s for d in ids for s, a in genes_raw.get(d, ()) if a == "UNKNOWN"})
        gs, gsrc = (mend, 1) if mend else ((orph, 2) if orph else ([], 0))
        if mt:
            name = mt.get("name", key)
            syns = pick_synonyms(name, mt["syn"])
            omim = sorted({x.split(":")[1] for x in mt["xref"] if x.startswith("OMIM:")} |
                          {d.split(":")[1] for d in ids if d.startswith("OMIM:")})
            orpha = sorted({x.split(":")[1] for x in mt["xref"] if x.startswith("Orphanet:")} |
                           {d.split(":")[1] for d in ids if d.startswith("ORPHA:")})
        else:
            name = next((raw_name[d] for d in sorted(ids) if d in raw_name), None) or \
                next((subtype_name[d] for d in sorted(ids) if d in subtype_name), None)
            if not name:
                dropped_no_name += 1
                continue
            syns, omim, orpha = [], sorted(d.split(":")[1] for d in ids if d.startswith("OMIM:")), \
                sorted(d.split(":")[1] for d in ids if d.startswith("ORPHA:"))
        entries[key] = {"id": key, "name": name, "syn": syns, "omim": omim, "orpha": orpha, "genes": gs,
                        "gsrc": gsrc, "n": len(direct), "atlas": atlas_of.get(key), "direct": direct,
                        "inh": inh, "raw": sorted(ids)}

    # ---------------------------------------------------------------- vectors
    q_ids = sorted(k for k, e in entries.items() if e["n"] >= MIN_TERMS)
    prop = {k: frozenset().union(*(anc(t) for t in entries[k]["direct"])) for k in q_ids}
    term_ix = {}
    for k in q_ids:
        for t in prop[k]:
            if ic.get(t, 0) > 0 and t not in term_ix:
                term_ix[t] = len(term_ix)

    def matrix(profile_sets):
        r, c, v = [], [], []
        for i, ps in enumerate(profile_sets):
            for t in ps:
                j = term_ix.get(t)
                if j is not None:
                    r.append(i)
                    c.append(j)
                    v.append(ic[t])
        m = sp.csr_matrix((np.array(v, dtype=np.float32), (r, c)), shape=(len(profile_sets), len(term_ix)))
        norms = np.sqrt(np.asarray(m.multiply(m).sum(axis=1)).ravel())
        norms[norms == 0] = 1
        return sp.diags(1 / norms).dot(m).tocsr()

    def centroid(groups_of_raw):
        """One vector per merged disease = mean of its sources' normalised vectors, re-normalised.
        Union-merging lets one source's idiosyncratic annotation style dominate (ORPHA:399 adds a
        block of behavioural terms to Huntington disease); the centroid weighs each source equally."""
        flat, owner = [], []
        for i, raws in enumerate(groups_of_raw):
            srcs = [d for d in raws if direct_raw.get(d)]
            for d in srcs:
                flat.append(prop_raw[d])
                owner.append((i, 1.0 / len(srcs)))
        R = matrix(flat)
        M = sp.csr_matrix(([w for _i, w in owner], ([i for i, _w in owner], list(range(len(owner))))),
                          shape=(len(groups_of_raw), len(flat)))
        Y = (M @ R).tocsr()
        norms = np.sqrt(np.asarray(Y.multiply(Y).sum(axis=1)).ravel())
        norms[norms == 0] = 1
        return sp.diags(1 / norms).dot(Y).tocsr()

    X = centroid([entries[k]["raw"] for k in q_ids])
    pool_mask = np.array([not EXCLUDE_AS_NEIGHBOUR.search(entries[k]["name"]) for k in q_ids])
    pool_idx = np.where(pool_mask)[0]
    XP = X[pool_idx].T.tocsc()

    def shared_top(a_prop, b_prop, k=TOP_SHARED):
        """Most informative shared terms, no term that is an ancestor of one already chosen."""
        out = []
        for t in sorted(a_prop & b_prop, key=lambda t: (-ic.get(t, 0), t)):
            if ic.get(t, 0) <= 0:
                break
            if any(t in anc(u) for u in out):
                continue
            out.append(t)
            if len(out) == k:
                break
        return out

    def own_top(direct, k=TOP_OWN):
        out = []
        for t in sorted(direct, key=lambda t: (-ic.get(t, 0), t)):
            if any(t in anc(u) for u in out):
                continue
            out.append(t)
            if len(out) == k:
                break
        return out

    # ---------------------------------------------------------------- atlas umbrellas
    umb = [s for s in ATLAS if profiles.get(s, {}).get("annotated_entities")]
    umb_prop = []
    for s in umb:
        d = set().union(*(direct_raw[e] for e in profiles[s]["annotated_entities"]))
        umb_prop.append(frozenset().union(*(anc(t) for t in d)))
    U = centroid([profiles[s]["annotated_entities"] for s in umb])
    A = (X @ U.T).toarray()                                     # q x umbrellas
    slice_rows = np.array([entries[k]["atlas"] is not None for k in q_ids])
    bg = A[pool_mask & ~slice_rows]                             # background: non-slice comparable diseases
    bg_sorted = np.sort(bg, axis=0)
    # Calibration of "near": the atlas's own curated similar_phenotype edges are the in-family positives.
    # T = the LOWEST cosine among those pairs, i.e. "at least as similar to an atlas disease as the
    # least-similar pair the atlas itself links". Per-umbrella percentiles were rejected: the background
    # is dense in epilepsies and sparse in myasthenias, so the same percentile means different things.
    UU = (U @ U.T).toarray()
    upos = {f"disease:{s}": i for i, s in enumerate(umb)}
    fam = []
    for e in g.edges_of("similar_phenotype"):
        if e["source"] in upos and e["target"] in upos:
            fam.append((e["id"], float(UU[upos[e["source"]], upos[e["target"]]])))
    fam.sort(key=lambda x: x[1])
    # Trimmed minimum: the weakest curated pair after dropping the lowest 5% of pairs. With all four
    # families the literal minimum (NPC1-ARSA 0.129) is one of four lysosomal pairs that link visceral
    # to neurological subtypes, and it would call 74% of all diseases "near" - no longer informative.
    TRIM = int(round(0.05 * len(fam)))
    T_NEAR = round(fam[TRIM][1], 4)
    bgn = A[pool_mask & ~slice_rows]
    cal = {
        "in_family_pairs": [{"edge": eid, "cosine": round(c, 4)} for eid, c in fam],
        "chosen_threshold": T_NEAR,
        "chosen_rule": f"weakest curated similar_phenotype pair after trimming the lowest 5% ({TRIM} of {len(fam)} "
                       f"pairs); the untrimmed minimum is reported as literal_minimum",
        "literal_minimum": {"edge": fam[0][0], "cosine": round(fam[0][1], 4),
                            "share_near_any": round(float((bgn >= fam[0][1]).any(axis=1).mean()), 4)},
        "trimmed_pairs": [{"edge": e_, "cosine": round(c_, 4)} for e_, c_ in fam[:TRIM]],
        "share_of_comparable_non_slice_diseases_near_any": round(float((bgn >= T_NEAR).any(axis=1).mean()), 4),
        "alternatives_considered": {
            f"median_in_family_{round(float(np.median([c for _e, c in fam])), 4)}":
                round(float((bgn >= np.median([c for _e, c in fam])).any(axis=1).mean()), 4),
            "per_umbrella_p99": round(float((bgn >= np.quantile(bg, 0.99, axis=0)).any(axis=1).mean()), 4),
        },
    }
    thr = np.full(len(umb), T_NEAR)

    # ---------------------------------------------------------------- neighbours (block product)
    shards = defaultdict(dict)
    shard_terms = defaultdict(set)
    sanity = {}
    n_pool = len(pool_idx)
    pos_in_pool = {int(ix): j for j, ix in enumerate(pool_idx)}
    BLOCK = 1500
    for start in range(0, len(q_ids), BLOCK):
        blk = (X[start:start + BLOCK] @ XP).toarray()           # block x pool
        for r in range(blk.shape[0]):
            qi = start + r
            row = blk[r]
            if qi in pos_in_pool:
                row[pos_in_pool[qi]] = -1.0                       # never your own neighbour
            top = np.argpartition(-row, TOP_NEIGHBOURS)[:TOP_NEIGHBOURS]
            top = top[np.argsort(-row[top])]
            srt = np.sort(row)
            key = q_ids[qi]
            neigh = []
            for j in top:
                nk = q_ids[pool_idx[j]]
                s = float(row[j])
                pct = float(np.searchsorted(srt, s, side="left")) / (n_pool - 1)
                st = shared_top(prop[key], prop[nk])
                shard_terms[bucket(key)].update(st)
                neigh.append([nk, round(s, 4), round(min(pct, 1.0), 4), st])
            own = own_top(entries[key]["direct"])
            shard_terms[bucket(key)].update(own)
            shard_terms[bucket(key)].update(entries[key]["inh"])
            arow = A[qi]
            order = np.argsort(-arow)[:TOP_ATLAS]
            atl = []
            for u in order:
                s = float(arow[u])
                pct = float(np.searchsorted(bg_sorted[:, u], s, side="left")) / len(bg_sorted)
                st = shared_top(prop[key], umb_prop[u])
                shard_terms[bucket(key)].update(st)
                atl.append([f"disease:{umb[u]}", round(s, 4), round(min(pct, 1.0), 4), bool(s >= thr[u]), st])
            far = not any(a[3] for a in atl)
            if key in SANITY:
                sanity[key] = {"name": entries[key]["name"], "far_from_atlas": far,
                               "top10": [[x[0], entries[x[0]]["name"], x[1]] for x in neigh],
                               "expected_neighbour_ranks": {
                                   e: {"name": entries[e]["name"] if e in entries else None,
                                       "genes": entries[e]["genes"] if e in entries else None,
                                       "rank": (int((row > row[pos_in_pool[q_ids.index(e)]]).sum()) + 1)
                                       if e in entries and q_ids.index(e) in pos_in_pool else None}
                                   for e in SANITY[key]}}
            shards[bucket(key)][key] = {"nb": neigh, "own": own, "inh": sorted(entries[key]["inh"]),
                                        "atlas": atl, "far": far}
        print(f"  rows {start + blk.shape[0]}/{len(q_ids)}", flush=True)

    # ---------------------------------------------------------------- intermediates for mechanism_index.py
    # (data/raw/downloads/ is gitignored): merged entries and the phenotype vectors, so the mechanism
    # step reuses exactly the same identities and cosine without recomputing them.
    sp.save_npz(DOWNLOADS / "global_vectors.npz", X.tocsr())
    write_json(DOWNLOADS / "global_entries.json", {
        "q_ids": q_ids,
        "ic": {t: round(v, 4) for t, v in ic.items() if v > 0},
        "entries": {k: {"name": e["name"], "genes": e["genes"], "gsrc": e["gsrc"], "omim": e["omim"],
                        "orpha": e["orpha"], "raw": e["raw"], "n": e["n"], "inh": sorted(e["inh"]),
                        "direct": sorted(e["direct"]), "atlas": e["atlas"]} for k, e in entries.items()},
        "hpo_names": {t: hterms[t]["name"] for t in {t for e in entries.values() for t in e["direct"]} | set(ic)
                      if t in hterms},
        "ancestors": {t: sorted(anc(t)) for t in {t for e in entries.values() for t in e["direct"]}},
    }, compact=True)

    # ---------------------------------------------------------------- write shards
    sizes = []
    for b in range(N_BUCKETS):
        tmap = {t: [hterms[t]["name"], round(ic.get(t, 0.0), 2)] for t in sorted(shard_terms[b]) if t in hterms}
        sizes.append(write_json(SHARDS / f"{b}.json", {"bucket": b, "t": tmap, "d": shards[b]}, compact=True))

    # ---------------------------------------------------------------- index
    fields = ["id", "name", "syn", "omim", "orpha", "genes", "gsrc", "n", "atlas"]
    idx_rows = []
    for k in sorted(entries, key=lambda k: entries[k]["name"].lower()):
        e = entries[k]
        idx_rows.append([e["id"], e["name"], e["syn"], ",".join(e["omim"]), ",".join(e["orpha"]),
                         ",".join(e["genes"]), e["gsrc"], e["n"], e["atlas"] or 0])
    index_size = write_json(OUT / "index.json", {"f": fields, "rows": idx_rows}, compact=True)

    meta = {
        "generated": TODAY,
        "caveat": CAVEAT,
        "far_text": FAR_TEXT,
        "sources": {
            "MONDO": {"file": "mondo-base.obo", "version": mondo_version,
                      "url": "https://github.com/monarch-initiative/mondo/releases"},
            "HPO_annotations": {"file": "phenotype.hpoa", "version": hpoa_version,
                                "url": "https://github.com/obophenotype/human-phenotype-ontology/releases"},
            "HPO_ontology": {"file": "hp.obo", "version": hpo_version},
            "genes": {"file": "genes_to_disease.txt", "url": "https://hpo.jax.org/data/annotations"},
        },
        "counts": {
            "index_entries": len(entries),
            "mondo_entries": sum(1 for k in entries if k.startswith("MONDO:")),
            "unmapped_native_ids": sum(1 for k in entries if not k.startswith("MONDO:")),
            "dropped_no_name": dropped_no_name,
            "with_hpo_annotations": sum(1 for e in entries.values() if e["n"] > 0),
            "with_gene": sum(1 for e in entries.values() if e["genes"]),
            "with_neighbours": len(q_ids),
            "neighbour_pool": int(n_pool),
            "in_atlas": sum(1 for e in entries.values() if e["atlas"]),
            "raw_ids_merged": len(raw_ids),
            "raw_id_mapping": dict(mapped_counts),
            "hpo_terms_in_vectors": len(term_ix),
        },
        "method": {
            "identity": "OMIM and ORPHA ids merged through MONDO xrefs with source=MONDO:equivalentTo; "
                        "ids MONDO does not map keep their native id",
            "ic": "pipeline/biology/hpo.py: -ln(n annotated incl. descendants / N) over all phenotype.hpoa "
                  f"entries (N={n_ic}), aspect P, NOT rows dropped",
            "similarity": "IC-weighted cosine over ancestor-propagated HPO profiles (w_t = IC(t))",
            "neighbours": f"diseases with >= {MIN_TERMS} annotated terms; QTL/susceptibility loci never "
                          "listed as neighbours; percentile within the query disease's own row",
            "distinctive_ic": hpo.DISTINCTIVE_IC,
            "merge": "a disease merged from several sources (OMIM + ORPHA) is the centroid of its sources' "
                     "normalised vectors, so no single source's annotation style dominates",
            "atlas_threshold": {
                "rule": f"'near' an atlas disease = cosine >= {T_NEAR}, the weakest of the atlas's own curated "
                        "similar_phenotype pairs after trimming the lowest 5%; 'far' = near to none of the profiled atlas "
                        f"diseases ({len(umb)} of {len(ATLAS)} have an HPO profile)",
                "calibration": cal,
            },
        },
        "hash": {"function": "djb2, h = (h * 33 + charCode) mod 2^32, seed 5381, over the id string",
                 "buckets": N_BUCKETS, "file": "neighbours/<bucket>.json, bucket = djb2(id) % 64",
                 "test_vectors": [{"id": i, "djb2": djb2(i), "bucket": bucket(i)}
                                  for i in ("MONDO:0007739", "MONDO:0009061", "MONDO:0010679")]},
        "url_templates": {
            "OMIM": "https://omim.org/entry/{omim}",
            "Orphanet": "https://www.orpha.net/en/disease/detail/{orpha}",
            "MONDO_Monarch": "https://monarchinitiative.org/{mondo}",
            "ClinicalTrials_condition_search": "https://clinicaltrials.gov/search?cond={name_urlencoded}",
            "NORD_site_search": "https://rarediseases.org/?s={name_urlencoded}",
            "GeneReviews_search": "https://www.ncbi.nlm.nih.gov/books/NBK1116/?term={name_urlencoded}",
            "HPO_term": "https://hpo.jax.org/browse/term/{hpo}",
        },
        "sanity_checks": sanity,
        "files": {"index.json": index_size, "neighbours_total": sum(sizes), "neighbours_max_shard": max(sizes)},
    }
    old = read_json(OUT / "meta.json") if (OUT / "meta.json").exists() else {}
    for k in ("mechanism", "atlas_flags", "dismech"):  # written by mechanism_index.py / atlas_flags.py / dismech.py
        if k in old:
            meta[k] = old[k]
    write_json(OUT / "meta.json", meta)
    import atlas_flags                              # re-apply family_*.json umbrella flags (cheap)
    atlas_flags.main()
    print(f"[global] {len(entries)} entries ({sum(1 for k in entries if not k.startswith('MONDO:'))} without "
          f"MONDO, {dropped_no_name} nameless dropped), {len(q_ids)} with neighbours; "
          f"index {index_size / 1024:.0f} KB, shards {sum(sizes) / 1024 / 1024:.1f} MB "
          f"(max {max(sizes) / 1024:.0f} KB)")
    print(f"  near threshold {T_NEAR} (weakest in-family pair after trimming: {fam[TRIM][0]}); near-any share "
          f"{cal['share_of_comparable_non_slice_diseases_near_any']}; alternatives {cal['alternatives_considered']}")
    print(f"  raw id mapping: {dict(mapped_counts)}")


if __name__ == "__main__":
    main()
