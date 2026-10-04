"use client";

import { FACTORS, type FactorKey } from "@/lib/factors";
import { FACTOR_COLOR } from "../factors/FactorBits";
import { WeightsPanel } from "../factors/WeightsPanel";
import { clusterSlot, type GraphIndex } from "@/lib/graph";
import { bridgesOf } from "@/lib/bridges";
import { clusterColor, NO_CLUSTER_COLOR } from "@/lib/style";
import { TYPE_LABEL, plural } from "@/lib/text";
import Link from "next/link";
import { MECHSIM_RELATIONS, NODE_TYPES, type NodeType } from "@/lib/types";
import { NodeTypeIcon } from "../NodeTypeIcon";

export type SymptomMode = "none" | "distinctive" | "all";

export function LeftRail({
  idx,
  hiddenClusters,
  onToggleCluster,
  onSetAllClusters,
  visibleTypes,
  onToggleType,
  symptoms,
  onSymptoms,
  distinctiveCount,
  selectedClusterId,
  onSelectCluster,
  showMechsim = false,
  onShowMechsim,
  lens = null,
  onLens,
  weightsFor,
  linkGroups = [],
  hiddenGroups,
  onToggleGroup,
}: {
  idx: GraphIndex;
  hiddenClusters: Set<string>;
  onToggleCluster: (id: string) => void;
  onSetAllClusters: (visible: boolean) => void;
  visibleTypes: Set<NodeType>;
  onToggleType: (t: NodeType) => void;
  symptoms: SymptomMode;
  onSymptoms: (m: SymptomMode) => void;
  distinctiveCount: number;
  selectedClusterId: string | null;
  onSelectCluster: (id: string | null) => void;
  showMechsim?: boolean;
  onShowMechsim?: (on: boolean) => void;
  /** factor lens: null = off, "all" = every computed factor link, else one factor */
  lens?: FactorKey | "all" | null;
  onLens?: (l: FactorKey | "all" | null) => void;
  /** Research view: show the weights panel for this disease (undefined = hidden) */
  weightsFor?: string | null;
  /** link groups the user can hide */
  linkGroups?: { id: string; label: string; types: string[] }[];
  hiddenGroups?: Set<string>;
  onToggleGroup?: (id: string) => void;
}) {
  const mechsimCount = idx.graph.edges.filter((e) => MECHSIM_RELATIONS.includes(e.type)).length;
  const lensCounts: Record<string, number> = Object.fromEntries(FACTORS.map((f) => [f.key, idx.graph.edges.filter((e) => e.type === f.edge).length]));
  void mechsimCount;
  void showMechsim;
  void onShowMechsim;
  const typeCounts = new Map<NodeType, number>();
  for (const n of idx.graph.nodes) typeCounts.set(n.type, (typeCounts.get(n.type) ?? 0) + 1);
  const clusters = idx.graph.clusters;
  const anyHidden = hiddenClusters.size > 0;

  return (
    <aside aria-label="Map filters" className="panel-scroll h-full overflow-y-auto border-r border-line px-5 py-5">
      {onLens && (
        <section aria-labelledby="lens-h" className="mb-7">
          <h2 id="lens-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
            Factor lens
          </h2>
          <p className="mt-1.5 text-xs leading-relaxed text-ink-3">Which diseases share a pathway, a tissue, a structure…? Pick a factor to draw only its links.</p>
          <div className="mt-2 space-y-1" role="radiogroup" aria-label="Factor lens">
            {([["none", "Off (curated map)"], ["all", "All factors"], ...FACTORS.map((f) => [f.key, f.label])] as [string, string][]).map(([k, l]) => {
              const on = (lens ?? "none") === k;
              return (
                <label key={k} className={`flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm ${on ? "bg-accent-50 text-ink" : "text-ink-2 hover:bg-subtle"}`}>
                  <input type="radio" name="lens" checked={on} onChange={() => onLens(k === "none" ? null : (k as FactorKey | "all"))} className="accent-[#1f5a96]" />
                  {k !== "none" && k !== "all" && <span className="h-2.5 w-2.5 rounded-sm" style={{ background: FACTOR_COLOR[k as FactorKey] }} aria-hidden="true" />}
                  <span>{l}</span>
                  {k !== "none" && k !== "all" && <span className="ml-auto text-[11px] tabular-nums text-ink-3">{lensCounts[k] ?? 0}</span>}
                </label>
              );
            })}
          </div>
          {lens && (
            <p className="mt-2 text-xs leading-relaxed text-ink-3">
              {lens === "all" ? "Each colour is one factor." : "Line width = how alike the two diseases are on this factor."} Computed from public data
              (above each factor’s 95th–98th percentile), not curated; symptoms are the curated-symptom similarity links.{" "}
              <Link href="/mechanisms" className="text-accent-700 hover:underline">
                Compare all factors
              </Link>
            </p>
          )}
        </section>
      )}
      <section aria-labelledby="clusters-h">
        <div className="flex items-baseline justify-between">
          <h2 id="clusters-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
            Mechanism clusters
          </h2>
          {clusters.length > 1 && (
            <button type="button" onClick={() => onSetAllClusters(anyHidden)} className="text-xs text-accent-700 hover:underline">
              {anyHidden ? "Show all" : "Hide all"}
            </button>
          )}
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-3">Groups that share biology. Colour shows the cluster.</p>
        <ul className="mt-3 space-y-0.5">
          {clusters.map((c) => {
            const color = clusterColor(clusterSlot(idx, c.id));
            const on = !hiddenClusters.has(c.id);
            const diseases = c.members.filter((m) => idx.nodeById.get(m)?.type === "disease").length;
            const selected = selectedClusterId === c.id;
            return (
              <li key={c.id} className={`flex items-start gap-2.5 rounded-md px-1.5 py-1.5 ${selected ? "bg-subtle" : ""}`}>
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onToggleCluster(c.id)}
                  aria-label={`Show ${c.label}`}
                  className="mt-[3px] h-3.5 w-3.5 shrink-0 cursor-pointer appearance-none rounded-[3px] border-[1.5px] focus-visible:outline-2"
                  style={{ borderColor: color, background: on ? color : "#fff" }}
                />
                <button
                  type="button"
                  onClick={() => onSelectCluster(selected ? null : c.id)}
                  aria-pressed={selected}
                  className={`min-w-0 flex-1 text-left text-sm leading-snug ${on ? "text-ink" : "text-ink-3"} hover:text-accent-700`}
                >
                  <span className="block">{c.label}</span>
                  <span className="block text-xs text-ink-3">
                    {diseases ? plural(diseases, "disease") : plural(c.members.length, "member")} · by {c.basis}
                  </span>
                </button>
              </li>
            );
          })}
          <li className="flex items-center gap-2.5 px-1.5 pt-2.5">
            <PieGlyph colors={clusters.slice(0, 3).map((c) => clusterColor(clusterSlot(idx, c.id)))} />
            <span className="text-xs leading-snug text-ink-3">A disease in several clusters shows one slice per cluster</span>
          </li>
          <li className="flex items-center gap-2.5 px-1.5 py-1.5">
            <span className="h-3.5 w-3.5 shrink-0 rounded-[3px]" style={{ background: NO_CLUSTER_COLOR }} aria-hidden="true" />
            <span className="text-xs text-ink-3">Gray: not in a cluster</span>
          </li>
        </ul>
        {!clusters.length && <p className="mt-2 text-xs text-ink-3">No clusters in this data yet.</p>}
      </section>

      <section aria-labelledby="types-h" className="mt-7">
        <h2 id="types-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
          Show
        </h2>
        <ul className="mt-2.5 space-y-0.5">
          {NODE_TYPES.filter((t) => typeCounts.get(t)).map((t) => {
            if (t === "phenotype") {
              return (
                <li key={t}>
                  <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1.5 py-1 hover:bg-subtle" title="Distinctive symptoms shared by 2 or more diseases">
                    <input
                      type="checkbox"
                      checked={symptoms !== "none"}
                      onChange={() => onSymptoms(symptoms === "none" ? "distinctive" : "none")}
                      className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1f5a96]"
                    />
                    <NodeTypeIcon type={t} size={13} />
                    <span className={`flex-1 text-sm ${symptoms !== "none" ? "text-ink" : "text-ink-3"}`}>Shared symptoms</span>
                    <span className="text-xs tabular-nums text-ink-3">{symptoms === "all" ? typeCounts.get(t) : distinctiveCount}</span>
                  </label>
                  <label className="ml-6 flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-0.5 text-xs text-ink-3 hover:bg-subtle">
                    <input
                      type="checkbox"
                      checked={symptoms === "all"}
                      onChange={() => onSymptoms(symptoms === "all" ? "distinctive" : "all")}
                      className="h-3 w-3 shrink-0 cursor-pointer accent-[#1f5a96]"
                    />
                    Show all symptoms ({typeCounts.get(t)})
                  </label>
                </li>
              );
            }
            const on = visibleTypes.has(t);
            return (
              <li key={t}>
                <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1.5 py-1 hover:bg-subtle" title={TYPE_LABEL[t].hint}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => onToggleType(t)}
                    className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1f5a96]"
                  />
                  <NodeTypeIcon type={t} size={13} />
                  <span className={`flex-1 text-sm ${on ? "text-ink" : "text-ink-3"}`}>
                    {TYPE_LABEL[t].many}
                    {t === "variant_group" && !on && <span className="block text-[11px] leading-tight text-ink-3">shown for the selected gene</span>}
                  </span>
                  <span className="text-xs tabular-nums text-ink-3">{typeCounts.get(t)}</span>
                </label>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs leading-relaxed text-ink-3">
          Shared symptoms are the distinctive ones (specific, and seen in 2 or more diseases). Researchers, grants and publications
          start hidden.
        </p>
      </section>

      {onToggleGroup && linkGroups.length > 0 && (
        <section aria-labelledby="links-h" className="mt-7">
          <h2 id="links-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
            Links to show
          </h2>
          <ul className="mt-2 space-y-0.5">
            {linkGroups.map((g) => {
              const n = idx.graph.edges.filter((e) => g.types.includes(e.type)).length;
              if (!n) return null;
              return (
                <li key={g.id}>
                  <label className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm text-ink-2 hover:bg-subtle">
                    <input type="checkbox" checked={!hiddenGroups?.has(g.id)} onChange={() => onToggleGroup(g.id)} className="accent-[#1f5a96]" />
                    <span className="flex-1">{g.label}</span>
                    <span className="text-[11px] tabular-nums text-ink-3">{n}</span>
                  </label>
                </li>
              );
            })}
          </ul>
          <p className="mt-1 text-xs text-ink-3">Hidden links also stop the neighbourhood from growing through them. Right-click or long-press a node to hide it.</p>
        </section>
      )}
      {weightsFor !== undefined && <WeightsPanel idx={idx} diseaseId={weightsFor} />}

      <section aria-labelledby="lines-h" className="mt-7">
        <h2 id="lines-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
          Lines
        </h2>
        <MapLegend bridgeCount={bridgesOf(idx).size} />
      </section>
    </aside>
  );
}

function PieGlyph({ colors }: { colors: string[] }) {
  const k = Math.max(colors.length, 1);
  const r = 7;
  const paths = colors.map((c, i) => {
    const a0 = (2 * Math.PI * i) / k - Math.PI / 2;
    const a1 = (2 * Math.PI * (i + 1)) / k - Math.PI / 2;
    const p = (a: number) => `${8 + r * Math.cos(a)} ${8 + r * Math.sin(a)}`;
    return <path key={i} d={`M8 8 L${p(a0)} A${r} ${r} 0 0 1 ${p(a1)} Z`} fill={c} />;
  });
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      {paths}
    </svg>
  );
}

