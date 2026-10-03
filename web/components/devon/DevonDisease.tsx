"use client";

// Devon's page for a disease mapped in depth: graph (summary, mechanism, inheritance, therapies,
// symptoms, groups), population/channels.json (organisational contacts, registries, recruiting trials)
// and population/prevalence.json (estimated people). Template sentences, real data, nothing invented.
import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { type GraphIndex } from "@/lib/graph";
import { explain } from "@/lib/glossary";
import { closestDiseases, communitiesFor, diseaseContext, relatedOrgsFor } from "@/lib/insights";
import { loadChannels, loadPrevalence, peopleRange, type Channel, type ChannelsFile, type PrevalenceFile } from "@/lib/population";
import { useResource } from "@/lib/resource";
import { joinList, lowerFirst } from "@/lib/text";
import type { AtlasEdge, AtlasNode } from "@/lib/types";
import { studyKind, type Contact, type How, type Study } from "./DevonBits";
import { DevonPage, type DevonModel } from "./DevonPage";

const OPEN = new Set(["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]);
const REACH_OFFER: Record<string, string> = {
  registry: "Family registry",
  participate: "Research you can take part in",
  research: "Research news",
  contact: "Contact form",
  conference: "Family conferences",
  grants: "Research grants",
};

const isUmbrella = (scope?: string | null) => !!scope && /^(umbrella|multi-gene|multi-disease|disease-group)|consortium|coalition/i.test(scope);

export function DevonDisease({ idx, node, learnMore }: { idx: GraphIndex; node: AtlasNode; learnMore?: React.ReactNode }) {
  const channels = useResource<ChannelsFile | null>("pop:channels", loadChannels);
  const prevalence = useResource<PrevalenceFile | null>("pop:prevalence", loadPrevalence);
  const m = useMemo(
    () => buildModel(idx, node, channels?.data ?? null, prevalence?.data ?? null, channels?.status === "loading" || prevalence?.status === "loading"),
    [idx, node, channels, prevalence],
  );
  const chosen = useSearchParams().get("type");
  return <DevonPage m={{ ...m, chosenType: chosen }} learnMore={learnMore} />;
}

function edgeBetween(idx: GraphIndex, source: string, type: string, target: string): AtlasEdge | undefined {
  return idx.edgeById.get(`${source}|${type}|${target}`);
}

function buildModel(idx: GraphIndex, node: AtlasNode, ch: ChannelsFile | null, prev: PrevalenceFile | null, loading: boolean): DevonModel {
  const id = node.id;
  const ctx = diseaseContext(idx, id)!;
  const gene = ctx.genes[0];
  const short = gene?.label ?? node.label;
  const attrs = (node.attrs ?? {}) as { inheritance?: string; approved_treatment?: boolean };

  // 1. plain words
  const plain: DevonModel["plain"] = [];
  const causes = gene ? edgeBetween(idx, gene.id, "causes", id) : undefined;
  if (node.summary) plain.push({ text: node.summary, how: causes ? { edge: causes.id } : undefined });
  const mech = [...ctx.mechanisms.values()].sort((a, b) => b.strength - a.strength).find((m) => (m.mechanism.attrs as { kind?: string } | undefined)?.kind === "effect") ??
    [...ctx.mechanisms.values()].sort((a, b) => b.strength - a.strength)[0];
  if (mech) {
    const base = mech.mechanism.label.split(" (")[0];
    const paren = mech.mechanism.label.match(/\(([^)]+)\)/)?.[1];
    const meaning = explain(base) ?? (paren ? `${paren[0].toUpperCase()}${paren.slice(1)}.` : null);
    if (meaning) plain.push({ text: `What goes wrong, most often: ${meaning}`, how: { edge: mech.edges[mech.edges.length - 1]?.id } });
  }
  const inh = (attrs.inheritance ?? "").split(";").map((s) => s.trim()).filter(Boolean);
  if (inh.length === 1) {
    const e = explain(inh[0].replace(/ inheritance$/i, ""));
    if (e) plain.push({ text: `How it is passed on: ${e} A genetic counsellor can explain what this means for your family.` });
  } else if (inh.length > 1) {
    plain.push({ text: "It can be passed on in more than one way. A genetic counsellor can tell you which applies to your family." });
  }
  plain.push({ text: "Every child is different, and not everything on this page will apply to yours." });

  // approved treatment
  const approvedTherapies = (idx.adjacency.get(id) ?? [])
    .filter((n) => n.edge.type === "developed_for" && n.dir === "in")
    .map((n) => ({ t: idx.nodeById.get(n.other)!, e: n.edge }))
    .filter(({ t }) => {
      const a = (t?.attrs ?? {}) as { stage?: string; stage_by_disease?: Record<string, string> };
      return a.stage_by_disease?.[short] ? a.stage_by_disease[short] === "approved" : a.stage === "approved";
    });
  const approved = approvedTherapies.length
    ? {
        text: `There is an approved treatment for some forms of this condition: ${joinList(approvedTherapies.map((x) => x.t.label.split(" (")[0]), 3)}. Ask your doctor whether it fits your child.`,
        how: { edge: approvedTherapies[0].e.id },
      }
    : null;

  // 2–3. groups and registries: channels.json (organisational channels only), else the graph
  const byType = ch?.by_disease[id] ?? {};
  const chan = (t: string): Channel[] => [...new Set(byType[t] ?? [])].map((cid) => ch!.channels.find((c) => c.id === cid)).filter((c): c is Channel => !!c);
  const howFor = (c: Channel): How => {
    const edge = c.evidence?.find((e) => e.edge && idx.edgeById.has(e.edge))?.edge;
    if (edge) return { edge };
    return { note: c.layer?.startsWith("scale") ? "Found in a public directory of patient organisations (matched automatically)." : "Listed on the organisation’s own website.", links: c.url ? [{ label: "Their website", url: c.url }] : [] };
  };
  const toContact = (c: Channel): Contact => ({
    key: c.id,
    name: c.name,
    url: c.url,
    country: c.country ?? null,
    offers: [
      ...new Set((c.reach_links ?? []).map((r) => REACH_OFFER[r.kind]).filter((x): x is string => !!x)),
      ...(c.layer?.startsWith("scale") ? ["Found automatically"] : []),
    ],
    blurb: c.type === "patient_org" ? null : (c.how_to_reach ?? null),
    how: howFor(c),
  });
  let groups: Contact[] = [];
  let umbrella: Contact[] = [];
  let registries: Contact[] = [];
  if (ch) {
    // the most useful first: curated (deep) before directory matches, then the most ways to take part
    const orgs = chan("patient_org").sort(
      (a, b) => Number(b.layer === "deep") - Number(a.layer === "deep") || (b.reach_links?.length ?? 0) - (a.reach_links?.length ?? 0),
    );
    // "for this diagnosis" only when the scope is not an umbrella and, if it names a gene, names this one
    const otherGene = (o: Channel) => {
      const named = o.scope?.match(/^(?:gene|syndrome|disease)-specific \(([^)]+)\)/i)?.[1];
      return !!named && !named.toUpperCase().includes(short.toUpperCase()) && (o.diseases?.length ?? 0) > 1;
    };
    groups = orgs.filter((o) => !isUmbrella(o.scope) && !otherGene(o)).map(toContact);
    umbrella = orgs
      .filter((o) => isUmbrella(o.scope) || otherGene(o))
      .map((o) => {
        const named = o.scope?.match(/^(?:gene|syndrome|disease)-specific \(([^)]+)\)/i)?.[1];
        return {
          ...toContact(o),
          blurb: named ? `A ${named} group that also lists this condition.` : o.scope ? `Serves: ${o.scope.replace(/^umbrella:\s*/i, "")}` : null,
        };
      });
    registries = [...chan("registry"), ...chan("natural_history_study"), ...chan("data_platform")].map(toContact);
  } else {
    const comm = communitiesFor(idx, id);
    const orgContact = (o: { org: AtlasNode; edge: AtlasEdge }): Contact => ({
      key: o.org.id,
      name: o.org.label,
      url: (o.org.attrs as { url?: string } | undefined)?.url ?? null,
      country: (o.org.attrs as { country?: string } | undefined)?.country ?? null,
      how: { edge: o.edge.id },
    });
    groups = comm.specific.map(orgContact);
    umbrella = comm.umbrella.map(orgContact);
    registries = comm.registries.map((r) => ({ key: r.node.id, name: r.node.label, url: (r.node.attrs as { url?: string } | undefined)?.url ?? null, how: { edge: r.edge.id } }));
  }

  // related communities when there is no group of its own
  const related: Contact[] = [];
  if (!groups.length) {
    const matches = closestDiseases(idx, id, 4);
    for (const o of relatedOrgsFor(idx, matches, []).slice(0, 3))
      related.push({
        key: o.org.id,
        name: o.org.label,
        url: (o.org.attrs as { url?: string } | undefined)?.url ?? null,
        country: (o.org.attrs as { country?: string } | undefined)?.country ?? null,
        blurb: o.match ? `Supports families with ${o.match.disease.label}, a related condition.` : null,
        how: { edge: o.edge.id },
      });
  }

  // 1b. people
  const dp = prev?.deep[id];
  const range = peopleRange(dp?.estimated_people?.worldwide);
  const reported = Math.max(0, ...(dp?.entities ?? []).flatMap((e) => e.records.map((r) => r.n_reported ?? 0)));
  const peopleText = range
    ? `${range[0].toUpperCase()}${range.slice(1)} people worldwide are estimated to live with this condition.`
    : reported > 0
      ? `Medical reports describe at least ${reported.toLocaleString("en-US")} people with this condition.`
      : null;
  const peopleHow: How = {
    note: range
      ? "A rough range, not a count: Orphanet’s prevalence class multiplied by the world population. The true number could be lower or higher."
      : reported > 0
        ? "From the number of people described in published case reports (Orphanet)."
        : "Orphanet has no prevalence figure for this condition yet.",
    links: (dp?.entities ?? []).filter((e) => e.records.length).slice(0, 2).map((e) => ({ label: `Orphanet: ${e.name}`, url: e.url })),
  };

  // 6. studies looking for participants
  const trials = ch ? chan("recruiting_trial") : [];
  let studies: Study[] = trials
    .filter((t) => !t.status || OPEN.has(t.status))
    .map((t) => ({
      key: t.id,
      title: t.name,
      kind: studyKind(t.study_type, t.phase),
      detail: t.status === "NOT_YET_RECRUITING" ? "Opening soon" : t.status === "ENROLLING_BY_INVITATION" ? "By invitation" : "Recruiting now",
      sponsor: t.sponsor ?? null,
      url: t.url ?? `https://clinicaltrials.gov/study/${t.id.replace(/^study:/, "")}`,
      how: howFor(t),
    }));
  if (!ch) {
    studies = (idx.adjacency.get(id) ?? [])
      .filter((n) => n.edge.type === "studies" && n.dir === "in")
      .map((n) => ({ s: idx.nodeById.get(n.other)!, e: n.edge }))
      .filter(({ s }) => OPEN.has(String((s?.attrs as { status?: string } | undefined)?.status ?? "")))
      .map(({ s, e }) => {
        const a = (s.attrs ?? {}) as { study_type?: string; phase?: string; sponsor?: string; url?: string };
        return { key: s.id, title: s.label, kind: studyKind(a.study_type, a.phase), sponsor: a.sponsor ?? null, detail: "Recruiting now", url: a.url ?? "#", how: { edge: e.id } };
      });
  }

  // 5. questions for the doctor (templates over real data)
  const questions: string[] = [];
  if (mech) questions.push(`Does my child's variant work this way: ${lowerFirst(mech.mechanism.label)}? Some studies only include certain types of change.`);
  if (approvedTherapies.length) questions.push(`Is ${approvedTherapies[0].t.label.split(" (")[0]} suitable for my child, and how would we know it is working?`);
  else {
    const dev = (idx.adjacency.get(id) ?? []).filter((n) => n.edge.type === "developed_for" && n.dir === "in").map((n) => idx.nodeById.get(n.other)?.label.split(" (")[0]).filter(Boolean);
    questions.push(
      dev.length
        ? `Treatments are being studied for this condition, such as ${dev[0]}. Could my child be eligible for a study?`
        : "There is no approved treatment yet. What can we do now to help with symptoms and development?",
    );
  }
  const frequent = [...ctx.phenotypes.entries()]
    .map(([pid, e]) => ({ p: idx.nodeById.get(pid), f: String(e.attrs?.frequency ?? "") }))
    .filter((x) => x.p && (x.f === "HP:0040281" || x.f === "HP:0040280" || x.f === "HP:0040282"))
    .slice(0, 3)
    .map((x) => lowerFirst(x.p!.label));
  if (frequent.length) questions.push(`Which of these should we watch for, and what should we do if we see them: ${joinList(frequent)}?`);
  if (registries[0]) questions.push(`Should we join ${registries[0].name}? What would it involve for our family?`);
  if (studies.length) questions.push("Is my child's variant a type that could qualify for the studies listed here?");
  questions.push("Should we see a genetic counsellor about what this means for the rest of the family?");

  const ctgov = `https://clinicaltrials.gov/search?cond=${encodeURIComponent(node.label.split(" (")[0])}&aggFilters=status:rec%20not`;
  const sources = [
    ...(dp?.entities ?? []).slice(0, 1).map((e) => ({ label: "Orphanet", url: e.url })),
    { label: "ClinicalTrials.gov", url: ctgov },
  ];
  return {
    name: node.label,
    short,
    plain,
    approved,
    people: { text: peopleText, how: peopleHow, groups: groups.length },
    groups,
    umbrella,
    registries,
    studies: studies.slice(0, 6),
    openStudies: studies.length,
    studiesMoreUrl: ctgov,
    questions: questions.slice(0, 5),
    sources,
    related,
    sequenceGene: gene?.label ?? null,
    contributeHref: `/contribute?disease=${encodeURIComponent(id.replace(/^disease:/, ""))}`,
    loading,
  };
}

