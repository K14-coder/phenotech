// "Before we join forces": a side-by-side comparison of two diseases, computed from the graph.
// Pure module (used by /compare and by the compare-questions AI task on the server).
import { clustersOf, neighbors, type GraphIndex } from "./graph";
import {
  diseaseContext,
  diseasesFor,
  distinctiveThreshold,
  existingWork,
  matchBetween,
  phenotypeIc,
  type DiseaseContext,
  type ExistingItem,
  type MechanismLink,
} from "./insights";
import { capFirst, joinList, lowerFirst } from "./text";
import type { AtlasEdge, AtlasNode, Cluster } from "./types";

export interface SideMechanism {
  link: MechanismLink;
  /** the edge that ties the disease to the mechanism (driven_by, or the gene/variant route's last edge) */
  edge: AtlasEdge;
  minority: boolean;
  contested: boolean;
}

export interface SharedSymptom {
  phenotype: AtlasNode;
  ic: number;
  distinctive: boolean;
  edgeA: AtlasEdge;
  edgeB: AtlasEdge;
}

export type VariantClass = "truncating" | "missense" | "splice" | "large deletions";

export interface Spectrum {
  gene: string;
  counts: Record<VariantClass, number>;
  /** share among sequence variants (truncating + missense + splice) */
  share: Record<"truncating" | "missense" | "splice", number>;
  dominant: "truncating" | "missense" | "splice" | "mixed";
  total: number;
  edges: AtlasEdge[];
}

export interface CompareItem {
  node: AtlasNode;
  edgeA?: AtlasEdge;
  edgeB?: AtlasEdge;
  /** for one-sided items: how it relates to the other disease (existing reuse logic) */
  reuse?: ExistingItem;
}

export interface Connector {
  node: AtlasNode;
  linksA: AtlasEdge[];
  linksB: AtlasEdge[];
}

export interface ExpertQuestion {
  topic: "Biology" | "Who can take part" | "Measuring progress" | "Practical checks";
  text: string;
  edgeIds: string[];
}

export interface Comparison {
  a: DiseaseContext;
  b: DiseaseContext;
  shortA: string;
  shortB: string;
  shared: { mechanism: AtlasNode; a: SideMechanism; b: SideMechanism }[];
  onlyA: SideMechanism[];
  onlyB: SideMechanism[];
  sharedSymptoms: SharedSymptom[];
  onlyASymptoms: { phenotype: AtlasNode; ic: number; edge: AtlasEdge }[];
  onlyBSymptoms: { phenotype: AtlasNode; ic: number; edge: AtlasEdge }[];
  clusters: { both: Cluster[]; aOnly: Cluster[]; bOnly: Cluster[] };
  inheritance: { a: string | null; b: string | null; differs: boolean };
  onset: { a: string | null; b: string | null; differs: boolean };
  spectrum: { a: Spectrum | null; b: Spectrum | null; differs: boolean };
  assets: { both: CompareItem[]; aOnly: CompareItem[]; bOnly: CompareItem[] };
  studiesBoth: CompareItem[];
  connectors: Connector[];
  questions: ExpertQuestion[];
}

function sideMechanism(link: MechanismLink): SideMechanism {
  const edge = link.edges[link.edges.length - 1];
  return {
    link,
    edge,
    minority: link.edges.some((e) => e.attrs?.minority_mechanism === true),
    contested: link.edges.some((e) => e.status === "contested"),
  };
}

const SEQUENCE = ["truncating", "missense", "splice"] as const;

export function variantSpectrum(idx: GraphIndex, ctx: DiseaseContext): Spectrum | null {
  const gene = ctx.genes[0];
  if (!gene) return null;
  const counts: Record<VariantClass, number> = { truncating: 0, missense: 0, splice: 0, "large deletions": 0 };
  const edges: AtlasEdge[] = [];
  for (const v of neighbors(idx, gene.id, { relations: ["variant_in"], direction: "in" })) {
    const vg = idx.nodeById.get(v.other);
    if (!vg || vg.type !== "variant_group") continue;
    edges.push(v.edge);
    for (const [k, n] of Object.entries(vg.attrs?.clinvar_counts ?? {})) {
      if (typeof n !== "number") continue;
      if (/nonsense|frameshift|truncat|stop|start_lost/i.test(k)) counts.truncating += n;
      else if (/missense|inframe/i.test(k)) counts.missense += n;
      else if (/splice/i.test(k)) counts.splice += n;
      else if (/cnv|deletion|duplication/i.test(k)) counts["large deletions"] += n;
    }
  }
  const seq = SEQUENCE.reduce((t, k) => t + counts[k], 0);
  if (!seq) return null;
  const share = { truncating: counts.truncating / seq, missense: counts.missense / seq, splice: counts.splice / seq };
  const top = SEQUENCE.reduce((x, k) => (share[k] > share[x] ? k : x), "truncating" as (typeof SEQUENCE)[number]);
  return { gene: gene.label, counts, share, dominant: share[top] >= 0.5 ? top : "mixed", total: seq + counts["large deletions"], edges };
}

