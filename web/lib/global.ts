// Global rare-disease index: every rare disease with HPO annotations or a gene association, not only
// the families the atlas maps in depth. Basic data only (computed phenotype similarity and links out);
// nothing here is a curated claim, so it is never drawn as graph edges or given a confidence score.
// Schema, bucketing and search recipe: data/derived/global/README.md.
//
// Files (synced to public/data/derived/global by scripts/sync-data.mjs, all lazy):
//   index.json           11k rows; loaded on the first search focus or keystroke (or when idle on Home)
//   meta.json            caveat, far text, URL templates; loaded by global disease pages
//   neighbours/<b>.json  one shard per disease page, b = djb2(id) % 64
// Per-disease mechanism / pathway / cluster shards will use the same bucketing: add their folder to
// GlobalShardKind and read them with loadShard().
import { diseaseHref } from "./graph";
import { ensure } from "./resource";

export const GLOBAL_BASE = "/data/derived/global";
export const GLOBAL_BUCKETS = 64;

export interface GlobalRow {
  /** MONDO id, or a native OMIM:/ORPHA: id when MONDO has no match */
  id: string;
  name: string;
  /** up to 4 exact synonyms, abbreviations first */
  syn: string[];
  omim: string[];
  orpha: string[];
  genes: string[];
  /** 1 = OMIM Mendelian genes, 2 = Orphanet genes only (may include modifiers), 3 = DisMech curated genes, 0 = none */
  gsrc: number;
  /** distinct annotated HPO phenotype terms (< 5: no neighbours) */
  n: number;
  /** "disease:<GENE>" when this is one of the diseases the atlas maps in depth */
  atlas: string | null;
}

export type GlobalMatchKind = "name" | "synonym" | "gene" | "id";

export interface GlobalHit {
  row: GlobalRow;
  /** the text that matched, as written in the data */
  matched: string;
  kind: GlobalMatchKind;
  /** 0 exact name/synonym, 1 exact gene or id, 2 prefix, 3 word prefix */
  rank: number;
}

interface SearchKey {
  t: string;
  /** " " + t, for word-prefix matching */
  sp: string;
  raw: string;
  kind: GlobalMatchKind;
}

export interface GlobalIndex {
  rows: GlobalRow[];
  byId: Map<string, GlobalRow>;
  /** parallel to rows */
  keys: SearchKey[][];
}

// ---------- ids, hashing, links ----------

/** djb2 (seed 5381, h = h * 33 + charCode, unsigned 32-bit after every character), as in the README. */
export function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 33) + s.charCodeAt(i)) >>> 0;
  return h;
}

export function bucketOf(id: string): number {
  return djb2(id) % GLOBAL_BUCKETS;
}

export function isGlobalId(s: string | null | undefined): s is string {
  return !!s && /^(MONDO|OMIM|ORPHA):[A-Za-z0-9_.-]+$/.test(s);
}

/** /d/MONDO:0007739 (the colon is legal in a path segment and reads better than %3A) */
export function globalHref(id: string): string {
  return `/d/${encodeURIComponent(id).replace(/%3A/gi, ":")}`;
}

export function globalIdFromParam(param: string): string {
  try {
    return decodeURIComponent(param).trim();
  } catch {
    return param.trim();
  }
}

type LoadedGraph = { nodeById: Map<string, unknown> } | null | undefined;

/**
 * The atlas disease a row maps to, if the loaded graph has it. The index's atlas flag is rewritten
 * when family files land, which can be before the graph is rebuilt: until then the row stays basic.
 */
export function mappedAtlasId(row: GlobalRow, idx: LoadedGraph): string | null {
  return row.atlas && idx?.nodeById.has(row.atlas) ? row.atlas : null;
}

/** Mapped diseases keep their atlas action page; everything else gets the basic-data page. */
export function rowHref(row: GlobalRow, idx: LoadedGraph): string {
  const atlasId = mappedAtlasId(row, idx);
  return atlasId ? diseaseHref(atlasId) : globalHref(row.id);
}

// ---------- search (README recipe) ----------

