"use client";

import Link from "next/link";
import { WithGraph } from "../GraphProvider";
import { useTour } from "../tour/TourProvider";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { useDerived } from "@/lib/derived";

interface SourcedDate {
  date: string;
  ref: string;
  url: string;
  title?: string;
}
interface Timeline {
  disease: string;
  gene_discovery: SourcedDate;
  first_trial: SourcedDate | null;
  years?: number;
  years_so_far?: number;
  note?: string;
}
interface RouteStep {
  step: string;
  how?: string;
  time: string;
  basis?: string;
  url?: string;
}
interface Impact {
  status?: string;
  milestone: string;
  retrospective: { title: string; summary: string; caveat: string; timelines: Timeline[] };
  existing_route: RouteStep[];
  atlas_route: RouteStep[];
  assumptions: string[];
  validate_next: string[];
  sources_checked?: { ref: string; url: string; note?: string }[];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmt(date: string) {
  const [y, m] = date.split("-");
  return m ? `${MONTHS[Number(m) - 1] ?? ""} ${y}`.trim() : y;
}

export function ImpactView() {
  return <WithGraph>{(idx) => <ImpactPage idx={idx} />}</WithGraph>;
}

function ImpactPage({ idx }: { idx: GraphIndex }) {
  const data = useDerived<Impact>("impact");
  const { start } = useTour();
  if (data.status === "loading") return <p className="mx-auto max-w-[1040px] px-8 py-16 text-sm text-ink-3">Loading…</p>;
  if (data.status === "missing") return <p className="mx-auto max-w-[1040px] px-8 py-16 text-sm text-ink-3">The impact figures (impact.json) are not available in this build.</p>;
  const d = data.data;
  const rows = Math.max(d.existing_route.length, d.atlas_route.length);

  return (
    <div className="mx-auto w-full max-w-[1040px] px-8 pb-20 pt-10">
      <p className="text-sm text-ink-3">The 10× case</p>
      <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-ink">Why this could be 10× faster</h1>
      {d.status && <p className="mt-2 text-xs text-ink-3">{d.status[0].toUpperCase() + d.status.slice(1)}.</p>}

      {/* 1. milestone */}
      <section aria-labelledby="milestone-h" className="mt-8 border-l-[3px] border-accent-700 pl-5">
        <h2 id="milestone-h" className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">
          The milestone
        </h2>
        <p className="mt-1.5 max-w-[760px] text-[20px] font-medium leading-snug text-ink">{d.milestone}</p>
      </section>

      {/* 2. retrospective timelines */}
      <section aria-labelledby="retro-h" className="mt-14">
        <h2 id="retro-h" className="text-[22px] font-semibold tracking-tight text-ink">
          {d.retrospective.title}
        </h2>
        <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-ink-2">{d.retrospective.summary}</p>
        <Timelines idx={idx} timelines={d.retrospective.timelines} />
        <p className="mt-5 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm leading-relaxed text-warn-ink">
          <span className="font-semibold">Caveat: </span>
          {d.retrospective.caveat}
        </p>
      </section>

      {/* 3. routes */}
      <section aria-labelledby="routes-h" className="mt-14">
        <h2 id="routes-h" className="text-[22px] font-semibold tracking-tight text-ink">
          Today’s route vs the atlas route
        </h2>
        <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">The same three steps a small patient group has to take, side by side.</p>
        <div className="mt-5 overflow-hidden rounded-lg border border-line">
          <div className="grid grid-cols-2 border-b border-line bg-subtle text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
            <p className="px-5 py-2.5">Today</p>
            <p className="border-l border-line px-5 py-2.5">With the atlas</p>
          </div>
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="grid grid-cols-2 border-b border-line-2 last:border-b-0">
              <RouteCell n={i + 1} step={d.existing_route[i]} />
              <div className="border-l border-line">
                <RouteCell n={i + 1} step={d.atlas_route[i]} atlas />
              </div>
            </div>
          ))}
        </div>
        {d.sources_checked && d.sources_checked.length > 0 && (
          <p className="mt-2 text-xs text-ink-3">
            Sources checked:{" "}
            {d.sources_checked.map((s, i) => (
              <span key={s.url}>
                {i > 0 && "; "}
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                  {s.ref} ↗
                </a>
                {s.note ? ` (${s.note})` : ""}
              </span>
            ))}
          </p>
        )}
      </section>

      {/* 4. assumptions and validation */}
      <section className="mt-14 grid grid-cols-1 gap-10 md:grid-cols-2">
        <div>
          <h2 className="text-[17px] font-semibold text-ink">What this assumes</h2>
          <ul className="mt-3 space-y-2.5 text-sm leading-relaxed text-ink-2">
            {d.assumptions.map((a) => (
              <li key={a} className="border-l-2 border-line pl-3">
                {a}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-[17px] font-semibold text-ink">What we must validate next</h2>
          <ol className="mt-3 space-y-2.5 text-sm leading-relaxed text-ink-2">
            {d.validate_next.map((v, i) => (
              <li key={v} className="grid grid-cols-[20px_minmax(0,1fr)] gap-1">
                <span className="tabular-nums text-ink-3">{i + 1}</span>
                <span>{v}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 5. footer */}
      <p className="mt-14 border-t border-line pt-5 text-sm text-ink-2">
        See the route in practice:{" "}
        <button type="button" onClick={() => start("maria")} className="font-medium text-accent-700 hover:underline">
          follow Maria’s VAMP2 journey →
        </button>{" "}
        <span className="text-ink-3">· or read </span>
        <Link href="/method" className="text-accent-700 hover:underline">
          how we know
        </Link>
      </p>
    </div>
  );
}

function RouteCell({ n, step, atlas = false }: { n: number; step?: RouteStep; atlas?: boolean }) {
  if (!step) return <div className="px-5 py-4" />;
  const awaiting = step.time === "BASELINE_FROM_EXPERT";
  return (
    <div className="px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <p className="text-[15px] font-medium leading-snug text-ink">
          <span className="mr-2 tabular-nums text-ink-3">{n}</span>
          {step.step}
        </p>
        <p className={`shrink-0 text-right text-sm ${awaiting ? "text-ink-3" : atlas ? "font-semibold text-accent-700" : "font-semibold text-ink"}`}>
          {awaiting ? "awaiting expert figure" : step.time}
        </p>
      </div>
      {step.how && <p className="mt-1 text-sm leading-relaxed text-ink-3">{step.how}</p>}
      {step.basis && (
        <p className="mt-1.5 text-xs leading-relaxed text-ink-3">
          Basis: {step.basis}
          {step.url && (
            <>
              {" "}
              <a href={step.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                source ↗
              </a>
            </>
          )}
        </p>
      )}
    </div>
  );
}

/** Bars on a shared axis of years since the gene was discovered. */
function Timelines({ idx, timelines }: { idx: GraphIndex; timelines: Timeline[] }) {
  const span = (t: Timeline) => t.years ?? t.years_so_far ?? 0;
  const max = Math.max(14, Math.ceil(Math.max(...timelines.map(span)) + 1));
  const pct = (y: number) => `${(100 * y) / max}%`;
  const ticks = Array.from({ length: Math.floor(max / 2) + 1 }, (_, i) => i * 2);
  return (
    <div className="mt-6" role="group" aria-label="Years from gene discovery to first trial">
      <div className="space-y-6">
        {timelines.map((t) => {
          const node = idx.nodeById.get(t.disease);
          const open = !t.first_trial;
          const years = span(t);
          const shared = !!t.note && !open;
          return (
            <div key={t.disease} className="grid grid-cols-[170px_minmax(0,1fr)] items-start gap-4">
              <div className="pt-0.5">
                <Link href={diseaseHref(t.disease)} className="text-sm font-semibold text-ink hover:text-accent-700">
                  {node?.label.replace(/-related.*$/, "") ?? t.disease.replace(/^disease:/, "")}
                </Link>
                <p className={`text-sm tabular-nums ${shared ? "font-semibold text-accent-700" : "text-ink-2"}`}>
                  {open ? `${years} years and counting` : `${years} years`}
                </p>
              </div>
              <div>
                <div className="relative h-7">
                  <div className="absolute inset-y-[13px] left-0 right-0 h-px bg-line" aria-hidden="true" />
                  <div
                    className={`absolute top-1.5 h-4 rounded-sm ${open ? "border border-dashed border-ink-3 bg-subtle" : shared ? "bg-accent-700" : "bg-ink-3"}`}
                    style={{ left: 0, width: pct(years) }}
                    aria-hidden="true"
                  />
                  {open && (
                    <span className="absolute top-1.5 text-sm leading-4 text-ink-3" style={{ left: `calc(${pct(years)} + 6px)` }} aria-hidden="true">
                      →
                    </span>
                  )}
                </div>
                <div className="relative mt-1 flex justify-between gap-3 text-xs text-ink-3">
                  <a href={t.gene_discovery.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent-700" title={t.gene_discovery.title}>
                    Gene found {fmt(t.gene_discovery.date)} · <span className="text-accent-700">{t.gene_discovery.ref} ↗</span>
                  </a>
                  {t.first_trial ? (
                    <a href={t.first_trial.url} target="_blank" rel="noopener noreferrer" className="text-right hover:text-accent-700" title={t.first_trial.title}>
                      First trial {fmt(t.first_trial.date)} · <span className="text-accent-700">{t.first_trial.ref} ↗</span>
                    </a>
                  ) : (
                    <span className="text-right">No trial yet</span>
                  )}
                </div>
                {t.note && <p className={`mt-1 text-xs leading-relaxed ${shared ? "text-accent-900" : "text-ink-3"}`}>{t.note}</p>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 grid grid-cols-[170px_minmax(0,1fr)] gap-4" aria-hidden="true">
        <span className="text-[11px] text-ink-3">years since the gene was found</span>
        <div className="relative h-4 border-t border-line">
          {ticks.map((y) => (
            <span key={y} className="absolute top-1 -translate-x-1/2 text-[11px] tabular-nums text-ink-3" style={{ left: pct(y) }}>
              {y}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
