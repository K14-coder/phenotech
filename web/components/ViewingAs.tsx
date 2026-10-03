"use client";

import { PERSONAS, setPersona, usePersona, type Persona } from "@/lib/persona";

/**
 * The one "Viewing as" switch (brief's concept mockup). It sits in the header on most pages; on the
 * atlas it moves next to the selection panel ("Viewing as · Maria, patient leader") instead, so a page
 * never shows two. It changes the wording and section order of disease action pages.
 */
export function ViewingAs({ variant = "header" }: { variant?: "header" | "panel" }) {
  const persona = usePersona();
  const current = PERSONAS.find((p) => p.id === persona);
  const title = current ? `${current.hint} (disease action pages)` : undefined;
  const options = PERSONAS.map((p) => (
    <option key={p.id} value={p.id}>
      {p.label}
    </option>
  ));

  if (variant === "panel") {
    return (
      <label className="flex min-w-0 items-center gap-1 text-xs text-ink-3" title={title}>
        <span className="shrink-0">Viewing as ·</span>
        <span className="relative inline-flex min-w-0 items-center">
          <select
            value={persona}
            onChange={(e) => setPersona(e.target.value as Persona)}
            className="min-w-0 cursor-pointer appearance-none truncate rounded bg-transparent py-0.5 pl-1 pr-5 text-xs font-medium text-ink [field-sizing:content] hover:bg-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            data-tour="viewing-as"
            aria-label="Viewing as"
          >
            {options}
          </select>
          <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="pointer-events-none absolute right-1.5 text-ink-3">
            <path d="M1 2.5 4 5.5 7 2.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
          </svg>
        </span>
      </label>
    );
  }

  return (
    <label className="flex items-center gap-2 text-xs text-ink-3" title={title}>
      Viewing as
      <select
        value={persona}
        onChange={(e) => setPersona(e.target.value as Persona)}
        className="h-8 rounded-md border border-line bg-white px-2 text-xs text-ink focus:border-accent-700 focus:outline-none"
        data-tour="viewing-as"
        aria-label="Viewing as"
      >
        {options}
      </select>
    </label>
  );
}
