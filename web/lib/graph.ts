import type {
  AtlasEdge,
  AtlasGraph,
  AtlasNode,
  Cluster,
  EvidenceLevel,
  Gap,
  NodeType,
  RelationType,
} from "./types";
import { MECHSIM_RELATIONS } from "./types";

// ---------- Index ----------

export interface Neighbor {
  edge: AtlasEdge;
  /** id of the node on the other end */
  other: string;
  /** "out" = this node is the edge source */
  dir: "out" | "in";
}

export type SynonymKind = "label" | "synonym" | "protein" | "subtype" | "xref" | "gene";

export interface SynonymEntry {
  nodeId: string;
  term: string;
  kind: SynonymKind;
}

export interface GraphIndex {
  graph: AtlasGraph;
  nodeById: Map<string, AtlasNode>;
  edgeById: Map<string, AtlasEdge>;
  adjacency: Map<string, Neighbor[]>;
  degree: Map<string, number>;
  clusterById: Map<string, Cluster>;
  clustersByNode: Map<string, Cluster[]>;
  gapsByAbout: Map<string, Gap[]>;
  synonyms: SynonymEntry[];
  /** max information content among phenotypes, for normalising */
  maxIc: number;
  /** non-fatal data problems found while indexing (dangling edges etc.) */
  warnings: string[];
  /** page URLs that community contributions came from (attrs.contributed / contributed_sources) */
  contributedUrls: Set<string>;
}

const DEFAULT_URL = "/data/graph.json";
let cached: { url: string; promise: Promise<GraphIndex> } | null = null;

/** Fetches and indexes graph.json once per page session (fresh: true re-fetches, e.g. after a contribution). */
export function loadGraph(url = DEFAULT_URL, opts: { fresh?: boolean } = {}): Promise<GraphIndex> {
  if (!opts.fresh && cached && cached.url === url) return cached.promise;
  const promise = fetch(url, { cache: opts.fresh ? "no-store" : "no-cache" })
    .then((r) => {
      if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
      return r.json() as Promise<AtlasGraph>;
    })
    .then(buildIndex);
  promise.catch(() => {
    if (cached?.promise === promise) cached = null;
  });
  cached = { url, promise };
  return promise;
}

function clamp01(n: number) {
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
}

