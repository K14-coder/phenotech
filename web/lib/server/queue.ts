// Crowd research queue: volunteers each use their own OpenAI access to research diseases in parallel.
// See docs/agent-reports/research-queue.md.
//
//  - The queue is a sorted set of disease ids (lower score = earlier). Untouched diseases carry their
//    seed rank (0..N-1); an incomplete disease that comes back carries REQUEUE_BASE + time, so it sits
//    ahead of every untouched disease, oldest first.
//  - A claim is ZPOPMIN (atomic: two volunteers can never pop the same member) followed by
//    SET rq:lease:<id> NX (a second guard). The lease lasts LEASE_SECONDS (7 h).
//  - Expired leases are finalised lazily on every claim (and by /api/queue/sweep for cron): coverage is
//    recomputed from the accepted claims; complete diseases leave the queue, incomplete ones go back to
//    the top with their gaps listed, and after MAX_ROUNDS worked rounds a disease retires with its gaps.
//  - The server never trusts the client: every quote must be a verbatim sentence of the abstract the
//    server fetched from PubMed for this packet, the PMID must be in the packet, the schema must hold.
//
// Storage: Upstash Redis over REST on Vercel (same env vars as store.ts), else a JSON file in
// web/.data/queue.json guarded by a cross-process lock file (local development only).
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { mkdir, open, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import seedJson from "@/app/api/queue/_data/seed.json";
import { HttpError, assertSameOrigin, currentUser } from "./community";
import { getJson, storeMode } from "./store";

// ---------- configuration ----------

export const LEASE_SECONDS = 7 * 3600;
const LEASE_GRACE_SECONDS = 2 * 86400; // lease records outlive the lease so the sweeper still finds them
export const MAX_ROUNDS = Math.max(1, Number(process.env.QUEUE_MAX_ROUNDS) || 3);
const REQUEUE_BASE = -1e13;
const MAX_ABSTRACTS = 15;
const MAX_CLAIMS_PER_SUBMIT = 60;
const MAX_GROUPS_PER_SUBMIT = 30;
const CLAIMS_PER_HOUR = 20;
const SUBMITS_PER_HOUR = 120;
export const STATUS_LABEL = "community-researched, AI-extracted, quote-verified, unreviewed";
const NCBI_TOOL = "rare-disease-atlas";

// ---------- seed ----------

interface SeedFile {
  meta: { generated: string; n: number; weights: Record<string, number> };
  f: string[];
  clusters: Record<string, string>;
  rows: SeedTuple[];
}
type SeedTuple = [
  string, // id
  string, // name
  string[], // syn
  string[], // genes
  string[], // omim
  string[], // orpha
  number, // n HPO terms
  string[], // curated mechanism classes
  string | null, // cluster id
  number, // DisMech record (0/1)
  [number, number, number], // trials: by name, by gene, active (by name)
  number, // patient organisations
  number, // registries
  number, // prevalence record (0/1)
  string[], // mechanism neighbour of these deep diseases
  number, // score
];

export interface SeedDisease {
  id: string;
  name: string;
  synonyms: string[];
  genes: string[];
  omim: string[];
  orpha: string[];
  nHpo: number;
  mechanismClasses: string[];
  cluster: string | null;
  dismech: boolean;
  trials: { byName: number; byGene: number; active: number };
  orgs: number;
  registries: number;
  prevalence: boolean;
  neighbourOf: string[];
  score: number;
  rank: number;
}

const SEED = seedJson as unknown as SeedFile;
const SEED_VERSION = `${SEED.meta.generated}:${SEED.meta.n}`;
let seedIndex: Map<string, SeedDisease> | null = null;

function rowOf(t: SeedTuple, rank: number): SeedDisease {
  return {
    id: t[0],
    name: t[1],
    synonyms: t[2],
    genes: t[3],
    omim: t[4],
    orpha: t[5],
    nHpo: t[6],
    mechanismClasses: t[7],
    cluster: t[8] ? `${t[8]}${SEED.clusters[t[8]] ? ` · ${SEED.clusters[t[8]]}` : ""}` : null,
    dismech: !!t[9],
    trials: { byName: t[10][0], byGene: t[10][1], active: t[10][2] },
    orgs: t[11],
    registries: t[12],
    prevalence: !!t[13],
    neighbourOf: t[14],
    score: t[15],
    rank,
  };
}

export function seedDisease(id: string): SeedDisease | undefined {
  if (!seedIndex) seedIndex = new Map(SEED.rows.map((t, i) => [t[0], rowOf(t, i)]));
  return seedIndex.get(id);
}

/** Why a disease is where it is in the queue, in plain words. */
export function whyText(d: SeedDisease): string[] {
  const why: string[] = [];
  if (d.trials.byName) why.push(`${d.trials.byName} trial${d.trials.byName === 1 ? "" : "s"} name it`);
  else if (d.trials.byGene) why.push(`trials mention ${d.genes[0]}`);
  if (d.orgs) why.push(`${d.orgs} patient group${d.orgs === 1 ? "" : "s"}`);
  if (d.registries) why.push("registry");
  if (d.prevalence) why.push("prevalence known");
  if (!d.dismech) why.push("no curated mechanism chain yet");
  if (d.neighbourOf.length) why.push(`mechanism neighbour of ${d.neighbourOf.slice(0, 2).map((x) => x.replace("disease:", "")).join(", ")}`);
  return why;
}

// ---------- storage backend ----------

interface Z {
  member: string;
  score: number;
}
interface Backend {
  get(k: string): Promise<string | null>;
  mget(ks: string[]): Promise<(string | null)[]>;
  set(k: string, v: string, o?: { ex?: number; nx?: boolean }): Promise<boolean>;
  del(...ks: string[]): Promise<void>;
  zadd(k: string, items: Z[], nx?: boolean): Promise<number>;
  zpopmin(k: string): Promise<Z | null>;
  zrem(k: string, m: string): Promise<number>;
  zscore(k: string, m: string): Promise<number | null>;
  zrangeByScore(k: string, max: number, limit: number): Promise<Z[]>;
  zrange(k: string, start: number, stop: number): Promise<Z[]>;
  zrevrange(k: string, start: number, stop: number): Promise<Z[]>;
  zcard(k: string): Promise<number>;
  zincrby(k: string, inc: number, m: string): Promise<number>;
  sadd(k: string, ...ms: string[]): Promise<number>;
  srem(k: string, m: string): Promise<void>;
  smembers(k: string): Promise<string[]>;
  scard(k: string): Promise<number>;
  rpush(k: string, ...vs: string[]): Promise<number>;
  lrange(k: string, start: number, stop: number): Promise<string[]>;
  hincrby(k: string, f: string, n: number): Promise<number>;
  hgetall(k: string): Promise<Record<string, number>>;
  incrWindow(k: string, seconds: number): Promise<number>;
}

const REDIS_URL = process.env.UPSTASH_REDIS_REST_URL ?? process.env.KV_REST_API_URL;
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN ?? process.env.KV_REST_API_TOKEN;

async function rcall<T = unknown>(...cmd: (string | number)[]): Promise<T> {
  const r = await fetch(REDIS_URL!, {
    method: "POST",
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(cmd.map(String)),
    cache: "no-store",
  });
  const j = (await r.json()) as { result?: T; error?: string };
  if (!r.ok || j.error) throw new Error(`queue store: ${j.error ?? r.status}`);
  return j.result as T;
}

const pairs = (flat: unknown): Z[] => {
  const a = Array.isArray(flat) ? (flat as string[]) : [];
  const out: Z[] = [];
  for (let i = 0; i + 1 < a.length; i += 2) out.push({ member: String(a[i]), score: Number(a[i + 1]) });
  return out;
};

const redisBackend: Backend = {
  get: (k) => rcall<string | null>("GET", k),
  mget: async (ks) => (ks.length ? ((await rcall<(string | null)[]>("MGET", ...ks)) ?? []) : []),
  set: async (k, v, o) => {
    const args: (string | number)[] = ["SET", k, v];
    if (o?.ex) args.push("EX", Math.ceil(o.ex));
    if (o?.nx) args.push("NX");
    return (await rcall<string | null>(...args)) === "OK";
  },
  del: async (...ks) => {
    if (ks.length) await rcall("DEL", ...ks);
  },
  zadd: async (k, items, nx) => {
    if (!items.length) return 0;
    const args: (string | number)[] = ["ZADD", k];
    if (nx) args.push("NX");
    for (const z of items) args.push(z.score, z.member);
    return Number(await rcall(...args));
  },
  zpopmin: async (k) => pairs(await rcall("ZPOPMIN", k, 1))[0] ?? null,
  zrem: async (k, m) => Number(await rcall("ZREM", k, m)),
  zscore: async (k, m) => {
    const v = await rcall<string | null>("ZSCORE", k, m);
    return v === null || v === undefined ? null : Number(v);
  },
  zrangeByScore: async (k, max, limit) => pairs(await rcall("ZRANGEBYSCORE", k, "-inf", max, "WITHSCORES", "LIMIT", 0, limit)),
  zrange: async (k, a, b) => pairs(await rcall("ZRANGE", k, a, b, "WITHSCORES")),
  zrevrange: async (k, a, b) => pairs(await rcall("ZREVRANGE", k, a, b, "WITHSCORES")),
  zcard: async (k) => Number(await rcall("ZCARD", k)),
  zincrby: async (k, inc, m) => Number(await rcall("ZINCRBY", k, inc, m)),
  sadd: async (k, ...ms) => (ms.length ? Number(await rcall("SADD", k, ...ms)) : 0),
  srem: async (k, m) => {
    await rcall("SREM", k, m);
  },
  smembers: async (k) => (await rcall<string[]>("SMEMBERS", k)) ?? [],
  scard: async (k) => Number(await rcall("SCARD", k)),
  rpush: async (k, ...vs) => (vs.length ? Number(await rcall("RPUSH", k, ...vs)) : 0),
  lrange: async (k, a, b) => (await rcall<string[]>("LRANGE", k, a, b)) ?? [],
  hincrby: async (k, f, n) => Number(await rcall("HINCRBY", k, f, n)),
  hgetall: async (k) => {
    const v = await rcall<unknown>("HGETALL", k);
    const out: Record<string, number> = {};
    if (Array.isArray(v)) for (let i = 0; i + 1 < v.length; i += 2) out[String(v[i])] = Number(v[i + 1]);
    else if (v && typeof v === "object") for (const [f, n] of Object.entries(v)) out[f] = Number(n);
    return out;
  },
  incrWindow: async (k, seconds) => {
    const n = Number(await rcall("INCR", k));
    if (n === 1) await rcall("EXPIRE", k, seconds);
    return n;
  },
};

// JSON file with a cross-process lock (O_EXCL lock file) plus an in-process queue.
interface FileDb {
  kv: Record<string, { v: string; exp?: number }>;
  z: Record<string, Record<string, number>>;
  s: Record<string, string[]>;
  l: Record<string, string[]>;
  h: Record<string, Record<string, number>>;
}
const QFILE = path.join(process.cwd(), ".data", "queue.json");
const QLOCK = `${QFILE}.lock`;
let fileChain: Promise<unknown> = Promise.resolve();
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function acquireLock() {
  await mkdir(path.dirname(QFILE), { recursive: true });
  const started = Date.now();
  for (;;) {
    try {
      const h = await open(QLOCK, "wx");
      await h.writeFile(String(process.pid));
      await h.close();
      return;
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "EEXIST") throw e;
      const info = await stat(QLOCK).catch(() => null);
      if (info && Date.now() - info.mtimeMs > 10_000) await rm(QLOCK, { force: true });
      else if (Date.now() - started > 15_000) throw new Error("queue file is locked");
      else await sleep(5 + Math.random() * 20);
    }
  }
}

