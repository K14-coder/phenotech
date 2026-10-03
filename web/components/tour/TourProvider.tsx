"use client";

// Light guided tour: a spotlight on one element per step, a caption card, Next/Back/Exit.
// Navigates between pages, waits for the target to render, works without live AI.
import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore } from "react";
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
  if (TOURS[id]) save({ id, step: 0 });
};

export function TourProvider({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(subscribeTour, getTour, () => null);
  return (
    <Ctx.Provider value={{ start }}>
      {children}
      {state && <TourOverlay key={`${state.id}:${state.step}`} state={state} onChange={save} />}
    </Ctx.Provider>
  );
}

function TourOverlay({ state, onChange }: { state: { id: string; step: number }; onChange: (s: State) => void }) {
  const tour = TOURS[state.id];
  const step: TourStep = tour.steps[state.step];
  const router = useRouter();
  const atlas = useAtlas();
  const { openEdge, close, edgeId } = useEvidence();
  const [rect, setRect] = useState<DOMRect | null>(null);
  const elRef = useRef<Element | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const idx = atlas.status === "ready" ? atlas.idx : null;

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

  // navigate, wait for the target, run the step's action, then follow it while the page scrolls
  useEffect(() => {
    let cancelled = false;
    const here = window.location.pathname + window.location.search;
    if (here !== step.path) router.push(step.path, { scroll: false });
    const t0 = Date.now();
    let acted = false;
    const tick = setInterval(() => {
      if (cancelled) return;
      if (!acted && step.action === "openSearch") {
        const input = document.querySelector('[data-tour="search"] input') as HTMLInputElement | null;
        if (input && window.location.search === new URL(step.path, window.location.origin).search) {
          input.blur();
          input.focus();
          acted = true;
        }
      }
      if (!acted && idx && step.action) {
        if (step.action === "openLimitingEvidence" && window.location.pathname === step.path) {
          const id = limitingEdge(idx);
          if (id) openEdge(id);
          acted = true;
        } else if (step.action === "showPrecomputedProposal" && document.querySelector('[data-tour="proposal"] button')) {
          acted = true;
          void showPrecomputed();
        }
      }
      const el = document.querySelector(step.target);
      if (el && el !== elRef.current) {
        elRef.current = el;
        el.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      if (elRef.current && document.contains(elRef.current)) setRect(unionRect(elRef.current));
      else if (Date.now() - t0 > 10000) setRect(null);
    }, 200);
    return () => {
      cancelled = true;
      clearInterval(tick);
    };
  }, [idx, step, router, openEdge]);

  useEffect(() => {
    if (step.action !== "openSearch") cardRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onChange(null);
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  });

  const pad = 8;
  return (
    <div className="pointer-events-none fixed inset-0 z-[95]">
      {rect && (
        <div
          aria-hidden="true"
          className="absolute rounded-xl transition-all duration-300"
          style={{
            left: rect.left - pad,
            top: rect.top - pad,
            width: rect.width + 2 * pad,
            height: rect.height + 2 * pad,
            boxShadow: "0 0 0 9999px rgba(15, 18, 24, 0.42)",
            outline: "2px solid #1f5a96",
            outlineOffset: 0,
          }}
        />
      )}
      <div
        ref={cardRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="false"
        aria-labelledby="tour-title"
        className="pointer-events-auto absolute bottom-6 left-1/2 w-[560px] max-w-[calc(100vw-32px)] -translate-x-1/2 rounded-xl border border-line bg-white px-5 py-4 shadow-[0_16px_48px_rgba(16,24,40,0.18)] outline-none"
      >
        <p className="text-xs font-medium text-ink-3">
          {tour.name} · {state.step + 1} of {tour.steps.length}
        </p>
        <p id="tour-title" className="mt-1 text-[16px] font-semibold text-ink">
          {step.title}
        </p>
        <p className="mt-1 text-[15px] leading-relaxed text-ink-2">{step.caption}</p>
        <div className="mt-4 flex items-center justify-between">
          <button type="button" onClick={() => onChange(null)} className="text-sm text-ink-3 hover:text-ink">
            Exit tour
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => go(-1)}
              disabled={state.step === 0}
              className="rounded-md border border-line px-3.5 py-1.5 text-sm text-ink-2 hover:border-accent-500 disabled:opacity-40"
            >
              Back
            </button>
            <button type="button" onClick={() => go(1)} className="rounded-md bg-accent-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-900">
              {last ? "Finish" : "Next"}
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
