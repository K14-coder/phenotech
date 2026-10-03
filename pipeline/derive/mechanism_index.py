"""Mechanism layer for the global index: mechanism class, pathways and mechanism clusters at scale.

Run:  uv run --with numpy --with scipy --with igraph --with leidenalg python3 pipeline/derive/mechanism_index.py
      (after global_index.py, which writes the shared intermediates)
In (data/raw/downloads/, gitignored):
  g2p_all.csv                       Gene2Phenotype, all panels (www.ebi.ac.uk/gene2phenotype/api/panel/all/download/)
  clingen_gene_validity.csv         ClinGen gene-disease validity (search.clinicalgenome.org/kb/gene-validity/download)
  clingen_gene_dosage.csv           ClinGen dosage, with report URLs (search.clinicalgenome.org/kb/gene-dosage/download)
  ClinGen_gene_curation_list_GRCh38.tsv  ClinGen dosage scores + HI/TS disease ids (ftp.clinicalgenome.org)
  NCBI2Reactome.txt, ReactomePathways.txt, ReactomePathwaysRelation.txt   (reactome.org/download/current/)
  global_entries.json, global_vectors.npz   (written by global_index.py: identities + phenotype vectors)
Out (data/derived/global/):
  mechanism/<bucket>.json   same djb2 % 64 bucketing as neighbours/
  clusters.json             mechanism clusters with label, mix, phenotypes, members, rationale
  meta.json                 "mechanism" section: counts, rules, sources, sanity checks

Curated databases only. Every mechanism value carries the URL of the record it came from, and the
source label is kept verbatim next to the normalised class.
"""
from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict, deque

import igraph as ig
import leidenalg
import numpy as np
import scipy.sparse as sp

from dcommon import DOWNLOADS, ROOT, TODAY, read_json, write_json
from global_index import N_BUCKETS, bucket

OUT = ROOT / "data" / "derived" / "global"
MECH_DIR = OUT / "mechanism"

# ---------------------------------------------------------------- vocabulary
G2P_CLASS = {"loss of function": "mech:loss-of-function", "dominant negative": "mech:dominant-negative",
             "gain of function": "mech:gain-of-function"}
CLASS_LABEL = {"mech:loss-of-function": "loss of function", "mech:haploinsufficiency": "haploinsufficiency",
               "mech:dominant-negative": "dominant negative", "mech:gain-of-function": "gain of function"}
G2P_URL = "https://www.ebi.ac.uk/gene2phenotype/lgd/{}"
REACTOME_URL = "https://reactome.org/content/detail/{}"
HI_TEXT = {3: "sufficient", 2: "some"}

# ---------------------------------------------------------------- pathway rule
MID_DEPTH = 3          # top-level Reactome pathway = depth 0; e.g. Metabolism(0) > Metabolism of lipids(1)
                       # > Sphingolipid metabolism(2) > Glycosphingolipid metabolism(3)
MIN_DEPTH = 2          # a leaf shallower than MID_DEPTH is its own representative if depth >= 2
MAX_PATHWAY_GENES = 400  # broader than this is not "mid-level" (e.g. Neutrophil degranulation, ~480)
SHOW_PATHWAYS = 5

# ---------------------------------------------------------------- graph rule
W_PATHWAY, W_PHENO = 0.75, 0.25   # mechanism (shared pathways) dominates; phenotype refines
KNN = 15
RESOLUTION = 1.0
MAX_CLUSTER, MIN_CLUSTER = 80, 5
SEED = 20261003
TOP_NEIGHBOURS = 10

