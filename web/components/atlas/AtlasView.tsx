"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SearchBox } from "../search/SearchBox";
import { WithGraph } from "../GraphProvider";
import { useEvidence } from "../evidence/EvidenceProvider";
import { LeftRail, type SymptomMode } from "./LeftRail";
import { ClusterPanel, NodePanel, OverviewPanel } from "./AtlasPanels";
import { clustersOf, clusterSlot, neighbors, type GraphIndex } from "@/lib/graph";
import { clusterColor } from "@/lib/style";
import { MECHSIM_RELATIONS, type AtlasNode, type NodeType } from "@/lib/types";
import { FACTORS, type FactorKey } from "@/lib/factors";
import { usePersona } from "@/lib/persona";

const GraphCanvas = dynamic(() => import("./GraphCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-ink-3" role="status">
      Drawing the map…
    </div>
  ),
});

/** Shown by default. Variant groups appear for the selected gene; people and funding stay off. */
export const DEFAULT_TYPES: NodeType[] = ["disease", "gene", "mechanism", "patient_org", "asset", "study", "therapy"];
/** Link groups the user can hide (each maps to relation types in the graph). */
export const LINK_GROUPS: { id: string; label: string; types: string[] }[] = [
  { id: "causes", label: "Gene causes disease", types: ["causes", "variant_in", "part_of"] },
  { id: "mechanism", label: "Mechanism", types: ["driven_by", "has_effect", "participates_in"] },
  { id: "symptoms", label: "Symptoms", types: ["has_phenotype"] },
  { id: "treatments", label: "Treatments", types: ["developed_for", "targets"] },
  { id: "studies", label: "Studies", types: ["studies", "tests"] },
  { id: "orgs", label: "Organisations", types: ["serves", "covers", "maintains"] },
  { id: "people", label: "Researchers and funding", types: ["works_on", "funds", "about", "authored"] },
  { id: "simsym", label: "Similar symptoms", types: ["similar_phenotype"] },
  { id: "sharemech", label: "Shares mechanism", types: ["shares_mechanism"] },
  { id: "ideas", label: "Hypotheses", types: ["candidate_for"] },
  { id: "factor", label: "Factor-lens links", types: [...MECHSIM_RELATIONS] },
];
type Depth = 1 | 2 | 3 | "all";
/** "Distinctive shared" symptom: specific (information content >= 3.5) and seen in 2+ diseases. */
const DISTINCTIVE_IC = 3.5;

type Selection = { kind: "node" | "cluster"; id: string } | null;
type Scope = { mode: "focus"; id: string } | { mode: "all" };

export function AtlasView() {
  return <WithGraph>{(idx) => <Atlas idx={idx} />}</WithGraph>;
}

export function distinctiveSharedSymptoms(idx: GraphIndex): Set<string> {
  const out = new Set<string>();
  for (const n of idx.graph.nodes) {
    if (n.type !== "phenotype") continue;
    const ic = typeof n.attrs?.ic === "number" ? n.attrs.ic : 0;
    const diseases = neighbors(idx, n.id, { relations: ["has_phenotype"], direction: "in" }).length;
    if (ic >= DISTINCTIVE_IC && diseases >= 2) out.add(n.id);
  }
  return out;
}

function geneOfVariantGroup(idx: GraphIndex, vg: AtlasNode): string | undefined {
  if (vg.type === "variant_group" && vg.attrs?.gene && idx.nodeById.has(vg.attrs.gene)) return vg.attrs.gene;
  return neighbors(idx, vg.id, { relations: ["variant_in"], direction: "out" })[0]?.other;
}

