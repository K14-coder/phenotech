"use client";

// Explanatory gene factors for a disease page: gnomAD constraint (LOEUF / pLI), the ClinVar mutation spectrum
// and the AlphaMissense mean, each with a plain label. These did NOT improve ranking on the external PrimeKG
// benchmark (docs/agent-reports/ingest.md), so they are shown as explanations only, never as a score.
// Data: public/data/derived/web/factors/<djb2(gene)%64>.json, built by sync-data from data/derived/ingest/;
// labels follow data/derived/global/README.md ("Gene explanatory factors").
import { bucketOfGene } from "@/lib/clinvar";
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";

interface Factor {
  pli: number | null;
  loeuf: number | null;
  misz: number | null;
  am: number | null;
  n: number;
  c: Record<string, number> | null;
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

export function constraintLabel(f: Factor): string | null {
  if (f.loeuf == null && f.pli == null) return null;
  if ((f.loeuf != null && f.loeuf < 0.35) || (f.pli != null && f.pli >= 0.99)) return "very intolerant to losing one copy";
  if ((f.loeuf != null && f.loeuf < 0.6) || (f.pli != null && f.pli >= 0.9)) return "intolerant to losing one copy";
  if (f.loeuf != null && f.loeuf < 1) return "somewhat tolerant of losing one copy";
  return "tolerant of losing one copy";
}
export function amLabel(x: number | null): string | null {
  if (x == null) return null;
  return x >= 0.564 ? "most missense changes predicted damaging" : x >= 0.34 ? "missense changes predicted mixed" : "most missense changes predicted tolerated";
}

async function loadFactors(genes: string[]): Promise<Record<string, Factor>> {
  const a = await loadAvailableOnce();
  if (!a.factors) return {};
  const out: Record<string, Factor> = {};
  const buckets = [...new Set(genes.map(bucketOfGene))];
  const shards = await Promise.all(
    buckets.map((b) =>
      fetch(`/data/derived/web/factors/${b}.json`)
        .then((r) => (r.ok ? (r.json() as Promise<{ d: Record<string, Factor> }>) : null))
        .catch(() => null),
    ),
  );
  for (const g of genes) {
    const s = shards[buckets.indexOf(bucketOfGene(g))];
    if (s?.d[g]) out[g] = s.d[g];
  }
  return out;
}

const loaders = new Map<string, () => Promise<Record<string, Factor>>>();
/** one stable loader per gene list, so the resource effect does not re-run on every render */
function loaderFor(joined: string) {
  let l = loaders.get(joined);
  if (!l) loaders.set(joined, (l = () => loadFactors(joined ? joined.split(",") : [])));
  return l;
}

export function GeneFactors({ genes, compact = false }: { genes: string[]; compact?: boolean }) {
  const joined = genes.filter(Boolean).slice(0, 4).join(",");
  const list = joined ? joined.split(",") : [];
  const key = joined ? `factors:${joined}` : null;
  const data = useResource<Record<string, Factor>>(key, loaderFor(joined))?.data;
  const shown = list.filter((g) => data?.[g]);
  if (!shown.length) return null;
  return (
    <section aria-labelledby="factors-h" className={compact ? "" : "mt-8"}>
      <h2 id="factors-h" className={compact ? "text-[17px] font-semibold text-ink" : "text-[19px] font-semibold text-ink"}>
        What the gene tells us
      </h2>
      <p className="mt-1 text-sm text-ink-3">Explanations, not a score: on 1,300 external test cases these did not improve rankings, so they are shown only to help read the gene.</p>
      <div className={`mt-3 grid gap-3 ${shown.length > 1 ? "md:grid-cols-2" : ""}`}>
        {shown.map((g) => {
          const f = data![g];
          const cl = constraintLabel(f);
          const al = amLabel(f.am);
          const total = f.c ? Object.values(f.c).reduce((a, b) => a + b, 0) : 0;
          return (
            <div key={g} className="min-w-0 rounded-lg border border-line px-4 py-3 text-sm">
              <p className="font-mono text-[15px] font-semibold text-ink">{g}</p>
              <dl className="mt-2 space-y-2.5">
                {cl && (
                  <div>
                    <dt className="text-xs font-medium text-ink-3">In the general population (gnomAD v4.1)</dt>
                    <dd className="text-ink">
                      {cl[0].toUpperCase() + cl.slice(1)}
                      <span className="text-ink-3">
                        {" "}
                        · LOEUF {f.loeuf ?? "–"}, pLI {f.pli ?? "–"}
                      </span>
                    </dd>
                  </div>
                )}
                {total > 0 && f.c && (
                  <div>
                    <dt className="text-xs font-medium text-ink-3">Disease-causing changes in ClinVar ({f.n.toLocaleString("en")})</dt>
                    <dd>
                      <div className="mt-1 flex h-2.5 w-full overflow-hidden rounded-full bg-subtle" role="img" aria-label={SPEC.filter(([k]) => f.c![k]).map(([k, l]) => `${l} ${Math.round((100 * f.c![k]) / total)}%`).join(", ")}>
                        {SPEC.filter(([k]) => f.c![k]).map(([k, l, col]) => (
                          <span key={k} title={`${l}: ${f.c![k]}`} style={{ width: `${(100 * f.c![k]) / total}%`, background: col }} />
                        ))}
                      </div>
                      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-3">
                        {SPEC.filter(([k]) => f.c![k] && f.c![k] / total >= 0.03).map(([k, l, col]) => (
                          <li key={k} className="inline-flex items-center gap-1">
                            <span className="h-2 w-2 rounded-full" style={{ background: col }} aria-hidden="true" />
                            {l} {Math.round((100 * f.c![k]) / total)}%
                          </li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                )}
                {al && (
                  <div>
                    <dt className="text-xs font-medium text-ink-3">Predicted effect of missense changes (AlphaMissense)</dt>
                    <dd className="text-ink">
                      {al[0].toUpperCase() + al.slice(1)}
                      <span className="text-ink-3"> · mean {f.am}</span>
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-ink-3">Sources: gnomAD v4.1 constraint, ClinVar pathogenic / likely pathogenic (2026-09-29), AlphaMissense (Cheng et al. 2023).</p>
    </section>
  );
}
