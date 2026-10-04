#!/usr/bin/env node
/**
 * Export accepted community-research claims into a docs/SCHEMA.md fragment that build_graph.py merges.
 *
 *   node pipeline/crowd/export.mjs                    # read the production queue (Redis REST, read-only)
 *   node pipeline/crowd/export.mjs --file             # read the local dev queue file web/.data/queue.json
 *   node pipeline/crowd/export.mjs --out /tmp/x.json  # write somewhere else (default data/curated/crowd.json)
 *   node pipeline/crowd/export.mjs --min-claims 3     # only diseases with at least 3 accepted claims
 *
 * Redis credentials: KV_REST_API_URL + KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL/_TOKEN) from the
 * environment or web/.env.local. Only read commands are sent (SMEMBERS, LRANGE, GET).
 *
 * Mapping (everything is status "unverified", confidence <= 0.5, never presented as curated):
 *   disease (single-gene only)  -> node disease:<GENE> (gene-umbrella convention), attrs.layer "crowd"
 *   causes                      -> gene:<GENE> causes disease:<GENE>
 *   driven_by / has_effect      -> disease:<GENE> driven_by mech:<loss-of-function|haploinsufficiency|dominant-negative|gain-of-function>
 *   has_phenotype               -> disease has_phenotype phenotype:<HPO id>, only when the object equals an HPO label exactly
 *   developed_for               -> therapy:<slug> developed_for disease (therapy node, stage from therapy_stage)
 *   research groups             -> researcher:<name>--<institution> works_on disease (evidence quote = the paper title)
 *   participates_in / disrupts / targets / natural_history: kept on the /d/ page only (no safe node mapping yet)
 * Negated claims become counter_evidence on an edge that also has supporting claims; otherwise they are skipped.
 * evidence.extracted_by = "openai:<model> (community)" or "anthropic:<model> (community)".
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const argv = process.argv.slice(2);
const opt = (name, dflt) => (argv.includes(`--${name}`) ? argv[argv.indexOf(`--${name}`) + 1] : dflt);
const OUT = path.resolve(opt('out', path.join(ROOT, 'data', 'curated', 'crowd.json')));
const MIN_CLAIMS = Number(opt('min-claims', 1));
const FROM_FILE = argv.includes('--file');

function envFile(file) {
  const env = {};
  if (!existsSync(file)) return env;
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  return env;
}

// ---------- read the queue ----------
async function loadResearched() {
  if (FROM_FILE) {
    const db = JSON.parse(readFileSync(path.join(ROOT, 'web', '.data', 'queue.json'), 'utf8'));
    const ids = db.s['rq:researched'] ?? [];
    return ids.map((id) => ({
      id,
      claims: (db.l[`rq:claims:${id}`] ?? []).map((x) => JSON.parse(x)),
      groups: (db.l[`rq:groups:${id}`] ?? []).map((x) => JSON.parse(x)),
    }));
  }
  const env = { ...envFile(path.join(ROOT, 'web', '.env.local')), ...process.env };
  const url = env.KV_REST_API_URL ?? env.UPSTASH_REDIS_REST_URL;
  const token = env.KV_REST_API_TOKEN ?? env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) throw new Error('No Redis credentials (KV_REST_API_URL / KV_REST_API_TOKEN). Use --file for the local queue.');
  const READ_ONLY = new Set(['SMEMBERS', 'LRANGE', 'GET']);
  const r = async (...cmd) => {
    if (!READ_ONLY.has(cmd[0])) throw new Error(`refusing non-read command ${cmd[0]}`);
    const res = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(cmd.map(String)) });
    const j = await res.json();
    if (!res.ok || j.error) throw new Error(`redis: ${j.error ?? res.status}`);
    return j.result;
  };
  const ids = (await r('SMEMBERS', 'rq:researched')) ?? [];
  const out = [];
  for (const id of ids) {
    out.push({
      id,
      claims: ((await r('LRANGE', `rq:claims:${id}`, 0, -1)) ?? []).map((x) => JSON.parse(x)),
      groups: ((await r('LRANGE', `rq:groups:${id}`, 0, -1)) ?? []).map((x) => JSON.parse(x)),
    });
  }
  return out;
}

// ---------- reference data ----------
const seed = JSON.parse(readFileSync(path.join(ROOT, 'web', 'app', 'api', 'queue', '_data', 'seed.json'), 'utf8'));
const seedById = new Map(seed.rows.map((t) => [t[0], { id: t[0], name: t[1], syn: t[2], genes: t[3], omim: t[4], orpha: t[5] }]));
const graph = JSON.parse(readFileSync(path.join(ROOT, 'data', 'graph.json'), 'utf8'));
const graphNodes = new Set(graph.nodes.map((n) => n.id));
const hpoByLabel = new Map();
for (let b = 0; b < 64; b += 1) {
  const f = path.join(ROOT, 'data', 'derived', 'global', 'neighbours', `${b}.json`);
  if (!existsSync(f)) continue;
  for (const [hp, [label, ic]] of Object.entries(JSON.parse(readFileSync(f, 'utf8')).t ?? {})) {
    if (ic > 0) hpoByLabel.set(label.toLowerCase(), { hp, label, ic });
  }
}

const slug = (s, max = 60) => String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, max).replace(/-$/, '');
const MECH = { loss_of_function: 'loss-of-function', haploinsufficiency: 'haploinsufficiency', dominant_negative: 'dominant-negative', gain_of_function: 'gain-of-function' };
const MECH_LABEL = { loss_of_function: 'Loss of function', haploinsufficiency: 'Haploinsufficiency', dominant_negative: 'Dominant-negative', gain_of_function: 'Gain of function' };
const STAGE = { approved: 'approved', clinical: 'clinical', preclinical: 'preclinical', tried_off_label: 'clinical' };
const LEVEL = (st) => (st === 'clinical_trial' ? 'clinical' : st === 'functional_study' || st === 'animal_model' ? 'experimental' : 'observational');
const EV_STUDY = { natural_history_study: 'cohort', registry: 'cohort' };
const extractedBy = (c) => (c.provider === 'anthropic' ? `anthropic:${c.model} (community)` : c.provider === 'openai' || !c.provider ? `openai:${c.model} (community)` : `${c.model} (community)`);
const evidenceOf = (c) => ({
  source: 'PubMed',
  ref: `PMID:${c.pmid}`,
  url: `https://pubmed.ncbi.nlm.nih.gov/${c.pmid}/`,
  title: c.title,
  ...(c.year ? { year: c.year } : {}),
  quote: c.quote,
  kind: 'publication',
  study_type: EV_STUDY[c.study_type] ?? c.study_type,
  extracted_by: extractedBy(c),
  verified: true,
  retrieved: String(c.at).slice(0, 10),
  community: { handle: c.handle, round: c.round, certainty: c.certainty, species: c.species, status: c.status },
});

// ---------- build ----------
const nodes = new Map();
const edges = new Map();
const stats = { diseases: 0, skipped_multigene: 0, skipped_unknown: 0, skipped_few: 0, claims: 0, edges_from_claims: 0, unmapped_relation: 0, unmapped_phenotype: 0, negated_only: 0, groups: 0 };
const addNode = (n) => {
  if (!graphNodes.has(n.id) && !nodes.has(n.id)) nodes.set(n.id, n);
};
function addEdge(source, type, target, claim, explanation) {
  const id = `${source}|${type}|${target}`;
  const e = edges.get(id) ?? { id, source, type, target, explanation, evidence_level: 'observational', status: 'unverified', confidence: 0.3, evidence: [], counter_evidence: [], attrs: { layer: 'crowd', review: 'unreviewed' } };
  const ev = evidenceOf(claim);
  if (claim.negated) e.counter_evidence.push({ ...ev, supports: false });
  else e.evidence.push(ev);
  edges.set(id, e);
}

const researched = await loadResearched();
for (const r of researched) {
  const d = seedById.get(r.id);
  if (!d) {
    stats.skipped_unknown += 1;
    continue;
  }
  if (r.claims.length + r.groups.length < MIN_CLAIMS) {
    stats.skipped_few += 1;
    continue;
  }
  if (d.genes.length !== 1) {
    stats.skipped_multigene += 1;
    continue;
  }
  stats.diseases += 1;
  const G = d.genes[0];
  const dis = `disease:${G}`;
  const prev = nodes.get(dis);
  const subtype = { name: d.name, ...(d.id.startsWith('MONDO:') ? { MONDO: d.id } : {}), ...(d.omim[0] ? { OMIM: d.omim[0] } : {}), ...(d.orpha[0] ? { ORPHA: d.orpha[0] } : {}) };
  if (!graphNodes.has(dis)) {
    nodes.set(dis, {
      id: dis,
      type: 'disease',
      label: `${G}-related disorders`,
      synonyms: [...new Set([...(prev?.synonyms ?? []), d.name, ...d.syn])],
      xrefs: {
        MONDO: [...new Set([...(prev?.xrefs.MONDO ?? []), ...(d.id.startsWith('MONDO:') ? [d.id] : [])])],
        OMIM: [...new Set([...(prev?.xrefs.OMIM ?? []), ...d.omim])],
        ORPHA: [...new Set([...(prev?.xrefs.ORPHA ?? []), ...d.orpha])],
      },
      summary: `Community-researched profile (AI-extracted by volunteers, quote-verified, unreviewed) for ${d.name}.`,
      attrs: { layer: 'crowd', review: 'unreviewed', subtypes: [...(prev?.attrs.subtypes ?? []), subtype] },
    });
  }
  addNode({ id: `gene:${G}`, type: 'gene', label: G });
  for (const c of r.claims) {
    stats.claims += 1;
    const why = `Volunteer-run AI extraction, unreviewed: a PubMed sentence states that ${c.subject} ${c.relation.replace(/_/g, ' ')} ${c.object}.`;
    if (c.relation === 'causes') addEdge(`gene:${G}`, 'causes', dis, c, why);
    else if ((c.relation === 'driven_by' || c.relation === 'has_effect') && MECH[c.mechanism_class]) {
      const m = `mech:${MECH[c.mechanism_class]}`;
      addNode({ id: m, type: 'mechanism', label: MECH_LABEL[c.mechanism_class], attrs: { kind: 'effect' } });
      addEdge(dis, 'driven_by', m, c, why);
    } else if (c.relation === 'has_phenotype') {
      const hpo = hpoByLabel.get(String(c.object).toLowerCase().replace(/s$/, '')) ?? hpoByLabel.get(String(c.object).toLowerCase());
      if (!hpo) {
        stats.unmapped_phenotype += 1;
        continue;
      }
      addNode({ id: `phenotype:${hpo.hp}`, type: 'phenotype', label: hpo.label, attrs: { ic: hpo.ic } });
      addEdge(dis, 'has_phenotype', `phenotype:${hpo.hp}`, c, why);
    } else if (c.relation === 'developed_for' && c.therapy_stage) {
      const t = `therapy:${slug(c.subject)}`;
      addNode({ id: t, type: 'therapy', label: c.subject, attrs: { modality: 'other', stage: STAGE[c.therapy_stage], crowd_stage: c.therapy_stage, layer: 'crowd' } });
      addEdge(t, 'developed_for', dis, c, why);
    } else {
      stats.unmapped_relation += 1;
      continue;
    }
    stats.edges_from_claims += 1;
  }
  for (const g of r.groups) {
    stats.groups += 1;
    const inst = g.affiliation.split(',').map((x) => x.trim()).find((x) => /univ|institut|hospital|center|centre|college|school|foundation|laborator|clinic/i.test(x)) ?? g.affiliation.split(',')[0];
    const rid = `researcher:${slug(g.senior_author, 40)}--${slug(inst, 40)}`;
    addNode({ id: rid, type: 'researcher', label: g.senior_author, attrs: { affiliation: g.affiliation, layer: 'crowd' } });
    addEdge(rid, 'works_on', dis, { ...g, quote: g.title, study_type: 'review', negated: false, certainty: 'established', species: null, round: null }, `Senior author of a PubMed paper on ${d.name} (from the PubMed author list; volunteer-selected, unreviewed).`);
  }
}

// finalise edges: drop negated-only, set level and confidence (<= 0.5)
for (const [id, e] of edges) {
  if (!e.evidence.length) {
    edges.delete(id);
    stats.negated_only += 1;
    continue;
  }
  const pmids = new Set(e.evidence.map((x) => x.ref));
  e.confidence = Math.min(0.5, 0.3 + 0.1 * (pmids.size - 1));
  const levels = e.evidence.map((x) => LEVEL(x.study_type));
  e.evidence_level = levels.includes('clinical') ? 'clinical' : levels.includes('experimental') ? 'experimental' : 'observational';
  if (!e.counter_evidence.length) delete e.counter_evidence;
}

// self-check: no dangling edges, every PubMed evidence has a quote and url
const all = new Set([...graphNodes, ...nodes.keys()]);
const problems = [];
for (const e of edges.values()) {
  if (!all.has(e.source) || !all.has(e.target)) problems.push(`dangling ${e.id}`);
  for (const ev of e.evidence) if (!ev.quote || !ev.url) problems.push(`evidence without quote/url on ${e.id}`);
}
if (problems.length) throw new Error(`export self-check failed:\n${problems.slice(0, 20).join('\n')}`);

const fragment = {
  about: `Community research queue export (${new Date().toISOString()}): AI-extracted by volunteers with their own models, every quote verified verbatim against the PubMed abstract the atlas fetched; unreviewed. Built by pipeline/crowd/export.mjs.`,
  nodes: [...nodes.values()],
  edges: [...edges.values()],
  clusters: [],
  gaps: [],
};
mkdirSync(path.dirname(OUT), { recursive: true });
writeFileSync(OUT, `${JSON.stringify(fragment, null, 2)}\n`);
console.log(`[crowd] ${researched.length} researched diseases -> ${fragment.nodes.length} nodes, ${fragment.edges.length} edges -> ${path.relative(ROOT, OUT) || OUT}`);
console.log(`[crowd] ${JSON.stringify(stats)}`);
