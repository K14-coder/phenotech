// Browser side of community accounts: one cached GET /api/account, refreshed after every change.
import type { Announcement, InboxMessage, PublicUser } from "./community";
import { retry } from "./resource";

export interface AccountState {
  mode: "redis" | "file" | "off";
  /** "disabled" when the site sends no email (no Resend key); notices then appear only on /me */
  emailMode?: "dry-run" | "resend" | "disabled";
  user: PublicUser | null;
  inbox?: InboxMessage[];
  announcements?: Announcement[];
}

export const ACCOUNT_KEY = "account";

export async function loadAccount(): Promise<AccountState> {
  const r = await fetch("/api/account", { cache: "no-store" });
  if (r.status === 404) return { mode: "off", user: null };
  const j = (await r.json()) as AccountState & { error?: string };
  if (!r.ok) return { mode: "off", user: null };
  return j;
}

export function refreshAccount() {
  retry(ACCOUNT_KEY, loadAccount);
}

/** JSON call to an account route; throws the server's plain-language message on failure. */
export async function api<T = unknown>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = (await r.json().catch(() => ({}))) as T & { error?: string };
  if (!r.ok) throw new Error(j.error ?? `Request failed (${r.status})`);
  return j;
}
