// Server side of community accounts: users, sessions, rate limits, announcements and relayed messages.
// Passwords: scrypt with a per-user salt. Sessions: an HMAC-signed, httpOnly cookie. Emails are never
// logged and never shown to anyone but their owner.
import { createHmac, randomBytes, scrypt as scryptCb, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { cookies } from "next/headers";
import {
  COUNTRIES,
  DISEASE_ID,
  K_ANON,
  ROLES,
  looksInstitutional,
  type Announcement,
  type InboxMessage,
  type PublicUser,
  type Role,
  type SavedItem,
} from "../community";
import { del, getJson, incrWindow, sadd, setJson, smembers, srem, storeMode } from "./store";

const scrypt = promisify(scryptCb) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;
const COOKIE = "atlas_session";
const SESSION_DAYS = 30;

interface StoredUser extends PublicUser {
  hash: string;
  salt: string;
}

// ---------- helpers ----------

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function jsonError(e: unknown) {
  if (e instanceof HttpError) return Response.json({ error: e.message }, { status: e.status });
  console.error("community route failed:", e instanceof Error ? e.message : "unknown error");
  return Response.json({ error: "Something went wrong. Please try again." }, { status: 500 });
}

function secret(): string {
  const s = process.env.SESSION_SECRET;
  if (s && s.length >= 16) return s;
  if (process.env.VERCEL) throw new HttpError(503, "Sign-up is not configured yet.");
  return "dev-only-session-secret-change-me";
}

export function requireStore() {
  if (storeMode() === "off") throw new HttpError(503, "Sign-up opens soon.");
}

/** Same-origin POSTs only: the Origin header (when present) must match the Host. */
export function assertSameOrigin(req: Request) {
  const origin = req.headers.get("origin");
  if (!origin) return;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    if (new URL(origin).host !== host) throw new HttpError(403, "Cross-site request refused.");
  } catch (e) {
    if (e instanceof HttpError) throw e;
    throw new HttpError(403, "Cross-site request refused.");
  }
}

export async function rateLimit(req: Request, bucket: string, perMinute: number) {
  const ip = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || req.headers.get("x-real-ip") || "local";
  const n = await incrWindow(`rl:${bucket}:${ip}`, 60);
  if (n > perMinute) throw new HttpError(429, "Too many attempts. Please wait a minute and try again.");
}

export async function readBody(req: Request, max = 20_000): Promise<Record<string, unknown>> {
  if (!(req.headers.get("content-type") ?? "").includes("application/json")) throw new HttpError(415, "Send JSON.");
  const text = await req.text();
  if (text.length > max) throw new HttpError(413, "Too large.");
  try {
    const v = JSON.parse(text);
    if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("not an object");
    return v as Record<string, unknown>;
  } catch {
    throw new HttpError(400, "Invalid JSON.");
  }
}

const str = (v: unknown, max: number, field: string, required = true): string => {
  const s = typeof v === "string" ? v.trim() : "";
  if (required && !s) throw new HttpError(400, `${field} is required.`);
  if (s.length > max) throw new HttpError(400, `${field} is too long.`);
  return s;
};
const bool = (v: unknown) => v === true;
const diseasesOf = (v: unknown): string[] => {
  const list = Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && DISEASE_ID.test(x)) : [];
  return [...new Set(list)].slice(0, 20);
};
const countryOf = (v: unknown): string | null => (typeof v === "string" && COUNTRIES.includes(v) ? v : null);
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,24}$/i;

const newId = () => randomBytes(12).toString("base64url");

function publicUser(u: StoredUser): PublicUser {
  return { id: u.id, email: u.email, role: u.role, diseases: u.diseases, country: u.country, consent: u.consent, verified: u.verified, created: u.created, saved: u.saved };
}

// ---------- sessions ----------

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

async function setSession(uid: string) {
  const exp = Date.now() + SESSION_DAYS * 86400_000;
  const payload = Buffer.from(JSON.stringify({ uid, exp })).toString("base64url");
  (await cookies()).set(COOKIE, `${payload}.${sign(payload)}`, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 86400,
  });
}