/** Plain description: "mostly missense (62% of reported small changes)" */
export function spectrumWords(s: Spectrum): string {
  if (s.dominant === "mixed") {
    const top = SEQUENCE.reduce((x, k) => (s.share[k] > s.share[x] ? k : x), "truncating" as (typeof SEQUENCE)[number]);
    return `a mix, most often ${top} (${Math.round(s.share[top] * 100)}% of reported small changes)`;
  }
  return `mostly ${s.dominant} (${Math.round(s.share[s.dominant] * 100)}% of reported small changes)`;
}

export const SPECTRUM_WHY =
  "Why it matters: changes that cut the protein short usually mean too little protein, while missense changes can also change how the protein behaves, so a therapy approach that fits one may not fit the other.";

export function compareDiseases(idx: GraphIndex, aId: string, bId: string): Comparison | null {
  const a = diseaseContext(idx, aId);
  const b = diseaseContext(idx, bId);
  if (!a || !b || a.disease.type !== "disease" || b.disease.type !== "disease" || aId === bId) return null;
  const shortA = a.genes[0]?.label ?? a.disease.label;
  const shortB = b.genes[0]?.label ?? b.disease.label;

  // mechanisms
  const shared: Comparison["shared"] = [];
  const onlyA: SideMechanism[] = [];
  const onlyB: SideMechanism[] = [];
  for (const [mid, la] of a.mechanisms) {
    const lb = b.mechanisms.get(mid);
    if (lb) shared.push({ mechanism: la.mechanism, a: sideMechanism(la), b: sideMechanism(lb) });
    else onlyA.push(sideMechanism(la));
  }
  for (const [mid, lb] of b.mechanisms) if (!a.mechanisms.has(mid)) onlyB.push(sideMechanism(lb));
  shared.sort((x, y) => Math.min(y.a.link.strength, y.b.link.strength) - Math.min(x.a.link.strength, x.b.link.strength));

  // symptoms
  const threshold = distinctiveThreshold(idx);
  const sharedSymptoms: SharedSymptom[] = [];
  const onlyASymptoms: Comparison["onlyASymptoms"] = [];
  const onlyBSymptoms: Comparison["onlyBSymptoms"] = [];
  for (const [pid, ea] of a.phenotypes) {
    const p = idx.nodeById.get(pid);
    if (!p) continue;
    const ic = phenotypeIc(idx, p);
    const eb = b.phenotypes.get(pid);
    if (eb) sharedSymptoms.push({ phenotype: p, ic, distinctive: ic >= threshold, edgeA: ea, edgeB: eb });
    else if (ic >= threshold) onlyASymptoms.push({ phenotype: p, ic, edge: ea });
  }
  for (const [pid, eb] of b.phenotypes) {
    if (a.phenotypes.has(pid)) continue;
    const p = idx.nodeById.get(pid);
    if (!p) continue;
    const ic = phenotypeIc(idx, p);
    if (ic >= threshold) onlyBSymptoms.push({ phenotype: p, ic, edge: eb });
  }
  const byIc = <T extends { ic: number }>(x: T, y: T) => y.ic - x.ic;
  sharedSymptoms.sort(byIc);
  onlyASymptoms.sort(byIc);
  onlyBSymptoms.sort(byIc);

  // clusters
  const ca = clustersOf(idx, aId);
  const cb = clustersOf(idx, bId);
  const clusters = {
    both: ca.filter((c) => cb.includes(c)),
    aOnly: ca.filter((c) => !cb.includes(c)),
    bOnly: cb.filter((c) => !ca.includes(c)),
  };

  // inheritance, onset, variant spectrum
  const attr = (n: AtlasNode, k: "inheritance" | "onset") => (n.type === "disease" ? (n.attrs?.[k] ?? null) : null);
  const inhA = attr(a.disease, "inheritance");
  const inhB = attr(b.disease, "inheritance");
  const onA = attr(a.disease, "onset");
  const onB = attr(b.disease, "onset");
  const spA = variantSpectrum(idx, a);
  const spB = variantSpectrum(idx, b);
  const spectrumDiffers =
    !!spA && !!spB && (spA.dominant !== spB.dominant || Math.abs(spA.share.missense - spB.share.missense) >= 0.25 || Math.abs(spA.share.truncating - spB.share.truncating) >= 0.25);

  // assets and studies
  const matchAB = matchBetween(idx, aId, bId);
  const matchBA = matchBetween(idx, bId, aId);
  const fromA = matchAB ? existingWork(idx, aId, [matchAB]) : [];
  const fromB = matchBA ? existingWork(idx, bId, [matchBA]) : [];
  const coverOf = (dId: string) =>
    new Map(neighbors(idx, dId, { relations: ["covers", "studies"], direction: "in" }).map((n) => [n.other, n.edge] as const));
  const covA = coverOf(aId);
  const covB = coverOf(bId);
  const both: CompareItem[] = [];
  const aOnly: CompareItem[] = [];
  const bOnly: CompareItem[] = [];
  const studiesBoth: CompareItem[] = [];
  for (const [id, edgeA] of covA) {
    const node = idx.nodeById.get(id);
    if (!node) continue;
    const edgeB = covB.get(id);
    if (edgeB) (node.type === "study" ? studiesBoth : both).push({ node, edgeA, edgeB });
    else if (node.type === "asset") aOnly.push({ node, edgeA, reuse: fromB.find((it) => !it.own && it.node.id === id) });
  }
  for (const [id, edgeB] of covB) {
    const node = idx.nodeById.get(id);
    if (!node || covA.has(id) || node.type !== "asset") continue;
    bOnly.push({ node, edgeB, reuse: fromA.find((it) => !it.own && it.node.id === id) });
  }
  const reuseOrder = { as_is: 0, adaptable: 1, not_applicable: 2 } as const;
  const byReuse = (x: CompareItem, y: CompareItem) => reuseOrder[x.reuse?.reuse ?? "not_applicable"] - reuseOrder[y.reuse?.reuse ?? "not_applicable"];
  aOnly.sort(byReuse);
  bOnly.sort(byReuse);

  // people and organisations connected to both
  const connectors: Connector[] = [];
  for (const n of idx.graph.nodes) {
    if (n.type !== "researcher" && n.type !== "patient_org" && n.type !== "grant") continue;
    const rel = n.type === "researcher" ? "works_on" : n.type === "patient_org" ? "serves" : "about";
    const linksA: AtlasEdge[] = [];
    const linksB: AtlasEdge[] = [];
    for (const nb of neighbors(idx, n.id, { relations: [rel], direction: "out" })) {
      const t = idx.nodeById.get(nb.other);
      if (!t) continue;
      const ds = diseasesFor(idx, t);
      if (ds.includes(aId)) linksA.push(nb.edge);
      if (ds.includes(bId)) linksB.push(nb.edge);
    }
    if (linksA.length && linksB.length) connectors.push({ node: n, linksA, linksB });
  }
  const typeOrder = { patient_org: 0, researcher: 1, grant: 2 } as Record<string, number>;
  connectors.sort((x, y) => (typeOrder[x.node.type] ?? 9) - (typeOrder[y.node.type] ?? 9));

  const cmp: Comparison = {
    a,
    b,
    shortA,
    shortB,
    shared,
    onlyA,
    onlyB,
    sharedSymptoms,
    onlyASymptoms,
    onlyBSymptoms,
    clusters,
    inheritance: { a: inhA, b: inhB, differs: !!inhA && !!inhB && inhA !== inhB },
    onset: { a: onA, b: onB, differs: !!onA && !!onB && onA !== onB },
    spectrum: { a: spA, b: spB, differs: spectrumDiffers },
    assets: { both, aOnly, bOnly },
    studiesBoth,
    connectors,
    questions: [],
  };
  cmp.questions = expertQuestions(cmp);
  return cmp;
}

