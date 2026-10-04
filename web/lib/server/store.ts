// Tiny storage adapter for community accounts.
//  - Upstash Redis over REST (UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, set by Vercel's
//    Upstash/KV integration; KV_REST_API_URL/TOKEN accepted too). Plain fetch, no SDK.
//  - Otherwise, off Vercel: a JSON file in web/.data/ (gitignored) for local development.
//  - On Vercel without Redis: "off" (the UI says "Sign-up opens soon").
// Values are JSON. Sets hold ids. Never log emails.
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export type StoreMode = "redis" | "file" | "off";

const REDIS_URL = process.env.UPSTASH_REDIS_REST_URL ?? process.env.KV_REST_API_URL;
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN ?? process.env.KV_REST_API_TOKEN;

/**
 * On Vercel: Redis when its env vars exist, else off. Locally: the JSON file store by default, so tests
 * never touch the production database (web/.env.local carries the Vercel KV vars); STORE=redis opts in.
 */
export function storeMode(): StoreMode {
  const haveRedis = !!(REDIS_URL && REDIS_TOKEN);
  if (process.env.VERCEL) return haveRedis ? "redis" : "off";
  if (process.env.STORE === "redis" && haveRedis) return "redis";
  return "file";
}

// ---------- Redis over REST ----------

async function redis<T = unknown>(...cmd: (string | number)[]): Promise<T> {
  const r = await fetch(REDIS_URL!, {
    method: "POST",
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(cmd.map(String)),
    cache: "no-store",
  });
  const j = (await r.json()) as { result?: T; error?: string };
  if (!r.ok || j.error) throw new Error(`store: ${j.error ?? r.status}`);
  return j.result as T;
}

// ---------- JSON file ----------

interface FileDb {
  kv: Record<string, { v: string; exp?: number }>;
  sets: Record<string, string[]>;
}
const FILE = path.join(process.cwd(), ".data", "store.json");
let queue: Promise<unknown> = Promise.resolve();

async function readDb(): Promise<FileDb> {
  try {
    return JSON.parse(await readFile(FILE, "utf8")) as FileDb;
  } catch {
    return { kv: {}, sets: {} };
  }
}

/** Serialises file access inside this process (good enough for local development). */
function withDb<T>(fn: (db: FileDb) => T | Promise<T>, write: boolean): Promise<T> {
  const run = queue.then(async () => {
    const db = await readDb();
    const out = await fn(db);
    if (write) {
      await mkdir(path.dirname(FILE), { recursive: true });
      const tmp = `${FILE}.${process.pid}.tmp`;
      await writeFile(tmp, JSON.stringify(db));
      await rename(tmp, FILE);
    }
    return out;
  });
  queue = run.catch(() => undefined);
  return run;
}

const live = (e?: { v: string; exp?: number }) => (e && (!e.exp || e.exp > Date.now()) ? e : undefined);

// ---------- API ----------

export async function getJson<T>(key: string): Promise<T | null> {
  if (storeMode() === "redis") {
    const v = await redis<string | null>("GET", key);
    return v ? (JSON.parse(v) as T) : null;
  }
  return withDb((db) => {
    const e = live(db.kv[key]);
    return e ? (JSON.parse(e.v) as T) : null;
  }, false);
}

export async function setJson(key: string, value: unknown): Promise<void> {
  const v = JSON.stringify(value);
  if (storeMode() === "redis") {
    await redis("SET", key, v);
    return;
  }
  await withDb((db) => {
    db.kv[key] = { v };
  }, true);
}

export async function del(...keys: string[]): Promise<void> {
  if (!keys.length) return;
  if (storeMode() === "redis") {
    await redis("DEL", ...keys);
    return;
  }
  await withDb((db) => {
    for (const k of keys) {
      delete db.kv[k];
      delete db.sets[k];
    }
  }, true);
}

/** Counter with a time window (rate limiting). Returns the new value. */
export async function incrWindow(key: string, seconds: number): Promise<number> {
  if (storeMode() === "redis") {
    const n = await redis<number>("INCR", key);
    if (n === 1) await redis("EXPIRE", key, seconds);
    return n;
  }
  return withDb((db) => {
    const e = live(db.kv[key]);
    const n = (e ? Number(e.v) : 0) + 1;
    db.kv[key] = { v: String(n), exp: e?.exp ?? Date.now() + seconds * 1000 };
    return n;
  }, true);
}

export async function sadd(key: string, member: string): Promise<void> {
  if (storeMode() === "redis") {
    await redis("SADD", key, member);
    return;
  }
  await withDb((db) => {
    const s = new Set(db.sets[key] ?? []);
    s.add(member);
    db.sets[key] = [...s];
  }, true);
}

export async function srem(key: string, member: string): Promise<void> {
  if (storeMode() === "redis") {
    await redis("SREM", key, member);
    return;
  }
  await withDb((db) => {
    db.sets[key] = (db.sets[key] ?? []).filter((m) => m !== member);
    if (!db.sets[key].length) delete db.sets[key];
  }, true);
}

export async function smembers(key: string): Promise<string[]> {
  if (storeMode() === "redis") return (await redis<string[]>("SMEMBERS", key)) ?? [];
  return withDb((db) => [...(db.sets[key] ?? [])], false);
}
