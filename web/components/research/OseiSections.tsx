"use client";

// Dr. Osei's additions to a disease page (docs/persona-spec.md): patient population, trial readiness and
// how to reach patients for a study. Data: population/{prevalence,readiness,channels}.json + the graph.
import { AiAction } from "../ai/AiAction";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { investigatorsFor } from "@/lib/glance";
import type { GraphIndex } from "@/lib/graph";
import {
  CHANNEL_LABEL,
  READINESS_LABEL,
  loadChannels,
  loadPrevalence,
  loadReadiness,
  peopleRange,
  type Channel,
  type ChannelsFile,
  type PrevalenceFile,
  type ReadinessFile,
  type ReadinessStatus,
} from "@/lib/population";
import { useResource } from "@/lib/resource";
import type { AtlasNode } from "@/lib/types";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

export function OseiSections({ idx, node }: { idx: GraphIndex; node: AtlasNode }) {
  return (
    <>
      <Population idx={idx} node={node} />
      <Readiness idx={idx} node={node} />
      <Reach idx={idx} node={node} />
    </>
  );
}

function Chips({ idx, edges, max = 4 }: { idx: GraphIndex; edges: string[]; max?: number }) {
  const list = edges.map((e) => idx.edgeById.get(e)).filter((e): e is NonNullable<typeof e> => !!e);
  if (!list.length) return null;
  return (
    <span className="flex flex-wrap gap-1.5">
      {list.slice(0, max).map((e) => (
        <EvidenceChip key={e.id} edge={e} label={idx.nodeById.get(e.source === node(e) ? e.target : e.source)?.label.slice(0, 32)} className="min-h-[24px] px-2 py-0.5" />
      ))}
      {list.length > max && <span className="self-center text-xs text-ink-3">+{list.length - max}</span>}
    </span>
  );
  function node(e: { source: string; target: string }) {
    return e.source.startsWith("disease:") ? e.source : e.target;
  }
}