export function MapLegend({ bridgeCount }: { bridgeCount?: number }) {
  return (
    <ul className="mt-2.5 space-y-2 text-xs text-ink-2">
      <li className="flex items-center gap-3">
        <LineSample dash="" />
        Backed by evidence
      </li>
      <li className="flex items-center gap-3">
        <LineSample dash="5 3" />
        Inferred by the atlas
      </li>
      <li className="flex items-center gap-3">
        <LineSample dash="1 3" faint />
        Hypothesis, untested
      </li>
      <li className="flex items-center gap-3">
        <svg width="32" height="14" aria-hidden="true">
          <line x1="0" y1="7" x2="32" y2="7" stroke="#a3a9b3" strokeWidth="1.5" />
          <circle cx="16" cy="7" r="5.5" fill="#fdf0d5" stroke="#e6c27c" />
          <text x="16" y="10" textAnchor="middle" fontSize="8" fontWeight="700" fill="#7f520f">
            !
          </text>
        </svg>
        Contested: sources disagree
      </li>
      <li className="flex items-center gap-3">
        <BridgeSample />
        <span>
          Bridge across clusters
          {bridgeCount !== undefined && <span className="text-ink-3"> · {bridgeCount} in the atlas</span>}
        </span>
      </li>
      <li className="flex items-center gap-3">
        <svg width="32" height="14" aria-hidden="true">
          <line x1="0" y1="4" x2="32" y2="4" stroke="#a3a9b3" strokeWidth="0.8" />
          <line x1="0" y1="10" x2="32" y2="10" stroke="#a3a9b3" strokeWidth="2.4" />
        </svg>
        Thicker = more confident
      </li>
      <li className="flex items-center gap-3">
        <svg width="32" height="14" aria-hidden="true">
          <circle cx="3" cy="7" r="2" fill="#8b9099" />
          <circle cx="11.5" cy="7" r="3.5" fill="#8b9099" />
          <circle cx="24.5" cy="7" r="6.5" fill="#8b9099" />
        </svg>
        Size = how central it is in the atlas
      </li>
    </ul>
  );
}

/** Same encoding as the map: accent line on a pale accent band. */
export function BridgeSample({ width = 32 }: { width?: number }) {
  return (
    <svg width={width} height="14" aria-hidden="true" className="shrink-0">
      <line x1="3.5" y1="7" x2={width - 3.5} y2="7" stroke="#c7d8ea" strokeWidth="7" strokeLinecap="round" />
      <line x1="3.5" y1="7" x2={width - 3.5} y2="7" stroke="#3e6ea5" strokeWidth="1.8" />
    </svg>
  );
}

function LineSample({ dash, faint }: { dash: string; faint?: boolean }) {
  return (
    <svg width="32" height="14" aria-hidden="true">
      <line
        x1="0"
        y1="7"
        x2="32"
        y2="7"
        stroke={faint ? "#b8bdc5" : "#7d838c"}
        strokeWidth="1.6"
        strokeDasharray={dash || undefined}
        strokeLinecap={faint ? "round" : undefined}
      />
    </svg>
  );
}