export async function clearSession() {
  (await cookies()).delete(COOKIE);
}

export async function currentUser(): Promise<StoredUser | null> {
  if (storeMode() === "off") return null;
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  const [payload, mac] = raw.split(".");
  if (!payload || !mac) return null;
  const good = Buffer.from(sign(payload));
  const got = Buffer.from(mac);
  if (good.length !== got.length || !timingSafeEqual(good, got)) return null;
  try {
    const { uid, exp } = JSON.parse(Buffer.from(payload, "base64url").toString()) as { uid: string; exp: number };
    if (!uid || exp < Date.now()) return null;
    return await getJson<StoredUser>(`user:${uid}`);
  } catch {
    return null;
  }
}

export async function requireUser(): Promise<StoredUser> {
  const u = await currentUser();
  if (!u) throw new HttpError(401, "Please sign in.");
  return u;
}

// ---------- accounts ----------

async function hashPassword(pw: string, salt?: Buffer) {
  const s = salt ?? randomBytes(16);
  const h = await scrypt(pw, s, 64);
  return { hash: h.toString("base64"), salt: s.toString("base64") };
}

export async function signup(body: Record<string, unknown>): Promise<PublicUser> {
  const email = str(body.email, 254, "Email").toLowerCase();
  if (!EMAIL.test(email)) throw new HttpError(400, "Please enter a valid email address.");
  const password = typeof body.password === "string" ? body.password : "";
  if (password.length < 10 || password.length > 200) throw new HttpError(400, "Use a password of at least 10 characters.");
  const role = ROLES.some((r) => r.id === body.role) ? (body.role as Role) : null;
  if (!role) throw new HttpError(400, "Please choose who you are.");
  if (await getJson<string>(`email:${email}`)) throw new HttpError(409, "An account with this email already exists. Try signing in.");
  const { hash, salt } = await hashPassword(password);
  const user: StoredUser = {
    id: newId(),
    email,
    role,
    diseases: diseasesOf(body.diseases),
    country: countryOf(body.country),
    consent: { trials: bool(body.consentTrials), researcherContact: bool(body.consentContact), weeklyDigest: bool(body.weeklyDigest), groupForms: bool(body.groupForms) },
    verified: role === "researcher" ? looksInstitutional(email) : true,
    created: new Date().toISOString(),
    saved: [],
    hash,
    salt,
  };
  await setJson(`user:${user.id}`, user);
  await setJson(`email:${email}`, user.id);
  await sadd("users", user.id);
  for (const d of user.diseases) await sadd(`follow:${d}`, user.id);
  await setSession(user.id);
  return publicUser(user);
}

export async function login(body: Record<string, unknown>): Promise<PublicUser> {
  const email = str(body.email, 254, "Email").toLowerCase();
  const password = typeof body.password === "string" ? body.password : "";
  const uid = await getJson<string>(`email:${email}`);
  const u = uid ? await getJson<StoredUser>(`user:${uid}`) : null;
  // same message and similar work whether or not the account exists
  const { hash } = await hashPassword(password, u ? Buffer.from(u.salt, "base64") : randomBytes(16));
  if (!u || !timingSafeEqual(Buffer.from(hash), Buffer.from(u.hash))) throw new HttpError(401, "Email or password is not right.");
  await setSession(u.id);
  return publicUser(u);
}