export function buildIndex(raw: AtlasGraph): GraphIndex {
  const warnings: string[] = [];
  const graph: AtlasGraph = {
    meta: raw.meta ?? { version: "unknown", generated_at: "", slice: "", sources: [] },
    nodes: Array.isArray(raw.nodes) ? raw.nodes : [],
    edges: Array.isArray(raw.edges) ? raw.edges : [],
    clusters: Array.isArray(raw.clusters) ? raw.clusters : [],
    gaps: Array.isArray(raw.gaps) ? raw.gaps : [],
  };
  graph.meta.sources = graph.meta.sources ?? [];

  // one node per id (first wins): merged sources can repeat an id, and every list, React key and
  // Cytoscape element downstream assumes ids are unique
  const nodeById = new Map<string, AtlasNode>();
  const keptNodes: AtlasNode[] = [];
  for (const n of graph.nodes) {
    if (!n?.id) continue;
    if (nodeById.has(n.id)) {
      warnings.push(`duplicate node ${n.id} (kept the first)`);
      continue;
    }
    nodeById.set(n.id, n);
    keptNodes.push(n);
  }
  graph.nodes = keptNodes;

  const edgeById = new Map<string, AtlasEdge>();
  const adjacency = new Map<string, Neighbor[]>();
  const keptEdges: AtlasEdge[] = [];
  for (const e of graph.edges) {
    if (!e?.source || !e?.target) continue;
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) {
      warnings.push(`edge ${e.id} points to a missing node`);
      continue;
    }
    const eid = e.id || `${e.source}|${e.type}|${e.target}`;
    if (edgeById.has(eid)) {
      warnings.push(`duplicate edge ${eid} (kept the first)`);
      continue;
    }
    const edge: AtlasEdge = {
      ...e,
      id: e.id || `${e.source}|${e.type}|${e.target}`,
      confidence: clamp01(Number(e.confidence)),
      evidence: Array.isArray(e.evidence) ? e.evidence : [],
      counter_evidence: Array.isArray(e.counter_evidence) ? e.counter_evidence : [],
      status: e.status ?? "unverified",
      evidence_level: e.evidence_level ?? "hypothesis",
    };
    edgeById.set(edge.id, edge);
    keptEdges.push(edge);
    push(adjacency, edge.source, { edge, other: edge.target, dir: "out" });
    push(adjacency, edge.target, { edge, other: edge.source, dir: "in" });
  }
  graph.edges = keptEdges;

  const degree = new Map<string, number>();
  // the computed mechanistic-similarity overlay does not count towards how connected a node is
  for (const id of nodeById.keys())
    degree.set(id, (adjacency.get(id) ?? []).filter((nb) => !MECHSIM_RELATIONS.includes(nb.edge.type)).length);

  const clusterById = new Map<string, Cluster>();
  const clustersByNode = new Map<string, Cluster[]>();
  for (const c of graph.clusters) {
    c.members = [...new Set((c.members ?? []).filter((m) => nodeById.has(m)))];
    c.edge_ids = [...new Set((c.edge_ids ?? []).filter((id) => edgeById.has(id)))];
    clusterById.set(c.id, c);
    for (const m of c.members) push(clustersByNode, m, c);
  }

  const gapsByAbout = new Map<string, Gap[]>();
  for (const g of graph.gaps) push(gapsByAbout, g.about, g);

  let maxIc = 0;
  for (const n of graph.nodes) {
    if (n.type === "phenotype" && typeof n.attrs?.ic === "number") maxIc = Math.max(maxIc, n.attrs.ic);
  }

  const contributedUrls = new Set<string>();
  const addUrl = (c: unknown) => {
    const u = (c as { url?: unknown } | null)?.url;
    if (typeof u === "string" && u) contributedUrls.add(u);
  };
  for (const n of graph.nodes) {
    const a = (n.attrs ?? {}) as { contributed?: unknown; contributed_sources?: unknown };
    addUrl(a.contributed);
    if (Array.isArray(a.contributed_sources)) a.contributed_sources.forEach(addUrl);
  }
  for (const e of graph.edges) addUrl((e.attrs as { contributed?: unknown } | undefined)?.contributed);

  return {
    contributedUrls,
    graph,
    nodeById,
    edgeById,
    adjacency,
    degree,
    clusterById,
    clustersByNode,
    gapsByAbout,
    synonyms: buildSynonymIndex(graph.nodes),
    maxIc: maxIc || 1,
    warnings,
  };
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V) {
  const arr = m.get(k);
  if (arr) arr.push(v);
  else m.set(k, [v]);
}

// ---------- Lookups ----------

export function getNode(idx: GraphIndex, id: string | null | undefined): AtlasNode | undefined {
  return id ? idx.nodeById.get(id) : undefined;
}

export interface NeighborQuery {
  types?: NodeType[];
  relations?: RelationType[];
  direction?: "out" | "in" | "both";
}

export function neighbors(idx: GraphIndex, id: string, q: NeighborQuery = {}): Neighbor[] {
  const list = idx.adjacency.get(id) ?? [];
  return list.filter((n) => {
    if (q.direction && q.direction !== "both" && n.dir !== q.direction) return false;
    if (q.relations && !q.relations.includes(n.edge.type)) return false;
    if (q.types) {
      const other = idx.nodeById.get(n.other);
      if (!other || !q.types.includes(other.type)) return false;
    }
    return true;
  });
}

export function edgesBetween(idx: GraphIndex, a: string, b: string): AtlasEdge[] {
  return (idx.adjacency.get(a) ?? []).filter((n) => n.other === b).map((n) => n.edge);
}

