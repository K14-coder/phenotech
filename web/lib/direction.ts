"use client";

// Direction flag (eval.md section 6): a drug that lowers its target's function suits a disease with too much of it,
// and a drug that raises function suits too little. Shown ONLY when the drug's direct target is the disease gene,
// and per variant group where one gene mixes both directions. A flag, never a score.
import { loadAvailableOnce } from "./population";
import { useResource } from "./resource";

export interface DirectionData {
  generated: string | null;
  therapies: Record<string, { d: "increase" | "decrease"; t: string[]; b: string | null }>;
  diseases: Record<string, { g: string; d: "LoF" | "GoF" | "mixed" | null }>;
  vgs: Record<string, { g: string; d: "LoF" | "GoF" | "mixed" | null }>;
}

export interface DirectionFlag {
  fits: boolean;
  gene: string;
  drug: "increase" | "decrease";
  disease: "LoF" | "GoF";
  /** variant group id when the flag is for one group of changes */
  vg?: string;
}

async function load(): Promise<DirectionData | null> {
  const a = await loadAvailableOnce();
  if (!a.direction) return null;
  const r = await fetch("/data/derived/web/direction.json");
  return r.ok ? ((await r.json()) as DirectionData) : null;
}

export function useDirection(): DirectionData | null {
  return useResource<DirectionData | null>("web:direction", load)?.data ?? null;
}

function flagFor(t: DirectionData["therapies"][string] | undefined, target: { g: string; d: string | null } | undefined, vg?: string): DirectionFlag | null {
  if (!t || !target || (target.d !== "LoF" && target.d !== "GoF") || !t.t.includes(target.g)) return null;
  const fits = (t.d === "decrease" && target.d === "GoF") || (t.d === "increase" && target.d === "LoF");
  return { fits, gene: target.g, drug: t.d, disease: target.d, vg };
}

/** Disease-level flag, or, when the gene mixes directions, one flag per variant group of that gene. */
export function directionFor(data: DirectionData | null, therapyId: string, diseaseId: string): DirectionFlag[] {
  if (!data) return [];
  const t = data.therapies[therapyId];
  const d = data.diseases[diseaseId];
  if (!t || !d || !t.t.includes(d.g)) return [];
  const one = flagFor(t, d);
  if (one) return [one];
  return Object.entries(data.vgs)
    .filter(([, v]) => v.g === d.g)
    .map(([id, v]) => flagFor(t, v, id))
    .filter((f): f is DirectionFlag => !!f);
}

export function directionForVg(data: DirectionData | null, therapyId: string, vgId: string): DirectionFlag | null {
  if (!data) return null;
  return flagFor(data.therapies[therapyId], data.vgs[vgId], vgId);
}

/** Therapies with a direct target in this gene (for variant results). */
export function therapiesForGene(data: DirectionData | null, gene: string): string[] {
  if (!data) return [];
  return Object.entries(data.therapies)
    .filter(([, t]) => t.t.includes(gene))
    .map(([id]) => id);
}
