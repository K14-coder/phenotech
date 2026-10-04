"use client";

// Light guided tour: a spotlight on one element per step, a caption card, Next/Back/Exit.
// Navigates between pages, waits for the target to render, works without live AI.
import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { setPersona } from "@/lib/persona";
import { useRouter } from "next/navigation";
import { useAtlas } from "../GraphProvider";
import { useEvidence } from "../evidence/EvidenceProvider";
import { TOURS, type TourStep } from "@/lib/tours";
import { compareDiseases } from "@/lib/compare";
import { edgesBetween, type GraphIndex } from "@/lib/graph";
import { hasPrecomputed } from "@/lib/ai";

interface TourCtx {
  start: (id: string) => void;
}
const Ctx = createContext<TourCtx>({ start: () => {} });
export const useTour = () => useContext(Ctx);

const KEY = "atlas.tour";
type State = { id: string; step: number } | null;

function readState(): State {
  try {
    const s = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
    return s && typeof s.id === "string" && typeof s.step === "number" && TOURS[s.id] ? s : null;
  } catch {
    return null;
  }
}

// Tour position lives in sessionStorage (survives full page loads), exposed as an external store.
let cache: State | undefined;
const listeners = new Set<() => void>();
const getTour = (): State => (cache === undefined ? (cache = readState()) : cache);
const subscribeTour = (cb: () => void) => {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
};
function save(s: State) {
  cache = s;
  try {
    if (s) sessionStorage.setItem(KEY, JSON.stringify(s));
    else sessionStorage.removeItem(KEY);
  } catch {
    // tour still works for this page view
  }
  listeners.forEach((l) => l());
}
const start = (id: string) => {
  const t = TOURS[id];
  if (!t) return;
  // each tour is told from one profile's point of view
  if (t.persona) setPersona(t.persona);
  save({ id, step: 0 });
};

export function TourProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(subscribeTour, getTour, () => null);
  return (
    <Ctx.Provider value={{ start }}>
      {children}
      {/* one overlay for the whole tour (lives in the root layout), so steps and page changes never remount it */}
      {state && <TourOverlay key={state.id} state={state} onChange={save} />}
    </Ctx.Provider>
  );
}

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";
const GLIDE_MS = 420;
const FIND_TIMEOUT = 3000;
type Phase = "seeking" | "shown" | "missing";

function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia("(prefers-reduced-motion: reduce)");
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

