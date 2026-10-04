"use client";

// Published contact details for organisations and recruiting studies, from data/derived/contacts/
// (orgs.json: organisations' general emails and phones from their own websites; trials.json:
// ClinicalTrials.gov central contacts of recruiting studies). Loaded only when web/available.json lists
// them; until then nothing renders. Only organisational channels and study contact points are shown;
// individual researchers are never given a phone or email here.
import { loadAvailableOnce } from "./population";
import { useResource } from "./resource";

export interface ContactPoint {
  phones: { display: string; tel: string }[];
  emails: string[];
  source: "website" | "ctgov";
  url?: string;
  retrieved?: string;
}

/** Slim records written by scripts/sync-data.mjs from data/derived/contacts (names are dropped there). */
interface OrgRec {
  n?: string;
  w?: string | null;
  e?: string[];
  p?: { d: string; t: string | null }[];
  u?: string | null;
  r?: string | null;
}
interface TrialRec {
  e?: string | null;
  p?: { d: string; t: string | null } | null;
  r?: string | null;
}

export interface ContactsIndex {
  byId: Map<string, ContactPoint>;
  byHost: Map<string, ContactPoint>;
  byName: Map<string, ContactPoint>;
  trials: Map<string, ContactPoint>;
}

const host = (u?: string | null) => {
  if (!u) return "";
  try {
    return new URL(u).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
};
const nameKey = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const telOf = (s: string) => s.replace(/(?!^\+)[^\d]/g, "");
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function orgPoint(o: OrgRec): ContactPoint | null {
  const phones = (o.p ?? []).map((x) => ({ display: x.d, tel: telOf(x.t ?? x.d) })).filter((x) => x.tel.replace(/\D/g, "").length >= 6);
  const emails = (o.e ?? []).filter((x) => EMAIL.test(x));
  if (!phones.length && !emails.length) return null;
  return { phones, emails, source: "website", url: o.u ?? undefined, retrieved: o.r ?? undefined };
}

function trialPoint(t: TrialRec, nct: string): ContactPoint | null {
  const phones = t.p ? [{ display: t.p.d, tel: telOf(t.p.t ?? t.p.d) }] : [];
  const emails = t.e && EMAIL.test(t.e) ? [t.e] : [];
  if (!phones.length && !emails.length) return null;
  return { phones, emails, source: "ctgov", url: `https://clinicaltrials.gov/study/${nct}`, retrieved: t.r ?? undefined };
}

async function loadContacts(): Promise<ContactsIndex | null> {
  const a = await loadAvailableOnce();
  if (!a.contacts) return null;
  const [orgs, trials] = await Promise.all(
    ["orgs", "trials"].map((n) =>
      fetch(`/data/derived/contacts/${n}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ),
  );
  const idx: ContactsIndex = { byId: new Map(), byHost: new Map(), byName: new Map(), trials: new Map() };
  for (const [id, o] of Object.entries((orgs?.orgs ?? {}) as Record<string, OrgRec>)) {
    const p = orgPoint(o);
    if (!p) continue;
    idx.byId.set(id, p);
    const h = host(o.w);
    if (h && !idx.byHost.has(h)) idx.byHost.set(h, p);
    if (o.n) idx.byName.set(nameKey(o.n), p);
  }
  for (const [nct, t] of Object.entries((trials?.trials ?? {}) as Record<string, TrialRec>)) {
    const p = trialPoint(t, nct);
    if (p) idx.trials.set(nct, p);
  }
  return idx;
}

export function useContacts(): ContactsIndex | null {
  return useResource<ContactsIndex | null>("contacts", loadContacts)?.data ?? null;
}

export function orgContact(idx: ContactsIndex | null, o: { id?: string; url?: string | null; name?: string }): ContactPoint | null {
  if (!idx) return null;
  return (o.id && idx.byId.get(o.id)) || (host(o.url) && idx.byHost.get(host(o.url))) || (o.name && idx.byName.get(nameKey(o.name))) || null;
}

export function trialContact(idx: ContactsIndex | null, idOrUrl: string): ContactPoint | null {
  if (!idx) return null;
  const nct = idOrUrl.match(/NCT\d{8}/)?.[0];
  return nct ? (idx.trials.get(nct) ?? null) : null;
}
