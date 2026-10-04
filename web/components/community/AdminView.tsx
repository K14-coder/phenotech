"use client";

// /admin: the moderation queue for study announcements. The ADMIN_TOKEN is typed here (never stored) and sent
// as a header; nothing is approved without it.
import { useState } from "react";

interface Pending {
  id: string;
  title: string;
  organisation: string;
  summary: string;
  eligibility: string;
  contact: string;
  ethics: string;
  diseases: string[];
  created: string;
}

export function AdminView() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Pending[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const call = async (method: "GET" | "POST", body?: unknown) => {
    const r = await fetch("/api/admin/announcements", {
      method,
      headers: { "x-admin-token": token, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = (await r.json()) as { pending?: Pending[]; error?: string };
    if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
    return j;
  };
  const load = async () => {
    setError(null);
    try {
      setItems((await call("GET")).pending ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const decide = async (id: string, decision: "approved" | "rejected") => {
    try {
      await call("POST", { id, decision });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="mx-auto w-full max-w-[760px] space-y-6 px-4 pb-24 pt-10">
      <h1 className="text-[26px] font-semibold text-ink">Moderation: study announcements</h1>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <input type="password" placeholder="Admin token" value={token} onChange={(e) => setToken(e.target.value)} className="h-11 flex-1 rounded-lg border border-line px-3 text-[15px]" />
        <button type="submit" className="h-11 rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white">
          Load queue
        </button>
      </form>
      {error && (
        <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-warn-ink" role="alert">
          {error}
        </p>
      )}
      {items && !items.length && <p className="text-ink-3">Nothing waiting for review.</p>}
      <ul className="space-y-4">
        {(items ?? []).map((a) => (
          <li key={a.id} className="rounded-xl border border-line px-4 py-4">
            <p className="text-[17px] font-medium text-ink">{a.title}</p>
            <p className="text-sm text-ink-3">
              {a.organisation} · {a.diseases.join(", ")} · {new Date(a.created).toLocaleString()}
            </p>
            <p className="mt-2 whitespace-pre-line text-[15px] text-ink-2">{a.summary}</p>
            <p className="mt-2 text-sm text-ink-2">
              <b>Eligibility:</b> {a.eligibility}
              <br />
              <b>Contact:</b> {a.contact}
              <br />
              <b>Ethics / IRB:</b> {a.ethics}
            </p>
            <div className="mt-3 flex gap-2">
              <button type="button" onClick={() => void decide(a.id, "approved")} className="h-10 rounded-lg bg-accent-700 px-4 text-sm font-medium text-white">
                Approve
              </button>
              <button type="button" onClick={() => void decide(a.id, "rejected")} className="h-10 rounded-lg border border-line px-4 text-sm text-ink-2">
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
