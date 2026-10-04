// Daily job behind /api/cron/digest. For the diseases members follow it looks for news LIVE:
//  - ClinicalTrials.gov API v2: recruiting / not-yet-recruiting studies (name, synonyms or gene, with the
//    precision filter of data/derived/scale/README.md; see live.ts);
//  - NIH RePORTER: projects funded this or last fiscal year on the disease's genes ("new researchers").
// Each disease keeps a seen-set per source (alerts:seen:<source>:<d>); the first check of a disease only
// seeds it, silently. Anything not seen before becomes an inbox notice for every follower, and an email
// for followers who asked for study news (now, or in their weekly summary with queued announcements).
// sent:<uid> records what was emailed, so nothing is sent twice.
// Limits: at most ALERTS_MAX_REQUESTS live requests per run (default 40, two per disease) and a 40 s time
// budget; diseases are processed in a rotating order with a cursor (alerts:cursor), so a long list is
// covered across runs. Logs and returns counts only, never addresses.
import { type PendingNotice, type StoredUser, canEmail, nameOf, queueNotice, unsubscribeUrl } from "./community";
import { sendEmail, trialsEmail } from "./email";
import { type LiveItem, liveGrants, liveTrials, loadProfiles } from "./live";
import { getJson, sadd, setJson, smembers } from "./store";
import type { InboxMessage } from "@/lib/community";

const WEEK = 7 * 24 * 3600_000;
const BUDGET_MS = 40_000;

export interface DigestResult {
  members: number;
  diseases: number;
  checked: number;
  seeded: number;
  requests: number;
  failedRequests: number;
  newTrials: number;
  newGrants: number;
  inboxNotices: number;
  emailsSent: number;
  queued: number;
  digestsSent: number;
  cursor: number;
}

export interface DigestDeps {
  trials?: typeof liveTrials;
  grants?: typeof liveGrants;
}

export async function runDigest(base: string, now = Date.now(), deps: DigestDeps = {}): Promise<DigestResult> {
  const started = Date.now();
  const trials = deps.trials ?? liveTrials;
  const grants = deps.grants ?? liveGrants;
  const maxRequests = Math.max(2, Math.min(200, Number(process.env.ALERTS_MAX_REQUESTS) || 40));
  const res: DigestResult = { members: 0, diseases: 0, checked: 0, seeded: 0, requests: 0, failedRequests: 0, newTrials: 0, newGrants: 0, inboxNotices: 0, emailsSent: 0, queued: 0, digestsSent: 0, cursor: 0 };

  const members: StoredUser[] = [];
  for (const uid of await smembers("users")) {
    const u = await getJson<StoredUser>(`user:${uid}`);
    if (u) members.push(u);
  }
  res.members = members.length;
  const followed = [...new Set(members.flatMap((m) => m.diseases))].sort();
  res.diseases = followed.length;

  // 1. this run's slice of diseases, from the cursor
  const start = followed.length ? ((await getJson<number>("alerts:cursor")) ?? 0) % followed.length : 0;
  const order = [...followed.slice(start), ...followed.slice(0, start)];
  const slice = order.slice(0, Math.floor(maxRequests / 2));
  const profiles = await loadProfiles(slice, base);
  const fresh = new Map<string, LiveItem[]>();
  let done = 0;
  for (let i = 0; i < slice.length; i += 4) {
    if (Date.now() - started > BUDGET_MS) break;
    await Promise.all(
      slice.slice(i, i + 4).map(async (d) => {
        const p = profiles.get(d);
        if (!p) return;
        const [t, g] = await Promise.all([trials(p), grants(p, new Date(now))]);
        res.requests += (p.terms.length || p.genes.length ? 1 : 0) + (p.genes.length ? 1 : 0);
        for (const [src, list] of [["trials", t], ["grants", g]] as const) {
          if (list === null) {
            res.failedRequests++;
            continue; // try again next time; never seed from a failed request
          }
          const key = `alerts:seen:${src}:${d}`;
          const seen = await getJson<string[]>(key);
          if (!seen) res.seeded++;
          else {
            const s = new Set(seen);
            const add = list.filter((x) => !s.has(x.key));
            if (add.length) fresh.set(d, [...(fresh.get(d) ?? []), ...add]);
            if (src === "trials") res.newTrials += add.length;
            else res.newGrants += add.length;
          }
          await setJson(key, [...new Set([...(seen ?? []), ...list.map((x) => x.key)])].slice(-2000));
        }
        res.checked++;
      }),
    );
    done = Math.min(slice.length, i + 4);
  }
  res.cursor = followed.length ? (start + done) % followed.length : 0;
  await setJson("alerts:cursor", res.cursor);

  // 2. per member: inbox notices, then email now or queue for the weekly summary
  for (const m of members) {
    const sent = new Set(await smembers(`sent:${m.id}`));
    const items: PendingNotice[] = [];
    for (const d of m.diseases)
      for (const x of fresh.get(d) ?? []) {
        if (items.some((i) => i.key === x.key)) continue;
        const label = nameOf(m, d);
        items.push({ key: x.key, disease: x.kind === "grant" ? `New research · ${label}` : label, title: x.title, url: x.url, meta: x.meta });
        const msg: InboxMessage = {
          id: `alert-${x.key}`,
          kind: x.kind,
          diseases: [d],
          title: x.title,
          body: x.kind === "grant" ? `New research on ${label}: ${x.meta}.` : `A study for ${label} is recruiting or will start soon: ${x.meta}.`,
          created: new Date(now).toISOString(),
          url: x.url,
        };
        await setJson(`msg:${m.id}:${msg.id}`, msg);
        await sadd(`inbox:${m.id}`, msg.id);
        res.inboxNotices++;
      }
    if (!canEmail(m) || !m.consent.trials) continue; // inbox only: unconfirmed, unsubscribed or not asked
    const toSend = items.filter((i) => !sent.has(i.key));
    if (m.consent.weeklyDigest) {
      for (const i of toSend) await queueNotice(m, i);
      res.queued += toSend.length;
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
    } else if (toSend.length) {
      await sendEmail(trialsEmail(m.email, toSend, false, `${base}/me`, unsubscribeUrl(m, base)));
      for (const i of toSend) await sadd(`sent:${m.id}`, i.key);
      res.emailsSent++;
    }
  }
  await setJson("cron:lastRun", { at: new Date(now).toISOString(), ...res });
  console.info(`cron digest: ${JSON.stringify(res)}`);
  return res;
}