export async function updateMe(u: StoredUser, body: Record<string, unknown>): Promise<PublicUser> {
  const next: StoredUser = { ...u, consent: { ...u.consent } };
  if ("diseases" in body) {
    const d = diseasesOf(body.diseases);
    for (const x of u.diseases.filter((x) => !d.includes(x))) await srem(`follow:${x}`, u.id);
    for (const x of d.filter((x) => !u.diseases.includes(x))) await sadd(`follow:${x}`, u.id);
    next.diseases = d;
  }
  if ("country" in body) next.country = countryOf(body.country);
  if (body.consent && typeof body.consent === "object") {
    const c = body.consent as Record<string, unknown>;
    for (const k of ["trials", "researcherContact", "weeklyDigest", "groupForms"] as const) if (k in c) next.consent[k] = bool(c[k]);
  }
  if (body.save && typeof body.save === "object") {
    const s = body.save as Record<string, unknown>;
    const item: SavedItem = {
      kind: s.kind === "questions" || s.kind === "printout" ? s.kind : "page",
      title: str(s.title, 200, "Title"),
      href: str(s.href, 300, "Link"),
      at: new Date().toISOString(),
    };
    if (!item.href.startsWith("/")) throw new HttpError(400, "Only atlas links can be saved.");
    next.saved = [item, ...u.saved.filter((x) => x.href !== item.href)].slice(0, 50);
  }
  if (typeof body.unsave === "string") next.saved = u.saved.filter((x) => x.href !== body.unsave);
  await setJson(`user:${u.id}`, next);
  return publicUser(next);
}

/** Really deletes: the user record, the email index, follow memberships and the inbox. */
export async function deleteMe(u: StoredUser) {
  for (const d of u.diseases) await srem(`follow:${d}`, u.id);
  await srem("users", u.id);
  const inbox = await smembers(`inbox:${u.id}`);
  // published announcements stay (they are reviewed public study notices) but are no longer linked to this account
  await del(`user:${u.id}`, `email:${u.email}`, `inbox:${u.id}`, `anns:by:${u.id}`, ...inbox.map((m) => `msg:${u.id}:${m}`));
  await clearSession();
}

export async function exportMe(u: StoredUser) {
  return { account: publicUser(u), inbox: await inboxFor(u), exported: new Date().toISOString() };
}

// ---------- inbox ----------

export async function inboxFor(u: StoredUser): Promise<InboxMessage[]> {
  const out: InboxMessage[] = [];
  for (const id of await smembers("anns:approved")) {
    const a = await getJson<Announcement>(`ann:${id}`);
    if (!a || !a.diseases.some((d) => u.diseases.includes(d))) continue;
    out.push({
      id: `ann-${a.id}`,
      kind: "announcement",
      diseases: a.diseases.filter((d) => u.diseases.includes(d)),
      title: a.title,
      body: a.summary,
      created: a.created,
      extra: { organisation: a.organisation, eligibility: a.eligibility, contact: a.contact, ethics: a.ethics },
    });
  }
  for (const id of await smembers(`inbox:${u.id}`)) {
    const m = await getJson<InboxMessage>(`msg:${u.id}:${id}`);
    if (m) out.push(m);
  }
  return out.sort((a, b) => b.created.localeCompare(a.created));
}

// ---------- researchers ----------

function requireResearcher(u: StoredUser) {
  if (u.role !== "researcher" && u.role !== "industry") throw new HttpError(403, "Only researcher accounts can do this.");
}

export async function announce(u: StoredUser, body: Record<string, unknown>): Promise<Announcement> {
  requireResearcher(u);
  const diseases = diseasesOf(body.diseases);
  if (!diseases.length) throw new HttpError(400, "Choose at least one disease.");
  const a: Announcement = {
    id: newId(),
    diseases,
    title: str(body.title, 160, "Title"),
    summary: str(body.summary, 1500, "Plain-language summary"),
    eligibility: str(body.eligibility, 800, "Eligibility"),
    contact: str(body.contact, 300, "Contact"),
    ethics: str(body.ethics, 200, "Ethics / IRB reference"),
    organisation: str(body.organisation, 160, "Organisation"),
    status: "pending",
    created: new Date().toISOString(),
  };
  await setJson(`ann:${a.id}`, { ...a, by: u.id });
  await sadd("anns:pending", a.id);
  await sadd(`anns:by:${u.id}`, a.id);
  return a;
}

