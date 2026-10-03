/**
 * Shared helpers for the OpenAI cross-check layer (extract -> reconcile -> compare).
 * Dependency-free Node ESM. Paths are resolved from this file, so scripts run from any cwd.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const RAW_BIO_PUBMED = path.join(ROOT, 'data/raw/biology/pubmed');
export const RAW_COMMUNITY_PUBMED = path.join(ROOT, 'data/raw/community/pubmed');
export const OUT_RAW = path.join(ROOT, 'data/raw/openai');
export const EXTRACTIONS = path.join(OUT_RAW, 'extractions');
export const RECONCILE_CACHE = path.join(OUT_RAW, 'reconcile');
export const GRAPH = process.env.ATLAS_GRAPH ?? path.join(ROOT, 'data/graph.json'); // override only for tests
export const CROSSCHECK = path.join(ROOT, 'data/build/crosscheck.json');
export const FRAGMENT = path.join(ROOT, 'data/curated/openai_extracted.json');
export const REPORT = path.join(ROOT, 'docs/agent-reports/openai-extraction.md');
export const USAGE_LOG = path.join(OUT_RAW, 'usage_log.jsonl');
export const RUN_STATE = path.join(OUT_RAW, 'run_state.json');

export const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));
export function writeJson(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp-${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(value, null, 1)}\n`);
  renameSync(tmp, file);
}
export const sha1 = (text) => createHash('sha1').update(text).digest('hex').slice(0, 16);
export const today = () => new Date().toISOString().slice(0, 10);

// ---------------------------------------------------------------------------
// Text normalisation (same folding as pipeline/biology/verify_quotes.py)
// ---------------------------------------------------------------------------

/** NFKC, dash and curly-quote folding, whitespace collapse. Case is preserved: quotes must be verbatim. */
export function norm(text) {
  return String(text ?? '')
    .normalize('NFKC')
    .replace(/[‐-―−]/g, '-')
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
}

/** Is `quote` a verbatim substring of `source` after normalisation? Never edits the quote. */
export const isVerbatim = (quote, source) => {
  const q = norm(quote);
  return q.length > 0 && norm(source).includes(q);
};

// ---------------------------------------------------------------------------
// Abstract sources
// ---------------------------------------------------------------------------

/** Stored biology abstracts: data/raw/biology/pubmed/<PMID>.json (title + abstract as fetched). */
export function loadBiologyAbstracts() {
  return readdirSync(RAW_BIO_PUBMED)
    .filter((f) => /^\d+\.json$/.test(f))
    .sort()
    .map((f) => {
      const r = readJson(path.join(RAW_BIO_PUBMED, f));
      return {
        pmid: String(r.pmid), title: r.title ?? '', abstract: r.abstract ?? '', year: r.year ?? null,
        journal: r.journal ?? null, pub_types: r.pub_types ?? [], url: r.url ?? `https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`,
        origin: `data/raw/biology/pubmed/${f}`,
      };
    })
    .filter((r) => r.abstract.trim());
}

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
function decodeXml(text) {
  return text.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);/g, (whole, body) => {
    if (body[0] === '#') {
      const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    }
    return ENTITIES[body] ?? whole;
  });
}
// Same as Python's " ".join("".join(el.itertext()).split()): drop inline tags, then collapse whitespace.
const xmlText = (fragment) => decodeXml(String(fragment ?? '').replace(/<[^>]+>/g, '')).split(/\s+/).filter(Boolean).join(' ');

/**
 * PubMed efetch XML saved by pipeline/community/fetch_pubmed.py (batches joined by "<!-- batch -->").
 * Only records with a non-empty <Abstract> are returned. Title/abstract are assembled the same way as
 * pipeline/biology/pubmed.py ("LABEL: text" sections joined by spaces).
 */
