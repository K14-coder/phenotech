// Generates precomputed AI outputs for the deployed (precomputed-only) site.
//
// It drives the LOCAL dev server's /api/ai/generate route, so it uses exactly the same prompts,
// citation validation and signed-in session (Sign in with ChatGPT, or OPENAI_API_KEY) as the app.
// Output files: ../data/ai/<kind>--<safe id>.json  (sync-data copies them into public/data/ai/).
//
// Usage (from web/, with `npm run dev` running and `node ../integrations/openai/cli.mjs status` signed in):
//   node scripts/precompute-ai.mjs --dry-run                 # list targets, no model calls
//   node scripts/precompute-ai.mjs                           # proposal for every disease + explain-path pairs
//   node scripts/precompute-ai.mjs --only proposal --limit 1
//   node scripts/precompute-ai.mjs --only explain-path --pairs scripts/ai-targets.json
//   node scripts/precompute-ai.mjs --out /tmp/ai-test --force
//
// Options:
//   --only proposal|explain-path|compare-questions|experiment|outreach   one kind only
//   --limit N                      at most N model calls (default: no limit)
//   --pairs FILE                   targets JSON (default scripts/ai-targets.json):
//                                  explain-path {"from": "...", "to": "..."}, compare-questions {"kind": "compare-questions", "a": "...", "b": "..."}
//   --out DIR                      output directory (default ../data/ai)
//   --base URL                     dev server (default http://127.0.0.1:3000)
//   --ids VAMP2,STXBP1             only targets whose id contains one of these
//   --force                        regenerate files that already exist
//   --dry-run                      print the plan only
//
// Runs sequentially. Stops on usage or credit limits; backs off once on temporary errors.
// A ChatGPT Plus plan has a shared five-hour usage window: keep runs small.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : fallback;
};
const flag = (name) => args.includes(`--${name}`);

const base = opt("base", "http://127.0.0.1:3000").replace(/\/$/, "");
const outDir = resolve(opt("out", join(webRoot, "..", "data", "ai")));
const only = opt("only", null);
const limit = Number(opt("limit", "Infinity"));
const pairsFile = resolve(opt("pairs", join(webRoot, "scripts", "ai-targets.json")));
const dryRun = flag("dry-run");
const force = flag("force");
// --ids a,b: only targets whose id contains one of these strings (e.g. --ids VAMP2,STXBP1)
const idFilter = opt("ids", null)?.split(",").filter(Boolean) ?? null;

const fileName = (kind, id) => `${kind}--${id.replace(/[^A-Za-z0-9._-]/g, "_")}.json`;
const pathId = (from, to, hyp) => `${from}__to__${to}${hyp ? "__hyp" : ""}`;
const compareId = (a, b) => `${a}__vs__${b}`;

const graph = JSON.parse(readFileSync(join(webRoot, "public", "data", "graph.json"), "utf8"));
const nodeIds = new Set(graph.nodes.map((n) => n.id));

