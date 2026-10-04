"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { useEvidence } from "../evidence/EvidenceProvider";
import { LeftRail, type SymptomMode } from "./LeftRail";
import { ClusterPanel, NodePanel, OverviewPanel } from "./AtlasPanels";
import { clustersOf, clusterSlot, neighbors, type GraphIndex } from "@/lib/graph";
import { clusterColor } from "@/lib/style";
import { MECHSIM_RELATIONS, type AtlasNode, type NodeType } from "@/lib/types";

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
const FOCUS_HOPS = 2;
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
  const [visibleTypes, setVisibleTypes] = useState<Set<NodeType>>(() => new Set(DEFAULT_TYPES));
  const [symptoms, setSymptoms] = useState<SymptomMode>("distinctive");
  const [hiddenClusters, setHiddenClusters] = useState<Set<string>>(new Set());
  const [selection, setSelection] = useState<Selection>(() => (validFocus ? { kind: "node", id: validFocus } : null));
  const [scope, setScope] = useState<Scope>(() => (validFocus && !viewAll ? { mode: "focus", id: validFocus } : { mode: "all" }));
  const [centerRequest, setCenterRequest] = useState<{ id: string; n: number } | null>(() => (validFocus ? { id: validFocus, n: 1 } : null));
  const [fitKey, setFitKey] = useState(1);
  const [showMechsim, setShowMechsim] = useState(params.get("links") === "mechanistic");

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

  const syncUrl = (id: string | null, all: boolean) => {
    const q = new URLSearchParams();
    if (id) q.set("focus", id);
    if (all && id) q.set("view", "all");
    const s = q.toString();
    window.history.replaceState(null, "", s ? `/atlas?${s}` : "/atlas");
  };

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
      if (!ignoreClusters) {
        const cs = clustersOf(idx, n.id);
        if (cs.length && cs.every((c) => hiddenClusters.has(c.id))) return false;
      }
      return true;
    },
    [idx, symptoms, distinctive, visibleTypes, contextGenes, hiddenClusters],
  );

  const visibleIds = useMemo(() => {
    const forced = new Set([selectedNode?.id, scope.mode === "focus" ? scope.id : undefined].filter((x): x is string => !!x));
    let ids: Set<string>;
    if (scope.mode === "focus" && idx.nodeById.has(scope.id)) {
      ids = new Set([scope.id]);
      let frontier = [scope.id];
      for (let h = 0; h < FOCUS_HOPS; h++) {
        const next: string[] = [];
        for (const id of frontier) {
          for (const nb of idx.adjacency.get(id) ?? []) {
            if (ids.has(nb.other)) continue;
            if (!showMechsim && MECHSIM_RELATIONS.includes(nb.edge.type)) continue;
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
    for (const id of forced) ids.add(id);
    return ids;
  }, [idx, scope, passes, selectedNode, showMechsim]);

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
    [idx, scope],
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

  return (
    <div className="grid h-[calc(100vh-57px)] grid-cols-[256px_minmax(0,1fr)_372px] xl:grid-cols-[272px_minmax(0,1fr)_400px]">
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
        showMechsim={showMechsim}
        onShowMechsim={setShowMechsim}
      />
      <div className="relative min-w-0 bg-white">
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
          onSelectNode={(id) => selectNode(id)}
          onSelectEdge={(id) => openEdge(id)}
        />
        <div className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-center gap-2">
          {focusNode ? (
            <p className="pointer-events-auto flex items-center gap-2 rounded-md border border-line bg-white/95 px-2.5 py-1.5 text-xs text-ink-2 shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
              Showing what is within two steps of <span className="font-medium text-ink">{focusNode.label}</span>
              <span className="text-ink-3">· {visibleIds.size} of {idx.graph.nodes.length}</span>
              <button type="button" onClick={showWhole} className="ml-1 font-medium text-accent-700 hover:underline">
                Show whole atlas
              </button>
            </p>
          ) : (
            <p className="rounded bg-white/90 px-1.5 py-0.5 text-xs text-ink-3">
              {visibleIds.size} of {idx.graph.nodes.length} shown · hover to highlight neighbours · click a line for its evidence
            </p>
          )}
        </div>
      </div>
      <aside aria-label="Selection details" className="panel-scroll h-full overflow-y-auto border-l border-line">
        {selectedNode ? (
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
        )}
      </aside>
    </div>
  );
}
