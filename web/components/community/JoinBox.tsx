"use client";

// "Join the <disease> community": a small, polite card (bottom right on a desktop, a bottom sheet on a phone).
// Appears after ~40% of the page is read, can be dismissed for 7 days, never shows during a guided tour.
import Link from "next/link";
import { useEffect, useState } from "react";
import { ACCOUNT_KEY, api, loadAccount, refreshAccount, type AccountState } from "@/lib/account-client";
import { useResource } from "@/lib/resource";

const DISMISS_KEY = "atlas.join.dismissed";
const WEEK = 7 * 86400_000;

function dismissedRecently(): boolean {
  try {
    const t = Number(localStorage.getItem(DISMISS_KEY) ?? 0);
    return Date.now() - t < WEEK;
  } catch {
    return false;
  }
}
function inTour(): boolean {
  try {
    return !!sessionStorage.getItem("atlas.tour");
  } catch {
    return false;
  }
}

export function JoinBox({ diseaseId, diseaseName }: { diseaseId: string; diseaseName: string }) {
  const [show, setShow] = useState(false);
  const [closed, setClosed] = useState(false);
  const acct = useResource<AccountState>(ACCOUNT_KEY, loadAccount);
  const a = acct?.data;

  useEffect(() => {
    if (dismissedRecently()) return;
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (max > 0 && window.scrollY / max >= 0.4 && !inTour()) {
        setShow(true);
        window.removeEventListener("scroll", onScroll);
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const following = !!a?.user?.diseases.includes(diseaseId);
  if (!show || closed || !a || following) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {
      // fine: it stays closed for this page view
    }
    setClosed(true);
  };
  const follow = async () => {
    await api("/api/account", "PATCH", { diseases: [...(a.user?.diseases ?? []), diseaseId] });
    refreshAccount();
    setClosed(true);
  };

  return (
    <aside
      aria-labelledby="joinbox-h"
      className="fixed inset-x-0 bottom-0 z-40 rounded-t-2xl border border-line bg-white px-5 pb-5 pt-4 shadow-[0_-8px_30px_rgba(16,24,40,0.12)] print:hidden sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-[360px] sm:rounded-2xl"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 id="joinbox-h" className="text-[17px] font-semibold leading-snug text-ink">
          Join the {diseaseName} community
        </h2>
        <button type="button" onClick={dismiss} aria-label="Close" className="-mr-1 -mt-1 h-8 w-8 shrink-0 rounded-md text-ink-3 hover:bg-subtle hover:text-ink">
          ×
        </button>
      </div>
      <ul className="mt-2 space-y-1.5 text-[14px] leading-snug text-ink-2">
        {[
          "Get notified when a clinical trial starts recruiting for this disease",
          "Be counted, anonymously, so researchers can see that families exist and where",
          "Connect with the patient group and other families, through the group",
          "Get updates when new research or resources appear",
          "Save your questions and the doctor printout",
        ].map((b) => (
          <li key={b} className="flex gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent-700" aria-hidden="true" />
            {b}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        We never sell or share your contact details. Researchers only see anonymous counts unless you choose to be contacted.{" "}
        <Link href="/privacy" className="underline">
          Privacy
        </Link>
      </p>
      <div className="mt-3 flex items-center gap-3">
        {a.mode === "off" ? (
          <button type="button" disabled className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white opacity-50">
            Sign-up opens soon
          </button>
        ) : a.user ? (
          <button type="button" onClick={() => void follow()} className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900">
            Follow this disease
          </button>
        ) : (
          <Link
            href={`/join?disease=${encodeURIComponent(diseaseId)}`}
            className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900"
          >
            Sign up
          </Link>
        )}
        <button type="button" onClick={dismiss} className="min-h-[44px] px-2 text-[15px] text-ink-2 hover:text-ink">
          Not now
        </button>
      </div>
    </aside>
  );
}
