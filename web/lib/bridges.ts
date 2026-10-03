// Cross-cluster bridges ("bridge across clusters" in the brief's concept mockup).
//
// A bridge is a link that crosses a cluster boundary:
//  1. family: a disease–disease link (shares_mechanism, similar_phenotype) whose two diseases share no
//     pathway-based cluster, with at least one of them in one. STXBP1 ↔ SLC6A1 counts: SLC6A1 sits
//     outside the SNAREopathy family.
//  2. therapy-cluster: a therapy→disease link (developed_for, candidate_for) that connects the disease
//     to a cluster it is not a member of (the therapy belongs to clusters, none of which include it).
//  3. therapy-span: a therapy→disease link whose therapy is also linked to a disease on the other side
//     of a pathway boundary (one medicine spanning two families).
// Hypothesis links can be bridges too: the map keeps their dash pattern, so certainty still shows.
import { clustersOf, type GraphIndex } from "./graph";
import type { AtlasEdge, AtlasNode, Cluster, RelationType } from "./types";

const DISEASE_LINKS: readonly RelationType[] = ["shares_mechanism", "similar_phenotype"];
const THERAPY_LINKS: readonly RelationType[] = ["developed_for", "candidate_for"];

export type BridgeRule = "family" | "therapy-cluster" | "therapy-span";

export interface Bridge {
  edge: AtlasEdge;
  rule: BridgeRule;
  /** therapy-cluster: the therapy's cluster that does not include the disease */
  cluster?: Cluster;
  /** therapy-span: a disease across the boundary that the same therapy is linked to */
  via?: AtlasNode;
  /** one plain sentence for the evidence panel */
  why: string;
}

export interface BridgeGroup {
  /** the node on the other end */
  other: AtlasNode;
  bridges: Bridge[];
}

const cache = new WeakMap<GraphIndex, Map<string, Bridge>>();

function pathwayClusters(idx: GraphIndex, id: string): Cluster[] {
  return clustersOf(idx, id).filter((c) => c.basis === "pathway");
}

/** "SNAREopathies" from "SNAREopathies: one presynaptic fusion machine, many diagnoses" */
export function familyName(c: Cluster): string {
  return c.label.split(":")[0].trim();
}

function families(cs: Cluster[]): string {
  return [...new Map(cs.map((c) => [c.id, familyName(c)])).values()].join(" / ");
}

/** a and b sit on different sides of a pathway-cluster boundary */
function crossesFamily(idx: GraphIndex, a: string, b: string): boolean {
  const pa = pathwayClusters(idx, a);
  const pb = pathwayClusters(idx, b);
  if (!pa.length && !pb.length) return false;
  return !pa.some((c) => pb.some((d) => d.id === c.id));
}

function familySentence(idx: GraphIndex, a: AtlasNode, b: AtlasNode): string {
  const pa = pathwayClusters(idx, a.id);
  const pb = pathwayClusters(idx, b.id);
  if (pa.length && !pb.length) return `It links the ${families(pa)} with ${b.label}, outside that family.`;
  if (pb.length && !pa.length) return `It links the ${families(pb)} with ${a.label}, outside that family.`;
  return `It links two families: the ${families(pa)} and the ${families(pb)}.`;
}

/** Every bridge in the atlas, keyed by edge id (computed once per loaded graph). */
export function bridgesOf(idx: GraphIndex): Map<string, Bridge> {
  const hit = cache.get(idx);
  if (hit) return hit;
  const out = new Map<string, Bridge>();
  for (const e of idx.graph.edges) {
    const s = idx.nodeById.get(e.source);
    const t = idx.nodeById.get(e.target);
    if (!s || !t) continue;
    if (DISEASE_LINKS.includes(e.type)) {
      if (s.type === "disease" && t.type === "disease" && crossesFamily(idx, s.id, t.id))
        out.set(e.id, { edge: e, rule: "family", why: familySentence(idx, s, t) });
      continue;
    }
    if (!THERAPY_LINKS.includes(e.type) || s.type !== "therapy" || t.type !== "disease") continue;
    const own = clustersOf(idx, s.id);
    if (own.length && !own.some((c) => c.members.includes(t.id))) {
      out.set(e.id, {
        edge: e,
        rule: "therapy-cluster",
        cluster: own[0],
        why: `The therapy belongs to the “${own[0].label}” cluster, which does not include ${t.label}.`,
      });
      continue;
    }
    // strongest other link first (developed_for before candidate_for), so the caption names the best example
    const via = (idx.adjacency.get(s.id) ?? [])
      .filter((nb) => nb.dir === "out" && nb.other !== t.id && THERAPY_LINKS.includes(nb.edge.type))
      .sort((a, b) => Number(b.edge.type === "developed_for") - Number(a.edge.type === "developed_for") || b.edge.confidence - a.edge.confidence)
      .map((nb) => idx.nodeById.get(nb.other))
      .find((d): d is AtlasNode => d?.type === "disease" && crossesFamily(idx, d.id, t.id));
    if (via) {
      const fam = families([...pathwayClusters(idx, via.id), ...pathwayClusters(idx, t.id)]);
      out.set(e.id, { edge: e, rule: "therapy-span", via, why: `The same therapy is also linked to ${via.label}, across the ${fam} boundary.` });
    }
  }
  cache.set(idx, out);
  return out;
}

/** A node's bridges, grouped by the node on the other end (two links to one disease are one connection). */
export function bridgesFor(idx: GraphIndex, nodeId: string): BridgeGroup[] {
  const all = bridgesOf(idx);
  const groups = new Map<string, BridgeGroup>();
  for (const nb of idx.adjacency.get(nodeId) ?? []) {
    const b = all.get(nb.edge.id);
    const other = idx.nodeById.get(nb.other);
    if (!b || !other) continue;
    const g = groups.get(other.id);
    if (g) g.bridges.push(b);
    else groups.set(other.id, { other, bridges: [b] });
  }
  // diseases first (the family links), then therapies; strongest first within each
  const best = (g: BridgeGroup) => Math.max(...g.bridges.map((b) => b.edge.confidence));
  const rank = (g: BridgeGroup) => (g.other.type === "disease" ? 0 : 1);
  return [...groups.values()].sort((a, b) => rank(a) - rank(b) || best(b) - best(a) || a.other.label.localeCompare(b.other.label));
}

/** Short caption from the selected node's point of view: why this connection crosses a boundary. */
export function bridgeCaption(idx: GraphIndex, fromId: string, g: BridgeGroup): string {
  const b = g.bridges[0];
  const mine = pathwayClusters(idx, fromId);
  if (b.rule === "therapy-cluster" && b.cluster) return `From another cluster: ${b.cluster.label}`;
  if (b.rule === "therapy-span" && b.via) {
    const theirs = pathwayClusters(idx, b.via.id);
    return `Also linked to ${b.via.label}, ${theirs.length ? `in the ${families(theirs)}` : `outside the ${families(mine)}`}`;
  }
  const theirs = pathwayClusters(idx, g.other.id);
  if (mine.length && !theirs.length) return `Outside the ${families(mine)}`;
  if (!mine.length) return `In the ${families(theirs)}, unlike this disease`;
  return `In the ${families(theirs)}, a different family`;
}