function tx<T>(fn: (db: FileDb) => T, write: boolean): Promise<T> {
  const run = fileChain.then(async () => {
    await acquireLock();
    try {
      let db: FileDb;
      try {
        db = JSON.parse(await readFile(QFILE, "utf8")) as FileDb;
      } catch {
        db = { kv: {}, z: {}, s: {}, l: {}, h: {} };
      }
      const out = fn(db);
      if (write) {
        const tmp = `${QFILE}.${process.pid}.tmp`;
        await writeFile(tmp, JSON.stringify(db));
        await rename(tmp, QFILE);
      }
      return out;
    } finally {
      await rm(QLOCK, { force: true });
    }
  });
  fileChain = run.catch(() => undefined);
  return run;
}

const liveKv = (db: FileDb, k: string) => {
  const e = db.kv[k];
  if (!e) return null;
  if (e.exp && e.exp <= Date.now()) {
    delete db.kv[k];
    return null;
  }
  return e.v;
};
const sortedZ = (zs: Record<string, number> | undefined): Z[] =>
  Object.entries(zs ?? {})
    .map(([member, score]) => ({ member, score }))
    .sort((a, b) => a.score - b.score || (a.member < b.member ? -1 : a.member > b.member ? 1 : 0));
const slice = <T>(a: T[], start: number, stop: number) => a.slice(start, stop < 0 ? a.length + stop + 1 : stop + 1);

const fileBackend: Backend = {
  get: (k) => tx((db) => liveKv(db, k), false),
  mget: (ks) => tx((db) => ks.map((k) => liveKv(db, k)), false),
  set: (k, v, o) =>
    tx((db) => {
      if (o?.nx && liveKv(db, k) !== null) return false;
      db.kv[k] = o?.ex ? { v, exp: Date.now() + o.ex * 1000 } : { v };
      return true;
    }, true),
  del: (...ks) =>
    tx((db) => {
      for (const k of ks) {
        delete db.kv[k];
        delete db.z[k];
        delete db.s[k];
        delete db.l[k];
        delete db.h[k];
      }
    }, true),
  zadd: (k, items, nx) =>
    tx((db) => {
      const z = (db.z[k] ??= {});
      let added = 0;
      for (const it of items) {
        if (it.member in z) {
          if (!nx) z[it.member] = it.score;
        } else {
          z[it.member] = it.score;
          added++;
        }
      }
      return added;
    }, true),
  zpopmin: (k) =>
    tx((db) => {
      const first = sortedZ(db.z[k])[0];
      if (!first) return null;
      delete db.z[k][first.member];
      return first;
    }, true),
  zrem: (k, m) =>
    tx((db) => {
      if (!db.z[k] || !(m in db.z[k])) return 0;
      delete db.z[k][m];
      return 1;
    }, true),
  zscore: (k, m) => tx((db) => db.z[k]?.[m] ?? null, false),
  zrangeByScore: (k, max, limit) => tx((db) => sortedZ(db.z[k]).filter((x) => x.score <= max).slice(0, limit), false),
  zrange: (k, a, b) => tx((db) => slice(sortedZ(db.z[k]), a, b), false),
  zrevrange: (k, a, b) => tx((db) => slice(sortedZ(db.z[k]).reverse(), a, b), false),
  zcard: (k) => tx((db) => Object.keys(db.z[k] ?? {}).length, false),
  zincrby: (k, inc, m) =>
    tx((db) => {
      const z = (db.z[k] ??= {});
      z[m] = (z[m] ?? 0) + inc;
      return z[m];
    }, true),
  sadd: (k, ...ms) =>
    tx((db) => {
      const s = new Set(db.s[k] ?? []);
      const before = s.size;
      for (const m of ms) s.add(m);
      db.s[k] = [...s];
      return s.size - before;
    }, true),
  srem: (k, m) =>
    tx((db) => {
      db.s[k] = (db.s[k] ?? []).filter((x) => x !== m);
    }, true),
  smembers: (k) => tx((db) => [...(db.s[k] ?? [])], false),
  scard: (k) => tx((db) => (db.s[k] ?? []).length, false),
  rpush: (k, ...vs) =>
    tx((db) => {
      const l = (db.l[k] ??= []);
      l.push(...vs);
      return l.length;
    }, true),
  lrange: (k, a, b) => tx((db) => slice(db.l[k] ?? [], a, b), false),
  hincrby: (k, f, n) =>
    tx((db) => {
      const h = (db.h[k] ??= {});
      h[f] = (h[f] ?? 0) + n;
      return h[f];
    }, true),
  hgetall: (k) => tx((db) => ({ ...(db.h[k] ?? {}) }), false),
  incrWindow: (k, seconds) =>
    tx((db) => {
      const cur = liveKv(db, k);
      const n = (cur ? Number(cur) : 0) + 1;
      db.kv[k] = { v: String(n), exp: db.kv[k]?.exp ?? Date.now() + seconds * 1000 };
      return n;
    }, true),
};

function kv(): Backend {
  const mode = storeMode();
  if (mode === "off") throw new HttpError(503, "The research queue opens soon (no database configured).");
  if (mode === "redis" && !(REDIS_URL && REDIS_TOKEN)) throw new HttpError(503, "The research queue opens soon.");
  return mode === "redis" ? redisBackend : fileBackend;
}

