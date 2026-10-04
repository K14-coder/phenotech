"use client";

// /method → "Tested on 1,300 external cases": the PrimeKG therapy-transfer benchmark
// (data/derived/ingest/primekg_eval.json; write-up in docs/agent-reports/ingest.md). For each drug with two or more
// rare-disease indications in PrimeKG, one indication is hidden and the others must find it among 256 diseases.
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";

interface Res {
  rr: number;
  rr_ci?: [number, number];
  "r@5": number;
  median_rank?: number | null;
}
interface PrimeKgEval {
  benchmark: { cases: number; benchmark_drugs: number; candidate_pool: number };
  results: Record<string, Res>;
  no_shared_gene_cases: number;
  no_shared_gene_mrr: Record<string, { rr: number }>;
}

async function loadPrimeKg(): Promise<PrimeKgEval | null> {
  const a = await loadAvailableOnce();
  if (!a.primekg_eval) return null;
  const r = await fetch("/data/derived/ingest/primekg_eval.json");
  return r.ok ? ((await r.json()) as PrimeKgEval) : null;
}

const ROWS: [string, string, "signal" | "little" | "explain"][] = [
  ["phenotype", "Shared symptoms", "signal"],
  ["genes", "Same gene", "little"],
  ["pathway_full", "Shared pathways (Reactome)", "little"],
  ["gene_family", "Same gene family", "little"],
  ["protein_domain", "Shared protein domain", "little"],
  ["tissue", "Tissue where the gene is active", "explain"],
  ["mutation_spectrum", "Mutation type (ClinVar)", "explain"],
  ["constraint", "Gene constraint (gnomAD)", "explain"],
  ["alphamissense", "AlphaMissense", "explain"],
  ["structure_tm", "Protein structure", "explain"],
];
const TAG = { signal: "carries the signal", little: "helps a little", explain: "shown as explanation" };
const f2 = (x?: number) => (x == null ? "–" : x.toFixed(2));
const pct = (x?: number) => (x == null ? "–" : `${Math.round(x * 100)}%`);

export function PrimeKgSection() {
  const e = useResource<PrimeKgEval | null>("method:primekg", loadPrimeKg)?.data;
  if (!e) return null;
  const R = e.results;
  const best = R.nested_anchored;
  const ph = R["single:phenotype"];
  const rnd = R.random;
  if (!best || !ph || !rnd) return null;
  return (
    <section aria-labelledby="primekg-h" className="mt-16 border-t border-line pt-9">
      <h2 id="primekg-h" className="text-[22px] font-semibold tracking-tight text-ink">
        Tested on {e.benchmark.cases.toLocaleString("en")} external cases
      </h2>
      <p className="mt-2 max-w-[720px] text-[15px] leading-relaxed text-ink-2">
        PrimeKG, a public knowledge graph built by others, lists {e.benchmark.benchmark_drugs} drugs approved for two or more rare diseases. For each one we hid one
        disease and asked: using the others, can we find it among {e.benchmark.candidate_pool} diseases? Nothing in this test came from the atlas’s own curation.
      </p>
      <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-6 sm:grid-cols-3">
        {[
          { big: f2(best.rr), label: "score of the method the site uses", body: `Symptoms, plus same gene and shared pathways. 1 means always first.` },
          { big: f2(ph.rr), label: "symptoms alone", body: `Random guessing: ${f2(rnd.rr)}.` },
          { big: pct(best["r@5"]), label: "hidden disease in the top 5", body: `Symptoms alone: ${pct(ph["r@5"])}.` },
        ].map((t) => (
          <div key={t.label}>
            <p className="text-[34px] font-semibold leading-none tracking-tight tabular-nums text-ink">{t.big}</p>
            <p className="mt-2 text-sm font-medium text-ink">{t.label}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-3">{t.body}</p>
          </div>
        ))}
      </div>
      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <h3 className="text-[16px] font-semibold text-ink">Each factor on its own</h3>
          <p className="mt-1 text-sm text-ink-3">Mean reciprocal rank (MRR). The last column uses only the {e.no_shared_gene_cases} cases where the diseases share no gene.</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[320px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-3">
                  <th scope="col" className="py-2 pr-2 font-medium">Factor</th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">MRR</th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">Top 5</th>
                  <th scope="col" className="py-2 pl-2 text-right font-medium">No shared gene</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.filter(([k]) => R[`single:${k}`]).map(([k, label, tag]) => (
                  <tr key={k} className={`border-b border-line-2 align-top ${tag === "signal" ? "bg-accent-50 font-semibold text-ink" : "text-ink-2"}`}>
                    <th scope="row" className={`py-2 pr-2 text-left ${tag === "signal" ? "font-semibold" : "font-normal"}`}>
                      {label}
                      <span className={`block text-[11px] font-normal ${tag === "explain" ? "text-ink-3" : "text-accent-700"}`}>{TAG[tag]}</span>
                    </th>
                    <td className="px-2 py-2 text-right tabular-nums">{f2(R[`single:${k}`].rr)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{pct(R[`single:${k}`]["r@5"])}</td>
                    <td className="py-2 pl-2 text-right tabular-nums">{f2(e.no_shared_gene_mrr[`single:${k}`]?.rr)}</td>
                  </tr>
                ))}
                <tr className="text-ink-3">
                  <th scope="row" className="py-2 pr-2 text-left font-normal">Random guess</th>
                  <td className="px-2 py-2 text-right tabular-nums">{f2(rnd.rr)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{pct(rnd["r@5"])}</td>
                  <td className="py-2 pl-2 text-right tabular-nums">{f2(e.no_shared_gene_mrr.random?.rr)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="text-[16px] font-semibold text-ink">What it means</h3>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed text-ink-2">
            <li>
              <b className="font-medium text-ink">Symptoms carry the signal across genes.</b> When the diseases share no gene, symptoms still score {f2(e.no_shared_gene_mrr["single:phenotype"]?.rr)}; every other factor falls close to random.
            </li>
            <li>
              <b className="font-medium text-ink">Same gene and shared pathways help a little.</b> Adding them to symptoms raised the score from {f2(ph.rr)} to {f2(best.rr)}, so “Diseases most similar to this one” uses this combination and names the reason for each.
            </li>
            <li>
              <b className="font-medium text-ink">The rest didn’t improve ranking.</b> Tissue, mutation type, gene constraint, AlphaMissense and protein structure did not help, so we show them on disease pages as explanations, not as a score.
            </li>
            <li className="text-ink-3">
              Limits: approved uses are a narrow test of “similar”, and a hidden disease can rank low for reasons a doctor would see at once. Ranges and the full tables are in
              the JSON.{" "}
              <a href="/data/derived/ingest/primekg_eval.json" target="_blank" rel="noopener noreferrer" className="text-accent-700 underline">
                Full results (JSON)
              </a>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
