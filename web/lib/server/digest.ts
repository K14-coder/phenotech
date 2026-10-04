// Daily job behind /api/cron/digest: finds studies that newly appear as recruiting for each followed
// disease (from the synced data: population/channels.json for atlas diseases, web/scale shards for the
// global index), then
//  - members who chose single notices get one email with what is new for them;
//  - members who chose a weekly summary get it queued, and sent once seven days have passed,
//    together with queued study announcements.
// Every disease keeps a baseline of studies already known (trials:known:<d>); the first run for a
// disease only records the baseline, so nobody gets a flood of old studies. Per member, sent:<uid>
// records what was emailed, so a study is never sent twice. Returns counts only, never addresses.
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { ChannelsFile, ScaleEntry } from "@/lib/population";
import { type PendingNotice, type StoredUser, canEmail, nameOf, queueNotice, unsubscribeUrl } from "./community";
import { sendEmail, trialsEmail } from "./email";
import { getJson, sadd, setJson, smembers } from "./store";

/** djb2(id) % 64, as for every shard folder (lib/global.ts is client-side, so it is repeated here) */
function bucketOf(id: string): number {
  let h = 5381;
  for (let i = 0; i < id.length; i++) h = (Math.imul(h, 33) + id.charCodeAt(i)) >>> 0;
  return h % 64;
}

const OPEN = ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"];
const WEEK = 7 * 24 * 3600_000;
const status = (s?: string) => (s ?? "").toLowerCase().replace(/_/g, " ");

async function publicJson<T>(rel: string, base: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(process.cwd(), "public", rel), "utf8")) as T;
  } catch {
    // on Vercel the public folder is served by the CDN, not bundled with the function
    try {
      const r = await fetch(`${base}/${rel}`, { cache: "no-store" });
      return r.ok ? ((await r.json()) as T) : null;
    } catch {
      return null;
    }
  }
}

interface Study {
  id: string;
  title: string;
  url: string;
  meta: string;
}

/** Open studies for each disease id, from the synced data. */
async function openStudies(diseases: string[], base: string): Promise<Map<string, Study[]>> {
  const out = new Map<string, Study[]>();
  const channels = diseases.some((d) => d.startsWith("disease:")) ? await publicJson<ChannelsFile>("data/derived/population/channels.json", base) : null;
  const byId = new Map((channels?.channels ?? []).map((c) => [c.id, c]));
  const shards = new Map<number, Record<string, ScaleEntry> | null>();
  for (const d of diseases) {
    const list: Study[] = [];
    if (d.startsWith("disease:")) {
      for (const id of channels?.by_disease[d]?.recruiting_trial ?? []) {
        const c = byId.get(id);
        if (c && (!c.status || OPEN.includes(c.status))) list.push({ id: id.replace(/^study:/, ""), title: c.name, url: c.url ?? "", meta: [status(c.status), c.sponsor].filter(Boolean).join(" · ") });
      }
    }
    // global ids, and atlas ids that also have scale entries
    const b = bucketOf(d);
    if (!shards.has(b)) shards.set(b, (await publicJson<{ d: Record<string, ScaleEntry> }>(`data/derived/web/scale/${b}.json`, base))?.d ?? null);
    for (const s of shards.get(b)?.[d]?.studies ?? [])
      if (OPEN.includes(s.st) && !list.some((x) => x.id === s.id)) list.push({ id: s.id, title: s.t, url: s.u, meta: [status(s.st), s.sp].filter(Boolean).join(" · ") });
    out.set(d, list.filter((s) => s.url));
  }
  return out;
}

export interface DigestResult {
  members: number;
  diseases: number;
  newStudies: number;
  baselined: number;
  emailsSent: number;
  queued: number;
  digestsSent: number;
}

export async function runDigest(base: string, now = Date.now()): Promise<DigestResult> {
  const res: DigestResult = { members: 0, diseases: 0, newStudies: 0, baselined: 0, emailsSent: 0, queued: 0, digestsSent: 0 };
  const members: StoredUser[] = [];
  for (const uid of await smembers("users")) {
    const u = await getJson<StoredUser>(`user:${uid}`);
    if (u) members.push(u);
  }
  res.members = members.length;
  const followed = [...new Set(members.flatMap((m) => m.diseases))];
  res.diseases = followed.length;

  // 1. what is new per disease since the last run
  const studies = await openStudies(followed, base);
  const fresh = new Map<string, Study[]>();
  for (const d of followed) {
    const current = studies.get(d) ?? [];
    const known = await getJson<string[]>(`trials:known:${d}`);
    if (known) {
      const seen = new Set(known);
      const add = current.filter((s) => !seen.has(s.id));
      if (add.length) fresh.set(d, add);
      res.newStudies += add.length;
    } else res.baselined++;
    await setJson(`trials:known:${d}`, [...new Set([...(known ?? []), ...current.map((s) => s.id)])]);
  }

  // 2. per member: send now, or queue for the weekly summary
  for (const m of members) {
    const sent = new Set(await smembers(`sent:${m.id}`));
    const items: PendingNotice[] = [];
    if (m.consent.trials)
      for (const d of m.diseases)
        for (const s of fresh.get(d) ?? []) {
          const key = `trial-${s.id}`;
          if (!sent.has(key) && !items.some((i) => i.key === key)) items.push({ key, disease: nameOf(m, d), title: s.title, url: s.url, meta: s.meta });
        }
    if (!canEmail(m)) continue; // unconfirmed or unsubscribed: notices stay in the inbox on /me
    if (m.consent.weeklyDigest) {
      for (const i of items) await queueNotice(m, i);
      res.queued += items.length;
      const last = Date.parse(m.lastDigest ?? m.created);
      if (now - last < WEEK) continue;
      const pending = ((await getJson<PendingNotice[]>(`pending:${m.id}`)) ?? []).filter((i) => !sent.has(i.key));
      if (pending.length) {
        await sendEmail(trialsEmail(m.email, pending, true, `${base}/me`, unsubscribeUrl(m, base)));
        for (const i of pending) await sadd(`sent:${m.id}`, i.key);
        res.digestsSent++;
      }
      await setJson(`pending:${m.id}`, []);
      const fresher = await getJson<StoredUser>(`user:${m.id}`);
      if (fresher) await setJson(`user:${m.id}`, { ...fresher, lastDigest: new Date(now).toISOString() });
    } else if (items.length) {
      await sendEmail(trialsEmail(m.email, items, false, `${base}/me`, unsubscribeUrl(m, base)));
      for (const i of items) await sadd(`sent:${m.id}`, i.key);
      res.emailsSent++;
    }
  }
  await setJson("cron:lastRun", { at: new Date(now).toISOString(), ...res });
  return res;
}
