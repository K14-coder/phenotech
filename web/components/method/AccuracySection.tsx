"use client";

// /method → "How well does it work?": the accuracy evaluation from data/derived/eval.json
// (pipeline/eval/transfer_eval.py; write-up in docs/agent-reports/eval.md). Numbers are read from the
// file, so they follow every re-run; the section is left out when the file is not in this build.
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";

interface Metrics {
  n: number;
  "recall@1": number;
  "recall@3"?: number;
  "recall@5": number;
  mrr: number;
  median_rank: number;
  ci95?: Record<string, [number, number]>;
}
interface Loo {
  held_out: string;
  n_candidates: number;
  rank: Record<string, number>;
}
interface Check {
  therapy: string;
  known: string[];
  leave_one_out: Loo[];
  seed_only?: { seed: string; n_candidates: number; ranks_of_other_known: Record<string, number> };
}
export interface EvalFile {
  connectivity: {
    components: { giant_share: number; diseases_in_giant: number; diseases: number };
    mechanism_links: { diseases: number; specific_mechanism: number; specific_mechanism_cross_family: number; share_pairs_generic: number };
    counter_evidence: { edges_with_counter_evidence: number; share: number };
  };
  transfer_benchmark: {
    design: { n_cases_main: number; n_therapy_classes: number; n_cases_with_context: number };
    results: Record<"all_developed_for" | "transfer_context_nonempty", Record<string, Metrics>>;
    recommended_scorer: string;
  };
  known_collaboration_checks: Record<string, Check>;
  agreement: {
    openai_cross_check: { agree: number; pairs_both_cite: number; share: number; scope: string };
    claude_cross_check?: { agree: number; pairs_both_cite: number; share: number; abstracts: number; scope: string };
    quote_verification: { verified: number; with_quote: number };
    dismech: { primary_mechanism_class_agrees: string; deep_compared: string[] };
    g2p_clingen_mechanism_class?: { available: boolean; diseases_with_external_class: number; agree_strict: number; agree_lenient: number };
  };
}

const EVAL_URL = "/data/derived/eval.json";

async function loadEval(): Promise<EvalFile | null> {
  const a = await loadAvailableOnce();
  if (!a.eval) return null;
  const r = await fetch(EVAL_URL);
  return r.ok ? ((await r.json()) as EvalFile) : null;
}

const P = (x: number) => `${Math.round(x * 100)}%`;
const ord = (n: number) => {
  const r = Math.round(n);
  const s = r % 100 >= 11 && r % 100 <= 13 ? "th" : (["th", "st", "nd", "rd"][r % 10] ?? "th");
  return `${r}${s}`;
};

/** Scorers shown in the table, in plain words (keys as in eval.json). */
const ROWS: [string, string][] = [
  ["random", "Random guess"],
  ["phenotype", "Similar symptoms"],
  ["mechanism", "Shared specific mechanism"],
  ["pheno+mech", "Symptoms + mechanism"],
  ["mech+cluster", "Mechanism + curated cluster"],
  ["combined", "Symptoms + mechanism + cluster"],
  ["same-family", "Same disease family (baseline)"],
  ["hypotheses-rule", "Rule behind today’s ideas page"],
];

function range(ranks: number[]) {
  const lo = Math.min(...ranks);
  const hi = Math.max(...ranks);
  return lo === hi ? ord(lo) : `${ord(lo)} to ${ord(hi)}`;
}

