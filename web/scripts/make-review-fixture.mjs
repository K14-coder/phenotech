// Dev-only test fixture for the review fields in docs/SCHEMA.md (cross_checked, needs_review, review).
// Copies public/data/graph.json, adds FIXTURE values to two edges, marks it as sample data, and writes
// public/data/fixtures/review-demo.json (gitignored). View it in `npm run dev` with:
//   http://127.0.0.1:3000/disease/VAMP2?graph=review-demo   (the ?graph= switch is ignored in production)
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const g = JSON.parse(readFileSync(join(web, "public", "data", "graph.json"), "utf8"));
const today = new Date().toISOString().slice(0, 10);

const withEvidence = g.edges.filter((e) => Array.isArray(e.evidence) && e.evidence.length > 0);
const agreeEdge =
  withEvidence.find((e) => e.type === "shares_mechanism" && (e.source === "disease:VAMP2" || e.target === "disease:VAMP2")) ?? withEvidence[0];
const disagreeEdge = withEvidence.find((e) => e !== agreeEdge && e.evidence.some((ev) => ev.quote) && e.type === "driven_by") ?? withEvidence[1];

agreeEdge.evidence[0] = { ...agreeEdge.evidence[0], cross_checked: { by: "openai:gpt-6-astra", agrees: true, date: today } };
agreeEdge.review = { by: "human:biochemist", date: today, verdict: "confirmed", note: "FIXTURE: example review note, not a real review." };

const q = disagreeEdge.evidence.findIndex((ev) => ev.quote) >= 0 ? disagreeEdge.evidence.findIndex((ev) => ev.quote) : 0;
disagreeEdge.evidence[q] = { ...disagreeEdge.evidence[q], cross_checked: { by: "openai:gpt-6-astra", agrees: false, date: today } };
disagreeEdge.counter_evidence = [
  ...(disagreeEdge.counter_evidence ?? []),
  {
    ...disagreeEdge.evidence[q],
    supports: false,
    needs_review: true,
    verified: false,
    extracted_by: "openai:gpt-6-astra",
    quote: "FIXTURE: example sentence the AI re-reading flagged as limiting. Not a real quote.",
    cross_checked: undefined,
  },
];

// community contribution (pipeline/contribute shapes): a new asset + covers edge, and a new source on an existing node
const contributed = { by: "FIXTURE contributor", date: today, url: "https://example.org/fixture-contribution" };
const fixtureQuote = "FIXTURE: example sentence a contributor quoted from a page. Not a real quote.";
g.nodes.push({
  id: "asset:fixture-contributed-biobank",
  type: "asset",
  label: "FIXTURE contributed biobank",
  summary: "FIXTURE: a community-contributed resource, used to check how contributions are shown.",
  attrs: { kind: "biobank", url: contributed.url, contributed },
  sources: [{ source: "Website", ref: contributed.url, url: contributed.url, title: "FIXTURE page", quote: fixtureQuote, kind: "website", extracted_by: "human:FIXTURE contributor", verified: true, retrieved: today }],
});
g.edges.push({
  id: "asset:fixture-contributed-biobank|covers|disease:VAMP2",
  source: "asset:fixture-contributed-biobank",
  target: "disease:VAMP2",
  type: "covers",
  label: "covers",
  explanation: "FIXTURE: the contributed page says this biobank accepts VAMP2 samples.",
  evidence_level: "observational",
  status: "unverified",
  confidence: 0.4,
  evidence: [{ source: "Website", ref: contributed.url, url: contributed.url, title: "FIXTURE page", quote: fixtureQuote, kind: "website", extracted_by: "human:FIXTURE contributor", verified: true, retrieved: today }],
  attrs: { contributed, basis: "page" },
});
const existing = g.nodes.find((n) => n.type === "asset" && n.id !== "asset:fixture-contributed-biobank");
if (existing) existing.attrs = { ...(existing.attrs ?? {}), contributed_sources: [contributed] };

g.meta = { ...g.meta, version: `${g.meta?.version ?? "?"}+review-fixture`, sample: true };
const out = join(web, "public", "data", "fixtures", "review-demo.json");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(g));
console.log(`wrote ${out}\n  agrees + review: ${agreeEdge.id}\n  disagrees + needs_review: ${disagreeEdge.id}`);