/** Lowercase, fold accents, delete apostrophes ("Huntington's" -> "huntingtons"), other runs of non-alphanumerics -> one space. */
export function normalizeTerm(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function parseIndex(raw: { f: string[]; rows: unknown[][] }): GlobalIndex {
  const col = (k: string) => raw.f.indexOf(k);
  const I = {
    id: col("id"),
    name: col("name"),
    syn: col("syn"),
    omim: col("omim"),
    orpha: col("orpha"),
    genes: col("genes"),
    gsrc: col("gsrc"),
    n: col("n"),
    atlas: col("atlas"),
  };
  const list = (v: unknown) =>
    typeof v === "string" && v
      ? v
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
  const rows: GlobalRow[] = [];
  const keys: SearchKey[][] = [];
  for (const r of raw.rows) {
    const id = typeof r[I.id] === "string" ? (r[I.id] as string) : "";
    const name = typeof r[I.name] === "string" ? (r[I.name] as string) : "";
    if (!id || !name) continue;
    const syn = Array.isArray(r[I.syn]) ? (r[I.syn] as unknown[]).filter((s): s is string => typeof s === "string" && !!s) : [];
    const atlas = typeof r[I.atlas] === "string" && r[I.atlas] ? (r[I.atlas] as string) : null;
    const row: GlobalRow = {
      id,
      name,
      syn,
      omim: list(r[I.omim]),
      orpha: list(r[I.orpha]),
      genes: list(r[I.genes]),
      gsrc: Number(r[I.gsrc]) || 0,
      n: Number(r[I.n]) || 0,
      atlas,
    };
    const k: SearchKey[] = [];
    const add = (text: string, kind: GlobalMatchKind) => {
      const t = normalizeTerm(text);
      if (t && !k.some((x) => x.t === t)) k.push({ t, sp: ` ${t}`, raw: text, kind });
    };
    add(name, "name");
    for (const s of syn) add(s, "synonym");
    for (const g of row.genes) add(g, "gene");
    for (const o of row.omim) {
      add(o, "id");
      add(`OMIM:${o}`, "id");
    }
    for (const o of row.orpha) {
      add(o, "id");
      add(`ORPHA:${o}`, "id");
    }
    add(id, "id");
    rows.push(row);
    keys.push(k);
  }
  return { rows, keys, byId: new Map(rows.map((r) => [r.id, r])) };
}

const words = (t: string) => t.split(" ").length;

/**
 * README order: exact, then gene/id, then prefix, then word prefix. Within prefix and word-prefix
 * matches a whole-word match ranks above a partial one ("sma" -> "SMA type 1" before "SMARCA2"), and
 * the label with fewer extra words wins ("rett" -> Rett syndrome before "Rett syndrome, congenital
 * variant"). Remaining ties go to the better-annotated disease (higher n).
 */
export function searchGlobal(gi: GlobalIndex, query: string, limit = 8): GlobalHit[] {
  const q = normalizeTerm(query);
  if (q.length < 2) return [];
  const sq = ` ${q}`;
  const qWords = words(q);
  const hits: (GlobalHit & { extra: number })[] = [];
  for (let i = 0; i < gi.rows.length; i++) {
    let best: SearchKey | null = null;
    let bestRank = 9;
    for (const k of gi.keys[i]) {
      let r = 9;
      if (k.kind === "gene" || k.kind === "id") {
        if (k.t === q) r = 1;
      } else if (k.t === q) r = 0;
      else if (k.t.startsWith(q)) r = k.t[q.length] === " " ? 2 : 3;
      else {
        const at = k.sp.indexOf(sq);
        if (at >= 0) r = k.sp.length === at + sq.length || k.sp[at + sq.length] === " " ? 4 : 5;
      }
      const better =
        r < bestRank ||
        (r === bestRank && r < 9 && best && (words(k.t) < words(best.t) || (words(k.t) === words(best.t) && k.kind === "name" && best.kind !== "name")));
      if (better) {
        best = k;
        bestRank = r;
      }
    }
    if (best) hits.push({ row: gi.rows[i], matched: best.raw, kind: best.kind, rank: bestRank, extra: words(best.t) - qWords });
  }
  hits.sort((a, b) => a.rank - b.rank || a.extra - b.extra || b.row.n - a.row.n || a.row.name.length - b.row.name.length);
  return hits.slice(0, limit).map(({ row, matched, kind, rank }) => ({ row, matched, kind, rank }));
}

// ---------- loading ----------

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
  return (await r.json()) as T;
}

export const GLOBAL_INDEX_KEY = "global:index";
export const GLOBAL_META_KEY = "global:meta";

type RawIndex = { f: string[]; rows: unknown[][] };

/** index.json plus index_extra.json (same schema: DisMech disorders whose MONDO id index.json lacks). */
export const loadGlobalIndex = async (): Promise<GlobalIndex> => {
  const [main, extra] = await Promise.all([
    fetchJson<RawIndex>(`${GLOBAL_BASE}/index.json`),
    fetchJson<RawIndex>(`${GLOBAL_BASE}/index_extra.json`).catch(() => null),
  ]);
  const gi = parseIndex(main);
  if (extra?.f && Array.isArray(extra.rows)) {
    const more = parseIndex(extra);
    more.rows.forEach((r, i) => {
      if (gi.byId.has(r.id)) return;
      gi.rows.push(r);
      gi.keys.push(more.keys[i]);
      gi.byId.set(r.id, r);
    });
  }
  return gi;
};

