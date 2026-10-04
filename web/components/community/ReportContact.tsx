"use client";

// "Report or remove a contact": a short form on /privacy. Requests go to the admin moderation queue.
import { useState } from "react";
import { api } from "@/lib/account-client";

const FIELD = "mt-1 w-full rounded-lg border border-line px-3 text-[16px]";

export function ReportContact() {
  const [about, setAbout] = useState("");
  const [kind, setKind] = useState<"wrong" | "remove" | "other">("remove");
  const [message, setMessage] = useState("");
  const [replyTo, setReplyTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (done)
    return (
      <p className="mt-3 rounded-lg bg-subtle px-4 py-3 text-[15px] text-ink-2" role="status">
        Thank you. A person on our team will look at this, usually within a few days. If you left an address, we’ll tell you what we changed.
      </p>
    );
  return (
    <form
      className="mt-4 space-y-3 rounded-xl border border-line px-4 py-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api("/api/contact-report", "POST", { about, kind, message, replyTo, page: "/privacy" });
          setDone(true);
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <label className="block">
        <span className="text-[15px] font-medium text-ink">Which organisation or contact is it about?</span>
        <input required value={about} onChange={(e) => setAbout(e.target.value)} maxLength={200} className={`${FIELD} h-11`} placeholder="e.g. the group’s name and the disease page" />
      </label>
      <fieldset>
        <legend className="text-[15px] font-medium text-ink">What should we do?</legend>
        <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[15px] text-ink-2">
          {(
            [
              ["remove", "Remove it"],
              ["wrong", "It’s wrong or out of date"],
              ["other", "Something else"],
            ] as const
          ).map(([k, l]) => (
            <label key={k} className="inline-flex min-h-[36px] items-center gap-2">
              <input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} className="h-4 w-4 accent-[#1f5a96]" />
              {l}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block">
        <span className="text-[15px] font-medium text-ink">A short note</span>
        <textarea required value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} rows={3} className={`${FIELD} py-2`} />
      </label>
      <label className="block">
        <span className="text-[15px] font-medium text-ink">Your email, if you’d like a reply (optional)</span>
        <input type="email" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} maxLength={254} className={`${FIELD} h-11`} />
      </label>
      {error && (
        <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-[15px] text-warn-ink" role="alert">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy} className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900 disabled:opacity-60">
        {busy ? "Sending…" : "Send to our team"}
      </button>
    </form>
  );
}