function Atlas({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const focus = params.get("focus");
  const viewAll = params.get("view") === "all";
  const { openEdge, edgeId } = useEvidence();

  const validFocus = focus && idx.nodeById.has(focus) ? focus : null;
  const [visibleTypes, setVisibleTypes] = useState<Set<NodeType>>(() => {
    const t = params.get("types");
    return new Set(t ? (t.split(",") as NodeType[]) : DEFAULT_TYPES);
  });
  // hop depth from the focused item (default 1), hidden link groups and individually hidden nodes, all in the URL
  const [depth, setDepth] = useState<Depth>(() => {
    const d = params.get("depth");
    return d === "all" ? "all" : d === "2" ? 2 : d === "3" ? 3 : 1;
  });
  const [hiddenGroups, setHiddenGroups] = useState<Set<string>>(() => new Set((params.get("hide") ?? "").split(",").filter((g) => LINK_GROUPS.some((x) => x.id === g))));
  const [hiddenNodes, setHiddenNodes] = useState<Set<string>>(() => new Set((params.get("hn") ?? "").split(",").filter((id) => idx.nodeById.has(id))));
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [sheet, setSheet] = useState<"filters" | "details" | null>(null);
  const [symptoms, setSymptoms] = useState<SymptomMode>("distinctive");
  const [hiddenClusters, setHiddenClusters] = useState<Set<string>>(new Set());
  const [selection, setSelection] = useState<Selection>(() => (validFocus ? { kind: "node", id: validFocus } : null));
  const [scope, setScope] = useState<Scope>(() => (validFocus && !viewAll ? { mode: "focus", id: validFocus } : { mode: "all" }));
  const [centerRequest, setCenterRequest] = useState<{ id: string; n: number } | null>(() => (validFocus ? { id: validFocus, n: 1 } : null));
  const [fitKey, setFitKey] = useState(1);
  // factor lens (null = curated map only); ?links=mechanistic opens it on "all", ?lens=<factor> on one factor
  const [lens, setLens] = useState<FactorKey | "all" | null>(() => {
    const l = params.get("lens");
    if (l && FACTORS.some((f) => f.key === l)) return l as FactorKey;
    return params.get("links") === "mechanistic" || l === "all" ? "all" : null;
  });
  const showMechsim = lens !== null;
  const persona = usePersona();

  const distinctive = useMemo(() => distinctiveSharedSymptoms(idx), [idx]);

  // ?focus= changes from outside (header search, links) re-focus the map. Internal selections also
  // rewrite the URL, but they already match `selection`, so they don't move anything.
  const [handledFocus, setHandledFocus] = useState(focus);
  if (focus !== handledFocus) {
    setHandledFocus(focus);
    const n = focus ? idx.nodeById.get(focus) : undefined;
    if (n && !(selection?.kind === "node" && selection.id === n.id)) {
      setSelection({ kind: "node", id: n.id });
      setScope({ mode: "focus", id: n.id });
      setCenterRequest((r) => ({ id: n.id, n: (r?.n ?? 0) + 1 }));
      setFitKey((k) => k + 1);
    }
  }

  // the URL carries the selection plus the view choices, so a link reproduces what the user sees
  const urlState = useRef<{ id: string | null; all: boolean }>({ id: validFocus, all: viewAll });
  const writeUrl = useCallback(() => {
    const { id, all } = urlState.current;
    const q = new URLSearchParams();
    if (id) q.set("focus", id);
    if (all && id) q.set("view", "all");
    if (depth !== 1) q.set("depth", String(depth));
    if (hiddenGroups.size) q.set("hide", [...hiddenGroups].join(","));
    if (hiddenNodes.size) q.set("hn", [...hiddenNodes].join(","));
    if (lens) q.set("lens", lens);
    const def = new Set(DEFAULT_TYPES);
    if (visibleTypes.size !== def.size || [...visibleTypes].some((t) => !def.has(t))) q.set("types", [...visibleTypes].join(","));
    const s = q.toString();
    window.history.replaceState(null, "", s ? `/atlas?${s}` : "/atlas");
  }, [depth, hiddenGroups, hiddenNodes, lens, visibleTypes]);
  useEffect(() => writeUrl(), [writeUrl]);
  const syncUrl = useCallback(
    (id: string | null, all: boolean) => {
      urlState.current = { id, all };
      writeUrl();
    },
    [writeUrl],
  );
  const hiddenEdgeTypes = useMemo(() => new Set(LINK_GROUPS.filter((g) => hiddenGroups.has(g.id)).flatMap((g) => g.types)), [hiddenGroups]);

  const selectedNode = selection?.kind === "node" ? idx.nodeById.get(selection.id) : undefined;
  const selectedCluster = selection?.kind === "cluster" ? idx.clusterById.get(selection.id) : undefined;

  // genes whose variant groups should appear (selected or focused gene, or the gene of a selected variant group)
  const contextGenes = useMemo(() => {
    const s = new Set<string>();
    for (const id of [selectedNode?.id, scope.mode === "focus" ? scope.id : undefined]) {
      const n = id ? idx.nodeById.get(id) : undefined;
      if (!n) continue;
      if (n.type === "gene") s.add(n.id);
      if (n.type === "variant_group") {
        const g = geneOfVariantGroup(idx, n);
        if (g) s.add(g);
      }
    }
    return s;
  }, [idx, selectedNode, scope]);

  const passes = useCallback(
    (n: AtlasNode, ignoreClusters = false) => {
      if (n.type === "phenotype") {
        if (symptoms === "none") return false;
        if (symptoms === "distinctive" && !distinctive.has(n.id)) return false;
      } else if (n.type === "variant_group") {
        if (!visibleTypes.has("variant_group")) {
          const g = geneOfVariantGroup(idx, n);
          if (!g || !contextGenes.has(g)) return false;
        }
      } else if (!visibleTypes.has(n.type)) return false;
      if (hiddenNodes.has(n.id)) return false;
      if (!ignoreClusters) {
        const cs = clustersOf(idx, n.id);
        if (cs.length && cs.every((c) => hiddenClusters.has(c.id))) return false;
      }
      return true;
    },
    [idx, symptoms, distinctive, visibleTypes, contextGenes, hiddenClusters, hiddenNodes],
  );

  const visibleIds = useMemo(() => {
    const forced = new Set([selectedNode?.id, scope.mode === "focus" ? scope.id : undefined].filter((x): x is string => !!x));
    let ids: Set<string>;
    if (scope.mode === "focus" && idx.nodeById.has(scope.id)) {
      ids = new Set([scope.id]);
      let frontier = [scope.id];
      const hops = depth === "all" ? 99 : depth;
      for (let h = 0; h < hops && frontier.length; h++) {
        const next: string[] = [];
        for (const id of frontier) {
          for (const nb of idx.adjacency.get(id) ?? []) {
            if (ids.has(nb.other)) continue;
            // computed factor links never widen the neighbourhood: the lens only draws links between shown nodes
            if (MECHSIM_RELATIONS.includes(nb.edge.type) || hiddenEdgeTypes.has(nb.edge.type)) continue;
            const o = idx.nodeById.get(nb.other);
            if (!o || !(passes(o) || forced.has(o.id))) continue;
            ids.add(o.id);
            next.push(o.id);
          }
        }
        frontier = next;
      }
    } else {
      ids = new Set(idx.graph.nodes.filter((n) => passes(n)).map((n) => n.id));
    }
    for (const id of forced) if (!hiddenNodes.has(id) || id === (scope.mode === "focus" ? scope.id : "")) ids.add(id);
    return ids;
  }, [idx, scope, passes, selectedNode, depth, hiddenEdgeTypes, hiddenNodes]);

  const hiddenNodeIds = useMemo(() => new Set(idx.graph.nodes.filter((n) => !visibleIds.has(n.id)).map((n) => n.id)), [idx, visibleIds]);

  // the first layout always covers the whole-atlas default view, so focus <-> whole never reshuffles
  const [layoutSeedIds] = useState(
    () =>
      new Set(
        idx.graph.nodes
          .filter((n) => (n.type === "phenotype" ? distinctive.has(n.id) : DEFAULT_TYPES.includes(n.type)))
          .map((n) => n.id),
      ),
  );

  const clusterColors = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const n of idx.graph.nodes) {
      const cs = clustersOf(idx, n.id).filter((c) => !hiddenClusters.has(c.id));
      if (cs.length) m.set(n.id, cs.map((c) => clusterColor(clusterSlot(idx, c.id))));
    }
    return m;
  }, [idx, hiddenClusters]);

  const emphasisIds = useMemo(() => {
    if (selection?.kind !== "cluster") return null;
    return new Set(idx.clusterById.get(selection.id)?.members ?? []);
  }, [idx, selection]);

  const selectNode = useCallback(
    (id: string | null, center = false) => {
      if (!id) {
        setSelection(null);
        syncUrl(scope.mode === "focus" ? scope.id : null, scope.mode === "all");
        return;
      }
      if (!idx.nodeById.has(id)) return;
      setSelection({ kind: "node", id });
      syncUrl(id, scope.mode === "all");
      if (center) setCenterRequest((r) => ({ id, n: (r?.n ?? 0) + 1 }));
    },
    [idx, scope, syncUrl],
  );

  const focusOn = (id: string) => {
    setScope({ mode: "focus", id });
    setSelection({ kind: "node", id });
    syncUrl(id, false);
    setCenterRequest((r) => ({ id, n: (r?.n ?? 0) + 1 }));
    setFitKey((k) => k + 1);
  };

  const showWhole = () => {
    setScope({ mode: "all" });
    syncUrl(selectedNode?.id ?? null, true);
    setFitKey((k) => k + 1);
  };

  const selectCluster = useCallback((id: string | null) => {
    setSelection(id ? { kind: "cluster", id } : null);
    if (id)
      setHiddenClusters((s) => {
        if (!s.has(id)) return s;
        const next = new Set(s);
        next.delete(id);
        return next;
      });
  }, []);

  const focusNode = scope.mode === "focus" ? idx.nodeById.get(scope.id) : undefined;
  const hiddenCount = hiddenNodes.size + hiddenGroups.size;
  const showAllHidden = () => {
    setHiddenNodes(new Set());
    setHiddenGroups(new Set());
  };
  const hideNode = (id: string) => {
    setHiddenNodes((s) => new Set([...s, id]));
    if (selection?.kind === "node" && selection.id === id) setSelection(null);
    setMenu(null);
  };
  const onlyNeighbours = (id: string) => {
    setDepth(1);
    focusOn(id);
    setMenu(null);
  };

  const rail = (
    <LeftRail
      idx={idx}
      hiddenClusters={hiddenClusters}
      onToggleCluster={(id) =>
        setHiddenClusters((s) => {
          const next = new Set(s);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        })
      }
      onSetAllClusters={(visible) => setHiddenClusters(visible ? new Set() : new Set(idx.graph.clusters.map((c) => c.id)))}
      visibleTypes={visibleTypes}
      onToggleType={(t) =>
        setVisibleTypes((s) => {
          const next = new Set(s);
          if (next.has(t)) next.delete(t);
          else next.add(t);
          return next;
        })
      }
      symptoms={symptoms}
      onSymptoms={setSymptoms}
      distinctiveCount={distinctive.size}
      selectedClusterId={selectedCluster?.id ?? null}
      onSelectCluster={selectCluster}
      lens={lens}
      onLens={setLens}
      weightsFor={persona === "researcher" ? (selectedNode?.type === "disease" ? selectedNode.id : null) : undefined}
      linkGroups={LINK_GROUPS}
      hiddenGroups={hiddenGroups}
      onToggleGroup={(g) =>
        setHiddenGroups((s) => {
          const next = new Set(s);
          if (next.has(g)) next.delete(g);
          else next.add(g);
          return next;
        })
      }
    />
  );
  const details = selectedNode ? (
    <NodePanel
      key={selectedNode.id}
      idx={idx}
      node={selectedNode}
      onSelectNode={(id) => selectNode(id, true)}
      onSelectCluster={(id) => selectCluster(id)}
      onFocus={scope.mode === "focus" && scope.id === selectedNode.id ? undefined : () => focusOn(selectedNode.id)}
    />
  ) : selectedCluster ? (
    <ClusterPanel key={selectedCluster.id} idx={idx} cluster={selectedCluster} onSelectNode={(id) => selectNode(id, true)} />
  ) : (
    <OverviewPanel idx={idx} onSelectNode={(id) => focusOn(id)} />
  );

  return (
    <div className="relative h-[calc(100dvh-57px)] md:grid md:grid-cols-[256px_minmax(0,1fr)_372px] xl:grid-cols-[272px_minmax(0,1fr)_400px]">
      {/* desktop: three columns; phone: map first, filters and details as bottom sheets */}
      <div className="hidden min-h-0 md:block">{rail}</div>
      <div className="relative h-full min-w-0 bg-white">
        <h1 className="sr-only">Atlas map</h1>
        <GraphCanvas
          idx={idx}
          hiddenNodeIds={hiddenNodeIds}
          layoutSeedIds={layoutSeedIds}
          clusterColors={clusterColors}
          selectedNodeId={selectedNode?.id ?? null}
          selectedEdgeId={edgeId}
          emphasisIds={emphasisIds}
          centerRequest={centerRequest}
          fitKey={fitKey}
          dimOnSelect={!(scope.mode === "focus" && selectedNode?.id === scope.id)}
          showMechsim={showMechsim}
          lens={lens}
          hiddenEdgeTypes={hiddenEdgeTypes}
          onSelectNode={(id) => {
            selectNode(id);
            setMenu(null);
            if (id) setSheet((s) => (s === "filters" ? s : "details"));
          }}
          onSelectEdge={(id) => openEdge(id)}
          onNodeMenu={(id, x, y) => setMenu({ id, x, y })}
        />
        <div className="pointer-events-none absolute inset-x-2 top-2 flex flex-col gap-2 sm:inset-x-3 sm:top-3">
          <div className="pointer-events-auto flex flex-wrap items-center gap-2">
            <div className="w-full max-w-[340px] sm:w-[300px]">
              <SearchBox variant="field" shortcut={false} label="Find in the atlas" placeholder="Find a disease, gene, symptom…" onPick={(n) => focusOn(n.id)} />
            </div>
            <div className="flex items-center gap-1 rounded-md border border-line bg-white/95 px-1.5 py-1 text-xs text-ink-2 shadow-[0_1px_2px_rgba(16,24,40,0.05)]" role="group" aria-label="Connection depth">
              <span className="px-1">{focusNode ? "Steps from" : "Search to focus"}</span>
              {focusNode && <span className="max-w-[140px] truncate font-medium text-ink">{focusNode.label.split(" (")[0]}</span>}
              {([1, 2, 3, "all"] as Depth[]).map((d) => (
                <button
                  key={String(d)}
                  type="button"
                  disabled={!focusNode}
                  aria-pressed={focusNode ? depth === d : false}
                  onClick={() => setDepth(d)}
                  className={`h-7 min-w-[28px] rounded px-1.5 font-medium disabled:opacity-40 ${focusNode && depth === d ? "bg-accent-700 text-white" : "hover:bg-subtle"}`}
                >
                  {d === "all" ? "all" : d}
                </button>
              ))}
            </div>
          </div>
          <div className="pointer-events-auto flex flex-wrap items-center gap-2 text-xs">
            {focusNode ? (
              <span className="rounded-md border border-line bg-white/95 px-2 py-1 text-ink-2">
                {visibleIds.size} of {idx.graph.nodes.length} shown
                <button type="button" onClick={showWhole} className="ml-2 font-medium text-accent-700 hover:underline">
                  Show whole atlas
                </button>
              </span>
            ) : (
              <span className="rounded bg-white/90 px-1.5 py-0.5 text-ink-3">
                {visibleIds.size} of {idx.graph.nodes.length} shown · right-click or long-press a node for options
              </span>
            )}
            {hiddenCount > 0 && (
              <span className="rounded-md border border-warn-line bg-warn-bg px-2 py-1 text-warn-ink">
                Hidden: {hiddenCount}
                <button type="button" onClick={showAllHidden} className="ml-2 font-medium underline">
                  Show all
                </button>
              </span>
            )}
            {lens && (
              <span className="inline-flex items-center gap-1 rounded-md border border-accent-200 bg-accent-50 px-2 py-1 text-accent-900">
                Factor lens: {lens === "all" ? "all factors" : FACTORS.find((f) => f.key === lens)?.label}
                <button type="button" onClick={() => setLens(null)} aria-label="Turn the factor lens off" className="ml-1 rounded px-1 text-[15px] leading-none hover:bg-white">
                  ×
                </button>
              </span>
            )}
          </div>
        </div>
        {menu && (
          <div
            role="menu"
            aria-label="Node options"
            className="absolute z-30 w-56 rounded-lg border border-line bg-white py-1 text-sm shadow-[0_8px_24px_rgba(16,24,40,0.14)]"
            style={{ left: Math.max(8, Math.min(menu.x, 9999)), top: menu.y }}
          >
            <p className="truncate px-3 py-1.5 text-xs text-ink-3">{idx.nodeById.get(menu.id)?.label}</p>
            <button type="button" role="menuitem" onClick={() => onlyNeighbours(menu.id)} className="block w-full px-3 py-2 text-left hover:bg-subtle">
              Show only this and its neighbours
            </button>
            <button type="button" role="menuitem" onClick={() => hideNode(menu.id)} className="block w-full px-3 py-2 text-left hover:bg-subtle">
              Hide this node
            </button>
            <button type="button" role="menuitem" onClick={() => setMenu(null)} className="block w-full px-3 py-2 text-left text-ink-3 hover:bg-subtle">
              Cancel
            </button>
          </div>
        )}
        {/* phone controls */}
        <div className="absolute inset-x-2 bottom-3 flex justify-center gap-2 md:hidden">
          <button type="button" onClick={() => setSheet(sheet === "filters" ? null : "filters")} className="min-h-[44px] rounded-full border border-line bg-white px-4 text-sm font-medium text-ink shadow">
            Filters
          </button>
          <button type="button" onClick={() => setSheet(sheet === "details" ? null : "details")} className="min-h-[44px] rounded-full border border-line bg-white px-4 text-sm font-medium text-ink shadow">
            {selectedNode ? "Details" : "Overview"}
          </button>
        </div>
      </div>
      <aside aria-label="Selection details" className="panel-scroll hidden h-full overflow-y-auto border-l border-line md:block">
        {details}
      </aside>
      {sheet && (
        <div className="fixed inset-x-0 bottom-0 z-40 max-h-[70dvh] overflow-y-auto rounded-t-2xl border-t border-line bg-white shadow-[0_-8px_30px_rgba(16,24,40,0.15)] md:hidden" role="dialog" aria-label={sheet === "filters" ? "Map filters" : "Details"}>
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-white px-4 py-2">
            <span className="text-sm font-semibold text-ink">{sheet === "filters" ? "Filters" : selectedNode ? "Details" : "Overview"}</span>
            <button type="button" onClick={() => setSheet(null)} aria-label="Close" className="h-9 w-9 rounded-md text-lg text-ink-3 hover:bg-subtle">
              ×
            </button>
          </div>
          {sheet === "filters" ? rail : details}
        </div>
      )}
    </div>
  );
}
