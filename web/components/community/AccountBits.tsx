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
