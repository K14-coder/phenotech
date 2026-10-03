// Computations behind the disease action page. Everything here is derived from graph.json
// at runtime; nothing is invented. Heuristics are explained in the UI next to their output.
import { clustersOf, gapsAbout, neighbors, type GraphIndex } from "./graph";
import type { AssetKind, AtlasEdge, AtlasNode, Gap } from "./types";
import { joinList, lowerFirst } from "./text";

// ---------- Disease context ----------

export interface MechanismLink {
  mechanism: AtlasNode;
  /** 0–1: direct driven_by edges count fully; gene and variant routes are discounted */
  strength: number;
  /** edges that connect the disease to this mechanism (direct or via gene / variant group) */
  edges: AtlasEdge[];
  route: "direct" | "gene" | "variant";
}

export interface DiseaseContext {
  disease: AtlasNode;
  genes: AtlasNode[];
  variantGroups: AtlasNode[];
  mechanisms: Map<string, MechanismLink>;
  phenotypes: Map<string, AtlasEdge>;
}

const GENE_ROUTE = 0.7;
const VARIANT_ROUTE = 0.85;

export function diseaseContext(idx: GraphIndex, diseaseId: string): DiseaseContext | null {
  const disease = idx.nodeById.get(diseaseId);
  if (!disease) return null;
  const mechanisms = new Map<string, MechanismLink>();
  const offer = (mechId: string, strength: number, edges: AtlasEdge[], route: MechanismLink["route"]) => {
    const m = idx.nodeById.get(mechId);
    if (!m || m.type !== "mechanism") return;
    const prev = mechanisms.get(mechId);
    if (!prev || strength > prev.strength) mechanisms.set(mechId, { mechanism: m, strength, edges, route });
  };

  for (const nb of neighbors(idx, diseaseId, { relations: ["driven_by"], direction: "out" })) {
    offer(nb.other, nb.edge.confidence * hypoFactor(nb.edge), [nb.edge], "direct");
  }
  const genes: AtlasNode[] = [];
  const variantGroups: AtlasNode[] = [];
  for (const g of neighbors(idx, diseaseId, { relations: ["causes"], direction: "in" })) {
    const gene = idx.nodeById.get(g.other);
    if (!gene) continue;
    genes.push(gene);
    for (const p of neighbors(idx, gene.id, { relations: ["participates_in"], direction: "out" })) {
      offer(p.other, GENE_ROUTE * Math.min(g.edge.confidence, p.edge.confidence) * hypoFactor(p.edge), [g.edge, p.edge], "gene");
    }
    for (const v of neighbors(idx, gene.id, { relations: ["variant_in"], direction: "in" })) {
      const vg = idx.nodeById.get(v.other);
      if (!vg) continue;
      variantGroups.push(vg);
      for (const fx of neighbors(idx, vg.id, { relations: ["has_effect"], direction: "out" })) {
        const s = VARIANT_ROUTE * Math.min(g.edge.confidence, v.edge.confidence, fx.edge.confidence);
        offer(fx.other, s * hypoFactor(fx.edge) * (fx.edge.status === "contested" ? 0.6 : 1), [g.edge, v.edge, fx.edge], "variant");
      }
    }
  }
  const phenotypes = new Map<string, AtlasEdge>();
  for (const nb of neighbors(idx, diseaseId, { relations: ["has_phenotype"], direction: "out" })) {
    phenotypes.set(nb.other, nb.edge);
  }
  return { disease, genes, variantGroups, mechanisms, phenotypes };
}

function hypoFactor(e: AtlasEdge) {
  return e.evidence_level === "hypothesis" ? 0.4 : 1;
}

// ---------- Closest diseases ----------

export interface SharedMechanism {
  mechanism: AtlasNode;
  strength: number;
  edges: AtlasEdge[];
}

export interface SharedPhenotype {
  phenotype: AtlasNode;
  ic: number;
  distinctive: boolean;
  edges: AtlasEdge[];
}

