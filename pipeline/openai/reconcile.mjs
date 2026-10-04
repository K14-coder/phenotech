/**
 * Step 3: map every mention in a verified claim to one stable graph node.
 *
 *   node pipeline/openai/reconcile.mjs              # deterministic index, then OpenAI for the rest
 *   node pipeline/openai/reconcile.mjs --no-llm     # deterministic only (no calls)
 *   READER=claude node pipeline/openai/reconcile.mjs --dump-pending pending.json
 *   READER=claude node pipeline/openai/reconcile.mjs --apply-answers answers.json
 *       The Claude reader never calls a model from here: --dump-pending writes, per abstract, the same
 *       payload the OpenAI step would send (mentions, sentences, candidate nodes); a Claude agent answers
 *       it with RECONCILE_INSTRUCTIONS as {pmid: {resolutions: [{mention_id, mention, node_id, match,
 *       justification}]}}; --apply-answers caches them under the same accept rules (id must be one of
 *       that mention's candidates, mention text must match).
 *
 * 1. A deterministic index built from data/graph.json (labels, synonyms, xrefs, gene symbols, protein
 *    names, GO names, disease subtype names, HPO labels) resolves what it can, conservatively:
 *    exact normalised match, one-gene rules ("STXBP1-E" -> disease:STXBP1), variant-class keywords,
 *    and mechanism/therapy label containment. Syndrome names that do not name a gene resolve only
 *    when that gene is mentioned in the same abstract.
 * 2. Everything else gets ONE batched OpenAI call per abstract: each mention with its sentence and
 *    the top 10 fuzzy-matched candidate nodes; the model picks a candidate id or "none" with a
 *    one-line justification. Only ids from that mention's candidate list are accepted.
 * 3. Mentions resolved by the OpenAI step as "same" (another name for exactly that node) that
 *    literally appear in the abstract become synonym proposals.
 *
 * Input:  data/raw/openai/claims_verified.json (from extract.mjs)
 * Cache:  data/raw/openai/reconcile/<PMID>.json (keyed by mention signature, so reruns are free)
 * Output: data/raw/openai/claims_reconciled.json
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { complete } from '../../integrations/openai/llm.mjs';
import {
  FATAL_KINDS, OUT_RAW, READER, RECONCILE_CACHE, RUN_STATE, errorInfo, loadAllAbstracts, loadBaselineGraph, logUsage, norm, parseArgs,
  readJson, runPool, sha1, sourceText, writeJson,
} from './common.mjs';

const RESOLVABLE_TYPES = ['gene', 'disease', 'variant_group', 'mechanism', 'phenotype', 'therapy'];

// ---------------------------------------------------------------------------
// Normalisation
// ---------------------------------------------------------------------------

/** Compact key: NFKC, lower case, letters and digits only (Unicode-aware, so "α-SNAP" != "SNAP"). */
export const keyOf = (s) => norm(s).toLowerCase().replace(/[^\p{L}\p{N}+]/gu, '');
const words = (s) => norm(s).toLowerCase().split(/[^\p{L}\p{N}+]+/u).filter(Boolean).map((w) => (w.length > 4 ? w.replace(/s$/, '') : w));
const escapeRx = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const tokenRx = (s) => new RegExp(`(?<![\\p{L}\\p{N}])${escapeRx(norm(s)).replace(/-/g, '[-\\s]?')}(?![\\p{L}\\p{N}])`, 'iu');

