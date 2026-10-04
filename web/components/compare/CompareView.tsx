"use client";

import { CompareFactors } from "../factors/CompareFactors";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { Term } from "../Term";
import { EvidenceChip, WarnGlyph } from "../evidence/EvidenceBits";
import { AiAction } from "../ai/AiAction";
import { compareDiseases, spectrumWords, SPECTRUM_WHY, type CompareItem, type Comparison, type SideMechanism, type Spectrum } from "@/lib/compare";
import { clusterColor } from "@/lib/style";
import { clusterSlot, compareHref, diseaseHref, diseaseIdFromParam, type GraphIndex } from "@/lib/graph";
import { REUSE_META } from "@/lib/insights";
import { ASSET_KIND_LABEL, TYPE_LABEL, plural } from "@/lib/text";

export function CompareView() {
  return <WithGraph>{(idx) => <Compare idx={idx} />}</WithGraph>;
}

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

function Compare({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const router = useRouter();
  const a = params.get("a") ? diseaseIdFromParam(params.get("a")!) : "";
  const b = params.get("b") ? diseaseIdFromParam(params.get("b")!) : "";
  const diseases = useMemo(() => idx.graph.nodes.filter((n) => n.type === "disease").sort((x, y) => x.label.localeCompare(y.label)), [idx]);
  const c = useMemo(() => (a && b ? compareDiseases(idx, a, b) : null), [idx, a, b]);
  const set = (na: string, nb: string) => router.replace(compareHref(na, nb), { scroll: false });

  return (
    <div className="mx-auto w-full max-w-[1120px] px-8 pb-24 pt-8">
      <nav aria-label="Breadcrumb" className="text-xs text-ink-3">
        <Link href="/atlas" className="hover:text-ink">
          Atlas
        </Link>
        <span className="mx-1.5">/</span>
        <span>Compare</span>
      </nav>
      <h1 className="mt-3 text-[30px] font-semibold tracking-[-0.02em] text-ink">Before we join forces</h1>
      <p className="mt-2 max-w-[720px] text-[15px] leading-relaxed text-ink-3">
        Two diseases side by side: what you share, what differs, what already exists for both, and which questions an expert should answer
        first.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3" data-tour="compare-picker">
        <Picker label="Your disease" value={a} options={diseases} onChange={(v) => set(v, b || diseases.find((d) => d.id !== v)?.id || v)} />
        <button
          type="button"
          onClick={() => a && b && set(b, a)}
          className="mb-0.5 h-9 rounded-md border border-line px-3 text-sm text-ink-2 hover:border-accent-500"
          aria-label="Swap the two diseases"
        >
          ⇄
        </button>
        <Picker label="Compared with" value={b} options={diseases} onChange={(v) => set(a || diseases.find((d) => d.id !== v)?.id || v, v)} />
      </div>

      {!a || !b ? (
        <p className="mt-10 text-sm text-ink-3">Pick two diseases to compare.</p>
      ) : !c ? (
        <p className="mt-10 rounded-lg border border-dashed border-ink-4 px-5 py-4 text-sm text-ink-2">Pick two different diseases from the atlas.</p>
      ) : (
        <>
          <CompareFactors idx={idx} a={a} b={b} />
          <CompareBody idx={idx} c={c} />
        </>
      )}
    </div>
  );
}

function Picker({ label, value, options, onChange }: { label: string; value: string; options: { id: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <label className="min-w-[280px] flex-1">
      <span className="mb-1.5 block text-xs font-medium text-ink-3">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink focus:border-accent-700 focus:outline-none"
      >
        <option value="" disabled>
          Choose a disease
        </option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function CompareBody({ idx, c }: { idx: GraphIndex; c: Comparison }) {
  const A = c.shortA;
  const B = c.shortB;
  const distinctiveShared = c.sharedSymptoms.filter((s) => s.distinctive);
  const broadShared = c.sharedSymptoms.filter((s) => !s.distinctive);
  const [showBroad, setShowBroad] = useState(false);

  return (
    <>
      <nav aria-label="Summary" className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-5">
        {[
          [c.shared.length, "shared mechanisms"],
          [distinctiveShared.length, "distinctive shared symptoms"],
          [c.assets.both.length, "resources covering both"],
          [c.studiesBoth.length, "studies enrolling both"],
          [c.connectors.length, "people and groups linked to both"],
        ].map(([n, l]) => (
          <div key={l as string} className="bg-white px-4 py-3">
            <p className="text-2xl font-semibold tabular-nums text-ink">{n}</p>
            <p className="text-xs text-ink-3">{l}</p>
          </div>
        ))}
      </nav>

      <div className="mt-12 space-y-14">
        {/* 1 */}
        <section aria-labelledby="share-h" data-tour="compare-share">
          <p className={EYEBROW}>1</p>
          <h2 id="share-h" className={`mt-1 ${H2}`}>
            What we share
          </h2>
          <div className="mt-5 space-y-6">
            <Block title="Mechanisms">
              {c.shared.length ? (
                <ul className="space-y-2">
                  {c.shared.map((s) => (
                    <li key={s.mechanism.id} className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                      <span className="text-[15px] text-ink">
                        <Term>{s.mechanism.label}</Term>
                      </span>
                      <MechChip side={s.a} label={A} />
                      <MechChip side={s.b} label={B} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Muted>No shared mechanism in the current evidence.</Muted>
              )}
            </Block>
            <Block title="Distinctive symptoms in both">
              {distinctiveShared.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {distinctiveShared.map((s) => (
                    <EvidenceChip key={s.phenotype.id} edge={s.edgeB} label={s.phenotype.label} />
                  ))}
                </div>
              ) : (
                <Muted>No distinctive symptom recorded in both.</Muted>
              )}
              {broadShared.length > 0 && (
                <div className="mt-2">
                  <button type="button" onClick={() => setShowBroad(!showBroad)} className="text-xs font-medium text-accent-700 hover:underline">
                    {showBroad ? "Hide" : "Show"} {plural(broadShared.length, "broad symptom")} also in both (common across many conditions)
                  </button>
                  {showBroad && (
                    <div className="mt-2 flex flex-wrap gap-1.5 opacity-80">
                      {broadShared.map((s) => (
                        <EvidenceChip key={s.phenotype.id} edge={s.edgeB} label={`${s.phenotype.label} · broad`} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Block>
            <Block title="Clusters">
              {c.clusters.both.length ? (
                <ul className="flex flex-wrap gap-2">
                  {c.clusters.both.map((cl) => (
                    <li key={cl.id} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-sm text-ink-2">
                      <span className="h-2 w-2 rounded-full" style={{ background: clusterColor(clusterSlot(idx, cl.id)) }} aria-hidden="true" />
                      {cl.label.split(":")[0]}
                    </li>
                  ))}
                </ul>
              ) : (
                <Muted>Not in the same mechanism cluster.</Muted>
              )}
            </Block>
          </div>
        </section>

        {/* 2 */}
        <section aria-labelledby="differs-h" data-tour="compare-differs">
          <p className={EYEBROW}>2</p>
          <h2 id="differs-h" className={`mt-1 ${H2}`}>
            What differs
          </h2>
          <div className="mt-5 grid grid-cols-1 gap-x-10 gap-y-6 md:grid-cols-2">
            {([
              ["a", c.a.disease.label, c.onlyA, c.onlyASymptoms],
              ["b", c.b.disease.label, c.onlyB, c.onlyBSymptoms],
            ] as const).map(([k, name, mechs, syms]) => (
              <div key={k} className="space-y-5">
                <p className="text-[15px] font-semibold text-ink">Only in {name}</p>
                <Block title="Mechanisms">
                  {mechs.length ? (
                    <ul className="space-y-1.5">
                      {mechs.map((m) => (
                        <li key={m.link.mechanism.id} className="flex flex-wrap items-center gap-2">
                          <Term>{m.link.mechanism.label}</Term>
                          {(m.minority || m.contested) && (
                            <span className="inline-flex items-center gap-1 rounded border border-warn-line bg-warn-bg px-1.5 py-px text-[11px] font-medium text-warn-ink">
                              <WarnGlyph size={9} /> {m.minority ? "minority view" : "contested"}
                            </span>
                          )}
                          <EvidenceChip edge={m.edge} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Muted>None.</Muted>
                  )}
                </Block>
                <Block title="Distinctive symptoms">
                  {syms.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {syms.slice(0, 8).map((s) => (
                        <EvidenceChip key={s.phenotype.id} edge={s.edge} label={s.phenotype.label} />
                      ))}
                      {syms.length > 8 && <span className="self-center text-xs text-ink-3">and {syms.length - 8} more</span>}
                    </div>
                  ) : (
                    <Muted>None recorded.</Muted>
                  )}
                </Block>
              </div>
            ))}
          </div>
          <dl className="mt-8 divide-y divide-line-2 border-y border-line-2">
            <Row k="Inheritance" a={c.inheritance.a} b={c.inheritance.b} A={A} B={B} differs={c.inheritance.differs} />
            <Row k="Usual onset" a={c.onset.a} b={c.onset.b} A={A} B={B} differs={c.onset.differs} />
            <div className="grid grid-cols-1 gap-3 py-3 md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)]">
              <dt className="text-sm text-ink-3">
                Gene changes seen
                {c.spectrum.differs && <span className="mt-1 block text-xs font-medium text-warn-ink">differs</span>}
              </dt>
              <dd>
                <SpectrumBar s={c.spectrum.a} label={A} />
              </dd>
              <dd>
                <SpectrumBar s={c.spectrum.b} label={B} />
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-sm leading-relaxed text-ink-3">{SPECTRUM_WHY}</p>
        </section>

        {/* 3 */}
        <section aria-labelledby="assets-h">
          <p className={EYEBROW}>3</p>
          <h2 id="assets-h" className={`mt-1 ${H2}`}>
            What already exists
          </h2>
          <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <AssetColumn title="Covers both" items={c.assets.both} empty="No resource covers both yet." />
            <AssetColumn title={`Covers ${A} only`} subtitle={`Could it work for ${B}?`} items={c.assets.aOnly} empty={`Nothing specific to ${A}.`} />
            <AssetColumn title={`Covers ${B} only`} subtitle={`Could it work for ${A}?`} items={c.assets.bOnly} empty={`Nothing specific to ${B}.`} />
          </div>
        </section>

        {/* 4 */}
        <section aria-labelledby="studies-h">
          <p className={EYEBROW}>4</p>
          <h2 id="studies-h" className={`mt-1 ${H2}`}>
            Studies enrolling both
          </h2>
          {c.studiesBoth.length ? (
            <ul className="mt-5 space-y-2.5">
              {c.studiesBoth.map((s) => (
                <li key={s.node.id} className="rounded-lg border border-line px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <p className="text-[15px] font-medium text-ink">{s.node.label}</p>
                    <span className="flex gap-1.5">
                      {s.edgeA && <EvidenceChip edge={s.edgeA} label={A} />}
                      {s.edgeB && <EvidenceChip edge={s.edgeB} label={B} />}
                    </span>
                  </div>
                  {s.node.type === "study" && (
                    <p className="mt-1 text-xs text-ink-3">
                      {[s.node.attrs?.study_type, s.node.attrs?.sponsor, s.node.attrs?.status].filter(Boolean).join(" · ")}
                    </p>
                  )}
                  {s.node.type === "study" && s.node.attrs?.eligibility_note && (
                    <p className="mt-2 text-sm leading-relaxed text-ink-2">
                      <span className="text-ink-3">Eligibility: </span>
                      {s.node.attrs.eligibility_note}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Muted className="mt-4">No registered study enrols both in the sources searched.</Muted>
          )}
        </section>

        {/* 5 */}
        <section aria-labelledby="people-h">
          <p className={EYEBROW}>5</p>
          <h2 id="people-h" className={`mt-1 ${H2}`}>
            People and groups already connected to both
          </h2>
          <p className="mt-2 text-sm text-ink-3">Patient groups, researchers and grants linked to both diseases. Professional public information only.</p>
          {c.connectors.length ? (
            <ul className="mt-5 grid grid-cols-1 gap-2.5 md:grid-cols-2">
              {c.connectors.slice(0, 12).map((x) => (
                <li key={x.node.id} className="rounded-lg border border-line px-4 py-3">
                  <p className="flex items-center gap-2 text-sm font-medium text-ink">
                    <NodeTypeIcon type={x.node.type} size={11} />
                    {x.node.label}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-3">
                    {TYPE_LABEL[x.node.type]?.one}
                    {x.node.type === "researcher" && x.node.attrs?.affiliation ? ` · ${x.node.attrs.affiliation}` : ""}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <EvidenceChip edge={x.linksA[0]} label={A} />
                    <EvidenceChip edge={x.linksB[0]} label={B} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Muted className="mt-4">No person or group is linked to both yet.</Muted>
          )}
          {c.connectors.length > 12 && <p className="mt-2 text-xs text-ink-3">and {c.connectors.length - 12} more</p>}
        </section>

        {/* 6 */}
        <section aria-labelledby="questions-h" className="rounded-lg border-2 border-ink px-6 py-5" data-tour="compare-questions">
          <p className={EYEBROW}>6</p>
          <h2 id="questions-h" className={`mt-1 ${H2}`}>
            Questions an expert should answer before joining forces
          </h2>
          <p className="mt-1 text-sm text-ink-3">Generated from the differences above, using fixed templates. Each one links to the evidence it is about.</p>
          {c.questions.length ? (
            <div className="mt-4 space-y-4">
              {(["Biology", "Who can take part", "Measuring progress", "Practical checks"] as const).map((topic) => {
                const list = c.questions.filter((q) => q.topic === topic);
                if (!list.length) return null;
                return (
                  <div key={topic}>
                    <p className="text-sm font-semibold text-ink">{topic}</p>
                    <ol className="mt-1.5 space-y-2">
                      {list.map((q) => (
                        <li key={q.text} className="text-[15px] leading-relaxed text-ink-2">
                          {q.text}{" "}
                          {q.edgeIds.slice(0, 4).map((id) => {
                            const e = idx.edgeById.get(id);
                            return e ? <EvidenceChip key={id} edge={e} className="ml-1 align-middle" /> : null;
                          })}
                        </li>
                      ))}
                    </ol>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-4 text-sm text-ink-2">No differences were found that need an expert’s view, which usually means the data is thin, not that the diseases are the same.</p>
          )}
          <div className="mt-6 border-t border-line pt-4">
            <AiAction
              key={`${c.a.disease.id}|${c.b.disease.id}`}
              idx={idx}
              kind="compare-questions"
              payload={{ a: c.a.disease.id, b: c.b.disease.id }}
              label="Sharpen these questions with AI"
              busyLabel="Writing…"
            />
          </div>
          <p className="mt-4 text-xs text-ink-3">
            <Link href={diseaseHref(c.a.disease.id)} className="text-accent-700 hover:underline">
              Back to {c.a.disease.label}
            </Link>
          </p>
        </section>
      </div>
    </>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-[180px_minmax(0,1fr)]">
      <p className="pt-0.5 text-sm text-ink-3">{title}</p>
      <div>{children}</div>
    </div>
  );
}

function Muted({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`text-sm text-ink-3 ${className}`}>{children}</p>;
}

function MechChip({ side, label }: { side: SideMechanism; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <EvidenceChip edge={side.edge} label={label} />
      {side.minority && <span className="text-[11px] font-medium text-warn-ink">minority view</span>}
    </span>
  );
}

function Row({ k, a, b, A, B, differs }: { k: string; a: string | null; b: string | null; A: string; B: string; differs: boolean }) {
  return (
    <div className="grid grid-cols-1 gap-3 py-3 text-sm md:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)]">
      <dt className="text-ink-3">
        {k}
        {differs && <span className="mt-1 block text-xs font-medium text-warn-ink">differs</span>}
      </dt>
      <dd className="text-ink">
        <span className="text-xs text-ink-3">{A}: </span>
        {a ?? "Not recorded"}
      </dd>
      <dd className="text-ink">
        <span className="text-xs text-ink-3">{B}: </span>
        {b ?? "Not recorded"}
      </dd>
    </div>
  );
}

const SPECTRUM_COLORS: Record<string, string> = { truncating: "#153e67", missense: "#4f7fb3", splice: "#a8c1dd" };

function SpectrumBar({ s, label }: { s: Spectrum | null; label: string }) {
  if (!s) return <p className="text-sm text-ink-3">{label}: no ClinVar summary</p>;
  return (
    <div>
      <p className="text-sm text-ink">
        <span className="text-xs text-ink-3">{label}: </span>
        {spectrumWords(s)}
      </p>
      <div className="mt-1.5 flex h-2 w-full max-w-[280px] overflow-hidden rounded-full bg-line-2" aria-hidden="true">
        {(["truncating", "missense", "splice"] as const).map((k) => (
          <span key={k} style={{ width: `${s.share[k] * 100}%`, background: SPECTRUM_COLORS[k] }} />
        ))}
      </div>
      <p className="mt-1 text-[11px] text-ink-3">
        {(["truncating", "missense", "splice"] as const).map((k) => `${k} ${s.counts[k]}`).join(" · ")}
        {s.counts["large deletions"] ? ` · large deletions ${s.counts["large deletions"]}` : ""} (ClinVar)
      </p>
    </div>
  );
}

function AssetColumn({ title, subtitle, items, empty }: { title: string; subtitle?: string; items: CompareItem[]; empty: string }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 5);
  return (
    <div>
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      {subtitle && <p className="text-xs text-ink-3">{subtitle}</p>}
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {shown.map((it) => {
            const kind = it.node.type === "asset" && it.node.attrs?.kind ? ASSET_KIND_LABEL[it.node.attrs.kind] : TYPE_LABEL[it.node.type]?.one;
            const reuse = it.reuse?.reuse;
            return (
              <li key={it.node.id} className="rounded-lg border border-line px-3.5 py-3">
                <p className="text-xs text-ink-3">{kind}</p>
                <p className="mt-0.5 text-sm font-medium leading-snug text-ink">{it.node.label}</p>
                {subtitle && (
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-2">
                    <span
                      className={`mr-1.5 inline-flex rounded border px-1.5 py-px text-[11px] font-medium ${
                        reuse === "adaptable"
                          ? "border-accent-200 bg-accent-50 text-accent-900"
                          : reuse === "as_is"
                            ? "border-[#bcd9c6] bg-[#edf6f0] text-ok"
                            : "border-line bg-subtle text-ink-3"
                      }`}
                    >
                      {reuse === "adaptable" ? "Could be adapted" : reuse ? REUSE_META[reuse].label : "Not directly applicable"}
                    </span>
                    {it.reuse?.reason ?? ""}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {it.edgeA && <EvidenceChip edge={it.edgeA} label="Source" />}
                  {!it.edgeA && it.edgeB && <EvidenceChip edge={it.edgeB} label="Source" />}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-ink-3">{empty}</p>
      )}
      {items.length > 5 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-sm font-medium text-accent-700 hover:underline">
          {all ? "Show fewer" : `Show ${items.length - 5} more`}
        </button>
      )}
    </div>
  );
}
