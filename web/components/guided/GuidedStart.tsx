"use client";

// /start?d=<id>: Simple mode's guided start after a search. Step 1 reassures; step 2 asks "Do you know
// which type?" with large plain options, an "I'm not sure" path, and look-alike names kept apart.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { WithGraph } from "../GraphProvider";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { GLOBAL_INDEX_KEY, globalHref, loadGlobalIndex, mappedAtlasId, normalizeTerm, rowHref, type GlobalIndex, type GlobalRow } from "@/lib/global";
import { groupFor, loadGroups, type GroupsFile } from "@/lib/groups";
import { useResource } from "@/lib/resource";
import { capFirst } from "@/lib/text";

interface Option {
  key: string;
  title: string;
  line: string;
  href: string;
}

export function GuidedStart() {
  return <WithGraph>{(idx) => <Start idx={idx} />}</WithGraph>;
}

function Start({ idx }: { idx: GraphIndex }) {
  const id = useSearchParams().get("d") ?? "";
  const gres = useResource<GlobalIndex>(GLOBAL_INDEX_KEY, loadGlobalIndex);
  const groups = useResource<GroupsFile | null>("global:groups", loadGroups);
  const gi = gres?.data;

  const model = useMemo(() => {
    const node = idx.nodeById.get(id);
    if (node?.type === "disease") {
      const subtypes = ((node.attrs as { subtypes?: { name: string; MONDO?: string }[] } | undefined)?.subtypes ?? []).filter((s) => s.name);
      const base = diseaseHref(node.id);
      const options: Option[] = subtypes.map((s) => ({
        key: s.MONDO ?? s.name,
        title: capFirst(s.name),
        line: subtypeLine(s.name, gi?.byId.get(s.MONDO ?? "")),
        href: `${base}?type=${encodeURIComponent(s.name)}`,
      }));
      // look-alike names from the global grouping of the first subtype, minus anything this disease covers
      let lookalikes: GlobalRow[] = [];
      const anchor = subtypes.map((s) => gi?.byId.get(s.MONDO ?? "")).find((r): r is GlobalRow => !!r);
      if (gi && anchor) lookalikes = groupFor(gi, anchor, groups?.data).lookalikes.filter((r) => mappedAtlasId(r, idx) !== node.id);
      return { title: node.label, general: base, options: options.length > 1 ? options : [], lookalikes };
    }
    if (!gi) return null;
    const row = gi.byId.get(id);
    if (!row) return { title: id, general: globalHref(id), options: [], lookalikes: [] };
    const g = groupFor(gi, row, groups?.data);
    return {
      title: capFirst(g.head.name),
      general: rowHref(g.head, idx),
      options: g.members.map((m) => ({ key: m.row.id, title: capFirst(m.row.name), line: plainDistinction(m.distinction), href: rowHref(m.row, idx) })),
      lookalikes: g.lookalikes,
    };
  }, [idx, id, gi, groups]);

  if (!model)
    return (
      <p className="mx-auto max-w-[640px] px-4 py-16 text-[17px] text-ink-3" role="status">
        One moment…
      </p>
    );

  return (
    <div className="mx-auto w-full max-w-[640px] space-y-8 px-4 pb-24 pt-8 sm:pt-14">
      <section aria-labelledby="ok-h" className="rounded-xl bg-subtle px-5 py-5">
        <p className="text-sm text-ink-3">You searched for</p>
        <h1 id="ok-h" className="mt-1 text-[28px] font-semibold leading-tight text-ink">
          {model.title}
        </h1>
        <p className="mt-3 text-[17px] leading-relaxed text-ink">
          You’re in the right place. Many families start exactly here. Let’s find the information that fits you.
        </p>
      </section>

      {model.options.length > 0 ? (
        <section aria-labelledby="type-h">
          <h2 id="type-h" className="text-[22px] font-semibold text-ink">
            Do you know which type?
          </h2>
          <p className="mt-1 text-[15px] text-ink-3">It may be written on the genetic report or the clinic letter.</p>
          <ul className="mt-4 space-y-2.5">
            {model.options.map((o) => (
              <li key={o.key}>
                <Link
                  href={o.href}
                  className="block min-h-[56px] rounded-xl border border-line bg-white px-4 py-3.5 hover:border-accent-500 focus-visible:border-accent-700"
                >
                  <span className="block text-[17px] font-medium text-ink">{o.title}</span>
                  <span className="mt-0.5 block text-[15px] text-ink-3">{o.line}</span>
                </Link>
              </li>
            ))}
            <li>
              <Link
                href={model.general}
                className="block min-h-[56px] rounded-xl border-2 border-accent-700 bg-white px-4 py-3.5 text-[17px] font-medium text-accent-900 hover:bg-accent-50"
              >
                I’m not sure, show me the general information
              </Link>
            </li>
          </ul>
        </section>
      ) : (
        <Link
          href={model.general}
          className="inline-flex min-h-[52px] items-center rounded-xl bg-accent-700 px-5 text-[17px] font-medium text-white hover:bg-accent-900"
        >
          Show me the information →
        </Link>
      )}

      {model.lookalikes.length > 0 && (
        <details className="rounded-xl border border-line px-4 py-3">
          <summary className="cursor-pointer text-[15px] font-medium text-ink-2">Similar names that are different conditions</summary>
          <p className="mt-2 text-sm text-ink-3">These sound alike but are separate conditions, often with a different gene.</p>
          <ul className="mt-2 space-y-1.5">
            {model.lookalikes.map((r) => (
              <li key={r.id}>
                <Link href={rowHref(r, idx)} className="text-[15px] text-accent-700 hover:underline">
                  {capFirst(r.name)}
                </Link>
                {r.genes.length > 0 && <span className="text-sm text-ink-3"> · {r.genes.slice(0, 2).join(", ")}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** One plain line for a subtype of a mapped disease: its inheritance or gene, never invented. */
function subtypeLine(name: string, row?: GlobalRow): string {
  const n = normalizeTerm(name);
  if (/\b(lethal|perinatal|neonatal|infantile)\b/.test(n)) return "A form that starts very early in life.";
  if (/\bjuvenile\b/.test(n)) return "A form that starts in childhood or the teenage years.";
  if (/\badult\b/.test(n)) return "A form that starts in adulthood.";
  if (row?.genes.length) return `Listed with the ${row.genes.slice(0, 2).join(", ")} gene.`;
  return "A named form of this condition.";
}

/** "juvenile (HTT)" -> "Starts in childhood or the teenage years (HTT)"; other distinctions stay as written. */
function plainDistinction(d: string): string {
  const m = d.match(/^(\w+)(.*)$/);
  if (!m) return d;
  const w = m[1].toLowerCase();
  const rest = m[2];
  const plain: Record<string, string> = {
    juvenile: "Starts in childhood or the teenage years",
    infantile: "Starts in the first year of life",
    neonatal: "Starts around birth",
    perinatal: "Starts before or around birth",
    congenital: "Present from birth",
    adult: "Starts in adulthood",
    childhood: "Starts in childhood",
    atypical: "An unusual form",
  };
  return plain[w] ? `${plain[w]}${rest}` : capFirst(d);
}
