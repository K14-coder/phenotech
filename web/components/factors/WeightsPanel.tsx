"use client";

// Research view, atlas: seven sliders that re-weight the factors and re-rank the closest diseases live.
// Defaults are the combination tested on 1,300 external PrimeKG cases (symptoms 1, genes 0.5, pathway 0.5;
// the other factors explain but did not improve ranking, so they start at 0).
import Link from "next/link";
import { useMemo, useState } from "react";
import { FACTORS, TESTED_WEIGHTS, mechsimScores, weighted, type FactorKey } from "@/lib/factors";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { FACTOR_COLOR, FactorBar } from "./FactorBits";
import { useMechsim } from "./PairFactors";

export function WeightsPanel({ idx, diseaseId }: { idx: GraphIndex; diseaseId: string | null }) {
  const ix = useMechsim();
  const [w, setW] = useState<Record<FactorKey, number>>(TESTED_WEIGHTS);
  const diseases = useMemo(() => idx.graph.nodes.filter((n) => n.type === "disease"), [idx]);
  const target = diseaseId && idx.nodeById.get(diseaseId)?.type === "disease" ? diseaseId : "disease:STXBP1";
  const ranked = useMemo(() => {
    if (!ix) return [];
    return diseases
      .filter((d) => d.id !== target)
      .map((d) => ({ d, s: mechsimScores(ix, target, d.id, idx) }))
      .filter((x): x is { d: (typeof diseases)[number]; s: NonNullable<typeof x.s> } => !!x.s)
      .map((x) => ({ ...x, score: weighted(x.s, w) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 6);
  }, [ix, diseases, target, w, idx]);
  const isDefault = FACTORS.every((f) => w[f.key] === TESTED_WEIGHTS[f.key]);
  return (
    <section aria-labelledby="weights-h" className="mt-7">
      <h2 id="weights-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
        Weights
      </h2>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-3">
        Closest to <span className="font-medium text-ink">{idx.nodeById.get(target)?.label.split(" (")[0]}</span> (select a disease to change).
      </p>
      <div className="mt-2 space-y-1.5">
        {FACTORS.map((f) => (
          <label key={f.key} className="grid grid-cols-[86px_minmax(0,1fr)_26px] items-center gap-2 text-xs text-ink-2">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: FACTOR_COLOR[f.key] }} aria-hidden="true" />
              {f.short}
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.25}
              value={w[f.key]}
              onChange={(e) => setW((o) => ({ ...o, [f.key]: Number(e.target.value) }))}
              aria-label={`Weight for ${f.label}`}
              className="w-full accent-[#1f5a96]"
            />
            <span className="text-right tabular-nums">{w[f.key]}</span>
          </label>
        ))}
      </div>
      <button
        type="button"
        disabled={isDefault}
        onClick={() => setW(TESTED_WEIGHTS)}
        className="mt-2 rounded-md border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-accent-500 disabled:opacity-50"
      >
        Reset to tested defaults
      </button>
      <ol className="mt-3 space-y-2">
        {ranked.map((r, i) => (
          <li key={r.d.id} className="text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <Link href={diseaseHref(r.d.id)} className="min-w-0 truncate font-medium text-ink hover:text-accent-700">
                {i + 1}. {r.d.label.split(" (")[0]}
              </Link>
              <span className="shrink-0 tabular-nums text-ink-3">{r.score.toFixed(2)}</span>
            </div>
            <div className="mt-1">
              <FactorBar scores={r.s} size="sm" />
            </div>
          </li>
        ))}
        {!ix && <li className="text-xs text-ink-3">Loading the factor comparison…</li>}
      </ol>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
        Tested on 1,300 external cases: symptoms carry most of the signal; the other factors refine and explain. Defaults: symptoms 1, genes 0.5,
        pathway 0.5, others 0.{" "}
        <Link href="/method#seven-factors" className="underline">
          Method
        </Link>
      </p>
    </section>
  );
}