// Gene synonyms too short or too generic to identify a slice gene on their own.
const RISKY_GENE_SYNONYMS = new Set(['snap', 'sup', 'superprotein', 'syt', 'p65', 'stx1', 'unc18', 'sec9', 'sec18', 'svp65']);
const GENERIC_MENTION = /^(the |these |this |such |all |its |their |a |an )?(patients?|individuals?|children|subjects?|cases?|mice|neurons?|cells?|variants?|mutations?|disease|disorders?|syndromes?|function|it|they|genes?|proteins?|phenotypes?|symptoms?|treatment|therapy|drug|mechanism)$/i;
const OTHER_DISEASE = /\b(ALS|amyotrophic|frontotemporal|FTD|FTLD|Parkinson|Alzheimer|schizophreni|bipolar|depress|ADHD|attention[- ]deficit|cancer|carcinoma|tumou?r|glioma|diabetes|Huntington|botulism|cystic fibrosis|Williams|Wolf-Hirschhorn|microdeletion|contiguous|Lambert-Eaton myasthenic syndrome)\b/i;
const CONSEQUENCE_RULES = [
  ['truncating', /\b(truncat\w*|nonsense|frame-?shift\w*|stop[- ]gain\w*|premature (stop|termination)|start[- ]loss|null)\b/i],
  ['missense', /\b(missense|amino[- ]acid substitution\w*|(p\.)?[A-Z][a-z]{2}\d{1,4}[A-Z][a-z]{2}|[ACDEFGHIKLMNPQRSTVWY]\d{1,4}[ACDEFGHIKLMNPQRSTVWY])\b/],
  ['splice', /\b(splic\w*)\b/i],
  ['whole-gene-deletion', /\b(whole[- ]gene deletion\w*|gene deletion\w*|single[- ]gene deletion\w*)\b/i],
];

// ---------------------------------------------------------------------------
// Index from data/graph.json
// ---------------------------------------------------------------------------

export function buildIndex(graph) {
  const nodes = new Map(graph.nodes.filter((n) => RESOLVABLE_TYPES.includes(n.type)).map((n) => [n.id, n]));
  const exact = new Map(); // key -> Set(node id)
  const anchored = new Map(); // disease key -> boolean (names a gene or carries a number)
  const namesOf = new Map(); // node id -> [display names]
  const genes = [...nodes.values()].filter((n) => n.type === 'gene');
  const geneSymbols = new Set(genes.map((g) => g.label));

  const add = (key, id, display) => {
    if (!key || key.length < 2) return;
    if (!exact.has(key)) exact.set(key, new Set());
    exact.get(key).add(id);
    if (display) {
      if (!namesOf.has(id)) namesOf.set(id, []);
      if (!namesOf.get(id).includes(display)) namesOf.get(id).push(display);
    }
  };

  // Gene name patterns used to spot genes inside mentions and abstracts.
  const genePatterns = [];
  for (const g of genes) {
    const names = [g.label, ...(g.synonyms ?? []), g.attrs?.protein].filter(Boolean);
    for (const name of names) {
      const k = keyOf(name);
      if (RISKY_GENE_SYNONYMS.has(k) || k.length < 4) continue;
      genePatterns.push({ gene: g.label, name, rx: tokenRx(name) });
    }
  }
  // A synonym shared by two genes is not a gene identifier.
  const byKey = new Map();
  for (const p of genePatterns) {
    const k = keyOf(p.name);
    if (!byKey.has(k)) byKey.set(k, new Set());
    byKey.get(k).add(p.gene);
  }
  const genePats = genePatterns.filter((p) => byKey.get(keyOf(p.name)).size === 1);
  const genesIn = (text) => [...new Set(genePats.filter((p) => p.rx.test(norm(text))).map((p) => p.gene))];

  for (const n of nodes.values()) {
    const names = [n.label, ...(n.synonyms ?? [])];
    if (n.type === 'gene' && n.attrs?.protein) names.push(n.attrs.protein);
    if (n.type === 'mechanism') {
      if (n.attrs?.go_name) names.push(n.attrs.go_name);
      const head = n.label.split('(')[0].trim();
      names.push(head, ...head.split('/').map((s) => s.trim()));
      const bare = head.replace(/\s+(effect|mechanism)$/i, '').trim(); // "Dominant-negative effect" -> "Dominant-negative"
      if (bare !== head) names.push(bare);
    }
    if (n.type === 'disease') for (const st of n.attrs?.subtypes ?? []) if (st.name) names.push(st.name);
    if (n.type === 'variant_group') names.push(n.label.split(':').slice(1).join(':').split('(')[0].trim());
    for (const name of names) {
      if (!name) continue;
      const k = keyOf(name);
      if (n.type === 'gene' && RISKY_GENE_SYNONYMS.has(k)) continue;
      add(k, n.id, name);
      if (n.type === 'disease') anchored.set(`${n.id}|${k}`, genesIn(name).length > 0 || /\d/.test(name));
    }
    for (const [db, value] of Object.entries(n.xrefs ?? {})) {
      for (const v of Array.isArray(value) ? value : [value]) {
        if (!v || typeof v !== 'string') continue;
        add(keyOf(v.includes(':') ? v : `${db}:${v}`), n.id);
        if (n.type === 'disease') anchored.set(`${n.id}|${keyOf(v.includes(':') ? v : `${db}:${v}`)}`, true);
      }
    }
  }
  return { nodes, exact, anchored, namesOf, genesIn, geneSymbols };
}

