// Devon's model for any rare disease outside the deep families (/d/<id>): the global index row, its
// neighbours shard (symptoms, inheritance) and the web/scale shard (organisations, studies, registries,
// prevalence). Template sentences over real data; where data is missing the page says so.
import { explain } from "@/lib/glossary";
import type { GlobalRow, NeighbourEntry, NeighbourShard } from "@/lib/global";
import { peopleRange, type ScaleEntry } from "@/lib/population";
import { capFirst, joinList } from "@/lib/text";
import { studyKind, type Contact, type Study } from "./DevonBits";
import type { DevonModel } from "./DevonPage";

const OPEN = new Set(["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]);
const SOURCE_NAME: Record<string, string> = {
  globalgenes: "Global Genes directory",
  nord: "NORD directory",
  eurordis: "EURORDIS member list",
  geneticalliance_uk: "Genetic Alliance UK directory",
  "clinicaltrials.gov": "ClinicalTrials.gov (study sponsor)",
  serp: "web search result",
};

export function buildGlobalDevonModel(
  row: GlobalRow,
  entry: NeighbourEntry | null,
  terms: NeighbourShard["t"],
  scale: ScaleEntry | null,
  loading: boolean,
): DevonModel {
  const name = capFirst(row.name);
  const plain: DevonModel["plain"] = [];
  plain.push({
    text: row.genes.length
      ? `${name} is a rare condition linked to the ${joinList(row.genes, 3)} ${row.genes.length === 1 ? "gene" : "genes"}.`
      : `${name} is a rare condition.`,
    how: {
      note: row.gsrc === 2 ? "Genes from Orphanet; some may be modifiers rather than the cause." : "Disease and gene records from MONDO, OMIM and Orphanet.",
      links: [
        ...row.omim.slice(0, 1).map((o) => ({ label: `OMIM ${o}`, url: `https://omim.org/entry/${o}` })),
        ...row.orpha.slice(0, 1).map((o) => ({ label: `Orphanet ${o}`, url: `https://www.orpha.net/en/disease/detail/${o}` })),
      ],
    },
  });
  const signs = (entry?.own ?? []).map((h) => terms[h]?.[0]).filter((x): x is string => !!x).slice(0, 3);
  // the shard's own terms are the most *specific* ones (sometimes distressing, rarely typical), so Devon's
  // summary does not list them; they stay under Learn more
  const inh = (entry?.inh ?? []).map((h) => terms[h]?.[0]).filter((x): x is string => !!x);
  if (inh.length === 1) {
    const e = explain(inh[0].replace(/ inheritance$/i, ""));
    if (e) plain.push({ text: `How it is passed on: ${e} A genetic counsellor can explain what this means for your family.` });
  } else if (inh.length > 1) plain.push({ text: "It can be passed on in more than one way. A genetic counsellor can tell you which applies to your family." });
  plain.push({ text: "Every child is different, and not everything on this page will apply to yours." });

  // people
  const est = (scale?.prev ?? []).find((p) => p.lo != null || p.hi != null);
  const range = est ? peopleRange({ low: est.lo, high: est.hi }) : null;
  const reported = Math.max(0, ...(scale?.prev ?? []).flatMap((p) => p.r.map((r) => r.n ?? 0)));
  const peopleText = range
    ? `${range[0].toUpperCase()}${range.slice(1)} people worldwide are estimated to live with this condition.`
    : reported > 0
      ? `Medical reports describe at least ${reported.toLocaleString("en-US")} people with this condition.`
      : null;

  const groups: Contact[] = (scale?.orgs ?? []).map((o, i) => ({
    key: `${o.n}-${i}`,
    name: o.n,
    url: o.u,
    country: o.c,
    offers: ["Found automatically"],
    blurb: o.q,
    how: {
      note: `Listed for this condition in: ${o.src.map((s) => SOURCE_NAME[s] ?? s).join(", ")}. Matched automatically, so check their website.`,
      links: o.p ? [{ label: "Directory entry", url: o.p }] : [],
    },
  }));
  const registries: Contact[] = (scale?.regs ?? []).map((r) => ({
    key: r.n,
    name: r.n,
    url: r.u,
    how: { note: "This registry lists the condition or its gene among the ones it studies.", links: [{ label: "Their list", url: r.u }] },
  }));
  const open = (scale?.studies ?? []).filter((s) => OPEN.has(s.st));
  const studies: Study[] = open.map((s) => ({
    key: s.id,
    title: s.t,
    kind: studyKind(s.ty, s.ph),
    detail: `${s.st === "NOT_YET_RECRUITING" ? "Opening soon" : s.st === "ENROLLING_BY_INVITATION" ? "By invitation" : "Recruiting now"}${
      s.m?.includes("gene") && row.genes[0] ? ` · mentions the ${row.genes[0]} gene` : ""
    }`,
    sponsor: s.sp,
    url: s.u,
    how: { note: s.m === "name_in_conditions" ? "The study lists this condition." : "Matched to this condition by ClinicalTrials.gov search.", links: [{ label: s.id, url: s.u }] },
  }));
  const openCount = Math.max(scale?.rec ?? 0, studies.length);
  const ctgov = `https://clinicaltrials.gov/search?cond=${encodeURIComponent(row.name)}&aggFilters=status:rec%20not`;

  const questions: string[] = [];
  if (row.genes.length) questions.push(`Which gene change does my child have, and is it the kind usually seen in ${row.name}?`);
  questions.push("Is there a treatment for this condition, or a study we could join?");
  if (signs.length) questions.push(`Which signs should we watch for, and what should we do if we see them?`);
  if (registries[0]) questions.push(`Should we join ${registries[0].name}?`);
  questions.push("Should we see a genetic counsellor about what this means for the rest of the family?");

  return {
    name,
    short: row.genes[0] ?? name,
    plain,
    approved: null,
    people: {
      text: peopleText,
      groups: groups.length,
      how: {
        note: range
          ? "A rough range, not a count: Orphanet’s prevalence class multiplied by the world population."
          : reported > 0
            ? "From the number of people described in published case reports (Orphanet)."
            : "Orphanet has no prevalence figure for this condition yet.",
        links: (scale?.prev ?? []).slice(0, 2).map((p) => ({ label: `Orphanet: ${p.n}`, url: p.u })),
      },
    },
    groups,
    umbrella: [],
    registries,
    studies: studies.slice(0, 6),
    openStudies: openCount,
    studiesMoreUrl: ctgov,
    questions: questions.slice(0, 5),
    sources: [
      ...row.orpha.slice(0, 1).map((o) => ({ label: "Orphanet", url: `https://www.orpha.net/en/disease/detail/${o}` })),
      { label: "ClinicalTrials.gov", url: ctgov },
    ],
    related: [],
    contributeHref: "/contribute",
    loading,
  };
}
