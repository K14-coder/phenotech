// Runs the TypeScript variant parser (lib/variant.ts) against data/derived/variant_test_cases.json,
// comparing exactly the keys the Python reference harness compares (pipeline/derive/variants.py).
// Usage: node scripts/test-variants.mjs   (Node 23.6+ strips the TypeScript types natively)
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { lookupVariant } from "../lib/variant.ts";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const pick = (...paths) => paths.find((p) => existsSync(p));
const dataPath = pick(join(web, "public/data/derived/variants.json"), join(web, "../data/derived/variants.json"));
const casesPath = pick(join(web, "public/data/derived/variant_test_cases.json"), join(web, "../data/derived/variant_test_cases.json"));
if (!dataPath || !casesPath) {
  console.error("variants.json or variant_test_cases.json not found (run npm run sync-data)");
  process.exit(1);
}
const data = JSON.parse(readFileSync(dataPath, "utf8"));
const { cases } = JSON.parse(readFileSync(casesPath, "utf8"));

let bad = 0;
for (const c of cases) {
  const r = lookupVariant(c.query, data);
  const got = { status: r.status };
  if (r.matches.length) {
    const m = r.matches[0];
    Object.assign(got, { gene: m.gene, accession: m.accession, consequence: m.consequence, variant_group: m.variant_group });
  }
  if (r.fallback) Object.assign(got, { consequence: r.fallback.consequence, variant_group: r.fallback.variant_group });
  const diffs = Object.entries(c.expected).filter(([k, v]) => (k in got || k === "accession" || k === "gene") && got[k] !== v);
  const ok = diffs.length === 0;
  if (!ok) bad++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.query.padEnd(44)} ${r.status}${r.matches[0] ? " " + r.matches[0].accession : ""}${r.fallback ? " " + r.fallback.consequence + " -> " + r.fallback.variant_group : ""}${ok ? "" : "  " + JSON.stringify(diffs)}`);
}
console.log(`\n${cases.length - bad}/${cases.length} pass`);
process.exit(bad ? 1 : 0);
