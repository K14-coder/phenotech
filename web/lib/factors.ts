"use client";

// The seven factors the atlas compares diseases on, in one fixed order everywhere:
//   genes involved · signalling pathway · tissue type · symptoms · protein structure & family · mutation type ·
//   molecular consequence.
// Atlas pairs (188 entities, 17,578 pairs) use the computed per-axis scores of data/derived/mechsim.json
// (pipeline/derive/mechsim.py; symptoms = its IC-weighted symptom cosine). Other pairs are compared here from
// per-gene data (web/factors shards: PANTHER/Pfam/InterPro families, HPA tissues, ClinVar spectrum; mechclass:
// G2P/ClinGen class and direction), mirroring the simple Jaccard / Jensen-Shannon rules of
// pipeline/eval/feature_eval.py. Missing data stays missing (null), never zero.
import { bucketOfGene } from "./clinvar";
import { loadAvailableOnce } from "./population";
import type { GraphIndex } from "./graph";
import { diseaseContext, phenotypeIc } from "./insights";

export type FactorKey = "gene" | "pathway" | "tissue" | "symptoms" | "structure" | "mutation" | "fate";

export interface FactorDef {
  key: FactorKey;
  label: string;
  /** short form for bars and chips */
  short: string;
  /** graph edge type that draws this factor's links (atlas pairs above the axis floor) */
  edge: string;
  /** plain one-line explanation ("What does this mean?") */
  plain: string;
  sources: string;
}

export const FACTORS: FactorDef[] = [
  { key: "gene", label: "Genes involved", short: "Genes", edge: "shares_gene", plain: "Which gene changes cause it. Two conditions share this when the same gene can cause both.", sources: "OMIM, Orphanet, MONDO, HPO gene–disease links" },
  { key: "pathway", label: "Signalling pathway", short: "Pathway", edge: "shares_pathway", plain: "The chain of molecules the gene works in. Shared pathways can mean shared treatment ideas.", sources: "Reactome, MSigDB canonical pathways, STRING" },
  { key: "tissue", label: "Tissue type", short: "Tissue", edge: "shares_tissue", plain: "Where in the body the gene is most active and where the symptoms point.", sources: "Human Protein Atlas, GTEx v10, HPO anchors" },
  { key: "symptoms", label: "Symptoms", short: "Symptoms", edge: "similar_phenotype", plain: "The signs doctors record. The most distinctive ones count most.", sources: "HPO annotations (information-weighted)" },
  { key: "structure", label: "Protein structure & family", short: "Structure", edge: "similar_protein_structure", plain: "What the protein looks like and which protein family it belongs to.", sources: "AlphaFold (TM-align), Pfam, InterPro, PANTHER, UniProt" },
  { key: "mutation", label: "Mutation type", short: "Mutation", edge: "similar_mutation_spectrum", plain: "What kinds of DNA changes cause it: early stops, swaps of one building block, deletions…", sources: "ClinVar pathogenic / likely pathogenic" },
  { key: "fate", label: "Molecular consequence", short: "Consequence", edge: "similar_protein_fate", plain: "What the change does to the protein: missing, too little, poisoning its partners, or overactive.", sources: "G2P, ClinGen dosage, atlas variant-group evidence, direction layer" },
];

/** Combined-score weights tested on 1,300 external PrimeKG cases (ingest.md, global/README "Similar diseases"):
 *  symptoms 1, genes 0.5, pathway 0.5; the other factors did not improve ranking, so they default to 0. */
export const TESTED_WEIGHTS: Record<FactorKey, number> = { symptoms: 1, gene: 0.5, pathway: 0.5, tissue: 0, structure: 0, mutation: 0, fate: 0 };

export type FactorScores = Record<FactorKey, number | null>;

export function weighted(scores: FactorScores, w: Record<FactorKey, number>): number {
  let s = 0;
  let tot = 0;
  for (const f of FACTORS) {
    const v = scores[f.key];
    if (v == null || !w[f.key]) continue;
    s += w[f.key] * v;
    tot += w[f.key];
  }
  return tot ? s / tot : 0;
}

// ---------- mechsim (atlas pairs) ----------

