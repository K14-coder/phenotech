"use client";

import { EVIDENCE_LEVEL_META, EVIDENCE_LEVELS, CONFIDENCE_RUBRIC, confidenceWord } from "@/lib/text";
import { LEVEL_BADGE_CLASS } from "@/lib/style";
import type { AtlasEdge, EvidenceLevel } from "@/lib/types";
import { useEvidence } from "./EvidenceProvider";

export function EvidenceLevelBadge({ level, size = "md" }: { level: EvidenceLevel; size?: "sm" | "md" }) {
  const meta = EVIDENCE_LEVEL_META[level] ?? { label: level, short: level, legend: "" };
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border font-medium ${LEVEL_BADGE_CLASS[level] ?? ""} ${
        size === "sm" ? "px-1.5 py-px text-[11px]" : "px-2 py-0.5 text-xs"
      }`}
      title={meta.legend}
    >
      {size === "sm" ? meta.short : meta.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: AtlasEdge["status"] }) {
  if (status === "contested") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded border border-warn-line bg-warn-bg px-2 py-0.5 text-xs font-medium text-warn-ink"
        title="Sources disagree about this connection. Both sides are shown below."
      >
        <WarnGlyph /> Contested
      </span>
    );
  }
  if (status === "unverified") {
    return (
      <span className="inline-flex items-center rounded border border-line px-2 py-0.5 text-xs text-ink-3" title="Not yet checked against its sources.">
        Unverified
      </span>
    );
  }
  return null;
}

export function WarnGlyph({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
      <path d="M6 1 11.2 10.5H.8Z" fill="currentColor" />
      <rect x="5.4" y="4.2" width="1.2" height="3.4" fill="#fff" />
      <rect x="5.4" y="8.3" width="1.2" height="1.2" fill="#fff" />
    </svg>
  );
}

/** Confidence 0–1 as a bar with rubric ticks at 0.3 / 0.5 / 0.7 / 0.9. */
export function ConfidenceMeter({ value, compact = false }: { value: number; compact?: boolean }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  const word = confidenceWord(value);
  return (
    <div className={`flex items-center gap-2.5 ${compact ? "" : "min-w-[180px]"}`}>
      <div
        className={`relative overflow-hidden rounded-full bg-line-2 ${compact ? "h-1.5 w-16" : "h-2 w-28"}`}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value}
        aria-label={`Confidence ${value.toFixed(2)}, ${word}`}
      >
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${value >= 0.5 ? "bg-accent-700" : "bg-ink-4"}`}
          style={{ width: `${pct}%` }}
        />
        {[30, 50, 70, 90].map((t) => (
          <span key={t} className="absolute inset-y-0 w-px bg-white" style={{ left: `${t}%` }} aria-hidden="true" />
        ))}
      </div>
      <span className={`tabular-nums text-ink-2 ${compact ? "text-[11px]" : "text-xs"}`}>
        {compact ? value.toFixed(2) : `${word} · ${value.toFixed(2)}`}
      </span>
    </div>
  );
}

/** Small button that opens the Evidence panel for an edge. */
export function EvidenceChip({
  edge,
  label,
  className = "",
}: {
  edge: AtlasEdge;
  label?: string;
  className?: string;
}) {
  const { openEdge } = useEvidence();
  const meta = EVIDENCE_LEVEL_META[edge.evidence_level];
  const style =
    edge.evidence_level === "hypothesis"
      ? "border-dotted border-ink-4"
      : edge.evidence_level === "inferred"
        ? "border-dashed border-ink-4"
        : "border-line";
  return (
    <button
      type="button"
      onClick={() => openEdge(edge.id)}
      className={`inline-flex min-h-[28px] max-w-full items-center gap-1.5 rounded-md border bg-white px-2.5 py-1 text-xs text-ink-2 transition-colors hover:border-accent-500 hover:text-ink ${style} ${className}`}
      title={`Open evidence: ${edge.explanation}`}
    >
      <LevelDot level={edge.evidence_level} />
      <span className="truncate">{label ?? meta?.short ?? edge.evidence_level}</span>
      <span className="tabular-nums text-ink-3">{edge.confidence.toFixed(2)}</span>
      {edge.status === "contested" && (
        <span className="text-warn-ink" aria-label="contested">
          <WarnGlyph size={10} />
        </span>
      )}
    </button>
  );
}

export function LevelDot({ level }: { level: EvidenceLevel }) {
  const cls: Record<EvidenceLevel, string> = {
    clinical: "bg-accent-900",
    curated: "bg-accent-700",
    experimental: "bg-accent-200",
    observational: "bg-accent-100 ring-1 ring-accent-200",
    inferred: "bg-white ring-1 ring-ink-4",
    hypothesis: "bg-white ring-1 ring-ink-4 ring-dashed",
  };
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${cls[level] ?? "bg-ink-4"}`} aria-hidden="true" />;
}

export function EvidenceLegend() {
  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {EVIDENCE_LEVELS.map((l) => (
          <li key={l} className="flex items-start gap-3">
            <span className="w-[124px] shrink-0">
              <EvidenceLevelBadge level={l} size="sm" />
            </span>
            <span className="text-xs leading-relaxed text-ink-3">{EVIDENCE_LEVEL_META[l].legend}</span>
          </li>
        ))}
      </ul>
      <div>
        <p className="mb-1.5 text-xs font-medium text-ink-2">Confidence scale</p>
        <ul className="space-y-1">
          {CONFIDENCE_RUBRIC.map((r, i) => (
            <li key={r.min} className="flex gap-3 text-xs text-ink-3">
              <span className="w-[124px] shrink-0 tabular-nums">
                {i === 0 ? "0.90 – 1.00" : i === CONFIDENCE_RUBRIC.length - 1 ? "below 0.30" : `${r.min.toFixed(2)} – ${(CONFIDENCE_RUBRIC[i - 1].min - 0.01).toFixed(2)}`}
              </span>
              <span>{r.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