const K = {
  avail: "rq:avail",
  leases: "rq:leases",
  done: "rq:done",
  retired: "rq:retired",
  researched: "rq:researched",
  board: "rq:board",
  volunteers: "rq:volunteers",
  stats: "rq:stats",
  pstats: "rq:pstats",
  seeded: "rq:seeded",
  seedlock: "rq:seedlock",
  lease: (id: string) => `rq:lease:${id}`,
  ulease: (uid: string) => `rq:ulease:${uid}`,
  lstat: (token: string) => `rq:lstat:${token}`,
  state: (id: string) => `rq:state:${id}`,
  packet: (id: string) => `rq:packet:${id}`,
  claims: (id: string) => `rq:claims:${id}`,
  ckeys: (id: string) => `rq:ckeys:${id}`,
  groups: (id: string) => `rq:groups:${id}`,
  gkeys: (id: string) => `rq:gkeys:${id}`,
  ustats: (uid: string) => `rq:ustats:${uid}`,
  handle: (uid: string) => `rq:handle:${uid}`,
  handleName: (h: string) => `rq:handlename:${h.toLowerCase()}`,
  wtok: (hash: string) => `rq:wtok:${hash}`,
  wtoks: (uid: string) => `rq:wtoks:${uid}`,
  pm: (pmid: string) => `rq:pm:${pmid}`,
  pmq: (hash: string) => `rq:pmq:${hash}`,
};

const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const parse = <T>(s: string | null): T | null => {
  if (!s) return null;
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
};

// ---------- checklist & coverage ----------

export const MECH_CLASSES = ["loss_of_function", "haploinsufficiency", "dominant_negative", "gain_of_function"] as const;
export const RELATIONS = ["causes", "driven_by", "has_effect", "participates_in", "disrupts", "developed_for", "targets", "has_phenotype", "natural_history"] as const;
export const STUDY_TYPES = ["clinical_trial", "case_report", "case_series", "cohort", "functional_study", "animal_model", "review", "natural_history_study", "registry"] as const;
export const SPECIES = ["human", "mouse", "rat", "zebrafish", "fly", "worm", "cell", "in_vitro"] as const;
export const CERTAINTY = ["established", "suggested", "speculative"] as const;
export const THERAPY_STAGES = ["approved", "clinical", "preclinical", "tried_off_label"] as const;

export const CHECKLIST = [
  { id: "mechanism", label: "Molecular mechanism (loss of function, haploinsufficiency, dominant-negative or gain of function)", need: 2, unit: "verified quotes" },
  { id: "process", label: "Affected biological process", need: 1, unit: "claims" },
  { id: "therapies", label: "Therapies tried or approved, with stage", need: 1, unit: "therapies" },
  { id: "phenotypes", label: "Key distinctive phenotypes from the literature", need: 3, unit: "phenotypes" },
  { id: "natural_history", label: "Natural history or registry mentions", need: 1, unit: "mentions" },
  { id: "research_groups", label: "Research groups (senior author and affiliation, from PubMed)", need: 2, unit: "groups" },
] as const;
export type ChecklistId = (typeof CHECKLIST)[number]["id"];

export const PROVIDERS = ["openai", "anthropic", "other"] as const;
export type Provider = (typeof PROVIDERS)[number];
/** Which model family produced a claim: the client says so; a model name starting with "claude" is Anthropic. */
function providerOf(raw: unknown, model: string): Provider {
  if (raw === "openai" || raw === "anthropic") return raw;
  if (/^claude/i.test(model)) return "anthropic";
  if (/^(gpt|o\d|chatgpt)/i.test(model)) return "openai";
  return "other";
}

export interface StoredClaim {
  subject: string;
  relation: (typeof RELATIONS)[number];
  object: string;
  mechanism_class: (typeof MECH_CLASSES)[number] | "other" | null;
  therapy_stage: (typeof THERAPY_STAGES)[number] | null;
  quote: string;
  pmid: string;
  study_type: (typeof STUDY_TYPES)[number];
  species: (typeof SPECIES)[number] | null;
  certainty: (typeof CERTAINTY)[number];
  negated: boolean;
  disease: string;
  title: string;
  year: number | null;
  handle: string;
  model: string;
  provider: Provider;
  round: number;
  at: string;
  status: string;
}
export interface StoredGroup {
  pmid: string;
  senior_author: string;
  affiliation: string;
  title: string;
  year: number | null;
  disease: string;
  handle: string;
  model: string;
  provider: Provider;
  at: string;
  status: string;
}
export interface CoverageItem {
  id: ChecklistId;
  label: string;
  need: number;
  have: number;
  done: boolean;
  unit: string;
}

export function computeCoverage(claims: StoredClaim[], groups: StoredGroup[]): CoverageItem[] {
  const low = (s: string) => norm(s).toLowerCase();
  const distinct = (xs: string[]) => new Set(xs.map(low)).size;
  const have: Record<ChecklistId, number> = {
    mechanism: distinct(
      claims
        .filter((c) => (c.relation === "driven_by" || c.relation === "has_effect") && !c.negated && MECH_CLASSES.includes(c.mechanism_class as (typeof MECH_CLASSES)[number]))
        .map((c) => c.quote),
    ),
    process: distinct(claims.filter((c) => (c.relation === "participates_in" || c.relation === "disrupts") && !c.negated).map((c) => c.object)),
    therapies: distinct(claims.filter((c) => c.relation === "developed_for" && c.therapy_stage).map((c) => c.subject)),
    phenotypes: distinct(claims.filter((c) => c.relation === "has_phenotype" && !c.negated).map((c) => c.object)),
    natural_history: distinct(claims.filter((c) => c.relation === "natural_history").map((c) => c.quote)),
    research_groups: distinct(groups.map((g) => g.senior_author)),
  };
  return CHECKLIST.map((c) => ({ id: c.id, label: c.label, need: c.need, have: have[c.id], done: have[c.id] >= c.need, unit: c.unit }));
}
const gapsOf = (cov: CoverageItem[]) => cov.filter((c) => !c.done).map((c) => c.id);

// ---------- text normalisation & quote verification (same folding as pipeline/openai/common.mjs) ----------

export function norm(text: string): string {
  return String(text ?? "")
    .normalize("NFKC")
    .replace(/[‐-―−]/g, "-")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}
function sentenceCount(quote: string): number {
  return norm(quote)
    .replace(/\b(e\.g|i\.e|et al|vs|cf|Fig|Figs|approx|ca|No|Ref|Refs|sp|spp)\./g, "$1<dot>")
    .split(/(?<=[.!?])\s+(?=[A-Z(])/).length;
}

// ---------- PubMed (NCBI E-utilities, server-side, cached, throttled) ----------

export interface PubRecord {
  pmid: string;
  title: string;
  abstract: string;
  year: number | null;
  journal: string;
  first_author: string;
  n_authors: number;
  /** last two authors (senior positions) with their first affiliation, emails removed */
  senior: { name: string; affiliation: string }[];
  types: string[];
}

const ENT: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
const decode = (s: string) =>
  s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (w, b: string) => {
    if (b[0] === "#") {
      const code = b[1] === "x" || b[1] === "X" ? parseInt(b.slice(2), 16) : parseInt(b.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : w;
    }
    return ENT[b.toLowerCase()] ?? w;
  });
const xtext = (frag: string | undefined) =>
  decode(String(frag ?? "").replace(/<[^>]+>/g, ""))
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
export const stripEmails = (s: string) =>
  s
    .replace(/electronic address:?/gi, " ")
    .replace(/\S+@\S+/g, " ")
    .replace(/\s+([.,;])/g, "$1")
    .replace(/[\s.,;:]+$/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");

export function parsePubmedXml(xml: string): PubRecord[] {
  const out: PubRecord[] = [];
  for (const m of xml.matchAll(/<PubmedArticle>([\s\S]*?)<\/PubmedArticle>/g)) {
    const a = m[1];
    const pmid = /<PMID[^>]*>(\d+)<\/PMID>/.exec(a)?.[1];
    if (!pmid) continue;
    const absBlock = /<Abstract>([\s\S]*?)<\/Abstract>/.exec(a)?.[1] ?? "";
    const abstract = [...absBlock.matchAll(/<AbstractText([^>]*)>([\s\S]*?)<\/AbstractText>/g)]
      .map((x) => {
        const label = /Label="([^"]*)"/.exec(x[1])?.[1];
        const t = xtext(x[2]);
        return label && t ? `${decode(label)}: ${t}` : t;
      })
      .filter(Boolean)
      .join(" ");
    const authors = [...(/<AuthorList[^>]*>([\s\S]*?)<\/AuthorList>/.exec(a)?.[1] ?? "").matchAll(/<Author\b[^>]*>([\s\S]*?)<\/Author>/g)].map((x) => {
      const b = x[1];
      const last = xtext(/<LastName>([\s\S]*?)<\/LastName>/.exec(b)?.[1]);
      const fore = xtext(/<ForeName>([\s\S]*?)<\/ForeName>/.exec(b)?.[1]);
      const coll = xtext(/<CollectiveName>([\s\S]*?)<\/CollectiveName>/.exec(b)?.[1]);
      const aff = xtext(/<Affiliation>([\s\S]*?)<\/Affiliation>/.exec(b)?.[1]);
      return { name: last ? `${fore ? `${fore} ` : ""}${last}` : coll, affiliation: stripEmails(aff), collective: !last };
    });
    const people = authors.filter((x) => !x.collective && x.name);
    const year = Number(/<PubDate>[\s\S]*?<Year>(\d{4})<\/Year>/.exec(a)?.[1] ?? /<MedlineDate>(\d{4})/.exec(a)?.[1]) || null;
    out.push({
      pmid,
      title: xtext(/<ArticleTitle[^>]*>([\s\S]*?)<\/ArticleTitle>/.exec(a)?.[1]),
      abstract,
      year,
      journal: xtext(/<Journal>[\s\S]*?<Title>([\s\S]*?)<\/Title>/.exec(a)?.[1]),
      first_author: people[0]?.name ?? "",
      n_authors: people.length,
      senior: people.slice(-2).reverse().map(({ name, affiliation }) => ({ name, affiliation })),
      types: [...a.matchAll(/<PublicationType[^>]*>([^<]*)<\/PublicationType>/g)].map((x) => x[1]),
    });
  }
  return out;
}

