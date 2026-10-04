"use client";

// Lazy loaders for the derived data products (fetched only by the pages that need them).
import { useEffect, useState } from "react";
import type { Evidence } from "./types";

const PATHS = {
  variants: "/data/derived/variants.json",
  modality: "/data/curated/modality.json",
  opportunities: "/data/derived/opportunities.json",
  beyond: "/data/derived/beyond_slice.json",
  counterexamples: "/data/derived/counterexamples.json",
  impact: "/data/curated/impact.json",
  mechsim: "/data/derived/mechsim.json",
} as const;
export type DerivedName = keyof typeof PATHS;

const cache = new Map<DerivedName, Promise<unknown>>();

export function loadDerived<T>(name: DerivedName): Promise<T> {
  let p = cache.get(name);
  if (!p) {
    p = fetch(PATHS[name], { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${PATHS[name]}: HTTP ${r.status}`);
      return r.json();
    });
    p.catch(() => cache.delete(name));
    cache.set(name, p);
  }
  return p as Promise<T>;
}

export type Loaded<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "missing"; error: string };

export function useDerived<T>(name: DerivedName): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    loadDerived<T>(name).then(
      (data) => alive && setState({ status: "ready", data }),
      (e: unknown) => alive && setState({ status: "missing", error: e instanceof Error ? e.message : String(e) }),
    );
    return () => {
      alive = false;
    };
  }, [name]);
  return state;
}

// ---------- shapes (only the fields the UI reads) ----------

export type Fit = "good" | "conditional" | "poor" | "not_assessed";

export interface ModalityCell {
  fit: Fit;
  reasons: { rule: string; votes: Fit; text: string }[];
  caveats: { rule: string; text: string }[];
  citation_ids: string[];
  graph_edge_ids: Record<string, string[]>;
  rules_fired: string[];
  open_questions_for_expert: string[];
}

export interface ModalityData {
  status: string;
  not_advice: string;
  meta: { fit_scale: Record<string, string>; aggregation: string };
  citations: Record<string, Evidence>;
  modalities: { id: string; label: string; what_it_does: string; best_case_mechanism: string }[];
  rules: { id: string; modality: string; condition: string; votes: Fit; reason: string; caveat?: string }[];
  assessments: Record<
    string,
    {
      gene: string;
      label: string;
      checks: {
        existing_programmes?: { therapy: string; label: string; modality: string; stage: string; edge_id?: string; edge_status?: string; trials: string[]; trial_status: string[]; why_stopped: string[] }[];
        stopped_programmes?: { therapy: string; trials: string[]; status: string[]; why_stopped: string[] }[];
        interventional_studies?: unknown;
        [k: string]: unknown;
      };
      modalities: Record<string, ModalityCell>;
    }
  >;
}

export interface Counterexample {
  id: string;
  title: string;
  plain_language: string;
  why_it_matters: string;
  edge_ids: string[];
}

export interface BeyondData {
  label: string;
  meta: { method: string; n_compared: number; excluded_rule?: string };
  diseases: Record<
    string,
    {
      neighbors: { id: string; name: string; genes: string[]; score: number; percentile: number; top_shared_terms: { hpo: string; name: string; ic: number; specificity: string }[] }[];
      note?: string;
    }
  >;
}

export interface OpportunityPair {
  shared_mechanism: string;
  shared_mechanism_label: string;
  has_model: string;
  has_model_label: string;
  assets: { asset: string; label: string; kind: string; edge_id: string }[];
  lacks_model?: string;
  lacks_model_label?: string;
  [k: string]: unknown;
}
