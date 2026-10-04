// /method → "The seven factors": what the atlas compares diseases on, where each comes from, and how it is used.
import Link from "next/link";
import { FACTORS, TESTED_WEIGHTS } from "@/lib/factors";

export function SevenFactors() {
  return (
    <section id="seven-factors" aria-labelledby="seven-factors-h" className="mt-16 scroll-mt-20 border-t border-line pt-9">
      <h2 id="seven-factors-h" className="text-[22px] font-semibold tracking-tight text-ink">
        The seven factors
      </h2>
      <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-ink-2">
        Every disease page shows a fingerprint of the same seven factors, and every list of similar diseases shows how alike they are on each one.
        On the external test only some factors improved the ranking, so the rest are shown as explanations, not counted in the score.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-ink-3">
              <th scope="col" className="py-2 pr-3 font-medium">Factor</th>
              <th scope="col" className="py-2 pr-3 font-medium">Sources</th>
              <th scope="col" className="py-2 font-medium">How it is used</th>
            </tr>
          </thead>
          <tbody>
            {FACTORS.map((f) => (
              <tr key={f.key} className="border-b border-line-2 align-top">
                <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                  {f.label}
                  <span className="block text-xs font-normal text-ink-3">{f.plain}</span>
                </th>
                <td className="py-2 pr-3 text-ink-2">{f.sources}</td>
                <td className="py-2 text-ink-2">
                  {TESTED_WEIGHTS[f.key] ? (
                    <>
                      <b className="font-medium text-ink">Ranking</b>, weight {TESTED_WEIGHTS[f.key]}
                    </>
                  ) : (
                    "Explanation (did not improve ranking)"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-3">
        For the 45 diseases mapped in depth, the factor scores come from a computed comparison of 188 genes and 17,578 pairs (mechanistic similarity:
        AlphaFold structure with TM-align, Pfam, GTEx and HPA, ClinVar spectra, G2P and curated variant evidence). For other diseases they are
        computed from per-gene data.{" "}
        <a href="#primekg-h" className="text-accent-700 underline">
          See the benchmark results
        </a>{" "}
        ·{" "}
        <Link href="/mechanisms" className="text-accent-700 underline">
          Explore all pairs
        </Link>
      </p>
    </section>
  );
}