let ncbiLast = 0;
let ncbiChain: Promise<unknown> = Promise.resolve();
async function ncbiThrottle() {
  // in this instance: at least 350 ms between requests; across instances: at most 3 per second window
  const mine = ncbiChain.then(async () => {
    const d = ncbiLast + 350 - Date.now();
    if (d > 0) await sleep(d);
    ncbiLast = Date.now();
  });
  ncbiChain = mine.catch(() => undefined);
  await mine;
  const limit = process.env.NCBI_API_KEY ? 9 : 3;
  for (let i = 0; i < 20; i++) {
    const sec = Math.floor(Date.now() / 1000);
    if ((await kv().incrWindow(`rq:ncbi:${sec}`, 3)) <= limit) return;
    await sleep(1000 - (Date.now() % 1000) + 25);
  }
}

async function ncbi(endpoint: "esearch" | "efetch", params: Record<string, string>): Promise<string> {
  const q = new URLSearchParams({ db: "pubmed", tool: NCBI_TOOL, ...params });
  if (process.env.NCBI_API_KEY) q.set("api_key", process.env.NCBI_API_KEY);
  const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/${endpoint}.fcgi`;
  for (let attempt = 0; attempt < 3; attempt++) {
    await ncbiThrottle();
    let r: Response;
    try {
      r = await fetch(url, { method: "POST", body: q, cache: "no-store", signal: AbortSignal.timeout(25_000) });
    } catch {
      await sleep(800 * (attempt + 1));
      continue;
    }
    if (r.status === 429 || r.status >= 500) {
      await sleep(1200 * (attempt + 1));
      continue;
    }
    if (!r.ok) throw new HttpError(502, `PubMed returned HTTP ${r.status}.`);
    return r.text();
  }
  throw new HttpError(503, "PubMed is not answering right now. Please try again in a minute.");
}

const cleanTerm = (s: string) =>
  s
    .replace(/["[\]()#*:]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
const TOPIC: Record<string, string> = {
  mechanism: '"loss of function"[tiab] OR haploinsufficiency[tiab] OR "dominant negative"[tiab] OR "gain of function"[tiab] OR pathogenesis[tiab] OR mechanism*[tiab]',
  process: "pathway*[tiab] OR function*[tiab]",
  therapies: "therap*[tiab] OR treatment*[tiab] OR trial*[tiab]",
  phenotypes: "phenotyp*[tiab] OR clinical[tiab] OR features[tiab]",
  natural_history: '"natural history"[tiab] OR registry[tiab] OR cohort[tiab] OR outcome*[tiab]',
};

/** PubMed queries in priority order: disease names with the missing topics, names alone, then the gene in a germline/syndromic context. */
export function buildQueries(d: SeedDisease, gaps: string[]): string[] {
  const names = [...new Set([d.name, ...d.synonyms].map(cleanTerm))].filter((n) => n.length >= 4 && n.length <= 90).slice(0, 5);
  const nameClause = names.length ? `(${names.map((n) => `"${n}"[tiab]`).join(" OR ")})` : "";
  const genes = d.genes.slice(0, 3).map((g) => `${cleanTerm(g)}[tiab]`);
  const geneClause = genes.length
    ? `((${genes.join(" OR ")}) AND (germline[tiab] OR inherited[tiab] OR hereditary[tiab] OR syndrome[tiab] OR "de novo"[tiab] OR congenital[tiab] OR patients[tiab]))`
    : "";
  const topics = [...new Set((gaps.length ? gaps : Object.keys(TOPIC)).filter((g) => TOPIC[g]).map((g) => TOPIC[g]))];
  const topicClause = topics.length ? ` AND (${topics.join(" OR ")})` : "";
  const out: string[] = [];
  if (nameClause) out.push(`${nameClause}${topicClause} AND hasabstract`, `${nameClause} AND hasabstract`);
  if (geneClause) out.push(`${geneClause}${topicClause} AND hasabstract`);
  return out;
}

async function esearch(term: string): Promise<string[]> {
  const key = K.pmq(sha(term).slice(0, 32));
  const cached = parse<string[]>(await kv().get(key));
  if (cached) return cached;
  const j = JSON.parse(await ncbi("esearch", { term, retmode: "json", retmax: "80", sort: "relevance" })) as { esearchresult?: { idlist?: string[] } };
  const ids = (j.esearchresult?.idlist ?? []).filter((x) => /^\d{1,9}$/.test(x));
  await kv().set(key, JSON.stringify(ids), { ex: 7 * 86400 });
  return ids;
}

export async function pubRecords(pmids: string[]): Promise<Map<string, PubRecord>> {
  const store = kv();
  const out = new Map<string, PubRecord>();
  const cached = await store.mget(pmids.map(K.pm));
  pmids.forEach((p, i) => {
    const r = parse<PubRecord>(cached[i]);
    if (r) out.set(p, r);
  });
  const missing = pmids.filter((p) => !out.has(p));
  if (missing.length) {
    const xml = await ncbi("efetch", { id: missing.join(","), retmode: "xml", rettype: "abstract" });
    for (const r of parsePubmedXml(xml)) {
      if (!missing.includes(r.pmid)) continue;
      out.set(r.pmid, r);
      await store.set(K.pm(r.pmid), JSON.stringify(r));
    }
  }
  return out;
}

// ---------- state, leases, packets ----------

interface Lease {
  id: string;
  uid: string;
  handle: string;
  token: string;
  claimedAt: number;
  expiresAt: number;
  round: number;
  originalScore: number;
}
interface HistoryEntry {
  handle: string;
  claimedAt: string;
  finishedAt: string;
  reason: "done" | "expired";
  submissions: number;
  accepted: number;
  rejected: number;
}
export interface DiseaseState {
  id: string;
  status: "queued" | "leased" | "complete" | "retired";
  rounds: number;
  abandoned: number;
  coverage: CoverageItem[];
  gaps: string[];
  usedPmids: string[];
  history: HistoryEntry[];
  updated: string;
}
interface PacketMeta {
  id: string;
  token: string;
  round: number;
  pmids: string[];
  query: string;
  built: string;
}

const getState = async (id: string) => parse<DiseaseState>(await kv().get(K.state(id)));
const saveState = (s: DiseaseState) => kv().set(K.state(s.id), JSON.stringify({ ...s, updated: new Date().toISOString() }));
const newState = (id: string): DiseaseState => ({ id, status: "queued", rounds: 0, abandoned: 0, coverage: computeCoverage([], []), gaps: CHECKLIST.map((c) => c.id), usedPmids: [], history: [], updated: "" });
const getLease = async (id: string) => parse<Lease>(await kv().get(K.lease(id)));

export async function claimsFor(id: string): Promise<StoredClaim[]> {
  return (await kv().lrange(K.claims(id), 0, -1)).map((s) => parse<StoredClaim>(s)).filter((x): x is StoredClaim => !!x);
}
export async function groupsFor(id: string): Promise<StoredGroup[]> {
  return (await kv().lrange(K.groups(id), 0, -1)).map((s) => parse<StoredGroup>(s)).filter((x): x is StoredGroup => !!x);
}

let seededMemo = false;
async function ensureSeeded() {
  if (seededMemo) return;
  const store = kv();
  if (await store.get(K.seeded)) {
    seededMemo = true;
    return;
  }
  if (!(await store.set(K.seedlock, "1", { ex: 120, nx: true }))) {
    // another request is seeding right now: wait for it (seeding takes a few seconds at most)
    for (let i = 0; i < 60; i++) {
      await sleep(250);
      if (await store.get(K.seeded)) {
        seededMemo = true;
        return;
      }
    }
    throw new HttpError(503, "The queue is being prepared. Try again in a few seconds.");
  }
  const items = SEED.rows.map((t, i) => ({ member: t[0], score: i }));
  for (let i = 0; i < items.length; i += 1000) await store.zadd(K.avail, items.slice(i, i + 1000), true);
  await store.set(K.seeded, SEED_VERSION);
  seededMemo = true;
}

/** Finalise one disease whose lease ended (expired or "I'm done"): coverage, gaps, requeue or retire. */
async function finalize(id: string, lease: Lease | null, reason: "done" | "expired") {
  const store = kv();
  const [claims, groups] = await Promise.all([claimsFor(id), groupsFor(id)]);
  const coverage = computeCoverage(claims, groups);
  const st = (await getState(id)) ?? newState(id);
  const ls = lease ? await store.hgetall(K.lstat(lease.token)) : {};
  const submissions = ls.submissions ?? 0;
  st.history.push({
    handle: lease?.handle ?? "unknown",
    claimedAt: lease ? new Date(lease.claimedAt).toISOString() : "",
    finishedAt: new Date().toISOString(),
    reason,
    submissions,
    accepted: ls.accepted ?? 0,
    rejected: ls.rejected ?? 0,
  });
  st.history = st.history.slice(-20);
  if (submissions > 0) st.rounds += 1;
  else st.abandoned += 1;
  st.coverage = coverage;
  st.gaps = gapsOf(coverage);
  const now = Date.now();
  if (!st.gaps.length) {
    st.status = "complete";
    await store.zadd(K.done, [{ member: id, score: now }]);
  } else if (st.rounds >= MAX_ROUNDS) {
    st.status = "retired";
    await store.zadd(K.retired, [{ member: id, score: now }]);
  } else {
    st.status = "queued";
    await store.zadd(K.avail, [{ member: id, score: REQUEUE_BASE + now }]);
  }
  await saveState(st);
  if (lease) {
    if ((await store.get(K.ulease(lease.uid))) === id) await store.del(K.ulease(lease.uid));
    if (submissions > 0) await store.hincrby(K.ustats(lease.uid), "tasks", 1);
  }
  await store.del(K.lease(id));
  if (reason === "done" || submissions > 0) await store.hincrby(K.stats, "rounds_finished", 1);
  return st;
}

/** Finalise leases that ran out. Lazy (called on every claim) and from /api/queue/sweep. */
export async function sweepExpired(limit = 25): Promise<string[]> {
  const store = kv();
  const expired = await store.zrangeByScore(K.leases, Date.now(), limit);
  const done: string[] = [];
  for (const { member: id } of expired) {
    if ((await store.zrem(K.leases, id)) !== 1) continue; // another sweeper took it
    await finalize(id, await getLease(id), "expired");
    done.push(id);
  }
  return done;
}

/** Re-add diseases that fell out of every list (e.g. a crash between ZPOPMIN and the lease write). */
export async function reconcile(): Promise<number> {
  const store = kv();
  await ensureSeeded();
  const [avail, leases, done, retired] = await Promise.all([store.zrange(K.avail, 0, -1), store.zrange(K.leases, 0, -1), store.zrange(K.done, 0, -1), store.zrange(K.retired, 0, -1)]);
  const known = new Set([...avail, ...leases, ...done, ...retired].map((z) => z.member));
  const missing = SEED.rows.map((t, i) => ({ member: t[0], score: i })).filter((z) => !known.has(z.member));
  let readded = 0;
  for (const z of missing) {
    if (await getLease(z.member)) continue; // a claim is in flight
    const st = await getState(z.member);
    readded += await store.zadd(K.avail, [{ member: z.member, score: st && st.rounds > 0 ? REQUEUE_BASE + Date.now() : z.score }], true);
  }
  return readded;
}

// ---------- packets ----------

export const INSTRUCTIONS = `You are helping build an open rare-disease knowledge graph. You read PubMed records (title, abstract and the two senior authors) about ONE disease and extract evidence claims in JSON that matches the schema. A server checks every claim: anything not copied exactly from the records is rejected.

Relations (subject -> object):
- causes: gene -> disease. Variants in the gene cause the disease.
- driven_by: disease -> molecular mechanism. Set mechanism_class to loss_of_function, haploinsufficiency, dominant_negative or gain_of_function (or "other" for a different molecular effect). The object names the mechanism as the text does.
- has_effect: variant group (e.g. "truncating variants", "p.R123W") -> molecular mechanism. Set mechanism_class as for driven_by.
- participates_in: gene or protein -> biological process (e.g. "lysosomal degradation of heparan sulfate", "mitochondrial complex I assembly").
- disrupts: disease -> biological process affected in patients or models.
- developed_for: therapy -> disease. A treatment approved, tested in a trial, tried off-label, or tested in models. Set therapy_stage: approved, clinical (in a clinical trial), preclinical (cells or animals), tried_off_label (case reports or series). Name the therapy as the text does.
- targets: therapy -> mechanism or process it acts on.
- has_phenotype: disease -> clinical feature observed in patients (not in animal or cell models). Prefer distinctive features over generic ones.
- natural_history: disease -> a natural history study, registry, long-term cohort or outcome finding (object names the study, registry or cohort, or the course described).

Rules:
1. quote: copy exactly ONE sentence from the title or abstract of the record whose pmid you give, character for character: the same words, case, punctuation, numbers, symbols and Greek letters. Never paraphrase, shorten, join two sentences or fix anything. If no single sentence states the claim, leave the claim out.
2. pmid: the PMID of the record the quote comes from, exactly as given.
3. subject and object: specific entities as the text names them. No generic subjects or objects ("patients", "the disease", "these variants", "function").
4. negated = true when the sentence says the relation does NOT hold ("did not improve", "no dominant-negative effect"). Write the claim in its positive form and set negated = true.
5. certainty: "established" = a result of this work or accepted fact; "suggested" = the authors' interpretation ("suggest", "may", "likely"); "speculative" = a hypothesis ("could", "might", "we propose").
6. study_type: the design behind the claim: clinical_trial, case_report, case_series, cohort, functional_study, animal_model, review, natural_history_study, registry. species: human, mouse, rat, zebrafish, fly, worm, cell, in_vitro, or null.
7. mechanism_class is null unless the relation is driven_by or has_effect. therapy_stage is null unless the relation is developed_for.
8. research_groups: for records that report original research on this disease, give the senior author exactly as listed under "Senior authors" and that author's affiliation copied exactly (or a contiguous part of it naming the institution). Never give emails or other contact details.
9. Focus on what the task says is still missing, then add other solid claims. At most 25 claims per request. Return empty arrays if the records contain nothing usable.`;

export const CLAIM_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["claims", "research_groups"],
  properties: {
    claims: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["subject", "relation", "object", "mechanism_class", "therapy_stage", "quote", "pmid", "study_type", "species", "certainty", "negated"],
        properties: {
          subject: { type: "string" },
          relation: { type: "string", enum: [...RELATIONS] },
          object: { type: "string" },
          mechanism_class: { type: ["string", "null"], enum: [...MECH_CLASSES, "other", null] },
          therapy_stage: { type: ["string", "null"], enum: [...THERAPY_STAGES, null] },
          quote: { type: "string", description: "ONE sentence copied character for character from the title or abstract" },
          pmid: { type: "string" },
          study_type: { type: "string", enum: [...STUDY_TYPES] },
          species: { type: ["string", "null"], enum: [...SPECIES, null] },
          certainty: { type: "string", enum: [...CERTAINTY] },
          negated: { type: "boolean" },
        },
      },
    },
    research_groups: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["pmid", "senior_author", "affiliation"],
        properties: { pmid: { type: "string" }, senior_author: { type: "string" }, affiliation: { type: "string" } },
      },
    },
  },
} as const;

export interface Packet {
  version: 1;
  lease: { diseaseId: string; token: string; claimedAt: string; expiresAt: string; round: number; maxRounds: number };
  disease: { id: string; name: string; synonyms: string[]; genes: string[]; mondo: string | null; omim: string[]; orpha: string[]; url: string };
  known: {
    mechanismClasses: string[];
    dismech: boolean;
    cluster: string | null;
    trials: { byName: number; byGene: number; active: number };
    patientOrganisations: number;
    registries: number;
    prevalence: boolean;
    mechanismNeighbourOf: string[];
    acceptedClaims: number;
  };
  checklist: CoverageItem[];
  missing: string[];
  previousRounds: { handle: string; finishedAt: string; reason: string; accepted: number }[];
  query: string;
  abstracts: { pmid: string; title: string; abstract: string; year: number | null; journal: string; senior_authors: { name: string; affiliation: string }[]; url: string }[];
  instructions: string;
  schema: typeof CLAIM_SCHEMA;
  batchSize: number;
  statusLabel: string;
}

async function buildPacketMeta(d: SeedDisease, st: DiseaseState | null, token: string, round: number): Promise<PacketMeta> {
  const gaps = st?.gaps?.length ? st.gaps : CHECKLIST.map((c) => c.id);
  const used = new Set(st?.usedPmids ?? []);
  const ids: string[] = [];
  const asked: string[] = [];
  for (const q of buildQueries(d, gaps)) {
    if (ids.length >= MAX_ABSTRACTS + 5) break;
    asked.push(q);
    for (const p of await esearch(q)) if (!used.has(p) && !ids.includes(p)) ids.push(p);
  }
  const query = asked.join("  ||  ");
  const recs = await pubRecords(ids.slice(0, MAX_ABSTRACTS + 5));
  const pmids = ids.filter((p) => recs.get(p)?.abstract).slice(0, MAX_ABSTRACTS);
  return { id: d.id, token, round, pmids, query, built: new Date().toISOString() };
}

async function packetFor(lease: Lease, meta: PacketMeta): Promise<Packet> {
  const d = seedDisease(lease.id)!;
  const st = await getState(lease.id);
  const [claims, groups, recs] = await Promise.all([claimsFor(lease.id), groupsFor(lease.id), pubRecords(meta.pmids)]);
  const coverage = computeCoverage(claims, groups);
  return {
    version: 1,
    lease: { diseaseId: lease.id, token: lease.token, claimedAt: new Date(lease.claimedAt).toISOString(), expiresAt: new Date(lease.expiresAt).toISOString(), round: lease.round, maxRounds: MAX_ROUNDS },
    disease: {
      id: d.id,
      name: d.name,
      synonyms: d.synonyms,
      genes: d.genes,
      mondo: d.id.startsWith("MONDO:") ? d.id : null,
      omim: d.omim,
      orpha: d.orpha,
      url: `/d/${encodeURIComponent(d.id)}`,
    },
    known: {
      mechanismClasses: d.mechanismClasses,
      dismech: d.dismech,
      cluster: d.cluster,
      trials: d.trials,
      patientOrganisations: d.orgs,
      registries: d.registries,
      prevalence: d.prevalence,
      mechanismNeighbourOf: d.neighbourOf,
      acceptedClaims: claims.length,
    },
    checklist: coverage,
    missing: gapsOf(coverage),
    previousRounds: (st?.history ?? []).map((h) => ({ handle: h.handle, finishedAt: h.finishedAt, reason: h.reason, accepted: h.accepted })),
    query: meta.query,
    abstracts: meta.pmids
      .map((p) => recs.get(p))
      .filter((r): r is PubRecord => !!r)
      .map((r) => ({ pmid: r.pmid, title: r.title, abstract: r.abstract, year: r.year, journal: r.journal, senior_authors: r.senior, url: `https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/` })),
    instructions: INSTRUCTIONS,
    schema: CLAIM_SCHEMA,
    batchSize: 5,
    statusLabel: STATUS_LABEL,
  };
}

// ---------- volunteers ----------

export interface Volunteer {
  uid: string;
  handle: string;
  via: "session" | "token";
}

const HANDLE_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{2,23}$/;

export async function handleOf(uid: string): Promise<string> {
  const store = kv();
  const h = await store.get(K.handle(uid));
  if (h) return h;
  const auto = `volunteer-${sha(`handle:${uid}`).slice(0, 6)}`;
  await store.set(K.handle(uid), auto, { nx: true });
  return (await store.get(K.handle(uid))) ?? auto;
}

export async function setHandle(uid: string, wanted: unknown): Promise<string> {
  const h = typeof wanted === "string" ? wanted.trim() : "";
  if (!HANDLE_RE.test(h)) throw new HttpError(400, "Use 3–24 letters, numbers, - or _ for your handle.");
  if (/admin|atlas|moderator|anthropic|openai/i.test(h)) throw new HttpError(400, "Please choose another handle.");
  const store = kv();
  const current = await handleOf(uid);
  if (current.toLowerCase() === h.toLowerCase()) {
    await store.set(K.handle(uid), h);
    return h;
  }
  if (!(await store.set(K.handleName(h), uid, { nx: true }))) throw new HttpError(409, "That handle is taken.");
  await store.del(K.handleName(current));
  await store.set(K.handle(uid), h);
  return h;
}

/** Who is calling: an atlas session cookie (browser) or a worker token (Authorization: Bearer rqw_…). */
export async function volunteer(req: Request, { write }: { write: boolean }): Promise<Volunteer> {
  const store = kv();
  const auth = req.headers.get("authorization") ?? "";
  if (/^Bearer\s+/i.test(auth)) {
    const tok = auth.replace(/^Bearer\s+/i, "").trim();
    if (!/^rqw_[A-Za-z0-9_-]{30,80}$/.test(tok)) throw new HttpError(401, "That worker token is not valid. Create a new one on /research-queue.");
    const uid = await store.get(K.wtok(sha(tok)));
    if (!uid || !(await getJson(`user:${uid}`))) throw new HttpError(401, "That worker token is not recognised (revoked, expired or the account was deleted). Create a new one on /research-queue.");
    return { uid, handle: await handleOf(uid), via: "token" };
  }
  if (write) assertSameOrigin(req);
  const u = await currentUser();
  if (!u) throw new HttpError(401, "Please sign in to your atlas account to research. Anonymous use is refused to deter abuse.");
  return { uid: u.id, handle: await handleOf(u.id), via: "session" };
}

export async function createWorkerToken(v: Volunteer): Promise<{ token: string; expires: string }> {
  if (v.via !== "session") throw new HttpError(403, "Create worker tokens from the website while signed in.");
  const store = kv();
  const n = await store.incrWindow(`rq:rl:tok:${v.uid}`, 3600);
  if (n > 10) throw new HttpError(429, "Too many tokens this hour.");
  const token = `rqw_${randomBytes(30).toString("base64url")}`;
  const ttl = 30 * 86400;
  await store.set(K.wtok(sha(token)), v.uid, { ex: ttl });
  await store.sadd(K.wtoks(v.uid), sha(token));
  return { token, expires: new Date(Date.now() + ttl * 1000).toISOString() };
}

export async function revokeWorkerTokens(v: Volunteer): Promise<number> {
  const store = kv();
  const hashes = await store.smembers(K.wtoks(v.uid));
  await store.del(...hashes.map(K.wtok), K.wtoks(v.uid));
  return hashes.length;
}

// ---------- claim / submit / done ----------

async function currentLease(uid: string): Promise<Lease | null> {
  const store = kv();
  const id = await store.get(K.ulease(uid));
  if (!id) return null;
  const lease = await getLease(id);
  if (!lease || lease.uid !== uid) return null;
  return lease;
}

export async function myTask(v: Volunteer): Promise<Packet | null> {
  const lease = await currentLease(v.uid);
  if (!lease || lease.expiresAt <= Date.now()) return null;
  const meta = parse<PacketMeta>(await kv().get(K.packet(lease.id)));
  if (!meta || meta.token !== lease.token) return null;
  return packetFor(lease, meta);
}

export async function claim(v: Volunteer): Promise<{ packet: Packet | null; resumed: boolean; swept: string[] }> {
  const store = kv();
  await ensureSeeded();
  const swept = await sweepExpired(10);
  const existing = await myTask(v);
  if (existing) return { packet: existing, resumed: true, swept };
  if ((await store.incrWindow(`rq:rl:claim:${v.uid}`, 3600)) > CLAIMS_PER_HOUR) throw new HttpError(429, "You have claimed many diseases this hour. Please wait a little.");
  await store.sadd(K.volunteers, v.uid);
  for (let attempt = 0; attempt < 6; attempt++) {
    const top = await store.zpopmin(K.avail);
    if (!top) return { packet: null, resumed: false, swept };
    const d = seedDisease(top.member);
    if (!d) continue; // no longer in the seed: dropped
    const st = await getState(d.id);
    const now = Date.now();
    const lease: Lease = {
      id: d.id,
      uid: v.uid,
      handle: v.handle,
      token: randomBytes(18).toString("base64url"),
      claimedAt: now,
      expiresAt: now + LEASE_SECONDS * 1000,
      round: (st?.rounds ?? 0) + 1,
      originalScore: top.score,
    };
    // second guard: if a lease record already exists (an orphan re-added by reconcile), skip it
    if (!(await store.set(K.lease(d.id), JSON.stringify(lease), { ex: LEASE_SECONDS + LEASE_GRACE_SECONDS, nx: true }))) continue;
    let meta: PacketMeta;
    try {
      meta = await buildPacketMeta(d, st, lease.token, lease.round);
    } catch (e) {
      // PubMed trouble: give the disease back at the same place and report the error
      await store.del(K.lease(d.id));
      await store.zadd(K.avail, [{ member: d.id, score: top.score }]);
      throw e;
    }
    await store.zadd(K.leases, [{ member: d.id, score: lease.expiresAt }]);
    await store.set(K.ulease(v.uid), d.id, { ex: LEASE_SECONDS + LEASE_GRACE_SECONDS });
    await store.set(K.packet(d.id), JSON.stringify(meta), { ex: LEASE_SECONDS + LEASE_GRACE_SECONDS });
    const next = st ?? newState(d.id);
    next.status = "leased";
    next.usedPmids = [...new Set([...(next.usedPmids ?? []), ...meta.pmids])].slice(-300);
    await saveState(next);
    return { packet: await packetFor(lease, meta), resumed: false, swept };
  }
  return { packet: null, resumed: false, swept };
}

async function leaseFor(v: Volunteer, token: unknown): Promise<Lease> {
  const lease = await currentLease(v.uid);
  const t = typeof token === "string" ? token : "";
  if (!lease || !t || t.length !== lease.token.length || !timingSafeEqual(Buffer.from(t), Buffer.from(lease.token)))
    throw new HttpError(409, "This task is no longer yours (finished or taken over). Claim a new disease.");
  if (lease.expiresAt <= Date.now()) throw new HttpError(410, "Your 7-hour lease has expired. The disease went back to the queue; claim again to continue.");
  return lease;
}

export interface Rejection {
  index: number;
  kind: "claim" | "research_group";
  reason: string;
}

const isStr = (x: unknown, max: number, min = 1): x is string => typeof x === "string" && x.trim().length >= min && x.length <= max;
const oneOf = <T extends readonly (string | null)[]>(x: unknown, list: T): x is T[number] => list.includes(x as T[number]);

function checkClaimShape(c: unknown): string | null {
  if (!c || typeof c !== "object" || Array.isArray(c)) return "not an object";
  const o = c as Record<string, unknown>;
  const allowed = CLAIM_SCHEMA.properties.claims.items.required as readonly string[];
  for (const k of Object.keys(o)) if (!allowed.includes(k)) return `unexpected field "${k.slice(0, 40)}"`;
  for (const k of allowed) if (!(k in o)) return `missing field "${k}"`;
  if (!isStr(o.subject, 200)) return "subject must be a non-empty string (max 200)";
  if (!isStr(o.object, 300)) return "object must be a non-empty string (max 300)";
  if (!oneOf(o.relation, RELATIONS)) return "relation is not one of the allowed values";
  if (!oneOf(o.mechanism_class, [...MECH_CLASSES, "other", null] as const)) return "mechanism_class is not one of the allowed values";
  if (!oneOf(o.therapy_stage, [...THERAPY_STAGES, null] as const)) return "therapy_stage is not one of the allowed values";
  if (!isStr(o.quote, 800)) return "quote must be a non-empty string (max 800)";
  if (typeof o.pmid !== "string" || !/^\d{1,9}$/.test(o.pmid.trim())) return "pmid must be digits";
  if (!oneOf(o.study_type, STUDY_TYPES)) return "study_type is not one of the allowed values";
  if (!oneOf(o.species, [...SPECIES, null] as const)) return "species is not one of the allowed values";
  if (!oneOf(o.certainty, CERTAINTY)) return "certainty is not one of the allowed values";
  if (typeof o.negated !== "boolean") return "negated must be true or false";
  if ((o.relation === "driven_by" || o.relation === "has_effect") && !o.mechanism_class) return "driven_by / has_effect need a mechanism_class";
  if (o.relation === "developed_for" && !o.therapy_stage) return "developed_for needs a therapy_stage";
  return null;
}

function checkGroupShape(g: unknown): string | null {
  if (!g || typeof g !== "object" || Array.isArray(g)) return "not an object";
  const o = g as Record<string, unknown>;
  for (const k of Object.keys(o)) if (!["pmid", "senior_author", "affiliation"].includes(k)) return `unexpected field "${k.slice(0, 40)}"`;
  if (typeof o.pmid !== "string" || !/^\d{1,9}$/.test(o.pmid.trim())) return "pmid must be digits";
  if (!isStr(o.senior_author, 120)) return "senior_author must be a non-empty string";
  if (!isStr(o.affiliation, 1200, 8)) return "affiliation must be 8 to 1200 characters";
  if (/@|https?:\/\/|\+?\d[\d\s().-]{7,}\d/.test(o.affiliation as string)) return "affiliation must not contain emails, links or phone numbers";
  return null;
}

/** Verify and store one submission. Nothing from the client is trusted. */
export async function submit(v: Volunteer, body: Record<string, unknown>) {
  const store = kv();
  const lease = await leaseFor(v, body.token);
  if ((await store.incrWindow(`rq:rl:submit:${v.uid}`, 3600)) > SUBMITS_PER_HOUR) throw new HttpError(429, "Too many submissions this hour. Please slow down.");
  const meta = parse<PacketMeta>(await store.get(K.packet(lease.id)));
  if (!meta || meta.token !== lease.token) throw new HttpError(409, "The task packet is missing. Claim again.");
  const model = typeof body.model === "string" && /^[\w.:/@ -]{1,80}$/.test(body.model.trim()) ? body.model.trim() : "unknown";
  const provider = providerOf(body.provider, model);
  const rawClaims = Array.isArray(body.claims) ? body.claims : [];
  const rawGroups = Array.isArray(body.research_groups) ? body.research_groups : [];
  if (!Array.isArray(body.claims) && !Array.isArray(body.research_groups)) throw new HttpError(400, "Send claims and/or research_groups arrays.");
  if (rawClaims.length > MAX_CLAIMS_PER_SUBMIT || rawGroups.length > MAX_GROUPS_PER_SUBMIT)
    throw new HttpError(413, `At most ${MAX_CLAIMS_PER_SUBMIT} claims and ${MAX_GROUPS_PER_SUBMIT} research groups per submission.`);

  const inPacket = new Set(meta.pmids);
  const recs = await pubRecords(meta.pmids);
  const now = new Date().toISOString();
  const rejected: Rejection[] = [];
  const accepted: StoredClaim[] = [];
  const acceptedGroups: StoredGroup[] = [];
  let duplicates = 0;

  for (const [index, c] of rawClaims.entries()) {
    const bad = checkClaimShape(c);
    if (bad) {
      rejected.push({ index, kind: "claim", reason: `schema: ${bad}` });
      continue;
    }
    const o = c as Record<string, unknown>;
    const pmid = String(o.pmid).trim();
    const rec = recs.get(pmid);
    if (!inPacket.has(pmid) || !rec) {
      rejected.push({ index, kind: "claim", reason: `PMID ${pmid} is not in this task's packet` });
      continue;
    }
    const q = norm(String(o.quote));
    if (q.length < 25 || q.split(" ").length < 4) {
      rejected.push({ index, kind: "claim", reason: "quote is too short to be a sentence" });
      continue;
    }
    if (!norm(rec.abstract).includes(q) && !norm(rec.title).includes(q)) {
      rejected.push({ index, kind: "claim", reason: `quote is not a verbatim sentence of PMID ${pmid}'s title or abstract` });
      continue;
    }
    if (sentenceCount(q) > 1) {
      rejected.push({ index, kind: "claim", reason: "quote spans more than one sentence" });
      continue;
    }
    const claimKey = sha(`${pmid}|${q}|${o.relation}|${norm(String(o.object)).toLowerCase()}|${o.negated}`).slice(0, 24);
    if ((await store.sadd(K.ckeys(lease.id), claimKey)) === 0) {
      duplicates++;
      continue;
    }
    accepted.push({
      subject: norm(String(o.subject)),
      relation: o.relation as StoredClaim["relation"],
      object: norm(String(o.object)),
      mechanism_class: (o.relation === "driven_by" || o.relation === "has_effect" ? o.mechanism_class : null) as StoredClaim["mechanism_class"],
      therapy_stage: (o.relation === "developed_for" ? o.therapy_stage : null) as StoredClaim["therapy_stage"],
      quote: String(o.quote).trim(),
      pmid,
      study_type: o.study_type as StoredClaim["study_type"],
      species: o.species as StoredClaim["species"],
      certainty: o.certainty as StoredClaim["certainty"],
      negated: o.negated as boolean,
      disease: lease.id,
      title: rec.title,
      year: rec.year,
      handle: v.handle,
      model,
      provider,
      round: lease.round,
      at: now,
      status: STATUS_LABEL,
    });
  }

  for (const [index, g] of rawGroups.entries()) {
    const bad = checkGroupShape(g);
    if (bad) {
      rejected.push({ index, kind: "research_group", reason: `schema: ${bad}` });
      continue;
    }
    const o = g as Record<string, string>;
    const pmid = o.pmid.trim();
    const rec = recs.get(pmid);
    if (!inPacket.has(pmid) || !rec) {
      rejected.push({ index, kind: "research_group", reason: `PMID ${pmid} is not in this task's packet` });
      continue;
    }
    const who = rec.senior.find((s) => norm(s.name).toLowerCase() === norm(o.senior_author).toLowerCase());
    if (!who) {
      rejected.push({ index, kind: "research_group", reason: `"${o.senior_author.slice(0, 60)}" is not a senior (last two) author of PMID ${pmid}` });
      continue;
    }
    const aff = norm(o.affiliation);
    if (!who.affiliation || !norm(who.affiliation).includes(aff)) {
      rejected.push({ index, kind: "research_group", reason: "affiliation is not copied from that author's PubMed affiliation" });
      continue;
    }
    if ((await store.sadd(K.gkeys(lease.id), sha(`${norm(who.name).toLowerCase()}|${aff.toLowerCase()}`).slice(0, 24))) === 0) {
      duplicates++;
      continue;
    }
    acceptedGroups.push({ pmid, senior_author: who.name, affiliation: aff, title: rec.title, year: rec.year, disease: lease.id, handle: v.handle, model, provider, at: now, status: STATUS_LABEL });
  }

  if (accepted.length) await store.rpush(K.claims(lease.id), ...accepted.map((c) => JSON.stringify(c)));
  if (acceptedGroups.length) await store.rpush(K.groups(lease.id), ...acceptedGroups.map((g) => JSON.stringify(g)));
  const nAcc = accepted.length + acceptedGroups.length;
  const nRej = rejected.length;
  await Promise.all([
    store.hincrby(K.lstat(lease.token), "submissions", 1),
    nAcc ? store.hincrby(K.lstat(lease.token), "accepted", nAcc) : null,
    nRej ? store.hincrby(K.lstat(lease.token), "rejected", nRej) : null,
    nAcc ? store.hincrby(K.ustats(v.uid), "accepted", nAcc) : null,
    nRej ? store.hincrby(K.ustats(v.uid), "rejected", nRej) : null,
    duplicates ? store.hincrby(K.ustats(v.uid), "duplicates", duplicates) : null,
    store.zincrby(K.board, nAcc, v.uid),
    accepted.length ? store.hincrby(K.stats, "claims_verified", accepted.length) : null,
    acceptedGroups.length ? store.hincrby(K.stats, "groups_verified", acceptedGroups.length) : null,
    nRej ? store.hincrby(K.stats, "rejected", nRej) : null,
    store.hincrby(K.stats, "submissions", 1),
    nAcc ? store.hincrby(K.pstats, `${provider}:accepted`, nAcc) : null,
    nRej ? store.hincrby(K.pstats, `${provider}:rejected`, nRej) : null,
    nAcc ? store.sadd(K.researched, lease.id) : null,
  ]);
  const [claims, groups] = await Promise.all([claimsFor(lease.id), groupsFor(lease.id)]);
  const coverage = computeCoverage(claims, groups);
  const st = (await getState(lease.id)) ?? newState(lease.id);
  st.coverage = coverage;
  st.gaps = gapsOf(coverage);
  await saveState(st);
  return { accepted: accepted.length, acceptedGroups: acceptedGroups.length, duplicates, rejected, checklist: coverage, missing: st.gaps, complete: !st.gaps.length };
}