export function AccuracySection() {
  const r = useResource<EvalFile | null>("method:eval", loadEval);
  const e = r?.data;
  if (!e) return null;
  const best = e.transfer_benchmark.recommended_scorer;
  const all = e.transfer_benchmark.results.all_developed_for;
  const ctx = e.transfer_benchmark.results.transfer_context_nonempty;
  const m = all[best];
  const rnd = all.random;
  const t = ctx[best];
  const d = e.transfer_benchmark.design;
  const c = e.connectivity;
  const ai = e.agreement.openai_cross_check;
  if (!m || !rnd || !t) return null;

  const checks = Object.entries(e.known_collaboration_checks).filter(([k]) => !/ablation/i.test(k));
  const ablation = Object.entries(e.known_collaboration_checks).find(([k]) => /phenylbutyrate/i.test(k) && /ablation/i.test(k))?.[1];
  const pba = checks.find(([k]) => /phenylbutyrate/i.test(k))?.[1];
  const mek = checks.find(([k]) => /MEK/i.test(k))?.[1];
  const mig = checks.find(([k]) => /miglustat/i.test(k))?.[1];
  const rk = (x: Loo) => x.rank[best];

  const tiles = [
    { big: P(m["recall@5"]), label: "hidden disease in the top 5", body: `Out of ${d.n_cases_main} tests. Random guessing: ${P(rnd["recall@5"])}.` },
    { big: P(m["recall@1"]), label: "hidden disease ranked first", body: `Random guessing: ${P(rnd["recall@1"])}.` },
    { big: P(t["recall@5"]), label: "in the top 5 when the therapy already helps another disease", body: `${t.n} of the tests.` },
    { big: `${ai.agree} / ${ai.pairs_both_cite}`, label: "readings agree with an independent AI", body: `${P(ai.share)}. One disease family, abstracts only.` },
  ];

  const summary = [
    `The atlas links all ${c.components.diseases_in_giant} diseases in one network. Many of those links run through broad labels such as “loss of function”, which about ${Math.round(c.mechanism_links.share_pairs_generic * 10)} in 10 disease pairs share. Through specific biology, ${c.mechanism_links.specific_mechanism} of ${c.mechanism_links.diseases} diseases connect to another disease, and only ${c.mechanism_links.specific_mechanism_cross_family} connect to a disease in a different family.`,
    `To test whether the atlas can spot how progress on one disease could help another, we hid each of ${d.n_cases_main} known therapy–disease links, one at a time, and asked it to rank all ${c.components.diseases} diseases for that therapy.`,
    `Combining shared symptoms with shared specific mechanisms, it put the hidden disease first in ${P(m["recall@1"])} of tests and in its top 5 in ${P(m["recall@5"])} (random guessing: ${P(rnd["recall@1"])} and ${P(rnd["recall@5"])}). When the therapy already had another known disease to learn from, the top-5 rate rose to ${P(t["recall@5"])}.`,
    "It recovered real cross-disease connections: 4-phenylbutyrate between STXBP1 and SLC6A1 in both directions, MEK inhibitors across the RASopathies, and miglustat within the lysosomal diseases, though less sharply. But the test is small, and the same literature built both the graph and the test, so read a high rank as a reason to look, not as proof.",
    `Every link shows its sources: ${(c.counter_evidence.share * 100).toFixed(1)}% of links carry contradicting evidence, shown rather than hidden, and an independent AI re-reading of the same papers agreed with the curators on ${ai.agree} of ${ai.pairs_both_cite} (${P(ai.share)}) readings of the same paper and link.`,
  ];

  const known: { name: string; body: string }[] = [];
  if (pba?.leave_one_out.length) {
    const [a, b] = pba.leave_one_out;
    known.push({
      name: "4-phenylbutyrate",
      body: b
        ? `Hidden ${a.held_out} comes back ${ord(rk(a))} of ${a.n_candidates}, and hidden ${b.held_out} ${ord(rk(b))} of ${b.n_candidates}.${ablation?.leave_one_out.length && ablation.leave_one_out.every((x) => rk(x) === rk(a)) ? " Removing the target that was curated from the SLC6A1 work changes nothing." : ""}`
        : `Hidden ${a.held_out} comes back ${ord(rk(a))} of ${a.n_candidates}.`,
    });
  }
  if (mek?.leave_one_out.length) {
    const lz = mek.seed_only?.ranks_of_other_known.LZTR1;
    known.push({
      name: "MEK inhibitors (RASopathies)",
      body: `Each hidden RASopathy ranks ${range(mek.leave_one_out.map(rk))} of ${mek.leave_one_out[0].n_candidates}; the diseases above it are RASopathies not yet tried.${lz ? ` Starting from NF1 alone, LZTR1 ranks ${ord(lz)}: the graph lacks the RAS → MAPK link.` : ""}`,
    });
  }
  if (mig?.leave_one_out.length)
    known.push({
      name: "Miglustat (lysosomal)",
      body: `Each hidden lysosomal disease ranks ${range(mig.leave_one_out.map(rk))} of about ${mig.leave_one_out[0].n_candidates}: the family is found, the order within it is weak.`,
    });

  const g2p = e.agreement.g2p_clingen_mechanism_class;

  return (
    <section aria-labelledby="accuracy-h" className="mt-16 border-t border-line pt-9">
      <h2 id="accuracy-h" className="text-[22px] font-semibold tracking-tight text-ink">
        How well does it work?
      </h2>
      <p className="mt-2 max-w-[720px] text-[15px] leading-relaxed text-ink-2">
        We hid each of {d.n_cases_main} known therapy–disease links, one at a time, and asked the atlas to rank all {c.components.diseases} diseases for that
        therapy. A good atlas puts the hidden disease near the top.
      </p>

      <div className="mt-7 grid grid-cols-1 gap-x-10 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((x) => (
          <div key={x.label}>
            <p className="text-[34px] font-semibold leading-none tracking-tight tabular-nums text-ink">{x.big}</p>
            <p className="mt-2 text-sm font-medium text-ink">{x.label}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-3">{x.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <h3 className="text-[16px] font-semibold text-ink">In plain words</h3>
          <ol className="mt-3 space-y-3">
            {summary.map((s, i) => (
              <li key={i} className="grid grid-cols-[22px_minmax(0,1fr)] gap-1 text-sm leading-relaxed text-ink-2">
                <span className="tabular-nums text-ink-3">{i + 1}</span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="min-w-0">
          <h3 className="text-[16px] font-semibold text-ink">Ways of ranking, compared</h3>
          <p className="mt-1 text-sm text-ink-3">All {m.n} tests. Higher is better. The 95% range for the best method is shown under each figure.</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[300px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-3">
                  <th scope="col" className="py-2 pr-2 font-medium">
                    Method
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Top 1
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Top 5
                  </th>
                  <th scope="col" className="py-2 pl-2 text-right font-medium" title="Mean reciprocal rank: 1 means always first">
                    MRR
                  </th>
                </tr>
              </thead>
              <tbody>
                {ROWS.filter(([k]) => all[k]).map(([k, label]) => {
                  const x = all[k];
                  const top = k === best;
                  const ci = (f: string) => (top && x.ci95?.[f] ? <span className="block text-[11px] font-normal text-ink-3">{`${P(x.ci95[f][0])}–${P(x.ci95[f][1])}`}</span> : null);
                  return (
                    <tr key={k} className={`border-b border-line-2 align-top ${top ? "bg-accent-50 font-semibold text-ink" : "text-ink-2"}`}>
                      <th scope="row" className={`py-2 pr-2 text-left ${top ? "font-semibold" : "font-normal"}`}>
                        {label}
                        {top && <span className="block text-[11px] font-normal text-accent-700">best honest method</span>}
                      </th>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {P(x["recall@1"])}
                        {ci("recall@1")}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {P(x["recall@5"])}
                        {ci("recall@5")}
                      </td>
                      <td className="py-2 pl-2 text-right tabular-nums">
                        {x.mrr.toFixed(2)}
                        {top && x.ci95?.mrr ? <span className="block text-[11px] font-normal text-ink-3">{`${x.ci95.mrr[0].toFixed(2)}–${x.ci95.mrr[1].toFixed(2)}`}</span> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-ink-3">
            A rank orders candidates; it is not a probability. Curated clusters that list a therapy are left out of every honest method, because they
            partly contain the answer.
          </p>
        </div>
      </div>

      <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {known.length > 0 && (
          <div>
            <h3 className="text-[16px] font-semibold text-ink">Does it find connections we already know?</h3>
            <dl className="mt-3 space-y-3 text-sm leading-relaxed">
              {known.map((k) => (
                <div key={k.name}>
                  <dt className="font-medium text-ink">{k.name}</dt>
                  <dd className="text-ink-2">{k.body}</dd>
                </div>
              ))}
            </dl>
            <h3 className="mt-8 text-[16px] font-semibold text-ink">Agreement with other sources</h3>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-ink-2">
              <li>
                Independent AI re-reading (OpenAI): {ai.agree} of {ai.pairs_both_cite} readings agree ({P(ai.share)}). One disease family, one model, abstracts only.
              </li>
              {e.agreement.claude_cross_check && (
                <li>
                  Independent AI re-reading (Claude), the other three families: {e.agreement.claude_cross_check.agree} of {e.agreement.claude_cross_check.pairs_both_cite} readings agree ({P(e.agreement.claude_cross_check.share)}), over {e.agreement.claude_cross_check.abstracts} abstracts. Read blind to the curation, but parts of the atlas were curated with Claude, so this is weaker evidence than agreement between different models.
                </li>
              )}
              {g2p?.available && (
                <li>
                  Disease mechanism class vs G2P and ClinGen: {g2p.agree_lenient} of {g2p.diseases_with_external_class} agree broadly, {g2p.agree_strict} exactly.
                </li>
              )}
              <li>
                DisMech (Monarch): the main mechanism agrees for {e.agreement.dismech.primary_mechanism_class_agrees} diseases compared in depth ({e.agreement.dismech.deep_compared.join(", ")}). A
                qualitative check, not a rate.
              </li>
              <li>
                Quotes checked word for word: {e.agreement.quote_verification.verified.toLocaleString("en")} of {e.agreement.quote_verification.with_quote.toLocaleString("en")}.
              </li>
            </ul>
          </div>
        )}
        <div>
          <h3 className="text-[16px] font-semibold text-ink">Limitations</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-ink-2">
            <li>
              <span className="font-medium text-ink">A small test.</span> {d.n_cases_main} cases from {d.n_therapy_classes} therapy classes, so the ranges are wide and one drug
              class can move the averages.
            </li>
            <li>
              <span className="font-medium text-ink">Partly circular.</span> The same curators built the mechanism links, clusters and therapy links from overlapping papers.
            </li>
            <li>
              <span className="font-medium text-ink">Unknowns count as misses.</span> A disease ranked above the hidden one may be an untested opportunity, not an error.
            </li>
            <li>
              <span className="font-medium text-ink">A small world.</span> {c.components.diseases} diseases in 4 families is much easier than searching every rare disease.
            </li>
            <li>
              <span className="font-medium text-ink">Coarse inputs.</span> About 20 symptom terms per disease and a short list of mechanisms, with no RAS → MAPK hierarchy.
            </li>
            <li>
              <span className="font-medium text-ink">Chosen after the fact.</span> The best method was picked over a pre-declared one that scored the same within noise.
            </li>
          </ul>
          <p className="mt-4 text-xs leading-relaxed text-ink-3">
            Method: leave-one-out over therapy classes, ties scored at their expected value, 95% ranges by bootstrap over therapy classes.{" "}
            <a href={EVAL_URL} className="text-accent-700 underline" target="_blank" rel="noopener noreferrer">
              Full results (JSON)
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
