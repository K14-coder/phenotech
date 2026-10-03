import type { EvidenceLevel, NodeType } from "./types";

/** Muted categorical palette for clusters. Colour carries cluster meaning only. */
export const CLUSTER_COLORS = ["#C27C3A", "#5A9873", "#B65E69", "#4A95A0", "#8E8350", "#7A8BB5"];
export const NO_CLUSTER_COLOR = "#8B9099";

export function clusterColor(slot: number): string {
  if (slot < 0) return NO_CLUSTER_COLOR;
  return CLUSTER_COLORS[slot % CLUSTER_COLORS.length];
}

/** Node shape per type (Cytoscape shape names). Shape = type, colour = cluster. */
export const TYPE_SHAPE: Record<NodeType, string> = {
  disease: "ellipse",
  gene: "round-rectangle",
  variant_group: "round-tag",
  mechanism: "round-diamond",
  phenotype: "ellipse",
  patient_org: "round-hexagon",
  asset: "round-pentagon",
  study: "round-triangle",
  therapy: "star",
  publication: "rectangle",
  researcher: "round-octagon",
  grant: "cut-rectangle",
};

/** Neutral fills for nodes outside any cluster; hollow for symptoms. */
export const TYPE_FILL: Record<NodeType, string> = {
  disease: "#5C626C",
  gene: "#6B717B",
  variant_group: "#7D838C",
  mechanism: "#5C626C",
  phenotype: "#FFFFFF",
  patient_org: "#6B717B",
  asset: "#868B94",
  study: "#868B94",
  therapy: "#6B717B",
  publication: "#A2A7AE",
  researcher: "#959AA2",
  grant: "#A2A7AE",
};

export const HIDDEN_BY_DEFAULT: NodeType[] = ["publication", "researcher", "grant"];

/** Ordinal scale for evidence strength: filled = strong, outlined = inferred/hypothesis. */
export const LEVEL_BADGE_CLASS: Record<EvidenceLevel, string> = {
  clinical: "bg-accent-900 text-white border-accent-900",
  curated: "bg-accent-700 text-white border-accent-700",
  experimental: "bg-accent-100 text-accent-900 border-accent-200",
  observational: "bg-accent-50 text-accent-900 border-accent-100",
  inferred: "bg-white text-ink-2 border-ink-4 border-dashed",
  hypothesis: "bg-white text-ink-3 border-ink-4 border-dotted",
};
