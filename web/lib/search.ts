import Fuse from "fuse.js";
import type { GraphIndex, SynonymEntry, SynonymKind } from "./graph";
import type { AtlasNode, NodeType } from "./types";

export interface SearchHit {
  node: AtlasNode;
  /** the term that matched (may be a synonym, protein name, subtype or ID) */
  matched: string;
  kind: SynonymKind;
  /** 0 = perfect, 1 = poor */
  score: number;
}

const TYPE_BOOST: Partial<Record<NodeType, number>> = {
  disease: -0.06,
  gene: -0.04,
  mechanism: -0.02,
  phenotype: -0.01,
  patient_org: -0.01,
};

const norm = (s: string) => s.toLowerCase().replace(/[\s_-]+/g, "");

export type Searcher = (query: string, limit?: number) => SearchHit[];

export function createSearcher(idx: GraphIndex): Searcher {
  const fuse = new Fuse<SynonymEntry>(idx.synonyms, {
    keys: ["term"],
    includeScore: true,
    ignoreLocation: true,
    threshold: 0.34,
    minMatchCharLength: 2,
  });
  const exact = new Map<string, SynonymEntry[]>();
  for (const e of idx.synonyms) {
    const k = norm(e.term);
    const arr = exact.get(k);
    if (arr) arr.push(e);
    else exact.set(k, [e]);
  }

  return (query: string, limit = 8) => {
    const q = query.trim();
    if (q.length < 2) return [];
    const nq = norm(q);
    const best = new Map<string, SearchHit>();
    const consider = (e: SynonymEntry, raw: number) => {
      const node = idx.nodeById.get(e.nodeId);
      if (!node) return;
      let score = raw;
      const nt = norm(e.term);
      if (nt === nq) score = 0;
      // "VAMP2" -> "VAMP2-related disorders": a whole-word prefix counts as exact, so the disease
      // (type boost) ranks above the bare gene for a gene-symbol query
      else if (e.term.toLowerCase().startsWith(q.toLowerCase()) && /^[\s\-–(]/.test(e.term.slice(q.length))) score = 0.005;
      else if (nt.startsWith(nq)) score = Math.min(score, 0.08);
      score += TYPE_BOOST[node.type] ?? 0;
      if (e.kind !== "label") score += 0.01; // prefer the canonical label on ties
      const prev = best.get(node.id);
      if (!prev || score < prev.score) best.set(node.id, { node, matched: e.term, kind: e.kind, score });
    };
    for (const e of exact.get(nq) ?? []) consider(e, 0);
    for (const r of fuse.search(q, { limit: 60 })) consider(r.item, r.score ?? 1);
    return [...best.values()].sort((a, b) => a.score - b.score).slice(0, limit);
  };
}

/** Completes the sentence "Matched …" under a resolved search hit. */
export const MATCH_KIND_LABEL: Record<SynonymKind, string> = {
  label: "the name",
  synonym: "a synonym",
  protein: "the protein this gene makes",
  subtype: "a clinical subtype",
  xref: "a database ID",
  gene: "the gene",
};
