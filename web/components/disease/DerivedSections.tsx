"use client";

import Link from "next/link";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { IdeaCard, ideasFor } from "../ideas/IdeaCard";
import type { GraphIndex } from "@/lib/graph";
import { useDerived, type BeyondData, type Counterexample } from "@/lib/derived";
import type { DiseaseContext } from "@/lib/insights";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

export function IdeasSection({ idx, diseaseId }: { idx: GraphIndex; diseaseId: string }) {
  const ideas = ideasFor(idx, diseaseId);
  if (!ideas.length) return null;
  return (
    <section aria-labelledby="ideas-h" className="scroll-mt-20" data-tour="ideas">
      <p className={EYEBROW}>Going further</p>
      <h2 id="ideas-h" className={`mt-1 ${H2}`}>
        Ideas worth testing <span className="text-ink-3">(hypotheses, not evidence)</span>
      </h2>
      <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">
        The atlas connected dots nobody has connected yet. Each idea shows its chain of links, its weakest link, the caveats, and an
        experiment that could prove it wrong. None of this is a treatment suggestion.{" "}
        <Link href="/ideas" className="font-medium text-accent-700 hover:underline">
          All ideas →
        </Link>
      </p>
      <div className="mt-5 space-y-4">
        {ideas.map((e) => (
          <IdeaCard key={e.id} idx={idx} edge={e} />
        ))}
      </div>
    </section>
  );
}

/** Counterexamples whose edges touch this disease, its gene(s) or its variant groups. */
export function PatternBreaks({ idx, ctx }: { idx: GraphIndex; ctx: DiseaseContext }) {
  const data = useDerived<{ items: Counterexample[] }>("counterexamples");
  if (data.status !== "ready") return null;
  const ids = new Set([ctx.disease.id, ...ctx.genes.map((g) => g.id), ...ctx.variantGroups.map((v) => v.id)]);
  const items = data.data.items.filter((it) =>
    it.edge_ids.some((id) => {
      const e = idx.edgeById.get(id);
      return e && (ids.has(e.source) || ids.has(e.target));
    }),
  );
  if (!items.length) return null;
  return (
    <section aria-labelledby="breaks-h" className="scroll-mt-20">
      <h2 id="breaks-h" className={H2}>
        Where the pattern breaks
      </h2>
      <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">
        Places where the tidy story above does not hold. Read these before acting on any shared mechanism.{" "}
        <Link href="/method#breaks" className="font-medium text-accent-700 hover:underline">
          All of them →
        </Link>
      </p>
      <ul className="mt-4 space-y-3">
        {items.map((it) => (
          <CounterexampleCard key={it.id} idx={idx} it={it} />
        ))}
      </ul>
    </section>
  );
}

export function CounterexampleCard({ idx, it }: { idx: GraphIndex; it: Counterexample }) {
  const edges = it.edge_ids.map((id) => idx.edgeById.get(id)).filter((e): e is NonNullable<typeof e> => !!e);
  return (
    <li className="rounded-lg border border-warn-line px-5 py-4">
      <p className="text-[15px] font-semibold text-ink">{it.title}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{it.plain_language}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-3">
        <span className="font-medium text-ink-2">Why it matters: </span>
        {it.why_it_matters}
      </p>
      {edges.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {edges.slice(0, 6).map((e) => (
            <EvidenceChip key={e.id} edge={e} label={`${idx.nodeById.get(e.source)?.label ?? e.source} → ${idx.nodeById.get(e.target)?.label ?? e.target}`} />
          ))}
          {edges.length > 6 && <span className="self-center text-xs text-ink-3">and {edges.length - 6} more</span>}
        </div>
      )}
    </li>
  );
}

export function LookAlikes({ diseaseId, short }: { diseaseId: string; short: string }) {
  const data = useDerived<BeyondData>("beyond");
  if (data.status !== "ready") return null;
  const entry = data.data.diseases[diseaseId];
  if (!entry) return null;
  const top = entry.neighbors.slice(0, 5);
  return (
    <section aria-labelledby="beyond-h" className="scroll-mt-20">
      <h2 id="beyond-h" className={H2}>
        Look-alikes beyond our map
      </h2>
      <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">
        Diseases elsewhere with similar distinctive symptoms <span className="font-medium text-ink-2">(phenotype only, mechanism not assessed)</span>.
        A high score is a reason to look, not evidence of a shared cause. Compared against {data.data.meta.n_compared.toLocaleString()} diseases.
      </p>
      {entry.note && !top.length ? (
        <p className="mt-3 text-sm text-ink-3">{entry.note}</p>
      ) : (
        <ul className="mt-4 divide-y divide-line-2 border-y border-line-2">
          {top.map((n) => (
            <li key={n.id} className="grid grid-cols-1 gap-2 py-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
              <div>
                <p className="text-sm font-medium text-ink">{n.name}</p>
                <p className="text-xs text-ink-3">
                  {n.genes.length ? n.genes.join(", ") : "gene not recorded"} · {n.id} · more similar than {(n.percentile * 100).toFixed(n.percentile > 0.999 ? 2 : 1)}% of compared diseases
                </p>
              </div>
              <p className="text-sm text-ink-2">
                <span className="text-ink-3">Shared distinctive symptoms: </span>
                {n.top_shared_terms.map((t) => `${t.name} (${t.ic.toFixed(1)})`).join(", ")}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        How the atlas would grow to include them: curate each one’s gene, mechanism evidence and patient groups the same way as {short}, then
        they join the comparisons on this page.
      </p>
    </section>
  );
}

/** The family persona's pointer to the variant lookup. */
export function VariantHint() {
  return (
    <p className="mt-3 rounded-lg border border-line bg-subtle px-4 py-3 text-sm text-ink-2">
      Have a genetic report?{" "}
      <Link href="/variant" className="font-medium text-accent-700 hover:underline">
        Paste the variant line
      </Link>{" "}
      to see what kind of change it is and what it points to. It is not a diagnosis; your genetic counselor can explain it.
    </p>
  );
}