/** Resolves once the element's box has not moved for `frames` consecutive animation frames (layout settled, scroll ended). */
function waitStable(el: Element, frames: number, isCancelled: () => boolean, maxMs = 1500): Promise<void> {
  return new Promise((resolve) => {
    let prev = "";
    let same = 0;
    const t0 = performance.now();
    const step = () => {
      if (isCancelled()) return resolve();
      const r = el.getBoundingClientRect();
      const key = `${Math.round(r.left)}:${Math.round(r.top)}:${Math.round(r.width)}:${Math.round(r.height)}`;
      same = key === prev ? same + 1 : 0;
      prev = key;
      if (same >= frames || performance.now() - t0 > maxMs) resolve();
      else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

function TourOverlay({ state, onChange }: { state: { id: string; step: number }; onChange: (s: State) => void }) {
  const tour = TOURS[state.id];
  const step: TourStep = tour.steps[state.step];
  const router = useRouter();
  const atlas = useAtlas();
  const { openEdge, close, edgeId } = useEvidence();
  const reduced = useReducedMotion();
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [phase, setPhase] = useState<Phase>("seeking");
  const [animating, setAnimating] = useState(false);
  const [follow, setFollow] = useState(false);
  const elRef = useRef<Element | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const idx = atlas.status === "ready" ? atlas.idx : null;
  // a new step starts in "seeking" (state adjusted during render, not in an effect)
  const [seenStep, setSeenStep] = useState(state.step);
  if (seenStep !== state.step) {
    setSeenStep(state.step);
    setPhase("seeking");
    setFollow(false);
  }

  const last = state.step === tour.steps.length - 1;
  const go = (d: number) => {
    const n = state.step + d;
    if (n < 0) return;
    if (n >= tour.steps.length) onChange(null);
    else onChange({ id: state.id, step: n });
  };

  // close the evidence drawer when leaving the evidence step
  const drawerOpen = !!edgeId;
  useEffect(() => {
    if (step.action !== "openLimitingEvidence" && drawerOpen) close();
  }, [step.action, drawerOpen, close]);

  // prefetch the next step's page so the change is quick
  useEffect(() => {
    const next = tour.steps[state.step + 1];
    if (next) router.prefetch(next.path.split("?")[0]);
  }, [tour, state.step, router]);

  // one step: navigate if needed, wait for the target and its layout to settle, run the action, smooth-scroll it
  // into view, wait for the scroll to end, then let the spotlight glide there.
  useEffect(() => {
    let cancelled = false;
    const isCancelled = () => cancelled;
    elRef.current = null;
    const here = window.location.pathname + window.location.search;
    if (here !== step.path) router.push(step.path, { scroll: false });
    const t0 = Date.now();
    let acted = false;
    const runAction = () => {
      if (acted) return;
      if (step.action === "openSearch") {
        const input = document.querySelector('[data-tour="search"] input') as HTMLInputElement | null;
        if (input && window.location.search === new URL(step.path, window.location.origin).search) {
          input.blur();
          input.focus();
          acted = true;
        }
      } else if (idx && step.action === "openLimitingEvidence" && window.location.pathname === step.path) {
        const id = limitingEdge(idx);
        if (id) openEdge(id);
        acted = true;
      } else if (idx && step.action === "showPrecomputedProposal" && document.querySelector('[data-tour="proposal"] button')) {
        acted = true;
        void showPrecomputed();
      } else if (!step.action) acted = true;
    };
    let missed = false;
    const find = async () => {
      while (!cancelled) {
        const onPage = window.location.pathname === step.path.split("?")[0];
        runAction();
        const el = onPage ? document.querySelector(step.target) : null;
        if (el && (el as HTMLElement).getClientRects().length) {
          await waitStable(el, 4, isCancelled);
          if (cancelled) return;
          const r = el.getBoundingClientRect();
          const inView = r.top >= 64 && r.bottom <= window.innerHeight - 180;
          if (!inView) {
            el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
            await new Promise((res) => setTimeout(res, 60));
            await waitStable(el, 6, isCancelled, 1800);
          }
          if (cancelled) return;
          elRef.current = el;
          setAnimating(true);
          setRect(unionRect(el));
          setPhase("shown");
          window.setTimeout(() => {
            if (!cancelled) {
              setAnimating(false);
              setFollow(true);
            }
          }, reduced ? 200 : GLIDE_MS + 40);
          return;
        }
        if (Date.now() - t0 > FIND_TIMEOUT && !missed) {
          missed = true;
          setPhase("missing");
          setRect(null);
          // keep looking quietly: if the target shows up late, move there
        }
        await new Promise((res) => setTimeout(res, 120));
      }
    };
    void find();
    return () => {
      cancelled = true;
    };
  }, [idx, step, router, openEdge, reduced]);

  // after the glide, keep the spotlight on the target while the user scrolls or the page resizes (no animation)
  useEffect(() => {
    if (!follow) return;
    let raf = 0;
    const update = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = elRef.current;
        if (el && document.contains(el)) setRect(unionRect(el));
      });
    };
    window.addEventListener("scroll", update, { passive: true, capture: true });
    window.addEventListener("resize", update);
    const iv = window.setInterval(update, 500); // popovers that open and close (search results)
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", update, { capture: true });
      window.removeEventListener("resize", update);
      window.clearInterval(iv);
    };
  }, [follow]);

  useEffect(() => {
    if (step.action !== "openSearch" && phase === "shown") cardRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onChange(null);
      else if (e.key === "ArrowRight" && !(e.target instanceof HTMLInputElement)) go(1);
      else if (e.key === "ArrowLeft" && !(e.target instanceof HTMLInputElement)) go(-1);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  });

  const pad = 8;
  // spotlight box: the target (padded), or a zero-size box at the centre while looking (the shadow then dims everything)
  const vw = typeof window === "undefined" ? 1200 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const box = rect ? { x: rect.left - pad, y: rect.top - pad, w: rect.width + 2 * pad, h: rect.height + 2 * pad } : { x: vw / 2, y: vh / 2, w: 0, h: 0 };
  const glide = animating && !reduced;
  const spotTransition = reduced
    ? "opacity 200ms ease"
    : glide
      ? `transform ${GLIDE_MS}ms ${EASE}, width ${GLIDE_MS}ms ${EASE}, height ${GLIDE_MS}ms ${EASE}, opacity 200ms ease`
      : "opacity 200ms ease";
  const loading = phase === "seeking";
  return (
    <div className="pointer-events-none fixed inset-0 z-[95]" aria-live="polite">
      <div
        aria-hidden="true"
        className="fixed left-0 top-0 rounded-xl"
        style={{
          transform: `translate3d(${box.x}px, ${box.y}px, 0)`,
          width: box.w,
          height: box.h,
          boxShadow: `0 0 0 9999px rgba(15, 18, 24, ${loading && !rect ? 0.3 : 0.42})`,
          outline: rect ? "2px solid #1f5a96" : "none",
          opacity: reduced && loading ? 0.6 : 1,
          transition: spotTransition,
          willChange: glide ? "transform, width, height" : "auto",
        }}
      />
      <div
        ref={cardRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="false"
        aria-labelledby="tour-title"
        className="pointer-events-auto fixed bottom-4 left-1/2 w-[560px] max-w-[calc(100vw-24px)] rounded-xl border border-line bg-white px-5 py-4 shadow-[0_16px_48px_rgba(16,24,40,0.18)] outline-none sm:bottom-6"
        style={
          phase === "missing"
            ? { top: "50%", bottom: "auto", transform: "translate(-50%, -50%)", transition: "opacity 200ms ease" }
            : { transform: "translateX(-50%)" }
        }
      >
        <div
          key={`${state.step}:${phase === "seeking" ? "s" : "r"}`}
          className="tour-card-in"
          style={{ animationDuration: reduced ? "160ms" : "260ms" }}
        >
          <p className="text-xs font-medium text-ink-3">
            {tour.name} · {state.step + 1} of {tour.steps.length}
          </p>
          <p id="tour-title" className="mt-1 text-[16px] font-semibold text-ink">
            {step.title}
          </p>
          {loading ? (
            <div className="mt-2 space-y-1.5" aria-label="Loading the next step">
              <p className="text-[15px] text-ink-3">Loading the next step…</p>
              <span className="block h-2.5 w-4/5 animate-pulse rounded bg-subtle" />
              <span className="block h-2.5 w-3/5 animate-pulse rounded bg-subtle" />
            </div>
          ) : (
            <p className="mt-1 text-[15px] leading-relaxed text-ink-2">{step.caption}</p>
          )}
          {phase === "missing" && <p className="mt-2 text-sm text-warn-ink">This part of the page isn’t showing right now. You can skip ahead.</p>}
        </div>
        <div className="mt-4 flex items-center justify-between">
          <button type="button" onClick={() => onChange(null)} className="text-sm text-ink-3 hover:text-ink">
            Exit tour <span className="hidden text-xs text-ink-4 sm:inline">(Esc)</span>
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => go(-1)}
              disabled={state.step === 0}
              className="rounded-md border border-line px-3.5 py-1.5 text-sm text-ink-2 transition-transform duration-150 hover:border-accent-500 active:scale-[0.97] disabled:opacity-40"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              className="rounded-md bg-accent-700 px-4 py-1.5 text-sm font-medium text-white transition-transform duration-150 hover:bg-accent-900 active:scale-[0.97]"
            >
              {phase === "missing" ? (last ? "Finish" : "Skip") : last ? "Finish" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The target plus any attached popover (e.g. the search results list). */
function unionRect(el: Element): DOMRect {
  const r = el.getBoundingClientRect();
  let { left, top, right, bottom } = r;
  el.querySelectorAll("[data-tour-extend]").forEach((x) => {
    const q = x.getBoundingClientRect();
    left = Math.min(left, q.left);
    top = Math.min(top, q.top);
    right = Math.max(right, q.right);
    bottom = Math.max(bottom, q.bottom);
  });
  return new DOMRect(left, top, right - left, Math.min(bottom, window.innerHeight - 16) - top);
}

/** A VAMP2–STXBP1 link that carries limiting or contradicting evidence (falls back to the direct link). */
function limitingEdge(idx: GraphIndex): string | null {
  const direct = edgesBetween(idx, "disease:VAMP2", "disease:STXBP1");
  const c = compareDiseases(idx, "disease:VAMP2", "disease:STXBP1");
  const candidates = [...direct, ...(c?.shared.flatMap((s) => [s.a.edge, s.b.edge]) ?? [])];
  const limited = candidates.find((e) => (e.counter_evidence?.length ?? 0) > 0 || e.evidence.some((ev) => ev.supports === false));
  return (limited ?? candidates[0])?.id ?? null;
}

/** Only click "Draft a collaboration proposal" when a precomputed draft exists, so the tour never calls live AI. */
async function showPrecomputed() {
  try {
    if (!(await hasPrecomputed("proposal", "disease:VAMP2"))) return;
    (document.querySelector('[data-tour="proposal"] button') as HTMLButtonElement | null)?.click();
  } catch {
    // leave the button for the presenter
  }
}
