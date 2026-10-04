// "Report or remove a contact": requests from the public about a phone, email or named contact person shown on
// Phenotech. They go into the admin moderation queue (reports:pending); nothing is changed automatically.
import { HttpError } from "./community";
import { getJson, sadd, setJson, smembers, srem } from "./store";
import { randomBytes } from "node:crypto";

export interface ContactReport {
  id: string;
  /** what is shown, e.g. the organisation name or the page */
  about: string;
  kind: "wrong" | "remove" | "other";
  message: string;
  /** optional, so we can reply; never shown anywhere else */
  replyTo: string | null;
  page: string | null;
  created: string;
  status: "pending" | "resolved";
}

const clean = (v: unknown, max: number) => (typeof v === "string" ? v.replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max) : "");
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function fileReport(body: Record<string, unknown>): Promise<{ ok: true }> {
  const about = clean(body.about, 200);
  const message = clean(body.message, 2000);
  const kind = body.kind === "wrong" || body.kind === "remove" ? body.kind : "other";
  const replyTo = clean(body.replyTo, 254);
  if (!about) throw new HttpError(400, "Please say which organisation or contact this is about.");
  if (message.length < 5) throw new HttpError(400, "Please add a short note so we know what to change.");
  if (replyTo && !EMAIL.test(replyTo)) throw new HttpError(400, "That email address doesn’t look right (you can also leave it empty).");
  const page = clean(body.page, 300);
  const r: ContactReport = {
    id: randomBytes(8).toString("base64url"),
    about,
    kind,
    message,
    replyTo: replyTo || null,
    page: page.startsWith("/") ? page : null,
    created: new Date().toISOString(),
    status: "pending",
  };
  await setJson(`report:${r.id}`, r);
  await sadd("reports:pending", r.id);
  return { ok: true };
}

export async function pendingReports(): Promise<ContactReport[]> {
  const out: ContactReport[] = [];
  for (const id of await smembers("reports:pending")) {
    const r = await getJson<ContactReport>(`report:${id}`);
    if (r) out.push(r);
  }
  return out.sort((a, b) => b.created.localeCompare(a.created));
}

export async function resolveReport(id: string) {
  const r = await getJson<ContactReport>(`report:${id}`);
  if (!r) throw new HttpError(404, "Not found.");
  await setJson(`report:${id}`, { ...r, status: "resolved" });
  await srem("reports:pending", id);
}
