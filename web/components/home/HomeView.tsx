"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { usePersona } from "@/lib/persona";
import { useTour } from "../tour/TourProvider";
import { WithGraph } from "../GraphProvider";
import { SearchBox } from "../search/SearchBox";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import type { Searcher } from "@/lib/search";

const PREFERRED_CHIPS = ["Munc18-1", "Seizures", "Haploinsufficiency", "SNAP25"];

export function HomeView() {
  return <WithGraph>{(idx, search) => <Home idx={idx} search={search} />}</WithGraph>;
}

function Home({ idx, search }: { idx: GraphIndex; search: Searcher }) {
  const params = useSearchParams();
  const qParam = params.get("q") ?? "";
  const [q, setQ] = useState(qParam);
  const [focusKey, setFocusKey] = useState(qParam ? 1 : 0);
  // ?q= (used by the guided tour) fills the search box and opens the results
  const [handledQ, setHandledQ] = useState(qParam);
  if (qParam !== handledQ) {
    setHandledQ(qParam);
    if (qParam) {
      setQ(qParam);
      setFocusKey((k) => k + 1);
    }
  }
  const { start } = useTour();
  const meta = idx.graph.meta;
  const persona = usePersona();
  const router = useRouter();

  // Industry lands on therapeutic approaches, Research on the cohort view: once per visit, so the Search
  // link still reaches this page afterwards
  useEffect(() => {
    if (qParam || (persona !== "biotech" && persona !== "researcher")) return;
    try {
      if (sessionStorage.getItem("atlas.landed")) return;
      sessionStorage.setItem("atlas.landed", "1");
    } catch {
      return;
    }
    router.replace(persona === "biotech" ? "/approach" : "/research");
  }, [persona, qParam, router]);

  const chips = useMemo(() => exampleChips(idx, search), [idx, search]);
  const diseases = useMemo(
    () =>
      idx.graph.nodes
        .filter((n) => n.type === "disease")
        .sort((a, b) => (idx.degree.get(b.id) ?? 0) - (idx.degree.get(a.id) ?? 0))
        .slice(0, 6),
    [idx],
  );
  const counts = useMemo(() => {
    const c = { disease: 0, gene: 0, patient_org: 0 } as Record<string, number>;
    for (const n of idx.graph.nodes) c[n.type] = (c[n.type] ?? 0) + 1;
    return c;
  }, [idx]);

  if (persona === "family")
    return <DevonHome q={q} setQ={setQ} focusKey={focusKey} onTour={() => start("syt2")} diseases={diseases} />;

  return (
    <div className="mx-auto w-full max-w-[780px] px-6 pb-24 pt-[12vh]">
      {meta.slice && <p className="text-sm text-ink-3">{meta.slice}</p>}
      <h1 className="mt-3 text-[34px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink">
        Find who shares your disease’s biology, what already exists, and what to do together.
      </h1>
      <p className="mt-4 text-[17px] leading-relaxed text-ink-3">
        Every connection shows where it comes from, how strong it is, and what is still unknown.
      </p>

      <div className="mt-9" data-tour="search">
        <SearchBox variant="hero" value={q} onChange={setQ} autoFocus focusKey={focusKey} label="Search diseases, genes, proteins, symptoms, mechanisms and patient groups" />
      </div>

      {chips.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="mr-1 text-sm text-ink-3">Try</span>
          {chips.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => {
                setQ(c);
                setFocusKey((k) => k + 1);
              }}
              className="rounded-full border border-line px-3 py-1 text-sm text-ink-2 transition-colors hover:border-accent-500 hover:text-ink"
            >
              {c}
            </button>
          ))}
        </div>
      )}
      <p className="mt-3 text-sm text-ink-3">
        New diagnosis? Start with the gene name on the genetic test report, or{" "}
        <Link href={`/variant?q=${encodeURIComponent("NM_003165.6(STXBP1):c.1162C>T (p.Arg388Ter)")}`} className="font-medium text-accent-700 hover:underline">
          paste a line from a genetic report
        </Link>{" "}
        to look up the variant.
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <span className="text-sm text-ink-3">Guided tour</span>
        <button
          type="button"
          onClick={() => start("maria")}
          className="rounded-md border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-accent-500"
        >
          Follow a patient group (VAMP2)
        </button>
        <button
          type="button"
          onClick={() => start("syt2")}
          className="rounded-md border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-accent-500"
        >
          Follow a family with no patient group (SYT2)
        </button>
      </div>

      <section aria-label="What the atlas answers" className="mt-20 grid grid-cols-1 gap-8 border-t border-line pt-8 sm:grid-cols-3">
        {[
          ["Who shares our disease characteristics?", "Diseases ranked by shared mechanism and distinctive symptoms, not by name."],
          ["What useful work already exists?", "Registries, studies and models from related diseases, marked reusable, adaptable or not applicable."],
          ["What should we do together?", "Partners, a suggested next step, and an honest list of what nobody knows yet."],
        ].map(([title, body], i) => (
          <div key={title}>
            <p className="text-xs font-medium tabular-nums text-ink-3">0{i + 1}</p>
            <h2 className="mt-1.5 text-[15px] font-semibold leading-snug text-ink">{title}</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-3">{body}</p>
          </div>
        ))}
      </section>

      {diseases.length > 0 && (
        <section aria-label="Diseases in the atlas" className="mt-12">
          <h2 className="text-sm font-medium text-ink-2">Or open a disease</h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {diseases.map((d) => (
              <li key={d.id}>
                <Link
                  href={diseaseHref(d.id)}
                  className="inline-block rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 transition-colors hover:border-accent-500 hover:text-ink"
                >
                  {d.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="mt-14 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-3">
        <span>
          {counts.disease ?? 0} diseases · {counts.gene ?? 0} genes · {counts.patient_org ?? 0} patient groups ·{" "}
          {idx.graph.edges.length} connections
        </span>
        <span>
          Data {meta.version}
          {meta.generated_at ? `, generated ${meta.generated_at}` : ""}
        </span>
        <Link href="/atlas" className="font-medium text-accent-700 hover:underline">
          Explore the full atlas →
        </Link>
      </footer>
    </div>
  );
}

/** Devon's landing (docs/persona-spec.md): one friendly question, a hint, and reassurance. Nothing technical above the fold. */
function DevonHome({
  q,
  setQ,
  focusKey,
  onTour,
  diseases,
}: {
  q: string;
  setQ: (s: string) => void;
  focusKey: number;
  onTour: () => void;
  diseases: { id: string; label: string }[];
}) {
  return (
    <div className="mx-auto w-full max-w-[680px] px-4 pb-24 pt-10 sm:px-6 sm:pt-[12vh]">
      <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.01em] text-ink sm:text-[38px]">Which disease are you looking for?</h1>
      <p className="mt-3 text-[17px] leading-relaxed text-ink-2">
        Type the name of the condition or the gene (for example STXBP1). It’s fine if you’re looking for a relative or a friend. You can also
        paste a line from a genetic report.
      </p>
      <div className="mt-6" data-tour="search">
        <SearchBox
          variant="hero"
          value={q}
          onChange={setQ}
          autoFocus
          focusKey={focusKey}
          label="Which disease are you looking for?"
          placeholder="Gene or condition, e.g. STXBP1"
        />
      </div>
      <ul className="mt-8 space-y-2.5 text-[17px] leading-relaxed text-ink">
        <li className="flex gap-3">
          <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-700" aria-hidden="true" />
          You are not alone.
        </li>
        <li className="flex gap-3">
          <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-700" aria-hidden="true" />
          This atlas connects families, researchers and studies.
        </li>
        <li className="flex gap-3">
          <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-700" aria-hidden="true" />
          Everything here links to its source.
        </li>
      </ul>
      <p className="mt-6 text-[16px] text-ink-2">
        Have a DNA sequence file from your test?{" "}
        <Link href="/sequence" className="font-medium text-accent-700 underline underline-offset-4">
          Check it here
        </Link>
        . It never leaves your device.
      </p>
      <p className="mt-8 text-sm leading-relaxed text-ink-3">
        This is information, not medical advice. A doctor or genetic counsellor is the right person for decisions.
      </p>

      <section className="mt-[22vh] border-t border-line pt-8" aria-label="More ways to start">
        <p className="text-[15px] text-ink-2">Not sure where to start?</p>
        <button
          type="button"
          onClick={onTour}
          className="mt-3 inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] font-medium text-ink hover:border-accent-500"
        >
          Follow a family through the atlas
        </button>
        {diseases.length > 0 && (
          <>
            <p className="mt-8 text-[15px] text-ink-2">Or open one of these:</p>
            <ul className="mt-3 flex flex-wrap gap-2">
              {diseases.map((d) => (
                <li key={d.id}>
                  <Link href={diseaseHref(d.id)} className="inline-flex min-h-[40px] items-center rounded-lg border border-line px-3 text-[15px] text-ink-2 hover:border-accent-500 hover:text-ink">
                    {d.label}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function exampleChips(idx: GraphIndex, search: Searcher): string[] {
  const ok = PREFERRED_CHIPS.filter((c) => search(c, 1).length > 0);
  if (ok.length >= 3) return ok;
  // fall back to examples drawn from the data: a protein synonym, a symptom, a mechanism, a disease
  const out = [...ok];
  const gene = idx.graph.nodes.find((n) => n.type === "gene" && (n.synonyms?.length || n.attrs?.protein));
  if (gene && gene.type === "gene") out.push(gene.attrs?.protein ?? gene.synonyms![0]);
  const pheno = idx.graph.nodes.find((n) => n.type === "phenotype");
  if (pheno) out.push(pheno.label);
  const mech = idx.graph.nodes.find((n) => n.type === "mechanism");
  if (mech) out.push(mech.label);
  return [...new Set(out)].slice(0, 4);
}