/** Cluster lookup: every cluster that lists this node as a member. */
export function clustersOf(idx: GraphIndex, nodeId: string): Cluster[] {
  return idx.clustersByNode.get(nodeId) ?? [];
}

/** Stable colour slot for a cluster (its position in graph.clusters). */
export function clusterSlot(idx: GraphIndex, clusterId: string): number {
  return idx.graph.clusters.findIndex((c) => c.id === clusterId);
}

export function gapsAbout(idx: GraphIndex, ids: string[]): Gap[] {
  const seen = new Set<string>();
  const out: Gap[] = [];
  for (const id of ids) {
    for (const g of idx.gapsByAbout.get(id) ?? []) {
      if (!seen.has(g.id)) {
        seen.add(g.id);
        out.push(g);
      }
    }
  }
  return out;
}

// ---------- Synonym index (search) ----------

export function buildSynonymIndex(nodes: AtlasNode[]): SynonymEntry[] {
  const out: SynonymEntry[] = [];
  for (const n of nodes) {
    const seen = new Set<string>();
    const add = (term: unknown, kind: SynonymKind) => {
      if (typeof term !== "string") return;
      const t = term.trim();
      const key = t.toLowerCase();
      if (!t || seen.has(key)) return;
      seen.add(key);
      out.push({ nodeId: n.id, term: t, kind });
    };
    add(n.label, "label");
    for (const s of n.synonyms ?? []) add(s, "synonym");
    if (n.type === "gene") add(n.attrs?.protein, "protein");
    if (n.type === "disease") for (const s of n.attrs?.subtypes ?? []) add(s?.name, "subtype");
    for (const [db, v] of Object.entries(n.xrefs ?? {})) {
      for (const x of Array.isArray(v) ? v : [v]) {
        if (typeof x !== "string") continue;
        add(x, "xref");
        if (!x.includes(":")) add(`${db}:${x}`, "xref");
      }
    }
    // HPO ids live in the node id for phenotypes ("phenotype:HP:0001250")
    if (n.type === "phenotype") add(n.id.replace(/^phenotype:/, ""), "xref");
  }
  return out;
}

// ---------- Evidence-weighted shortest path ----------

const LEVEL_PENALTY: Record<EvidenceLevel, number> = {
  clinical: 0,
  curated: 0,
  experimental: 0.1,
  observational: 0.15,
  inferred: 0.4,
  hypothesis: 1.5,
};

/** Cost of walking an edge: low for strong, well-sourced edges; high for weak or contested ones. */
export function edgeCost(e: AtlasEdge): number {
  const conf = Math.max(0.02, e.confidence);
  return (
    -Math.log(conf) +
    (LEVEL_PENALTY[e.evidence_level] ?? 0.5) +
    (e.status === "contested" ? 0.6 : 0) +
    0.15 // per-hop cost: prefer shorter routes among equally strong ones
  );
}

/** Passing through common symptoms (e.g. "seizure") says little; distinctive ones say more. */
function nodeCost(idx: GraphIndex, n: AtlasNode | undefined): number {
  if (!n) return 0;
  if (n.type === "phenotype") {
    const ic = typeof n.attrs?.ic === "number" ? n.attrs.ic : idx.maxIc / 2;
    return 0.8 * (1 - Math.min(1, ic / idx.maxIc));
  }
  return 0;
}

export interface PathStep {
  from: string;
  to: string;
  edge: AtlasEdge;
  /** true when walking the edge from its source to its target */
  forward: boolean;
}

export interface PathResult {
  nodes: string[];
  steps: PathStep[];
  cost: number;
  weakest: AtlasEdge | null;
}

export interface PathOptions {
  includeHypotheses?: boolean;
  excludeTypes?: NodeType[];
}

