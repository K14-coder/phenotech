"use client";

// Per-factor breakdown for one pair of diseases: the 7-segment bar plus the strongest factors in words.
// Atlas pairs use mechsim; other pairs pass precomputed scores.
import { useDerived } from "@/lib/derived";
import { mechsimIndex, mechsimScores, strongest, topTypes, type FactorKey, type FactorScores, type MechsimData } from "@/lib/factors";
import { FactorBar } from "./FactorBits";
import { useAtlas } from "../GraphProvider";

export function useMechsim() {
  const ms = useDerived<MechsimData>("mechsim");
  return ms.status === "ready" ? mechsimIndex(ms.data) : null;
}

/** Words for an atlas pair's strongest factors, from mechsim profiles and graph edge details. */
export function pairWords(ix: ReturnType<typeof useMechsim>, a: string, b: string): Partial<Record<FactorKey, string>> {
  if (!ix) return {};
  const pa = ix.data.profiles[ix.byId.get(a) ?? -1];
  const pb = ix.data.profiles[ix.byId.get(b) ?? -1];
  if (!pa || !pb) return {};
  const words: Partial<Record<FactorKey, string>> = {};
  const sharedGenes = pa.genes.filter((g) => pb.genes.includes(g));
  if (sharedGenes.length) words.gene = `same gene: ${sharedGenes.slice(0, 2).join(", ")}`;
  const sharedPw = pa.pathways
    .filter((p) => pb.pathways.includes(p))
    .map((p) => ix.data.pathway_sets[p])
    .filter(Boolean)
    .sort((x, y) => x.size - y.size);
  if (sharedPw.length) words.pathway = `same pathway: ${sharedPw[0].name}`;
  const ta = new Set((pa.tissue?.symptoms ?? []).slice(0, 2).map(([t]) => t));
  const tShared = (pb.tissue?.symptoms ?? []).slice(0, 2).map(([t]) => t).find((t) => ta.has(t));
  if (tShared) words.tissue = `same tissue: ${tShared.replace(/ \(.*\)$/, "")}`;
  const p = ix.pair(a, b);
  if (p?.tm_score != null) words.structure = `similar structure (TM-score ${p.tm_score.toFixed(2)})`;
  const pf = (pa.structure?.pfam ?? []).filter((x) => (pb.structure?.pfam ?? []).includes(x));
  if (pf.length) words.structure = `same protein family: ${ix.data.pfam[pf[0]]?.name ?? pf[0]}${p?.tm_score != null ? ` (TM-score ${p.tm_score.toFixed(2)})` : ""}`;
  if (p?.mutation != null) words.mutation = mutationWords(pa.mutation?.types, pb.mutation?.types) ?? "similar mix of mutation types";
  if (p?.fate != null) words.fate = `same molecular consequence (${Math.round(p.fate * 100)}%)`;
  return words;
}

/** What kind of DNA change causes each disease: "both mostly substitutions" or "substitutions vs deletions". */
export function mutationWords(a: Record<string, number> | null | undefined, b: Record<string, number> | null | undefined): string | null {
  const ta = topTypes(a, 1)[0];
  const tb = topTypes(b, 1)[0];
  if (!ta || !tb) return null;
  return ta.key === tb.key ? `both mostly ${ta.words}` : `mostly ${ta.words} vs mostly ${tb.words}`;
}

export function PairFactorsView({ scores, words }: { scores: FactorScores; words?: Partial<Record<FactorKey, string>> }) {
  const top = strongest(scores, words ?? {});
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      <FactorBar scores={scores} size="sm" />
      {top.length > 0 && <span className="text-xs text-ink-3">{top.join("; ")}</span>}
    </div>
  );
}

/** Atlas pair: reads mechsim; renders nothing when the pair is not covered. */
export function AtlasPairFactors({ a, b }: { a: string; b: string }) {
  const ix = useMechsim();
  const atlas = useAtlas();
  if (!ix) return null;
  const s = mechsimScores(ix, a, b, atlas.status === "ready" ? atlas.idx : undefined);
  if (!s) return null;
  return <PairFactorsView scores={s} words={pairWords(ix, a, b)} />;
}
