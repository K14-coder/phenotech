"use client";

import { useEffect, useId, useRef, useState } from "react";
import { PERSONAS, personaMeta, setPersona, usePersona, usePersonaChosen, type Persona } from "@/lib/persona";

/**
 * The one mode switch, top right on every page: "Viewing: Simple ▾". The menu gives each mode a
 * one-line description. Every page reads the profile and changes its content.
 */
export function ViewingAs() {
  const persona = usePersona();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const listId = useId();
  const current = personaMeta(persona);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (p: Persona) => {
    setPersona(p);
    setOpen(false);
  };

  return (
    <div ref={wrap} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        data-tour="viewing-as"
        className="flex h-9 items-center gap-1.5 rounded-md border border-line bg-white px-2.5 text-sm text-ink hover:border-accent-500"
      >
        <span className="hidden text-ink-3 sm:inline">View:</span>
        <span className="font-medium">{current.name}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="text-ink-3">
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      </button>
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Switch view"
          className="absolute right-0 z-50 mt-1.5 w-[min(340px,calc(100vw-24px))] overflow-hidden rounded-lg border border-line bg-white py-1 shadow-[0_8px_24px_rgba(16,24,40,0.10)]"
        >
          <li className="px-3 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3" role="presentation">
            Choose a view
          </li>
          {PERSONAS.map((p) => (
            <li key={p.id} role="option" aria-selected={p.id === persona}>
              <button
                type="button"
                onClick={() => choose(p.id)}
                className={`flex w-full gap-2.5 px-3 py-2 text-left hover:bg-subtle ${p.id === persona ? "bg-subtle" : ""}`}
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${p.id === persona ? "bg-accent-700" : "border border-ink-4"}`} aria-hidden="true" />
                <span>
                  <span className="block text-sm font-medium text-ink">{p.label}</span>
                  <span className="block text-xs leading-snug text-ink-3">{p.hint}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Asked once, gently, on a first visit. Simple is preselected; nothing is blocked while it shows. */
export function FirstVisitChooser() {
  const chosen = usePersonaChosen();
  const persona = usePersona();
  const [pick, setPick] = useState<Persona>(persona);
  if (chosen) return null;
  return (
    <div className="border-b border-line bg-subtle/70 print:hidden">
      <div className="mx-auto flex max-w-[1120px] flex-col gap-3 px-4 py-4 sm:px-8 md:flex-row md:items-center">
        <p className="shrink-0 text-[15px] font-medium text-ink">
          Welcome to Phenotech. How should we show things? <span className="font-normal text-ink-3">(You can change this anytime)</span>
        </p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Choose a view">
          {PERSONAS.map((p) => (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={pick === p.id}
              onClick={() => setPick(p.id)}
              title={p.hint}
              className={`rounded-lg border px-3 py-1.5 text-left text-sm ${
                pick === p.id ? "border-accent-700 bg-white font-medium text-ink" : "border-line bg-white text-ink-2 hover:border-accent-500"
              }`}
            >
              <span className="block font-medium text-ink">{p.label}</span>
              <span className="block text-xs text-ink-3">{p.short}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setPersona(pick)}
          className="rounded-md bg-accent-700 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-accent-900 md:ml-auto"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