export interface DiseaseMatch {
  disease: AtlasNode;
  context: DiseaseContext;
  score: number;
  directEdges: AtlasEdge[];
  sharedMechanisms: SharedMechanism[];
  sharedPhenotypes: SharedPhenotype[];
  /** symptoms recorded for the focus disease but not this one (most distinctive first) */
  notShared: AtlasNode[];
}

export function phenotypeIc(idx: GraphIndex, n: AtlasNode): number {
  return n.type === "phenotype" && typeof n.attrs?.ic === "number" ? n.attrs.ic : idx.maxIc / 2;
}

/** "Distinctive" = information content in the top half of this graph's symptoms. */
export function distinctiveThreshold(idx: GraphIndex): number {
  const ics = idx.graph.nodes
    .filter((n) => n.type === "phenotype")
    .map((n) => phenotypeIc(idx, n))
    .sort((a, b) => a - b);
  if (!ics.length) return Infinity;
  return ics[Math.floor(ics.length / 2)];
}

export function closestDiseases(idx: GraphIndex, diseaseId: string, limit = 8): DiseaseMatch[] {
  const me = diseaseContext(idx, diseaseId);
  if (!me) return [];
  const threshold = distinctiveThreshold(idx);
  const out: DiseaseMatch[] = [];

  for (const other of idx.graph.nodes) {
    if (other.type !== "disease" || other.id === diseaseId) continue;
    const ctx = diseaseContext(idx, other.id);
    if (!ctx) continue;

    const sharedMechanisms: SharedMechanism[] = [];
    for (const [mid, a] of me.mechanisms) {
      const b = ctx.mechanisms.get(mid);
      if (!b) continue;
      sharedMechanisms.push({ mechanism: a.mechanism, strength: Math.min(a.strength, b.strength), edges: uniq([...a.edges, ...b.edges]) });
    }
    sharedMechanisms.sort((x, y) => y.strength - x.strength);

    const sharedPhenotypes: SharedPhenotype[] = [];
    let icShared = 0;
    let icUnion = 0;
    const seen = new Set<string>();
    for (const [pid, ea] of me.phenotypes) {
      const p = idx.nodeById.get(pid);
      if (!p) continue;
      const ic = phenotypeIc(idx, p);
      icUnion += ic;
      seen.add(pid);
      const eb = ctx.phenotypes.get(pid);
      if (eb) {
        icShared += ic;
        sharedPhenotypes.push({ phenotype: p, ic, distinctive: ic >= threshold, edges: [ea, eb] });
      }
    }
    for (const pid of ctx.phenotypes.keys()) {
      if (seen.has(pid)) continue;
      const p = idx.nodeById.get(pid);
      if (p) icUnion += phenotypeIc(idx, p);
    }
    sharedPhenotypes.sort((x, y) => y.ic - x.ic);

    const directEdges = (idx.adjacency.get(diseaseId) ?? [])
      .filter((n) => n.other === other.id && (n.edge.type === "shares_mechanism" || n.edge.type === "similar_phenotype"))
      .map((n) => n.edge);

    const mechScore = 1 - sharedMechanisms.reduce((acc, m) => acc * (1 - m.strength), 1);
    const phenoScore = icUnion ? icShared / icUnion : 0;
    const directScore = directEdges.reduce((mx, e) => Math.max(mx, e.confidence * hypoFactor(e)), 0);
    const score = 0.45 * mechScore + 0.25 * phenoScore + 0.3 * directScore;
    if (score <= 0) continue;

    const notShared = [...me.phenotypes.keys()]
      .filter((pid) => !ctx.phenotypes.has(pid))
      .map((pid) => idx.nodeById.get(pid))
      .filter((n): n is AtlasNode => !!n)
      .sort((a, b) => phenotypeIc(idx, b) - phenotypeIc(idx, a));

    out.push({ disease: other, context: ctx, score, directEdges, sharedMechanisms, sharedPhenotypes, notShared });
  }
  return out.sort((a, b) => b.score - a.score).slice(0, limit);
}

