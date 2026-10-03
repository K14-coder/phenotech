"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { SourceCard } from "../evidence/EvidencePanel";
import { FitBadge } from "../variant/VariantView";
import { diseaseHref, neighbors, type GraphIndex } from "@/lib/graph";
import { communitiesFor, diseaseContext } from "@/lib/insights";
import { useDerived, type ModalityCell, type ModalityData } from "@/lib/derived";
import { ASSET_KIND_LABEL, isPlaceholderUrl, joinList } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";

const FIT_ORDER: Record<string, number> = { good: 0, conditional: 1, poor: 2, not_assessed: 3 };

/** Which modalities act on a mechanism (by what the mechanism is). */
export function modalitiesForMechanism(mech: AtlasNode | undefined): string[] {
  const s = `${mech?.id ?? ""} ${mech?.label ?? ""}`.toLowerCase();
  if (/haploinsuff|loss-of-function|loss of function/.test(s)) return ["aav_gene_replacement", "transcript_upregulation", "gene_editing"];
  if (/gain-of-function|gain of function|dominant-negative|dominant negative/.test(s)) return ["aso_sirna_knockdown", "gene_editing"];
  if (/destabil|misfold/.test(s)) return ["chemical_chaperone"];
  return ["symptomatic_pathway_small_molecule"];
}

export function ApproachView() {
  return <WithGraph>{(idx) => <Approach idx={idx} />}</WithGraph>;
}

