"use client";

import Link from "next/link";
import { atlasHref, nodeHref, pathHref, type GraphIndex } from "@/lib/graph";
import { bridgesOf } from "@/lib/bridges";
import {
  STUDY_TYPE_LABEL,
  TYPE_LABEL,
  isPlaceholderUrl,
  relationName,
  relationSentence,
  rubricFor,
  isEvidenceBacked,
} from "@/lib/text";
import { isAiReview, type AtlasEdge, type AtlasNode, type Evidence } from "@/lib/types";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { ContributedBadge, contributionsOf } from "../ContributedBadge";
import { ConfidenceMeter, EvidenceLegend, EvidenceLevelBadge, StatusBadge } from "./EvidenceBits";

export function EvidencePanel({
  idx,
  edge,
  onClose,
}: {
  idx: GraphIndex;
  edge: AtlasEdge;
  onNavigate?: (edgeId: string) => void;
  onClose?: () => void;
}) {
  const s = idx.nodeById.get(edge.source);
  const t = idx.nodeById.get(edge.target);
  // AI-flagged contradictions (needs_review) are listed with the limiting evidence, clearly labelled
  const supporting = edge.evidence.filter((e) => e.supports !== false && !e.needs_review);
  const limiting = [...edge.evidence.filter((e) => e.supports === false || e.needs_review), ...(edge.counter_evidence ?? [])];
  const isSample = !!idx.graph.meta.sample || [...edge.evidence, ...limiting].some((e) => e.ref === "SAMPLE");
  const bridge = bridgesOf(idx).get(edge.id);

  return (
    <div className="space-y-8 px-6 pb-10 pt-6">
      {/* Summary first */}
      <section className="space-y-4">
        <p className="text-xs font-medium text-ink-3">{relationName(edge.type)}</p>
        <h2 id="evidence-title" className="text-[19px] font-semibold leading-snug tracking-tight text-ink">
          {relationSentence(edge, s, t)}
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <EndpointLink node={s} onClose={onClose} />
          <span className="text-ink-3" aria-hidden="true">
            →
          </span>
          <EndpointLink node={t} onClose={onClose} />
        </div>
        <p className="text-[15px] leading-relaxed text-ink-2">{edge.explanation}</p>
        {bridge && (
          <p className="flex items-start gap-2.5 text-sm leading-relaxed text-ink-2">
            <svg width="22" height="14" aria-hidden="true" className="mt-[3px] shrink-0">
              <line x1="3.5" y1="7" x2="18.5" y2="7" stroke="#c7d8ea" strokeWidth="7" strokeLinecap="round" />
              <line x1="3.5" y1="7" x2="18.5" y2="7" stroke="#3e6ea5" strokeWidth="1.8" />
            </svg>
            <span>
              <span className="font-medium text-accent-700">Bridge across clusters.</span> {bridge.why}
            </span>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg bg-subtle px-4 py-3">
          <div className="flex items-center gap-2">
            <EvidenceLevelBadge level={edge.evidence_level} />
            <StatusBadge status={edge.status} />
          </div>
          <ConfidenceMeter value={edge.confidence} />
          <p className="w-full text-xs leading-relaxed text-ink-3">
            {isEvidenceBacked(edge.evidence_level)
              ? "Backed by sources. "
              : edge.evidence_level === "inferred"
                ? "Computed by the atlas, not stated by a source. "
                : "Untested idea, not a finding. "}
            A score of {edge.confidence.toFixed(2)} means: {rubricFor(edge.confidence).toLowerCase()}.
            {edge.status === "contested" ? " Sources disagree, so read both sides below." : ""}
          </p>
        </div>
      </section>

      {edge.review && <ReviewNote review={edge.review} />}
      {contributionsOf(edge).length > 0 && (
        <p className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
          <ContributedBadge stamps={contributionsOf(edge)} />
          Added through “Contribute what you know”; drawn lighter on the map until an expert reviews it.
        </p>
      )}

      {isSample && (
        <p className="rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-xs leading-relaxed text-warn-ink">
          Sample data: the sources below are placeholders that show where real citations will appear. They are not real
          records.
        </p>
      )}

      {/* Sources */}
      <section aria-labelledby="ev-sources" className="space-y-3">
        <h3 id="ev-sources" className="text-sm font-semibold text-ink">
          Sources supporting this <span className="font-normal text-ink-3">({supporting.length})</span>
        </h3>
        {supporting.length === 0 ? (
          <p className="rounded-lg border border-dashed border-ink-4 px-4 py-3 text-sm text-ink-2">
            {edge.evidence_level === "hypothesis"
              ? "No sources yet. This is a hypothesis: an idea to test, not a finding."
              : "No sources recorded for this connection. Treat it as unverified."}
          </p>
        ) : (
          <ul className="space-y-3">
            {supporting.map((ev, i) => (
              <li key={`${ev.ref}-${i}`}>
                <SourceCard ev={ev} contributed={idx.contributedUrls.has(ev.url)} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Counter-evidence: always shown, never hidden */}
      <section aria-labelledby="ev-counter" className="space-y-3" data-tour="counter">
        <h3 id="ev-counter" className="text-sm font-semibold text-ink">
          Contradicting or limiting evidence{" "}
          <span className="font-normal text-ink-3">({limiting.length})</span>
        </h3>
        {limiting.length === 0 ? (
          <p className="text-sm text-ink-3">None found in sources searched.</p>
        ) : (
          <ul className="space-y-3">
            {limiting.map((ev, i) => (
              <li key={`${ev.ref}-c-${i}`}>
                <SourceCard ev={ev} contradicts />
              </li>
            ))}
          </ul>
        )}
      </section>

      <details className="group rounded-lg border border-line">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-ink-2 hover:text-ink">
          <span className="mr-2 inline-block transition-transform group-open:rotate-90" aria-hidden="true">
            ›
          </span>
          What do evidence levels and scores mean?
        </summary>
        <div className="border-t border-line px-4 py-4">
          <EvidenceLegend />
        </div>
      </details>

      <section className="flex flex-wrap gap-2 border-t border-line pt-5">
        <Link
          href={atlasHref(edge.source)}
          onClick={onClose}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
        >
          Show in atlas
        </Link>
        <Link
          href={pathHref(edge.source, edge.target)}
          onClick={onClose}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
        >
          Open as path
        </Link>
      </section>
      <p className="break-all text-[11px] text-ink-3">Connection ID: {edge.id}</p>
    </div>
  );
}

function EndpointLink({ node, onClose }: { node?: AtlasNode; onClose?: () => void }) {
  if (!node) return <span className="text-ink-3">Unknown</span>;
  return (
    <Link
      href={nodeHref(node)}
      onClick={onClose}
      className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-ink-2 hover:border-accent-500 hover:text-ink"
    >
      <NodeTypeIcon type={node.type} size={12} />
      <span className="font-medium">{node.label}</span>
      <span className="text-xs text-ink-3">{TYPE_LABEL[node.type]?.one}</span>
    </Link>
  );
}

function extractedByText(x: Evidence["extracted_by"]): string {
  if (!x) return "Unknown origin";
  if (x === "database") return "Imported from the database record";
  if (x === "agent-curation") return "Extracted by an AI curation agent";
  if (x === "computed") return "Computed by the atlas";
  if (x.startsWith("openai:")) return `Extracted by OpenAI (${x.slice(7)})`;
  if (x.startsWith("claude:")) return "Extracted by an independent Claude reading";
  if (x.startsWith("human:")) return `Added by ${x.slice(6)}`;
  return x;
}

/** "openai:gpt-6-astra" -> "GPT-6-Astra"; "claude:agent-reading" -> "Claude" */
export function modelName(by: string): string {
  if (/^claude:/i.test(by)) return "Claude";
  const raw = by.replace(/^openai:/i, "").replace(/^human:/i, "");
  return raw
    .split("-")
    .map((p) => (/^gpt$/i.test(p) ? "GPT" : /^o\d/i.test(p) ? p : p.charAt(0).toUpperCase() + p.slice(1)))
    .join("-");
}

const VERDICT: Record<string, string> = { confirmed: "Confirmed", corrected: "Corrected", rejected: "Rejected", "needs-human": "Needs a human expert" };

function ReviewNote({ review }: { review: NonNullable<AtlasEdge["review"]> }) {
  const ai = isAiReview(review);
  const warn = review.verdict === "rejected" || review.verdict === "needs-human";
  // AI notes start with their own disclaimer; the label already says it, so it is not repeated
  const note = ai ? review.note?.replace(/^Independent AI review \([^)]*\), not a human expert\.\s*/i, "") : review.note;
  const model = ai ? review.by.replace(/^ai-review:/, "") : "";
  return (
    <section className={`rounded-lg border px-4 py-3 ${warn ? "border-warn-line bg-warn-bg" : ai ? "border-accent-200 bg-accent-50" : "border-[#bcd9c6] bg-[#f3f9f5]"}`}>
      <p className={`flex flex-wrap items-center gap-x-2 text-sm font-medium ${warn ? "text-warn-ink" : ai ? "text-accent-900" : "text-ok"}`}>
        <CheckGlyph />
        {ai ? "Independently reviewed by AI (not a human expert)" : "Reviewed by a biochemist"}
        <span className="font-normal text-ink-3">
          · {model ? `${model.charAt(0).toUpperCase()}${model.slice(1)} · ` : ""}
          {review.date} · {VERDICT[review.verdict] ?? review.verdict}
        </span>
      </p>
      {note && <p className="mt-1.5 text-sm leading-relaxed text-ink-2">“{note}”</p>}
    </section>
  );
}

function CheckGlyph() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="6.5" fill="currentColor" />
      <path d="M4 7.2 6 9.2 10 5" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CrossCheck({ cc }: { cc: NonNullable<Evidence["cross_checked"]> }) {
  return cc.agrees ? (
    <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-ok" title={`An independent re-reading of this source by ${modelName(cc.by)} on ${cc.date} agreed with it.`}>
      <CheckGlyph /> Cross-checked by {modelName(cc.by)}
      <span className="font-normal text-ink-3">· {cc.date}</span>
    </p>
  ) : (
    <p className="mt-2 inline-flex items-center gap-1.5 rounded border border-warn-line bg-warn-bg px-2 py-0.5 text-xs font-medium text-warn-ink">
      AI re-reading disagrees, needs expert review
      <span className="font-normal">· {modelName(cc.by)} · {cc.date}</span>
    </p>
  );
}

export function SourceCard({ ev, contradicts = false, contributed = false }: { ev: Evidence; contradicts?: boolean; contributed?: boolean }) {
  const needsQuote = (ev.source === "PubMed" || ev.source === "Website") && !ev.quote;
  const kind = ev.study_type ? STUDY_TYPE_LABEL[ev.study_type] : ev.kind;
  return (
    <article
      className={`rounded-lg border px-4 py-3.5 ${contradicts ? "border-warn-line bg-warn-bg/40" : "border-line bg-white"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold text-ink">{ev.source}</span>
            {kind && <span className="text-xs text-ink-3">{kind}</span>}
            {contributed && <ContributedBadge stamps={[{ by: ev.extracted_by?.startsWith("human:") ? ev.extracted_by.slice(6) : undefined }]} />}
            {contradicts &&
              (ev.needs_review ? (
                <span className="text-xs font-medium text-warn-ink">Flagged by AI re-reading, not yet reviewed</span>
              ) : (
                <span className="text-xs font-medium text-warn-ink">Contradicts or limits</span>
              ))}
          </div>
          {ev.title && <p className="mt-0.5 text-sm leading-snug text-ink-2">{ev.title}</p>}
          <p className="mt-0.5 text-xs tabular-nums text-ink-3">
            {[ev.ref, ev.year, ev.retrieved ? `retrieved ${ev.retrieved}` : null].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Verified verified={!!ev.verified} />
      </div>
      {ev.quote && (
        <blockquote className="mt-3 border-l-2 border-ink-4 pl-3 text-sm leading-relaxed text-ink-2">
          “{ev.quote}”
        </blockquote>
      )}
      {ev.cross_checked && <CrossCheck cc={ev.cross_checked} />}
      {ev.cross_checked_also?.map((cc) => <CrossCheck key={cc.by} cc={cc} />)}
      {needsQuote && (
        <p className="mt-3 text-xs text-warn-ink">No verbatim quote recorded. This source type should include one.</p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="text-ink-3">{extractedByText(ev.extracted_by)}</span>
        {isPlaceholderUrl(ev.url) ? (
          <span className="text-ink-3">No link (placeholder)</span>
        ) : (
          <a
            href={ev.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-accent-700 underline-offset-2 hover:underline"
          >
            Open source<span className="sr-only"> (opens in a new tab)</span> ↗
          </a>
        )}
      </div>
    </article>
  );
}

function Verified({ verified }: { verified: boolean }) {
  return verified ? (
    <span
      className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-ok"
      title="The quote was matched against the stored source text, or a person checked it."
    >
      <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
        <circle cx="7" cy="7" r="6.5" fill="currentColor" />
        <path d="M4 7.2 6 9.2 10 5" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Verified
    </span>
  ) : (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs text-ink-3" title="Not yet matched against the source text.">
      <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
        <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.2" />
      </svg>
      Not verified
    </span>
  );
}
