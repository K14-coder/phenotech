"use client";

// Small shared pieces of the seven-factor view: the 7-segment bar and the fingerprint table.
import { FACTORS, type FactorKey, type FactorScores } from "@/lib/factors";

export const FACTOR_COLOR: Record<FactorKey, string> = {
  gene: "#1f5a96",
  pathway: "#7a5ea8",
  tissue: "#2a7a4b",
  symptoms: "#C27C3A",
  structure: "#3e6ea5",
  mutation: "#b07a22",
  fate: "#a8455e",
};

/** One segment per factor, in the fixed order; the fill shows that factor's similarity, grey = no data. */
export function FactorBar({ scores, size = "md" }: { scores: FactorScores; size?: "sm" | "md" }) {
  const h = size === "md" ? "h-3" : "h-2";
  const label = FACTORS.map((f) => `${f.label}: ${scores[f.key] == null ? "no data" : `${Math.round((scores[f.key] as number) * 100)}%`}`).join(", ");
  return (
    <div className="flex items-center gap-[3px]" role="img" aria-label={`Similarity by factor. ${label}`}>
      {FACTORS.map((f) => {
        const v = scores[f.key];
        return (
          <span
            key={f.key}
            title={`${f.label}: ${v == null ? "no data" : `${Math.round(v * 100)}%`}`}
            className={`relative ${h} w-6 overflow-hidden rounded-sm ${v == null ? "bg-[repeating-linear-gradient(45deg,#eceef1,#eceef1_3px,#f7f8f9_3px,#f7f8f9_6px)]" : "bg-subtle"} sm:w-7`}
          >
            {v != null && <span className="absolute inset-y-0 left-0" style={{ width: `${Math.max(4, Math.min(100, v * 100))}%`, background: FACTOR_COLOR[f.key] }} />}
          </span>
        );
      })}
    </div>
  );
}

export function FactorLegend() {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-3" aria-label="Factor colours">
      {FACTORS.map((f) => (
        <li key={f.key} className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-sm" style={{ background: FACTOR_COLOR[f.key] }} aria-hidden="true" />
          {f.short}
        </li>
      ))}
      <li className="inline-flex items-center gap-1">
        <span className="h-2 w-2 rounded-sm bg-[repeating-linear-gradient(45deg,#d9dce1,#d9dce1_2px,#f7f8f9_2px,#f7f8f9_4px)]" aria-hidden="true" />
        no data
      </li>
    </ul>
  );
}

export interface FingerprintRow {
  key: FactorKey;
  /** full detail (Research / Industry) */
  value: React.ReactNode;
  /** plain one-liner (Simple) */
  plain: string;
  source?: { label: string; url: string } | null;
}

/** The seven labelled rows, always in the same order. `plain` renders the Simple one-liners with "What does this mean?". */
export function FingerprintTable({ rows, plain = false, open = true, title = "Disease fingerprint" }: { rows: FingerprintRow[]; plain?: boolean; open?: boolean; title?: string }) {
  const byKey = new Map(rows.map((r) => [r.key, r]));
  const body = (
    <dl className={plain ? "mt-3 space-y-3" : "mt-3 divide-y divide-line-2 border-y border-line-2"}>
      {FACTORS.map((f) => {
        const r = byKey.get(f.key);
        if (plain)
          return (
            <div key={f.key}>
              <dt className="text-[15px] font-medium text-ink">
                <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: FACTOR_COLOR[f.key] }} aria-hidden="true" />
                {f.label}
              </dt>
              <dd className="mt-0.5 text-[15px] leading-relaxed text-ink-2">{r?.plain ?? "Not known yet."}</dd>
              <details className="mt-0.5 text-sm text-ink-3">
                <summary className="cursor-pointer select-none hover:text-ink">What does this mean?</summary>
                <p className="mt-1">{f.plain}</p>
              </details>
            </div>
          );
        return (
          <div key={f.key} className="grid grid-cols-1 gap-1 py-2.5 sm:grid-cols-[190px_minmax(0,1fr)] sm:gap-4">
            <dt className="flex items-start gap-2 text-sm font-medium text-ink">
              <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: FACTOR_COLOR[f.key] }} aria-hidden="true" />
              <span title={f.plain}>{f.label}</span>
            </dt>
            <dd className="min-w-0 text-sm text-ink-2 [overflow-wrap:anywhere]">
              {r ? r.value : <span className="text-ink-3">No data yet.</span>}
              {r?.source && (
                <a href={r.source.url} target="_blank" rel="noopener noreferrer" className="ml-2 whitespace-nowrap text-xs text-accent-700 hover:underline">
                  {r.source.label} ↗
                </a>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
  return (
    <section aria-label={title} className="max-w-[860px]">
      {plain ? (
        <>
          <h3 className="text-[18px] font-semibold text-ink">{title}</h3>
          <p className="mt-1 text-sm text-ink-3">The seven things the atlas compares diseases on, in plain words.</p>
          {body}
        </>
      ) : (
        <details open={open} className="group">
          <summary className="cursor-pointer list-none">
            <span className="text-[19px] font-semibold text-ink">{title}</span>
            <span className="ml-2 text-sm text-ink-3 group-open:hidden">· show the seven factors</span>
            <p className="mt-1 text-sm text-ink-3">The seven factors the atlas compares diseases on. Symptoms, genes and pathways drive the ranking; the rest explain it.</p>
          </summary>
          {body}
        </details>
      )}
    </section>
  );
}

const SPEC: [string, string, string][] = [
  ["nonsense", "Early stop", "#7f520f"],
  ["frameshift", "Frameshift", "#b07a22"],
  ["splice", "Splice", "#d9a84e"],
  ["missense", "Missense", "#1f5a96"],
  ["inframe", "In-frame", "#6f97c4"],
  ["cnv", "Deletion / duplication", "#5f6672"],
  ["other", "Other", "#c4c9d0"],
];

export function SpectrumMini({ c, n }: { c: Record<string, number>; n: number }) {
  const total = Object.values(c).reduce((a, b) => a + b, 0) || 1;
  const parts = SPEC.filter(([k]) => c[k]);
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="inline-flex h-2.5 w-36 overflow-hidden rounded-full bg-subtle" role="img" aria-label={parts.map(([k, l]) => `${l} ${Math.round((100 * c[k]) / total)}%`).join(", ")}>
        {parts.map(([k, l, col]) => (
          <span key={k} title={`${l}: ${c[k]}`} style={{ width: `${(100 * c[k]) / total}%`, background: col }} />
        ))}
      </span>
      <span className="text-xs text-ink-3">
        {parts
          .filter(([k]) => c[k] / total >= 0.12)
          .map(([k, l]) => `${l} ${Math.round((100 * c[k]) / total)}%`)
          .join(" · ")}{" "}
        ({n.toLocaleString("en")} in ClinVar)
      </span>
    </span>
  );
}

export const topSpectrumWords = (c: Record<string, number> | null | undefined): string | null => {
  if (!c) return null;
  const total = Object.values(c).reduce((a, b) => a + b, 0);
  if (!total) return null;
  const words: Record<string, string> = { nonsense: "early stops", frameshift: "frameshifts", splice: "splice changes", missense: "single building-block swaps", inframe: "small in-frame changes", cnv: "deletions or duplications", other: "other changes" };
  const top = Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 2);
  return top.map(([k, v]) => `${words[k] ?? k} (${Math.round((100 * v) / total)}%)`).join(" and ");
};