// ---------------------------------------------------------------------------
// Deterministic resolution
// ---------------------------------------------------------------------------

/** Returns { id, method } or null. ctxGenes: slice genes named anywhere in this abstract. */
export function resolveDeterministic(index, mention, type, ctxGenes) {
  const { nodes, exact, anchored, genesIn } = index;
  const k = keyOf(mention);
  if (!k || GENERIC_MENTION.test(norm(mention))) return null;
  const typed = [...(exact.get(k) ?? [])].filter((id) => nodes.get(id)?.type === type);
  if (typed.length === 1) {
    const id = typed[0];
    if (type !== 'disease' || anchored.get(`${id}|${k}`)) return { id, method: 'exact' };
    // Syndrome names that don't name a gene ("Doose syndrome") only count in that gene's context.
    if (ctxGenes.includes(id.slice('disease:'.length))) return { id, method: 'exact+context' };
    return null;
  }
  const hits = genesIn(mention);
  if (type === 'gene' && hits.length === 1) return { id: `gene:${hits[0]}`, method: 'gene-rule' };
  // A bare gene symbol that is not a slice gene (SCN1A, GABRG2...) has no node: no need to ask.
  if (type === 'gene' && hits.length === 0 && /^[A-Z][A-Z0-9-]{1,9}$/.test(norm(mention))
      && ![...index.geneSymbols].some((g) => norm(mention).startsWith(g))) {
    return { id: null, method: 'not-in-graph' };
  }
  if (type === 'disease' && hits.length === 1 && !OTHER_DISEASE.test(mention)) {
    return { id: `disease:${hits[0]}`, method: 'gene-rule' };
  }
  if (type === 'variant_group') {
    const gene = hits.length === 1 ? hits[0] : hits.length === 0 && ctxGenes.length === 1 ? ctxGenes[0] : null;
    if (!gene || OTHER_DISEASE.test(mention)) return null;
    const classes = CONSEQUENCE_RULES.filter(([, rx]) => rx.test(mention)).map(([c]) => c);
    if (classes.length === 1) {
      const id = `vg:${gene}:${classes[0]}`;
      return nodes.has(id) ? { id, method: hits.length ? 'variant-rule' : 'variant-rule+context' } : null;
    }
    // "STXBP1 variants" / "SYT1 mutations" with no class: a gene-level claim. Deletions, duplications,
    // CNVs and indels are ambiguous (in-frame, whole-gene or contiguous), so the OpenAI step decides.
    if (classes.length === 0 && !/(delet|duplicat|cnv|copy[- ]number|insertion|indel|microdel|translocation)/i.test(mention)) {
      return { id: `gene_level:${gene}`, method: hits.length ? 'variant-rule(gene-level)' : 'variant-rule(gene-level)+context' };
    }
    return null;
  }
  if (type === 'mechanism' || type === 'therapy') {
    // Label containment: the mention contains exactly one node's distinctive name ("STXBP1 haploinsufficiency").
    const m = ` ${words(mention).join(' ')} `;
    const found = new Set();
    for (const [key, ids] of exact) {
      for (const id of ids) {
        const n = nodes.get(id);
        if (n.type !== type) continue;
        for (const name of index.namesOf.get(id) ?? []) {
          if (keyOf(name) !== key || name.length < 4) continue;
          const w = ` ${words(name).join(' ')} `;
          if (w.trim().length >= 4 && m.includes(w)) found.add(id);
        }
      }
    }
    if (found.size === 1) return { id: [...found][0], method: 'label-containment' };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Fuzzy candidates for the OpenAI step
// ---------------------------------------------------------------------------

const trigrams = (s) => {
  const t = ` ${norm(s).toLowerCase()} `;
  const out = new Set();
  for (let i = 0; i < t.length - 2; i += 1) out.add(t.slice(i, i + 3));
  return out;
};
function similarity(a, b) {
  const wa = new Set(words(a));
  const wb = new Set(words(b));
  const inter = [...wa].filter((w) => wb.has(w)).length;
  const jac = inter / Math.max(1, new Set([...wa, ...wb]).size);
  const ta = trigrams(a);
  const tb = trigrams(b);
  const ti = [...ta].filter((x) => tb.has(x)).length;
  const dice = (2 * ti) / Math.max(1, ta.size + tb.size);
  return 0.5 * jac + 0.5 * dice;
}

const COMPATIBLE = {
  gene: ['gene'],
  disease: ['disease'],
  variant_group: ['variant_group'],
  mechanism: ['mechanism'],
  phenotype: ['phenotype'],
  therapy: ['therapy'],
};

export function candidatesFor(index, mention, type, ctxGenes, k = 10) {
  const scored = [];
  for (const n of index.nodes.values()) {
    if (!COMPATIBLE[type]?.includes(n.type)) continue;
    const names = index.namesOf.get(n.id) ?? [n.label];
    let best = Math.max(...names.map((name) => similarity(mention, name)));
    const nodeGene = n.type === 'gene' ? n.label : n.type === 'disease' ? n.id.slice(8) : n.type === 'variant_group' ? n.attrs?.gene : null;
    if (nodeGene && ctxGenes.includes(nodeGene)) best += 0.25; // the abstract is about this gene
    if (nodeGene && n.type === 'variant_group' && !ctxGenes.includes(nodeGene)) best -= 0.5;
    scored.push({ id: n.id, score: best });
  }
  scored.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  return scored.slice(0, k).map((s) => s.id);
}

function describeNode(index, id) {
  const n = index.nodes.get(id);
  const syn = (n.synonyms ?? []).slice(0, 8);
  const extra = n.type === 'mechanism' ? `kind: ${n.attrs?.kind}` : n.type === 'phenotype' ? `HPO ${n.xrefs?.HPO ?? ''}` : '';
  const summary = (n.summary ?? '').slice(0, 160);
  return { id, type: n.type, label: n.label, ...(syn.length ? { synonyms: syn } : {}), ...(extra ? { note: extra } : {}), ...(summary ? { summary } : {}) };
}

export const RECONCILE_INSTRUCTIONS = `You link entity mentions from one biomedical abstract to nodes of a rare-disease knowledge graph. Disease nodes are gene-defined umbrella entities ("STXBP1-related disorders"); specific clinical entities of that gene are subtypes of them. Phenotype nodes are HPO terms. Mechanism nodes are molecular effects (kind: effect) or biological processes (kind: process).

For each mention you get the declared type, the sentence it came from, and up to 10 candidate nodes. Choose the one candidate the mention refers to, or "none".
- match "same": the mention is another name for exactly this node (synonym, abbreviation, gene or protein name, older or alternative disease name, equivalent clinical term).
- match "instance": the mention refers to this node more narrowly or descriptively: a subtype or gene-specific form of the disorder, a specific variant of the variant class, a specific description of this mechanism or phenotype.
- match "none": no candidate is this entity, the mention is broader than the candidate (e.g. "epilepsy" in general versus one gene's disorder, unless the sentence ties it to that gene), only related, or ambiguous.
Pick only from that mention's candidates and copy the id exactly. justification: one short line.`;

const RECONCILE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['resolutions'],
  properties: {
    resolutions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['mention_id', 'node_id', 'match', 'justification'],
        properties: {
          mention_id: { type: 'string' },
          node_id: { type: 'string', description: 'a candidate id copied exactly, or "none"' },
          match: { type: 'string', enum: ['same', 'instance', 'none'] },
          justification: { type: 'string' },
        },
      },
    },
  },
};

