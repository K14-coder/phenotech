// The selected-disease summary on the atlas (the brief's concept mockup): centrality, key investigators
// and active patient groups. Cross-cluster bridges live in lib/bridges.ts.
import { neighbors, type GraphIndex } from "./graph";
import type { AtlasEdge, AtlasNode } from "./types";

/** attrs.centrality: 0–100 betweenness percentile computed by the build (pipeline/build_graph.py). */
export function centralityOf(n: AtlasNode | undefined): number | null {
  const c = (n?.attrs as { centrality?: unknown } | undefined)?.centrality;
  return typeof c === "number" && Number.isFinite(c) ? Math.max(0, Math.min(100, c)) : null;
}

export interface Investigator {
  researcher: AtlasNode;
  institution: string | null;
  /** works_on links to the disease or its gene */
  links: number;
}

/** Researchers with a works_on link to the disease or its gene, and their distinct institutions. */
export function investigatorsFor(idx: GraphIndex, diseaseId: string): { people: Investigator[]; institutions: string[] } {
  const genes = neighbors(idx, diseaseId, { relations: ["causes"], direction: "in" }).map((g) => g.other);
  const byId = new Map<string, Investigator>();
  for (const target of [diseaseId, ...genes]) {
    for (const nb of neighbors(idx, target, { relations: ["works_on"], direction: "in" })) {
      const r = idx.nodeById.get(nb.other);
      if (!r || r.type !== "researcher") continue;
      const cur = byId.get(r.id);
      if (cur) cur.links++;
      else byId.set(r.id, { researcher: r, institution: r.attrs?.affiliation?.trim() || null, links: 1 });
    }
  }
  const people = [...byId.values()].sort(
    (a, b) =>
      b.links - a.links ||
      (centralityOf(b.researcher) ?? 0) - (centralityOf(a.researcher) ?? 0) ||
      a.researcher.label.localeCompare(b.researcher.label),
  );
  const institutions = new Map<string, string>();
  for (const p of people) if (p.institution) institutions.set(p.institution.toLowerCase(), p.institution);
  return { people, institutions: [...institutions.values()] };
}

export interface ActiveGroup {
  node: AtlasNode;
  edge: AtlasEdge;
}

/** Patient organisations that serve the disease, plus registries and natural history studies that cover it. */
export function patientGroupsFor(idx: GraphIndex, diseaseId: string): { orgs: ActiveGroup[]; registries: ActiveGroup[]; studies: ActiveGroup[] } {
  const pick = (rel: "serves" | "covers", ok: (n: AtlasNode) => boolean) => {
    const seen = new Set<string>();
    const out: ActiveGroup[] = [];
    for (const nb of neighbors(idx, diseaseId, { relations: [rel], direction: "in" })) {
      const node = idx.nodeById.get(nb.other);
      if (!node || seen.has(node.id) || !ok(node)) continue;
      seen.add(node.id);
      out.push({ node, edge: nb.edge });
    }
    return out.sort((a, b) => b.edge.confidence - a.edge.confidence || a.node.label.localeCompare(b.node.label));
  };
  return {
    orgs: pick("serves", (n) => n.type === "patient_org"),
    registries: pick("covers", (n) => n.type === "asset" && n.attrs?.kind === "registry"),
    studies: pick("covers", (n) => n.type === "asset" && n.attrs?.kind === "natural_history_study"),
  };
}