SANITY_SETS = {
    "lysosomal_storage": ["GBA1", "GLA", "HEXA", "HEXB", "GALC", "ARSA", "ASAH1", "SMPD1", "NPC1", "NPC2", "GAA",
                          "IDUA", "IDS", "SGSH", "NAGLU", "HGSNAT", "GNS", "GALNS", "GLB1", "ARSB", "GUSB",
                          "NEU1", "CTSA", "GNPTAB", "MAN2B1", "MANBA", "AGA", "FUCA1", "NAGA", "LIPA", "PSAP",
                          "GM2A", "SUMF1", "CLN3", "PPT1", "TPP1", "CTSD", "LAMP2"],
    "rasopathies": ["PTPN11", "SOS1", "RAF1", "KRAS", "HRAS", "BRAF", "MAP2K1"],
    "sodium_channel_epilepsies": ["SCN1A", "SCN2A", "SCN8A", "SCN1B", "SCN3A"],
    "snare_slice_11": ["STXBP1", "SYT1", "SNAP25", "VAMP2", "STX1B", "SYT2", "CPLX1", "UNC13A", "STX1A", "NSF",
                       "SLC6A1"],
}


def read_clingen_csv(path):
    """ClinGen web downloads: banner rows, a header row, '+++' separator rows, then data."""
    rows, header = [], None
    with open(path, newline="") as fh:
        for r in csv.reader(fh):
            if not r or r[0].startswith("+++"):
                continue
            if header is None:
                if r[0] == "GENE SYMBOL":
                    header = r
                continue
            rows.append(dict(zip(header, r)))
    return rows


def file_created(path):
    with open(path) as fh:
        for line in fh:
            m = re.search(r"FILE CREATED: (\d{4}-\d{2}-\d{2})", line)
            if m:
                return m.group(1)
    return None


