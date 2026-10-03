// Server-side copy of the graph the browser sees (public/data/graph.json), re-read when the file changes.
// The AI routes build their prompts from this, never from evidence sent by the browser.
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { buildIndex, type GraphIndex } from "../graph";
import type { AtlasGraph } from "../types";

let cached: { mtimeMs: number; idx: GraphIndex } | null = null;

export async function serverGraph(): Promise<GraphIndex> {
  const file = path.join(process.cwd(), "public", "data", "graph.json");
  const s = await stat(file);
  if (cached && cached.mtimeMs === s.mtimeMs) return cached.idx;
  const idx = buildIndex(JSON.parse(await readFile(file, "utf8")) as AtlasGraph);
  cached = { mtimeMs: s.mtimeMs, idx };
  return idx;
}
