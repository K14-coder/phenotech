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

interface EmailStatus {
  mode: "dry-run" | "smtp" | "resend" | "disabled";
  domainVerified: boolean;
}

const EMAIL_NOTE: Record<EmailStatus["mode"], string> = {
  "dry-run": "Email is in dry-run mode: messages are written to .data/outbox/ on the server, not sent.",
  disabled: "Email is switched off (RESEND_API_KEY and EMAIL_FROM are not set). Notices appear only in members’ inboxes on My atlas.",
  resend: "Email is sent through Resend.",
  smtp: "Email is sent through the mailbox’s own SMTP server.",
};

function TestEmail({ token }: { token: string }) {
  const [state, setState] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3 text-[15px]">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setState(null);
          try {
            const r = await fetch("/api/admin/test-email", { method: "POST", headers: { "x-admin-token": token, "Content-Type": "application/json" }, body: "{}" });
            const j = (await r.json()) as { transport?: string; sent?: boolean; error?: string | null };
            setState(r.ok ? `Transport: ${j.transport}. ${j.sent ? "Sent to your own address." : `Not sent (${j.error ?? "unknown"}).`}` : (j.error ?? `HTTP ${r.status}`));
          } catch (e) {
            setState(e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
        className="h-10 rounded-lg border border-line px-4 text-sm text-ink-2 hover:border-accent-500 disabled:opacity-50"
      >
        {busy ? "Sending…" : "Send a test email to myself"}
      </button>
      {state && (
        <span className="text-sm text-ink-2" role="status">
          {state}
        </span>
      )}
      <span className="w-full text-xs text-ink-3">Goes to the address of the account you are signed in with on this browser.</span>
    </div>
  );
}

export function AdminView() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Pending[] | null>(null);
  const [email, setEmail] = useState<EmailStatus | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const call = async (method: "GET" | "POST", body?: unknown) => {
    const r = await fetch("/api/admin/announcements", {
      method,
      headers: { "x-admin-token": token, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = (await r.json()) as { pending?: Pending[]; email?: EmailStatus; emailed?: number; queued?: number; error?: string };
    if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
    return j;
  };
  const load = async () => {
    setError(null);
    try {
      const j = await call("GET");
      setItems(j.pending ?? []);
      setEmail(j.email ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const decide = async (id: string, decision: "approved" | "rejected") => {
    try {
      const j = await call("POST", { id, decision });
      setNote(decision === "approved" ? `Approved. Emailed ${j.emailed ?? 0} member(s) now; ${j.queued ?? 0} will get it in their weekly summary.` : "Rejected.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="mx-auto w-full max-w-[760px] space-y-6 px-4 pb-24 pt-10">
      <h1 className="text-[26px] font-semibold text-ink">Moderation: study announcements</h1>
      <p className="text-sm">
        <a href="/admin/emails" className="text-accent-700 hover:underline">
          Email previews →
        </a>
      </p>
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
      {email && (
        <div className="space-y-2 text-[15px]">
          {!email.domainVerified && (
            <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-warn-ink" role="status">
              <b>Email delivery is in test mode.</b> Until the sending domain is verified in Resend (then set EMAIL_DOMAIN_VERIFIED=1), Resend only delivers to the account owner’s own address;
              other members see their notices in My atlas only.
            </p>
          )}
          <p className="text-ink-3">{EMAIL_NOTE[email.mode]}</p>
        </div>
      )}
      {email && <TestEmail token={token} />}
      {note && (
        <p className="rounded-lg bg-subtle px-3 py-2 text-[15px] text-ink-2" role="status">
          {note}
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