def main():
    MECH_DIR.mkdir(parents=True, exist_ok=True)
    G = read_json(DOWNLOADS / "global_entries.json")
    E = G["entries"]
    ic = G["ic"]
    hpo_names = G["hpo_names"]
    anc = {t: set(v) for t, v in G["ancestors"].items()}
    q_ids = G["q_ids"]
    qpos = {k: i for i, k in enumerate(q_ids)}
    X = sp.load_npz(DOWNLOADS / "global_vectors.npz").tocsr()

    by_mondo = {k for k in E if k.startswith("MONDO:")}
    by_omim, by_gene_single = defaultdict(set), defaultdict(set)
    for k, e in E.items():
        for o in e["omim"]:
            by_omim[o].add(k)
        if len(e["genes"]) == 1:
            by_gene_single[e["genes"][0]].add(k)

    # ================================================================ 1. mechanisms (curated only)
    mech = defaultdict(list)       # disease id -> [record]
    validity = defaultdict(list)
    join_stats = Counter()

    def attach_targets(mondo, mims, gene):
        if mondo and mondo in by_mondo:
            return [mondo], "MONDO"
        hits = set().union(*(by_omim.get(m, set()) for m in mims)) if mims else set()
        if len(hits) == 1:
            return list(hits), "OMIM"
        cands = by_gene_single.get(gene, set())
        if len(cands) == 1:
            return list(cands), "gene (only single-gene entry for this gene)"
        return [], None

    g2p_rows = list(csv.DictReader(open(DOWNLOADS / "g2p_all.csv", newline="")))
    g2p_monoallelic = set()
    for r in g2p_rows:
        conf = (r["confidence"] or "").strip()
        if conf == "refuted":
            join_stats["g2p_refuted_skipped"] += 1
            continue
        mims = [m.strip() for m in (r["disease mim"] or "").split(";") if m.strip()]
        targets, how = attach_targets((r["disease MONDO"] or "").strip(), mims, r["gene symbol"].strip())
        if not targets:
            join_stats["g2p_unjoined"] += 1
            continue
        join_stats[f"g2p_joined_by_{how.split(' ')[0]}"] += 1
        label = r["molecular mechanism"].strip()
        if r["molecular mechanism categorisation"].strip():
            label += f" ({r['molecular mechanism categorisation'].strip()})"
        rec = {"class": G2P_CLASS.get(r["molecular mechanism"].strip()) if conf != "disputed" else None,
               "source": "G2P", "label_verbatim": label, "url": G2P_URL.format(r["g2p id"]),
               "confidence": conf, "allelic_requirement": r["allelic requirement"],
               "mechanism_support": r["molecular mechanism support"],
               "variant_consequence": r["variant consequence"], "gene": r["gene symbol"],
               "panels": r["panel"], "joined_by": how, "record": r["g2p id"]}
        if r["molecular mechanism evidence"].strip():
            rec["mechanism_evidence"] = r["molecular mechanism evidence"].strip()[:400]
        for t in targets:
            mech[t].append(rec)
            if r["allelic requirement"].startswith("monoallelic"):
                g2p_monoallelic.add(t)

    for r in read_clingen_csv(DOWNLOADS / "clingen_gene_validity.csv"):
        targets, how = attach_targets(r["DISEASE ID (MONDO)"], [], r["GENE SYMBOL"])
        if not targets:
            join_stats["clingen_validity_unjoined"] += 1
            continue
        join_stats["clingen_validity_joined"] += 1
        for t in targets:
            validity[t].append({"classification": r["CLASSIFICATION"], "moi": r["MOI"], "gene": r["GENE SYMBOL"],
                                "url": r["ONLINE REPORT"], "date": r["CLASSIFICATION DATE"][:10],
                                "gcep": r["GCEP"], "joined_by": how})

    dosage_url = {r["GENE SYMBOL"]: r["ONLINE REPORT"] for r in read_clingen_csv(DOWNLOADS / "clingen_gene_dosage.csv")}
    dosage_text = {r["GENE SYMBOL"]: (r["HAPLOINSUFFICIENCY"], r["TRIPLOSENSITIVITY"])
                   for r in read_clingen_csv(DOWNLOADS / "clingen_gene_dosage.csv")}
    with open(DOWNLOADS / "ClinGen_gene_curation_list_GRCh38.tsv") as fh:
        hdr = None
        for line in fh:
            if line.startswith("#Gene Symbol"):
                hdr = line[1:].rstrip("\n").split("\t")
                continue
            if line.startswith("#") or not hdr:
                continue
            r = dict(zip(hdr, line.rstrip("\n").split("\t")))
            sym = r["Gene Symbol"]
            try:
                hi = int(r["Haploinsufficiency Score"])
            except ValueError:
                continue
            if hi not in HI_TEXT:
                continue
            hi_dis = (r.get("Haploinsufficiency Disease ID") or "").strip()
            targets = set()
            if hi_dis in by_mondo:
                targets.add(hi_dis)
            for k in by_gene_single.get(sym, ()):   # gene-level score: only dominant entries of that gene
                if "HP:0000006" in E[k]["inh"] or k in g2p_monoallelic:
                    targets.add(k)
            if not targets:
                join_stats["clingen_hi_unjoined"] += 1
                continue
            join_stats["clingen_hi_joined"] += 1
            verb = dosage_text.get(sym, (r["Haploinsufficiency Description"], ""))[0]
            for t in targets:
                mech[t].append({"class": "mech:haploinsufficiency", "source": "ClinGen dosage",
                                "label_verbatim": verb, "url": dosage_url.get(sym, ""),
                                "confidence": f"HI score {hi} ({HI_TEXT[hi]} evidence)", "gene": sym,
                                "joined_by": "HI disease id" if t == hi_dis else
                                "gene-level score on a dominant entry of this gene"})

    classes_of = {k: {m["class"] for m in v if m["class"]} for k, v in mech.items()}

    # ================================================================ 2. pathways (Reactome mid-level)
    names = {}
    with open(DOWNLOADS / "ReactomePathways.txt") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3 and f[2] == "Homo sapiens":
                names[f[0]] = f[1].strip()
    parents = defaultdict(set)
    children = defaultdict(set)
    with open(DOWNLOADS / "ReactomePathwaysRelation.txt") as fh:
        for line in fh:
            a, b = line.rstrip("\n").split("\t")
            if a.startswith("R-HSA") and b.startswith("R-HSA"):
                parents[b].add(a)
                children[a].add(b)
    roots = [p for p in names if not parents.get(p)]
    depth = {}
    dq = deque((r, 0) for r in roots)
    while dq:
        p, d = dq.popleft()
        if p in depth and depth[p] <= d:
            continue
        depth[p] = d
        for c in children.get(p, ()):
            dq.append((c, d + 1))

    sym_to_ncbi = {}
    for line in (DOWNLOADS / "genes_to_disease.txt").read_text().splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 2:
            sym_to_ncbi.setdefault(f[1], f[0].replace("NCBIGene:", ""))
    ncbi_to_sym = {v: k for k, v in sym_to_ncbi.items()}
    leaves, all_leaves = defaultdict(set), defaultdict(set)
    with open(DOWNLOADS / "NCBI2Reactome.txt") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 6 and f[5] == "Homo sapiens" and f[1] in names:
                all_leaves[f[0]].add(f[1])
                if f[0] in ncbi_to_sym:
                    leaves[ncbi_to_sym[f[0]]].add(f[1])

    anc_cache = {}

    def p_ancestors(p):
        if p not in anc_cache:
            out = {p}
            for q in parents.get(p, ()):
                out |= p_ancestors(q)
            anc_cache[p] = out
        return anc_cache[p]

    size = Counter()                      # human genes per pathway (all of Reactome, not only disease genes)
    for gid, ls in all_leaves.items():
        for p in set().union(*(p_ancestors(x) for x in ls)):
            size[p] += 1
    n_human_genes = len(all_leaves)

    def representatives(leaf):
        d = depth.get(leaf)
        if d is None:
            return set()
        if d <= MID_DEPTH:
            return {leaf} if d >= MIN_DEPTH else set()
        return {a for a in p_ancestors(leaf) if depth.get(a) == MID_DEPTH}

    gene_pw, gene_pw_rank = {}, {}
    for gsym, ls in leaves.items():
        votes = Counter()
        for leaf in ls:
            for rep in representatives(leaf):
                if size[rep] <= MAX_PATHWAY_GENES:
                    votes[rep] += 1
        if votes:
            gene_pw[gsym] = set(votes)
            gene_pw_rank[gsym] = sorted(votes, key=lambda p: (-votes[p], size[p], names[p]))

    # ================================================================ 3. clusters
    # Nodes are GENES: pathways are a property of the gene, so a gene's allelic diseases must share a
    # cluster (a disease-level graph split SCN1A's own diseases across four clusters), and genes with
    # many somatic/allelic entries (BRAF, KRAS) must not dominate cluster sizes. Each single-gene
    # disease then inherits its gene's cluster.
    dis_of_gene = defaultdict(list)
    for k, e in E.items():
        if len(e["genes"]) == 1 and e["genes"][0] in gene_pw:
            dis_of_gene[e["genes"][0]].append(k)
    nodes = sorted(dis_of_gene)                                  # genes
    npos = {g_: i for i, g_ in enumerate(nodes)}
    ndis = np.array([len(dis_of_gene[g_]) for g_ in nodes])
    pw_list = sorted({p for g_ in nodes for p in gene_pw[g_]})
    pw_ix = {p: i for i, p in enumerate(pw_list)}
    idf = np.array([math.log(n_human_genes / max(1, size[p])) for p in pw_list], dtype=np.float32)
    rows_, cols_ = [], []
    for i, g_ in enumerate(nodes):
        for p in gene_pw[g_]:
            rows_.append(i)
            cols_.append(pw_ix[p])
    B = sp.csr_matrix((np.ones(len(rows_), dtype=np.float32), (rows_, cols_)), shape=(len(nodes), len(pw_list)))
    Bw = B @ sp.diags(idf)                                       # IDF-weighted membership
    tot = np.asarray(Bw.sum(axis=1)).ravel()
    # gene phenotype vector = centroid of its diseases' vectors (diseases with >= 5 terms), re-normalised
    rr, cc, vv = [], [], []
    for i, g_ in enumerate(nodes):
        ks = [qpos[k] for k in dis_of_gene[g_] if k in qpos]
        for q in ks:
            rr.append(i)
            cc.append(q)
            vv.append(1.0 / len(ks))
    M = sp.csr_matrix((vv, (rr, cc)), shape=(len(nodes), X.shape[0]))
    Xg = (M @ X).tocsr()
    nrm = np.sqrt(np.asarray(Xg.multiply(Xg).sum(axis=1)).ravel())
    nrm[nrm == 0] = 1
    Xg = sp.diags(1 / nrm) @ Xg
    BwT = Bw.T.tocsc()
    XgT = Xg.T.tocsc()
    knn = {}
    BLOCK = 1500
    for s0 in range(0, len(nodes), BLOCK):
        inter = (B[s0:s0 + BLOCK] @ BwT).toarray()               # sum of IDF over shared pathways
        cos = (Xg[s0:s0 + BLOCK] @ XgT).toarray()
        for r in range(inter.shape[0]):
            i = s0 + r
            it = inter[r]
            union = tot[i] + tot - it
            jac = np.where(it > 0, it / np.maximum(union, 1e-9), 0.0)
            w = np.where(it > 0, W_PATHWAY * jac + W_PHENO * cos[r], 0.0)
            w[i] = 0.0
            nz = np.nonzero(w)[0]
            if not len(nz):
                continue
            top = nz[np.argsort(-w[nz])[:KNN]]
            knn[i] = [(int(j), float(w[j]), float(jac[j]), float(cos[r][j])) for j in top]
    edges = {}
    for i, lst in knn.items():
        for j, w, jac, c in lst:
            a, b = (i, j) if i < j else (j, i)
            if w > edges.get((a, b), (0,))[0]:
                edges[(a, b)] = (w, jac, c)
    graph = ig.Graph(n=len(nodes), edges=list(edges.keys()))
    graph.es["weight"] = [v[0] for v in edges.values()]

    def leiden(gr, res):
        return leidenalg.find_partition(gr, leidenalg.RBConfigurationVertexPartition, weights="weight",
                                        resolution_parameter=res, seed=SEED, n_iterations=-1)

    membership = list(leiden(graph, RESOLUTION).membership)
    # re-split communities holding more than MAX_CLUSTER diseases, on their own subgraph
    next_id = max(membership) + 1
    for rnd in range(1, 7):
        groups = defaultdict(list)
        for v, c in enumerate(membership):
            groups[c].append(v)
        changed = False
        for c, vs in groups.items():
            if ndis[vs].sum() <= MAX_CLUSTER or len(vs) < 2:
                continue
            part = leiden(graph.subgraph(vs), RESOLUTION * (2 ** rnd))
            if len(set(part.membership)) == 1:
                continue
            changed = True
            remap = {}
            for local, cc_ in enumerate(part.membership):
                if cc_ not in remap:
                    remap[cc_] = next_id
                    next_id += 1
                membership[vs[local]] = remap[cc_]
        if not changed:
            break
    groups = defaultdict(list)
    for v, c in enumerate(membership):
        groups[c].append(v)
    ordered = sorted(groups.values(), key=lambda vs: (-int(ndis[vs].sum()), nodes[vs[0]]))
    cluster_of, cluster_of_gene, clusters = {}, {}, []
    for n_, vs in enumerate(ordered):
        cid = f"MC{n_ + 1:04d}"
        mem = []
        for v in vs:
            cluster_of_gene[nodes[v]] = cid
            for k in dis_of_gene[nodes[v]]:
                cluster_of[k] = cid
                mem.append(k)
        clusters.append((cid, sorted(mem)))

    # ---------------------------------------------------------------- cluster descriptions
    def prop_terms(k):
        out = set()
        for t in E[k]["direct"]:
            out |= anc.get(t, {t})
        return out

    def non_redundant(terms, k):
        out = []
        for t in terms:
            if any(t in anc.get(u, set()) for u in out):
                continue
            out.append(t)
            if len(out) == k:
                break
        return out

    clusters_out = []
    for cid, mem in clusters:
        pwc = Counter(p for k in mem for p in gene_pw[E[k]["genes"][0]])
        top_pw = sorted(pwc, key=lambda p: (-pwc[p], size[p], names[p]))[:3]
        mix = Counter()
        for k in mem:
            cl = classes_of.get(k, set())
            if not cl:
                mix["unassigned"] += 1
            for c in cl:
                mix[CLASS_LABEL[c]] += 1
        assigned = {c: n for c, n in mix.items() if c != "unassigned"}
        dom = max(assigned, key=assigned.get) if assigned else None
        n_with = sum(1 for k in mem if classes_of.get(k))
        dom_txt = (dom if dom and assigned[dom] >= 0.5 * n_with else "mixed mechanism") if dom else "mechanism unassigned"
        ph_mem = [k for k in mem if E[k]["n"] >= 5]
        tc = Counter()
        for k in ph_mem:
            for t in prop_terms(k):
                if ic.get(t, 0) >= 2.5:
                    tc[t] += 1
        cand = sorted((t for t in tc if tc[t] >= max(2, 0.3 * len(ph_mem))),
                      key=lambda t: (-(tc[t] / max(1, len(ph_mem))) * ic[t], t))
        phen = non_redundant(cand, 3)
        genes = Counter(E[k]["genes"][0] for k in mem)
        label = " · ".join([names[top_pw[0]] if top_pw else "no shared pathway", dom_txt]
                           + ([hpo_names.get(phen[0], phen[0]).lower()] if phen else []))
        clusters_out.append({
            "id": cid, "label": label, "size": len(mem), "small": len(mem) < MIN_CLUSTER,
            "top_pathways": [{"id": p, "name": names[p], "coverage": round(pwc[p] / len(mem), 3),
                              "url": REACTOME_URL.format(p)} for p in top_pw],
            "mechanism_mix": dict(mix.most_common()),
            "dominant_mechanism": dom_txt,
            "distinctive_phenotypes": [{"hpo": t, "name": hpo_names.get(t, t), "ic": round(ic[t], 2),
                                        "coverage": round(tc[t] / max(1, len(ph_mem)), 3)} for t in phen],
            "genes": dict(genes.most_common(12)),
            "members": mem,
            "rationale": (f"{len(mem)} single-gene diseases from {len(genes)} genes. Genes were grouped by Leiden "
                          f"on a graph whose edges require a shared mid-level Reactome pathway and weigh "
                          f"{W_PATHWAY} x IDF-weighted pathway Jaccard + {W_PHENO} x IC-weighted phenotype cosine "
                          f"(gene phenotype = centroid of its diseases); each disease inherits its gene's cluster. "
                          + (f"{pwc[top_pw[0]]}/{len(mem)} members share '{names[top_pw[0]]}'. " if top_pw else "")
                          + f"Mechanism class (G2P/ClinGen) known for {n_with}/{len(mem)}"
                          + (f", mostly {dom}." if dom else ".")
                          + (f" Phenotype refinement: {len(ph_mem)} members with >= 5 terms; enriched for "
                             + ", ".join(hpo_names.get(t, t) for t in phen) + "." if phen else "")),
            "evidence_basis": {"pathways": "Reactome NCBI2Reactome (lowest level) rolled up to depth 3",
                               "mechanism": "G2P molecular mechanism; ClinGen dosage haploinsufficiency",
                               "phenotype": "HPO phenotype.hpoa, IC-weighted cosine (global index)"},
        })

    # ---------------------------------------------------------------- per-disease shard records
    members_of = {cid: mem for cid, mem in clusters}
    shards = defaultdict(dict)
    shard_pw = defaultdict(set)
    for k, e in E.items():
        rec = {}
        if mech.get(k):
            rec["mechanisms"] = mech[k]
        if validity.get(k):
            rec["validity"] = validity[k]
        pws = []
        if len(e["genes"]) == 1 and e["genes"][0] in gene_pw_rank:
            pws = gene_pw_rank[e["genes"][0]][:SHOW_PATHWAYS]
        elif 1 < len(e["genes"]) <= 3:
            votes = Counter(p for g in e["genes"] for p in gene_pw_rank.get(g, [])[:SHOW_PATHWAYS])
            pws = [p for p, _ in votes.most_common(SHOW_PATHWAYS)]
        if pws:
            rec["pathways"] = pws
            shard_pw[bucket(k)].update(pws)
        if k in cluster_of:
            rec["cluster_id"] = cluster_of[k]
            g0 = e["genes"][0]
            wmap = {nodes[j]: w for j, w, _jac, _c in knn.get(npos[g0], [])}
            wmap[g0] = 1.0
            cands = []
            for other in members_of[cluster_of[k]]:
                if other == k:
                    continue
                g1 = E[other]["genes"][0]
                shared_pw = sorted(gene_pw[g0] & gene_pw[g1])
                shared_cl = sorted(classes_of.get(k, set()) & classes_of.get(other, set()))
                if not (shared_pw and shared_cl):
                    continue
                pc = float(X[qpos[k]].multiply(X[qpos[other]]).sum()) if k in qpos and other in qpos else 0.0
                cands.append((wmap.get(g1, 0.0), pc, other, shared_pw, shared_cl))
            cands.sort(key=lambda x: (-x[0], -x[1], x[2]))
            mn = [{"id": o, "gene": E[o]["genes"][0], "shared_pathways": sp_[:5], "shared_mechanisms": sc_,
                   "gene_edge_weight": round(w_, 3), "phenotype_cosine": round(pc_, 3)}
                  for w_, pc_, o, sp_, sc_ in cands[:TOP_NEIGHBOURS]]
            for x_ in mn:
                shard_pw[bucket(k)].update(x_["shared_pathways"])
            if mn:
                rec["mechanism_neighbours"] = mn
        if rec:
            shards[bucket(k)][k] = rec
    sizes = []
    for b in range(N_BUCKETS):
        sizes.append(write_json(MECH_DIR / f"{b}.json",
                                {"bucket": b, "p": {p: names[p] for p in sorted(shard_pw[b])}, "d": shards[b]},
                                compact=True))
    size_clusters = write_json(OUT / "clusters.json", {
        "about": "Mechanism clusters over single-gene diseases: Leiden communities on a pathway-dominant graph "
                 "(phenotype refines). Labels are '<top pathway> · <dominant mechanism> · <distinctive phenotype>'. "
                 "Computed, not curated.",
        "generated": TODAY, "n_clusters": len(clusters_out),
        "clusters": clusters_out}, compact=False)

    # ---------------------------------------------------------------- sanity checks
    cl_by_id = {c["id"]: c for c in clusters_out}
    sanity = {}
    for name, genes in SANITY_SETS.items():
        hits = sorted(((E[k]["genes"][0], k, E[k]["name"], cluster_of.get(k)) for k in E
                       if len(E[k]["genes"]) == 1 and E[k]["genes"][0] in genes), key=lambda x: (x[3] or "", x[0]))
        by_cl = defaultdict(list)
        for gsym, k, nm, c in hits:
            by_cl[c].append(f"{gsym}: {nm}")
        sanity[name] = {
            "genes": genes,
            "diseases": len(hits),
            "clustered": sum(1 for h in hits if h[3]),
            "clusters": [{"cluster_id": c, "label": cl_by_id[c]["label"] if c else None,
                          "size": cl_by_id[c]["size"] if c else None, "members_from_set": v}
                         for c, v in sorted(by_cl.items(), key=lambda kv: -len(kv[1]))],
        }

    sizes_hist = Counter()
    for c in clusters_out:
        s = c["size"]
        sizes_hist["<5" if s < 5 else "5-80" if s <= 80 else ">80"] += 1
    in_target = sum(c["size"] for c in clusters_out if MIN_CLUSTER <= c["size"] <= MAX_CLUSTER)
    meta_path = OUT / "meta.json"
    meta = read_json(meta_path)
    meta["mechanism"] = {
        "generated": TODAY,
        "counts": {
            "diseases_with_mechanism_class": sum(1 for k in E if classes_of.get(k)),
            "diseases_with_any_mechanism_record": sum(1 for k in E if mech.get(k)),
            "diseases_with_clingen_validity": sum(1 for k in E if validity.get(k)),
            "diseases_with_pathway": sum(1 for k, r in shards.items() for _ in [0]
                                         for kk in r if "pathways" in r[kk]),
            "clustered_diseases": len(cluster_of),
            "clusters": len(clusters_out),
            "clusters_by_size": dict(sizes_hist),
            "diseases_in_5_to_80_clusters": in_target,
            "genes_with_mid_level_pathway": len(gene_pw),
            "join_stats": dict(join_stats),
            "class_counts": dict(Counter(c for v in classes_of.values() for c in v)),
        },
        "sources": {
            "G2P": {"file": "g2p_all.csv", "url": "https://www.ebi.ac.uk/gene2phenotype/api/panel/all/download/",
                    "retrieved": TODAY, "records": len(g2p_rows)},
            "ClinGen_validity": {"file": "clingen_gene_validity.csv",
                                 "file_created": file_created(DOWNLOADS / "clingen_gene_validity.csv")},
            "ClinGen_dosage": {"files": ["clingen_gene_dosage.csv", "ClinGen_gene_curation_list_GRCh38.tsv"],
                               "file_created": file_created(DOWNLOADS / "clingen_gene_dosage.csv")},
            "Reactome": {"files": ["NCBI2Reactome.txt", "ReactomePathways.txt", "ReactomePathwaysRelation.txt"],
                         "url": "https://reactome.org/download/current/", "retrieved": TODAY},
        },
        "rules": {
            "class_mapping": {"G2P 'loss of function'": "mech:loss-of-function",
                              "G2P 'dominant negative'": "mech:dominant-negative",
                              "G2P 'gain of function'": "mech:gain-of-function",
                              "G2P 'undetermined' / 'undetermined non-loss-of-function'": "no class (label kept)",
                              "ClinGen HI score 3 or 2": "mech:haploinsufficiency (dominant entries of that gene, "
                                                         "or the curated HI disease)",
                              "G2P disputed": "label kept, no class", "G2P refuted": "skipped"},
            "join": "MONDO id, else a unique OMIM number, else the only single-gene entry for that gene",
            "pathway_level": (f"each gene's lowest-level Reactome pathways rolled up to their depth-{MID_DEPTH} "
                              f"ancestor (top level = 0); a shallower leaf at depth >= {MIN_DEPTH} is kept as is; "
                              f"anything with > {MAX_PATHWAY_GENES} genes is dropped as too broad; up to "
                              f"{SHOW_PATHWAYS} shown per gene, most-annotated first"),
            "graph": (f"nodes = genes of single-gene diseases with >= 1 mid-level pathway; edge only if they "
                      f"share a pathway; weight = {W_PATHWAY} x IDF-weighted pathway Jaccard (IDF over all "
                      f"Reactome human genes) + {W_PHENO} x phenotype cosine of the genes' disease centroids; "
                      f"{KNN} nearest neighbours per gene, symmetrised; diseases inherit their gene's cluster"),
            "community_detection": (f"Leiden (RBConfiguration, resolution {RESOLUTION}, seed {SEED}); communities "
                                    f"holding > {MAX_CLUSTER} diseases re-split on their own subgraph at doubled "
                                    f"resolution (up to 6 rounds)"),
            "mechanism_neighbours": "same cluster AND >= 1 shared pathway AND >= 1 shared mechanism class",
            "url_templates": {"G2P": G2P_URL.format("{g2p_id}"), "Reactome": REACTOME_URL.format("{id}")},
        },
        "sanity_checks": sanity,
        "files": {"mechanism_total": sum(sizes), "mechanism_max_shard": max(sizes), "clusters.json": size_clusters},
    }
    write_json(meta_path, meta)

    c = meta["mechanism"]["counts"]
    print(f"[mechanism] class for {c['diseases_with_mechanism_class']} diseases "
          f"(records for {c['diseases_with_any_mechanism_record']}), validity for {c['diseases_with_clingen_validity']}, "
          f"pathways for {c['diseases_with_pathway']}; {c['clustered_diseases']} clustered into {c['clusters']} "
          f"clusters {c['clusters_by_size']} ({in_target} diseases in 5-80 clusters)")
    print(f"  shards {sum(sizes) / 1024 / 1024:.1f} MB (max {max(sizes) / 1024:.0f} KB), clusters.json "
          f"{size_clusters / 1024:.0f} KB; joins {dict(join_stats)}")
    for name, s in sanity.items():
        print(f"\n  == {name}: {s['clustered']}/{s['diseases']} clustered")
        for cc in s["clusters"][:8]:
            print(f"     {cc['cluster_id']} (n={cc['size']}) {cc['label']}: {len(cc['members_from_set'])} -> "
                  f"{'; '.join(cc['members_from_set'][:6])}")


if __name__ == "__main__":
    main()
