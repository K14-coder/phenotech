"use client";

import Link from "next/link";
import { useState } from "react";
import { ACCOUNT_KEY, api, loadAccount, refreshAccount, type AccountState } from "@/lib/account-client";
import { useResource } from "@/lib/resource";

/** Header link: "My atlas" when signed in, "Sign in" otherwise; nothing while accounts are switched off. */
export function AccountLink() {
  const a = useResource<AccountState>(ACCOUNT_KEY, loadAccount)?.data;
  if (!a || a.mode === "off") return null;
  return (
    <Link href="/me" className="hidden rounded-md px-2 py-1.5 text-sm text-ink-2 hover:text-ink sm:inline">
      {a.user ? "My atlas" : "Sign in"}
    </Link>
  );
}

/** "Save to my atlas" for signed-in members (questions, the doctor printout, a page). */
export function SaveButton({ title, kind = "page" }: { title: string; kind?: "questions" | "printout" | "page" }) {
  const a = useResource<AccountState>(ACCOUNT_KEY, loadAccount)?.data;
  const [done, setDone] = useState(false);
  if (!a?.user) return null;
  return (
    <button
      type="button"
      disabled={done}
      onClick={async () => {
        await api("/api/account", "PATCH", { save: { kind, title, href: location.pathname + location.search } });
        refreshAccount();
        setDone(true);
      }}
      className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] text-ink-2 hover:border-accent-500 disabled:opacity-60"
    >
      {done ? "Saved to my atlas" : "Save to my atlas"}
    </button>
  );
}

/** One tap "Follow for alerts" for signed-in members on a disease page (never automatic). */
export function FollowButton({ diseaseId, diseaseName }: { diseaseId: string; diseaseName: string }) {
  const a = useResource<AccountState>(ACCOUNT_KEY, loadAccount)?.data;
  const [busy, setBusy] = useState(false);
  if (!a?.user) return null;
  const following = a.user.diseases.includes(diseaseId);
  if (following)
    return (
      <p className="mt-3 inline-flex min-h-[36px] items-center gap-2 text-sm text-ink-2 print:hidden">
        <span className="h-2 w-2 rounded-full bg-ok" aria-hidden="true" />
        Following: new studies and research appear in{" "}
        <Link href="/me" className="text-accent-700 underline">
          My atlas
        </Link>
      </p>
    );
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await api("/api/account", "PATCH", { diseases: [...a.user!.diseases, diseaseId], labels: { [diseaseId]: diseaseName } });
          refreshAccount();
        } finally {
          setBusy(false);
        }
      }}
      className="mt-3 inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-accent-700 px-4 text-[15px] font-medium text-accent-700 hover:bg-accent-50 disabled:opacity-60 print:hidden"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M8 2.5a3.5 3.5 0 0 0-3.5 3.5v2.4L3.2 11h9.6l-1.3-2.6V6A3.5 3.5 0 0 0 8 2.5zM6.5 12.5a1.5 1.5 0 0 0 3 0" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
      {busy ? "Following…" : "Follow for alerts"}
    </button>
  );
}