export interface MechsimProfile {
  id: string;
  gene: string;
  label: string;
  genes: string[];
  pathways: string[];
  tissue?: { symptoms?: [string, number][]; expression_top?: [string, number][]; hpa_specificity?: string | null };
  mutation?: { n: number; types?: Record<string, number>; consequence?: Record<string, number> };
  fate?: { vector: number[]; labels: string[]; evidence?: string[] };
  structure?: { uniprot?: string; length?: number; pfam?: string[]; clans?: string[]; pdb?: { alphafold?: { url: string; mean_plddt?: number } | null; n_pdb_entries?: number } | null } | null;
}
export interface MechsimData {
  meta: { axis_label: Record<string, string>; edge_rule: { floor: Record<string, number> }; fate_labels: Record<string, string> };
  pathway_sets: Record<string, { name: string; origin: string; url: string; size: number }>;
  pfam: Record<string, { name: string; description: string; clan?: string; clan_name?: string }>;
  profiles: MechsimProfile[];
  pair_fields: string[];
  pairs: (number | null)[][];
}

export interface MechsimIndex {
  data: MechsimData;
  byId: Map<string, number>;
  pair: (a: string, b: string) => Record<string, number | null> | null;
}

const indexCache = new WeakMap<MechsimData, MechsimIndex>();
export function mechsimIndex(data: MechsimData): MechsimIndex {
  const hit = indexCache.get(data);
  if (hit) return hit;
  const byId = new Map(data.profiles.map((p, i) => [p.id, i]));
  const F = Object.fromEntries(data.pair_fields.map((k, i) => [k, i]));
  const map = new Map<string, (number | null)[]>();
  for (const row of data.pairs) map.set(`${row[F.i]}|${row[F.j]}`, row);
  const pair = (a: string, b: string) => {
    const i = byId.get(a);
    const j = byId.get(b);
    if (i == null || j == null || i === j) return null;
    const row = map.get(`${Math.min(i, j)}|${Math.max(i, j)}`);
    return row ? (Object.fromEntries(data.pair_fields.map((k, n) => [k, row[n]])) as Record<string, number | null>) : null;
  };
  const idx = { data, byId, pair };
  indexCache.set(data, idx);
  return idx;
}

/**
 * The seven factor scores of an atlas pair: six from mechsim; symptoms from the IC-weighted Jaccard of the two
 * diseases' curated HPO symptoms in the graph (mechsim's symptom_cosine is a tissue-anchor profile, used inside
 * its tissue axis, so it is not reused as "symptoms").
 */
export function mechsimScores(ix: MechsimIndex, a: string, b: string, idx?: GraphIndex): FactorScores | null {
  const p = ix.pair(a, b);
  if (!p) return null;
  return { gene: p.gene, pathway: p.pathway, tissue: p.tissue, symptoms: idx ? symptomSim(idx, a, b) : null, structure: p.structure, mutation: p.mutation, fate: p.fate };
}

const symCache = new Map<string, number | null>();
/** IC-weighted Jaccard of curated HPO symptoms (as in lib/insights closestDiseases). */
export function symptomSim(idx: GraphIndex, a: string, b: string): number | null {
  const key = a < b ? `${a}|${b}` : `${b}|${a}`;
  if (symCache.has(key)) return symCache.get(key)!;
  const pa = diseaseContext(idx, a)?.phenotypes;
  const pb = diseaseContext(idx, b)?.phenotypes;
  let v: number | null = null;
  if (pa?.size && pb?.size) {
    let inter = 0;
    let uni = 0;
    const all = new Set([...pa.keys(), ...pb.keys()]);
    for (const id of all) {
      const n = idx.nodeById.get(id);
      if (!n) continue;
      const ic = phenotypeIc(idx, n);
      uni += ic;
      if (pa.has(id) && pb.has(id)) inter += ic;
    }
    v = uni ? inter / uni : null;
  }
  symCache.set(key, v);
  return v;
}

// ---------- per-gene data (any disease) ----------

export interface GeneFeature {
  pli: number | null;
  loeuf: number | null;
  am: number | null;
  n: number;
  c: Record<string, number> | null;
  uni?: string | null;
  len?: number | null;
  panther?: string[];
  ipr?: string[];
  pfam?: string[];
  hpa?: string | null;
  tis?: Record<string, number>;
}

const shardCache = new Map<number, Promise<Record<string, GeneFeature>>>();
export async function loadGeneFeatures(genes: string[]): Promise<Record<string, GeneFeature>> {
  const a = await loadAvailableOnce();
  if (!a.factors) return {};
  const out: Record<string, GeneFeature> = {};
  await Promise.all(
    [...new Set(genes.map(bucketOfGene))].map(async (b) => {
      let p = shardCache.get(b);
      if (!p) {
        p = fetch(`/data/derived/web/factors/${b}.json`)
          .then((r) => (r.ok ? (r.json() as Promise<{ d: Record<string, GeneFeature> }>) : { d: {} }))
          .then((j) => j.d)
          .catch(() => ({}));
        shardCache.set(b, p);
      }
      const d = await p;
      for (const g of genes) if (d[g]) out[g] = d[g];
    }),
  );
  return out;
}

