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

// global disease index (every rare disease, basic data; see data/derived/global/README.md), folder
// structure kept: index.json, meta.json, neighbours/<0-63>.json and any later shard folders
//   ../data/derived/global/**/*.json -> public/data/derived/global/**
const copyTree = (from, to) => {
  const out = { files: 0, bytes: 0, skipped: 0 };
  if (!existsSync(from)) return out;
  mkdirSync(to, { recursive: true });
  for (const ent of readdirSync(from, { withFileTypes: true })) {
    const s = join(from, ent.name);
    const d = join(to, ent.name);
    if (ent.isDirectory()) {
      const sub = copyTree(s, d);
      out.files += sub.files;
      out.bytes += sub.bytes;
      out.skipped += sub.skipped;
    } else if (ent.name.endsWith(".json")) {
      const text = readFileSync(s, "utf8");
      try {
        JSON.parse(text);
      } catch (err) {
        console.warn(`[sync-data] skipping global/${ent.name}: not valid JSON (${err.message})`);
        out.skipped++;
        continue;
      }
      copyFileSync(s, d);
      out.files++;
      out.bytes += Buffer.byteLength(text);
    }
  }
  return out;
};
{
  const g = copyTree(join(dataRoot, "derived", "global"), join(webRoot, "public", "data", "derived", "global"));
  if (g.files) console.log(`[sync-data] copied ${g.files} global index file(s), ${(g.bytes / 1e6).toFixed(1)} MB${g.skipped ? `, ${g.skipped} skipped` : ""}`);
}

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
