"use client";

import { DirectionFlags } from "../direction/DirectionFlag";
import Link from "next/link";
import { EvidenceChip, EvidenceLevelBadge } from "../evidence/EvidenceBits";
import { SourceCard } from "../evidence/EvidencePanel";
import { AiAction } from "../ai/AiAction";
import { atlasHref, diseaseHref, neighbors, type GraphIndex } from "@/lib/graph";
import { relationSentence } from "@/lib/text";
import type { AtlasEdge, Evidence } from "@/lib/types";

export interface IdeaAttrs {
  title?: string;
  chain?: { kind: string; edges: string[]; edge_confidences?: number[]; contested_edges?: string[]; mechanism?: string };
  weakest_link?: string;
  caveats?: { kind: string; text: string }[];
  caveat_citations?: Evidence[];
  test?: { what_to_test?: string; existing_assay_or_model?: string[]; existing_assay_note?: string; what_result_would_change_the_plan?: string };
}

const CHAIN_WORDS: Record<string, string> = {
  driven_by: "the disease is directly linked to the mechanism the therapy targets",
  variant_group: "a variant group of the gene has the effect the therapy targets",
  pathway: "the gene takes part in the process the therapy targets (a weaker, pathway-only link)",
  cluster: "only a curated cluster groups the therapy and the disease (the weakest kind of link)",
};

/** Candidate_for edges pointing at a disease (computed hypotheses). */
export function ideasFor(idx: GraphIndex, diseaseId?: string): AtlasEdge[] {
  const all = idx.graph.edges.filter((e) => e.type === "candidate_for");
  const list = diseaseId ? neighbors(idx, diseaseId, { relations: ["candidate_for"], direction: "in" }).map((n) => n.edge) : all;
  return [...list].sort((a, b) => b.confidence - a.confidence);
}

export function IdeaCard({ idx, edge, compact = false }: { idx: GraphIndex; edge: AtlasEdge; compact?: boolean }) {
  const a = (edge.attrs ?? {}) as IdeaAttrs;
  const therapy = idx.nodeById.get(edge.source);
  const disease = idx.nodeById.get(edge.target);
  const steps = (a.chain?.edges ?? [])
    .map((id, i) => ({ id, edge: idx.edgeById.get(id), conf: a.chain?.edge_confidences?.[i] }))
    .filter((s, i, all) => all.findIndex((x) => x.id === s.id) === i);
  const contested = new Set(a.chain?.contested_edges ?? []);
  // weakest link: the lowest-confidence step; a contested step wins a tie
  const weakestId = [...steps].sort(
    (x, y) => (x.edge?.confidence ?? x.conf ?? 1) - (y.edge?.confidence ?? y.conf ?? 1) || Number(contested.has(y.id)) - Number(contested.has(x.id)),
  )[0]?.id;

  return (
    <article className="rounded-lg border border-dashed border-ink-4 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-ink-3">
            {therapy?.label} → {disease ? <Link href={diseaseHref(disease.id)} className="hover:text-accent-700">{disease.label}</Link> : edge.target}
          </p>
          <h3 className="mt-0.5 text-[16px] font-semibold leading-snug text-ink">{a.title ?? edge.label ?? "Idea worth testing"}</h3>
        </div>
        <span className="flex items-center gap-2">
          <EvidenceLevelBadge level="hypothesis" size="sm" />
          <EvidenceChip edge={edge} label="Why it was proposed" />
        </span>
      </div>
      {a.chain?.kind && <p className="mt-2 text-sm text-ink-3">Kind of link: {CHAIN_WORDS[a.chain.kind] ?? a.chain.kind}.</p>}
      <DirectionFlags therapyId={edge.source} diseaseId={edge.target} />

      <ol className="mt-3 space-y-1.5" aria-label="Chain of links">
        {steps.map((s, i) => {
          const weak = s.id === weakestId;
          return (
            <li key={s.id} className={`flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5 text-sm ${weak ? "border border-warn-line bg-warn-bg" : ""}`}>
              <span className="w-4 tabular-nums text-ink-3">{i + 1}</span>
              <span className="text-ink-2">{s.edge ? relationSentence(s.edge, idx.nodeById.get(s.edge.source), idx.nodeById.get(s.edge.target)) : s.id}</span>
              {s.edge && <EvidenceChip edge={s.edge} />}
              {weak && <span className="text-xs font-semibold text-warn-ink">weakest link</span>}
            </li>
          );
        })}
      </ol>
      {a.weakest_link && (
        <p className="mt-2 text-sm leading-relaxed text-warn-ink">
          <b className="font-medium">Weakest link:</b> {a.weakest_link}
        </p>
      )}

      {!compact && (
        <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-4 border-t border-line-2 pt-4 md:grid-cols-2">
          {a.caveats && a.caveats.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">Caveats</p>
              <ul className="mt-1.5 space-y-1.5 text-sm leading-relaxed text-ink-2">
                {a.caveats.map((c) => (
                  <li key={c.text}>
                    <span className="text-ink-3">{c.kind}: </span>
                    {c.text}
                  </li>
                ))}
              </ul>
              {a.caveat_citations && a.caveat_citations.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-ink-2">Sources for the caveats ({a.caveat_citations.length})</summary>
                  <div className="mt-2 space-y-2">
                    {a.caveat_citations.map((ev, i) => (
                      <SourceCard key={`${ev.ref}-${i}`} ev={ev} />
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
          {a.test && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">How to test it</p>
              {a.test.what_to_test && <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{a.test.what_to_test}</p>}
              {a.test.existing_assay_or_model && a.test.existing_assay_or_model.length > 0 && (
                <p className="mt-2 text-sm text-ink-2">
                  <span className="text-ink-3">Already exists: </span>
                  {a.test.existing_assay_or_model.map((x, i) => {
                    const n = idx.nodeById.get(x);
                    const pmid = /^PMID:(\d+)$/.exec(x);
                    return (
                      <span key={x}>
                        {i > 0 && ", "}
                        {n ? (
                          <Link href={atlasHref(n.id)} className="text-accent-700 hover:underline">
                            {n.label}
                          </Link>
                        ) : pmid ? (
                          <a href={`https://pubmed.ncbi.nlm.nih.gov/${pmid[1]}/`} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                            {x} ↗
                          </a>
                        ) : (
                          x
                        )}
                      </span>
                    );
                  })}
                </p>
              )}
              {a.test.existing_assay_note && <p className="mt-1 text-xs leading-relaxed text-ink-3">{a.test.existing_assay_note}</p>}
              {a.test.what_result_would_change_the_plan && (
                <p className="mt-2 text-sm leading-relaxed text-ink-2">
                  <span className="text-ink-3">What would change the plan: </span>
                  {a.test.what_result_would_change_the_plan}
                </p>
              )}
            </div>
          )}
          <div className="md:col-span-2 empty:hidden">
            <AiAction idx={idx} kind="experiment" payload={{ id: edge.id }} label="Draft the experiment" busyLabel="Drafting…" />
          </div>
        </div>
      )}
    </article>
  );
}