function Population({ idx, node }: { idx: GraphIndex; node: AtlasNode }) {
  const prev = useResource<PrevalenceFile | null>("pop:prevalence", loadPrevalence);
  const dp = prev?.data?.deep[node.id];
  const est = dp?.estimated_people;
  // ClinVar groups: "21 of 35 pathogenic or likely-pathogenic ClinVar records for VAMP2 fall in this group."
  const gene = (idx.adjacency.get(node.id) ?? []).find((n) => n.edge.type === "causes" && n.dir === "in")?.other;
  const vgs = gene
    ? (idx.adjacency.get(gene) ?? [])
        .filter((n) => n.edge.type === "variant_in" && n.dir === "in")
        .map((n) => idx.nodeById.get(n.other))
        .filter((v): v is AtlasNode => !!v)
        .map((v) => {
          const m = v.summary?.match(/(\d+) of (\d+) pathogenic/);
          return { label: v.label.split(": ").slice(1).join(": ") || v.label, n: m ? Number(m[1]) : null, of: m ? Number(m[2]) : null };
        })
        .sort((a, b) => (b.n ?? 0) - (a.n ?? 0))
    : [];
  const studies = (idx.adjacency.get(node.id) ?? [])
    .filter((n) => n.edge.type === "studies" && n.dir === "in")
    .map((n) => ({ s: idx.nodeById.get(n.other)!, e: n.edge }))
    .map(({ s, e }) => ({ s, e, a: (s.attrs ?? {}) as { enrollment?: number; status?: string; study_type?: string; phase?: string } }))
    .filter((x) => typeof x.a.enrollment === "number")
    .sort((a, b) => (b.a.enrollment ?? 0) - (a.a.enrollment ?? 0));
  const enrolled = studies.reduce((n, x) => n + (x.a.enrollment ?? 0), 0);
  return (
    <section aria-labelledby="pop-h" className="max-w-[920px]">
      <p className={EYEBROW}>For researchers</p>
      <h2 id="pop-h" className={`mt-1 ${H2}`}>
        Patient population
      </h2>
      {prev?.status === "loading" ? (
        <p className="mt-3 text-sm text-ink-3">Loading prevalence…</p>
      ) : !dp ? (
        <p className="mt-3 text-sm text-ink-3">Prevalence data not available yet.</p>
      ) : (
        <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div className="rounded-lg border border-line px-4 py-3">
            <p className="text-xs font-medium text-ink-3">Estimated affected (rough range, not a count)</p>
            <dl className="mt-2 space-y-1 text-sm">
              {(["worldwide", "europe", "us"] as const).map((k) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-ink-3">{k === "us" ? "US" : k[0].toUpperCase() + k.slice(1)}</dt>
                  <dd className="tabular-nums text-ink">{est?.[k] ? (est[k]!.text ?? peopleRange(est[k])) : "not estimable"}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs leading-relaxed text-ink-3">
              Basis: {dp.estimate_basis.join(", ") || "no usable prevalence class"}. Orphanet class bounds × population.
            </p>
          </div>
          <div className="rounded-lg border border-line px-4 py-3">
            <p className="text-xs font-medium text-ink-3">Prevalence records (Orphanet)</p>
            <ul className="mt-2 space-y-1.5 text-sm">
              {dp.entities.flatMap((e) => e.records.map((r, i) => ({ e, r, i }))).slice(0, 8).map(({ e, r, i }) => (
                <li key={`${e.orpha}-${i}`} className="flex flex-wrap gap-x-2 text-ink-2">
                  <span className="text-ink">{r.type}</span>
                  {r.class && <span>{r.class}</span>}
                  {r.n_reported != null && <span>{r.n_reported} reported</span>}
                  {r.area && <span className="text-ink-3">{r.area}</span>}
                  <a href={e.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                    {r.source ?? "Orphanet"} ↗
                  </a>
                </li>
              ))}
              {!dp.entities.some((e) => e.records.length) && <li className="text-ink-3">No prevalence record for this disease’s Orphanet entities.</li>}
            </ul>
          </div>
        </div>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-line px-4 py-3">
          <p className="text-xs font-medium text-ink-3">ClinVar pathogenic variants by type</p>
          {vgs.length ? (
            <ul className="mt-2 space-y-1 text-sm">
              {vgs.map((v) => (
                <li key={v.label} className="flex justify-between gap-3">
                  <span className="text-ink-2">{v.label}</span>
                  <span className="tabular-nums text-ink">{v.n != null ? `${v.n} of ${v.of}` : "—"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-ink-3">No variant groups recorded.</p>
          )}
        </div>
        <div className="rounded-lg border border-line px-4 py-3">
          <p className="text-xs font-medium text-ink-3">Enrollment in existing studies</p>
          {studies.length ? (
            <>
              <p className="mt-1 text-sm text-ink">
                {enrolled.toLocaleString("en-US")} planned or actual participants across {studies.length} studies (overlap possible)
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {studies.slice(0, 4).map(({ s, e, a }) => (
                  <li key={s.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-ink-2" title={s.label}>
                      {s.label}
                    </span>
                    <span className="flex shrink-0 items-center gap-2 tabular-nums text-ink">
                      {a.enrollment}
                      <EvidenceChip edge={e} label={a.status?.toLowerCase().replace(/_/g, " ")} className="min-h-[22px] px-1.5 py-0" />
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-2 text-sm text-ink-3">No study enrollment recorded.</p>
          )}
        </div>
      </div>
    </section>
  );
}

const MARK: Record<ReadinessStatus, { glyph: string; cls: string; word: string }> = {
  yes: { glyph: "✓", cls: "border-ok/40 bg-white text-ok", word: "in place" },
  partial: { glyph: "◐", cls: "border-warn-line bg-warn-bg text-warn-ink", word: "partial" },
  no: { glyph: "–", cls: "border-line bg-subtle text-ink-3", word: "gap" },
};

function Readiness({ idx, node }: { idx: GraphIndex; node: AtlasNode }) {
  const r = useResource<ReadinessFile | null>("pop:readiness", loadReadiness);
  const d = r?.data?.diseases[node.id];
  return (
    <section aria-labelledby="ready-h" className="max-w-[920px]">
      <h2 id="ready-h" className={H2}>
        Trial readiness
      </h2>
      {r?.status === "loading" ? (
        <p className="mt-3 text-sm text-ink-3">Loading…</p>
      ) : !d ? (
        <p className="mt-3 text-sm text-ink-3">Trial-readiness scorecard not available yet.</p>
      ) : (
        <>
          <p className="mt-1.5 text-sm text-ink-3">
            {d.tally} of {d.tally_of} in place (yes = 1, partial = ½). A description of what the atlas holds, not a prediction.
          </p>
          <ul className="mt-4 divide-y divide-line-2 border-y border-line-2">
            {Object.entries(d.components).map(([k, c]) => {
              const m = MARK[c.status] ?? MARK.no;
              return (
                <li key={k} className="grid gap-2 py-2.5 sm:grid-cols-[220px_minmax(0,1fr)] sm:items-start">
                  <span className="flex items-center gap-2 text-sm text-ink">
                    <span className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${m.cls}`} aria-label={m.word}>
                      {m.glyph}
                    </span>
                    {READINESS_LABEL[k] ?? k}
                  </span>
                  <span className="space-y-1.5">
                    <span className="block text-sm text-ink-2">
                      {c.note}
                      {c.highest_phase ? ` · highest phase ${c.highest_phase}` : ""}
                    </span>
                    <Chips idx={idx} edges={c.edges} />
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

const REACH_ORDER = ["registry", "natural_history_study", "data_platform", "biobank", "research_network", "consortium", "patient_org", "recruiting_trial"];

function Reach({ idx, node }: { idx: GraphIndex; node: AtlasNode }) {
  const ch = useResource<ChannelsFile | null>("pop:channels", loadChannels);
  const by = ch?.data?.by_disease[node.id];
  const find = (id: string): Channel | undefined => ch?.data?.channels.find((c) => c.id === id);
  const inv = investigatorsFor(idx, node.id);
  const byInst = new Map<string, number>();
  for (const p of inv.people) if (p.institution) byInst.set(p.institution, (byInst.get(p.institution) ?? 0) + 1);
  const insts = [...byInst].sort((a, b) => b[1] - a[1]);
  return (
    <section aria-labelledby="reach-h" className="max-w-[920px]">
      <h2 id="reach-h" className={H2}>
        Reach patients for a study
      </h2>
      <p className="mt-1.5 text-sm text-ink-3">
        Organisational channels only: registries with research access, patient organisations’ research contacts, active groups and trial sponsors.
        No personal contact details are collected or shown.
      </p>
      {ch?.status === "loading" ? (
        <p className="mt-3 text-sm text-ink-3">Loading…</p>
      ) : !by ? (
        <p className="mt-3 text-sm text-ink-3">Recruitment channels not available yet.</p>
      ) : (
        <div className="mt-4 space-y-5">
          {REACH_ORDER.filter((t) => by[t]?.length).map((t) => (
            <div key={t}>
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
                {CHANNEL_LABEL[t] ?? t} <span className="font-normal normal-case tracking-normal">{by[t].length}</span>
              </p>
              <ul className="mt-2 space-y-2">
                {[...new Set(by[t])]
                  .map(find)
                  .filter((c): c is Channel => !!c)
                  .slice(0, t === "patient_org" || t === "recruiting_trial" ? 6 : 8)
                  .map((c) => (
                    <li key={c.id} className="rounded-md border border-line px-3 py-2 text-sm">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <span className="font-medium text-ink">{c.name}</span>
                        <span className="text-xs text-ink-3">
                          {[c.country, c.phase, c.status?.toLowerCase().replace(/_/g, " "), c.layer?.startsWith("scale") ? "directory match" : null].filter(Boolean).join(" · ")}
                        </span>
                      </div>
                      {c.how_to_reach && <p className="mt-0.5 text-ink-2">{c.how_to_reach}</p>}
                      <div className="mt-1 flex flex-wrap gap-x-3 text-xs">
                        {c.url && (
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                            {t === "recruiting_trial" ? "ClinicalTrials.gov record" : "Website"} ↗
                          </a>
                        )}
                        {(c.reach_links ?? [])
                          .filter((l) => l.kind !== "contact")
                          .filter((l, i, all) => all.findIndex((x) => x.url === l.url) === i)
                          .map((l) => (
                            <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                              {l.kind} page ↗
                            </a>
                          ))}
                      </div>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
          {insts.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-3">
                Active investigators by institution <span className="font-normal normal-case tracking-normal">{insts.length}</span>
              </p>
              <p className="mt-1.5 text-sm text-ink-2">
                {insts
                  .slice(0, 10)
                  .map(([i, n]) => (n > 1 ? `${i} (${n})` : i))
                  .join(" · ")}
              </p>
            </div>
          )}
        </div>
      )}
      <div className="mt-5">
        <AiAction idx={idx} kind="outreach" payload={{ id: node.id }} label="Draft an outreach message" busyLabel="Drafting…" />
        <p className="mt-1.5 text-xs text-ink-3">
          Writes to the patient organisation proposing a study, citing the atlas. It never asks for personal data.
        </p>
        <p className="mt-3 text-sm text-ink-2">
          Have an approved study?{" "}
          <a href="/me#rt-h" className="font-medium text-accent-700 hover:underline">
            Announce it to this community, see anonymous member counts or request contact →
          </a>
        </p>
      </div>
    </section>
  );
}
