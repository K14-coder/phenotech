"use client";

// /help?q=: when a search finds nothing. Say so plainly, then close spellings, related symptoms or genes,
// who to contact now, and a way to tell us about the disease.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { WithGraph } from "../GraphProvider";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { GLOBAL_INDEX_KEY, loadGlobalIndex, normalizeTerm, rowHref, suggestGlobal, type GlobalIndex } from "@/lib/global";
import { useResource } from "@/lib/resource";
import { capFirst } from "@/lib/text";
import { GeneralHelp } from "./GeneralHelp";

export function HelpView() {
  return <WithGraph>{(idx) => <Help idx={idx} />}</WithGraph>;
}

function Help({ idx }: { idx: GraphIndex }) {
  const q = (useSearchParams().get("q") ?? "").trim().slice(0, 120);
  const gres = useResource<GlobalIndex>(GLOBAL_INDEX_KEY, loadGlobalIndex);
  const gi = gres?.data;
  const sugg = useMemo(() => (gi && q ? suggestGlobal(gi, q, 6) : []), [gi, q]);
  const related = useMemo(() => {
    const nq = normalizeTerm(q);
    if (nq.length < 3) return { symptoms: [], genes: [] as { gene: string; rows: { id: string; name: string; href: string }[] }[] };
    // symptoms recorded in the atlas whose name contains the words typed
    // the whole phrase first; otherwise any longer word typed ("seizure disorderz" -> seizure), shortest labels first
    const words = nq.split(" ").filter((w) => w.length >= 5);
    const hit = (s: string) => {
      const t = ` ${normalizeTerm(s)} `;
      return t.includes(` ${nq}`) || words.some((w) => t.includes(` ${w} `) || t.includes(` ${w}s `));
    };
    const symptoms = idx.graph.nodes
      .filter((n) => n.type === "phenotype" && [n.label, ...(n.synonyms ?? [])].some(hit))
      .sort((a, b) => a.label.length - b.label.length)
      .slice(0, 3)
      .map((p) => ({
        label: p.label,
        diseases: (idx.adjacency.get(p.id) ?? [])
          .filter((x) => x.edge.type === "has_phenotype" && x.dir === "in")
          .map((x) => idx.nodeById.get(x.other)!)
          .filter(Boolean)
          .slice(0, 6),
      }))
      .filter((s) => s.diseases.length);
    // a gene symbol that partly matches (e.g. "STXBP" -> STXBP1)
    const genes: { gene: string; rows: { id: string; name: string; href: string }[] }[] = [];
    if (gi && /^[a-z0-9-]{2,12}$/i.test(q)) {
      const byGene = new Map<string, { id: string; name: string; href: string }[]>();
      for (const r of gi.rows)
        for (const g of r.genes)
          if (g.toLowerCase().startsWith(q.toLowerCase())) {
            const list = byGene.get(g) ?? [];
            if (list.length < 5) list.push({ id: r.id, name: capFirst(r.name), href: rowHref(r, idx) });
            byGene.set(g, list);
          }
      for (const [gene, rows] of [...byGene].slice(0, 3)) genes.push({ gene, rows });
    }
    return { symptoms, genes };
  }, [q, idx, gi]);

  return (
    <div className="mx-auto w-full max-w-[680px] space-y-8 px-4 pb-24 pt-8 sm:pt-12">
      <header>
        <h1 className="text-[26px] font-semibold leading-tight text-ink sm:text-[30px]">We couldn’t find “{q || "that"}” in the atlas yet.</h1>
        <p className="mt-3 text-[17px] leading-relaxed text-ink-2">
          The atlas covers more than 11,000 rare diseases, but names are spelled many ways and new conditions are described every year. Here is what
          you can do now.
        </p>
      </header>

      {sugg.length > 0 && (
        <section aria-labelledby="dym-h">
          <h2 id="dym-h" className="text-[19px] font-semibold text-ink">
            Did you mean
          </h2>
          <ul className="mt-2 space-y-1.5">
            {sugg.map((s) => (
              <li key={s.row.id}>
                <Link href={rowHref(s.row, idx)} className="text-[17px] text-accent-700 hover:underline">
                  {capFirst(s.row.name)}
                </Link>
                {s.matched && normalizeTerm(s.matched) !== normalizeTerm(s.row.name) && <span className="text-sm text-ink-3"> · also called {s.matched}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(related.symptoms.length > 0 || related.genes.length > 0) && (
        <section aria-labelledby="rel-h">
          <h2 id="rel-h" className="text-[19px] font-semibold text-ink">
            Closely related problems
          </h2>
          {related.symptoms.map((s) => (
            <div key={s.label} className="mt-3">
              <p className="text-[16px] text-ink">
                Diseases where <b className="font-medium">{s.label.toLowerCase()}</b> is recorded:
              </p>
              <ul className="mt-1 flex flex-wrap gap-2">
                {s.diseases.map((d) => (
                  <li key={d.id}>
                    <Link href={diseaseHref(d.id)} className="inline-flex min-h-[40px] items-center rounded-lg border border-line px-3 text-[15px] text-ink-2 hover:border-accent-500">
                      {d.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {related.genes.map((g) => (
            <div key={g.gene} className="mt-3">
              <p className="text-[16px] text-ink">
                Conditions linked to the <b className="font-medium">{g.gene}</b> gene:
              </p>
              <ul className="mt-1 space-y-1">
                {g.rows.map((r) => (
                  <li key={r.id}>
                    <Link href={r.href} className="text-[15px] text-accent-700 hover:underline">
                      {r.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      <GeneralHelp />

      <section className="rounded-xl bg-subtle px-4 py-4">
        <h2 className="text-[19px] font-semibold text-ink">Tell us about this disease</h2>
        <p className="mt-1 text-[15px] text-ink-2">If you know the condition, a patient group or a study for it, tell us so the next person finds it.</p>
        <Link href="/contribute" className="mt-3 inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900">
          Tell us about it
        </Link>
      </section>
    </div>
  );
}
