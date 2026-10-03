/**
 * Step 1+2: independent OpenAI claim extraction from stored PubMed abstracts, then code-side quote
 * verification.
 *
 *   node pipeline/openai/extract.mjs                       # biology abstracts (data/raw/biology/pubmed)
 *   node pipeline/openai/extract.mjs --set community --limit 40   # community records with abstracts, in priority order
 *   node pipeline/openai/extract.mjs --pmids 18469812,29538625
 *   node pipeline/openai/extract.mjs --verify-only         # no calls: re-verify every cached extraction
 *
 * Calls go through integrations/openai/llm.mjs on the ChatGPT-plan path only (authMode "chatgpt";
 * OPENAI_API_KEY is never used). At most 2 requests in flight. Each response is cached per PMID in
 * data/raw/openai/extractions/<PMID>.json, so reruns are free. Only title + abstract are sent.
 * A usage-limit / plan error stops new requests; finished work is kept.
 *
 * Verification: every quote must be a verbatim substring of the stored title + abstract after
 * Unicode/whitespace normalisation (common.mjs norm()). Non-matching claims are rejected and
 * counted. Quotes are never edited. Output: data/raw/openai/claims_verified.json
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { complete } from '../../integrations/openai/llm.mjs';
import {
  EXTRACTIONS, FATAL_KINDS, OUT_RAW, RUN_STATE, errorInfo, isVerbatim, loadAllAbstracts, loadBaselineGraph, logUsage, norm,
  parseArgs, readJson, runPool, sha1, sourceText, writeJson,
} from './common.mjs';

export const NODE_TYPES = ['gene', 'disease', 'variant_group', 'mechanism', 'phenotype', 'therapy'];
export const RELATIONS = ['causes', 'has_effect', 'participates_in', 'driven_by', 'has_phenotype', 'targets', 'developed_for'];
export const STUDY_TYPES = ['clinical_trial', 'case_report', 'case_series', 'cohort', 'functional_study', 'animal_model', 'review'];
export const SPECIES = ['human', 'mouse', 'rat', 'fly', 'worm', 'cell', 'in_vitro'];
export const CERTAINTY = ['established', 'suggested', 'speculative'];

export const CLAIM_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['claims'],
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['subject_mention', 'subject_type', 'relation', 'object_mention', 'object_type', 'quote', 'study_type', 'species', 'certainty', 'negated'],
        properties: {
          subject_mention: { type: 'string' },
          subject_type: { type: 'string', enum: NODE_TYPES },
          relation: { type: 'string', enum: RELATIONS },
          object_mention: { type: 'string' },
          object_type: { type: 'string', enum: NODE_TYPES },
          quote: { type: 'string', description: 'ONE sentence copied character for character from the title or abstract' },
          study_type: { type: 'string', enum: STUDY_TYPES },
          species: { type: ['string', 'null'], enum: [...SPECIES, null] },
          certainty: { type: 'string', enum: CERTAINTY },
          negated: { type: 'boolean' },
        },
      },
    },
  },
};

export const EXTRACT_INSTRUCTIONS = `You read one PubMed record (title and abstract) and extract the relation claims it states, for a rare-disease knowledge graph. Answer with JSON matching the schema.

Relations (subject_type -> object_type):
- causes: gene -> disease. Variants in the gene cause the disorder.
- has_effect: variant_group -> mechanism. A variant class (e.g. "STXBP1 missense variants", "truncating variants") or a named variant (e.g. "SNAP25 V48F") has a molecular effect: loss of function, haploinsufficiency, dominant-negative, gain of function, or protein destabilization (misfolding, aggregation, degradation, ER retention).
- participates_in: gene -> mechanism. The gene's protein takes part in a biological process (e.g. SNARE complex assembly or disassembly, synaptic vesicle docking, priming or fusion, Ca2+-triggered neurotransmitter release, GABA reuptake).
- driven_by: disease -> mechanism. The disorder arises through a mechanism (e.g. "STXBP1 encephalopathy is caused by haploinsufficiency").
- has_phenotype: disease -> phenotype. Patients with the disorder show a clinical feature (seizure types, intellectual disability, developmental delay, movement disorders, hypotonia, EEG patterns, autism, and so on). Only features observed in people, not in animal or cell models. If the text names patients only by gene ("patients with SYT1 variants"), the subject is the disease, mentioned by the gene name.
- targets: therapy -> mechanism. A treatment acts on, corrects or rescues a mechanism.
- developed_for: therapy -> disease. A treatment was developed, tested or used for the disorder, in patients or in models of it.

Rules:
1. quote: copy exactly ONE sentence from the title or abstract that states the claim, character for character: the same words, case, punctuation, numbers, symbols and Greek letters. Never paraphrase, shorten, join two sentences or correct anything. If no single sentence states the claim, leave the claim out.
2. subject_mention and object_mention: the entity as this text names it (e.g. "Munc18-1", "Ohtahara syndrome", "GAT-1", "tremor"). For a variant group, give the gene and the variant words (e.g. "STXBP1 missense variants", "SNAP25 V48F").
3. Only specific entities. No generic subjects or objects such as "patients", "the disease", "these variants", "neurons" or "function".
4. negated = true when the sentence says the relation does NOT hold (e.g. "did not rescue", "no dominant-negative effect", "was not associated with"). Write the claim in its positive form (subject, relation, object) and set negated = true.
5. certainty: "established" = reported as a result of this work or as accepted fact; "suggested" = the authors' interpretation ("suggest", "indicate", "likely", "may"); "speculative" = a hypothesis or proposal ("could", "might", "we propose", "potential").
6. study_type = the design of the evidence behind the claim in this paper: clinical_trial, case_report (one patient), case_series (several patients or families), cohort (a larger patient group or registry), functional_study (cells, neurons, protein biochemistry, structure), animal_model (mouse, rat, fly, worm, zebrafish), review.
7. species = where the claim was observed: human, mouse, rat, fly, worm, cell (cultured or iPSC-derived cells), in_vitro (purified proteins, cell-free assays); null if not stated or another organism.
8. Extract every distinct claim, at most 20. Prefer specific claims about genes, variants, mechanisms and therapies, then patient phenotypes, over general background. Return {"claims": []} if there are none.`;

export const INSTRUCTIONS_SHA = sha1(EXTRACT_INSTRUCTIONS + JSON.stringify(CLAIM_SCHEMA));
export const inputFor = (rec) => `Title: ${rec.title}\n\nAbstract: ${rec.abstract}`;
const cachePath = (pmid) => path.join(EXTRACTIONS, `${pmid}.json`);

/** Community records in priority order: cited on a graph edge, then a slice gene in the title, then the rest. */
function communityPriority(records) {
  const graph = loadBaselineGraph();
  const cited = new Set();
  for (const e of graph.edges) {
    for (const ev of [...(e.evidence ?? []), ...(e.counter_evidence ?? [])]) {
      if (String(ev.ref ?? '').startsWith('PMID:')) cited.add(ev.ref.slice(5));
    }
  }
  const genes = graph.nodes.filter((n) => n.type === 'gene').map((n) => n.label);
  const geneInTitle = (t) => genes.some((g) => new RegExp(`\\b${g}\\b`, 'i').test(t));
  const rank = (r) => (cited.has(r.pmid) ? 0 : geneInTitle(r.title) ? 1 : 2);
  return [...records].sort((a, b) => rank(a) - rank(b) || (b.year ?? 0) - (a.year ?? 0) || a.pmid.localeCompare(b.pmid));
}

