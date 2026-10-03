"use client";

// Client-only (loaded with next/dynamic, ssr: false). Cytoscape + fcose.
//
// Layout stability: one fcose layout runs on load over the whole-atlas default view. After that,
// filters only hide/show nodes. Nodes that become visible for the first time are placed next to
// their visible neighbours (ring around a single anchor, or the centroid of several); only a large
// reveal (e.g. "show all symptoms") runs an incremental fcose with every existing node pinned.
import cytoscape, { type Core, type ElementDefinition, type Collection, type NodeSingular } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";
import type { GraphIndex } from "@/lib/graph";
import { bridgesOf } from "@/lib/bridges";
import { centralityOf } from "@/lib/glance";
import { NO_CLUSTER_COLOR, TYPE_FILL, TYPE_SHAPE } from "@/lib/style";
import { relationName } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";

let registered = false;
function ensureFcose() {
  if (!registered) {
    cytoscape.use(fcose);
    registered = true;
  }
}

const MAX_SLICES = 6;
/** node diameter range (px at zoom 1) */
const SIZE_MIN = 10;
const SIZE_MAX = 56;
/** accent tokens (app/globals.css) */
const ACCENT_200 = "#c7d8ea";
const ACCENT_500 = "#3e6ea5";
const ACCENT_700 = "#1f5a96";
const ACCENT_900 = "#153e67";
const EMPTY_SET = new Set<string>();
const EMPTY_COLORS = new Map<string, string[]>();

export interface GraphCanvasProps {
  idx: GraphIndex;
  hiddenNodeIds: Set<string>;
  /** nodes laid out on first load (the whole-atlas default view), even if currently hidden */
  layoutSeedIds: Set<string>;
  /** colours of the visible clusters each node belongs to (2+ = pie slices) */
  clusterColors: Map<string, string[]>;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  emphasisIds: Set<string> | null;
  /** bump n to fit the view around a node's neighbourhood */
  centerRequest: { id: string; n: number } | null;
  /** bump to fit everything visible (scope changes) */
  fitKey: number;
  /** dim everything outside the selected node's neighbourhood (off for the focus node in focus mode) */
  dimOnSelect?: boolean;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string) => void;
}

const LAYOUT_BASE = {
  name: "fcose",
  quality: "proof",
  nodeDimensionsIncludeLabels: true,
  packComponents: true,
  nodeRepulsion: 12000,
  idealEdgeLength: 95,
  edgeElasticity: 0.35,
  gravity: 0.3,
  gravityRange: 3.8,
  numIter: 2500,
  tile: true,
  padding: 48,
};

function baseColor(idx: GraphIndex, id: string) {
  const n = idx.nodeById.get(id);
  if (!n) return NO_CLUSTER_COLOR;
  return n.type === "phenotype" ? NO_CLUSTER_COLOR : TYPE_FILL[n.type] ?? NO_CLUSTER_COLOR;
}

/**
 * Size scales with centrality (attrs.centrality, the build's 0–100 betweenness percentile). Squared, so
 * the hubs stand out from the long tail of leaves. Graphs without centrality fall back to link counts.
 */
function nodeSize(idx: GraphIndex, n: AtlasNode): number {
  const c = centralityOf(n);
  if (c === null) return Math.min(SIZE_MAX, 12 + 6.5 * Math.sqrt(idx.degree.get(n.id) ?? 0));
  const t = c / 100;
  return SIZE_MIN + (SIZE_MAX - SIZE_MIN) * t * t;
}

