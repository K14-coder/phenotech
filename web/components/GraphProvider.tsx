"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { loadGraph, type GraphIndex } from "@/lib/graph";
import { createSearcher, type Searcher } from "@/lib/search";

type AtlasState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; idx: GraphIndex; search: Searcher };

const Ctx = createContext<AtlasState>({ status: "loading" });
const ReloadCtx = createContext<() => Promise<GraphIndex | null>>(async () => null);

/** Re-fetch graph.json (no-store) and re-index, without a page refresh. */
export function useGraphReload() {
  return useContext(ReloadCtx);
}

export function GraphProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AtlasState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    // Dev-only: ?graph=<name> loads public/data/fixtures/<name>.json (e.g. review-demo). Ignored in production.
    const fixture = process.env.NODE_ENV !== "production" ? new URLSearchParams(window.location.search).get("graph") : null;
    const url = fixture && /^[a-z0-9-]+$/.test(fixture) ? `/data/fixtures/${fixture}.json` : undefined;
    loadGraph(url)
      .then((idx) => {
        if (!alive) return;
        if (idx.warnings.length) console.warn("[atlas] data warnings:", idx.warnings);
        setState({ status: "ready", idx, search: createSearcher(idx) });
      })
      .catch((err: unknown) => {
        if (alive) setState({ status: "error", error: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      alive = false;
    };
  }, []);
  const reload = useCallback(async () => {
    try {
      const fixture = process.env.NODE_ENV !== "production" ? new URLSearchParams(window.location.search).get("graph") : null;
      const idx = await loadGraph(fixture && /^[a-z0-9-]+$/.test(fixture) ? `/data/fixtures/${fixture}.json` : undefined, { fresh: true });
      setState({ status: "ready", idx, search: createSearcher(idx) });
      return idx;
    } catch {
      return null;
    }
  }, []);
  return (
    <ReloadCtx.Provider value={reload}>
      <Ctx.Provider value={state}>{children}</Ctx.Provider>
    </ReloadCtx.Provider>
  );
}

export function useAtlas(): AtlasState {
  return useContext(Ctx);
}

/** Renders children only once the graph is loaded; shows calm loading / error states otherwise. */
export function WithGraph({
  children,
  fallback,
}: {
  children: (idx: GraphIndex, search: Searcher) => React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const s = useAtlas();
  if (s.status === "ready") return <>{children(s.idx, s.search)}</>;
  if (s.status === "error") {
    return (
      <div className="mx-auto max-w-xl px-6 py-24 text-center">
        <p className="text-sm font-medium text-ink">The atlas data could not be loaded.</p>
        <p className="mt-2 text-sm text-ink-3">{s.error}</p>
        <p className="mt-4 text-sm text-ink-3">
          Check that <code className="rounded bg-subtle px-1">public/data/graph.json</code> exists and is valid JSON.
        </p>
      </div>
    );
  }
  return (
    <>
      {fallback ?? (
        <div className="flex flex-1 items-center justify-center py-24" role="status" aria-live="polite">
          <span className="text-sm text-ink-3">Loading the atlas…</span>
        </div>
      )}
    </>
  );
}
