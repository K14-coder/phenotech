"use client";

// /method → "What we collect and how often": generated from what this build actually contains
// (web/available.json, written by scripts/sync-data.mjs, and the graph's own source list), plus the
// daily live checks that /api/cron/digest runs for followed diseases.
import { AVAILABLE_KEY, loadAvailable, type Available } from "@/lib/population";
import { useResource } from "@/lib/resource";
import type { GraphIndex } from "@/lib/graph";

interface Row {
  what: string;
  from: string;
  how: string;
  live?: boolean;
}

export function CollectionList({ idx }: { idx: GraphIndex }) {
  const a = useResource<Available>(AVAILABLE_KEY, loadAvailable)?.data;
  const g = idx.graph;
  const built = a?.generated ?? g.meta.generated_at?.slice(0, 10);
  const rows: Row[] = [
    {
      what: "New recruiting studies and newly funded research, for every disease a member follows",
      from: "ClinicalTrials.gov API and NIH RePORTER, queried live",
      how: "Daily. Only for followed diseases; matches use the same precision rules as the trial layer.",
      live: true,
    },
    {
      what: `The in-depth atlas: ${g.nodes.length.toLocaleString("en")} entries and ${g.edges.length.toLocaleString("en")} sourced connections`,
      from: g.meta.sources.length ? `${g.meta.sources.length} public sources (listed on the right), each with its retrieval date` : "Public databases and websites",
      how: "Refreshed when the site is rebuilt.",
    },
    { what: "Every rare disease, basic data (names, genes, symptoms)", from: "Orphanet, OMIM, MONDO and HPO", how: "Refreshed when the site is rebuilt." },
  ];
  if (a?.scale) rows.push({ what: "Patient groups, studies and registries at scale (automated matches)", from: "ClinicalTrials.gov, patient-group directories, registries", how: "Refreshed when the site is rebuilt." });
  if (a?.population?.length) rows.push({ what: "How many people, trial readiness and ways to reach families", from: "Orphanet prevalence and the atlas’s own channels", how: "Refreshed when the site is rebuilt." });
  if (a?.dismech) rows.push({ what: "Disease mechanism chains", from: "DisMech (Monarch Initiative)", how: "Refreshed when the site is rebuilt." });
  if (a?.mechanism) rows.push({ what: "Mechanism class per gene", from: "Gene2Phenotype and ClinGen", how: "Refreshed when the site is rebuilt." });
  if (a?.clinvar_full) rows.push({ what: "ClinVar’s full list of disease-causing changes (387,722 in 13,292 genes), for the DNA checker", from: "ClinVar (NCBI), release of 2026-09-29", how: "Refreshed when the site is rebuilt." });
  if (a?.factors) rows.push({ what: "Gene constraint, mutation spectrum and AlphaMissense, shown as explanations", from: "gnomAD v4.1, ClinVar, AlphaMissense", how: "Refreshed when the site is rebuilt." });
  if (a?.similar) rows.push({ what: "Similar diseases for every rare disease with symptoms", from: "HPO symptoms, genes and Reactome pathways, checked against PrimeKG", how: "Refreshed when the site is rebuilt." });
  if (a?.contacts) rows.push({ what: "Published phone numbers and emails of organisations and recruiting studies", from: "Organisations’ own websites and ClinicalTrials.gov", how: "Refreshed when the site is rebuilt; each shows its retrieval date." });
  if (a?.testing_options) rows.push({ what: "How to get a DNA file or a genetic test", from: "Lab, regulator and programme pages, quoted word for word", how: "Refreshed when the site is rebuilt." });
  if (a?.eval) rows.push({ what: "Accuracy evaluation", from: "Computed from the atlas itself", how: "Re-run after curation changes." });

  return (
    <section aria-labelledby="collect-h" className="mt-12">
      <h2 id="collect-h" className="text-[22px] font-semibold tracking-tight text-ink">
        What we collect and how often
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-3">
        Public information only. {built ? `This version was built on ${built}.` : ""} Members’ own data is described on the{" "}
        <a href="/privacy" className="text-accent-700 underline">
          privacy page
        </a>
        .
      </p>
      <ul className="mt-4 divide-y divide-line-2 border-y border-line-2">
        {rows.map((r) => (
          <li key={r.what} className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_200px] sm:gap-4">
            <div>
              <p className="text-[15px] font-medium text-ink">{r.what}</p>
              <p className="text-sm text-ink-3">{r.from}</p>
            </div>
            <p className={`text-sm ${r.live ? "font-medium text-ok" : "text-ink-2"}`}>{r.how}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