export type MechClass = Record<string, { c?: string[]; d?: string }>;
let mechClassP: Promise<MechClass> | null = null;
export function loadMechClass(): Promise<MechClass> {
  mechClassP ??= fetch("/data/derived/web/mechclass.json")
    .then((r) => (r.ok ? (r.json() as Promise<MechClass>) : {}))
    .catch(() => ({}));
  return mechClassP;
}

const jacc = (a: Set<string>, b: Set<string>) => {
  if (!a.size || !b.size) return null;
  let i = 0;
  for (const x of a) if (b.has(x)) i++;
  return i / (a.size + b.size - i);
};
const union = <T,>(lists: (T[] | undefined)[]) => new Set(lists.flatMap((l) => l ?? []));

/** 1 − Jensen–Shannon distance between two ClinVar spectra (smoothed), as in mechsim's mutation axis. */
function spectrumSim(a: Record<string, number> | null, b: Record<string, number> | null): number | null {
  if (!a || !b) return null;
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])];
  const ta = keys.reduce((s, k) => s + (a[k] ?? 0), 0);
  const tb = keys.reduce((s, k) => s + (b[k] ?? 0), 0);
  if (ta < 3 || tb < 3) return null;
  const P = keys.map((k) => ((a[k] ?? 0) + 0.5) / (ta + 0.5 * keys.length));
  const Q = keys.map((k) => ((b[k] ?? 0) + 0.5) / (tb + 0.5 * keys.length));
  const M = P.map((p, i) => (p + Q[i]) / 2);
  const kl = (X: number[]) => X.reduce((s, x, i) => s + x * Math.log2(x / M[i]), 0);
  return 1 - Math.sqrt(Math.max(0, (kl(P) + kl(Q)) / 2));
}

const sumSpectra = (fs: GeneFeature[]) => {
  const out: Record<string, number> = {};
  let any = false;
  for (const f of fs)
    for (const [k, v] of Object.entries(f.c ?? {})) {
      out[k] = (out[k] ?? 0) + v;
      any = true;
    }
  return any ? out : null;
};

/** Per-factor similarity from per-gene data, for pairs outside mechsim. Gene / symptoms / pathway come from the caller. */
export function geneLevelScores(
  aGenes: string[],
  bGenes: string[],
  feats: Record<string, GeneFeature>,
  mc: MechClass,
  aId: string,
  bId: string,
): Pick<FactorScores, "tissue" | "structure" | "mutation" | "fate"> {
  const fa = aGenes.map((g) => feats[g]).filter(Boolean);
  const fb = bGenes.map((g) => feats[g]).filter(Boolean);
  const tissueA = union(fa.map((f) => Object.keys(f.tis ?? {})));
  const tissueB = union(fb.map((f) => Object.keys(f.tis ?? {})));
  const famA = union(fa.flatMap((f) => [f.panther, f.pfam, f.ipr]));
  const famB = union(fb.flatMap((f) => [f.panther, f.pfam, f.ipr]));
  const ca = mc[aId];
  const cb = mc[bId];
  let fate: number | null = null;
  if (ca && cb) {
    const s = jacc(new Set([...(ca.c ?? []), ...(ca.d ? [`dir:${ca.d}`] : [])]), new Set([...(cb.c ?? []), ...(cb.d ? [`dir:${cb.d}`] : [])]));
    fate = s;
  }
  return {
    tissue: tissueA.size && tissueB.size ? jacc(tissueA, tissueB) : null,
    structure: famA.size && famB.size ? jacc(famA, famB) : null,
    mutation: spectrumSim(sumSpectra(fa), sumSpectra(fb)),
    fate,
  };
}

// ---------- words for the strongest factors ----------

export function strongest(scores: FactorScores, words: Partial<Record<FactorKey, string>>, max = 3): string[] {
  return FACTORS.map((f) => ({ f, v: scores[f.key] }))
    .filter((x) => x.v != null && x.v >= 0.3)
    .sort((x, y) => (y.v as number) - (x.v as number))
    .slice(0, max)
    .map(({ f, v }) => words[f.key] ?? `${f.short.toLowerCase()} ${Math.round((v as number) * 100)}%`);
}
