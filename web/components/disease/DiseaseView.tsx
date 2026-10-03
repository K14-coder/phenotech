"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { Term } from "../Term";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { SearchBox } from "../search/SearchBox";
import { ProposalDraft } from "./ProposalDraft";
import { ContributedBadge, contributionsOf } from "../ContributedBadge";
import { BiotechNeed, ResearcherMechanisms } from "./PersonaSections";
import { IdeasSection, LookAlikes, PatternBreaks, VariantHint } from "./DerivedSections";
import { usePersona, type Persona } from "@/lib/persona";
import { DevonDisease } from "../devon/DevonDisease";
import { OseiSections } from "../research/OseiSections";
import { DisMechForAtlas } from "../global/MechanismBits";
import { atlasHref, clustersOf, clusterSlot, compareHref, diseaseHref, diseaseIdFromParam, pathHref, type GraphIndex } from "@/lib/graph";
import {
  REUSE_META,
  closestDiseases,
  diseaseContext,
  existingWork,
  gapsForDisease,
  communitiesFor,
  overlapWord,
  relatedOrgsFor,
  therapiesFor,
  researcherPartners,
  suggestNextStep,
  type DiseaseContext,
  type DiseaseMatch,
  type ExistingItem,
  type ExistingItemLite,
  type OrgPartner,
  type Reuse,
} from "@/lib/insights";
import { clusterColor } from "@/lib/style";
import { ASSET_KIND_LABEL, THERAPY_MODALITY_LABEL, THERAPY_STAGE_LABEL, isPlaceholderUrl, joinList, lowerFirst, plural, relationName } from "@/lib/text";
import type { AtlasNode, Gap } from "@/lib/types";

export function DiseaseView({ param }: { param: string }) {
  return <WithGraph>{(idx) => <DiseaseByProfile idx={idx} id={diseaseIdFromParam(param)} />}</WithGraph>;
}

/** Devon gets his own plain page (the detailed one sits under "Learn more"); the others share the action page. */
function DiseaseByProfile({ idx, id }: { idx: GraphIndex; id: string }) {
  const persona = usePersona();
  const node = idx.nodeById.get(id);
  if (persona === "family" && node?.type === "disease")
    return <DevonDisease key={id} idx={idx} node={node} learnMore={<Disease idx={idx} id={id} as="leader" embedded />} />;
  return <Disease idx={idx} id={id} as={persona} />;
}

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