function Approach({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const router = useRouter();
  const md = useDerived<ModalityData>("modality");
  const mechanismId = params.get("mechanism");
  const focusDisease = params.get("disease");
  const mechanism = mechanismId ? idx.nodeById.get(mechanismId) : undefined;
  const allowed = mechanism ? modalitiesForMechanism(mechanism) : null;
  const modalityId = params.get("modality") ?? allowed?.[0] ?? "aav_gene_replacement";
  const mechanisms = useMemo(() => idx.graph.nodes.filter((n) => n.type === "mechanism").sort((a, b) => a.label.localeCompare(b.label)), [idx]);

  const set = (o: { modality?: string; mechanism?: string | null }) => {
    const q = new URLSearchParams();
    const mech = o.mechanism === undefined ? mechanismId : o.mechanism;
    if (mech) q.set("mechanism", mech);
    q.set("modality", o.modality ?? (o.mechanism !== undefined && mech ? modalitiesForMechanism(idx.nodeById.get(mech))[0] : modalityId));
    router.replace(`/approach?${q.toString()}`, { scroll: false });
  };

  if (md.status === "loading") return <p className="mx-auto max-w-[1120px] px-8 py-16 text-sm text-ink-3">Loading the approach screen…</p>;
  if (md.status === "missing") return <p className="mx-auto max-w-[1120px] px-8 py-16 text-sm text-ink-3">The approach screen (modality.json) is not available in this build.</p>;
  const data = md.data;
  const mod = data.modalities.find((m) => m.id === modalityId) ?? data.modalities[0];

  const rows = Object.entries(data.assessments)
    .filter(([d]) => idx.nodeById.has(d) && (!mechanism || diseaseContext(idx, d)?.mechanisms.has(mechanism.id)))
    .map(([d, a]) => ({ id: d, a, cell: a.modalities[mod.id] }))
    .filter((r) => r.cell)
    .sort(
      (x, y) =>
        (FIT_ORDER[x.cell.fit] ?? 9) - (FIT_ORDER[y.cell.fit] ?? 9) ||
        y.cell.reasons.filter((r) => r.votes === "good").length - x.cell.reasons.filter((r) => r.votes === "good").length ||
        x.a.label.localeCompare(y.a.label),
    );

  return (
    <div className="mx-auto w-full max-w-[1120px] px-8 pb-24 pt-8">
      <p className="text-sm text-ink-3">For biotech scouts and researchers</p>
      <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.02em] text-ink">Therapy approaches</h1>
      <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-ink-3">
        Pick an approach or a mechanism. Diseases are ranked by how well their published mechanism matches what the approach does, with the
        rules and reasons behind every label, because the signal is in the reasons.
      </p>
      <div className="mt-5 rounded-lg border border-warn-line bg-warn-bg px-5 py-3.5" role="note">
        <p className="text-sm font-semibold text-warn-ink">{data.status[0].toUpperCase() + data.status.slice(1)}</p>
        <p className="mt-1 text-sm leading-relaxed text-warn-ink">{data.not_advice}</p>
      </div>

      <div className="mt-7 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div>
          <p className="text-xs font-medium text-ink-3">Approach</p>
          <div className="mt-2 flex flex-wrap gap-2" role="tablist" aria-label="Approaches">
            {data.modalities.map((m) => {
              const on = m.id === mod.id;
              const muted = allowed && !allowed.includes(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => set({ modality: m.id })}
                  className={`rounded-md border px-3 py-1.5 text-sm ${on ? "border-accent-700 bg-accent-50 text-ink" : muted ? "border-line text-ink-3" : "border-line text-ink-2 hover:border-accent-500"}`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-sm leading-relaxed text-ink-2">
            <b className="font-medium text-ink">{mod.label}.</b> {mod.what_it_does} <span className="text-ink-3">Best case: {mod.best_case_mechanism}.</span>
          </p>
        </div>
        <label className="block">
          <span className="text-xs font-medium text-ink-3">Or start from a mechanism</span>
          <select
            value={mechanismId ?? ""}
            onChange={(e) => set({ mechanism: e.target.value || null })}
            className="mt-2 h-9 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink focus:border-accent-700 focus:outline-none"
          >
            <option value="">All mechanisms</option>
            {mechanisms.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          {mechanism && (
            <span className="mt-1.5 block text-xs text-ink-3">
              Showing diseases linked to this mechanism. Approaches that act on it: {joinList(allowed!.map((a) => data.modalities.find((m) => m.id === a)?.label ?? a), 3)}.
            </span>
          )}
        </label>
      </div>

      <details className="mt-5 rounded-lg border border-line px-4 py-2.5 text-sm">
        <summary className="cursor-pointer font-medium text-ink-2">How the fit labels work</summary>
        <ul className="mt-2 space-y-1 text-ink-2">
          {Object.entries(data.meta.fit_scale).map(([k, v]) => (
            <li key={k}>
              <FitBadge fit={k} /> <span className="ml-1">{v}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-3">Aggregation: {data.meta.aggregation}.</p>
      </details>

      <ol className="mt-8 space-y-4">
        {rows.map((r, i) => (
          <DiseaseRow key={r.id} idx={idx} data={data} diseaseId={r.id} cell={r.cell} rank={i + 1} open={r.id === focusDisease || (i === 0 && !focusDisease)} />
        ))}
        {!rows.length && <p className="text-sm text-ink-3">No disease in the atlas is linked to this mechanism.</p>}
      </ol>
    </div>
  );
}

function DiseaseRow({ idx, data, diseaseId, cell, rank, open }: { idx: GraphIndex; data: ModalityData; diseaseId: string; cell: ModalityCell; rank: number; open: boolean }) {
  const [expanded, setExpanded] = useState(open);
  const [allReasons, setAllReasons] = useState(false);
  const a = data.assessments[diseaseId];
  const d = idx.nodeById.get(diseaseId)!;
  const mechEdges = (cell.graph_edge_ids.mechanism ?? []).map((id) => idx.edgeById.get(id)).filter((e): e is NonNullable<typeof e> => !!e);
  const community = communitiesFor(idx, diseaseId);
  const covers = neighbors(idx, diseaseId, { relations: ["covers"], direction: "in" })
    .map((n) => ({ node: idx.nodeById.get(n.other)!, edge: n.edge }))
    .filter((x) => x.node?.type === "asset");
  const infra = covers.filter((x) => x.node.type === "asset" && ["registry", "natural_history_study", "animal_model", "cell_model", "outcome_measure", "biobank"].includes(x.node.attrs?.kind ?? ""));
  const trials = neighbors(idx, diseaseId, { relations: ["studies"], direction: "in" })
    .map((n) => idx.nodeById.get(n.other))
    .filter((n): n is AtlasNode => !!n && n.type === "study" && n.attrs?.study_type === "interventional");
  const ctx = diseaseContext(idx, diseaseId);
  const geneIds = new Set(ctx?.genes.map((g) => g.id) ?? []);
  const contacts = neighbors(idx, diseaseId, { relations: ["works_on"], direction: "in" })
    .concat([...geneIds].flatMap((g) => neighbors(idx, g, { relations: ["works_on"], direction: "in" })))
    .map((n) => ({ node: idx.nodeById.get(n.other)!, edge: n.edge }))
    .filter((x, i, all) => x.node && all.findIndex((y) => y.node.id === x.node.id) === i)
    .slice(0, 5);
  const programmes = a.checks.existing_programmes ?? [];
  const stopped = a.checks.stopped_programmes ?? [];
  const approved = d.type === "disease" ? d.attrs?.approved_treatment : undefined;
  const reasons = allReasons ? cell.reasons : cell.reasons.slice(0, 3);
  const ruleText = (id: string) => data.rules.find((r) => r.id === id);

  return (
    <li className="rounded-lg border border-line px-5 py-4" id={`row-${diseaseId}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span className="w-5 text-sm tabular-nums text-ink-3">{rank}</span>
          <div>
            <Link href={diseaseHref(diseaseId)} className="text-[17px] font-semibold text-ink hover:text-accent-700">
              {a.label}
            </Link>
            <span className="ml-2 text-xs text-ink-3">{a.gene}</span>
          </div>
        </div>
        <FitBadge fit={cell.fit} />
      </div>

      <ul className="mt-3 space-y-1.5 pl-8 text-sm leading-relaxed text-ink-2">
        {reasons.map((r) => (
          <li key={r.rule} className="flex gap-2">
            <span className={`mt-[3px] shrink-0 rounded px-1 text-[10px] font-semibold ${r.votes === "good" ? "bg-[#edf6f0] text-ok" : r.votes === "poor" ? "bg-warn-bg text-warn-ink" : "bg-accent-50 text-accent-900"}`} title={ruleText(r.rule)?.condition}>
              {r.rule}
            </span>
            <span>{r.text}</span>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap gap-4 pl-8 text-sm">
        {cell.reasons.length > 3 && (
          <button type="button" onClick={() => setAllReasons(!allReasons)} className="font-medium text-accent-700 hover:underline">
            {allReasons ? "Fewer reasons" : `All ${cell.reasons.length} reasons`}
          </button>
        )}
        <button type="button" onClick={() => setExpanded(!expanded)} className="font-medium text-accent-700 hover:underline" aria-expanded={expanded}>
          {expanded ? "Hide details" : "Evidence, communities, programmes and contacts"}
        </button>
        <span className="text-xs text-ink-3 self-center">Rules fired: {cell.rules_fired.join(", ")}</span>
      </div>

      {expanded && (
        <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-5 border-t border-line-2 pl-8 pt-4 md:grid-cols-2">
          <Block title="Mechanistic evidence">
            {mechEdges.length ? (
              <div className="flex flex-wrap gap-1.5">
                {mechEdges.map((e) => (
                  <EvidenceChip key={e.id} edge={e} label={idx.nodeById.get(e.target)?.label ?? e.target} />
                ))}
              </div>
            ) : (
              <Muted>No mechanism edge recorded.</Muted>
            )}
          </Block>
          <Block title="Unmet need">
            <p className="text-sm text-ink-2">
              Approved treatment: {approved === true ? "yes" : approved === false ? "none known" : "not recorded"}. Interventional trials:{" "}
              {trials.length ? `${trials.length} (${joinList(trials.map((t) => t.label), 2)})` : "none registered in the sources searched"}.
            </p>
          </Block>
          <Block title="Patient communities">
            {community.specific.length || community.umbrella.length ? (
              <p className="text-sm text-ink-2">{joinList([...community.specific, ...community.umbrella].map((o) => o.org.label), 4)}</p>
            ) : (
              <Muted>No patient group recorded.</Muted>
            )}
          </Block>
          <Block title="Existing infrastructure">
            {infra.length ? (
              <ul className="space-y-1 text-sm text-ink-2">
                {infra.slice(0, 5).map((x) => (
                  <li key={x.node.id}>
                    {x.node.label} <span className="text-xs text-ink-3">{x.node.type === "asset" && x.node.attrs?.kind ? ASSET_KIND_LABEL[x.node.attrs.kind] : ""}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Muted>No registry, natural history study or model recorded.</Muted>
            )}
          </Block>
          <Block title="Existing programmes">
            {programmes.length || stopped.length ? (
              <ul className="space-y-1.5 text-sm text-ink-2">
                {programmes.map((p) => (
                  <li key={p.therapy}>
                    {p.label} <span className="text-xs text-ink-3">· {p.stage}{p.trials.length ? ` · ${p.trials.join(", ")} (${p.trial_status.join(", ").toLowerCase().replace(/_/g, " ")})` : ""}</span>
                    {p.why_stopped.length > 0 && <span className="block text-xs font-medium text-warn-ink">Stopped: {p.why_stopped.join("; ")}</span>}
                  </li>
                ))}
                {stopped
                  .filter((s) => !programmes.some((p) => p.therapy === s.therapy))
                  .map((s) => (
                    <li key={s.therapy} className="text-warn-ink">
                      {idx.nodeById.get(s.therapy)?.label ?? s.therapy}: {s.status.join(", ").toLowerCase()}, {s.why_stopped.join("; ")}
                    </li>
                  ))}
              </ul>
            ) : (
              <Muted>No programme recorded.</Muted>
            )}
          </Block>
          <Block title="Named contacts">
            {contacts.length ? (
              <ul className="space-y-1.5 text-sm">
                {contacts.map((c) => {
                  const url = c.node.type === "researcher" ? c.node.attrs?.url : undefined;
                  return (
                    <li key={c.node.id} className="flex flex-wrap items-center gap-2">
                      <span className="text-ink">{c.node.label}</span>
                      {c.node.type === "researcher" && c.node.attrs?.affiliation && <span className="text-xs text-ink-3">{c.node.attrs.affiliation}</span>}
                      <EvidenceChip edge={c.edge} label="Paper" />
                      {!isPlaceholderUrl(url) && (
                        <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent-700 hover:underline">
                          Publications ↗
                        </a>
                      )}
                    </li>
                  );
                })}
                {community.specific[0] && <li className="text-xs text-ink-3">Patient group: {community.specific[0].org.label}</li>}
              </ul>
            ) : (
              <Muted>No researcher linked yet.</Muted>
            )}
          </Block>
          {cell.caveats.length > 0 && (
            <Block title="Caveats">
              <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">
                {cell.caveats.map((c) => (
                  <li key={c.rule + c.text}>{c.text}</li>
                ))}
              </ul>
            </Block>
          )}
          <Block title="Open questions for an expert">
            {cell.open_questions_for_expert.length ? (
              <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">
                {cell.open_questions_for_expert.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            ) : (
              <Muted>None recorded.</Muted>
            )}
          </Block>
          {cell.citation_ids.length > 0 && (
            <details className="md:col-span-2">
              <summary className="cursor-pointer text-sm font-medium text-ink-2">Sources behind these rules ({cell.citation_ids.length})</summary>
              <ul className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                {cell.citation_ids.map((cid) => {
                  const ev = data.citations[cid];
                  return ev ? (
                    <li key={cid}>
                      <SourceCard ev={ev} />
                    </li>
                  ) : null;
                })}
              </ul>
            </details>
          )}
        </div>
      )}
    </li>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">{title}</p>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-ink-3">{children}</p>;
}

