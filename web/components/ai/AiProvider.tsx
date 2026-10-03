"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { PRECOMPUTED_STATUS, type AiStatusPayload } from "@/lib/ai-shared";
import { aiLogin, aiLogout, aiStatus } from "@/lib/ai";

interface AiCtx {
  status: AiStatusPayload;
  loaded: boolean;
  /** true while a "Continue with ChatGPT" sign-in is waiting for the browser */
  pending: boolean;
  authorizeUrl: string | null;
  message: string | null;
  refresh: () => Promise<AiStatusPayload>;
  login: (reconsent?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  /** live generation is possible right now (local server + a usable auth path) */
  canGenerateLive: boolean;
}

const Ctx = createContext<AiCtx>({
  status: PRECOMPUTED_STATUS,
  loaded: false,
  pending: false,
  authorizeUrl: null,
  message: null,
  refresh: async () => PRECOMPUTED_STATUS,
  login: async () => {},
  logout: async () => {},
  canGenerateLive: false,
});

export function useAi() {
  return useContext(Ctx);
}

const NOTICE_KEY = "atlas.chatgptPlanNotice";

function readNoticeSeen(): string | null {
  try {
    return typeof window === "undefined" ? null : localStorage.getItem(NOTICE_KEY);
  } catch {
    return null;
  }
}
const POLL_MS = 2000;
const POLL_MAX_MS = 10 * 60 * 1000;

export function AiProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AiStatusPayload>(PRECOMPUTED_STATUS);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [authorizeUrl, setAuthorizeUrl] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const pollStart = useRef(0);

  const refresh = useCallback(async () => {
    const s = await aiStatus();
    setStatus(s);
    setLoaded(true);
    return s;
  }, []);

  useEffect(() => {
    let alive = true;
    aiStatus().then((s) => {
      if (!alive) return;
      setStatus(s);
      setLoaded(true);
      if (s.login.status === "pending") {
        setPending(true);
        setAuthorizeUrl(s.login.authorizeUrl ?? null);
        pollStart.current = Date.now();
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  // poll while a sign-in is pending
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(async () => {
      const s = await aiStatus();
      setStatus(s);
      const timedOut = Date.now() - pollStart.current > POLL_MAX_MS;
      if (s.signedIn || s.login.status === "failed" || s.login.status === "done" || timedOut) {
        setPending(false);
        setAuthorizeUrl(null);
        if (s.login.status === "failed") setMessage(s.login.error?.message ?? "Sign-in did not finish.");
        else if (timedOut && !s.signedIn) setMessage("Sign-in timed out. Try again.");
        else if (s.signedIn && !s.planUsage) setMessage("Signed in, but ChatGPT plan usage was not granted.");
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [pending]);

  // One-time "You're using your ChatGPT plan" confirmation, keyed on planUsageFirstEnabledAt.
  // Status is only known after the client-side fetch, so reading storage here can't break hydration.
  const firstAt = status.authPath === "chatgpt" ? status.planUsageFirstEnabledAt : null;
  const notice = firstAt && dismissed !== firstAt && readNoticeSeen() !== firstAt ? firstAt : null;

  const login = useCallback(async (reconsent = false) => {
    setMessage(null);
    const r = await aiLogin(reconsent);
    if (r.error || !r.authorizeUrl) {
      setMessage(r.error?.message ?? "Could not start sign-in.");
      return;
    }
    setAuthorizeUrl(r.authorizeUrl);
    pollStart.current = Date.now();
    setPending(true);
  }, []);

  const logout = useCallback(async () => {
    const r = await aiLogout();
    setMessage(r.error ? r.error.message : r.message ?? null);
    await refresh();
  }, [refresh]);

  const canGenerateLive = status.mode === "live" && status.authPath !== "none";

  return (
    <Ctx.Provider value={{ status, loaded, pending, authorizeUrl, message, refresh, login, logout, canGenerateLive }}>
      {children}
      {notice && (
        <PlanNotice
          manageUsageUrl={status.manageUsageUrl}
          onClose={() => {
            try {
              localStorage.setItem(NOTICE_KEY, notice);
            } catch {
              // storage unavailable: the notice may show again next time
            }
            setDismissed(notice);
          }}
        />
      )}
    </Ctx.Provider>
  );
}

function PlanNotice({ manageUsageUrl, onClose }: { manageUsageUrl: string; onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-ink/20 px-4">
      <div role="dialog" aria-modal="true" aria-labelledby="plan-notice-title" className="w-full max-w-[420px] rounded-xl border border-line bg-white p-6 shadow-[0_16px_48px_rgba(16,24,40,0.12)]">
        <h2 id="plan-notice-title" className="text-[17px] font-semibold text-ink">
          You’re using your ChatGPT plan
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          AI drafts in Rare Disease Atlas now run on your ChatGPT plan. They count toward your plan’s usage limits, which are shared
          with your own ChatGPT use. This app adds no charges of its own.
        </p>
        <div className="mt-5 flex items-center justify-end gap-3">
          <a href={manageUsageUrl} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-accent-700 hover:underline">
            Manage usage ↗
          </a>
          <button ref={ref} type="button" onClick={onClose} className="rounded-md bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-black">
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
