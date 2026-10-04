"use client";

import Link from "next/link";
import { PERSONAS } from "@/lib/persona";
import { useMemo } from "react";
import { WithGraph } from "../GraphProvider";
import { AccuracySection } from "./AccuracySection";
import { CollectionList } from "./CollectionList";
import { EvidenceLegend } from "../evidence/EvidenceBits";
import { CounterexampleCard } from "../disease/DerivedSections";
import { useDerived, type Counterexample } from "@/lib/derived";
import type { GraphIndex } from "@/lib/graph";
import { isPlaceholderUrl } from "@/lib/text";

export function MethodView() {
  return <WithGraph>{(idx) => <Method idx={idx} />}</WithGraph>;
}

function pct(x: number, y: number) {
  return y ? Math.round((100 * x) / y) : 0;
}

function Method({ idx }: { idx: GraphIndex }) {
  const g = idx.graph;
  const cx = useDerived<{ items: Counterexample[] }>("counterexamples");
  const s = useMemo(() => {
    const edges = g.edges;
    const sourced = edges.filter((e) => e.evidence.some((ev) => ev.supports !== false && !ev.needs_review)).length;
    const allEvidence = edges.flatMap((e) => [...e.evidence, ...(e.counter_evidence ?? [])]);
    const quoted = allEvidence.filter((ev) => typeof ev.quote === "string" && ev.quote.trim());
    const verified = quoted.filter((ev) => ev.verified).length;
    const crossChecked = edges.filter((e) => [...e.evidence, ...(e.counter_evidence ?? [])].some((ev) => ev.cross_checked));
    const disagreements = edges.filter((e) => [...e.evidence, ...(e.counter_evidence ?? [])].some((ev) => ev.cross_checked && !ev.cross_checked.agrees || ev.needs_review)).length;
    const reviewed = edges.filter((e) => e.review);
    const contested = edges.filter((e) => e.status === "contested").length;
    const inferred = edges.filter((e) => e.evidence_level === "inferred" || e.evidence_level === "hypothesis").length;
    return {
      edges: edges.length,
      sourced,
      quoted: quoted.length,
      verified,
      crossChecked: crossChecked.length,
      disagreements,
      reviewed: reviewed.length,
      corrected: reviewed.filter((e) => e.review?.verdict !== "confirmed").length,
      contested,
      inferred,
      gaps: g.gaps.length,
    };
  }, [g]);

  const tiles: { big: string; label: string; body: string }[] = [
    { big: `${s.sourced} / ${s.edges}`, label: "links with a source", body: `${pct(s.sourced, s.edges)}% of connections cite at least one database record, paper, trial or website.` },
    { big: `${s.verified} / ${s.quoted}`, label: "quotes string-verified", body: "Every quote shown is checked word for word against the stored source text. Unmatched quotes are marked “Not verified”." },
    {
      big: `${s.crossChecked}`,
      label: "connections cross-checked by OpenAI",
      body: s.crossChecked ? `An independent AI re-reading of the source. ${s.disagreements} disagreement${s.disagreements === 1 ? "" : "s"} flagged for expert review.` : "An independent AI re-reading of each source. Results are added as they arrive.",
    },
    {
      big: `${s.reviewed}`,
      label: "connections reviewed by a biochemist",
      body: s.reviewed ? `${s.corrected} corrected or rejected after review.` : "Human review results are added as they arrive. Until then, nothing is marked as reviewed.",
    },
    { big: `${s.contested}`, label: "contested connections", body: "Sources disagree. Both sides are shown in the evidence panel, never hidden." },
    { big: `${s.gaps}`, label: "open questions recorded", body: "Things the atlas could not answer, with what was searched and how to find out." },
  ];

  return (
    <div className="mx-auto w-full max-w-[1040px] px-8 pb-24 pt-12">
      <p className="text-sm text-ink-3">{g.meta.slice}</p>
      <h1 className="mt-2 text-[32px] font-semibold tracking-[-0.02em] text-ink">How we know</h1>
      <p className="mt-3 max-w-[680px] text-[17px] leading-relaxed text-ink-3">
        Every connection in the atlas has to show where it comes from. These numbers are counted live from the data you are looking at.
      </p>
      <p className="mt-2 text-sm">
        <Link href="/impact" className="font-medium text-accent-700 hover:underline">
          Why this could be 10× faster →
        </Link>
      </p>

      <section aria-label="Evidence integrity in numbers" data-tour="method-numbers" className="mt-10 grid grid-cols-1 gap-x-10 gap-y-9 border-t border-line pt-9 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <div key={t.label}>
            <p className="text-[34px] font-semibold leading-none tracking-tight tabular-nums text-ink">{t.big}</p>
            <p className="mt-2 text-sm font-medium text-ink">{t.label}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink-3">{t.body}</p>
          </div>
        ))}
      </section>

      <AccuracySection />

      <div className="mt-16 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-labelledby="built-h">
          <h2 id="built-h" className="text-[22px] font-semibold tracking-tight text-ink">
            How the atlas is built
          </h2>
          <ol className="mt-5 space-y-5">
            {[
              ["Public sources", "Genes, diseases, symptoms, variants, trials, grants and patient groups come from the public databases and websites listed on the right, each with the date it was retrieved."],
              ["Curation", "Each connection is written as a plain sentence, given an evidence level (clinical, curated database, experimental, case reports, inferred, hypothesis) and a confidence score from a fixed rubric."],
              ["Verbatim quotes, verified", "Quotes from papers and websites are copied word for word and string-matched against the stored source text. A quote that doesn't match is shown as not verified."],
              ["An independent OpenAI re-reading", "A second, independent pass with an OpenAI model re-reads each source. When it disagrees, the connection is flagged for expert review. A flag alone never turns a link into “contested”."],
              ["Human review", "A biochemist reviews flagged and important connections. Their verdict and note appear in the evidence panel."],
            ].map(([title, body], i) => (
              <li key={title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-2">
                <span className="text-sm tabular-nums text-ink-3">{i + 1}</span>
                <div>
                  <p className="text-[15px] font-medium text-ink">{title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">{body}</p>
                </div>
              </li>
            ))}
          </ol>

          <CollectionList idx={idx} />

          <h2 className="mt-12 text-[22px] font-semibold tracking-tight text-ink">What the atlas will not do</h2>
          <ul className="mt-4 space-y-3 text-sm leading-relaxed text-ink-2">
            <li>
              <span className="font-medium text-ink">No medical advice.</span> Treatment evidence is shown as published evidence to discuss
              with your neurologist.
            </li>
            <li>
              <span className="font-medium text-ink">AI never invents a link.</span> AI drafts may only cite connections that already exist
              in the atlas; anything else is removed or shown as uncited framing.
            </li>
            <li>
              <span className="font-medium text-ink">Guesses look like guesses.</span> {s.inferred} connections are inferred by the atlas or
              are hypotheses. They are drawn dashed or dotted and never presented as fact.
            </li>
            <li>
              <span className="font-medium text-ink">Unknowns stay visible.</span> When nothing connects, the atlas says so and records the gap.
            </li>
          </ul>

          <h2 id="breaks" className="mt-12 scroll-mt-20 text-[22px] font-semibold tracking-tight text-ink">
            Where the pattern breaks
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-3">
            The places where “same mechanism, shared research” does not hold cleanly. Every item links to the evidence behind it.
          </p>
          {cx.status === "ready" ? (
            <ul className="mt-4 space-y-3">
              {cx.data.items.map((it) => (
                <CounterexampleCard key={it.id} idx={idx} it={it} />
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-ink-3">{cx.status === "loading" ? "Loading…" : "Not available in this build."}</p>
          )}

          <h2 className="mt-12 text-[22px] font-semibold tracking-tight text-ink">Ideas, kept separate from evidence</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            Computed hypotheses (a therapy that a mechanism links to a disease nobody has tried it in) are drawn dashed, labelled “Hypothesis”,
            capped at low confidence and shown with their weakest link and a test that could prove them wrong.{" "}
            <Link href="/ideas" className="font-medium text-accent-700 hover:underline">
              See the ideas worth testing →
            </Link>
          </p>

          <h2 className="mt-12 text-[22px] font-semibold tracking-tight text-ink">Reading the evidence labels</h2>
          <div className="mt-4 rounded-lg border border-line px-5 py-4">
            <EvidenceLegend />
          </div>
        </section>

        <aside aria-labelledby="sources-h">
          <h2 id="sources-h" className="text-sm font-semibold text-ink">
            Sources
          </h2>
          <ul className="mt-3 divide-y divide-line-2 border-y border-line-2">
            {g.meta.sources.map((src) => (
              <li key={src.name} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                {isPlaceholderUrl(src.url) ? (
                  <span className="text-ink">{src.name}</span>
                ) : (
                  <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                    {src.name} ↗
                  </a>
                )}
                <span className="shrink-0 text-xs text-ink-3">{src.version_or_date.replace(/^retrieved /, "")}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            Data version {g.meta.version}
            {g.meta.generated_at ? `, built ${g.meta.generated_at.slice(0, 10)}` : ""}. {g.nodes.length} entries, {g.edges.length} connections.
          </p>
          <Link href="/atlas" className="mt-4 inline-block text-sm font-medium text-accent-700 hover:underline">
            Explore the atlas →
          </Link>
        </aside>
      </div>

      <section aria-labelledby="views-h" className="mt-14 border-t border-line pt-8">
        <h2 id="views-h" className="text-[19px] font-semibold text-ink">
          One atlas, four views
        </h2>
        <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-2">
          The same sourced data is shown four ways; switch at the top right. The evidence behind every view is identical, only the
          wording and what comes first change.
        </p>
        <dl className="mt-4 grid max-w-[900px] gap-3 sm:grid-cols-2">
          {PERSONAS.map((p) => (
            <div key={p.id} className="rounded-lg border border-line px-4 py-3">
              <dt className="text-sm font-semibold text-ink">{p.label}</dt>
              <dd className="mt-0.5 text-sm text-ink-3">{p.short}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