function buildElements(idx: GraphIndex): ElementDefinition[] {
  const els: ElementDefinition[] = [];
  const nodeIds = new Set<string>();
  const bridges = bridgesOf(idx);
  for (const n of idx.graph.nodes) {
    if (!n?.id || nodeIds.has(n.id)) continue;
    nodeIds.add(n.id);
    const data: Record<string, unknown> = { id: n.id, label: n.label, color: baseColor(idx, n.id), size: nodeSize(idx, n), shape: TYPE_SHAPE[n.type] ?? "ellipse" };
    for (let i = 1; i <= MAX_SLICES; i++) {
      data[`p${i}c`] = "#ffffff";
      data[`p${i}s`] = 0;
    }
    els.push({ group: "nodes", data, classes: `t-${n.type}` });
  }
  const edgeIds = new Set<string>();
  for (const e of idx.graph.edges) {
    // never add an edge unless both endpoints exist (and never twice)
    if (!e?.id || edgeIds.has(e.id) || !nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    edgeIds.add(e.id);
    const rel = e.label ?? relationName(e.type);
    const bridge = bridges.has(e.id);
    els.push({
      group: "edges",
      data: { id: e.id, source: e.source, target: e.target, conf: e.confidence, rel: bridge ? `Bridge across clusters · ${rel}` : rel },
      classes: `lvl-${e.evidence_level}${e.status === "contested" ? " contested" : ""}${e.type === "candidate_for" ? " idea" : ""}${(e.attrs as { contributed?: unknown } | undefined)?.contributed ? " contrib" : ""}${bridge ? " bridge" : ""}`,
    });
  }
  return els;
}

function stylesheet(fontFamily: string): cytoscape.StylesheetJson {
  const pie: Record<string, unknown> = { "pie-size": "100%" };
  for (let i = 1; i <= MAX_SLICES; i++) {
    pie[`pie-${i}-background-color`] = `data(p${i}c)`;
    pie[`pie-${i}-background-size`] = `data(p${i}s)`;
  }
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        shape: "data(shape)",
        width: "data(size)",
        height: "data(size)",
        label: "data(label)",
        "font-family": fontFamily,
        "font-size": 10.5,
        color: "#3f4550",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 5,
        "text-wrap": "wrap",
        "text-max-width": "130px",
        "min-zoomed-font-size": 8,
        "text-background-color": "#ffffff",
        "text-background-opacity": 0.85,
        "text-background-padding": "1px",
        "border-width": 0,
        "transition-property": "opacity",
        "transition-duration": 150,
      },
    },
    { selector: "node.pie", style: pie },
    // non-round shapes: a white body with a cluster-coloured outline, so the round pie has no coloured corners
    { selector: 'node.pie[shape != "ellipse"]', style: { "background-color": "#ffffff", "border-width": 2, "border-color": "data(color)" } },
    { selector: "node.t-disease", style: { "font-size": 12.5, "font-weight": 600, color: "#16181d", "border-width": 1.5, "border-color": "#ffffff" } },
    { selector: "node.t-mechanism", style: { "font-size": 11, "font-weight": 500, color: "#16181d" } },
    { selector: "node.t-phenotype", style: { "background-color": "#ffffff", "border-width": 1.6, "border-color": "data(color)", "font-size": 9.5 } },
    { selector: "node.t-variant_group", style: { "font-size": 9.5 } },
    {
      selector: "edge",
      style: {
        width: "mapData(conf, 0, 1, 0.6, 2.2)",
        "line-color": "#cbd0d6",
        "curve-style": "bezier",
        opacity: 0.9,
        "transition-property": "opacity, line-color",
        "transition-duration": 150,
      },
    },
    { selector: "edge.lvl-inferred", style: { "line-style": "dashed", "line-dash-pattern": [6, 4] } },
    { selector: "edge.lvl-hypothesis", style: { "line-style": "dotted", opacity: 0.6 } },
    // computed "ideas worth testing" (candidate_for): dashed and labelled, never mistaken for evidence
    {
      selector: "edge.idea",
      style: {
        "line-style": "dashed",
        "line-dash-pattern": [5, 4],
        "line-color": "#a3a9b3",
        opacity: 0.85,
        label: "Hypothesis",
        "font-family": fontFamily,
        "font-size": 9,
        color: "#5f6672",
        "text-rotation": "autorotate",
        "text-background-color": "#ffffff",
        "text-background-opacity": 1,
        "text-background-padding": "1px",
      },
    },
    {
      selector: "edge.contested",
      style: {
        label: "!",
        "font-family": fontFamily,
        "font-size": 9,
        "font-weight": 700,
        color: "#7f520f",
        "text-background-color": "#fdf0d5",
        "text-background-opacity": 1,
        "text-background-shape": "circle",
        "text-background-padding": "3px",
        "text-border-color": "#e6c27c",
        "text-border-width": 1,
        "text-border-opacity": 1,
      },
    },
    {
      selector: "edge.hover",
      style: {
        label: "data(rel)",
        "font-family": fontFamily,
        "font-size": 10,
        "font-weight": 500,
        color: "#16181d",
        "text-rotation": "autorotate",
        "text-background-color": "#ffffff",
        "text-background-opacity": 1,
        "text-background-shape": "roundrectangle",
        "text-background-padding": "2px",
        "text-border-width": 0,
        "line-color": "#6b717b",
        width: 2.6,
      },
    },
    // community-contributed, not yet reviewed: lighter
    { selector: "edge.contrib", style: { "line-color": "#dfe2e6", opacity: 0.55, "line-style": "dashed", "line-dash-pattern": [2, 3] } },
    { selector: ".dim", style: { opacity: 0.12 } },
    { selector: "edge.hl", style: { "line-color": "#7d838c" } },
    // cross-cluster bridges: an accent line on a pale accent band. Dashes still mean inferred/hypothesis,
    // so a hypothetical bridge is a dashed accent line on the band. Hover names it.
    {
      selector: "edge.bridge",
      style: {
        "line-color": ACCENT_500,
        width: "mapData(conf, 0, 1, 1.5, 2.8)",
        "underlay-color": ACCENT_200,
        "underlay-padding": 3.5,
        "underlay-opacity": 0.85,
        "z-index": 2,
      },
    },
    { selector: "edge.bridge.hover", style: { "line-color": ACCENT_700, color: ACCENT_900, width: 2.8 } },
    { selector: "edge.bridge.dim", style: { "underlay-opacity": 0.1 } },
    { selector: "node:selected", style: { "border-width": 3, "border-color": "#153e67", "border-opacity": 1 } },
    { selector: "edge:selected", style: { "line-color": "#1f5a96", width: 3, opacity: 1 } },
    { selector: ".hidden", style: { display: "none" } },
  ] as unknown as cytoscape.StylesheetJson;
}

