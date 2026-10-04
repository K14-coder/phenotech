// Precomputed AI drafts written by a Claude agent instead of the OpenAI route, through the same
// evidence packs and the same citation validation as /api/ai/generate.
//
//   node scripts/agent-ai.mjs --emit DIR --only outreach [--ids VAMP2,SCN2A] [--force]
//       Writes DIR/<file>.task.json for every target without a precomputed file: {kind, id, instructions,
//       input, schema}. `instructions` and `input` are exactly what the app would send to the model
//       (lib/ai-tasks.ts buildTask on public/data/graph.json).
//   node scripts/agent-ai.mjs --apply DIR
//       For every DIR/<file>.answer.json ({title, sections:[{heading, sentences:[{text, edge_ids}]}]}),
//       rebuilds the task, runs sanitizeDoc (citations must point at connections in that task's
//       input; others are dropped), and writes ../data/ai/<file> with model "Claude (agent draft)".
//
// lib/*.ts is transpiled to CommonJS in a temp directory with the project's TypeScript, so the
// script runs with plain Node. Kinds: proposal, outreach, explain-path, compare-questions, experiment
// (targets for the last three come from scripts/ai-targets.json, as in precompute-ai.mjs).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : fallback;
};
const flag = (name) => args.includes(`--${name}`);
export const AGENT_MODEL = "Claude (agent draft)";

const outDir = resolve(join(webRoot, "..", "data", "ai"));
const build = join(tmpdir(), "atlas-agent-ai");
execFileSync(join(webRoot, "node_modules", ".bin", "tsc"), [
  join(webRoot, "lib", "ai-tasks.ts"), "--outDir", build, "--module", "commonjs", "--target", "es2022",
  "--skipLibCheck", "--esModuleInterop", "--resolveJsonModule",
], { stdio: "inherit" });
const require = createRequire(import.meta.url);
const tasks = require(join(build, "ai-tasks.js"));
const { buildIndex } = require(join(build, "graph.js"));
const { aiFileName, compareAiId, pathAiId } = require(join(build, "ai-shared.js"));

const idx = buildIndex(JSON.parse(readFileSync(join(webRoot, "public", "data", "graph.json"), "utf8")));
const pairs = JSON.parse(readFileSync(join(webRoot, "scripts", "ai-targets.json"), "utf8"));

function targets(only) {
  const out = [];
  const diseases = idx.graph.nodes.filter((n) => n.type === "disease");
  if (!only || only === "proposal") for (const n of diseases) out.push({ kind: "proposal", id: n.id, payload: { id: n.id } });
  if (!only || only === "outreach") for (const n of diseases) out.push({ kind: "outreach", id: n.id, payload: { id: n.id } });
  for (const p of pairs) {
    const kind = p.kind ?? "explain-path";
    if (only && only !== kind) continue;
    if (kind === "explain-path") out.push({ kind, id: pathAiId(p.from, p.to, !!p.includeHypotheses), payload: p });
    else if (kind === "compare-questions") out.push({ kind, id: compareAiId(p.a, p.b), payload: p });
    else if (kind === "experiment" && p.edge) out.push({ kind, id: p.edge, payload: p });
  }
  return out;
}

if (opt("emit")) {
  const dir = resolve(opt("emit"));
  mkdirSync(dir, { recursive: true });
  const ids = opt("ids", null)?.split(",").filter(Boolean);
  let n = 0;
  for (const t of targets(opt("only", null))) {
    if (ids && !ids.some((x) => t.id.includes(x))) continue;
    const file = aiFileName(t.kind, t.id);
    if (existsSync(join(outDir, file)) && !flag("force")) continue;
    const built = tasks.buildTask(idx, t.kind, t.payload);
    if (built.error) {
      console.log(`  skip ${t.kind} ${t.id}: ${built.error}`);
      continue;
    }
    const { task } = built;
    writeFileSync(join(dir, file.replace(/\.json$/, ".task.json")), `${JSON.stringify({
      kind: task.kind, id: task.id, payload: t.payload, instructions: task.instructions, input: task.input, schema: tasks.AI_DOC_SCHEMA,
    }, null, 1)}\n`);
    n += 1;
  }
  console.log(`[agent-ai] wrote ${n} task file(s) to ${dir}`);
} else if (opt("apply")) {
  const dir = resolve(opt("apply"));
  let n = 0;
  for (const f of readdirSync(dir).filter((x) => x.endsWith(".answer.json"))) {
    const t = JSON.parse(readFileSync(join(dir, f.replace(/\.answer\.json$/, ".task.json")), "utf8"));
    const built = tasks.buildTask(idx, t.kind, t.payload);
    if (built.error) throw new Error(`${f}: ${built.error}`);
    if (built.task.input !== t.input) throw new Error(`${f}: the graph changed since --emit; re-emit and redraft`);
    const { doc, dropped } = tasks.sanitizeDoc(JSON.parse(readFileSync(join(dir, f), "utf8")), built.task.refs);
    const sentences = doc.sections.reduce((s, x) => s + x.sentences.length, 0);
    const cited = doc.sections.reduce((s, x) => s + x.sentences.filter((y) => y.edge_ids.length).length, 0);
    const file = aiFileName(t.kind, t.id);
    writeFileSync(join(outDir, file), `${JSON.stringify({
      kind: t.kind, id: t.id, model: AGENT_MODEL, generated_at: new Date().toISOString(), dropped_citations: dropped, ...doc,
    }, null, 2)}\n`);
    console.log(`  ${file}: ${sentences} sentences, ${cited} cited, ${dropped} citation(s) dropped`);
    n += 1;
  }
  console.log(`[agent-ai] wrote ${n} draft(s) to ${outDir}`);
} else {
  console.log("usage: node scripts/agent-ai.mjs --emit DIR [--only KIND] [--ids A,B] [--force] | --apply DIR");
}
