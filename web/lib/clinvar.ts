"use client";

// Full ClinVar P/LP (data/derived/ingest/clinvar/<djb2(gene)%64>.json, 387,722 variants in 13,292 genes),
// loaded one shard at a time, plus web/clinvar_genes.json: per assembly and chromosome, the span of each
// gene's exact ClinVar keys, so a VCF line can find its gene (and shard) from its position alone.
import { loadAvailableOnce } from "./population";
import type { Assembly } from "./sequence";
import { normalizeC, normalizeP } from "./variant";

export interface ClinvarHit {
  vid: number;
  gene: string;
  /** ClinVar's own name, e.g. NM_007194.4(CHEK2):c.1100del (p.Thr367fs) */
  name: string;
  hgvs: string;
  protein: string;
  type: string;
  consequence: string;
  cls: "P" | "LP" | "PLP";
  stars: number;
  url: string;
}

interface Shard {
  bucket: number;
  f: string[];
  g: Record<string, { tx: string[]; ph: string[]; v: unknown[][] }>;
}
type Spans = Record<Assembly, Record<string, [number, number, string][]>>;

const ROOT = "/data/derived/ingest/clinvar";

export function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 33) + s.charCodeAt(i)) >>> 0;
  return h;
}
export const bucketOfGene = (gene: string) => djb2(gene) % 64;

export const CLS_PLAIN: Record<string, string> = { P: "Pathogenic", LP: "Likely pathogenic", PLP: "Pathogenic / likely pathogenic" };

let spansP: Promise<(Spans & { maxEnd: Record<Assembly, Record<string, number[]>> }) | null> | null = null;
export function loadGeneSpans() {
  spansP ??= (async () => {
    const a = await loadAvailableOnce();
    if (!a.clinvar_full) return null;
    const r = await fetch("/data/derived/web/clinvar_genes.json");
    if (!r.ok) return null;
    const s = (await r.json()) as Spans;
    // running maximum of span ends, so a backwards scan can stop as soon as no earlier span can reach pos
    const maxEnd = { GRCh38: {}, GRCh37: {} } as Record<Assembly, Record<string, number[]>>;
    for (const asm of ["GRCh38", "GRCh37"] as Assembly[])
      for (const [c, list] of Object.entries(s[asm] ?? {})) {
        let m = 0;
        maxEnd[asm][c] = list.map((x) => (m = Math.max(m, x[1])));
      }
    return { ...s, maxEnd };
  })().catch(() => null);
  return spansP;
}

/** Genes whose ClinVar span covers chrom:pos on this assembly. */
export function genesAt(spans: Awaited<ReturnType<typeof loadGeneSpans>>, asm: Assembly, chrom: string, pos: number): string[] {
  const list = spans?.[asm]?.[chrom.replace(/^chr/i, "")];
  const me = spans?.maxEnd[asm]?.[chrom.replace(/^chr/i, "")];
  if (!list || !me) return [];
  let lo = 0;
  let hi = list.length - 1;
  let i = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid][0] <= pos) {
      i = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  const out: string[] = [];
  for (; i >= 0 && me[i] >= pos; i--) if (list[i][1] >= pos) out.push(list[i][2]);
  return out;
}

const shardCache = new Map<number, Promise<Shard | null>>();
export function loadShard(bucket: number): Promise<Shard | null> {
  let p = shardCache.get(bucket);
  if (!p) {
    p = fetch(`${ROOT}/${bucket}.json`)
      .then((r) => (r.ok ? (r.json() as Promise<Shard>) : null))
      .catch(() => null);
    shardCache.set(bucket, p);
  }
  return p;
}

function toHit(shard: Shard, gene: string, row: unknown[]): ClinvarHit {
  const F = Object.fromEntries(shard.f.map((k, i) => [k, i]));
  const g = shard.g[gene];
  const tx = g.tx[row[F.tx] as number] ?? "";
  const hgvs = String(row[F.hgvs] ?? "");
  const protein = String(row[F.protein] ?? "");
  const vid = Number(row[F.vid]);
  return {
    vid,
    gene,
    hgvs,
    protein,
    name: `${tx ? `${tx}(${gene}):` : ""}${hgvs}${protein ? ` (${protein})` : ""}`,
    type: String(row[F.type] ?? ""),
    consequence: String(row[F.consequence] ?? ""),
    cls: row[F.class] as ClinvarHit["cls"],
    stars: Number(row[F.stars] ?? 0),
    url: `https://www.ncbi.nlm.nih.gov/clinvar/variation/${vid}/`,
  };
}

/** Exact chr:pos:ref:alt match in a gene's shard (keys are VCF-style, 1-based, with the anchor base). */
export async function lookupKey(gene: string, asm: Assembly, chrom: string, pos: number, ref: string, alt: string): Promise<ClinvarHit | null> {
  const shard = await loadShard(bucketOfGene(gene));
  const g = shard?.g[gene];
  if (!shard || !g) return null;
  const col = shard.f.indexOf(asm === "GRCh37" ? "grch37" : "grch38");
  const key = `${chrom.replace(/^chr/i, "")}:${pos}:${ref.toUpperCase()}:${alt.toUpperCase()}`;
  const row = g.v.find((v) => v[col] === key);
  return row ? toHit(shard, gene, row) : null;
}

/** Build a key -> hit map for one gene (fast repeated lookups for whole-exome files). */
export async function keyMap(gene: string, asm: Assembly): Promise<Map<string, ClinvarHit>> {
  const shard = await loadShard(bucketOfGene(gene));
  const out = new Map<string, ClinvarHit>();
  const g = shard?.g[gene];
  if (!shard || !g) return out;
  const col = shard.f.indexOf(asm === "GRCh37" ? "grch37" : "grch38");
  for (const v of g.v) if (v[col]) out.set(String(v[col]), toHit(shard, gene, v));
  return out;
}

/** "c.1100delC" and "c.1100del" are the same deletion: drop the bases after del/dup for comparison. */
const normC = (c: string) => (normalizeC(c) ?? c).replace(/(del|dup)[ACGTN]+$/i, "$1");

/** Report-line fallback for genes outside the atlas: match a c. or p. change in the gene's shard. */
export async function lookupHgvs(gene: string, c: string | null, p: string | null): Promise<{ hits: ClinvarHit[]; on: "c" | "p" | null; geneKnown: boolean }> {
  const shard = await loadShard(bucketOfGene(gene));
  const g = shard?.g[gene];
  if (!shard || !g) return { hits: [], on: null, geneKnown: false };
  const F = Object.fromEntries(shard.f.map((k, i) => [k, i]));
  if (c) {
    const want = normC(c);
    const rows = g.v.filter((v) => normC(String(v[F.hgvs])) === want);
    if (rows.length) return { hits: rows.map((r) => toHit(shard, gene, r)), on: "c", geneKnown: true };
  }
  if (p) {
    // p is normalised by lib/variant normalizeP (one-letter code); ClinVar's three-letter form is normalised the same way
    const rows = g.v.filter((v) => {
      const pr = String(v[F.protein] ?? "");
      return !!pr && normalizeP(pr) === p;
    });
    if (rows.length) return { hits: rows.map((r) => toHit(shard, gene, r)), on: "p", geneKnown: true };
  }
  return { hits: [], on: null, geneKnown: true };
}
