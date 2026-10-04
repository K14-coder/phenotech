"use client";

// /compare → "Seven factors side by side": each factor's value for both diseases and how alike they are on it.
import { FACTORS, mechsimScores, type FactorScores } from "@/lib/factors";
import type { GraphIndex } from "@/lib/graph";
import { FACTOR_COLOR, FactorBar, FactorLegend } from "./FactorBits";
import { useAtlasRows } from "./Fingerprint";
import { pairWords, useMechsim } from "./PairFactors";

export function CompareFactors({ idx, a, b }: { idx: GraphIndex; a: string; b: string }) {
  const na = idx.nodeById.get(a)!;
  const nb = idx.nodeById.get(b)!;
  const ra = useAtlasRows(idx, na);
  const rb = useAtlasRows(idx, nb);
  const ix = useMechsim();
  const scores: FactorScores | null = ix ? mechsimScores(ix, a, b, idx) : null;
  const words = ix ? pairWords(ix, a, b) : {};
  const ma = new Map(ra.map((r) => [r.key, r]));
  const mb = new Map(rb.map((r) => [r.key, r]));
  const short = (n: typeof na) => n.label.split(" (")[0];
  return (
    <section aria-labelledby="seven-h" className="mt-8">
      <h2 id="seven-h" className="text-[22px] font-semibold tracking-tight text-ink">
        Seven factors side by side
      </h2>
      <p className="mt-1 text-sm text-ink-3">
        How {short(na)} and {short(nb)} compare on each factor the atlas uses. The middle column shows how alike they are (grey stripes = no data).
      </p>
      {scores && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <FactorBar scores={scores} />
          <FactorLegend />
        </div>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-3">
              <th scope="col" className="w-[170px] py-2 pr-3 font-medium">Factor</th>
              <th scope="col" className="py-2 pr-3 font-medium">{short(na)}</th>
              <th scope="col" className="w-[120px] px-2 py-2 text-center font-medium">Alike</th>
              <th scope="col" className="py-2 pl-3 font-medium">{short(nb)}</th>
            </tr>
          </thead>
          <tbody>
            {FACTORS.map((f) => {
              const v = scores?.[f.key] ?? null;
              return (
                <tr key={f.key} className="border-b border-line-2 align-top">
                  <th scope="row" className="py-2.5 pr-3 text-left font-medium text-ink">
                    <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: FACTOR_COLOR[f.key] }} aria-hidden="true" />
                    {f.label}
                  </th>
                  <td className="min-w-0 py-2.5 pr-3 text-ink-2 [overflow-wrap:anywhere]">{ma.get(f.key)?.value ?? <span className="text-ink-3">No data</span>}</td>
                  <td className="px-2 py-2.5 text-center">
                    {v == null ? (
                      <span className="text-xs text-ink-3">no data</span>
                    ) : (
                      <>
                        <span className="block text-[15px] font-semibold tabular-nums text-ink">{Math.round(v * 100)}%</span>
                        {words[f.key] && <span className="block text-[11px] leading-snug text-ink-3">{words[f.key]}</span>}
                      </>
                    )}
                  </td>
                  <td className="min-w-0 py-2.5 pl-3 text-ink-2 [overflow-wrap:anywhere]">{mb.get(f.key)?.value ?? <span className="text-ink-3">No data</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-3">Similarities from the mechanistic comparison (pipeline/derive/mechsim.py); symptoms are the information-weighted overlap of the curated HPO symptoms.</p>
    </section>
  );
}
