// Copies the merged graph produced by the pipeline into the web app.
//   ../data/graph.json  ->  public/data/graph.json   (only if the source exists)
//   ../data/ai/*.json   ->  public/data/ai/           (optional precomputed AI outputs)
// If ../data/graph.json is missing, the committed sample graph stays in place.
// Runs automatically before `npm run dev` and `npm run build`.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const dataRoot = join(webRoot, "..", "data");
const src = join(dataRoot, "graph.json");
const dest = join(webRoot, "public", "data", "graph.json");

if (existsSync(src)) {
  try {
    const g = JSON.parse(readFileSync(src, "utf8"));
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
    console.log(
      `[sync-data] copied ../data/graph.json (${g.nodes?.length ?? "?"} nodes, ${g.edges?.length ?? "?"} edges${g.meta?.sample ? ", sample" : ""})`,
    );
  } catch (err) {
    console.warn(`[sync-data] ../data/graph.json is not valid JSON, keeping the existing file: ${err.message}`);
  }
} else {
  console.log("[sync-data] ../data/graph.json not found, using public/data/graph.json as is");
}

// derived data products (lazy-loaded by the pages that need them)
//   ../data/derived/*.json            -> public/data/derived/
//   ../data/curated/{modality,impact}.json -> public/data/curated/
const copyJson = (from, toDir, names) => {
  if (!existsSync(from)) return 0;
  mkdirSync(toDir, { recursive: true });
  let n = 0;
  for (const f of names ?? readdirSync(from).filter((x) => x.endsWith(".json"))) {
    const src = join(from, f);
    if (!existsSync(src)) continue;
    try {
      JSON.parse(readFileSync(src, "utf8"));
    } catch (err) {
      console.warn(`[sync-data] skipping ${f}: not valid JSON (${err.message})`);
      continue;
    }
    copyFileSync(src, join(toDir, f));
    n++;
  }
  return n;
};
const nDerived = copyJson(join(dataRoot, "derived"), join(webRoot, "public", "data", "derived"));
const nCurated = copyJson(join(dataRoot, "curated"), join(webRoot, "public", "data", "curated"), ["modality.json", "impact.json"]);
if (nDerived || nCurated) console.log(`[sync-data] copied ${nDerived} derived and ${nCurated} curated file(s)`);

const aiSrc = join(dataRoot, "ai");
if (existsSync(aiSrc)) {
  const aiDest = join(webRoot, "public", "data", "ai");
  mkdirSync(aiDest, { recursive: true });
  let n = 0;
  for (const f of readdirSync(aiSrc)) {
    if (f.endsWith(".json")) {
      copyFileSync(join(aiSrc, f), join(aiDest, f));
      n++;
    }
  }
  console.log(`[sync-data] copied ${n} precomputed AI file(s) from ../data/ai`);
}

// public/data/ai/index.json lists the precomputed AI files that exist, so the app never probes
// for missing ones (each probe would log a 404 in the browser console)
{
  const aiDir = join(webRoot, "public", "data", "ai");
  mkdirSync(aiDir, { recursive: true });
  const files = readdirSync(aiDir)
    .filter((f) => f.endsWith(".json") && f !== "index.json")
    .sort();
  writeFileSync(join(aiDir, "index.json"), JSON.stringify({ generated: new Date().toISOString().slice(0, 10), files }, null, 2) + "\n");
  console.log(`[sync-data] public/data/ai/index.json lists ${files.length} precomputed AI file(s)`);
}