function Disease({ idx, id, as: persona, embedded = false }: { idx: GraphIndex; id: string; as: Persona; embedded?: boolean }) {
  const node = idx.nodeById.get(id);
  const data = useMemo(() => {
    if (!node || node.type !== "disease") return null;
    const ctx = diseaseContext(idx, id)!;
    const matches = closestDiseases(idx, id, 6);
    const items = existingWork(idx, id, matches);
    const community = communitiesFor(idx, id);
    const ownOrgs = community.specific;
    const relatedOrgs = relatedOrgsFor(idx, matches, [...community.specific, ...community.umbrella]);
    const researchers = researcherPartners(idx, id, matches);
    const gaps = gapsForDisease(idx, ctx);
    const step = suggestNextStep(idx, node, matches, items, ownOrgs, researchers, gaps);
    const therapies = therapiesFor(idx, id);
    return { ctx, matches, items, ownOrgs, umbrellaOrgs: community.umbrella, registries: community.registries, relatedOrgs, researchers, gaps, step, therapies };
  }, [idx, id, node]);

  if (!node || node.type !== "disease" || !data) return <NotFound id={id} />;
  const { ctx, matches, items, ownOrgs, umbrellaOrgs, registries, relatedOrgs, researchers, gaps, step, therapies } = data;
  const short = ctx.genes[0]?.label ?? node.label;
  const nextPartner = matches.find((m) => m.sharedMechanisms.length) ?? matches[0];
  const genes = ctx.genes.map((g) => g.label);
  const mechs = [...ctx.mechanisms.values()].sort((a, b) => b.strength - a.strength);
  const clusters = clustersOf(idx, id);
  const searched = gaps.flatMap((g) => g.searched);
  const searchedList = searched.length ? [...new Set(searched)] : idx.graph.meta.sources.map((s) => s.name);

  return (
    <div className={embedded ? "pb-6" : "pb-24"}>
      {/* Header: summary first */}
      <header className={`border-b border-line ${embedded ? "hidden" : ""}`}>
        <div className="mx-auto max-w-[1120px] px-8 pb-8 pt-7">
          <nav aria-label="Breadcrumb" className="text-xs text-ink-3">
            <Link href="/atlas" className="hover:text-ink">
              Atlas
            </Link>
            <span className="mx-1.5">/</span>
            <span>Diseases</span>
          </nav>
          <div className="mt-4 flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-[700px]">
              <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-ink">{node.label}</h1>
              <p className="mt-1.5 text-sm text-ink-3">
                {genes.length ? <>Caused by changes in the {joinList(genes)} gene</> : "Gene not recorded"}
                {node.synonyms?.length ? <> · Also called {node.synonyms.slice(0, 3).join(", ")}</> : null}
              </p>
              {node.summary && <p className="mt-4 text-base leading-relaxed text-ink-2">{node.summary}</p>}
              {mechs.length > 0 && (
                <div className="mt-5" data-tour="mechanisms">
                  <p className="text-xs font-medium text-ink-3">How it happens in the body</p>
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {mechs.slice(0, 4).map((m) => (
                      <li key={m.mechanism.id} className="inline-flex items-center gap-2 rounded-md border border-line px-2.5 py-1 text-sm text-ink">
                        <Term>{m.mechanism.label}</Term>
                        <EvidenceChip edge={m.edges[m.edges.length - 1]} className="!border-0 !px-0 !py-0" />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <dl className="w-full shrink-0 divide-y divide-line-2 rounded-lg border border-line px-4 lg:w-[300px]">
              <FactRow k="Inheritance">{node.attrs?.inheritance ?? "Not recorded"}</FactRow>
              {node.attrs?.onset && <FactRow k="Usual onset">{node.attrs.onset}</FactRow>}
              <FactRow k="Approved treatment">
                {node.attrs?.approved_treatment === true ? "Yes" : node.attrs?.approved_treatment === false ? "None known" : "Not recorded"}
              </FactRow>
              <FactRow k="Patient group">
                {ownOrgs.length ? (
                  joinList(ownOrgs.map((o) => o.org.label), 2)
                ) : (
                  <span className="text-warn-ink">
                    None specific to {short}
                    {umbrellaOrgs.length ? <span className="text-ink-3">; umbrella: {joinList(umbrellaOrgs.map((o) => o.org.label), 1)}</span> : null}
                  </span>
                )}
              </FactRow>
              {clusters.length > 0 && (
                <FactRow k="Cluster">
                  {clusters.slice(0, 2).map((c) => (
                    <span key={c.id} className="mb-1 flex items-start gap-1.5 leading-snug">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: clusterColor(clusterSlot(idx, c.id)) }} aria-hidden="true" />
                      {c.label.split(":")[0]}
                    </span>
                  ))}
                  {clusters.length > 2 && <span className="text-xs text-ink-3">and {clusters.length - 2} more</span>}
                </FactRow>
              )}
            </dl>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link href={atlasHref(id)} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink">
              See it on the map
            </Link>
            <Link href={pathHref(id)} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink">
              Trace a path from here
            </Link>
          </div>
        </div>
      </header>

      {/* The three questions, answered in one line each */}
      <nav aria-label="On this page" className={`border-b border-line bg-subtle/60 ${embedded ? "hidden" : ""}`}>
        <ol className="mx-auto grid max-w-[1120px] grid-cols-1 gap-px px-8 md:grid-cols-3">
          <SummaryCell n={1} href="#shares" q="Who shares our disease characteristics?">
            {matches.length ? (
              <>
                {plural(matches.length, "related disease")}. Closest: <b className="font-medium text-ink">{matches[0].disease.label}</b>
                {matches[0].sharedMechanisms[0] ? <> (shares {lowerFirst(matches[0].sharedMechanisms[0].mechanism.label)})</> : null}
              </>
            ) : (
              "No related disease found in the current data."
            )}
          </SummaryCell>
          <SummaryCell n={2} href="#exists" q="What useful work already exists?">
            {items.length ? (
              <>
                {items.filter((i) => i.own).length} already include {short}; {items.filter((i) => !i.own && i.reuse !== "not_applicable").length} more could be adapted
              </>
            ) : (
              "No registries, studies or models found yet."
            )}
          </SummaryCell>
          <SummaryCell n={3} href="#together" q="What should we do together?">
            {step.title}
          </SummaryCell>
        </ol>
      </nav>

      <div className={`mx-auto max-w-[1120px] space-y-16 ${embedded ? "px-0 pt-2" : "px-8 pt-12"}`}>
        {persona === "family" && (
          <section id="community" aria-labelledby="community-h" className="scroll-mt-20">
            <p className={EYEBROW}>Start here</p>
            <h2 id="community-h" className={`mt-1 ${H2}`}>
              Find your community
            </h2>
            <VariantHint />
            <div className="mt-5 max-w-[760px]">
              <CommunityBlock
                node={node}
                short={short}
                ownOrgs={ownOrgs}
                umbrellaOrgs={umbrellaOrgs}
                registries={registries}
                relatedOrgs={relatedOrgs}
                searchedList={searchedList}
                gaps={gaps}
              />
            </div>
          </section>
        )}
        {persona === "researcher" && <OseiSections idx={idx} node={node} />}
        {persona === "researcher" && <ResearcherMechanisms idx={idx} ctx={ctx} />}
        {persona === "biotech" && <BiotechNeed ctx={ctx} items={items} ownOrgs={ownOrgs} umbrellaOrgs={umbrellaOrgs} />}
        {(persona === "researcher" || persona === "biotech" || embedded) && <DisMechForAtlas atlasId={id} />}
        {/* 1 */}
        <section id="shares" aria-labelledby="shares-h" className="scroll-mt-20">
          <p className={EYEBROW}>Question 1</p>
          <h2 id="shares-h" className={`mt-1 ${H2}`}>
            Who shares our disease characteristics?
          </h2>
          <p className="mt-2 max-w-[720px] text-sm leading-relaxed text-ink-3">
            {persona === "family"
              ? "Diseases whose biology works like yours, closest first. Tap any badge to see where the information comes from."
              : "Ranked by shared mechanism first, then by shared symptoms. Distinctive symptoms count more than common ones like seizures. Click any badge to see the evidence."}
          </p>
          {matches.length ? (
            <ol className="mt-6 space-y-3">
              {matches.map((m, i) => (
                <MatchCard key={m.disease.id} me={ctx} m={m} rank={i + 1} />
              ))}
            </ol>
          ) : (
            <EmptyNote>
              The atlas found no disease that shares a mechanism or symptoms with {node.label} in the current data. That is a gap,
              not proof of uniqueness.
            </EmptyNote>
          )}
        </section>

        {/* 2 */}
        <section id="exists" aria-labelledby="exists-h" className="scroll-mt-20">
          <p className={EYEBROW}>Question 2</p>
          <h2 id="exists-h" className={`mt-1 ${H2}`}>
            What useful work already exists?
          </h2>
          <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">
            Registries, natural history studies, models and trials. Some already include people with {short}; others were built for
            a related disease and could be adapted. Each says what differs.
          </p>
          {items.length ? (
            <div className="mt-6 space-y-8">
              {(["covers", "as_is", "adaptable", "not_applicable"] as const).map((g) => {
                const list = items.filter((i) => (g === "covers" ? i.own : !i.own && i.reuse === g));
                if (!list.length) return null;
                const help =
                  g === "covers"
                    ? `People with ${short} can already take part or be found here.`
                    : g === "adaptable"
                      ? "Built for a disease that shares biology with yours. The design, protocol or measures could be adapted."
                      : REUSE_META[g].help;
                return (
                  <div key={g} data-tour={`${g}-group`}>
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <ReuseBadge group={g} short={short} />
                      <span className="text-xs text-ink-3">{help}</span>
                    </div>
                    <Collapsible
                      items={list.map((it) => (
                        <ItemCard key={it.node.id} it={it} short={short} />
                      ))}
                      initial={g === "covers" ? 8 : 5}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyNote>
              No registries, natural history studies, models or trials were found for {node.label} or its neighbours in the sources
              searched.
            </EmptyNote>
          )}

          <p className="mt-5 text-sm text-ink-2">
            Know something we missed?{" "}
            <Link href={contributeHref(id)} className="font-medium text-accent-700 hover:underline">
              Add it →
            </Link>
          </p>

          {therapies.length > 0 && (
            <div className="mt-10" data-tour="treatments">
              <h3 className="text-[15px] font-semibold text-ink">Treatment evidence to discuss with your neurologist</h3>
              <p className="mt-1 max-w-[760px] text-sm leading-relaxed text-ink-3">
                Published evidence about treatments for {short}. This is not medical advice: bring it to your child’s neurologist,
                who can judge whether it applies.
              </p>
              <ul className="mt-3 space-y-2.5">
                {therapies.map((t) => (
                  <li key={t.node.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-line px-5 py-3.5">
                    <div className="min-w-0">
                      <p className="text-[15px] font-medium text-ink">{t.node.label}</p>
                      <p className="mt-0.5 text-xs text-ink-3">
                        {t.node.type === "therapy" && t.node.attrs?.modality ? THERAPY_MODALITY_LABEL[t.node.attrs.modality] ?? t.node.attrs.modality : "Therapy"}
                        {t.node.type === "therapy" && t.node.attrs?.stage ? ` · ${THERAPY_STAGE_LABEL[t.node.attrs.stage] ?? t.node.attrs.stage}` : ""}
                      </p>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{t.edge.explanation}</p>
                    </div>
                    <EvidenceChip edge={t.edge} label="Evidence" />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* 3 */}
        <section id="together" aria-labelledby="together-h" className="scroll-mt-20">
          <p className={EYEBROW}>Question 3</p>
          <h2 id="together-h" className={`mt-1 ${H2}`}>
            What should we do together?
          </h2>

          <div className="mt-6 rounded-lg border border-line border-l-[3px] border-l-accent-700 px-6 py-5">
            <p className="text-xs font-semibold text-accent-700">Suggested next step</p>
            <p className="mt-1.5 text-[18px] font-semibold leading-snug text-ink">{step.title}</p>
            {step.why && <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-2">{step.why}</p>}
            {step.checks.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-ink">Before joining forces, check:</p>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink-2 marker:text-ink-4">
                  {step.checks.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
            {step.edgeIds.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs text-ink-3">Based on</span>
                {step.edgeIds.map((eid) => {
                  const e = idx.edgeById.get(eid);
                  return e ? (
                    <EvidenceChip key={eid} edge={e} label={`${idx.nodeById.get(e.source)?.label} → ${idx.nodeById.get(e.target)?.label}`} />
                  ) : null;
                })}
              </div>
            )}
            {nextPartner && (
              <p className="mt-4 text-sm">
                <Link href={compareHref(id, nextPartner.disease.id)} className="font-medium text-accent-700 hover:underline">
                  Compare {short} and {nextPartner.context.genes[0]?.label ?? nextPartner.disease.label} side by side before you write →
                </Link>
              </p>
            )}
            <div className="mt-5 border-t border-line pt-4" data-tour="proposal">
              <ProposalDraft
                idx={idx}
                payload={{
                  id,
                  disease: node.label,
                  next_step: step.title,
                  checks: step.checks,
                  neighbours: matches.slice(0, 3).map((m) => ({
                    id: m.disease.id,
                    label: m.disease.label,
                    shared_mechanisms: m.sharedMechanisms.map((s) => s.mechanism.label),
                  })),
                  partners: [...ownOrgs, ...relatedOrgs].map((o) => o.org.label),
                  gaps: gaps.map((g) => g.question),
                  edge_ids: step.edgeIds,
                }}
              />
            </div>
          </div>

          <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-2">
            {persona !== "family" && (
              <CommunityBlock
                heading
                node={node}
                short={short}
                ownOrgs={ownOrgs}
                umbrellaOrgs={umbrellaOrgs}
                registries={registries}
                relatedOrgs={relatedOrgs}
                searchedList={searchedList}
                gaps={gaps}
              />
            )}
            {persona !== "family" && (
            <div>
              <h3 className="text-[15px] font-semibold text-ink">Researchers who bridge diseases</h3>
              <p className="mt-1 text-xs text-ink-3">Professional public information only.</p>
              {researchers.length ? (
                <ul className="mt-3 space-y-2.5">
                  {researchers.map((r) => (
                    <li key={r.researcher.id} className="rounded-lg border border-line px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-ink">{r.researcher.label}</p>
                          {r.researcher.type === "researcher" && r.researcher.attrs?.affiliation && (
                            <p className="text-xs text-ink-3">{r.researcher.attrs.affiliation}</p>
                          )}
                        </div>
                        {r.bridges ? (
                          <span className="shrink-0 rounded border border-accent-200 bg-accent-50 px-1.5 py-px text-[11px] font-medium text-accent-900">
                            Bridges diseases
                          </span>
                        ) : (
                          <span className="shrink-0 rounded border border-line px-1.5 py-px text-[11px] text-ink-3">Related disease only</span>
                        )}
                      </div>
                      <p className="mt-2 text-sm text-ink-2">
                        Works on {joinList(r.diseases, 3)}
                        {!r.bridges && <span className="text-ink-3">; not yet linked to {node.label}</span>}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {r.links.map((l) => (
                          <EvidenceChip key={l.edge.id} edge={l.edge} label={l.target.label} />
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-ink-3">
                  No researchers are linked to this disease or its neighbours yet. They appear when publications and grants are added.
                </p>
              )}
            </div>
            )}
          </div>

          <UnknownsBox gaps={gaps} disease={node} family={persona === "family"} />
        </section>

        <IdeasSection idx={idx} diseaseId={id} />
        <PatternBreaks idx={idx} ctx={ctx} />
        <LookAlikes diseaseId={id} short={short} />
      </div>
    </div>
  );
}

function FactRow({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-2.5 text-sm">
      <dt className="w-32 shrink-0 text-ink-3">{k}</dt>
      <dd className="min-w-0 flex-1 text-ink">{children}</dd>
    </div>
  );
}

function SummaryCell({ n, href, q, children }: { n: number; href: string; q: string; children: React.ReactNode }) {
  return (
    <li>
      <a href={href} className="block h-full px-1 py-4 pr-6 hover:[&_p:first-child]:text-accent-700">
        <p className="text-xs font-medium text-ink-3">
          {n} · {q}
        </p>
        <p className="mt-1 text-sm leading-snug text-ink-2">{children}</p>
      </a>
    </li>
  );
}

function MatchCard({ me, m, rank }: { me: DiseaseContext; m: DiseaseMatch; rank: number }) {
  const myGene = me.genes[0]?.label ?? "Ours";
  const theirGene = m.context.genes[0]?.label ?? "Theirs";
  const distinctive = m.sharedPhenotypes.filter((p) => p.distinctive);
  const common = m.sharedPhenotypes.filter((p) => !p.distinctive);
  return (
    <li className="rounded-lg border border-line px-5 py-4" data-tour={`closest-${rank - 1}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <span className="w-5 text-sm tabular-nums text-ink-3">{rank}</span>
          <div>
            <Link href={diseaseHref(m.disease.id)} className="text-[17px] font-semibold text-ink hover:text-accent-700">
              {m.disease.label}
            </Link>
            <span className="ml-2 text-xs text-ink-3">{theirGene} gene</span>
          </div>
        </div>
        <OverlapMeter score={m.score} />
      </div>
      <dl className="mt-3 space-y-2.5 pl-8 text-sm">
        <Reason k="Shared mechanism">
          {m.sharedMechanisms.length ? (
            <ul className="space-y-1.5">
              {m.sharedMechanisms.map((s) => {
                const mine = me.mechanisms.get(s.mechanism.id);
                const theirs = m.context.mechanisms.get(s.mechanism.id);
                return (
                  <li key={s.mechanism.id} className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                    <span className="text-ink">
                      <Term>{s.mechanism.label}</Term>
                    </span>
                    {mine && <EvidenceChip edge={mine.edges[mine.edges.length - 1]} label={myGene} />}
                    {theirs && <EvidenceChip edge={theirs.edges[theirs.edges.length - 1]} label={theirGene} />}
                  </li>
                );
              })}
            </ul>
          ) : (
            <span className="text-ink-3">None shown in the evidence</span>
          )}
        </Reason>
        <Reason k="Shared symptoms">
          {m.sharedPhenotypes.length ? (
            <span className="flex flex-wrap items-center gap-1.5">
              {[...distinctive, ...common].map((p) => (
                <EvidenceChip
                  key={p.phenotype.id}
                  edge={p.edges[1]}
                  label={`${p.phenotype.label}${p.distinctive ? " · distinctive" : ""}`}
                  className={p.distinctive ? "" : "opacity-80"}
                />
              ))}
            </span>
          ) : (
            <span className="text-ink-3">None recorded</span>
          )}
        </Reason>
        {m.directEdges.length > 0 && (
          <Reason k="Atlas link">
            <span className="flex flex-wrap items-center gap-1.5">
              {m.directEdges.map((e) => (
                <EvidenceChip key={e.id} edge={e} label={relationName(e.type)} />
              ))}
            </span>
          </Reason>
        )}
        {m.notShared.length > 0 && (
          <Reason k="What differs">
            <span className="text-ink-2">
              Not recorded there: {joinList(m.notShared.map((p) => lowerFirst(p.label)), 3)}
            </span>
          </Reason>
        )}
      </dl>
      <div className="mt-3 flex gap-4 pl-8 text-sm">
        <Link href={compareHref(me.disease.id, m.disease.id)} className="font-medium text-accent-700 hover:underline">
          Compare side by side →
        </Link>
        <Link href={pathHref(me.disease.id, m.disease.id)} className="text-ink-2 hover:text-accent-700 hover:underline">
          See the connecting path
        </Link>
      </div>
    </li>
  );
}

function Reason({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-3">
      <dt className="pt-0.5 text-ink-3">{k}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function OverlapMeter({ score }: { score: number }) {
  const filled = score >= 0.45 ? 3 : score >= 0.3 ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-2 text-xs text-ink-2" title={`Overlap score ${score.toFixed(2)} (shared mechanism 45%, atlas link 30%, symptoms 25%)`}>
      <span className="flex gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={`h-2.5 w-1.5 rounded-sm ${i <= filled ? "bg-accent-700" : "bg-line"}`} />
        ))}
      </span>
      {overlapWord(score)}
    </span>
  );
}

type ReuseGroup = "covers" | Reuse;

function ReuseBadge({ group, short }: { group: ReuseGroup; short: string }) {
  const cls: Record<ReuseGroup, string> = {
    covers: "border-[#bcd9c6] bg-[#edf6f0] text-ok",
    as_is: "border-[#bcd9c6] bg-[#edf6f0] text-ok",
    adaptable: "border-accent-200 bg-accent-50 text-accent-900",
    not_applicable: "border-line bg-subtle text-ink-3",
  };
  const label = group === "covers" ? `Already covers ${short}` : group === "adaptable" ? "Could be adapted" : REUSE_META[group].label;
  return <span className={`inline-flex shrink-0 rounded border px-2 py-0.5 text-xs font-medium ${cls[group]}`}>{label}</span>;
}

function ItemCard({ it, short }: { it: ExistingItem; short: string }) {
  const n = it.node;
  const kind =
    n.type === "asset"
      ? n.attrs?.kind
        ? ASSET_KIND_LABEL[n.attrs.kind] ?? n.attrs.kind
        : "Resource"
      : n.type === "study"
        ? `${n.attrs?.study_type === "observational" ? "Observational study" : "Clinical trial"}${n.attrs?.phase ? `, ${n.attrs.phase}` : ""}`
        : n.type;
  const status = n.type === "asset" ? n.attrs?.status : n.type === "study" ? n.attrs?.status : undefined;
  const url = n.type === "asset" ? n.attrs?.url : n.type === "study" ? n.attrs?.url : undefined;
  return (
    <li className="grid grid-cols-1 gap-3 rounded-lg border border-line px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs text-ink-3">
          <NodeTypeIcon type={n.type} size={11} />
          {kind} · {it.own ? `includes ${short}` : `built for ${it.forDisease.label}`}
          {it.maintainers.length ? ` · run by ${it.maintainers.map((x) => x.label).join(", ")}` : ""}
          {n.type === "study" && n.attrs?.sponsor ? ` · ${n.attrs.sponsor}` : ""}
          {status ? ` · ${status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ")}` : ""}
        </p>
        <p className="mt-1 text-[15px] font-medium text-ink">
          <Link href={atlasHref(n.id)} className="hover:text-accent-700">
            {n.label}
          </Link>
          <ContributedBadge stamps={contributionsOf(n)} className="ml-2 align-middle" />
        </p>
        {it.own ? (
          it.alsoCovers.length > 0 && (
            <p className="mt-1 text-sm leading-relaxed text-ink-2">
              Also includes {joinList(it.alsoCovers.map((d) => d.label), 3)}, so families can compare notes across diseases.
            </p>
          )
        ) : (
          <p className="mt-1 text-sm leading-relaxed text-ink-2">{it.reason}</p>
        )}
        {it.differs.length > 0 && (
          <div className="mt-2">
            <p className="text-xs font-medium text-ink-3">What differs</p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-sm text-ink-2 marker:text-ink-4">
              {it.differs.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="flex flex-row flex-wrap items-start gap-2 md:flex-col md:items-end">
        <EvidenceChip edge={it.link} label="Source" />
        {isPlaceholderUrl(url) ? null : (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent-700 hover:underline">
            Open record ↗
          </a>
        )}
      </div>
    </li>
  );
}

function OrgCard({ o, note }: { o: OrgPartner; note: string }) {
  const url = o.org.type === "patient_org" ? o.org.attrs?.url : undefined;
  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-line px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">
          {o.org.label}
          <ContributedBadge stamps={contributionsOf(o.org)} className="ml-2 align-middle" />
        </p>
        <p className="mt-0.5 text-xs text-ink-3">{note}</p>
        {!isPlaceholderUrl(url) && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs text-accent-700 hover:underline">
            Website ↗
          </a>
        )}
      </div>
      <EvidenceChip edge={o.edge} label="Source" />
    </li>
  );
}

function UnknownsBox({ gaps, disease, family = false }: { gaps: Gap[]; disease: AtlasNode; family?: boolean }) {
  return (
    <section aria-labelledby="unknown-h" className="mt-10 rounded-lg border-2 border-ink px-6 py-5" data-tour="gaps">
      <h3 id="unknown-h" className="text-[17px] font-semibold text-ink">
        {family ? "What nobody knows yet, and how you could help" : "What we don’t know yet"}
      </h3>
      <p className="mt-1 text-sm text-ink-3">
        {family
          ? "These questions have no answer in the sources yet. Families often help answer them, for example by joining a registry or a natural history study."
          : "Open questions the atlas could not answer from its sources. Each one is a place to contribute."}
      </p>
      {gaps.length ? (
        <ol className="mt-4 space-y-5">
          {gaps.map((g, i) => (
            <li key={g.id} className="grid grid-cols-[24px_minmax(0,1fr)] gap-2">
              <span className="text-sm tabular-nums text-ink-3">{i + 1}</span>
              <div>
                <p className="text-[15px] font-medium leading-snug text-ink">{g.question}</p>
                {g.what_is_missing.length > 0 && (
                  <p className="mt-1.5 text-sm text-ink-2">
                    <span className="text-ink-3">Missing: </span>
                    {g.what_is_missing.join("; ")}
                  </p>
                )}
                {g.how_to_find_out && (
                  <p className="mt-1 text-sm text-ink-2">
                    <span className="text-ink-3">How to find out: </span>
                    {g.how_to_find_out}
                  </p>
                )}
                {g.searched.length > 0 && <p className="mt-1 text-xs text-ink-3">Searched: {g.searched.join("; ")}</p>}
                <Link href={contributeHref(disease.id, g.id)} className="mt-1.5 inline-block text-sm font-medium text-accent-700 hover:underline">
                  Help fill this gap →
                </Link>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 text-sm leading-relaxed text-ink-2">
          No open questions have been recorded for {disease.label} yet. That does not mean everything is known: it means nobody has
          logged a gap.
        </p>
      )}
    </section>
  );
}

/** "Searched: a, b, c and 9 more" with the full list on demand. Entries are shortened to their name. */
function SearchedList({ items }: { items: string[] }) {
  const short = items.map((s) => s.replace(/\s*\(https?:[^)]*\)/g, "").replace(/\s*https?:\S+/g, "").split(/[;:]/).slice(0, 2).join(":").trim());
  const head = [...new Set(short)].filter(Boolean);
  return (
    <div className="mt-1 text-xs leading-relaxed text-warn-ink">
      <p>
        Searched {head.length ? joinList(head.slice(0, 3), 3) : "no sources listed"}
        {head.length > 3 ? ` and ${head.length - 3} more` : ""}. If you know of a group, it belongs here.
      </p>
      {items.length > 3 && (
        <details className="mt-1">
          <summary className="cursor-pointer underline-offset-2 hover:underline">Everything we searched</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 break-words">
            {items.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** Shows the first few items; the rest behind a "Show N more" button (keeps the page calm). */
function Collapsible({ items, initial }: { items: React.ReactNode[]; initial: number }) {
  const [open, setOpen] = useState(false);
  const shown = open ? items : items.slice(0, initial);
  return (
    <>
      <ul className="mt-3 space-y-2.5">{shown}</ul>
      {items.length > initial && (
        <button type="button" onClick={() => setOpen(!open)} className="mt-2.5 text-sm font-medium text-accent-700 hover:underline">
          {open ? "Show fewer" : `Show ${items.length - initial} more`}
        </button>
      )}
    </>
  );
}

function CommunityBlock({
  heading = false,
  node,
  short,
  ownOrgs,
  umbrellaOrgs,
  registries,
  relatedOrgs,
  searchedList,
  gaps,
}: {
  heading?: boolean;
  node: AtlasNode;
  short: string;
  ownOrgs: OrgPartner[];
  umbrellaOrgs: OrgPartner[];
  registries: ExistingItemLite[];
  relatedOrgs: OrgPartner[];
  searchedList: string[];
  gaps: Gap[];
}) {
  return (
    <div data-tour="community">
      {heading && <h3 className="text-[15px] font-semibold text-ink">Patient communities</h3>}
              {ownOrgs.length ? (
                <ul className="mt-3 space-y-2.5">
                  {ownOrgs.map((o) => (
                    <OrgCard key={o.org.id} o={o} note={`Patient group for ${short}`} />
                  ))}
                </ul>
              ) : (
                <div className="mt-3 rounded-lg border border-warn-line bg-warn-bg px-4 py-3.5" data-tour="no-group">
                  <p className="text-sm font-medium text-warn-ink">
                    There is no patient group specifically for {node.label} in the sources we searched.
                  </p>
                  <SearchedList items={searchedList} />
                  {(umbrellaOrgs.length > 0 || registries.length > 0) && (
                    <p className="mt-2 text-sm text-warn-ink">The closest communities that already include {short} are listed below.</p>
                  )}
                </div>
              )}
              {(umbrellaOrgs.length > 0 || (!ownOrgs.length && registries.length > 0)) && (
                <div data-tour="closest-community">
                  <p className="mt-5 text-xs font-medium text-ink-3">{ownOrgs.length ? `Umbrella groups that include ${short}` : "Closest community"}</p>
                  <ul className="mt-2 space-y-2.5">
                    {umbrellaOrgs.map((o) => (
                      <OrgCard
                        key={o.org.id}
                        o={o}
                        note={`Umbrella group that includes ${short}${o.edge.evidence_level === "inferred" ? " (link inferred by the atlas)" : ""}`}
                      />
                    ))}
                    {!ownOrgs.length &&
                      registries.map((r) => (
                        <li key={r.node.id} className="flex items-start justify-between gap-3 rounded-lg border border-line px-4 py-3">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-ink">{r.node.label}</p>
                            <p className="mt-0.5 text-xs text-ink-3">Registry that already accepts people with {short}</p>
                            {r.node.type === "asset" && !isPlaceholderUrl(r.node.attrs?.url) && (
                              <a href={r.node.attrs?.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs text-accent-700 hover:underline">
                                Website ↗
                              </a>
                            )}
                          </div>
                          <EvidenceChip edge={r.edge} label="Source" />
                        </li>
                      ))}
                  </ul>
                </div>
              )}
              {relatedOrgs.length > 0 && (
                <>
                  <p className="mt-5 text-xs font-medium text-ink-3">{ownOrgs.length ? "Communities on the same pathway" : "Closest related communities"}</p>
                  <ul className="mt-2 space-y-2.5">
                    {relatedOrgs.map((o) => (
                      <OrgCard
                        key={o.org.id}
                        o={o}
                        note={`Serves ${o.serves.label}${o.match?.sharedMechanisms[0] ? `, which shares ${lowerFirst(o.match.sharedMechanisms[0].mechanism.label)}` : ""}`}
                      />
                    ))}
                  </ul>
                </>
              )}
              {!ownOrgs.length && !relatedOrgs.length && (
                <p className="mt-3 text-sm text-ink-3">No related communities were found either. Starting a family network may be the first step.</p>
              )}
      {!ownOrgs.length && <HelpBuild short={short} diseaseId={node.id} umbrellaOrgs={umbrellaOrgs} registries={registries} gaps={gaps} />}
    </div>
  );
}

/** Concrete, data-grounded ways a family can help when no dedicated group exists. */
function HelpBuild({ short, diseaseId, umbrellaOrgs, registries, gaps }: { short: string; diseaseId: string; umbrellaOrgs: OrgPartner[]; registries: ExistingItemLite[]; gaps: Gap[] }) {
  const steps: string[] = [];
  for (const r of registries.slice(0, 2)) steps.push(`Join ${r.node.label}, so researchers and other families can find people with ${short}.`);
  for (const o of umbrellaOrgs.slice(0, 1)) steps.push(`Ask ${o.org.label} whether they could host a ${short} family group.`);
  steps.push(`Ask the clinic that made the diagnosis to pass your contact details on to other ${short} families, with their permission.`);
  const g = gaps.find((x) => /patient|communit|organi[sz]ation|famil|group/i.test(x.question));
  if (g?.how_to_find_out) steps.push(g.how_to_find_out);
  return (
    <div data-tour="help-build" className="mt-5 rounded-lg border border-line bg-subtle px-4 py-3.5">
      <p className="text-sm font-semibold text-ink">How to help build the missing community</p>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-ink-2">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <p className="mt-2 text-sm">
        Know a group, registry or study we missed?{" "}
        <Link href={contributeHref(diseaseId)} className="font-medium text-accent-700 hover:underline">
          Add it to the atlas →
        </Link>
      </p>
    </div>
  );
}

/** /contribute?disease=VAMP2[&gap=...] */
function contributeHref(diseaseId: string, gapId?: string) {
  const q = new URLSearchParams({ disease: diseaseId.replace(/^disease:/, "") });
  if (gapId) q.set("gap", gapId);
  return `/contribute?${q.toString()}`;
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="mt-5 rounded-lg border border-dashed border-ink-4 px-5 py-4 text-sm leading-relaxed text-ink-2">{children}</p>;
}

function NotFound({ id }: { id: string }) {
  // start the search with what was asked for, so a disease outside the mapped families shows up right away
  const [q, setQ] = useState(id.replace(/^disease:/, ""));
  return (
    <div className="mx-auto w-full max-w-xl px-6 py-24">
      <h1 className="text-xl font-semibold text-ink">That disease isn’t mapped in depth</h1>
      <p className="mt-2 text-sm text-ink-3">
        “{id.replace(/^disease:/, "")}” is not one of the diseases the atlas maps in depth. Search below: every other rare disease has a page
        with basic data.
      </p>
      <div className="mt-6">
        <SearchBox variant="field" autoFocus value={q} onChange={setQ} focusKey={1} />
      </div>
    </div>
  );
}