const mentionSig = (m) => sha1(`${m.type}|${norm(m.mention)}|${m.candidates.join(',')}`);
/**
 * Cached answer for a mention, looked up by (type, mention) rather than by candidate list, so that
 * answers stay valid when other layers add nodes. The candidates the model actually saw are stored
 * with each entry, and acceptance was checked against them at answer time.
 */
const findCached = (cache, type, mention) => {
  const want = norm(mention).toLowerCase();
  return Object.values(cache.entries ?? {}).find((e) => e.type === type && norm(e.mention).toLowerCase() === want);
};

// Synonym hygiene: the OpenAI "same" judgement is necessary but not sufficient for a good synonym.
const singular = (s) => norm(s).toLowerCase().split(/[^\p{L}\p{N}+]+/u).filter(Boolean)
  .map((w) => w.replace(/ies$/, 'y').replace(/([^s])s$/, '$1')).join(' ');
const DESCRIPTIVE = /\b(treatment|therapy|patients?|variants?|mutations?|mice|neurons?|cells?|types|different|various)\b|\/|\s\([^)]*\)$/i;
export function synonymOk(literal, node, index) {
  if (DESCRIPTIVE.test(literal)) return { ok: false, why: 'descriptive phrase, not a name' };
  const labelParts = node.label.split(/[/(]/).map((s) => s.replace(/\)/g, '').trim()).filter(Boolean);
  const names = [node.label, ...labelParts, ...(node.synonyms ?? []), node.attrs?.protein].filter(Boolean);
  if (names.some((n) => singular(n) === singular(literal))) return { ok: false, why: 'only a plural/spelling variant of an existing name' };
  // Names are short; a long phrase ("exocytosis of synaptic vesicles from nerve terminals") is a description.
  if (node.type !== 'disease' && singular(literal).split(' ').length > 5) return { ok: false, why: 'long descriptive phrase' };
  // Disease nodes are gene-defined umbrellas: a name that neither names the gene nor carries a number
  // ("Epilepsy", "CMS") would be ambiguous across genes.
  if (node.type === 'disease' && !index.genesIn(literal).includes(node.id.slice(8)) && !/\d/.test(literal)) {
    return { ok: false, why: 'generic disease name without the gene' };
  }
  if (node.type === 'mechanism' && singular(literal).split(' ').length < 2) return { ok: false, why: 'single generic word' };
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = parseArgs();
  const useLlm = !args['no-llm'];
  const graph = loadBaselineGraph(); // graph.json minus this layer's own earlier contributions
  const index = buildIndex(graph);
  const abstracts = loadAllAbstracts();
  const input = readJson(path.join(OUT_RAW, 'claims_verified.json'));
  const claims = input.claims.filter((c) => c.verified);

  // 1. Deterministic pass, collecting unresolved mentions per abstract.
  const ctxCache = new Map();
  const ctxGenesOf = (pmid) => {
    if (!ctxCache.has(pmid)) ctxCache.set(pmid, index.genesIn(sourceText(abstracts.get(pmid))));
    return ctxCache.get(pmid);
  };
  const pending = new Map(); // pmid -> Map(sig -> mention)
  const resolutions = new Map(); // `${pmid}|${type}|${normMention}` -> resolution
  const mkey = (pmid, type, mention) => `${pmid}|${type}|${norm(mention).toLowerCase()}`;
  for (const c of claims) {
    // Phenotypes seen only in animal/cell models are not compared (compare.mjs), so don't spend calls on them.
    if (c.relation === 'has_phenotype' && c.species && c.species !== 'human') continue;
    for (const side of ['subject', 'object']) {
      const mention = c[`${side}_mention`];
      const type = c[`${side}_type`];
      const key = mkey(c.pmid, type, mention);
      if (resolutions.has(key)) continue;
      if (!mention || GENERIC_MENTION.test(norm(mention))) {
        resolutions.set(key, { id: null, method: 'generic' });
        continue;
      }
      const ctx = ctxGenesOf(c.pmid);
      const det = resolveDeterministic(index, mention, type, ctx);
      if (det) {
        resolutions.set(key, det);
        continue;
      }
      const candidates = candidatesFor(index, mention, type, ctx);
      const m = { mention, type, sentence: c.quote, candidates };
      if (!pending.has(c.pmid)) pending.set(c.pmid, new Map());
      pending.get(c.pmid).set(mentionSig(m), m);
      resolutions.set(key, { id: null, method: 'pending', sig: mentionSig(m) });
    }
  }

  // 2. OpenAI pass: one batched call per abstract for mentions not already in its cache.
  let stop = null;
  let calls = 0;
  const work = [...pending.entries()]
    .filter(([pmid]) => !args.set || abstracts.get(pmid)?.set === args.set) // --set biology|community
    .map(([pmid, ms]) => ({ pmid, ms }));
  const cacheFile = (pmid) => path.join(RECONCILE_CACHE, `${pmid}.json`);
  const loadCache = (pmid) => (existsSync(cacheFile(pmid)) ? readJson(cacheFile(pmid)) : { pmid, entries: {} });
  const concurrency = Math.min(2, Number(args.concurrency ?? 2) || 1); // hard cap: 2 in flight
  const answers = args['apply-answers'] ? readJson(String(args['apply-answers'])) : null;
  const dump = {};
  let applied = 0;
  const record = (cache, todo, resolutions, model) => {
    const byId = new Map((resolutions ?? []).map((r) => [r.mention_id, r]));
    todo.forEach(([sig, m], i) => {
      const r = byId.get(`m${i + 1}`);
      if (answers && r && r.mention !== undefined && norm(r.mention) !== norm(m.mention)) return; // stale answer
      if (answers && !r) return;
      const accepted = r && r.node_id !== 'none' && r.match !== 'none' && m.candidates.includes(r.node_id);
      cache.entries[sig] = {
        mention: m.mention, type: m.type, candidates: m.candidates,
        node_id: accepted ? r.node_id : null, match: r?.match ?? 'missing', justification: r?.justification ?? null,
        raw_node_id: r?.node_id ?? null, rejected_not_in_candidates: Boolean(r && r.node_id !== 'none' && !m.candidates.includes(r.node_id)),
        model, generated_at: new Date().toISOString(),
      };
      applied += 1;
    });
  };
  await runPool(work, concurrency, async ({ pmid, ms }) => {
    const cache = loadCache(pmid);
    const todo = [...ms.entries()].filter(([, m]) => !findCached(cache, m.type, m.mention));
    if (!todo.length) return;
    const wantPayload = args['dump-pending'] || answers || (useLlm && READER === 'openai');
    if (!wantPayload) return;
    const rec = abstracts.get(pmid);
    const payload = {
      title: rec.title,
      mentions: todo.map(([sig, m], i) => ({
        mention_id: `m${i + 1}`, mention: m.mention, declared_type: m.type, sentence: m.sentence,
        candidates: m.candidates.map((id) => describeNode(index, id)),
      })),
    };
    if (args['dump-pending']) {
      dump[pmid] = payload;
      return;
    }
    if (answers) {
      if (!answers[pmid]) return;
      record(cache, todo, answers[pmid].resolutions, 'agent-reading');
      cache.calls = [...(cache.calls ?? []), { model: 'agent-reading', reader: READER, generated_at: new Date().toISOString(), request_payload: payload, raw_response: JSON.stringify(answers[pmid]) }];
      writeJson(cacheFile(pmid), cache);
      return;
    }
    const started = Date.now();
    try {
      const out = await complete({ instructions: RECONCILE_INSTRUCTIONS, input: JSON.stringify(payload), schema: RECONCILE_SCHEMA, schemaName: 'resolutions', authMode: 'chatgpt' });
      calls += 1;
      record(cache, todo, out.json?.resolutions, out.model);
      cache.calls = [...(cache.calls ?? []), { model: out.model, generated_at: new Date().toISOString(), usage: out.usage, request_payload: payload, raw_response: out.text }];
      writeJson(cacheFile(pmid), cache);
      logUsage({ script: 'reconcile', pmid, model: out.model, auth_path: out.authPath, structured_mode: out.structuredMode, usage: out.usage, ms: Date.now() - started, ok: true, mentions: todo.length });
      console.log(`  ok ${pmid}: ${todo.length} mentions (${((Date.now() - started) / 1000).toFixed(1)}s, ${out.model})`);
    } catch (error) {
      const info = errorInfo(error);
      logUsage({ script: 'reconcile', pmid, ok: false, error: info, ms: Date.now() - started });
      console.log(`  FAIL ${pmid}: ${info.kind} ${info.message}`);
      if (FATAL_KINDS.has(info.kind)) stop = info;
    }
  }, () => Boolean(stop));
  if (args['dump-pending']) {
    writeJson(String(args['dump-pending']), dump);
    console.log(`[reconcile] wrote ${Object.keys(dump).length} abstracts with pending mentions to ${args['dump-pending']}`);
  }
  if (answers) console.log(`[reconcile] applied ${applied} answered mentions`);
  if (useLlm && READER === 'openai' && !args['dump-pending'] && !answers) {
    const state = existsSync(RUN_STATE) ? readJson(RUN_STATE) : {};
    state.reconcile = { at: new Date().toISOString(), calls, stopped: stop };
    writeJson(RUN_STATE, state);
    if (stop) console.log(`[reconcile] STOPPED: ${stop.kind} - ${stop.message}`);
  }

  // 3. Apply cached OpenAI resolutions, build reconciled claims and synonym proposals.
  const caches = new Map();
  const cacheOf = (pmid) => {
    if (!caches.has(pmid)) caches.set(pmid, loadCache(pmid));
    return caches.get(pmid);
  };
  const synonymProposals = new Map(); // node id -> Map(lower -> {synonym, pmids, justification})
  const synonymRejected = [];
  const mentionStats = { total: 0, generic: 0, deterministic: 0, reader: 0, unresolved: 0, reader_rejected_not_in_candidates: 0 };
  const methodCounts = {};
  const resolveSide = (c, side) => {
    const mention = c[`${side}_mention`];
    const type = c[`${side}_type`];
    const r = resolutions.get(mkey(c.pmid, type, mention));
    if (!r) return { id: null, method: 'skipped(model-only phenotype)' };
    if (r.method !== 'pending') return r;
    const e = findCached(cacheOf(c.pmid), type, mention);
    if (!e) return { id: null, method: 'unresolved(no-llm-answer)' };
    if (!e.node_id) return { id: null, method: e.rejected_not_in_candidates ? `${READER}:rejected-not-in-candidates` : `${READER}:none`, justification: e.justification };
    if (!index.nodes.has(e.node_id)) return { id: null, method: `${READER}:stale-node`, justification: e.justification };
    return { id: e.node_id, method: `${READER}:${e.match}`, justification: e.justification };
  };

  const seenMention = new Set();
  const reconciled = claims.map((c) => {
    const out = { ...c };
    for (const side of ['subject', 'object']) {
      const r = resolveSide(c, side);
      out[`${side}_node`] = r.id;
      out[`${side}_resolution`] = r.method;
      if (r.justification) out[`${side}_justification`] = r.justification;
      const mk = mkey(c.pmid, c[`${side}_type`], c[`${side}_mention`]);
      if (!seenMention.has(mk)) {
        seenMention.add(mk);
        mentionStats.total += 1;
        methodCounts[r.method] = (methodCounts[r.method] ?? 0) + 1;
        if (r.method === 'generic') mentionStats.generic += 1;
        else if (r.method === 'not-in-graph') mentionStats.not_in_graph = (mentionStats.not_in_graph ?? 0) + 1;
        else if (r.method.startsWith('skipped')) mentionStats.skipped_model_only_phenotype = (mentionStats.skipped_model_only_phenotype ?? 0) + 1;
        else if (r.method.startsWith(`${READER}:`) && r.id) mentionStats.reader += 1;
        else if (r.id) mentionStats.deterministic += 1;
        else mentionStats.unresolved += 1;
        if (r.method === `${READER}:rejected-not-in-candidates`) mentionStats.reader_rejected_not_in_candidates += 1;
      }
      // Synonym proposal: OpenAI said "same", the mention literally appears in the abstract, and it is new.
      if (r.method === `${READER}:same` && r.id && !r.id.startsWith('vg:') && !r.id.startsWith('gene_level:')) {
        const mention = norm(c[`${side}_mention`]);
        const text = norm(sourceText(abstracts.get(c.pmid)));
        let literal = text.includes(mention) ? mention : null;
        if (!literal) {
          const at = text.toLowerCase().indexOf(mention.toLowerCase());
          if (at >= 0) literal = text.slice(at, at + mention.length);
        }
        const node = index.nodes.get(r.id);
        const known = new Set([node.label, ...(node.synonyms ?? []), node.attrs?.protein].filter(Boolean).map(keyOf));
        const otherGene = index.genesIn(mention).some((g) => !r.id.endsWith(`:${g}`) && r.id !== `gene:${g}`);
        const hygiene = literal ? synonymOk(literal, node, index) : { ok: false };
        if (literal && !hygiene.ok && !known.has(keyOf(literal))) {
          synonymRejected.push({ node_id: r.id, mention: literal, pmid: c.pmid, why: hygiene.why });
        }
        if (literal && hygiene.ok && literal.length >= 3 && !known.has(keyOf(literal)) && !GENERIC_MENTION.test(literal) && !otherGene) {
          if (!synonymProposals.has(r.id)) synonymProposals.set(r.id, new Map());
          const m = synonymProposals.get(r.id);
          const lk = keyOf(literal);
          if (!m.has(lk)) m.set(lk, { synonym: literal, pmids: [], justification: r.justification });
          if (!m.get(lk).pmids.includes(c.pmid)) m.get(lk).pmids.push(c.pmid);
        }
      }
    }
    return out;
  });

  const proposals = [...synonymProposals.entries()].flatMap(([id, m]) => [...m.values()].map((p) => ({ node_id: id, node_label: index.nodes.get(id).label, node_type: index.nodes.get(id).type, ...p })));

  // One entity, several nodes? Names shared by two nodes of the same type (diseases excluded: a
  // multi-gene clinical group legitimately names several gene-defined umbrellas).
  // Report-only name map (label heads included); deliberately separate from the resolution index so
  // that cached OpenAI answers stay valid. Variant groups share class names by design.
  const shared = new Map();
  for (const n of index.nodes.values()) {
    if (n.type === 'disease' || n.type === 'variant_group') continue;
    const names = [n.label, n.label.split('(')[0], ...(n.synonyms ?? []), n.attrs?.protein].filter(Boolean);
    for (const name of names) {
      const k = `${n.type}|${keyOf(name)}`;
      if (!shared.has(k)) shared.set(k, { name: name.trim(), ids: new Set() });
      shared.get(k).ids.add(n.id);
    }
  }
  const duplicateSuspects = [...shared.entries()].filter(([, v]) => v.ids.size > 1)
    .map(([k, v]) => ({ shared_name: v.name, type: k.split('|')[0], node_ids: [...v.ids].sort() }));
  const both = reconciled.filter((c) => c.subject_node && c.object_node).length;
  const out = {
    generated_at: new Date().toISOString(),
    stats: {
      verified_claims: claims.length,
      claims_both_endpoints_resolved: both,
      mentions: mentionStats,
      methods: methodCounts,
      synonym_proposals: proposals.length,
      synonym_candidates_rejected_by_hygiene: new Set(synonymRejected.map((x) => `${x.node_id}|${x.mention.toLowerCase()}`)).size,
    },
    synonym_proposals: proposals,
    duplicate_node_suspects: duplicateSuspects,
    synonym_rejected: [...new Map(synonymRejected.map((x) => [`${x.node_id}|${x.mention.toLowerCase()}`, x])).values()],
    claims: reconciled,
  };
  writeJson(path.join(OUT_RAW, 'claims_reconciled.json'), out);
  console.log(`[reconcile] ${claims.length} verified claims; both endpoints resolved: ${both}`);
  console.log(`[reconcile] mentions ${JSON.stringify(mentionStats)}`);
  console.log(`[reconcile] synonym proposals: ${proposals.length}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