export function loadCommunityAbstracts() {
  const out = new Map();
  if (!existsSync(RAW_COMMUNITY_PUBMED)) return [];
  for (const file of readdirSync(RAW_COMMUNITY_PUBMED).filter((f) => f.endsWith('.efetch.xml')).sort()) {
    const gene = file.split('.')[0];
    const raw = readFileSync(path.join(RAW_COMMUNITY_PUBMED, file), 'utf8');
    for (const match of raw.matchAll(/<PubmedArticle>([\s\S]*?)<\/PubmedArticle>/g)) {
      const art = match[1];
      const pmid = art.match(/<PMID[^>]*>(\d+)<\/PMID>/)?.[1];
      if (!pmid) continue;
      const title = xmlText(art.match(/<ArticleTitle[^>]*>([\s\S]*?)<\/ArticleTitle>/)?.[1] ?? '');
      const absBlock = art.match(/<Abstract>([\s\S]*?)<\/Abstract>/)?.[1] ?? '';
      const sections = [...absBlock.matchAll(/<AbstractText([^>]*?)(?:\/>|>([\s\S]*?)<\/AbstractText>)/g)].map((m) => ({
        label: m[1].match(/Label="([^"]*)"/)?.[1] ?? null,
        text: xmlText(m[2] ?? ''),
      }));
      const abstract = sections.filter((s) => s.text).map((s) => (s.label ? `${decodeXml(s.label)}: ` : '') + s.text).join(' ');
      if (!abstract.trim()) continue;
      const journalBlock = art.match(/<Journal>([\s\S]*?)<\/Journal>/)?.[1] ?? '';
      const yearText = journalBlock.match(/<PubDate>[\s\S]*?<Year>(\d{4})<\/Year>/)?.[1]
        ?? journalBlock.match(/<MedlineDate>(\d{4})/)?.[1] ?? art.match(/<ArticleDate[^>]*>\s*<Year>(\d{4})<\/Year>/)?.[1];
      const pubTypes = [...art.matchAll(/<PublicationType[^>]*>([\s\S]*?)<\/PublicationType>/g)].map((m) => xmlText(m[1]));
      const prev = out.get(pmid);
      if (prev) {
        prev.genes.push(gene);
        continue;
      }
      out.set(pmid, {
        pmid, title, abstract, year: yearText ? Number(yearText) : null,
        journal: xmlText(journalBlock.match(/<Title>([\s\S]*?)<\/Title>/)?.[1] ?? '') || null,
        pub_types: pubTypes, url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`,
        origin: `data/raw/community/pubmed/${file}`, genes: [gene],
      });
    }
  }
  return [...out.values()].sort((a, b) => a.pmid.localeCompare(b.pmid));
}

/** All abstracts keyed by PMID: biology first (they win on overlap), then community. */
export function loadAllAbstracts() {
  const map = new Map();
  for (const r of loadBiologyAbstracts()) map.set(r.pmid, { ...r, set: 'biology' });
  for (const r of loadCommunityAbstracts()) if (!map.has(r.pmid)) map.set(r.pmid, { ...r, set: 'community' });
  return map;
}

export const sourceText = (rec) => `${rec.title} ${rec.abstract}`;

// ---------------------------------------------------------------------------
// Baseline graph: data/graph.json minus everything this layer contributed
// ---------------------------------------------------------------------------

const CURATED_DIR = path.join(ROOT, 'data/curated');

/**
 * The curated graph to compare against. Once build_graph.py has merged openai_extracted.json and
 * crosscheck.json, graph.json also contains this layer's candidate edges, evidence and synonyms (from
 * whichever fragment version was merged); comparing against those would be circular. So, independent
 * of fragment versions: keep only synonyms that some non-OpenAI curated fragment (or overrides.json)
 * gives that node, drop evidence with extracted_by "openai:*", and drop edges left with no evidence
 * that no non-OpenAI fragment defines.
 */
export function loadBaselineGraph() {
  const graph = readJson(GRAPH);
  const curatedSyn = new Map();
  const curatedEdgeIds = new Set();
  const addSyn = (id, s) => {
    if (!curatedSyn.has(id)) curatedSyn.set(id, new Set());
    curatedSyn.get(id).add(String(s).toLowerCase());
  };
  for (const f of readdirSync(CURATED_DIR)) {
    if (!f.endsWith('.json') || f === path.basename(FRAGMENT)) continue;
    const d = readJson(path.join(CURATED_DIR, f));
    if (f === 'overrides.json') {
      for (const [id, patch] of Object.entries(d.node_patches ?? {})) for (const s of patch?.synonyms ?? []) addSyn(id, s);
      continue;
    }
    for (const n of Array.isArray(d.nodes) ? d.nodes : []) for (const s of n.synonyms ?? []) addSyn(n.id, s);
    for (const e of Array.isArray(d.edges) ? d.edges : []) curatedEdgeIds.add(e.id ?? `${e.source}|${e.type}|${e.target}`);
  }
  graph.nodes = graph.nodes.map((n) => (n.synonyms
    ? { ...n, synonyms: n.synonyms.filter((s) => curatedSyn.get(n.id)?.has(s.toLowerCase())) }
    : n));
  const isOpenAI = (ev) => String(ev?.extracted_by ?? '').startsWith('openai:');
  graph.edges = graph.edges
    .map((e) => ({ ...e, evidence: (e.evidence ?? []).filter((ev) => !isOpenAI(ev)), counter_evidence: (e.counter_evidence ?? []).filter((ev) => !isOpenAI(ev)) }))
    .filter((e) => curatedEdgeIds.has(e.id) || e.evidence.length || e.counter_evidence.length);
  return graph;
}

// ---------------------------------------------------------------------------
// OpenAI call bookkeeping
// ---------------------------------------------------------------------------

/** Errors after which we stop sending requests (keep what is done, report it). */
export const FATAL_KINDS = new Set([
  'usage_limit', 'not_eligible', 'policy_or_region', 'auth', 'not_authorized', 'client_not_enabled', 'quota',
  'unsupported_route', 'rate_limited', 'no_llm_available', 'login_required', 'plan_usage_not_granted',
  'model_not_found', 'unsupported_capability',
]);

export function errorInfo(error) {
  return {
    name: error?.name ?? 'Error',
    kind: error?.kind ?? error?.code ?? 'error',
    code: error?.code ?? null,
    status: error?.status ?? null,
    requestId: error?.requestId ?? null,
    message: String(error?.message ?? error).slice(0, 400),
  };
}

export function logUsage(entry) {
  mkdirSync(OUT_RAW, { recursive: true });
  appendFileSync(USAGE_LOG, `${JSON.stringify({ ts: new Date().toISOString(), ...entry })}\n`);
}

export function readUsageLog() {
  if (!existsSync(USAGE_LOG)) return [];
  return readFileSync(USAGE_LOG, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
}

/**
 * Run `worker(item)` over items with at most `concurrency` in flight. `shouldStop()` is checked before
 * each new item, so a fatal error stops new work while in-flight requests finish.
 */
export async function runPool(items, concurrency, worker, shouldStop = () => false) {
  let next = 0;
  const lanes = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (next < items.length && !shouldStop()) {
      const item = items[next];
      next += 1;
      await worker(item);
    }
  });
  await Promise.all(lanes);
  return next;
}

export function parseArgs(argv = process.argv.slice(2)) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const [k, v] = a.slice(2).split('=');
      if (v !== undefined) args[k] = v;
      else if (argv[i + 1] && !argv[i + 1].startsWith('--')) args[k] = argv[++i];
      else args[k] = true;
    } else args._.push(a);
  }
  return args;
}
