"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useAtlas } from "../GraphProvider";
import { EvidencePanel } from "./EvidencePanel";

interface EvidenceCtx {
  openEdge: (edgeId: string) => void;
  close: () => void;
  edgeId: string | null;
}

const Ctx = createContext<EvidenceCtx>({ openEdge: () => {}, close: () => {}, edgeId: null });

export function useEvidence() {
  return useContext(Ctx);
}

/** Holds the Evidence panel state for the whole app; any EvidenceChip can open it. */
export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const [edgeId, setEdgeId] = useState<string | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const openEdge = useCallback((id: string) => {
    if (!returnFocus.current) returnFocus.current = document.activeElement as HTMLElement | null;
    setEdgeId(id);
  }, []);
  const close = useCallback(() => {
    setEdgeId(null);
    const el = returnFocus.current;
    returnFocus.current = null;
    if (el && document.contains(el)) setTimeout(() => el.focus(), 0);
  }, []);

  return (
    <Ctx.Provider value={{ openEdge, close, edgeId }}>
      {children}
      {edgeId && <EvidenceDrawer edgeId={edgeId} onClose={close} onNavigate={setEdgeId} />}
    </Ctx.Provider>
  );
}

function EvidenceDrawer({
  edgeId,
  onClose,
  onNavigate,
}: {
  edgeId: string;
  onClose: () => void;
  onNavigate: (id: string) => void;
}) {
  const atlas = useAtlas();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // move focus into the dialog (the panel itself, so no button looks pre-selected)
  useEffect(() => {
    panelRef.current?.focus();
  }, [edgeId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Tab" && panelRef.current) {
        // keep focus inside the dialog
        const f = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
        );
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (atlas.status !== "ready") return null;
  const edge = atlas.idx.edgeById.get(edgeId);

  return (
    <div className="fixed inset-0 z-[80]">
      <div className="absolute inset-0 bg-ink/10" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        tabIndex={-1}
        style={{ outline: "none" }}
        className="absolute inset-y-0 right-0 flex w-[520px] max-w-full flex-col border-l border-line bg-white shadow-[-12px_0_32px_rgba(16,24,40,0.06)]"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-6">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Evidence</span>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="-mr-2 rounded-md px-2 py-1 text-sm text-ink-3 hover:bg-subtle hover:text-ink"
          >
            Close <span className="sr-only">evidence panel</span>
            <span aria-hidden="true" className="ml-1">
              Esc
            </span>
          </button>
        </div>
        <div className="panel-scroll flex-1 overflow-y-auto">
          {edge ? (
            <EvidencePanel idx={atlas.idx} edge={edge} onNavigate={onNavigate} onClose={onClose} />
          ) : (
            <p className="p-6 text-sm text-ink-3">This connection is not in the current data ({edgeId}).</p>
          )}
        </div>
      </div>
    </div>
  );
}
