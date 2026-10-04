"use client";

// "Community research" block on /d/<id>: claims volunteers extracted with their own OpenAI access,
// each quote verified verbatim against the PubMed abstract by the server. Renders nothing when there are none.
import Link from "next/link";
import { useEffect, useState } from "react";
import { SHORT, qapi, type DiseaseResearch, type StoredClaim } from "./queue-client";

const REL: Record<string, string> = {
  causes: "causes",
  driven_by: "is driven by",
  has_effect: "has the effect",
  participates_in: "takes part in",
  disrupts: "disrupts",
  developed_for: "was developed or tried for",
  targets: "targets",
  has_phenotype: "has the feature",
  natural_history: "natural history:",
};
const GROUP_OF: Record<string, string> = {
  driven_by: "mechanism",
  has_effect: "mechanism",
  causes: "mechanism",
  participates_in: "process",
  disrupts: "process",
  developed_for: "therapies",
  targets: "therapies",
  has_phenotype: "phenotypes",
  natural_history: "natural_history",
};
const label = (s: string | null) => (s ? s.replace(/_/g, " ") : "");

export function CommunityResearch({ id }: { id: string }) {
  const [data, setData] = useState<DiseaseResearch | null>(null);
  useEffect(() => {
    let live = true;
    qapi<DiseaseResearch>(`/api/queue/disease/${encodeURIComponent(id)}`)
      .then((d) => live && setData(d))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [id]);
  if (!data || (!data.claims.length && !data.groups.length)) return null;

  const order = ["mechanism", "process", "therapies", "phenotypes", "natural_history"];
  const byGroup = new Map<string, StoredClaim[]>();
  for (const c of data.claims) {
    const g = GROUP_OF[c.relation] ?? "mechanism";
    byGroup.set(g, [...(byGroup.get(g) ?? []), c]);
  }
  const done = data.checklist.filter((c) => c.done).length;

  return (
    <section aria-labelledby="crowd-h" className="max-w-[760px]">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Community research</p>
      <h2 id="crowd-h" className="mt-1 text-[22px] font-semibold tracking-tight text-ink">
        What volunteers found in the literature
      </h2>
      <p className="mt-2 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm leading-relaxed text-warn-ink">
        <span className="font-semibold">Unreviewed.</span> {capFirst(data.statusLabel)}: volunteers ran their own AI models (OpenAI or Anthropic Claude) over PubMed abstracts the
        atlas fetched, and the server kept only claims whose quote appears word for word in that abstract. No expert has checked them yet. Not medical advice:
        discuss anything here with your clinician.
      </p>
      <p className="mt-3 text-sm text-ink-3">
        {data.claims.length} verified claim{data.claims.length === 1 ? "" : "s"}
        {data.groups.length ? ` and ${data.groups.length} research group${data.groups.length === 1 ? "" : "s"}` : ""} · checklist {done} of {data.checklist.length}{" "}
        covered ·{" "}
        <Link href="/research-queue" className="text-accent-700 hover:underline">
          how the research queue works
        </Link>
      </p>

      {order
        .filter((g) => byGroup.has(g))
        .map((g) => (
          <div key={g} className="mt-6">
            <h3 className="text-[15px] font-semibold text-ink">{SHORT[g]}</h3>
            <ul className="mt-2 divide-y divide-line-2 border-y border-line-2">
              {byGroup.get(g)!.slice(0, 12).map((c, i) => (
                <li key={`${c.pmid}-${i}`} className="py-3">
                  <p className="text-[15px] text-ink">
                    {c.negated && <span className="mr-1.5 rounded bg-subtle px-1.5 py-0.5 text-xs font-medium text-ink-2">NOT</span>}
                    <span className="font-medium">{c.subject}</span> <span className="text-ink-3">{REL[c.relation] ?? c.relation}</span>{" "}
                    <span className="font-medium">{c.object}</span>
                    {c.mechanism_class && <span className="ml-2 rounded bg-accent-50 px-1.5 py-0.5 text-xs text-accent-900">{label(c.mechanism_class)}</span>}
                    {c.therapy_stage && <span className="ml-2 rounded bg-accent-50 px-1.5 py-0.5 text-xs text-accent-900">{label(c.therapy_stage)}</span>}
                  </p>
                  <blockquote className="mt-1.5 border-l-2 border-line pl-3 text-sm italic leading-relaxed text-ink-2">“{c.quote}”</blockquote>
                  <p className="mt-1 text-xs text-ink-3">
                    <a href={`https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                      PMID {c.pmid}
                    </a>
                    {c.year ? ` (${c.year})` : ""} · {label(c.study_type)}
                    {c.species ? `, ${c.species}` : ""} · {c.certainty} · by {c.handle} with {c.model}
                  </p>
                </li>
              ))}
            </ul>
            {byGroup.get(g)!.length > 12 && <p className="mt-1 text-xs text-ink-3">and {byGroup.get(g)!.length - 12} more</p>}
          </div>
        ))}

      {data.groups.length > 0 && (
        <div className="mt-6">
          <h3 className="text-[15px] font-semibold text-ink">Research groups (senior authors, from PubMed)</h3>
          <ul className="mt-2 divide-y divide-line-2 border-y border-line-2">
            {data.groups.slice(0, 12).map((g, i) => (
              <li key={`${g.pmid}-${i}`} className="py-2.5 text-sm">
                <span className="font-medium text-ink">{g.senior_author}</span> <span className="text-ink-2">· {g.affiliation}</span>
                <span className="block text-xs text-ink-3">
                  <a href={`https://pubmed.ncbi.nlm.nih.gov/${g.pmid}/`} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                    PMID {g.pmid}
                  </a>
                  {g.year ? ` (${g.year})` : ""}: {g.title}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function capFirst(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