export default function GraphCanvas(props: GraphCanvasProps) {
  const { idx, selectedNodeId = null, selectedEdgeId = null, emphasisIds = null, centerRequest = null, fitKey = 0 } = props;
  const hiddenNodeIds = props.hiddenNodeIds ?? EMPTY_SET;
  const clusterColors = props.clusterColors ?? EMPTY_COLORS;
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const hoverRef = useRef<string | null>(null);
  const laidOut = useRef(false);
  const positioned = useRef(new Set<string>());
  const cbRef = useRef(props);
  // keep the latest props for Cytoscape event handlers (runs before the effects below)
  useEffect(() => {
    cbRef.current = props;
  });

  const emphasize = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const { selectedNodeId: sel, emphasisIds: emph, dimOnSelect = true } = cbRef.current;
    const focusId = hoverRef.current ?? (dimOnSelect ? sel : null);
    let coll: Collection | null = null;
    if (focusId) {
      const n = cy.getElementById(focusId);
      if (n.nonempty() && !n.hasClass("hidden")) coll = n.closedNeighborhood();
    } else if (emph && emph.size) {
      const nodes = cy.nodes().filter((n) => emph.has(n.id()));
      coll = nodes.union(nodes.edgesWith(nodes));
    }
    cy.batch(() => {
      cy.elements().removeClass("dim hl");
      if (!coll) return;
      cy.elements().not(coll).addClass("dim");
      coll.edges().addClass("hl");
    });
  };

  // init once per graph
  useEffect(() => {
    ensureFcose();
    const font = getComputedStyle(document.body).fontFamily || "Inter, system-ui, sans-serif";
    const cy = cytoscape({
      container: containerRef.current,
      elements: buildElements(idx),
      style: stylesheet(font),
      minZoom: 0.12,
      maxZoom: 3,
      boxSelectionEnabled: false,
      selectionType: "single",
    });
    cyRef.current = cy;
    laidOut.current = false;
    positioned.current = new Set();
    const container = containerRef.current!;

    cy.on("tap", "node", (e) => cbRef.current.onSelectNode(e.target.id()));
    cy.on("tap", "edge", (e) => cbRef.current.onSelectEdge(e.target.id()));
    cy.on("tap", (e) => {
      if (e.target === cy) cbRef.current.onSelectNode(null);
    });
    cy.on("mouseover", "node", (e) => {
      hoverRef.current = e.target.id();
      container.style.cursor = "pointer";
      emphasize();
    });
    cy.on("mouseout", "node", () => {
      hoverRef.current = null;
      container.style.cursor = "";
      emphasize();
    });
    cy.on("mouseover", "edge", (e) => {
      e.target.addClass("hover");
      container.style.cursor = "pointer";
    });
    cy.on("mouseout", "edge", (e) => {
      e.target.removeClass("hover");
      container.style.cursor = "";
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [idx]);

  // cluster colours: one colour, or pie slices for nodes in several visible clusters
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const colors = clusterColors?.get(n.id()) ?? [];
        if (colors.length >= 2) {
          const k = Math.min(colors.length, MAX_SLICES);
          const data: Record<string, unknown> = { color: colors[0] };
          for (let i = 1; i <= MAX_SLICES; i++) {
            data[`p${i}c`] = i <= k ? colors[i - 1] : "#ffffff";
            data[`p${i}s`] = i <= k ? 100 / k : 0;
          }
          n.data(data);
          n.addClass("pie");
        } else {
          n.data({ color: colors[0] ?? baseColor(idx, n.id()) });
          n.removeClass("pie");
        }
      });
    });
  }, [clusterColors, idx]);

  // visibility (+ the one initial layout, + placement of first-time-visible nodes)
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    if (!laidOut.current) {
      const seedIds = cbRef.current.layoutSeedIds ?? EMPTY_SET;
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          n.toggleClass("hidden", !seedIds.has(n.id()));
        });
      });
      const seed = cy.nodes().not(".hidden");
      const eles = seed.union(seed.edgesWith(seed));
      try {
        eles.layout({ ...LAYOUT_BASE, randomize: true, animate: false, fit: false } as unknown as cytoscape.LayoutOptions).run();
      } catch {
        // fall back to a grid if fcose fails on odd data
        eles.layout({ name: "grid", fit: false } as cytoscape.LayoutOptions).run();
      }
      seed.forEach((n) => {
        positioned.current.add(n.id());
      });
      laidOut.current = true;
    }
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        n.toggleClass("hidden", hiddenNodeIds.has(n.id()));
      });
    });
    const fresh = cy.nodes().not(".hidden").filter((n) => !positioned.current.has(n.id()));
    if (fresh.nonempty()) placeNear(cy, fresh, positioned.current);
    fresh.forEach((n) => {
      positioned.current.add(n.id());
    });
    if (fresh.length > 12) relax(cy, fresh);
    emphasize();
  }, [hiddenNodeIds]);

  // scope changes: fit everything visible, centred on the focus node if there is one
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !laidOut.current) return;
    // fit the whole visible neighbourhood (the focus node is selected and highlighted)
    const nodes = cy.nodes().not(".hidden");
    if (nodes.empty()) return;
    try {
      cy.fit(nodes, 56);
    } catch {
      return;
    }
    if (cy.zoom() > 1.3) cy.zoom({ level: 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }, [fitKey]);

  // selection
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements(":selected").unselect();
      if (selectedNodeId) cy.getElementById(selectedNodeId).select();
      else if (selectedEdgeId) cy.getElementById(selectedEdgeId).select();
    });
    emphasize();
  }, [selectedNodeId, selectedEdgeId, emphasisIds, props.dimOnSelect]);

  // explicit centring requests ("show in map" buttons)
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !centerRequest || !laidOut.current) return;
    fitAround(cy, centerRequest.id);
  }, [centerRequest]);

  const zoomBy = (f: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.animate({
      zoom: { level: Math.min(3, Math.max(0.12, cy.zoom() * f)), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } },
      duration: 180,
    });
  };

  const tidy = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const visible = visibleEles(cy);
    visible
      .layout({ ...LAYOUT_BASE, randomize: false, animate: "end", animationDuration: 450, fit: true } as unknown as cytoscape.LayoutOptions)
      .run();
  };

  const btn = "h-8 w-8 border-t border-line text-base hover:bg-subtle first:border-t-0";
  return (
    <div className="relative h-full w-full">
      {/* cytoscape forces position:relative on its container, so size it explicitly */}
      <div
        ref={containerRef}
        className="h-full w-full"
        role="region"
        aria-label="Network map. Click a shape for a summary, or a line for its evidence. Keyboard users can use search and the side panels."
      />
      <div className="absolute bottom-4 right-4 flex flex-col overflow-hidden rounded-md border border-line bg-white text-ink-2 shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
        <button type="button" onClick={() => zoomBy(1.25)} className={btn} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoomBy(0.8)} className={btn} aria-label="Zoom out">
          −
        </button>
        <button
          type="button"
          onClick={() => {
            const cy = cyRef.current;
            const nodes = cy?.nodes().not(".hidden");
            if (cy && nodes && nodes.nonempty()) cy.animate({ fit: { eles: nodes, padding: 48 }, duration: 250 });
          }}
          className={`${btn} text-[10px] font-medium`}
          aria-label="Fit the visible map"
        >
          Fit
        </button>
        <button type="button" onClick={tidy} className={`${btn} text-[10px] font-medium`} aria-label="Re-arrange the visible map" title="Re-arrange">
          ↻
        </button>
      </div>
    </div>
  );
}

