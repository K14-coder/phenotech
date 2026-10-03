"""DisMech ingest: expert-curated disease mechanism "pathographs" for every DisMech disorder.

Run:  uv run --with pyyaml python3 pipeline/derive/dismech.py        (about 20 s)
In:   data/raw/downloads/dismech/          shallow clone of github.com/monarch-initiative/dismech
                                           (BSD-3-Clause); the commit sha is read from the clone
      data/raw/downloads/mondo-base.obo    MONDO names / obsolete -> replaced_by / equivalentTo xrefs
      data/derived/global/index.json       read-only: which MONDO ids we already have
      data/graph.json, data/curated/family_*.json   read-only: atlas `disease:<GENE>` umbrella xrefs
Out:  data/derived/global/dismech/<b>.json    64 shards, b = djb2(MONDO id) % 64 (same hash as neighbours/)
      data/derived/global/dismech_index.json  one row per MONDO id: name, steps, evidence, refutes
      data/derived/global/index_extra.json    DisMech MONDO ids missing from index.json, same row format
      data/derived/global/dismech_atlas_links.json   DisMech disorders matching atlas umbrella diseases
      data/derived/global/meta.json           only the `dismech` section is (re)written

Faithfulness rules
  * Every evidence item is copied from the parsed YAML unchanged: `snippet` and `explanation` are the
    exact strings PyYAML returns (folded `>-` scalars join lines with single spaces, which is also how
    DisMech's own snippet validator reads them). Nothing is trimmed, normalised or re-cased.
    The script re-reads its own output and checks every carried snippet against the source.
  * Causal edges use DisMech's own rule: a `downstream[].target` must equal another node's `name`
    verbatim. Unresolved targets are counted, never guessed.
  * Genes link to mechanism nodes with DisMech's own graph.py rule (gene descriptor keys shared with a
    pathophysiology node's gene/genes/genetic_context; MODIFIER/BIOMARKER/... genes do not link).
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DL = ROOT / "data" / "raw" / "downloads"
REPO = DL / "dismech"
KB = REPO / "kb" / "disorders"
GLOBAL = ROOT / "data" / "derived" / "global"
SHARDS = GLOBAL / "dismech"
DETAIL = GLOBAL / "dismech_evidence"
N_BUCKETS = 64
MAX_CHAINS = 12
GITHUB = "https://github.com/monarch-initiative/dismech"
SITE = "https://dismech.monarchinitiative.org/pages/disorders/{stem}.html"
SOURCE = "DisMech (Monarch Initiative)"
LICENSE = "BSD-3-Clause"
ATTRIBUTION_TEXT = (
    "Mechanism pathograph from DisMech, the Disorder Mechanisms Knowledge Base of the Monarch "
    "Initiative (https://dismech.monarchinitiative.org), BSD-3-Clause. Curated independently of this "
    "atlas; evidence snippets are quoted verbatim from DisMech.")

NEOPLASM = re.compile(r"cancer|carcinoma|tumou?r|neoplasm|leukemia|lymphoma|sarcoma|histiocytosis|"
                      r"adenoma|seminoma|thymoma|blastoma|glioma|myeloma", re.I)
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def djb2(s: str) -> int:
    """Identical to pipeline/derive/global_index.py (classic djb2, unsigned 32-bit after every step)."""
    h = 5381
    for ch in s:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    return h


def bucket(i: str) -> int:
    return djb2(i) % N_BUCKETS


# ---------------------------------------------------------------- reference -> URL
def ref_url(ref: str):
    ref = str(ref).strip()
    pre, _, rest = ref.partition(":")
    p = pre.upper()
    if p == "URL":
        return rest if rest.startswith("http") else None
    if p == "PMID":
        return f"https://pubmed.ncbi.nlm.nih.gov/{rest}/"
    if p == "ORPHA":
        return f"https://www.orpha.net/en/disease/detail/{rest}"
    if p == "DOI":
        return f"https://doi.org/{rest}"
    if p == "CLINICALTRIALS":
        return f"https://clinicaltrials.gov/study/{rest}"
    if p == "CGGV":
        return f"https://search.clinicalgenome.org/kb/gene-validity/CGGV:{rest}"
    if p == "CGDS":
        return f"https://search.clinicalgenome.org/kb/gene-dosage/{rest.replace('HGNC_', 'HGNC:')}"
    if p == "GEO":
        return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={rest}"
    if p == "PPR":
        return f"https://europepmc.org/article/PPR/{rest}"
    if p == "ICTRP":
        return f"https://trialsearch.who.int/Trial2.aspx?TrialID={rest}"
    if p == "NCIT":
        return f"https://evsexplore.semantics.cancer.gov/evsexplore/concept/ncit/{rest}"
    if p == "CIVIC_ASSERTION":
        return f"https://civicdb.org/assertions/{rest}/summary"
    if p == "CIVIC_EID":
        return f"https://civicdb.org/evidence/{rest}/summary"
    if p == "METABOLIGHTS":
        return f"https://www.ebi.ac.uk/metabolights/{rest}"
    return None  # e.g. STRCHIVE: no stable public URL pattern; the ref string is still shown


# ---------------------------------------------------------------- evidence
class Tally:
    def __init__(self):
        self.supports = Counter()
        self.items = 0
        self.snippets = 0
        self.flags = Counter()
        self.prefix = Counter()
        self.no_url = Counter()
        self.non_str_snippet = 0


T = Tally()


def ev_list(items, refs: dict):
    """Copy evidence items verbatim. `refs` collects {ref: [title, url]} for the shard."""
    out = []
    for e in items or []:
        if not isinstance(e, dict):
            continue
        ref = str(e.get("reference", ""))
        url = ref_url(ref)
        o = {"ref": ref, "supports": e.get("supports")}
        if "snippet" in e:
            sn = e["snippet"]
            if not isinstance(sn, str):
                T.non_str_snippet += 1
            o["snippet"] = sn
            T.snippets += 1
        if "explanation" in e:
            o["explanation"] = e["explanation"]
        if e.get("evidence_source"):
            o["source"] = e["evidence_source"]
        if e.get("directness"):
            o["directness"] = e["directness"]
        if e.get("quote_role"):
            o["quote_role"] = e["quote_role"]
        s = e.get("supports")
        flag = {"REFUTE": "refute", "NO_EVIDENCE": "no_evidence"}.get(s)
        if not flag and e.get("directness") == "INDIRECT":
            flag = "indirect"
        if flag:
            o["flag"] = flag
            T.flags[flag] += 1
        T.supports[s] += 1
        T.items += 1
        T.prefix[ref.split(":")[0]] += 1
        if url is None:
            T.no_url[ref.split(":")[0]] += 1
        if ref and ref not in refs:
            refs[ref] = [e.get("reference_title"), url]
        elif ref and refs[ref][0] is None and e.get("reference_title"):
            refs[ref][0] = e.get("reference_title")
        out.append(o)
    return out


# ---------------------------------------------------------------- descriptors
def term_of(d):
    """{'id','label'} from a DisMech descriptor ({preferred_term, term:{id,label}, modifier?})."""
    if not isinstance(d, dict):
        return None
    t = d.get("term") if isinstance(d.get("term"), dict) else {}
    o = {}
    if t.get("id"):
        o["id"] = str(t["id"])
    if t.get("label"):
        o["label"] = t["label"]
    if d.get("preferred_term") and d.get("preferred_term") != o.get("label"):
        o["preferred"] = d["preferred_term"]
    if d.get("modifier"):
        o["modifier"] = d["modifier"]
    return o or None


def norm_key(v):
    if v is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(v).lower())


def desc_keys(d):
    if not isinstance(d, dict):
        return set()
    vals = [d.get("preferred_term")]
    t = d.get("term")
    if isinstance(t, dict):
        vals += [t.get("label"), t.get("id")]
    return {k for k in (norm_key(v) for v in vals) if k}


def gene_keys(item, *, name_fallback=False, with_context=False):
    keys = set()
    keys |= desc_keys(item.get("gene"))
    keys |= desc_keys(item.get("gene_term"))
    for g in item.get("genes") or []:
        keys |= desc_keys(g)
    gc = item.get("genetic_context")
    if with_context and isinstance(gc, dict):
        keys |= desc_keys(gc.get("gene"))
        for g in gc.get("genes") or []:
            keys |= desc_keys(g)
    if name_fallback and not keys and not item.get("affected_regions"):
        n = str(item.get("name") or "").strip()
        if n and len(n) <= 20 and all(c.isalnum() or c in "-_" for c in n):
            keys.add(norm_key(n))
    return keys


NONCONTRIB_REL = {"BIOMARKER", "DISPUTED", "MODIFIER", "PROTECTIVE", "UNKNOWN"}
NONCONTRIB_WORDS = {"biomarker", "disputed", "modifier", "protective", "refuted", "unknown"}


def gene_contributes(g):
    rt = g.get("relationship_type")
    if isinstance(rt, str):
        return rt.upper() not in NONCONTRIB_REL
    a = g.get("association")
    if not isinstance(a, str):
        return True
    words = {w.strip().lower() for w in a.replace("-", " ").replace("_", " ").split()}
    return not (words & NONCONTRIB_WORDS)


def hgnc_norm(i):
    if not i:
        return None
    i = str(i)
    return "HGNC:" + i.split(":", 1)[1] if i.lower().startswith("hgnc:") else i


def simplify(v):
    """Classification values: descriptor -> 'label (ID)' style dict, lists mapped, scalars kept."""
    if isinstance(v, list):
        return [simplify(x) for x in v]
    if isinstance(v, dict):
        t = term_of(v)
        if t:
            return t
        return {k: simplify(x) for k, x in v.items() if k not in ("evidence",)}
    return v


# ---------------------------------------------------------------- one disorder
SCALE = {"MOLECULAR": "molecular", "CELLULAR": "cellular", "TISSUE": "tissue", "ORGANISM": "organism"}
TYPE_RANK = {"environmental": 0, "gene": 1, "molecular": 2, "cellular": 3, "tissue": 4, "organism": 5,
             "unspecified": 5, "phenotype": 6}
PP_TERM_SLOTS = ["genes", "gene", "molecular_functions", "chemical_entities", "protein_complexes",
                 "gene_products", "biological_processes", "cellular_components", "cell_types", "locations",
                 "pathways"]


def pp_type(p, has_incoming):
    sc = p.get("biological_scale")
    if isinstance(sc, str) and sc.upper() in SCALE:
        return SCALE[sc.upper()], "scale"
    has_gene = bool(p.get("genes") or p.get("gene") or p.get("genetic_context"))
    if has_gene and not has_incoming:
        return "gene", "inferred:gene"
    if p.get("molecular_functions") or p.get("chemical_entities") or p.get("protein_complexes") \
            or p.get("gene_products"):
        return "molecular", "inferred:molecular"
    if p.get("cell_types"):
        return "cellular", "inferred:cell_types"
    if p.get("locations"):
        return "tissue", "inferred:locations"
    return "unspecified", "none"


def step_terms(p):
    out = []
    for slot in PP_TERM_SLOTS:
        v = p.get(slot)
        for d in (v if isinstance(v, list) else [v] if v else []):
            t = term_of(d)
            if t and t.get("id"):
                t["slot"] = slot
                out.append(t)
    gc = p.get("genetic_context")
    if isinstance(gc, dict):
        for d in ([gc.get("gene")] if gc.get("gene") else []) + list(gc.get("genes") or []):
            t = term_of(d)
            if t and t.get("id"):
                t["slot"] = "genetic_context"
                out.append(t)
    return out


class Dangling:
    n = 0
    examples = []


def build(d: dict, stem: str, refs: dict):
    pp = [p for p in (d.get("pathophysiology") or []) if isinstance(p, dict) and p.get("name")]
    ph = [p for p in (d.get("phenotypes") or []) if isinstance(p, dict) and p.get("name")]
    env = [e for e in (d.get("environmental") or []) if isinstance(e, dict) and e.get("name")]
    genetic = [g for g in (d.get("genetic") or []) if isinstance(g, dict) and g.get("name")]
    pp_names = {p["name"] for p in pp}
    ph_by = {}
    for p in ph:
        ph_by.setdefault(p["name"], p)

    # raw edges by name
    raw = []  # (src_kind, src_name, tgt_name, edge_dict)
    for p in pp:
        for e in p.get("downstream") or []:
            if isinstance(e, dict) and e.get("target"):
                raw.append(("pp", p["name"], str(e["target"]), e, "downstream"))
    for p in ph:
        for e in p.get("sequelae") or []:
            if isinstance(e, dict) and e.get("target"):
                raw.append(("ph", p["name"], str(e["target"]), e, "sequela"))
    for x in env:
        for e in x.get("influences_mechanisms") or []:
            if isinstance(e, dict) and e.get("target"):
                raw.append(("env", x["name"], str(e["target"]), e, "influences"))

    resolved = []
    used_ph = set()
    for kind, s, t, e, pred in raw:
        if t in pp_names:
            resolved.append((kind, s, "pp", t, e, pred))
        elif t in ph_by:
            resolved.append((kind, s, "ph", t, e, pred))
            used_ph.add(t)
        else:
            Dangling.n += 1
            if len(Dangling.examples) < 8:
                Dangling.examples.append(f"{stem}: {s} -> {t}")
    # a phenotype that is the source of a resolved sequela edge is in the chain too
    for kind, s, tk, t, e, pred in resolved:
        if kind == "ph":
            used_ph.add(s)

    # gene -> mechanism links (DisMech graph.py rule)
    pp_by_gene = defaultdict(set)
    for p in pp:
        for k in gene_keys(p, with_context=True):
            pp_by_gene[k].add(p["name"])
    gene_edges = []
    for g in genetic:
        if not gene_contributes(g):
            continue
        tg = set()
        for k in gene_keys(g, name_fallback=True):
            tg |= pp_by_gene.get(k, set())
        for t in sorted(tg):
            gene_edges.append((g["name"], t, "dismech"))
    # Ours, flagged: a contributing gene that DisMech's rule leaves unlinked is linked to a ROOT
    # pathophysiology node (no incoming causal edge) whose name contains the gene symbol as a word,
    # e.g. "STXBP1 Haploinsufficiency ..." or "SCN1A Gene Mutation".
    has_in_pp = {r[3] for r in resolved if r[2] == "pp"}
    linked_now = {x[0] for x in gene_edges}
    for g in genetic:
        if g["name"] in linked_now or not gene_contributes(g):
            continue
        sym = (term_of(g.get("gene_term")) or {}).get("label") or g["name"]
        if not re.fullmatch(r"[A-Za-z0-9\-]{2,15}", str(sym)):
            continue
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(str(sym)) + r"(?![A-Za-z0-9])")
        for p in pp:
            if p["name"] not in has_in_pp and pat.search(p["name"]):
                gene_edges.append((g["name"], p["name"], "name_match"))

    # ---- nodes
    incoming = Counter(r[3] for r in resolved)
    for _, t, _how in gene_edges:
        incoming[t] += 1
    nodes = []  # dicts with key
    key_idx = {}

    def add(key, node):
        key_idx[key] = len(nodes)
        nodes.append(node)

    linked_genes = {g for g, _, _how in gene_edges}
    for g in genetic:
        if g["name"] in linked_genes:
            gt = term_of(g.get("gene_term")) or {}
            add(("gene", g["name"]), {
                "label": g["name"], "sec": "genetic", "type": "gene", "type_basis": "section",
                "terms": ([{"id": hgnc_norm(gt["id"]), "label": gt.get("label"), "slot": "gene_term"}]
                          if gt.get("id") else []),
                "evidence": [],  # gene evidence lives under genes[]; not duplicated here
                "gene_ref": g["name"], "order": len(nodes)})
    for x in env:
        if any(r[0] == "env" and r[1] == x["name"] for r in resolved):
            t = term_of(x.get("exposure_term"))
            add(("env", x["name"]), {
                "label": x["name"], "sec": "environmental", "type": "environmental", "type_basis": "section",
                "terms": [dict(t, slot="exposure_term")] if t and t.get("id") else [],
                "evidence": ev_list(x.get("evidence"), refs), "order": len(nodes)})
    for p in pp:
        typ, basis = pp_type(p, incoming[p["name"]] > 0)
        n = {"label": p["name"], "sec": "pathophysiology", "type": typ, "type_basis": basis}
        if p.get("biological_scale"):
            n["scale"] = p["biological_scale"]
        if p.get("role"):
            n["role"] = p["role"]
        if p.get("description"):
            n["description"] = p["description"]
        if p.get("conforms_to"):
            n["conforms_to"] = p["conforms_to"]
        if p.get("mechanism_confidence"):
            n["mechanism_confidence"] = simplify(p["mechanism_confidence"])
        n["terms"] = step_terms(p)
        n["evidence"] = ev_list(p.get("evidence"), refs)
        n["order"] = len(nodes)
        add(("pp", p["name"]), n)
    for p in ph:
        if p["name"] not in used_ph:
            continue
        t = term_of(p.get("phenotype_term"))
        n = {"label": p["name"], "sec": "phenotypes", "type": "phenotype", "type_basis": "section",
             "terms": [dict(t, slot="phenotype_term")] if t and t.get("id") else []}
        if p.get("description"):
            n["description"] = p["description"]
        if p.get("frequency"):
            n["frequency"] = simplify(p["frequency"])
        n["evidence"] = ev_list(p.get("evidence"), refs)
        n["order"] = len(nodes)
        add(("ph", p["name"]), n)

    edges = []
    for g, t, how in gene_edges:
        edges.append((key_idx[("gene", g)], key_idx[("pp", t)],
                      {"link": "contributes_to"} if how == "dismech"
                      else {"link": "contributes_to", "inferred": "gene symbol in root node name (ours, not DisMech)"}))
    for kind, s, tk, t, e, pred in resolved:
        a = key_idx[(kind, s)]
        b = key_idx[(tk, t)]
        o = {"link": e.get("causal_link_type") or e.get("environmental_effect") or pred}
        if pred != "downstream":
            o["predicate"] = pred
        if e.get("description"):
            o["description"] = e["description"]
        if e.get("intermediate_mechanisms"):
            o["intermediate"] = e["intermediate_mechanisms"]
        if e.get("evidence"):
            o["evidence"] = ev_list(e.get("evidence"), refs)
        edges.append((a, b, o))

    # ---- topological order (Kahn; ties by type rank, then file order)
    n_nodes = len(nodes)
    succ = defaultdict(list)
    indeg = [0] * n_nodes
    seen_pairs = set()
    for a, b, _ in edges:
        if (a, b) in seen_pairs or a == b:
            continue
        seen_pairs.add((a, b))
        succ[a].append(b)
        indeg[b] += 1
    import heapq
    heap = [(TYPE_RANK[nodes[i]["type"]], nodes[i]["order"], i) for i in range(n_nodes) if indeg[i] == 0]
    heapq.heapify(heap)
    order, deg = [], indeg[:]
    while heap:
        _, _, i = heapq.heappop(heap)
        order.append(i)
        for j in succ[i]:
            deg[j] -= 1
            if deg[j] == 0:
                heapq.heappush(heap, (TYPE_RANK[nodes[j]["type"]], nodes[j]["order"], j))
    cyclic = len(order) < n_nodes
    if cyclic:
        rest = sorted((i for i in range(n_nodes) if i not in set(order)),
                      key=lambda i: (TYPE_RANK[nodes[i]["type"]], nodes[i]["order"]))
        order += rest
    pos = {old: new for new, old in enumerate(order)}
    steps = []
    for old in order:
        n = dict(nodes[old])
        n.pop("order", None)
        steps.append(dict({"i": pos[old]}, **n))
    out_edges = [dict({"s": pos[a], "t": pos[b]}, **o) for a, b, o in edges]

    # ---- chains: root-to-sink paths (DFS, capped)
    nsucc = defaultdict(list)
    for e in out_edges:
        if e["t"] not in nsucc[e["s"]] and e["s"] != e["t"]:
            nsucc[e["s"]].append(e["t"])
    has_in = {e["t"] for e in out_edges if e["s"] != e["t"]}
    roots = [s["i"] for s in steps if s["i"] not in has_in and nsucc.get(s["i"])]
    chains, total = [], 0

    def dfs(path):
        nonlocal total
        nxt = [j for j in nsucc.get(path[-1], []) if j not in path]
        if not nxt:
            total += 1
            if len(chains) < MAX_CHAINS and len(path) > 1:
                chains.append(list(path))
            return
        for j in sorted(nxt):
            if total > 5000:
                return
            dfs(path + [j])

    for r in roots:
        dfs([r])
    # longest chains first so a page can show the deepest causal story
    chains.sort(key=lambda c: -len(c))

    # ---- genes
    genes = []
    for g in genetic:
        gt = term_of(g.get("gene_term")) or {}
        o = {"symbol": gt.get("label") or gt.get("preferred") or g["name"], "name": g["name"]}
        if gt.get("id"):
            o["hgnc"] = hgnc_norm(gt["id"])
        for k in ("association", "relationship_type", "presence", "variant_origin"):
            if g.get(k):
                o[k] = g[k]
        inh = [ (i.get("name") if isinstance(i, dict) else i) for i in (g.get("inheritance") or [])]
        if inh:
            o["inheritance"] = inh
        if g.get("notes"):
            o["notes"] = g["notes"]
        vals = []
        for v in g.get("gene_disease_validity") or []:
            if isinstance(v, dict):
                vals.append({k: v.get(k) for k in ("validity_classification", "classified_by", "external_id")
                             if v.get(k)})
        if vals:
            o["validity"] = vals
        o["contributes"] = gene_contributes(g)
        hows = {how for gg, _t, how in gene_edges if gg == g["name"]}
        o["linked_to_mechanism"] = "dismech" if "dismech" in hows else ("name_match" if hows else False)
        o["evidence"] = ev_list(g.get("evidence"), refs)
        genes.append(o)

    # ---- treatments
    step_by_label = {s["label"]: s["i"] for s in steps}
    tx = []
    for t in d.get("treatments") or []:
        if not isinstance(t, dict) or not t.get("name"):
            continue
        o = {"name": t["name"]}
        if t.get("description"):
            o["description"] = t["description"]
        if t.get("therapeutic_modality"):
            o["modality"] = t["therapeutic_modality"]
        tt = t.get("treatment_term") if isinstance(t.get("treatment_term"), dict) else {}
        a = term_of(tt)
        if a:
            o["action"] = a
        ag = [term_of(x) for x in (tt.get("therapeutic_agent") or [])]
        ag = [x for x in ag if x]
        if ag:
            o["agents"] = ag
        rg = term_of(tt.get("regimen_term"))
        if rg:
            o["regimen"] = rg
        tm = []
        for m in t.get("target_mechanisms") or []:
            if isinstance(m, dict) and m.get("target"):
                x = {"target": m["target"], "step": step_by_label.get(str(m["target"]))}
                for k in ("treatment_effect", "mechanism_of_action", "description"):
                    if m.get(k):
                        x[k] = m[k]
                if m.get("evidence"):
                    x["evidence"] = ev_list(m.get("evidence"), refs)
                tm.append(x)
        if tm:
            o["targets"] = tm
        o["evidence"] = ev_list(t.get("evidence"), refs)
        tx.append(o)

    # ---- hypotheses and open questions (where DisMech records contested mechanisms)
    hyps = []
    for h in d.get("mechanistic_hypotheses") or []:
        if isinstance(h, dict):
            o = {k: h.get(k) for k in ("hypothesis_group_id", "hypothesis_label", "status", "description")
                 if h.get(k)}
            o["evidence"] = ev_list(h.get("evidence"), refs)
            hyps.append(o)
    disc = []
    for x in d.get("discussions") or []:
        if isinstance(x, dict):
            o = {k: x.get(k) for k in ("discussion_id", "kind", "status", "prompt", "rationale", "attaches_to")
                 if x.get(k)}
            o["evidence"] = ev_list(x.get("evidence"), refs)
            disc.append(o)

    other_ph = []
    for p in ph:
        if p["name"] in used_ph:
            continue
        t = term_of(p.get("phenotype_term")) or {}
        other_ph.append([p["name"], t.get("id")])

    return {"steps": steps, "edges": out_edges, "chains": chains, "n_paths": total,
            "cyclic": cyclic, "genes": genes, "treatments": tx, "hypotheses": hyps,
            "open_questions": disc, "unlinked_phenotypes": other_ph}


def count_ev(rec):
    """(items, refutes, no_evidence) over everything carried in one record."""
    n = r = ne = 0

    def walk(o):
        nonlocal n, r, ne
        if isinstance(o, dict):
            if "ref" in o and "supports" in o:
                n += 1
                r += o.get("supports") == "REFUTE"
                ne += o.get("supports") == "NO_EVIDENCE"
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(rec)
    return n, r, ne


MOVED_TEXT = ("description", "rationale", "notes")


def split(rec, tdict):
    """Core record (structure, ids, counts) and detail record (verbatim evidence + long prose).

    Every object in steps/edges/genes/treatments(+targets)/hypotheses/open_questions loses its
    `evidence` list and long text, which move to detail["x"][<path>]; the core keeps `ev`:
    [items, refutes, no_evidence] so a page can badge it without fetching the detail shard."""
    detail = {"file": rec["file"], "x": {}}

    def move(o, path):
        ent = {}
        ev = o.pop("evidence", None)
        if ev:
            ent["evidence"] = ev
            o["ev"] = [len(ev), sum(e.get("supports") == "REFUTE" for e in ev),
                       sum(e.get("supports") == "NO_EVIDENCE" for e in ev)]
        for k in MOVED_TEXT:
            if k in o:
                ent[k] = o.pop(k)
        if ent:
            detail["x"][path] = ent

    for st in rec.get("steps") or []:  # ontology terms -> [id, slot, modifier?] + shard-local labels
        packed = []
        for t in st.get("terms") or []:
            if t.get("label"):
                tdict.setdefault(t["id"], t["label"])
            packed.append([t["id"], t.get("slot")] + ([t["modifier"]] if t.get("modifier") else []))
        st["terms"] = packed
    for sec in ("steps", "edges", "genes", "treatments", "hypotheses", "open_questions"):
        for i, o in enumerate(rec.get(sec) or []):
            move(o, f"{sec}/{i}")
            for j, t in enumerate(o.get("targets") or []):
                move(t, f"{sec}/{i}/targets/{j}")
    return rec, detail


# ---------------------------------------------------------------- MONDO
def parse_mondo(path):
    terms, cur, version = {}, None, None
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("data-version:"):
                version = line.split(": ", 1)[1]
            if line == "[Term]":
                cur = {"xref": [], "obsolete": False, "syn": []}
                continue
            if line.startswith("["):
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
            elif k == "xref":
                m = re.match(r"(\S+)(?:\s+\{(.*)\})?", v)
                if m and "MONDO:equivalentTo" in (m.group(2) or ""):
                    cur["xref"].append(m.group(1))
            elif k == "replaced_by":
                cur["replaced_by"] = v
            elif k == "is_obsolete" and v == "true":
                cur["obsolete"] = True
    if cur and "id" in cur:
        terms[cur["id"]] = cur
    return terms, version


def atlas_umbrellas():
    """{disease:<GENE>: {"label", "MONDO": {id: how}, "files": [...]}} from graph.json + family files."""
    out = {}
    srcs = [ROOT / "data" / "graph.json"] + [Path(p) for p in sorted(glob.glob(str(ROOT / "data" / "curated" / "family_*.json")))]
    for f in srcs:
        try:
            frag = json.loads(f.read_text())
        except Exception as ex:
            print(f"[dismech] skipped {f.name}: {ex}")
            continue
        for n in frag.get("nodes", []):
            if n.get("type") != "disease" or not str(n.get("id", "")).startswith("disease:"):
                continue
            u = out.setdefault(n["id"], {"label": n.get("label"), "MONDO": {}, "files": []})
            if f.name not in u["files"]:
                u["files"].append(f.name)
            mx = (n.get("xrefs") or {}).get("MONDO") or []
            for m in (mx if isinstance(mx, list) else [mx]):
                if str(m).startswith("MONDO:"):
                    u["MONDO"].setdefault(str(m), "xref")
            for st in (n.get("attrs") or {}).get("subtypes") or []:
                m = st.get("MONDO")
                if m and str(m).startswith("MONDO:"):
                    u["MONDO"].setdefault(str(m), "subtype")
    return out


# ---------------------------------------------------------------- main
def main():
    t0 = time.time()
    if not KB.is_dir():
        sys.exit("[dismech] clone missing: git clone --depth 1 https://github.com/monarch-initiative/dismech "
                 "data/raw/downloads/dismech")
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    commit_date = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%cI"],
                                 capture_output=True, text=True).stdout.strip()
    mondo, mondo_version = parse_mondo(DL / "mondo-base.obo")
    idx = json.loads((GLOBAL / "index.json").read_text())
    icol = {k: i for i, k in enumerate(idx["f"])}
    index_ids = {r[icol["id"]] for r in idx["rows"]}

    files = sorted(glob.glob(str(KB / "*.yaml")))
    shards = defaultdict(lambda: {"d": {}, "x": {}, "refs": {}, "t": {}})
    no_mondo, src_snips = [], {}
    corpus_items = corpus_snips = 0
    corpus_supports = Counter()
    per_id = defaultdict(list)
    type_counts = Counter()
    basis_counts = Counter()
    n_records = 0

    def corpus_walk(o):
        nonlocal corpus_items, corpus_snips
        if isinstance(o, dict):
            if "reference" in o and ("supports" in o or "snippet" in o):
                corpus_items += 1
                corpus_supports[o.get("supports")] += 1
                corpus_snips += "snippet" in o
            for v in o.values():
                corpus_walk(v)
        elif isinstance(o, list):
            for v in o:
                corpus_walk(v)

    for f in files:
        stem = Path(f).stem
        d = yaml.load(open(f, encoding="utf-8"), Loader=Loader)
        corpus_walk(d)
        dt = (d.get("disease_term") or {})
        term = dt.get("term") if isinstance(dt.get("term"), dict) else {}
        mid, joined = term.get("id"), "disease_term"
        if not (mid and str(mid).startswith("MONDO:")):
            mid = None
            for m in ((d.get("mappings") or {}).get("mondo_mappings") or []):
                if isinstance(m, dict) and m.get("mapping_predicate") == "skos:exactMatch":
                    mid = (m.get("term") or {}).get("id")
                    joined = "mappings.mondo_mappings exactMatch"
                    break
        if not mid:
            no_mondo.append({"file": f"{stem}.yaml", "name": d.get("name")})
            continue
        mid = str(mid)
        b = bucket(mid)
        sh = shards[b]
        body = build(d, stem, sh["refs"])
        mt = mondo.get(mid, {})
        rec = {
            "file": f"{stem}.yaml",
            "name": d.get("name"),
            "mondo": mid,
            "mondo_label": term.get("label") or mt.get("name"),
            "joined_by": joined,
        }
        if mt.get("obsolete"):
            rec["mondo_obsolete"] = True
            if mt.get("replaced_by"):
                rec["mondo_replaced_by"] = mt["replaced_by"]
        if dt.get("preferred_term"):
            rec["preferred_term"] = dt["preferred_term"]
        for k in ("category", "description"):
            if d.get(k):
                rec[k] = d[k]
        for k in ("synonyms", "parents", "categories"):
            if d.get(k):
                rec[k] = [str(x) for x in d[k]]
        if isinstance(d.get("classifications"), dict):
            rec["classifications"] = {k: simplify(v) for k, v in d["classifications"].items()}
        inh = []
        for i in d.get("inheritance") or []:
            if isinstance(i, dict):
                t = term_of(i.get("inheritance_term")) or {}
                inh.append({"name": i.get("name"), "hp": t.get("id")})
        if inh:
            rec["inheritance"] = inh
        rec.update(body)
        n_ev, n_ref, n_ne = count_ev(rec)
        mech_steps = sum(1 for s in rec["steps"] if s["sec"] == "pathophysiology")
        for s in rec["steps"]:
            type_counts[s["type"]] += 1
            basis_counts[s["type_basis"].split(":")[0]] += 1
        rec["counts"] = {"steps": len(rec["steps"]), "mechanism_steps": mech_steps, "edges": len(rec["edges"]),
                         "evidence": n_ev, "refute": n_ref, "no_evidence": n_ne, "genes": len(rec["genes"]),
                         "treatments": len(rec["treatments"])}
        rec["attribution"] = {"file_url": f"{GITHUB}/blob/{sha}/kb/disorders/{stem}.yaml",
                              "page_url": SITE.format(stem=stem)}
        core, detail = split(rec, sh["t"])
        sh["d"].setdefault(mid, []).append(core)
        sh["x"].setdefault(mid, []).append(detail)
        per_id[mid].append(core)
        n_records += 1
        # keep the source snippets for the verbatim check
        src_snips[f"{stem}.yaml"] = d

    # ---- write shards
    shard_attr = {"source": SOURCE, "license": LICENSE, "commit": sha, "text": ATTRIBUTION_TEXT}
    SHARDS.mkdir(parents=True, exist_ok=True)
    DETAIL.mkdir(parents=True, exist_ok=True)
    sizes, dsizes = {}, {}
    for b in range(N_BUCKETS):
        sh = shards.get(b, {"d": {}, "x": {}, "refs": {}, "t": {}})
        text = json.dumps({"bucket": b, "attribution": shard_attr, "t": sh["t"], "d": sh["d"]}, ensure_ascii=False, separators=(",", ":"), default=str)
        (SHARDS / f"{b}.json").write_text(text + "\n", encoding="utf-8")
        sizes[b] = len(text.encode())
        text = json.dumps({"bucket": b, "attribution": shard_attr, "refs": sh["refs"], "d": sh["x"]}, ensure_ascii=False,
                          separators=(",", ":"), default=str)
        (DETAIL / f"{b}.json").write_text(text + "\n", encoding="utf-8")
        dsizes[b] = len(text.encode())

    # ---- verbatim check: every carried snippet equals a snippet string in the source file
    mismatches = 0
    checked = 0
    for b in range(N_BUCKETS):
        obj = json.loads((DETAIL / f"{b}.json").read_text(encoding="utf-8"))
        for mid, recs in obj["d"].items():
            for rec in recs:
                src = set()

                def collect(o):
                    if isinstance(o, dict):
                        if "snippet" in o and "reference" in o:
                            src.add(json.dumps(o["snippet"], ensure_ascii=False, default=str))
                        for v in o.values():
                            collect(v)
                    elif isinstance(o, list):
                        for v in o:
                            collect(v)
                collect(src_snips[rec["file"]])

                def check(o):
                    nonlocal mismatches, checked
                    if isinstance(o, dict):
                        if "ref" in o and "snippet" in o:
                            checked += 1
                            if json.dumps(o["snippet"], ensure_ascii=False, default=str) not in src:
                                mismatches += 1
                        for v in o.values():
                            check(v)
                    elif isinstance(o, list):
                        for v in o:
                            check(v)
                check(rec)
    assert mismatches == 0, f"{mismatches} snippets differ from the source"

    # ---- dismech_index.json
    rows = []
    for mid in sorted(per_id, key=lambda m: (per_id[m][0]["name"] or "").lower()):
        recs = per_id[mid]
        rows.append([mid, recs[0]["name"], sum(r["counts"]["mechanism_steps"] for r in recs),
                     sum(r["counts"]["steps"] for r in recs), sum(r["counts"]["evidence"] for r in recs),
                     sum(r["counts"]["refute"] for r in recs), len(recs), mid in index_ids])
    di = {"f": ["id", "name", "mech_steps", "steps", "evidence", "refute", "entries", "in_index"],
          "source": SOURCE, "license": LICENSE, "commit": sha, "rows": rows}
    (GLOBAL / "dismech_index.json").write_text(json.dumps(di, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")

    # ---- index_extra.json: DisMech MONDO ids that index.json does not have
    extra = []
    extra_obsolete = []
    for mid, recs in per_id.items():
        if mid in index_ids:
            continue
        r0 = recs[0]
        mt = mondo.get(mid, {})
        name = r0.get("mondo_label") or r0["name"]
        syn, seen = [], {name.lower()}
        for s in [r0["name"], r0.get("preferred_term")] + [x for r in recs for x in (r.get("synonyms") or [])] \
                + [r["name"] for r in recs[1:]]:
            if s and s.lower() not in seen and len(s) <= 80:
                seen.add(s.lower())
                syn.append(s)
        omim = sorted({x.split(":", 1)[1] for x in mt.get("xref", []) if x.startswith("OMIM:")})
        orpha = sorted({x.split(":", 1)[1] for x in mt.get("xref", []) if x.startswith("Orphanet:")})
        genes = []
        for r in recs:
            for g in r["genes"]:
                if g.get("contributes") and g["symbol"] not in genes and re.fullmatch(r"[A-Za-z0-9\-\.]+", g["symbol"]):
                    genes.append(g["symbol"])
        extra.append([mid, name, syn[:6], ",".join(omim), ",".join(orpha), ",".join(genes[:8]),
                      3 if genes else 0, 0, 0])
        if mt.get("obsolete") or not mt:
            extra_obsolete.append(mid)
    extra.sort(key=lambda r: r[1].lower())
    ie = {"f": idx["f"], "source": "DisMech disorders whose MONDO id is not in index.json",
          "gsrc_note": "gsrc 3 = genes from DisMech's curated `genetic` section (not OMIM/Orphanet)",
          "rows": extra}
    (GLOBAL / "index_extra.json").write_text(json.dumps(ie, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")

    # ---- atlas cross-links
    ums = atlas_umbrellas()
    links = []
    gene_only = []
    for aid, u in sorted(ums.items()):
        ids = dict(u["MONDO"])
        for m, how in list(ids.items()):  # follow obsolete -> replaced_by
            rb = mondo.get(m, {}).get("replaced_by")
            if mondo.get(m, {}).get("obsolete") and rb and rb not in ids:
                ids[rb] = f"{how} (obsolete {m} replaced_by)"
        hit_files = set()
        gene = aid.split(":", 1)[1]
        for m, how in sorted(ids.items()):
            for r in per_id.get(m, []):
                hit_files.add(r["file"])
                contrib = list(dict.fromkeys(g["symbol"] for g in r["genes"] if g.get("contributes")))
                names = {x for g in r["genes"] if g.get("contributes") for x in (g["symbol"], g["name"])}
                kind = ("single_gene" if len(contrib) == 1 and gene in names else
                        "multi_gene_lists_gene" if gene in names else "group_gene_not_listed")
                links.append({"atlas_id": aid, "atlas_label": u["label"], "mondo": m, "joined_by": how,
                              "kind": kind, "dismech_genes": contrib[:12],
                              "dismech_file": r["file"], "dismech_name": r["name"],
                              "mondo_label": r.get("mondo_label"), "bucket": bucket(m),
                              "mech_steps": r["counts"]["mechanism_steps"], "steps": r["counts"]["steps"],
                              "evidence": r["counts"]["evidence"], "refute": r["counts"]["refute"],
                              "page_url": r["attribution"]["page_url"], "file_url": r["attribution"]["file_url"]})
        for m, recs in per_id.items():
            for r in recs:
                if r["file"] in hit_files:
                    continue
                gs = [g for g in r["genes"] if gene in (g["symbol"], g["name"]) and g.get("contributes")
                      and g.get("variant_origin") != "SOMATIC"
                      and "somatic" not in str(g.get("association") or "").lower()]
                if gs and NEOPLASM.search(f'{r["name"]} {r.get("mondo_label") or ""}'):
                    continue
                n_contrib = len({g["symbol"] for g in r["genes"] if g.get("contributes")})
                if gs and n_contrib <= 3:
                    gene_only.append({"atlas_id": aid, "mondo": m, "dismech_file": r["file"],
                                      "dismech_name": r["name"], "bucket": bucket(m),
                                      "gene_association": gs[0].get("association"),
                                      "n_contributing_genes": n_contrib})
    al = {"generated": time.strftime("%Y-%m-%d"), "source": SOURCE, "license": LICENSE, "commit": sha,
          "rule": ("A DisMech disorder is linked when its MONDO id equals a MONDO xref or attrs.subtypes[].MONDO of an "
                   "atlas disease:<GENE> node in data/graph.json or data/curated/family_*.json; an obsolete xref is "
                   "followed to its MONDO replaced_by term."),
          "kind_rule": ("single_gene: DisMech's contributing genes are exactly the umbrella gene; "
                        "multi_gene_lists_gene: DisMech lists several contributing genes including it (e.g. Dravet); "
                        "group_gene_not_listed: a clinical group our node lists as a subtype but whose DisMech entry "
                        "does not name the gene. Show only the first two kinds on a gene page by default."),
          "gene_only_rule": ("Weaker, listed separately: a DisMech disorder with no MONDO match whose curated genetic "
                             "section names the umbrella gene as a contributing, non-somatic gene, with at most 3 "
                             "contributing genes, excluding neoplasms by name. Not an identity match: each is a lead "
                             "for a missing MONDO xref on our node, to be checked by a person."),
          "atlas_diseases": len(ums),
          "atlas_diseases_linked": len({l["atlas_id"] for l in links}),
          "links": links, "gene_only": gene_only}
    (GLOBAL / "dismech_atlas_links.json").write_text(json.dumps(al, ensure_ascii=False, indent=1, default=str) + "\n")

    # ---- meta.json `dismech` section
    meta_p = GLOBAL / "meta.json"
    meta = json.loads(meta_p.read_text())
    total_steps = sum(type_counts.values())
    mech_total = sum(r["counts"]["mechanism_steps"] for v in per_id.values() for r in v)
    meta["dismech"] = {
        "source": SOURCE, "repo": GITHUB, "site": "https://dismech.monarchinitiative.org",
        "license": LICENSE, "commit": sha, "commit_date": commit_date,
        "attribution_text": ATTRIBUTION_TEXT, "mondo_version": mondo_version,
        "counts": {
            "yaml_files": len(files), "records": n_records, "mondo_ids": len(per_id),
            "mondo_ids_with_2plus_entries": sum(1 for v in per_id.values() if len(v) > 1),
            "no_mondo_skipped": len(no_mondo),
            "joined_by_mapping_exactMatch": sum(1 for v in per_id.values() for r in v if r["joined_by"] != "disease_term"),
            "in_index_json": sum(1 for m in per_id if m in index_ids),
            "index_extra_rows": len(extra), "index_extra_obsolete_or_unknown_mondo": len(extra_obsolete),
            "steps_total": total_steps, "mechanism_steps": mech_total,
            "steps_by_type": dict(type_counts.most_common()),
            "step_type_basis": dict(basis_counts.most_common()),
            "edges": sum(len(r["edges"]) for v in per_id.values() for r in v),
            "dangling_causal_targets": Dangling.n,
            "evidence_items_carried": T.items, "snippets_carried": T.snippets,
            "snippets_verified_verbatim": checked,
            "supports": dict(T.supports.most_common()), "flags": dict(T.flags.most_common()),
            "evidence_items_in_corpus": corpus_items, "snippets_in_corpus": corpus_snips,
            "supports_in_corpus": dict(corpus_supports.most_common()),
            "reference_prefixes": dict(T.prefix.most_common()),
            "refs_without_url": dict(T.no_url.most_common()),
            "atlas_links": len(links), "atlas_gene_only": len(gene_only),
        },
        "shards": {"dismech": {"total_bytes": sum(sizes.values()), "max_bytes": max(sizes.values()),
                               "min_bytes": min(sizes.values()), "n": N_BUCKETS},
                   "dismech_evidence": {"total_bytes": sum(dsizes.values()), "max_bytes": max(dsizes.values()),
                                        "min_bytes": min(dsizes.values()), "n": N_BUCKETS}},
        "files": {"dismech_index.json": (GLOBAL / "dismech_index.json").stat().st_size,
                  "index_extra.json": (GLOBAL / "index_extra.json").stat().st_size,
                  "dismech_atlas_links.json": (GLOBAL / "dismech_atlas_links.json").stat().st_size},
        "no_mondo_files": no_mondo,
        "dangling_examples": Dangling.examples,
    }
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")

    c = meta["dismech"]["counts"]
    print(f"[dismech] commit {sha[:12]}  {len(files)} files -> {n_records} records, {len(per_id)} MONDO ids "
          f"({len(no_mondo)} without MONDO skipped)")
    print(f"  steps {total_steps} (mechanism {mech_total}) by type {dict(type_counts.most_common())}")
    print(f"  evidence carried {T.items} (snippets {T.snippets}, verified verbatim {checked}); corpus {corpus_items}")
    print(f"  supports {dict(T.supports)}  flags {dict(T.flags)}")
    print(f"  index_extra {len(extra)}  atlas links {len(links)} ({al['atlas_diseases_linked']}/{len(ums)} umbrellas), "
          f"gene-only {len(gene_only)}  dangling {Dangling.n}")
    for nm, sz in (("dismech", sizes), ("dismech_evidence", dsizes)):
        print(f"  {nm}/ total {sum(sz.values())/1e6:.1f} MB, max {max(sz.values())/1e3:.0f} KB, "
              f"median {sorted(sz.values())[32]/1e3:.0f} KB, min {min(sz.values())/1e3:.0f} KB")
    print(f"  ({time.time()-t0:.1f} s)")


if __name__ == "__main__":
    main()