/** "I'm done": finalise the volunteer's lease now. */
export async function done(v: Volunteer, body: Record<string, unknown>) {
  const store = kv();
  const lease = await currentLease(v.uid);
  const t = typeof body.token === "string" ? body.token : "";
  if (!lease || !t || t !== lease.token) throw new HttpError(409, "This task is no longer yours.");
  if ((await store.zrem(K.leases, lease.id)) !== 1) throw new HttpError(409, "This task was already finished.");
  const st = await finalize(lease.id, lease, "done");
  return { status: st.status, checklist: st.coverage, missing: st.gaps, rounds: st.rounds, maxRounds: MAX_ROUNDS };
}

// ---------- public views ----------

export async function stats(v: Volunteer | null) {
  const store = kv();
  const seeded = !!(await store.get(K.seeded));
  const ps = await store.hgetall(K.pstats);
  const byProvider = PROVIDERS.map((p) => ({ provider: p, accepted: ps[`${p}:accepted`] ?? 0, rejected: ps[`${p}:rejected`] ?? 0 })).filter((p) => p.accepted || p.rejected);
  const [inQueue, leasedNow, completed, retired, s, volunteers] = await Promise.all([
    seeded ? store.zcard(K.avail) : Promise.resolve(SEED.rows.length),
    store.zcard(K.leases),
    store.zcard(K.done),
    store.zcard(K.retired),
    store.hgetall(K.stats),
    store.scard(K.volunteers),
  ]);
  const nextZ = seeded ? await store.zrange(K.avail, 0, 19) : SEED.rows.slice(0, 20).map((t, i) => ({ member: t[0], score: i }));
  const states = await store.mget(nextZ.map((z) => K.state(z.member)));
  const next = nextZ.map((z, i) => {
    const d = seedDisease(z.member);
    const st = parse<DiseaseState>(states[i]);
    return {
      id: z.member,
      name: d?.name ?? z.member,
      genes: d?.genes ?? [],
      returning: z.score < 0,
      round: (st?.rounds ?? 0) + 1,
      gaps: st && st.history.length ? st.gaps : null,
      why: d ? whyText(d) : [],
    };
  });
  const boardZ = await store.zrevrange(K.board, 0, 19);
  const handles = await store.mget(boardZ.map((z) => K.handle(z.member)));
  const leaderboard = boardZ.filter((z) => z.score > 0).map((z) => ({ handle: handles[boardZ.indexOf(z)] ?? "volunteer", verified: z.score }));
  const recentZ = await store.zrevrange(K.done, 0, 9);
  const recentlyCompleted = recentZ.map((z) => ({ id: z.member, name: seedDisease(z.member)?.name ?? z.member, at: new Date(z.score).toISOString() }));
  let me = null;
  if (v) {
    const us = await store.hgetall(K.ustats(v.uid));
    const lease = await currentLease(v.uid);
    me = {
      handle: v.handle,
      accepted: us.accepted ?? 0,
      rejected: us.rejected ?? 0,
      duplicates: us.duplicates ?? 0,
      tasks: us.tasks ?? 0,
      lease: lease && lease.expiresAt > Date.now() ? { diseaseId: lease.id, name: seedDisease(lease.id)?.name ?? lease.id, expiresAt: new Date(lease.expiresAt).toISOString() } : null,
    };
  }
  return {
    total: SEED.rows.length,
    inQueue,
    leasedNow,
    completed,
    retired,
    claimsVerified: s.claims_verified ?? 0,
    groupsVerified: s.groups_verified ?? 0,
    rejected: s.rejected ?? 0,
    submissions: s.submissions ?? 0,
    volunteers,
    byProvider,
    next,
    leaderboard,
    recentlyCompleted,
    me,
    leaseHours: LEASE_SECONDS / 3600,
    maxRounds: MAX_ROUNDS,
    checklist: CHECKLIST,
    statusLabel: STATUS_LABEL,
  };
}

export async function diseaseResearch(id: string) {
  const store = kv();
  const [claims, groups, st] = await Promise.all([claimsFor(id), groupsFor(id), getState(id)]);
  const leased = (await store.zscore(K.leases, id)) !== null;
  return {
    id,
    inQueue: !!seedDisease(id),
    status: leased ? "leased" : (st?.status ?? (seedDisease(id) ? "queued" : null)),
    claims,
    groups,
    checklist: computeCoverage(claims, groups),
    rounds: st?.rounds ?? 0,
    statusLabel: STATUS_LABEL,
  };
}

/** Every accepted claim and group (for pipeline/crowd/export; same data the /d/ pages show). */
export async function exportAll() {
  const store = kv();
  const ids = await store.smembers(K.researched);
  const out = [];
  for (const id of ids) {
    const [claims, groups, st] = await Promise.all([claimsFor(id), groupsFor(id), getState(id)]);
    out.push({ id, disease: seedDisease(id) ?? null, claims, groups, state: st });
  }
  return out;
}