export function verifyAll(abstracts) {
  const claims = [];
  const perPmid = {};
  const models = new Set();
  for (const [pmid, rec] of abstracts) {
    const file = cachePath(pmid);
    if (!existsSync(file)) continue;
    const cached = readJson(file);
    if (cached.error || !Array.isArray(cached.claims)) continue;
    models.add(cached.model);
    const text = sourceText(rec);
    const stats = { claims: 0, verified: 0, rejected: 0 };
    cached.claims.forEach((c, i) => {
      const verified = isVerbatim(c.quote, text);
      // A quote that matches but spans more than one sentence still counts as verbatim; record it.
      // (Abbreviations such as "e.g." or "et al." are not sentence ends.)
      const sentences = norm(c.quote)
        .replace(/\b(e\.g|i\.e|et al|vs|cf|Fig|Figs|approx|ca|No|Ref|Refs)\./g, '$1<dot>')
        .split(/(?<=[.!?])\s+(?=[A-Z(])/).length;
      claims.push({
        claim_id: `${pmid}#${i}`, pmid, set: rec.set, title: rec.title, year: rec.year, ...c,
        verified, ...(verified ? {} : { reject_reason: 'quote not a verbatim substring of stored title+abstract' }),
        ...(sentences > 1 ? { multi_sentence: true } : {}),
        model: cached.model,
      });
      stats.claims += 1;
      stats[verified ? 'verified' : 'rejected'] += 1;
    });
    perPmid[pmid] = stats;
  }
  const total = claims.length;
  const verified = claims.filter((c) => c.verified).length;
  const out = {
    generated_at: new Date().toISOString(),
    models: [...models],
    stats: {
      abstracts_with_extraction: Object.keys(perPmid).length,
      claims: total, verified, rejected: total - verified,
      verified_pct: total ? Math.round((1000 * verified) / total) / 10 : null,
      verified_but_multi_sentence: claims.filter((c) => c.verified && c.multi_sentence).length,
      by_set: Object.fromEntries(['biology', 'community'].map((s) => {
        const cs = claims.filter((c) => c.set === s);
        const extracted = Object.keys(perPmid).filter((p) => abstracts.get(p)?.set === s);
        return [s, {
          abstracts: extracted.length, abstracts_with_claims: new Set(cs.map((c) => c.pmid)).size,
          claims: cs.length, verified: cs.filter((c) => c.verified).length,
        }];
      })),
    },
    per_pmid: perPmid,
    claims,
  };
  writeJson(path.join(OUT_RAW, 'claims_verified.json'), out);
  return out;
}

async function main() {
  const args = parseArgs();
  const concurrency = Math.min(2, Number(args.concurrency ?? 2) || 1); // hard cap: 2 in flight
  const abstracts = loadAllAbstracts();
  const set = args.set ?? 'biology';
  let queue;
  if (args.pmids) {
    queue = String(args.pmids).split(',').map((p) => p.trim()).filter((p) => abstracts.has(p)).map((p) => abstracts.get(p));
  } else {
    const pool = [...abstracts.values()].filter((r) => set === 'all' || r.set === set);
    queue = set === 'biology' ? pool : communityPriority(pool);
  }
  const todo = queue.filter((r) => {
    if (!existsSync(cachePath(r.pmid))) return true;
    const cached = readJson(cachePath(r.pmid));
    return Boolean(cached.error) && !args['skip-failed'];
  });
  const limited = args.limit ? todo.slice(0, Number(args.limit)) : todo;

  if (!args['verify-only'] && limited.length) {
    console.log(`[extract] ${queue.length} abstracts in set "${args.pmids ? 'pmids' : set}", ${queue.length - todo.length} cached, ${limited.length} to call (concurrency ${concurrency})`);
    let stop = null;
    let consecutiveFailures = 0;
    let done = 0;
    await runPool(limited, concurrency, async (rec) => {
      const started = Date.now();
      const input = inputFor(rec);
      try {
        const out = await complete({ instructions: EXTRACT_INSTRUCTIONS, input, schema: CLAIM_SCHEMA, schemaName: 'claims', authMode: 'chatgpt' });
        const ms = Date.now() - started;
        writeJson(cachePath(rec.pmid), {
          pmid: rec.pmid, set: rec.set, model: out.model, generated_at: new Date().toISOString(),
          auth_path: out.authPath, structured_mode: out.structuredMode, response_id: out.responseId, request_id: out.requestId,
          usage: out.usage, latency_ms: ms, input_sha1: sha1(input), instructions_sha1: INSTRUCTIONS_SHA,
          source: rec.origin, raw_response: out.text, claims: out.json?.claims ?? [],
        });
        logUsage({ script: 'extract', pmid: rec.pmid, model: out.model, auth_path: out.authPath, structured_mode: out.structuredMode, usage: out.usage, ms, ok: true });
        consecutiveFailures = 0;
        done += 1;
        console.log(`  ok ${rec.pmid} (${out.json?.claims?.length ?? 0} claims, ${(ms / 1000).toFixed(1)}s, ${out.model}) [${done}/${limited.length}]`);
      } catch (error) {
        const info = errorInfo(error);
        logUsage({ script: 'extract', pmid: rec.pmid, ok: false, error: info, ms: Date.now() - started });
        console.log(`  FAIL ${rec.pmid}: ${info.kind} ${info.message}`);
        if (FATAL_KINDS.has(info.kind)) {
          stop = info;
          return;
        }
        consecutiveFailures += 1;
        if (consecutiveFailures >= 3) stop = { ...info, note: '3 consecutive failures' };
      }
    }, () => Boolean(stop));
    const state = existsSync(RUN_STATE) ? readJson(RUN_STATE) : {};
    state.extract = { at: new Date().toISOString(), set: args.pmids ? 'pmids' : set, requested: limited.length, completed: done, stopped: stop };
    writeJson(RUN_STATE, state);
    if (stop) console.log(`[extract] STOPPED: ${stop.kind} - ${stop.message}`);
  }

  const v = verifyAll(abstracts);
  console.log(`[verify] ${v.stats.abstracts_with_extraction} abstracts, ${v.stats.claims} claims, ${v.stats.verified} verbatim (${v.stats.verified_pct}%), ${v.stats.rejected} rejected`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