export function overlapWord(score: number): string {
  if (score >= 0.45) return "Strong overlap";
  if (score >= 0.3) return "Moderate overlap";
  return "Weak overlap";
}

function uniq<T>(xs: T[]): T[] {
  return [...new Set(xs)];
}

/** Keep the first item per key (lists can reach the same node through several paths). */
export function uniqBy<T>(xs: T[], key: (x: T) => string): T[] {
  const seen = new Set<string>();
  return xs.filter((x) => {
    const k = key(x);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// ---------- What already exists ----------

export type Reuse = "as_is" | "adaptable" | "not_applicable";

export const REUSE_META: Record<Reuse, { label: string; help: string }> = {
  as_is: { label: "Reusable as-is", help: "Built for this disease, or a shared platform that can take related conditions." },
  adaptable: { label: "Adaptable", help: "Built for a neighbour that shares a mechanism or distinctive symptoms. Needs changes before use." },
  not_applicable: { label: "Not directly applicable", help: "Tied to a different gene, or the overlap is too weak. Methods may still transfer." },
};

export interface ExistingItem {
  node: AtlasNode;
  forDisease: AtlasNode;
  link: AtlasEdge;
  own: boolean;
  reuse: Reuse;
  reason: string;
  differs: string[];
  maintainers: AtlasNode[];
  /** other diseases this resource also covers or studies */
  alsoCovers: AtlasNode[];
}

const GENE_SPECIFIC: AssetKind[] = ["animal_model", "cell_model"];
const SHARED_PLATFORMS: AssetKind[] = ["research_network", "data_platform", "funding_program"];
const SYMPTOM_TRANSFERABLE: AssetKind[] = ["registry", "natural_history_study", "outcome_measure", "data_platform"];

export function existingWork(idx: GraphIndex, diseaseId: string, matches: DiseaseMatch[]): ExistingItem[] {
  const me = idx.nodeById.get(diseaseId);
  if (!me) return [];
  const items: ExistingItem[] = [];
  const seen = new Set<string>();

  const collect = (d: AtlasNode, match?: DiseaseMatch) => {
    for (const nb of neighbors(idx, d.id, { relations: ["covers", "studies"], direction: "in" })) {
      const node = idx.nodeById.get(nb.other);
      if (!node || seen.has(node.id)) continue;
      seen.add(node.id);
      const maintainers = neighbors(idx, node.id, { relations: ["maintains"], direction: "in" })
        .map((m) => idx.nodeById.get(m.other))
        .filter((n): n is AtlasNode => !!n);
      const { reuse, reason } = judgeReuse(idx, node, d, match);
      const alsoCovers = neighbors(idx, node.id, { relations: ["covers", "studies"], direction: "out" })
        .map((x) => idx.nodeById.get(x.other))
        .filter((x): x is AtlasNode => !!x && x.type === "disease" && x.id !== diseaseId && x.id !== d.id);
      items.push({
        node,
        forDisease: d,
        link: nb.edge,
        own: !match,
        reuse,
        reason,
        differs: match ? differences(idx, match, node) : [],
        maintainers,
        alsoCovers,
      });
    }
  };
  collect(me);
  for (const m of matches) collect(m.disease, m);
  const order: Record<Reuse, number> = { as_is: 0, adaptable: 1, not_applicable: 2 };
  const rank = new Map(matches.map((m, i) => [m.disease.id, i]));
  // own first; then closest neighbour first; then the most directly useful kinds first
  return items.sort(
    (a, b) =>
      Number(b.own) - Number(a.own) ||
      order[a.reuse] - order[b.reuse] ||
      (rank.get(a.forDisease.id) ?? -1) - (rank.get(b.forDisease.id) ?? -1) ||
      kindRank(a.node) - kindRank(b.node),
  );
}

const KIND_ORDER: string[] = [
  "natural_history_study",
  "outcome_measure",
  "registry",
  "animal_model",
  "cell_model",
  "data_platform",
  "biobank",
  "assay",
  "trial_design",
  "research_network",
  "funding_program",
];

/** Usefulness order for sorting resources: natural history and registries first, then measures and models; trials last. */
function kindRank(n: AtlasNode): number {
  if (n.type === "asset") {
    const i = KIND_ORDER.indexOf(n.attrs?.kind ?? "");
    return i < 0 ? KIND_ORDER.length : i;
  }
  return KIND_ORDER.length + (n.type === "study" && n.attrs?.study_type === "observational" ? 1 : 2);
}

function geneOf(idx: GraphIndex, diseaseId: string): string {
  const g = neighbors(idx, diseaseId, { relations: ["causes"], direction: "in" })[0];
  return g ? idx.nodeById.get(g.other)?.label ?? "another gene" : "another gene";
}

function judgeReuse(idx: GraphIndex, node: AtlasNode, d: AtlasNode, match?: DiseaseMatch): { reuse: Reuse; reason: string } {
  if (!match) return { reuse: "as_is", reason: "Built for this disease." };
  const strongMech = match.sharedMechanisms.find((m) => m.strength >= 0.3);
  const distinctive = match.sharedPhenotypes.filter((p) => p.distinctive);
  const gene = geneOf(idx, d.id);

  if (node.type === "asset") {
    const kind = node.attrs?.kind;
    if (kind && GENE_SPECIFIC.includes(kind)) {
      return strongMech
        ? {
            reuse: "adaptable",
            reason: `It carries a ${gene} change, so it can't be used as-is, but the diseases share ${lowerFirst(strongMech.mechanism.label)}: its methods and measurements could be adapted.`,
          }
        : {
            reuse: "not_applicable",
            reason: `Carries a ${gene} change, so it models a different gene. Its methods and measurements may still transfer.`,
          };
    }
    if (strongMech) {
      if (kind && SHARED_PLATFORMS.includes(kind)) {
        return { reuse: "as_is", reason: `A shared platform; ${d.label} shares ${strongMech.mechanism.label}. Confirm it accepts related conditions.` };
      }
      return { reuse: "adaptable", reason: `${d.label} shares ${lowerFirst(strongMech.mechanism.label)} with your disease, so the design could be extended with changes.` };
    }
    if (distinctive.length && kind && SYMPTOM_TRANSFERABLE.includes(kind)) {
      return { reuse: "adaptable", reason: `Shares distinctive symptoms (${joinList(distinctive.map((p) => p.phenotype.label), 2)}); symptom measures may transfer.` };
    }
    return { reuse: "not_applicable", reason: "The overlap with this disease is weak in the current evidence." };
  }

  if (node.type === "study") {
    if (node.attrs?.study_type === "observational") {
      return strongMech
        ? { reuse: "adaptable", reason: `Observational design for a disease that shares ${strongMech.mechanism.label}.` }
        : { reuse: "not_applicable", reason: "Observational study for a weakly related disease." };
    }
    // interventional: is the tested therapy aimed at a mechanism this disease also has?
    const therapies = neighbors(idx, node.id, { relations: ["tests"], direction: "out" }).map((t) => t.other);
    const targets = therapies.flatMap((t) => neighbors(idx, t, { relations: ["targets"], direction: "out" }).map((x) => x.other));
    const shared = match.sharedMechanisms.find((m) => targets.includes(m.mechanism.id));
    if (shared) return { reuse: "adaptable", reason: `Tests a therapy aimed at ${shared.mechanism.label}, which this disease also shows. Eligibility would need to change.` };
    return { reuse: "not_applicable", reason: "Tests a therapy aimed at a mechanism not shown for this disease." };
  }
  return { reuse: "not_applicable", reason: "Not a reusable resource type." };
}

function differences(idx: GraphIndex, match: DiseaseMatch, node: AtlasNode): string[] {
  // (what it was built for and its type are already in the card header)
  const out: string[] = [];
  if (match.notShared.length) {
    out.push(`Symptoms of your disease not recorded there: ${joinList(match.notShared.map((p) => lowerFirst(p.label)), 2)}.`);
  }
  const theirOnly = [...match.context.mechanisms.values()]
    .filter((m) => !match.sharedMechanisms.some((s) => s.mechanism.id === m.mechanism.id))
    .map((m) => m.mechanism.label);
  if (theirOnly.length) out.push(`Mechanisms only shown there: ${joinList(theirOnly, 2)}.`);
  if (node.type === "study" && node.attrs?.eligibility_note) out.push(`Eligibility: ${node.attrs.eligibility_note}`);
  return out;
}

// ---------- Partners ----------

export interface OrgPartner {
  org: AtlasNode;
  serves: AtlasNode;
  edge: AtlasEdge;
  match?: DiseaseMatch;
}

export interface ResearcherPartner {
  researcher: AtlasNode;
  /** works_on links, each with the disease it relates to */
  links: { target: AtlasNode; edge: AtlasEdge; diseases: string[] }[];
  /** labels of diseases this person's work touches */
  diseases: string[];
  bridges: boolean;
}

/**
 * A patient group is "yours" only if a source says it serves this disease (not inferred) and it is
 * not an umbrella or multi-gene organisation. Umbrella groups are shown as the closest community.
 */
export function isSpecificOrg(o: OrgPartner): boolean {
  const scope = o.org.type === "patient_org" ? o.org.attrs?.scope ?? "" : "";
  const backed = o.edge.evidence_level !== "inferred" && o.edge.evidence_level !== "hypothesis";
  return backed && !/^(umbrella|multi-gene|multi-disease|consortium)/i.test(scope) && !/consortium|coalition/i.test(scope);
}

export function communitiesFor(idx: GraphIndex, diseaseId: string): { specific: OrgPartner[]; umbrella: OrgPartner[]; registries: ExistingItemLite[] } {
  const all = uniqBy(orgsFor(idx, diseaseId), (o) => o.org.id);
  const registries = neighbors(idx, diseaseId, { relations: ["covers"], direction: "in" })
    .map((nb) => ({ node: idx.nodeById.get(nb.other)!, edge: nb.edge }))
    .filter((r) => r.node?.type === "asset" && (r.node.attrs?.kind === "registry" || r.node.attrs?.kind === "data_platform" || r.node.attrs?.kind === "research_network"));
  return { specific: all.filter(isSpecificOrg), umbrella: all.filter((o) => !isSpecificOrg(o)), registries: uniqBy(registries, (r) => r.node.id) };
}

export interface ExistingItemLite {
  node: AtlasNode;
  edge: AtlasEdge;
}

/** Therapies with published evidence for this disease (developed_for), strongest first. */
export function therapiesFor(idx: GraphIndex, diseaseId: string): ExistingItemLite[] {
  return uniqBy(neighbors(idx, diseaseId, { relations: ["developed_for"], direction: "in" }), (n) => n.other)
    .map((nb) => ({ node: idx.nodeById.get(nb.other)!, edge: nb.edge }))
    .filter((t) => t.node?.type === "therapy")
    .sort((a, b) => b.edge.confidence - a.edge.confidence);
}

export function orgsFor(idx: GraphIndex, diseaseId: string, match?: DiseaseMatch): OrgPartner[] {
  const d = idx.nodeById.get(diseaseId);
  if (!d) return [];
  return neighbors(idx, diseaseId, { relations: ["serves"], direction: "in" })
    .map((nb) => ({ org: idx.nodeById.get(nb.other)!, serves: d, edge: nb.edge, match }))
    .filter((p) => !!p.org);
}

/** Patient groups serving the neighbours, each listed once (umbrella groups serve several), minus our own. */
export function relatedOrgsFor(idx: GraphIndex, matches: DiseaseMatch[], own: OrgPartner[]): OrgPartner[] {
  const seen = new Set(own.map((o) => o.org.id));
  const out: OrgPartner[] = [];
  for (const m of matches) {
    for (const o of orgsFor(idx, m.disease.id, m)) {
      if (seen.has(o.org.id)) continue;
      seen.add(o.org.id);
      out.push(o);
    }
  }
  return out;
}

/** Which diseases does a works_on target relate to? */
export function diseasesFor(idx: GraphIndex, node: AtlasNode): string[] {
  switch (node.type) {
    case "disease":
      return [node.id];
    case "gene":
      return neighbors(idx, node.id, { relations: ["causes"], direction: "out" }).map((n) => n.other);
    case "mechanism": {
      const direct = neighbors(idx, node.id, { relations: ["driven_by"], direction: "in" }).map((n) => n.other);
      const viaGenes = neighbors(idx, node.id, { relations: ["participates_in"], direction: "in" }).flatMap((g) =>
        neighbors(idx, g.other, { relations: ["causes"], direction: "out" }).map((n) => n.other),
      );
      return [...new Set([...direct, ...viaGenes])];
    }
    default:
      return [];
  }
}

export function researcherPartners(idx: GraphIndex, diseaseId: string, matches: DiseaseMatch[]): ResearcherPartner[] {
  const neighbourIds = new Set(matches.map((m) => m.disease.id));
  const researchers = idx.graph.nodes.filter((n) => n.type === "researcher");
  const out: ResearcherPartner[] = [];
  for (const r of researchers) {
    const links = neighbors(idx, r.id, { relations: ["works_on"], direction: "out" })
      .map((nb) => {
        const target = idx.nodeById.get(nb.other);
        return target ? { target, edge: nb.edge, diseases: diseasesFor(idx, target) } : null;
      })
      .filter((x): x is NonNullable<typeof x> => !!x);
    const all = new Set(links.flatMap((l) => l.diseases));
    if (!all.has(diseaseId) && ![...all].some((d) => neighbourIds.has(d))) continue;
    const touchesMe = all.has(diseaseId);
    const touchesNeighbour = [...all].some((d) => neighbourIds.has(d));
    out.push({
      researcher: r,
      links: uniqBy(links, (l) => l.edge.id),
      diseases: [...all].map((d) => idx.nodeById.get(d)?.label ?? d),
      bridges: touchesMe && touchesNeighbour,
    });
  }
  return out
    .filter((p) => p.bridges || p.diseases.length > 0)
    .sort((a, b) => Number(b.bridges) - Number(a.bridges) || b.diseases.length - a.diseases.length);
}

// ---------- Next step ----------

export interface NextStep {
  title: string;
  why: string;
  checks: string[];
  edgeIds: string[];
}

const CORE_ASSETS: AssetKind[] = ["natural_history_study", "registry", "outcome_measure"];

export function suggestNextStep(
  idx: GraphIndex,
  disease: AtlasNode,
  matches: DiseaseMatch[],
  items: ExistingItem[],
  ownOrgs: OrgPartner[],
  researchers: ResearcherPartner[],
  gaps: Gap[],
): NextStep {
  const best = matches.find((m) => m.sharedMechanisms.length > 0) ?? matches[0];
  const checks: string[] = [];
  const edgeIds: string[] = [];
  const bridge = researchers.find((r) => r.bridges);

  if (!best) {
    return {
      title: `Document what is known about ${disease.label} and invite related communities`,
      why: "The atlas found no related disease with shared mechanism or symptoms in the current data.",
      checks: gaps.slice(0, 3).map((g) => g.question),
      edgeIds,
    };
  }

  const mech = best.sharedMechanisms[0];
  if (mech) edgeIds.push(...mech.edges.map((e) => e.id));
  edgeIds.push(...best.directEdges.map((e) => e.id));
  const reason = mech
    ? `${best.disease.label} shares ${mech.mechanism.label} with ${disease.label}`
    : `${best.disease.label} shares symptoms with ${disease.label}`;

  const ownCore = items.find((i) => i.own && i.node.type === "asset" && CORE_ASSETS.includes(i.node.attrs?.kind as AssetKind));
  // prefer a natural history study, then a registry or outcome measure, ideally run by a patient group
  const theirCore = items
    .filter(
      (i) => !i.own && i.forDisease.id === best.disease.id && i.reuse !== "not_applicable" && i.node.type === "asset" && CORE_ASSETS.includes(i.node.attrs?.kind as AssetKind),
    )
    .sort(
      (a, b) =>
        kindRank(a.node) - kindRank(b.node) ||
        Number(b.maintainers.some((m) => m.type === "patient_org")) - Number(a.maintainers.some((m) => m.type === "patient_org")),
    )[0];
  const theirOrgs = orgsFor(idx, best.disease.id, best);

  let title: string;
  if (ownCore && !theirCore) {
    title = `Offer your ${ownCore.node.label.replace(/\s*\(sample\)$/, "")} to ${best.disease.label} families`;
    if (!theirOrgs.length) checks.push(`${best.disease.label} has no patient group in the atlas, so reach families through clinics or the researchers below.`);
  } else if (theirCore) {
    const owner = theirCore.maintainers.find((m) => m.type === "patient_org") ?? theirCore.maintainers[0] ?? theirOrgs[0]?.org;
    title = `Ask ${owner ? owner.label : `the team behind ${theirCore.node.label}`} whether ${theirCore.node.label} could include ${disease.label}`;
    edgeIds.push(theirCore.link.id);
  } else if (theirOrgs.length) {
    title = `Contact ${theirOrgs[0].org.label} to compare notes on ${mech ? mech.mechanism.label : "shared symptoms"}`;
    edgeIds.push(theirOrgs[0].edge.id);
  } else {
    title = `Start a shared symptom record with ${best.disease.label} families`;
  }
  if (!ownOrgs.length) checks.unshift(`${disease.label} has no patient group of its own in the atlas yet; a family network could be the first step.`);
  if (bridge) checks.push(`${bridge.researcher.label} already works on ${joinList(bridge.diseases, 3)} and could review the plan.`);
  if (best.notShared.length) checks.push(`Confirm whether ${joinList(best.notShared.slice(0, 2).map((p) => lowerFirst(p.label)), 2)} also occur in ${best.disease.label}.`);
  const contested = mech?.edges.find((e) => e.status === "contested");
  if (contested) checks.push("One link in this route is contested; read both sides in the evidence panel.");
  for (const g of gaps.slice(0, 2)) checks.push(g.question);

  return { title, why: `${reason}. ${mech ? "A shared mechanism means shared biology, so data, designs and expertise can carry over." : ""}`.trim(), checks, edgeIds: [...new Set(edgeIds)] };
}

export function gapsForDisease(idx: GraphIndex, ctx: DiseaseContext): Gap[] {
  const ids = [
    ctx.disease.id,
    ...ctx.genes.map((g) => g.id),
    ...ctx.variantGroups.map((v) => v.id),
    ...[...ctx.mechanisms.keys()],
    ...clustersOf(idx, ctx.disease.id).map((c) => c.id),
  ];
  return gapsAbout(idx, ids);
}

/** The match record between two specific diseases (empty overlap if they share nothing). */
export function matchBetween(idx: GraphIndex, aId: string, bId: string): DiseaseMatch | null {
  const found = closestDiseases(idx, aId, 1000).find((m) => m.disease.id === bId);
  if (found) return found;
  const a = diseaseContext(idx, aId);
  const b = diseaseContext(idx, bId);
  if (!a || !b) return null;
  const notShared = [...a.phenotypes.keys()]
    .filter((pid) => !b.phenotypes.has(pid))
    .map((pid) => idx.nodeById.get(pid))
    .filter((n): n is AtlasNode => !!n);
  return { disease: b.disease, context: b, score: 0, directEdges: [], sharedMechanisms: [], sharedPhenotypes: [], notShared };
}