export function shortestEvidencePath(
  idx: GraphIndex,
  from: string,
  to: string,
  opts: PathOptions = {},
): PathResult | null {
  if (!idx.nodeById.has(from) || !idx.nodeById.has(to)) return null;
  if (from === to) return { nodes: [from], steps: [], cost: 0, weakest: null };
  const exclude = new Set(opts.excludeTypes ?? []);

  const dist = new Map<string, number>([[from, 0]]);
  const prev = new Map<string, { node: string; edge: AtlasEdge }>();
  const heap = new MinHeap();
  heap.push(from, 0);
  const done = new Set<string>();

  while (heap.size) {
    const { id, d } = heap.pop()!;
    if (done.has(id)) continue;
    done.add(id);
    if (id === to) break;
    for (const nb of idx.adjacency.get(id) ?? []) {
      if (done.has(nb.other)) continue;
      if (!opts.includeHypotheses && nb.edge.evidence_level === "hypothesis") continue;
      const other = idx.nodeById.get(nb.other);
      if (!other) continue;
      if (nb.other !== to && exclude.has(other.type)) continue;
      const nd = d + edgeCost(nb.edge) + (nb.other === to ? 0 : nodeCost(idx, other));
      if (nd < (dist.get(nb.other) ?? Infinity)) {
        dist.set(nb.other, nd);
        prev.set(nb.other, { node: id, edge: nb.edge });
        heap.push(nb.other, nd);
      }
    }
  }

  if (!prev.has(to)) return null;
  const nodes: string[] = [to];
  const steps: PathStep[] = [];
  let cur = to;
  while (cur !== from) {
    const p = prev.get(cur)!;
    steps.unshift({ from: p.node, to: cur, edge: p.edge, forward: p.edge.source === p.node });
    nodes.unshift(p.node);
    cur = p.node;
  }
  const weakest = steps.reduce<AtlasEdge | null>(
    (w, s) => (!w || s.edge.confidence < w.confidence ? s.edge : w),
    null,
  );
  return { nodes, steps, cost: dist.get(to) ?? 0, weakest };
}

class MinHeap {
  private items: { id: string; d: number }[] = [];
  get size() {
    return this.items.length;
  }
  push(id: string, d: number) {
    const a = this.items;
    a.push({ id, d });
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p].d <= a[i].d) break;
      [a[p], a[i]] = [a[i], a[p]];
      i = p;
    }
  }
  pop() {
    const a = this.items;
    if (!a.length) return undefined;
    const top = a[0];
    const last = a.pop()!;
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && a[l].d < a[m].d) m = l;
        if (r < a.length && a[r].d < a[m].d) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top;
  }
}

// ---------- URL helpers ----------

/** /disease/STXBP1 for "disease:STXBP1" */
export function diseaseHref(id: string): string {
  return `/disease/${encodeURIComponent(id.replace(/^disease:/, ""))}`;
}

export function diseaseIdFromParam(param: string): string {
  const p = decodeURIComponent(param);
  return p.startsWith("disease:") ? p : `disease:${p}`;
}

/**
 * Therapy-approach view for a mechanism (/approach): every disease it could apply to, ranked by fit.
 * Callers render a link only when this returns a path.
 */
export function approachHref(mechanismId: string): string | null {
  return `/approach?mechanism=${encodeURIComponent(mechanismId)}`;
}

/** /compare?a=VAMP2&b=STXBP1 (short gene ids; full disease ids are accepted too) */
export function compareHref(a: string, b: string): string {
  const s = (id: string) => encodeURIComponent(id.replace(/^disease:/, ""));
  return `/compare?a=${s(a)}&b=${s(b)}`;
}

export function atlasHref(focusId?: string): string {
  return focusId ? `/atlas?focus=${encodeURIComponent(focusId)}` : "/atlas";
}

export function pathHref(from?: string, to?: string): string {
  const q = new URLSearchParams();
  if (from) q.set("from", from);
  if (to) q.set("to", to);
  const s = q.toString();
  return s ? `/path?${s}` : "/path";
}

/** Primary destination for a node: diseases get their action page, everything else the atlas. */
export function nodeHref(n: AtlasNode): string {
  return n.type === "disease" ? diseaseHref(n.id) : atlasHref(n.id);
}