/** Starts the one-time index download (search focus, first keystroke, idle prefetch). */
export function ensureGlobalIndex() {
  return ensure(GLOBAL_INDEX_KEY, loadGlobalIndex);
}

export interface GlobalMeta {
  caveat: string;
  far_text: string;
  url_templates: Record<string, string>;
  method?: { distinctive_ic?: number };
  counts?: { index_entries?: number; with_neighbours?: number };
}

export const loadGlobalMeta = () => fetchJson<GlobalMeta>(`${GLOBAL_BASE}/meta.json`);

/** Shard folders under data/derived/global, all bucketed by djb2(id) % 64. */
export type GlobalShardKind = "neighbours" | "similar";

export function shardKey(kind: GlobalShardKind, id: string) {
  return `global:${kind}:${bucketOf(id)}`;
}

export function loadShard<T>(kind: GlobalShardKind, id: string): Promise<T> {
  return fetchJson<T>(`${GLOBAL_BASE}/${kind}/${bucketOf(id)}.json`);
}

/** [neighbour id, IC-weighted cosine 0–1, percentile in the comparison pool, up to 3 shared HPO ids] */
export type NeighbourTuple = [string, number, number, string[]];
/** [atlas disease id, cosine, percentile, near (>= calibrated threshold), shared HPO ids] */
export type AtlasTuple = [string, number, number, boolean, string[]];

export interface NeighbourEntry {
  nb: NeighbourTuple[];
  own: string[];
  inh: string[];
  atlas: AtlasTuple[];
  far: boolean;
}

/** similar/<bucket>.json (production scorer: symptoms + 0.5 same gene + 0.5 shared pathways), see data/derived/global/README.md */
export type SimilarTuple = [string, number, number, number, number, string[], string[], string[]];
export interface SimilarShard {
  bucket: number;
  f: string[];
  t: Record<string, [string, number]>;
  p: Record<string, string>;
  d: Record<string, SimilarTuple[]>;
}

export interface NeighbourShard {
  bucket: number;
  /** shard-local HPO dictionary: id -> [label, information content] */
  t: Record<string, [string, number]>;
  d: Record<string, NeighbourEntry>;
}

/** Fills a URL template from meta.url_templates ({omim}, {orpha}, {mondo}, {name_urlencoded}, {hpo}). */
export function fillTemplate(tpl: string, vars: Record<string, string>): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k: string) => vars[k] ?? "");
}

// ---------- "did you mean" (when nothing matched) ----------

function trigrams(t: string): Set<string> {
  const s = `  ${t} `;
  const out = new Set<string>();
  for (let i = 0; i + 3 <= s.length; i++) out.add(s.slice(i, i + 3));
  return out;
}

/** Closest names by trigram similarity (Dice), for misspellings like "huntingdon" or "duchene". */
export function suggestGlobal(gi: GlobalIndex, query: string, limit = 4): { row: GlobalRow; matched: string; score: number }[] {
  const q = normalizeTerm(query);
  if (q.length < 3) return [];
  const qt = trigrams(q);
  const best: { row: GlobalRow; matched: string; score: number }[] = [];
  for (let i = 0; i < gi.rows.length; i++) {
    let top = 0;
    let matched = "";
    for (const k of gi.keys[i]) {
      if (k.kind === "id") continue;
      // compare against the same number of leading words, so long names are not penalised
      const t = k.t.split(" ").slice(0, Math.max(1, q.split(" ").length)).join(" ");
      if (Math.abs(t.length - q.length) > Math.max(4, q.length)) continue;
      const tt = trigrams(t);
      let inter = 0;
      for (const g of qt) if (tt.has(g)) inter++;
      const dice = (2 * inter) / (qt.size + tt.size);
      if (dice > top) {
        top = dice;
        matched = k.raw;
      }
    }
    if (top >= (q.includes(" ") ? 0.6 : 0.45)) best.push({ row: gi.rows[i], matched, score: top + gi.rows[i].n / 10000 });
  }
  best.sort((a, b) => b.score - a.score);
  const seen = new Set<string>();
  return best.filter((b) => !seen.has(b.row.id) && (seen.add(b.row.id), true)).slice(0, limit);
}
