"use client";

// /method → the direction result (data/derived/eval_direction.json, eval.md section 6), in plain words:
// right when it fires, too rare to change rankings, so it is shown as a flag next to treatments, not as a score.
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";

interface EvalDirection {
  primekg?: { results?: Record<string, { rr: number }> };
}

async function load(): Promise<EvalDirection | null> {
  const a = await loadAvailableOnce();
  if (!a.eval_direction) return null;
  const r = await fetch("/data/derived/eval_direction.json");
  return r.ok ? ((await r.json()) as EvalDirection) : null;
}

export function DirectionNote() {
  const e = useResource<EvalDirection | null>("method:eval-direction", load)?.data;
  const res = e?.primekg?.results ?? {};
  const base = Object.entries(res).find(([k]) => k.startsWith("base"))?.[1]?.rr;
  const dir = res["nested direction-aware"]?.rr;
  return (
    <section id="direction" aria-labelledby="direction-h" className="mt-12 scroll-mt-20 border-t border-line pt-8">
      <h2 id="direction-h" className="text-[19px] font-semibold text-ink">
        Does the treatment push the gene the right way?
      </h2>
      <div className="mt-2 max-w-[760px] space-y-2 text-sm leading-relaxed text-ink-2">
        <p>
          Some diseases come from too little of a gene’s activity, others from too much. A drug that lowers a gene’s activity can help the second kind
          and harm the first. We labelled both sides and checked whether this helps find the right treatment.
        </p>
        <p>
          <b className="font-medium text-ink">It is right when it applies,</b> but it rarely applies: on the 1,300 external cases a drug’s target was the
          disease gene in only 8, and all 8 pointed the right way.
          {base != null && dir != null ? ` Ranking barely changed (${base.toFixed(3)} → ${dir.toFixed(3)}).` : ""}
        </p>
        <p>
          <b className="font-medium text-ink">So it is shown as a flag, not a score.</b> Next to a treatment you may see “Direction fits” or “Direction
          mismatch”, but only when the drug acts directly on the disease gene, and per group of changes where one gene can go either way (for example
          sodium-channel blockers help SCN2A gain-of-function changes and can harm loss-of-function ones).
        </p>
      </div>
    </section>
  );
}
