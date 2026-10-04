"use client";

// The pages that email links open: /verify (confirm an address), /forgot and /reset (password reset
// with a one-hour, single-use link) and /unsubscribe (one click, no sign-in needed).
// Links from emails carry a signed token in ?t=; the page posts it to the matching API route.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { api, refreshAccount } from "@/lib/account-client";
import { useResource } from "@/lib/resource";
import { Shell } from "./JoinView";

const BTN = "inline-flex min-h-[48px] items-center justify-center rounded-xl px-5 text-[16px] font-medium";
const FIELD = "mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px]";

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-4 rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-[15px] text-warn-ink" role="alert">
      {children}
    </p>
  );
}

/** Posts the token once per page view (keyed by the token, so a re-render never repeats it). */
function useTokenCall(route: string, t: string) {
  const load = useCallback(async () => {
    const r = await api<{ ok: boolean }>(route, "POST", { token: t });
    refreshAccount();
    return r;
  }, [route, t]);
  return useResource(t ? `${route}:${t}` : null, load);
}

export function VerifyView() {
  const t = useSearchParams().get("t") ?? "";
  const r = useTokenCall("/api/account/verify", t);
  return (
    <Shell>
      {!t || r?.status === "error" ? (
        <>
          <h1 className="text-[26px] font-semibold text-ink">This link has expired</h1>
          <Problem>{r?.error ?? "The confirmation link is incomplete."}</Problem>
          <p className="mt-4 text-[16px] text-ink-2">Sign in and choose “Send the link again” on My atlas. Links work for 7 days.</p>
          <Link href="/me" className={`${BTN} mt-5 bg-accent-700 text-white hover:bg-accent-900`}>
            Go to My atlas
          </Link>
        </>
      ) : r?.status === "ready" ? (
        <>
          <h1 className="text-[26px] font-semibold text-ink">Thank you, your email is confirmed</h1>
          <p className="mt-3 text-[17px] text-ink-2">We can now email you the notices you asked for. You can change what you receive, or unsubscribe, at any time on My atlas.</p>
          <Link href="/me" className={`${BTN} mt-6 bg-accent-700 text-white hover:bg-accent-900`}>
            Go to My atlas
          </Link>
        </>
      ) : (
        <p className="text-[17px] text-ink-3" role="status">
          Confirming your email…
        </p>
      )}
    </Shell>
  );
}

export function ForgotView() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Shell>
      <h1 className="text-[26px] font-semibold text-ink">Forgot your password?</h1>
      {sent ? (
        <>
          <p className="mt-3 text-[17px] text-ink-2">If an account uses that address, we have emailed it a link to choose a new password. The link works once, for one hour.</p>
          <p className="mt-3 text-[15px] text-ink-3">Nothing arrived after a few minutes? Check your spam folder, or try again.</p>
          <button type="button" onClick={() => setSent(false)} className={`${BTN} mt-5 border border-line text-ink-2`}>
            Try again
          </button>
        </>
      ) : (
        <form
          className="mt-5 space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("/api/account/forgot", "POST", { email });
              setSent(true);
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <p className="text-[16px] text-ink-2">Enter the email you signed up with. We’ll send you a link to choose a new one.</p>
          <label className="block">
            <span className="text-[15px] font-medium text-ink">Email</span>
            <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={FIELD} />
          </label>
          {error && <Problem>{error}</Problem>}
          <button type="submit" disabled={busy} className={`${BTN} w-full bg-accent-700 text-white hover:bg-accent-900 sm:w-auto`}>
            {busy ? "Sending…" : "Send me a link"}
          </button>
        </form>
      )}
      <p className="mt-6 text-[15px] text-ink-2">
        Remembered it?{" "}
        <Link href="/me" className="font-medium text-accent-700 underline">
          Sign in
        </Link>
      </p>
    </Shell>
  );
}

export function ResetView() {
  const t = useSearchParams().get("t") ?? "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (done)
    return (
      <Shell>
        <h1 className="text-[26px] font-semibold text-ink">Your password is changed</h1>
        <p className="mt-3 text-[17px] text-ink-2">You are signed in.</p>
        <Link href="/me" className={`${BTN} mt-6 bg-accent-700 text-white hover:bg-accent-900`}>
          Go to My atlas
        </Link>
      </Shell>
    );
  return (
    <Shell>
      <h1 className="text-[26px] font-semibold text-ink">Choose a new password</h1>
      {!t ? (
        <>
          <Problem>This reset link is incomplete.</Problem>
          <Link href="/forgot" className={`${BTN} mt-5 bg-accent-700 text-white hover:bg-accent-900`}>
            Ask for a new link
          </Link>
        </>
      ) : (
        <form
          className="mt-5 space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (password !== again) return setError("The two passwords are different.");
            setBusy(true);
            setError(null);
            try {
              await api("/api/account/reset", "POST", { token: t, password });
              refreshAccount();
              setDone(true);
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="block">
            <span className="text-[15px] font-medium text-ink">New password</span>
            <input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={FIELD} />
            <span className="mt-1 block text-sm text-ink-3">At least 10 characters.</span>
          </label>
          <label className="block">
            <span className="text-[15px] font-medium text-ink">Type it again</span>
            <input type="password" required minLength={10} autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} className={FIELD} />
          </label>
          {error && (
            <Problem>
              {error}{" "}
              {/not valid/.test(error) && (
                <Link href="/forgot" className="underline">
                  Ask for a new link
                </Link>
              )}
            </Problem>
          )}
          <button type="submit" disabled={busy} className={`${BTN} w-full bg-accent-700 text-white hover:bg-accent-900 sm:w-auto`}>
            {busy ? "Saving…" : "Save my new password"}
          </button>
        </form>
      )}
    </Shell>
  );
}

export function UnsubscribeView() {
  const t = useSearchParams().get("t") ?? "";
  const r = useTokenCall("/api/account/unsubscribe", t);
  return (
    <Shell>
      {!t || r?.status === "error" ? (
        <>
          <h1 className="text-[26px] font-semibold text-ink">We couldn’t read this link</h1>
          <Problem>{r?.error ?? "The unsubscribe link is incomplete."}</Problem>
          <p className="mt-4 text-[16px] text-ink-2">Sign in and turn emails off under “Privacy and notifications” on My atlas.</p>
          <Link href="/me" className={`${BTN} mt-5 bg-accent-700 text-white hover:bg-accent-900`}>
            Go to My atlas
          </Link>
        </>
      ) : r?.status === "ready" ? (
        <>
          <h1 className="text-[26px] font-semibold text-ink">You’re unsubscribed</h1>
          <p className="mt-3 text-[17px] text-ink-2">We won’t email you notices any more. Your account stays as it is, and new studies still appear on My atlas.</p>
          <p className="mt-3 text-[15px] text-ink-3">Changed your mind? Turn emails back on in My atlas.</p>
          <Link href="/me" className={`${BTN} mt-6 border border-line text-ink-2`}>
            Go to My atlas
          </Link>
        </>
      ) : (
        <p className="text-[17px] text-ink-3" role="status">
          One moment…
        </p>
      )}
    </Shell>
  );
}
