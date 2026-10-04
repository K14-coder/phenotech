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
  { key: "mutation", label: "Mutation type", short: "Mutation", edge: "similar_mutation_spectrum", plain: "The kind of DNA change that causes it: a single-letter substitution, a deletion, a duplication, an insertion, an inversion, a translocation, a repeat expansion…", sources: "ClinVar pathogenic / likely pathogenic (variant type)" },
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
  /** molecular consequence counts (missense, frameshift, …) */
  c: Record<string, number> | null;
  /** DNA change type counts (ClinVar Type: snv, del, dup, ins, indel, inv, trans, cnv_loss, cnv_gain, str, …) */
  t?: Record<string, number> | null;
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

// ---------- DNA change types (ClinVar "Type") ----------

/** The kinds of DNA change, in display order: code, label, plural for sentences, colour. */
export const DNA_TYPES: { key: string; label: string; words: string; color: string }[] = [
  { key: "snv", label: "Substitution", words: "single-letter substitutions", color: "#1f5a96" },
  { key: "del", label: "Deletion", words: "deletions", color: "#b07a22" },
  { key: "dup", label: "Duplication", words: "duplications", color: "#d9a84e" },
  { key: "ins", label: "Insertion", words: "insertions", color: "#6f97c4" },
  { key: "indel", label: "Deletion-insertion", words: "deletion-insertions (indels)", color: "#7f520f" },
  { key: "inv", label: "Inversion", words: "inversions", color: "#8a5aa8" },
  { key: "trans", label: "Translocation", words: "translocations", color: "#a8436b" },
  { key: "cnv_loss", label: "Copy-number loss", words: "losses of whole exons or genes", color: "#5f6672" },
  { key: "cnv_gain", label: "Copy-number gain", words: "extra copies of exons or genes", color: "#8c939e" },
  { key: "str", label: "Repeat expansion", words: "repeat expansions or contractions", color: "#3d8a6b" },
  { key: "complex", label: "Complex", words: "complex rearrangements", color: "#a9733b" },
  { key: "fusion", label: "Gene fusion", words: "gene fusions", color: "#b0566e" },
  { key: "other", label: "Other", words: "other changes", color: "#c4c9d0" },
];
const MECHSIM_TYPE: Record<string, string> = {
  "single nucleotide substitution": "snv", deletion: "del", duplication: "dup", insertion: "ins",
  "insertion-deletion (indel)": "indel", inversion: "inv", translocation: "trans", "copy-number loss": "cnv_loss",
  "copy-number gain": "cnv_gain", "repeat expansion / contraction": "str", "complex rearrangement": "complex", other: "other",
};

/** Plain meaning of each kind of DNA change, for one variant. */
export const DNA_TYPE_PLAIN: Record<string, string> = {
  snv: "Substitution: one DNA letter is swapped for another.",
  del: "Deletion: one or more DNA letters are missing.",
  dup: "Duplication: a stretch of DNA is copied twice.",
  ins: "Insertion: extra DNA letters are added.",
  indel: "Deletion-insertion: some letters are removed and others put in their place.",
  inv: "Inversion: a stretch of DNA is flipped end to end.",
  trans: "Translocation: a piece of DNA has moved to another place in the genome.",
  cnv_loss: "Copy-number loss: whole exons or the whole gene are missing.",
  cnv_gain: "Copy-number gain: whole exons or the whole gene are present in extra copies.",
  str: "Repeat expansion: a short repeated stretch of DNA is longer (or shorter) than usual.",
  complex: "Complex rearrangement: several kinds of change together.",
  fusion: "Gene fusion: parts of two genes are joined.",
};

/** Kind of DNA change from an HGVS c. description (c.123A>G, c.12del, c.12dup, c.12_13insAT, c.12delinsAT, c.12_40inv). */
export function hgvsType(c: string | null | undefined): string | null {
  if (!c) return null;
  if (/delins/.test(c)) return "indel";
  if (/dup/.test(c)) return "dup";
  if (/inv/.test(c)) return "inv";
  if (/ins/.test(c)) return "ins";
  if (/del/.test(c)) return "del";
  if (/>/.test(c)) return "snv";
  return null;
}

/** Type counts keyed by DNA_TYPES codes (accepts gene-level codes or mechsim's labels). */
export function normTypes(t: Record<string, number> | null | undefined): Record<string, number> | null {
  if (!t) return null;
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(t)) {
    const code = DNA_TYPES.some((d) => d.key === k) ? k : (MECHSIM_TYPE[k] ?? "other");
    out[code] = (out[code] ?? 0) + v;
  }
  return Object.keys(out).length ? out : null;
}

/** The leading DNA change types with their share, most common first. */
export function topTypes(t: Record<string, number> | null | undefined, max = 2): { key: string; words: string; label: string; pct: number }[] {
  const n = normTypes(t);
  if (!n) return [];
  const total = Object.values(n).reduce((a, b) => a + b, 0);
  return Object.entries(n)
    .sort((a, b) => b[1] - a[1])
    .slice(0, max)
    .map(([k, v]) => {
      const d = DNA_TYPES.find((x) => x.key === k)!;
      return { key: k, words: d.words, label: d.label, pct: Math.round((100 * v) / total) };
    });
}

/** "single-letter substitutions (70%) and deletions (18%)" */
export function typeSentence(t: Record<string, number> | null | undefined): string | null {
  const top = topTypes(t, 2);
  return top.length ? top.map((x) => `${x.words} (${x.pct}%)`).join(" and ") : null;
}

export const sumTypes = (fs: GeneFeature[]) => {
  const out: Record<string, number> = {};
  let any = false;
  for (const f of fs)
    for (const [k, v] of Object.entries(f.t ?? {})) {
      out[k] = (out[k] ?? 0) + v;
      any = true;
    }
  return any ? out : null;
};

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
    // by DNA change type, as mechsim's mutation axis; the consequence spectrum only when types are missing
    mutation: spectrumSim(sumTypes(fa), sumTypes(fb)) ?? spectrumSim(sumSpectra(fa), sumSpectra(fb)),
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
