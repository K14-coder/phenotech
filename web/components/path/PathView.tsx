"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { AiAction } from "../ai/AiAction";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { SearchBox } from "../search/SearchBox";
import { ConfidenceMeter, EvidenceLevelBadge, StatusBadge } from "../evidence/EvidenceBits";
import { useEvidence } from "../evidence/EvidenceProvider";
import { gapsAbout, nodeHref, pathHref, shortestEvidencePath, type GraphIndex } from "@/lib/graph";
import { familyName } from "@/lib/bridges";
import { GLOBAL_INDEX_KEY, globalHref, isGlobalId, loadGlobalIndex, type GlobalIndex, type GlobalRow } from "@/lib/global";
import { closestDiseases } from "@/lib/insights";
import { useResource } from "@/lib/resource";
import { EVIDENCE_LEVEL_META, TYPE_LABEL, capFirst, confidenceWord, joinList, relationSentence } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";

export function PathView() {
  return <WithGraph>{(idx) => <PathInner idx={idx} />}</WithGraph>;
}

function PathInner({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const router = useRouter();
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const [includeHyp, setIncludeHyp] = useState(params.get("hyp") === "1");
  // either end may be a disease outside the mapped families (MONDO/OMIM/ORPHA id from the global index)
  const anyGlobal = isGlobalId(from) || isGlobalId(to);
  const gres = useResource<GlobalIndex>(anyGlobal ? GLOBAL_INDEX_KEY : null, loadGlobalIndex);
  const gi = gres?.data;
  const resolve = (id: string) => {
    const row = isGlobalId(id) ? gi?.byId.get(id) : undefined;
    // a mapped disease reached by its global id is the atlas disease itself
    const node = idx.nodeById.get(id) ?? (row?.atlas ? idx.nodeById.get(row.atlas) : undefined);
    return { node, global: node ? undefined : isGlobalId(id) ? { id, row } : undefined };
  };
  const { node: fromNode, global: fromGlobal } = resolve(from);
  const { node: toNode, global: toGlobal } = resolve(to);

  const result = useMemo(
    () => (fromNode && toNode ? shortestEvidencePath(idx, fromNode.id, toNode.id, { includeHypotheses: includeHyp }) : null),
    [idx, fromNode, toNode, includeHyp],
  );
  const withHyp = useMemo(
    () =>
      fromNode && toNode && !result && !includeHyp
        ? shortestEvidencePath(idx, fromNode.id, toNode.id, { includeHypotheses: true })
        : null,
    [idx, fromNode, toNode, result, includeHyp],
  );

  const set = (f?: string, t?: string) => router.replace(pathHref(f || undefined, t || undefined), { scroll: false });

  const examples = useMemo(() => {
    const diseases = idx.graph.nodes
      .filter((n) => n.type === "disease")
      .sort((a, b) => (idx.degree.get(b.id) ?? 0) - (idx.degree.get(a.id) ?? 0));
    const out: [AtlasNode, AtlasNode][] = [];
    const d0 = diseases[0];
    if (d0) {
      for (const m of closestDiseases(idx, d0.id, 2)) out.push([d0, m.disease]);
      const therapy = idx.graph.nodes.find((n) => n.type === "therapy");
      const far = diseases.find((d) => d.id !== d0.id && !out.some(([, b]) => b.id === d.id));
      if (therapy && far) out.push([far, therapy]);
    }
    return out.slice(0, 3);
  }, [idx]);

  return (
    <div className="mx-auto w-full max-w-[880px] px-8 pb-24 pt-10">
      <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">How are these connected?</h1>
      <p className="mt-2 max-w-[640px] text-[15px] leading-relaxed text-ink-3">
        The atlas finds the best-supported route between two things. It prefers strong, well-sourced links and avoids weak,
        inferred or contested ones when it can.
      </p>

      <div className="mt-8 grid grid-cols-1 items-end gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <Picker label="From" node={fromNode} global={fromGlobal} onPick={(n) => set(n.id, to)} onPickGlobal={(r) => set(r.id, to)} onClear={() => set("", to)} />
        <button
          type="button"
          onClick={() => set(to, from)}
          disabled={!from && !to}
          className="mb-0.5 h-9 rounded-md border border-line px-3 text-sm text-ink-2 hover:border-accent-500 disabled:opacity-40"
          aria-label="Swap from and to"
        >
          ⇄
        </button>
        <Picker label="To" node={toNode} global={toGlobal} onPick={(n) => set(from, n.id)} onPickGlobal={(r) => set(from, r.id)} onClear={() => set(from, "")} />
      </div>
      <label className="mt-4 inline-flex cursor-pointer items-center gap-2 text-sm text-ink-2">
        <input type="checkbox" checked={includeHyp} onChange={(e) => setIncludeHyp(e.target.checked)} className="h-3.5 w-3.5 accent-[#1f5a96]" />
        Allow untested hypotheses in the route
      </label>

      {fromGlobal || toGlobal ? (
        <OutsideMapped idx={idx} ends={[fromGlobal, toGlobal].filter((g): g is GlobalEnd => !!g)} loading={gres?.status === "loading"} />
      ) : !fromNode || !toNode ? (
        <div className="mt-12">
          <p className="text-sm font-medium text-ink-2">{fromNode || toNode ? "Pick the other end to trace a route." : "Try one of these"}</p>
          {!fromNode && !toNode && (
            <ul className="mt-3 space-y-2">
              {examples.map(([a, b]) => (
                <li key={`${a.id}-${b.id}`}>
                  <Link
                    href={pathHref(a.id, b.id)}
                    className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
                  >
                    {a.label} <span className="text-ink-3">→</span> {b.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : result ? (
        <PathResultView idx={idx} result={result} includeHypotheses={includeHyp} />
      ) : (
        <NoRoute idx={idx} from={fromNode} to={toNode} hypothesisRoute={!!withHyp} onAllowHyp={() => setIncludeHyp(true)} />
      )}
    </div>
  );
}

type GlobalEnd = { id: string; row: GlobalRow | undefined };

function Picker({
  label,
  node,
  global,
  onPick,
  onPickGlobal,
  onClear,
}: {
  label: string;
  node?: AtlasNode;
  global?: GlobalEnd;
  onPick: (n: AtlasNode) => void;
  onPickGlobal: (r: GlobalRow) => void;
  onClear: () => void;
}) {
  return (
    <div className="min-w-0">
      <p className="mb-1.5 text-xs font-medium text-ink-3">{label}</p>
      {global ? (
        <div className="flex h-9 items-center justify-between gap-2 rounded-lg border border-line px-3">
          <span className="flex min-w-0 items-center gap-2 text-sm text-ink">
            <span className="h-[11px] w-[11px] shrink-0 rounded-full border-[1.5px] border-ink-4" aria-hidden="true" />
            <span className="truncate font-medium">{global.row ? capFirst(global.row.name) : global.id}</span>
            <span className="shrink-0 text-xs text-ink-3">basic data</span>
          </span>
          <button type="button" onClick={onClear} className="shrink-0 text-xs text-ink-3 hover:text-ink" aria-label={`Change ${label.toLowerCase()}`}>
            Change
          </button>
        </div>
      ) : node ? (
        <div className="flex h-9 items-center justify-between gap-2 rounded-lg border border-line px-3">
          <span className="flex min-w-0 items-center gap-2 text-sm text-ink">
            <NodeTypeIcon type={node.type} size={12} />
            <span className="truncate font-medium">{node.label}</span>
            <span className="shrink-0 text-xs text-ink-3">{TYPE_LABEL[node.type]?.one}</span>
          </span>
          <button type="button" onClick={onClear} className="shrink-0 text-xs text-ink-3 hover:text-ink" aria-label={`Change ${label.toLowerCase()}`}>
            Change
          </button>
        </div>
      ) : (
        <SearchBox
          variant="field"
          shortcut={false}
          onPick={onPick}
          onPickGlobal={onPickGlobal}
          label={`${label}: search the atlas`}
          placeholder="Disease, gene, symptom…"
        />
      )}
    </div>
  );
}

function PathResultView({
  idx,
  result,
  includeHypotheses,
}: {
  idx: GraphIndex;
  result: NonNullable<ReturnType<typeof shortestEvidencePath>>;
  includeHypotheses: boolean;
}) {
  const { openEdge } = useEvidence();
  const weakest = result.weakest;
  const usesHyp = result.steps.some((s) => s.edge.evidence_level === "hypothesis");
  const usesInferred = result.steps.some((s) => s.edge.evidence_level === "inferred");
  const contested = result.steps.filter((s) => s.edge.status === "contested").length;

  return (
    <div className="mt-10">
      <div className="rounded-lg bg-subtle px-5 py-4">
        <p className="text-[15px] text-ink">
          <span className="font-semibold">{result.steps.length === 1 ? "Directly connected." : `${result.steps.length} steps.`}</span>{" "}
          {weakest && (
            <>
              The weakest link is <span className="font-medium">{confidenceWord(weakest.confidence).toLowerCase()}</span> (
              {EVIDENCE_LEVEL_META[weakest.evidence_level].label.toLowerCase()}, {weakest.confidence.toFixed(2)}). A route is only as
              strong as its weakest link.
            </>
          )}
        </p>
        {(usesHyp || usesInferred || contested > 0) && (
          <p className="mt-1.5 text-sm text-ink-2">
            {usesHyp && "Includes an untested hypothesis. "}
            {usesInferred && "Includes a link inferred by the atlas, not stated by a source. "}
            {contested > 0 && "Includes a contested link: read both sides."}
          </p>
        )}
      </div>

      {result.steps.length > 0 && (
        <div className="mt-5">
          <AiAction
            key={`${result.nodes[0]}>${result.nodes[result.nodes.length - 1]}>${includeHypotheses}`}
            idx={idx}
            kind="explain-path"
            payload={{ from: result.nodes[0], to: result.nodes[result.nodes.length - 1], includeHypotheses }}
            label="Explain this in plain language"
            busyLabel="Explaining…"
          />
        </div>
      )}

      <ol className="mt-8" aria-label="Route">
        {result.nodes.map((id, i) => {
          const n = idx.nodeById.get(id)!;
          const step = result.steps[i];
          return (
            <li key={`${id}-${i}`}>
              <NodeRow node={n} first={i === 0} last={i === result.nodes.length - 1} />
              {step && (
                <div className="ml-[11px] border-l-2 border-line py-1 pl-7">
                  <div
                    className={`my-2 rounded-lg border px-4 py-3 ${
                      step.edge.evidence_level === "hypothesis"
                        ? "border-dotted border-ink-4"
                        : step.edge.evidence_level === "inferred"
                          ? "border-dashed border-ink-4"
                          : "border-line"
                    }`}
                  >
                    <p className="text-sm leading-relaxed text-ink">
                      {relationSentence(step.edge, idx.nodeById.get(step.edge.source), idx.nodeById.get(step.edge.target))}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-ink-3">{step.edge.explanation}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <EvidenceLevelBadge level={step.edge.evidence_level} size="sm" />
                      <StatusBadge status={step.edge.status} />
                      <ConfidenceMeter value={step.edge.confidence} compact />
                      <button
                        type="button"
                        onClick={() => openEdge(step.edge.id)}
                        className="ml-auto text-sm font-medium text-accent-700 hover:underline"
                      >
                        See evidence ({step.edge.evidence.length})
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function NodeRow({ node, first, last }: { node: AtlasNode; first: boolean; last: boolean }) {
  return (
    <div className="flex items-center gap-4">
      <span
        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
          first || last ? "border-accent-700 bg-white" : "border-line bg-white"
        }`}
      >
        <NodeTypeIcon type={node.type} size={10} />
      </span>
      <Link href={nodeHref(node)} className="group min-w-0">
        <span className="text-[16px] font-semibold text-ink group-hover:text-accent-700">{node.label}</span>
        <span className="ml-2 text-xs text-ink-3">{TYPE_LABEL[node.type]?.one}</span>
      </Link>
    </div>
  );
}

/** One or both ends sit outside the mapped families: say why there is no route, and where to go instead. */
function OutsideMapped({ idx, ends, loading }: { idx: GraphIndex; ends: GlobalEnd[]; loading: boolean }) {
  const families = idx.graph.clusters.filter((c) => c.basis === "pathway").map(familyName);
  const names = ends.map((e) => (e.row ? capFirst(e.row.name) : e.id));
  return (
    <div className="mt-10 rounded-lg border border-line px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">Paths run only inside the mapped families</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        A route here is a chain of sourced connections, and the atlas has those only for the{" "}
        {families.length > 1
          ? `${families.length} families it maps in depth (${families.join(", ")})`
          : families.length === 1
            ? `family it maps in depth (${families[0]})`
            : "diseases it maps in depth"}
        .{" "}
        {loading ? "Looking up the disease…" : `${joinList(names)} ${names.length > 1 ? "are" : "is"} mapped in basic form, so there is no evidence route to trace yet.`}
      </p>
      <ul className="mt-4 space-y-1.5">
        {ends.map((e, i) => (
          <li key={e.id}>
            <Link href={globalHref(e.id)} className="text-sm font-medium text-accent-700 hover:underline">
              Open {names[i]} (basic data) →
            </Link>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        Its page lists the most distinctive symptoms, the diseases with the most similar symptom patterns, and the closest disease in the
        mapped families.
      </p>
    </div>
  );
}

function NoRoute({
  idx,
  from,
  to,
  hypothesisRoute,
  onAllowHyp,
}: {
  idx: GraphIndex;
  from: AtlasNode;
  to: AtlasNode;
  hypothesisRoute: boolean;
  onAllowHyp: () => void;
}) {
  const gaps = gapsAbout(idx, [from.id, to.id]);
  return (
    <div className="mt-10 rounded-lg border-2 border-ink px-6 py-5">
      <h2 className="text-[17px] font-semibold text-ink">No supported route found</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        The atlas has no chain of sourced connections between {from.label} and {to.label}. That means the link is unknown in the
        sources searched, not that it is impossible.
      </p>
      {hypothesisRoute && (
        <p className="mt-3 text-sm text-ink-2">
          A route exists only through an untested hypothesis.{" "}
          <button type="button" onClick={onAllowHyp} className="font-medium text-accent-700 hover:underline">
            Show it anyway
          </button>
        </p>
      )}
      <p className="mt-3 text-xs text-ink-3">Searched: {idx.graph.meta.sources.map((s) => s.name).join("; ") || "no sources listed"}</p>
      {gaps.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium text-ink">Related open questions</p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-ink-2">
            {gaps.map((g) => (
              <li key={g.id}>
                {g.question} <span className="text-ink-3">{g.how_to_find_out}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