const targets = [];
if (!only || only === "proposal") {
  for (const n of graph.nodes.filter((n) => n.type === "disease")) targets.push({ kind: "proposal", id: n.id, payload: { id: n.id } });
}
const pairs = existsSync(pairsFile) ? JSON.parse(readFileSync(pairsFile, "utf8")) : [];
if (!only || only === "experiment") {
  for (const p of (Array.isArray(pairs) ? pairs : []).filter((x) => x.kind === "experiment")) {
    if (!graph.edges.some((e) => e.id === p.id && e.type === "candidate_for")) {
      console.warn(`skip experiment ${p.id}: no candidate_for edge with that id`);
      continue;
    }
    targets.push({ kind: "experiment", id: p.id, payload: { id: p.id } });
  }
}
if (!only || only === "outreach") {
  for (const p of (Array.isArray(pairs) ? pairs : []).filter((x) => x.kind === "outreach")) {
    if (!nodeIds.has(p.id)) {
      console.warn(`skip outreach ${p.id}: not in graph.json`);
      continue;
    }
    targets.push({ kind: "outreach", id: p.id, payload: { id: p.id } });
  }
}
if (!only || only === "compare-questions") {
  for (const p of (Array.isArray(pairs) ? pairs : []).filter((x) => x.kind === "compare-questions")) {
    if (!nodeIds.has(p.a) || !nodeIds.has(p.b)) {
      console.warn(`skip compare ${p.a} vs ${p.b}: not in graph.json`);
      continue;
    }
    targets.push({ kind: "compare-questions", id: compareId(p.a, p.b), payload: { a: p.a, b: p.b } });
  }
}
if (!only || only === "explain-path") {
  for (const p of (Array.isArray(pairs) ? pairs : []).filter((x) => !x.kind || x.kind === "explain-path")) {
    if (!nodeIds.has(p.from) || !nodeIds.has(p.to)) {
      console.warn(`skip pair ${p.from} -> ${p.to}: not in graph.json`);
      continue;
    }
    const hyp = p.includeHypotheses === true;
    targets.push({ kind: "explain-path", id: pathId(p.from, p.to, hyp), payload: { from: p.from, to: p.to, includeHypotheses: hyp } });
  }
}

console.log(`${targets.length} target(s); output ${outDir}${graph.meta?.sample ? " (WARNING: graph.json is SAMPLE data)" : ""}`);
if (dryRun) {
  for (const t of targets) console.log(`  ${t.kind}  ${t.id}  -> ${fileName(t.kind, t.id)}`);
  process.exit(0);
}

const status = await fetch(`${base}/api/ai/status`).then((r) => r.json()).catch(() => null);
if (!status || status.mode !== "live") {
  console.error(`No live AI at ${base}. Start the dev server (npm run dev) on this machine.`);
  process.exit(1);
}
if (status.authPath === "none") {
  console.error("Not signed in: run `node integrations/openai/cli.mjs login` (or set OPENAI_API_KEY) first.");
  process.exit(1);
}
console.log(`auth path: ${status.authPath}${status.authPath === "chatgpt" ? " (uses your ChatGPT plan; Plus has a shared five-hour limit)" : ""}`);

mkdirSync(outDir, { recursive: true });
let calls = 0;
for (const t of targets.filter((t) => !idFilter || idFilter.some((f) => t.id.includes(f)))) {
  const file = join(outDir, fileName(t.kind, t.id));
  if (!force && existsSync(file)) {
    console.log(`= ${t.kind} ${t.id} (exists, use --force)`);
    continue;
  }
  if (calls >= limit) break;
  let attempt = 0;
  for (;;) {
    calls++;
    const started = Date.now();
    const r = await fetch(`${base}/api/ai/generate`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: base },
      body: JSON.stringify({ kind: t.kind, payload: t.payload }),
    });
    const body = await r.json().catch(() => ({}));
    if (r.ok && Array.isArray(body.sections)) {
      writeFileSync(file, JSON.stringify(body, null, 2) + "\n");
      console.log(`+ ${t.kind} ${t.id} (${body.model}, ${((Date.now() - started) / 1000).toFixed(1)}s, ${body.dropped_citations ?? 0} citation(s) dropped)`);
      break;
    }
    const e = body.error ?? { kind: `http_${r.status}`, message: r.statusText };
    if (["usage_limit", "rate_limited", "credits_exhausted"].includes(e.kind)) {
      console.error(`! stopping: ${e.message}${e.action?.url ? ` (${e.action.url})` : ""}`);
      process.exit(2);
    }
    if (e.kind === "temporarily_unavailable" && attempt++ < 1 && calls < limit) {
      console.warn(`~ ${t.kind} ${t.id}: ${e.message}; retrying in 30s`);
      await new Promise((res) => setTimeout(res, 30_000));
      continue;
    }
    console.error(`x ${t.kind} ${t.id}: [${e.kind}] ${e.message}`);
    break;
  }
}
console.log(`done: ${calls} call(s). Run \`npm run sync-data\` (or restart dev) to copy them into public/data/ai/.`);