/** Visible nodes plus only the edges between them (edges to hidden nodes have no geometry). */
function visibleEles(cy: Core): Collection {
  const nodes = cy.nodes().not(".hidden");
  return nodes.union(nodes.edgesWith(nodes));
}

/** Put first-time-visible nodes next to what they connect to, without moving anything else. */
function placeNear(cy: Core, fresh: Collection, positioned: Set<string>) {
  const isPlaced = (m: NodeSingular) => positioned.has(m.id()) && !m.hasClass("hidden");
  const byAnchor = new Map<string, NodeSingular[]>();
  const loose: NodeSingular[] = [];
  fresh.nodes().forEach((n) => {
    const anchors = n.neighborhood("node").filter((m) => isPlaced(m as NodeSingular));
    if (anchors.empty()) loose.push(n);
    else if (anchors.length === 1) {
      const a = anchors[0].id();
      const list = byAnchor.get(a);
      if (list) list.push(n);
      else byAnchor.set(a, [n]);
    } else {
      let x = 0;
      let y = 0;
      anchors.forEach((m) => {
        x += m.position("x");
        y += m.position("y");
      });
      n.position({ x: x / anchors.length + (Math.random() - 0.5) * 30, y: y / anchors.length + (Math.random() - 0.5) * 30 });
    }
  });
  for (const [a, list] of byAnchor) {
    const ap = cy.getElementById(a).position();
    const r = 70 + list.length * 5;
    const start = Math.random() * Math.PI;
    list.forEach((n, i) => {
      const ang = start + (2 * Math.PI * i) / list.length;
      n.position({ x: ap.x + r * Math.cos(ang), y: ap.y + r * Math.sin(ang) });
    });
  }
  if (loose.length) {
    const bb = cy.nodes().filter((m) => isPlaced(m)).boundingBox();
    loose.forEach((n, i) => n.position({ x: bb.x2 + 80 + (i % 6) * 60, y: bb.y1 + Math.floor(i / 6) * 60 }));
  }
}

/** Large reveals: settle the new nodes with an incremental fcose while every older node stays pinned. */
function relax(cy: Core, fresh: Collection) {
  const visible = visibleEles(cy);
  const freshIds = new Set(fresh.map((n) => n.id()));
  const fixed = visible
    .nodes()
    .filter((n) => !freshIds.has(n.id()))
    .map((n) => ({ nodeId: n.id(), position: { ...(n as NodeSingular).position() } }));
  try {
    visible
      .layout({
        ...LAYOUT_BASE,
        randomize: false,
        animate: "end",
        animationDuration: 400,
        fit: false,
        fixedNodeConstraint: fixed,
      } as unknown as cytoscape.LayoutOptions)
      .run();
  } catch {
    // placement alone is acceptable
  }
}

function fitAround(cy: Core, id: string) {
  const n = cy.getElementById(id);
  if (n.empty() || n.hasClass("hidden")) return;
  const hood = n.closedNeighborhood().nodes().not(".hidden");
  if (hood.empty()) return;
  try {
    cy.animate({ fit: { eles: hood, padding: 90 }, duration: 350 });
  } catch {
    // never let a view adjustment break the page
  }
}
