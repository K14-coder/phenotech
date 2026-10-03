"use client";

// "Viewing as" persona. Stored in localStorage, overridable with ?as=family|leader|researcher|biotech.
import { useSyncExternalStore } from "react";

export type Persona = "family" | "leader" | "researcher" | "biotech";

/** The brief's four people, in its order: Maria leads; Devon, Priya and Dr. Osei. */
export const PERSONAS: { id: Persona; label: string; hint: string }[] = [
  { id: "leader", label: "Maria, patient leader", hint: "The full action page" },
  { id: "family", label: "Devon, newly diagnosed", hint: "Plainest wording; your community first" },
  { id: "biotech", label: "Priya, biotech scout", hint: "Mechanism and unmet need first" },
  { id: "researcher", label: "Dr. Osei, researcher", hint: "Mechanisms first, and who works on them" },
];

const KEY = "atlas.persona";
const DEFAULT: Persona = "leader";
const valid = (x: unknown): x is Persona => x === "family" || x === "leader" || x === "researcher" || x === "biotech";

let current: Persona | null = null;
const listeners = new Set<() => void>();

function read(): Persona {
  try {
    const q = new URLSearchParams(window.location.search).get("as");
    if (valid(q)) {
      localStorage.setItem(KEY, q);
      return q;
    }
    const s = localStorage.getItem(KEY);
    if (valid(s)) return s;
  } catch {
    // storage unavailable: default
  }
  return DEFAULT;
}

function getSnapshot(): Persona {
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
  current = p;
  try {
    localStorage.setItem(KEY, p);
  } catch {
    // keep it for this page view only
  }
  listeners.forEach((l) => l());
}

export function usePersona(): Persona {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT);
}