/** Deterministic, template-based questions for an expert, generated from the differences found. */
export function expertQuestions(c: Comparison): ExpertQuestion[] {
  const A = c.shortA;
  const B = c.shortB;
  const q: ExpertQuestion[] = [];
  if (!c.shared.length) {
    q.push({ topic: "Biology", text: `The atlas finds no shared mechanism between ${A} and ${B}. Is there shared biology beyond similar symptoms?`, edgeIds: [] });
  }
  // one question per shared mechanism that is disputed or thin on either side
  for (const s of c.shared) {
    const mech = lowerFirst(s.mechanism.label);
    const flagged = ([[s.a, A], [s.b, B]] as const).filter(([side]) => side.minority || side.contested);
    if (flagged.length === 2) {
      q.push({
        topic: "Biology",
        text: `For both ${A} and ${B}, the link to ${mech} is contested or a minority view. Is this mechanism really shared, and does it matter for a joint project?`,
        edgeIds: [s.a.edge.id, s.b.edge.id],
      });
    } else if (flagged.length === 1) {
      const [side, name] = flagged[0];
      q.push({
        topic: "Biology",
        text: `${name}'s link to ${mech} is ${side.minority ? "a minority view" : "contested"} in the sources. Does it hold for the patients who would join?`,
        edgeIds: [s.a.edge.id, s.b.edge.id],
      });
    } else {
      const weak = ([[s.a, A], [s.b, B]] as const).find(([side]) => side.link.strength < 0.45);
      if (weak) {
        q.push({
          topic: "Biology",
          text: `How solid is the evidence that ${weak[1]} involves ${mech}? In the atlas it rests on ${weak[0].edge.evidence_level === "inferred" ? "an inference" : "limited evidence"} (confidence ${weak[0].edge.confidence.toFixed(2)}).`,
          edgeIds: [weak[0].edge.id],
        });
      }
    }
  }
  for (const [list, name, other] of [
    [c.onlyA, A, B],
    [c.onlyB, B, A],
  ] as const) {
    const strong = list.filter((m) => !m.minority).slice(0, 2);
    if (strong.length) {
      q.push({
        topic: "Biology",
        text: `${joinList(strong.map((m) => lowerFirst(m.link.mechanism.label)), 2)} ${strong.length === 1 ? "is" : "are"} shown for ${name} but not ${other}. Is that a real difference, or just not studied yet in ${other}?`,
        edgeIds: strong.map((m) => m.edge.id),
      });
    }
  }
  const sa = c.spectrum.a;
  const sb = c.spectrum.b;
  if (c.spectrum.differs && sa && sb) {
    q.push({
      topic: "Measuring progress",
      text: `${A} changes are ${spectrumWords(sa)}, while ${B} changes are ${spectrumWords(sb)}. Would outcome measures and therapy approaches built for one transfer to the other?`,
      edgeIds: [...sa.edges.slice(0, 2), ...sb.edges.slice(0, 2)].map((e) => e.id),
    });
  }
  if (c.onlyASymptoms.length || c.onlyBSymptoms.length) {
    const xa = c.onlyASymptoms.slice(0, 2);
    const xb = c.onlyBSymptoms.slice(0, 2);
    const parts = [
      xa.length ? `${joinList(xa.map((s) => lowerFirst(s.phenotype.label)), 2)} (recorded in ${A} only)` : "",
      xb.length ? `${joinList(xb.map((s) => lowerFirst(s.phenotype.label)), 2)} (recorded in ${B} only)` : "",
    ].filter(Boolean);
    q.push({
      topic: "Measuring progress",
      text: `Are these distinctive symptoms really absent in the other group, or just not documented: ${parts.join("; ")}?`,
      edgeIds: [...xa, ...xb].map((s) => s.edge.id),
    });
  }
  if (c.inheritance.differs) {
    q.push({ topic: "Who can take part", text: `Inheritance differs (${A}: ${c.inheritance.a}; ${B}: ${c.inheritance.b}). Does that change who can enrol or how families are counselled?`, edgeIds: [] });
  }
  if (c.onset.differs) {
    q.push({ topic: "Who can take part", text: `Age at onset differs (${A}: ${c.onset.a}; ${B}: ${c.onset.b}). Would a shared study need different age ranges?`, edgeIds: [] });
  }
  for (const s of c.studiesBoth.slice(0, 2)) {
    q.push({
      topic: "Who can take part",
      text: `${s.node.label} already enrols both groups. Do its eligibility rules and visit schedule suit both equally?`,
      edgeIds: [s.edgeA?.id, s.edgeB?.id].filter((x): x is string => !!x),
    });
  }
  const adapt = [...c.assets.aOnly, ...c.assets.bOnly].find((it) => it.reuse?.reuse === "adaptable");
  if (adapt) {
    const builtFor = adapt.edgeA ? A : B;
    const forOther = adapt.edgeA ? B : A;
    q.push({
      topic: "Practical checks",
      text: `Could ${adapt.node.label} (built for ${builtFor}) take ${forOther} families, and what would need to change?`,
      edgeIds: [adapt.edgeA?.id ?? adapt.edgeB?.id].filter((x): x is string => !!x),
    });
  }
  // keep the list short: at most 4 biology questions, 10 in total, each starting with a capital
  let biology = 0;
  return q
    .filter((x) => x.topic !== "Biology" || ++biology <= 4)
    .slice(0, 10)
    .map((x) => ({ ...x, text: capFirst(x.text) }));
}
