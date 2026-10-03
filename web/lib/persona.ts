"use client";

// "Viewing as" profile (docs/persona-spec.md). Devon (newly diagnosed) is the default. Stored in
// localStorage, overridable with ?as=family|leader|researcher|biotech (ids are stable).
import { useSyncExternalStore } from "react";

export type Persona = "family" | "leader" | "researcher" | "biotech";

export const PERSONAS: { id: Persona; name: string; short: string; label: string; hint: string }[] = [
  {
    id: "family",
    name: "Devon",
    short: "new to this",
    label: "Devon (new to this)",
    hint: "Just received a diagnosis. Plain words: what it means, who to contact, what to do this week.",
  },
  {
    id: "leader",
    name: "Maria",
    short: "patient-group leader",
    label: "Maria (patient-group leader)",
    hint: "Runs a patient group. Neighbouring communities, reusable assets, partners and a sourced proposal.",
  },
  {
    id: "researcher",
    name: "Dr. Osei",
    short: "researcher",
    label: "Dr. Osei (researcher)",
    hint: "Researcher or clinician. Mechanism and evidence, patient population, trial readiness and how to reach patients.",
  },
  {
    id: "biotech",
    name: "Priya",
    short: "biotech scout",
    label: "Priya (biotech scout)",
    hint: "Biotech or pharma. Which diseases fit an approach, unmet need, trial readiness and population size.",
  },
];

const KEY = "atlas.persona";
export const DEFAULT_PERSONA: Persona = "family";
const valid = (x: unknown): x is Persona => x === "family" || x === "leader" || x === "researcher" || x === "biotech";

type State = { persona: Persona; chosen: boolean };
let current: State | null = null;
const SERVER: State = { persona: DEFAULT_PERSONA, chosen: true };
const listeners = new Set<() => void>();

function read(): State {
  try {
    const q = new URLSearchParams(window.location.search).get("as");
    if (valid(q)) {
      localStorage.setItem(KEY, q);
      return { persona: q, chosen: true };
    }
    const s = localStorage.getItem(KEY);
    if (valid(s)) return { persona: s, chosen: true };
  } catch {
    // storage unavailable: default, and don't nag
    return { persona: DEFAULT_PERSONA, chosen: true };
  }
  return { persona: DEFAULT_PERSONA, chosen: false };
}

function getSnapshot(): State {
  if (current === null) current = read();
  return current;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function setPersona(p: Persona) {
  current = { persona: p, chosen: true };
  try {
    localStorage.setItem(KEY, p);
  } catch {
    // keep it for this page view only
  }
  listeners.forEach((l) => l());
}

export function usePersona(): Persona {
  return useSyncExternalStore(subscribe, getSnapshot, () => SERVER).persona;
}

/** false only for a first-time visitor who has not picked a profile yet (drives the gentle chooser). */
export function usePersonaChosen(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => SERVER).chosen;
}

export function personaMeta(p: Persona) {
  return PERSONAS.find((x) => x.id === p) ?? PERSONAS[0];
}