export async function myAnnouncements(u: StoredUser): Promise<Announcement[]> {
  const ids = await smembers(`anns:by:${u.id}`);
  const list = await Promise.all(ids.map((id) => getJson<Announcement>(`ann:${id}`)));
  return list.filter((a): a is Announcement => !!a).sort((a, b) => b.created.localeCompare(a.created));
}

/** Members following each disease, by coarse country; any cell below K_ANON is withheld. */
export async function communityInterest(u: StoredUser, diseases: string[]) {
  requireResearcher(u);
  const out: { disease: string; total: number | null; byCountry: { country: string; n: number }[]; withheld: boolean }[] = [];
  for (const d of diseases.filter((x) => DISEASE_ID.test(x)).slice(0, 50)) {
    const ids = await smembers(`follow:${d}`);
    if (ids.length < K_ANON) {
      out.push({ disease: d, total: null, byCountry: [], withheld: true });
      continue;
    }
    const counts = new Map<string, number>();
    for (const id of ids) {
      const m = await getJson<StoredUser>(`user:${id}`);
      const c = m?.country ?? "Not given";
      counts.set(c, (counts.get(c) ?? 0) + 1);
    }
    const byCountry = [...counts].filter(([, n]) => n >= K_ANON).map(([country, n]) => ({ country, n })).sort((a, b) => b.n - a.n);
    out.push({ disease: d, total: ids.length, byCountry, withheld: byCountry.reduce((s, x) => s + x.n, 0) < ids.length });
  }
  return out;
}

/** Relays a message to followers who opted in to researcher contact. The sender never sees who. */
export async function requestContact(u: StoredUser, body: Record<string, unknown>) {
  requireResearcher(u);
  const disease = diseasesOf([body.disease])[0];
  if (!disease) throw new HttpError(400, "Choose a disease.");
  const msg = str(body.message, 1500, "Message");
  const organisation = str(body.organisation, 160, "Organisation");
  const ids = await smembers(`follow:${disease}`);
  let delivered = 0;
  for (const id of ids) {
    const m = await getJson<StoredUser>(`user:${id}`);
    if (!m?.consent.researcherContact || m.id === u.id) continue;
    const mid = newId();
    const im: InboxMessage = {
      id: `msg-${mid}`,
      kind: "contact",
      diseases: [disease],
      title: `A researcher at ${organisation} would like to hear from families`,
      body: msg,
      created: new Date().toISOString(),
      extra: { verified: u.verified ? "Institutional email" : "Unverified researcher account" },
    };
    await setJson(`msg:${m.id}:${im.id}`, im);
    await sadd(`inbox:${m.id}`, im.id);
    delivered++;
  }
  // exact small numbers would reveal individuals
  return { delivered: delivered >= K_ANON ? delivered : null, note: delivered >= K_ANON ? null : "Delivered to members who opted in (fewer than 5, so the number is not shown)." };
}

// ---------- admin ----------

export function requireAdmin(req: Request) {
  const t = process.env.ADMIN_TOKEN;
  const got = req.headers.get("x-admin-token") ?? "";
  if (!t || t.length < 12) throw new HttpError(503, "Moderation is not configured (set ADMIN_TOKEN).");
  const a = Buffer.from(t);
  const b = Buffer.from(got);
  if (a.length !== b.length || !timingSafeEqual(a, b)) throw new HttpError(401, "Wrong admin token.");
}

export async function pendingAnnouncements(): Promise<Announcement[]> {
  const ids = await smembers("anns:pending");
  const list = await Promise.all(ids.map((id) => getJson<Announcement & { by?: string }>(`ann:${id}`)));
  return list.filter((a): a is Announcement => !!a).map(({ ...a }) => {
    delete (a as { by?: string }).by;
    return a;
  });
}

export async function moderate(id: string, decision: "approved" | "rejected") {
  const a = await getJson<Announcement & { by?: string }>(`ann:${id}`);
  if (!a) throw new HttpError(404, "Not found.");
  await setJson(`ann:${id}`, { ...a, status: decision });
  await srem("anns:pending", id);
  if (decision === "approved") await sadd("anns:approved", id);
}
