/**
 * Tests for the contribute-evidence backend. No OpenAI calls (a fake `complete` is injected), no real
 * network (fetch and DNS are mocked) and no writes to the real data files (everything goes to a temp
 * directory; a guard test checks data/curated/contributions.json and data/raw/contributions/).
 *
 *   node --test pipeline/contribute/test.mjs        (or: node pipeline/contribute/test.mjs)
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  ContributeError, buildDiseaseIndex, buildNodeIndex, commit, findDuplicate, htmlToText, preview, reconcileMention, selectExcerpt,
  toHttpError, verifyQuote,
} from './contribute.mjs';
import { BRIGHTDATA_API, pageCachePath } from './page.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const REAL_FRAGMENT = path.join(ROOT, 'data', 'curated', 'contributions.json');
const REAL_RAW = path.join(ROOT, 'data', 'raw', 'contributions');
const PAGE_URL = 'https://www.stxbp1disorders.org/research-resources';
const TOKEN = 'test-token-0123456789abcdef';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const web = (url, quote) => ({ source: 'Website', ref: url, url, quote, kind: 'website', extracted_by: 'agent-curation', verified: true, retrieved: '2026-10-03' });
const causes = (g) => ({ id: `gene:${g}|causes|disease:${g}`, source: `gene:${g}`, target: `disease:${g}`, type: 'causes', evidence_level: 'curated', status: 'supported', confidence: 0.9, evidence: [] });

const GRAPH = {
  meta: { version: '0.1' },
  nodes: [
    { id: 'disease:STXBP1', type: 'disease', label: 'STXBP1-related disorders', synonyms: ['DEE4', 'STXBP1 encephalopathy', 'Munc18-1 encephalopathy', 'Ohtahara syndrome (STXBP1)'], attrs: { gene: 'STXBP1' } },
    { id: 'gene:STXBP1', type: 'gene', label: 'STXBP1', synonyms: ['Munc18-1', 'UNC18', 'p67'] },
    { id: 'disease:SYT1', type: 'disease', label: 'SYT1-related disorders (Baker-Gordon syndrome)', synonyms: ['Baker-Gordon syndrome', 'BAGOS'], attrs: { gene: 'SYT1' } },
    { id: 'gene:SYT1', type: 'gene', label: 'SYT1', synonyms: ['synaptotagmin-1', 'P65', 'SYT'] },
    { id: 'disease:SLC6A1', type: 'disease', label: 'SLC6A1-related disorders', synonyms: ['MAE', 'Doose syndrome', 'GAT-1 deficiency', 'autosomal dominant mental retardation'], attrs: { gene: 'SLC6A1' } },
    { id: 'gene:SLC6A1', type: 'gene', label: 'SLC6A1', synonyms: ['GAT-1', 'GAT1'] },
    { id: 'disease:NSF', type: 'disease', label: 'NSF-related developmental and epileptic encephalopathy', synonyms: ['DEE96'], attrs: { gene: 'NSF' } },
    { id: 'gene:NSF', type: 'gene', label: 'NSF', synonyms: ['N-ethylmaleimide-sensitive factor'] },
    { id: 'org:stxbp1-foundation', type: 'patient_org', label: 'STXBP1 Foundation', attrs: { url: 'https://www.stxbp1disorders.org/' }, sources: [web('https://www.stxbp1disorders.org/applyforagrant', 'The STXBP1 Foundation is a non-profit advocacy organization.')] },
    { id: 'org:combinedbrain', type: 'patient_org', label: 'COMBINEDBrain', attrs: { url: 'https://combinedbrain.org/' } },
    { id: 'asset:simons-searchlight', type: 'asset', label: 'Simons Searchlight (registry, natural history & biorepository)', xrefs: { NCT: 'NCT01238250' }, attrs: { kind: 'registry', url: 'https://www.simonssearchlight.org/research/what-we-study/' } },
    { id: 'asset:esco-european-stxbp1-consortium', type: 'asset', label: 'ESCO – European STXBP1 Consortium (registry + natural history study)', xrefs: { NCT: 'NCT06625112' }, attrs: { kind: 'research_network', url: 'https://stxbp1eu.org' } },
    { id: 'asset:bagos-registry', type: 'asset', label: 'Baker-Gordon Syndrome Foundation registry', attrs: { kind: 'registry', url: 'https://www.bagosfoundation.org/registry' } },
    { id: 'asset:heidelberg-stxbp1-registry', type: 'asset', label: 'STXBP1 patient registry (University Hospital Heidelberg)', attrs: { kind: 'registry', url: 'https://www.klinikum.uni-heidelberg.de/stxbp1-register' } },
    { id: 'asset:stxbp1-haploinsufficient-mice', type: 'asset', label: 'Stxbp1 haploinsufficient mouse models (Xue lab, Baylor)', attrs: { kind: 'animal_model', url: 'https://www.texaschildrens.org/xue-lab' } },
    { id: 'study:NCT06555965', type: 'study', label: 'STXBP1 and SYNGAP1 Related Disorders Natural History Study', xrefs: { NCT: 'NCT06555965' }, attrs: { status: 'RECRUITING', url: 'https://clinicaltrials.gov/study/NCT06555965' } },
  ],
  edges: [
    causes('STXBP1'), causes('SYT1'), causes('SLC6A1'), causes('NSF'),
    {
      id: 'asset:simons-searchlight|covers|disease:STXBP1', source: 'asset:simons-searchlight', target: 'disease:STXBP1', type: 'covers',
      evidence_level: 'observational', status: 'supported', confidence: 0.85, evidence: [web('https://www.simonssearchlight.org/research/what-we-study/', 'Simons Searchlight studies STXBP1.')],
    },
  ],
};

const PAGE_HTML = `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Research Resources &amp; Registry | STXBP1 Foundation</title>
<meta name="description" content="Tools for STXBP1 researchers and families.">
<style>.x { content: "STYLE TEXT MUST GO" }</style>
<script>var secret = "SCRIPT TEXT MUST GO";</script>
</head>
<body>
<nav><a href="/">Home</a> <a href="/donate">Donate</a></nav>
<!-- COMMENT TEXT MUST GO -->
<h1>Research resources</h1>
<p>The STXBP1 Foundation&rsquo;s patient registry collects medical histories from families of people with STXBP1-related disorders worldwide.</p>
<p>Families can join the registry online after giving consent, and researchers can request de-identified data.</p>
<p>A knock-in mouse carrying a patient variant in <i>Stxbp1</i> is available to academic labs through a material transfer agreement.</p>
<p>The STARR natural history study (NCT06555965) follows children with STXBP1 over three years.</p>
<p>We also partner with Simons&nbsp;Searchlight, an online registry for rare genetic conditions.</p>
<p>Questions? Write to info@stxbp1disorders.org and we will answer within a week.</p>
<p>Our seed grant program funds early-career investigators studying SYNGAP1 and other synaptic genes.</p>
</body></html>`;

const item = (over) => ({ kind: 'asset', name: '', asset_kind: null, diseases_or_genes_mentioned: [], what_it_offers: 'Offers something.', how_to_access: null, quote: '', nct_id: null, ...over });

const ITEMS = [
  item({ name: 'STXBP1 Patient Registry', asset_kind: 'registry', diseases_or_genes_mentioned: ['STXBP1-related disorders', 'Dravet syndrome'], what_it_offers: 'Medical histories from families, shared with researchers; contact info@example.org.', how_to_access: 'Families join online after consent; researchers request de-identified data.', quote: "The STXBP1 Foundation's patient registry collects medical histories from families of people with STXBP1-related disorders worldwide." }),
  item({ name: 'Stxbp1 knock-in mouse', asset_kind: 'animal_model', diseases_or_genes_mentioned: ['Stxbp1'], nct_id: 'NCT01234567', quote: 'A knock-in mouse carrying a patient variant in Stxbp1 is available to academic labs through a material transfer agreement.' }),
  item({ kind: 'patient_org', name: 'STXBP1 Foundation', diseases_or_genes_mentioned: ['STXBP1'], quote: 'The STXBP1 Foundation’s patient registry collects medical histories from families of people with STXBP1-related disorders worldwide.' }),
  item({ name: 'Seizure diary', asset_kind: 'outcome_measure', quote: 'Families keep a daily seizure diary for the study and share it with clinicians.' }),
  item({ kind: 'study', name: 'STARR natural history study', nct_id: 'NCT06555965', diseases_or_genes_mentioned: ['STXBP1'], quote: 'The STARR natural history study (NCT06555965) follows children with STXBP1 over three years.' }),
  item({ name: 'Simons Searchlight', asset_kind: 'registry', quote: 'We also partner with Simons Searchlight, an online registry for rare genetic conditions.' }),
  item({ name: 'Seed grant program', asset_kind: 'funding_program', diseases_or_genes_mentioned: ['SYNGAP1'], quote: 'Our seed grant program funds early-career investigators studying SYNGAP1 and other synaptic genes.' }),
];

function fakeComplete(items, calls, model = 'fake-model-1') {
  return async (request) => {
    calls.push(request);
    return { text: JSON.stringify({ items }), json: { items }, model, authPath: 'test', structuredMode: 'json_schema', usage: null, responseId: 'resp_test', requestId: 'req_test' };
  };
}

const html = (body, status = 200, headers = {}) => new Response(body, { status, headers: { 'content-type': 'text/html; charset=utf-8', ...headers } });

function mockFetch(routes, log = []) {
  const fn = async (url, init = {}) => {
    log.push({ url: String(url), method: init.method ?? 'GET', headers: init.headers ?? {}, body: init.body ?? null });
    const route = routes[String(url)];
    if (!route) return new Response('not found', { status: 404 });
    return route(String(url), init);
  };
  fn.log = log;
  return fn;
}

const publicLookup = async () => [{ address: '93.184.216.34', family: 4 }];
const NOW = new Date('2026-10-03T12:00:00Z');

let TMP;
const realState = {};

function snapshotReal() {
  return {
    fragment: existsSync(REAL_FRAGMENT) ? readFileSync(REAL_FRAGMENT, 'utf8') : null,
    fragmentMtime: existsSync(REAL_FRAGMENT) ? statSync(REAL_FRAGMENT).mtimeMs : null,
    raw: existsSync(REAL_RAW) ? readdirSync(REAL_RAW).sort() : null,
  };
}

/** A fresh workspace: graph fixture, empty fragment, raw cache dir. */
function workspace(name, graph = GRAPH) {
  const dir = path.join(TMP, name);
  mkdirSync(path.join(dir, 'raw'), { recursive: true });
  writeFileSync(path.join(dir, 'graph.json'), JSON.stringify(graph));
  writeFileSync(path.join(dir, 'contributions.json'), '{"nodes":[],"edges":[]}\n');
  return { dir, graphPath: path.join(dir, 'graph.json'), fragmentPath: path.join(dir, 'contributions.json'), rawDir: path.join(dir, 'raw') };
}

function options(ws, extra = {}) {
  return {
    graphPath: ws.graphPath,
    fragmentPath: ws.fragmentPath,
    rawDir: ws.rawDir,
    lookup: publicLookup,
    env: {},
    now: NOW,
    fetch: mockFetch({ [PAGE_URL]: () => html(PAGE_HTML) }),
    ...extra,
  };
}

before(() => {
  Object.assign(realState, snapshotReal());
  TMP = mkdtempSync(path.join(os.tmpdir(), 'contribute-test-'));
});

after(() => {
  rmSync(TMP, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// HTML to text
// ---------------------------------------------------------------------------

test('htmlToText drops script/style/comments/head, decodes entities and collapses whitespace', () => {
  const { title, description, body, text } = htmlToText(PAGE_HTML);
  assert.equal(title, 'Research Resources & Registry | STXBP1 Foundation');
  assert.equal(description, 'Tools for STXBP1 researchers and families.');
  for (const gone of ['STYLE TEXT', 'SCRIPT TEXT', 'COMMENT TEXT', '<p>', 'charset']) assert.ok(!text.includes(gone), `should drop ${gone}`);
  assert.ok(body.includes('The STXBP1 Foundation’s patient registry collects'), 'decodes &rsquo;');
  assert.ok(body.includes('variant in Stxbp1 is available'), 'inline tags leave no extra spaces');
  assert.ok(body.includes('partner with Simons Searchlight,'), '&nbsp; becomes a plain space');
  assert.ok(text.startsWith('Research Resources & Registry | STXBP1 Foundation\nTools for STXBP1'));
  assert.ok(!/ {2}|\t/.test(text), 'no runs of spaces');

  const tricky = htmlToText('<div title="a > b" data-x=\'1>2\'>Caf&eacute; &amp; &#8216;bar&#8217; &#x2014; &#150; x&nbsp;&nbsp; y</div><p>one<br>two</p><td>c1</td><td>c2</td>&unknown; &lt;b&gt;');
  assert.equal(tricky.text, 'Café & ‘bar’ — – x y\none\ntwo\nc1\nc2\n&unknown; <b>');
});

test('selectExcerpt keeps short pages whole and the relevant parts of long ones', () => {
  assert.deepEqual(selectExcerpt('short page'), { excerpt: 'short page', truncated: false });
  const filler = Array.from({ length: 400 }, (_, i) => `Lorem ipsum dolor sit amet line ${i} with nothing of interest to anyone at all.`);
  const key = 'Our biobank stores blood samples from patients, and researchers can request access.';
  filler.splice(250, 0, key);
  const { excerpt, truncated } = selectExcerpt(['Title line', 'Description line', ...filler].join('\n'), { maxChars: 12_000 });
  assert.equal(truncated, true);
  assert.ok(excerpt.length <= 12_000);
  assert.ok(excerpt.includes(key), 'keeps the biobank paragraph');
  assert.ok(excerpt.startsWith('Title line\nDescription line'), 'keeps the title lines first');
});

// ---------------------------------------------------------------------------
// Quote verification
// ---------------------------------------------------------------------------

test('verifyQuote passes verbatim quotes after whitespace/Unicode normalisation', () => {
  const page = htmlToText(PAGE_HTML).text;
  assert.deepEqual(verifyQuote("The STXBP1 Foundation's patient registry collects medical histories", page), { ok: true, verbatim: true, reason: null });
  assert.equal(verifyQuote('We also partner with Simons Searchlight,   an online\nregistry for rare genetic conditions.', page).ok, true);
  assert.equal(verifyQuote('A knock‑in mouse carrying a patient variant', page).ok, true, 'non-breaking hyphen folds to -');
});

test('verifyQuote fails paraphrases, case changes, short and missing quotes', () => {
  const page = htmlToText(PAGE_HTML).text;
  assert.equal(verifyQuote('The STXBP1 Foundation runs a registry of medical histories.', page).reason, 'not_on_page');
  assert.equal(verifyQuote("the stxbp1 foundation's patient registry collects", page).reason, 'not_on_page', 'case is preserved');
  assert.equal(verifyQuote('Research resources', page).reason, 'quote_too_short');
  assert.equal(verifyQuote('', page).reason, 'missing_quote');
  assert.equal(verifyQuote(null, page).ok, false);
});

// ---------------------------------------------------------------------------
// Reconciliation and duplicates
// ---------------------------------------------------------------------------

test('reconcileMention maps labels, specific synonyms, gene symbols and gene names to diseases', () => {
  const index = buildDiseaseIndex(GRAPH);
  const id = (m) => reconcileMention(m, index).matches.map((x) => x.id);
  assert.deepEqual(id('STXBP1'), ['disease:STXBP1']);
  assert.deepEqual(id('Stxbp1'), ['disease:STXBP1']);
  assert.deepEqual(id('Munc18-1'), ['disease:STXBP1']);
  assert.deepEqual(id('DEE4'), ['disease:STXBP1']);
  assert.deepEqual(id('Baker-Gordon Syndrome'), ['disease:SYT1']);
  assert.deepEqual(id('children with SLC6A1 variants'), ['disease:SLC6A1']);
  assert.deepEqual(id('GAT-1 deficiency'), ['disease:SLC6A1']);
  assert.deepEqual(id('NSF'), ['disease:NSF'], 'a short symbol matches as the whole mention');
  // broad or unknown names stay unreconciled
  for (const m of ['Doose syndrome', 'MAE', 'autosomal dominant mental retardation', 'SYNGAP1', 'Dravet syndrome', 'National Science Foundation (NSF)', 'P65']) {
    assert.equal(reconcileMention(m, index).status, 'unreconciled', m);
  }
});

test('findDuplicate matches existing nodes by name, label part, NCT and URL', () => {
  const nodeIndex = buildNodeIndex(GRAPH);
  const dup = (q, pageUrl = 'https://example.org/news', sameTypeOnPage = 2) => findDuplicate(q, { nodeIndex, pageUrl, sameTypeOnPage });
  assert.equal(dup({ type: 'patient_org', name: 'The STXBP1 Foundation, Inc.' }).id, 'org:stxbp1-foundation');
  assert.equal(dup({ type: 'asset', name: 'Simons Searchlight' }).match, 'name');
  assert.equal(dup({ type: 'asset', name: 'European STXBP1 Consortium' }).id, 'asset:esco-european-stxbp1-consortium');
  assert.equal(dup({ type: 'asset', name: 'ESCO' }).id, 'asset:esco-european-stxbp1-consortium');
  assert.deepEqual(
    (({ id, match }) => ({ id, match }))(dup({ type: 'study', name: 'Some other title', nct: 'NCT06555965' })),
    { id: 'study:NCT06555965', match: 'nct' },
  );
  const byUrl = dup({ type: 'asset', name: 'BAGOS family registry', assetKind: 'registry' }, 'http://bagosfoundation.org/registry/', 1);
  assert.deepEqual([byUrl.id, byUrl.match, byUrl.already_cites_url], ['asset:bagos-registry', 'url', true]);
  assert.equal(dup({ type: 'asset', name: 'Natural history study', assetKind: 'natural_history_study' }), null, 'generic names never match');
  assert.equal(dup({ type: 'asset', name: 'COMBINEDBrain' }), null, 'an asset never matches an organisation');
  assert.equal(dup({ type: 'patient_org', name: 'SLC6A1 Connect' }), null);
  // "STXBP1 patient registry (University Hospital Heidelberg)": the parenthesis is what identifies it
  assert.equal(dup({ type: 'asset', name: 'STXBP1 Patient Registry', assetKind: 'registry' }), null);
  assert.equal(dup({ type: 'asset', name: 'STXBP1 patient registry (University Hospital Heidelberg)' }).id, 'asset:heidelberg-stxbp1-registry');
  assert.equal(dup({ type: 'asset', name: 'Stxbp1 haploinsufficient mouse model' }).id, 'asset:stxbp1-haploinsufficient-mice', 'plural folding');
});

// ---------------------------------------------------------------------------
// preview()
// ---------------------------------------------------------------------------

test('preview: one model call, verified quotes, reconciled diseases, duplicates, nothing written to the fragment', async () => {
  const ws = workspace('preview');
  const calls = [];
  const result = await preview({ url: `${PAGE_URL}?utm_source=newsletter#top`, diseaseId: 'disease:STXBP1' }, options(ws, { complete: fakeComplete(ITEMS, calls), contributor: 'STXBP1 Foundation' }));

  assert.equal(calls.length, 1, 'exactly one model call');
  assert.ok(calls[0].schema && calls[0].instructions.includes('character for character'));
  assert.ok(calls[0].input.includes('<page>') && calls[0].input.includes('The STARR natural history study'));
  assert.ok(!calls[0].input.includes('info@stxbp1disorders.org'), 'e-mail addresses never reach the model');
  assert.equal(result.url, PAGE_URL, 'tracking parameters and fragment removed');
  assert.equal(result.page.via, 'direct');
  assert.equal(result.extraction.extracted_by, 'openai:fake-model-1');

  const status = Object.fromEntries(result.items.map((it) => [it.name, it.status]));
  assert.deepEqual(status, {
    'STXBP1 Patient Registry': 'new',
    'Stxbp1 knock-in mouse': 'new',
    'STXBP1 Foundation': 'duplicate',
    'Seizure diary': 'rejected',
    'STARR natural history study': 'duplicate',
    'Simons Searchlight': 'duplicate',
    'Seed grant program': 'new',
  });
  assert.deepEqual(result.verification.failed.map((f) => [f.name, f.reason]), [['Seizure diary', 'not_on_page']]);
  assert.equal(result.verification.passed, 6);

  const byName = Object.fromEntries(result.items.map((it) => [it.name, it]));
  const registry = byName['STXBP1 Patient Registry'];
  assert.equal(registry.node_id, 'asset:stxbp1-patient-registry');
  assert.deepEqual(registry.diseases, [{ id: 'disease:STXBP1', label: 'STXBP1-related disorders', basis: 'quote' }]);
  assert.deepEqual(registry.mentions.map((m) => [m.mention, m.status]), [['STXBP1-related disorders', 'reconciled'], ['Dravet syndrome', 'not_on_page']]);
  assert.ok(!registry.what_it_offers.includes('@'), 'e-mails are redacted from model text');
  const mouse = byName['Stxbp1 knock-in mouse'];
  assert.equal(mouse.nct_id, null, 'an NCT number not on the page is ignored');
  assert.match(mouse.warnings.join(' '), /NCT01234567 is not written on the page/);
  assert.deepEqual(byName['STARR natural history study'].duplicate_of.id, 'study:NCT06555965');
  assert.deepEqual(byName['Seed grant program'].diseases, [{ id: 'disease:STXBP1', label: 'STXBP1-related disorders', basis: 'page' }], 'the contributor picked STXBP1 and the page names it elsewhere');
  assert.deepEqual(byName['Seed grant program'].mentions.map((m) => m.status), ['unreconciled']);
  assert.deepEqual(result.duplicates.map((d) => [d.existing_id, d.match]), [['org:stxbp1-foundation', 'name'], ['study:NCT06555965', 'nct'], ['asset:simons-searchlight', 'name']]);

  // Fragment: new nodes carry attrs.contributed; duplicates are stubs that only add a source
  const nodes = Object.fromEntries(result.fragment.nodes.map((n) => [n.id, n]));
  assert.deepEqual(Object.keys(nodes).sort(), ['asset:seed-grant-program', 'asset:simons-searchlight', 'asset:stxbp1-knock-in-mouse', 'asset:stxbp1-patient-registry', 'org:stxbp1-foundation', 'study:NCT06555965']);
  assert.deepEqual(nodes['asset:stxbp1-patient-registry'].attrs, {
    kind: 'registry', url: PAGE_URL, access: 'Families join online after consent; researchers request de-identified data.',
    contributed: { by: 'STXBP1 Foundation', date: '2026-10-03', url: PAGE_URL },
  });
  assert.deepEqual(nodes['org:stxbp1-foundation'].attrs, { contributed_sources: [{ by: 'STXBP1 Foundation', date: '2026-10-03', url: PAGE_URL }] });
  assert.equal(nodes['org:stxbp1-foundation'].label, 'STXBP1 Foundation');
  const ev = nodes['asset:stxbp1-patient-registry'].sources[0];
  assert.deepEqual(ev, {
    source: 'Website', ref: PAGE_URL, url: PAGE_URL, title: 'Research Resources & Registry | STXBP1 Foundation', quote: ITEMS[0].quote,
    kind: 'website', extracted_by: 'openai:fake-model-1', verified: true, retrieved: '2026-10-03',
  });
  assert.equal(nodes['org:stxbp1-foundation'].sources.length, 1, 'the same sentence twice is one source');

  const edges = Object.fromEntries(result.fragment.edges.map((e) => [e.id, e]));
  assert.deepEqual(Object.keys(edges).sort(), [
    'asset:seed-grant-program|covers|disease:STXBP1',
    'asset:simons-searchlight|covers|disease:STXBP1',
    'asset:stxbp1-knock-in-mouse|covers|disease:STXBP1',
    'asset:stxbp1-patient-registry|covers|disease:STXBP1',
    'org:stxbp1-foundation|maintains|asset:seed-grant-program',
    'org:stxbp1-foundation|maintains|asset:simons-searchlight',
    'org:stxbp1-foundation|maintains|asset:stxbp1-knock-in-mouse',
    'org:stxbp1-foundation|maintains|asset:stxbp1-patient-registry',
    'org:stxbp1-foundation|serves|disease:STXBP1',
    'study:NCT06555965|studies|disease:STXBP1',
  ]);
  for (const e of Object.values(edges)) {
    assert.equal(e.status, 'unverified');
    assert.equal(e.evidence_level, 'observational');
    assert.ok(e.confidence <= 0.5, `${e.id} confidence ${e.confidence}`);
    assert.ok(['covers', 'serves', 'maintains', 'studies'].includes(e.type));
    for (const x of e.evidence) assert.equal(x.verified, true);
  }
  assert.equal(edges['asset:stxbp1-patient-registry|covers|disease:STXBP1'].confidence, 0.5);
  assert.equal(edges['asset:seed-grant-program|covers|disease:STXBP1'].confidence, 0.4);
  assert.equal(edges['org:stxbp1-foundation|maintains|asset:stxbp1-patient-registry'].attrs.basis, 'quote_names_org');
  assert.equal(edges['org:stxbp1-foundation|maintains|asset:stxbp1-knock-in-mouse'].attrs.basis, 'org_website');
  assert.equal(result.summary.evidence_for_existing_edges, 1, 'the Simons Searchlight covers edge already exists');
  assert.equal(result.summary.new_nodes, 3);
  assert.equal(result.summary.new_sources_for_existing_nodes, 3);

  // Only the raw cache was written
  assert.equal(readFileSync(ws.fragmentPath, 'utf8'), '{"nodes":[],"edges":[]}\n');
  const cached = JSON.parse(readFileSync(pageCachePath(PAGE_URL, ws.rawDir), 'utf8'));
  assert.equal(cached.retrieved, '2026-10-03');
  assert.equal(cached.via, 'direct');
  assert.ok(!cached.html.includes('info@stxbp1disorders.org') && cached.html.includes('[email-redacted]'));

  // A second preview reuses the cached page and extraction: no new fetch, no new model call
  const fetch2 = mockFetch({});
  const again = await preview({ url: PAGE_URL, diseaseId: 'disease:STXBP1' }, options(ws, { complete: fakeComplete(ITEMS, calls), fetch: fetch2 }));
  assert.equal(calls.length, 1);
  assert.equal(fetch2.log.length, 0);
  assert.equal(again.page.from_cache, true);
  assert.equal(again.extraction.from_cache, true);
  assert.equal(again.extraction.id, result.extraction.id);
});

test('preview: a long page sends at most ~12k characters, keeping the relevant part', async () => {
  const ws = workspace('long');
  const filler = Array.from({ length: 600 }, (_, i) => `<p>Lorem ipsum dolor sit amet, paragraph ${i}, consectetur adipiscing elit sed do eiusmod.</p>`).join('\n');
  const key = '<p>Our biobank stores blood samples from people with STXBP1-related disorders for approved research projects.</p>';
  const page = `<html><head><title>Long page</title></head><body>${filler.slice(0, 30_000)}${key}${filler.slice(30_000)}</body></html>`;
  const calls = [];
  const items = [item({ name: 'STXBP1 biobank', asset_kind: 'biobank', diseases_or_genes_mentioned: ['STXBP1'], quote: 'Our biobank stores blood samples from people with STXBP1-related disorders for approved research projects.' })];
  const result = await preview({ url: 'https://example.org/long' }, options(ws, { complete: fakeComplete(items, calls), fetch: mockFetch({ 'https://example.org/long': () => html(page) }) }));
  const sent = calls[0].input.split('<page>\n')[1].split('\n</page>')[0];
  assert.ok(result.page.text_chars > 40_000);
  assert.ok(sent.length <= 12_000, `sent ${sent.length}`);
  assert.ok(sent.includes('Our biobank stores blood samples'));
  assert.equal(result.extraction.excerpt_truncated, true);
  assert.equal(result.items[0].status, 'new');
});

test('preview: blocked direct fetch falls back to Bright Data Web Unlocker; the token never leaks', async () => {
  const ws = workspace('brightdata');
  const bot = '<html><head><title>Just a moment...</title></head><body><div id="challenge-platform/h/b">checking</div></body></html>';
  const fetch = mockFetch({
    [PAGE_URL]: () => html(bot, 403),
    [BRIGHTDATA_API]: (_, init) => {
      assert.equal(init.method, 'POST');
      assert.equal(init.headers.authorization, `Bearer ${TOKEN}`);
      assert.equal(init.headers['content-type'], 'application/json');
      assert.deepEqual(JSON.parse(init.body), { zone: 'unlocker_test_zone', url: PAGE_URL, format: 'raw' });
      return html(PAGE_HTML);
    },
  });
  const calls = [];
  const result = await preview({ url: PAGE_URL }, options(ws, { fetch, env: { BRIGHTDATA_API_TOKEN: TOKEN, BRIGHTDATA_UNLOCKER_ZONE: 'unlocker_test_zone' }, complete: fakeComplete(ITEMS, calls) }));
  assert.deepEqual(fetch.log.map((r) => [r.method, r.url]), [['GET', PAGE_URL], ['POST', BRIGHTDATA_API]]);
  assert.equal(result.page.via, 'brightdata');
  assert.equal(result.page.direct_problem, 'HTTP 403');
  assert.equal(result.items.find((it) => it.name === 'STXBP1 Patient Registry').status, 'new');
  assert.ok(!JSON.stringify(result).includes(TOKEN), 'token not in the result');
  for (const f of readdirSync(ws.rawDir)) assert.ok(!readFileSync(path.join(ws.rawDir, f), 'utf8').includes(TOKEN), `token not in ${f}`);

  // A 200 bot-check page (no HTTP error) also triggers the fallback
  const ws2 = workspace('brightdata-200');
  const fetch2 = mockFetch({ [PAGE_URL]: () => html(bot, 200), [BRIGHTDATA_API]: () => html(PAGE_HTML) });
  const r2 = await preview({ url: PAGE_URL }, options(ws2, { fetch: fetch2, env: { BRIGHTDATA_API_TOKEN: TOKEN }, complete: fakeComplete(ITEMS, []) }));
  assert.equal(r2.page.via, 'brightdata');
  assert.equal(JSON.parse(fetch2.log[1].body).zone, 'web_unlocker1', 'default zone');

  // A network error on the direct fetch also falls back
  const ws3 = workspace('brightdata-neterr');
  const fetch3 = mockFetch({ [PAGE_URL]: () => { throw Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNRESET' } }); }, [BRIGHTDATA_API]: () => html(PAGE_HTML) });
  const r3 = await preview({ url: PAGE_URL }, options(ws3, { fetch: fetch3, env: { BRIGHTDATA_API_TOKEN: TOKEN }, complete: fakeComplete(ITEMS, []) }));
  assert.equal(r3.page.direct_problem, 'ECONNRESET');

  // Web Unlocker headers: the target's redirect becomes the cited URL; its 404 is a not-found error
  const ws4 = workspace('brightdata-headers');
  const moved = 'https://www.stxbp1disorders.org/research-resources-2026';
  const fetch4 = mockFetch({ [PAGE_URL]: () => html(bot, 403), [BRIGHTDATA_API]: () => html(PAGE_HTML, 200, { 'x-brd-status-code': '200', 'x-unblocker-redirected-to': moved }) });
  const r4 = await preview({ url: PAGE_URL }, options(ws4, { fetch: fetch4, env: { BRIGHTDATA_API_TOKEN: TOKEN }, complete: fakeComplete(ITEMS, []) }));
  assert.deepEqual([r4.requested_url, r4.url], [PAGE_URL, moved]);
  assert.equal(r4.fragment.nodes.find((n) => n.id === 'asset:stxbp1-patient-registry').sources[0].ref, moved);
  const soft404 = '<html><head><title>Page Not Found - Some Charity</title></head><body><p>Sorry, we could not find that page. Try the menu above, our search box or the site map to find what you were looking for.</p></body></html>';
  const fetch5 = mockFetch({ [PAGE_URL]: () => html(bot, 403), [BRIGHTDATA_API]: () => html(soft404, 200, { 'x-brd-status-code': '404' }) });
  await assert.rejects(preview({ url: PAGE_URL }, options(workspace('brightdata-404'), { fetch: fetch5, env: { BRIGHTDATA_API_TOKEN: TOKEN } })), { code: 'not_found' });
  const fetch6 = mockFetch({ [PAGE_URL]: () => html(soft404, 200), [BRIGHTDATA_API]: () => assert.fail('no Bright Data call for a soft 404') });
  await assert.rejects(preview({ url: PAGE_URL }, options(workspace('soft-404'), { fetch: fetch6, env: { BRIGHTDATA_API_TOKEN: TOKEN } })), { code: 'not_found' });
});

test('preview: fetch failures give clear errors without the token', async () => {
  const ws = workspace('fetch-errors');
  const blocked = mockFetch({ [PAGE_URL]: () => html('denied', 403) });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { fetch: blocked, complete: fakeComplete(ITEMS, []) })), (e) => {
    assert.ok(e instanceof ContributeError);
    assert.equal(e.code, 'fetch_failed');
    assert.match(e.message, /HTTP 403.*Bright Data fallback is not configured/);
    return true;
  });
  const bdDown = mockFetch({ [PAGE_URL]: () => html('denied', 403), [BRIGHTDATA_API]: () => new Response(`zone error for ${TOKEN}`, { status: 502, headers: { 'x-brd-error': 'zone_not_found' } }) });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { fetch: bdDown, env: { BRIGHTDATA_API_TOKEN: TOKEN } })), (e) => {
    assert.equal(e.code, 'fetch_failed');
    assert.match(e.message, /Bright Data returned HTTP 502 \(zone_not_found\)/);
    assert.ok(!e.message.includes(TOKEN) && !JSON.stringify(toHttpError(e)).includes(TOKEN));
    return true;
  });
  const notFound = mockFetch({ [PAGE_URL]: () => html('gone', 404), [BRIGHTDATA_API]: () => assert.fail('no Bright Data call for a 404') });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { fetch: notFound, env: { BRIGHTDATA_API_TOKEN: TOKEN } })), { code: 'not_found' });
  const pdf = mockFetch({ [PAGE_URL]: () => new Response('%PDF-1.7', { headers: { 'content-type': 'application/pdf' } }) });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { fetch: pdf })), { code: 'unsupported_content' });
});

test('preview: invalid input is rejected before any fetch', async () => {
  const ws = workspace('input');
  const fetch = mockFetch({});
  const opts = options(ws, { fetch, complete: fakeComplete(ITEMS, []) });
  await assert.rejects(preview({ url: 'ftp://example.org/x' }, opts), { code: 'invalid_url' });
  await assert.rejects(preview({ url: 'https://user:pw@example.org/' }, opts), { code: 'invalid_url' });
  await assert.rejects(preview({ url: '' }, opts), { code: 'invalid_url' });
  await assert.rejects(preview({ url: 'http://127.0.0.1:3000/admin' }, opts), { code: 'blocked_host' });
  await assert.rejects(preview({ url: 'http://localhost/x' }, opts), { code: 'blocked_host' });
  await assert.rejects(preview({ url: 'https://intranet.example.org/' }, { ...opts, lookup: async () => [{ address: '10.0.0.5', family: 4 }] }), { code: 'blocked_host' });
  await assert.rejects(preview({ url: PAGE_URL, diseaseId: 'disease:NOPE' }, opts), { code: 'unknown_disease' });
  assert.equal(fetch.log.length, 0);
  const redirectToLocal = mockFetch({ [PAGE_URL]: () => new Response(null, { status: 302, headers: { location: 'http://127.0.0.1/secret' } }) });
  await assert.rejects(preview({ url: PAGE_URL }, { ...opts, fetch: redirectToLocal }), { code: 'blocked_host' });
});

test('preview: model errors map to stable codes', async () => {
  const ws = workspace('llm-errors');
  const usage = Object.assign(new Error('The ChatGPT plan or this app\'s usage limit was reached.'), { name: 'LLMRequestError', kind: 'usage_limit', manageUsageUrl: 'https://chatgpt.com/settings/usage' });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { complete: async () => { throw usage; } })), (e) => {
    assert.equal(e.code, 'llm_usage_limit');
    assert.equal(e.status, 429);
    assert.equal(toHttpError(e).error.llm.manage_usage_url, 'https://chatgpt.com/settings/usage');
    return true;
  });
  const none = Object.assign(new Error('No OpenAI credentials available.'), { name: 'NoLLMAvailableError', code: 'no_llm_available' });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { complete: async () => { throw none; }, reextract: true })), { code: 'llm_unavailable', status: 401 });
  await assert.rejects(preview({ url: PAGE_URL }, options(ws, { complete: async () => ({ json: { nope: 1 } }), reextract: true })), { code: 'llm_bad_output' });
});

test('preview: manual items (no AI) are verified the same way and attributed to the contributor', async () => {
  const ws = workspace('manual');
  const result = await preview({ url: PAGE_URL, items: [ITEMS[0], ITEMS[3]] }, options(ws, { complete: () => assert.fail('no model call'), contributor: 'Jane (STXBP1 parent)' }));
  assert.equal(result.extraction.extracted_by, 'human:Jane (STXBP1 parent)');
  assert.deepEqual(result.items.map((it) => it.status), ['new', 'rejected']);
  assert.equal(result.fragment.nodes.find((n) => n.id === 'asset:stxbp1-patient-registry').sources[0].extracted_by, 'human:Jane (STXBP1 parent)');

  // A disease the page never names: linked only on the contributor's word, at 0.3
  const hinted = await preview({ url: PAGE_URL, diseaseId: 'disease:SYT1', items: [ITEMS[6]] }, options(ws, { contributor: 'Jane' }));
  assert.deepEqual(hinted.items[0].diseases, [{ id: 'disease:SYT1', label: 'SYT1-related disorders (Baker-Gordon syndrome)', basis: 'contributor' }]);
  const edge = hinted.fragment.edges.find((e) => e.type === 'covers');
  assert.equal(edge.confidence, 0.3);
  assert.match(edge.explanation, /the page text does not name the disease/);
});

// ---------------------------------------------------------------------------
// commit()
// ---------------------------------------------------------------------------

test('commit: writes a normal fragment, is idempotent, and replaces an earlier contribution from the same URL', async () => {
  const ws = workspace('commit');
  const calls = [];
  const opts = options(ws, { complete: fakeComplete(ITEMS, calls), rebuild: false });
  const first = await preview({ url: PAGE_URL }, opts);
  const seed = first.items.find((it) => it.name === 'Seed grant program');
  assert.equal(seed.status, 'new');
  assert.deepEqual(seed.diseases, [], 'no atlas disease named and none picked');
  assert.deepEqual(seed.edges.map((e) => [e.id, e.basis]), [['org:stxbp1-foundation|maintains|asset:seed-grant-program', 'org_website']], 'linked only through the organisation whose site it is on');

  const c1 = await commit(first, { ...opts, contributor: 'STXBP1 Foundation' });
  assert.equal(c1.changed, true);
  assert.equal(c1.rebuild.ran, false);
  const text1 = readFileSync(ws.fragmentPath, 'utf8');
  const frag1 = JSON.parse(text1);
  assert.deepEqual(Object.keys(frag1), ['nodes', 'edges']);
  const ids1 = frag1.nodes.map((n) => n.id);
  assert.deepEqual(ids1, [...new Set(ids1)].sort(), 'sorted, unique node ids');
  assert.equal(frag1.nodes.find((n) => n.id === 'asset:stxbp1-patient-registry').attrs.contributed.by, 'STXBP1 Foundation');
  assert.ok(frag1.edges.every((e) => e.id === `${e.source}|${e.type}|${e.target}` && e.evidence.length >= 1));

  // Same preview again: nothing changes, byte for byte
  const c2 = await commit(first, { ...opts, contributor: 'STXBP1 Foundation' });
  assert.equal(c2.changed, false);
  assert.equal(readFileSync(ws.fragmentPath, 'utf8'), text1);

  // Re-preview of the same URL (now cached) and commit: still no change
  const again = await preview({ url: PAGE_URL }, opts);
  await commit(again, { ...opts, contributor: 'STXBP1 Foundation' });
  assert.equal(readFileSync(ws.fragmentPath, 'utf8'), text1);
  assert.equal(calls.length, 1);

  // Fresh extraction with a renamed item: the old node is replaced, nothing is duplicated
  const renamed = ITEMS.map((x, i) => (i === 0 ? { ...x, name: 'STXBP1 Registry' } : x));
  const third = await preview({ url: PAGE_URL }, { ...opts, complete: fakeComplete(renamed, calls), reextract: true });
  await assert.rejects(commit(first, { ...opts }), { code: 'stale_preview' }, 'an outdated preview cannot be committed');
  const c3 = await commit(third, { ...opts, contributor: 'STXBP1 Foundation' });
  assert.equal(c3.changed, true);
  assert.ok(c3.replaced.nodes.includes('asset:stxbp1-patient-registry'));
  const frag3 = JSON.parse(readFileSync(ws.fragmentPath, 'utf8'));
  const ids3 = frag3.nodes.map((n) => n.id);
  assert.ok(ids3.includes('asset:stxbp1-registry') && !ids3.includes('asset:stxbp1-patient-registry'));
  assert.ok(!frag3.edges.some((e) => e.source === 'asset:stxbp1-patient-registry' || e.target === 'asset:stxbp1-patient-registry'));
  const org = frag3.nodes.find((n) => n.id === 'org:stxbp1-foundation');
  assert.equal(org.sources.length, 1);
  assert.equal(org.attrs.contributed_sources.length, 1);
  assert.equal(frag3.edges.length, frag1.edges.length);

  // After a rebuild, graph.json contains this URL's own nodes: they are not "duplicates" of themselves
  const rebuilt = structuredClone(GRAPH);
  rebuilt.nodes.push(...frag3.nodes.filter((n) => n.attrs?.contributed));
  writeFileSync(ws.graphPath, JSON.stringify(rebuilt));
  const fourth = await preview({ url: PAGE_URL }, opts);
  assert.equal(fourth.items.find((it) => it.name === 'STXBP1 Registry').status, 'new');
  assert.deepEqual(fourth.previous_contribution.nodes.includes('asset:stxbp1-registry'), true);
  const c4 = await commit(fourth, { ...opts, contributor: 'STXBP1 Foundation' });
  assert.equal(c4.changed, false);

  // include: commit a subset only
  const subset = await commit(fourth, { ...opts, contributor: 'STXBP1 Foundation', include: [2] });
  assert.equal(subset.changed, true);
  const fragSub = JSON.parse(readFileSync(ws.fragmentPath, 'utf8'));
  assert.deepEqual(fragSub.nodes.map((n) => n.id), ['org:stxbp1-foundation']);
});

test('commit: a different contributor URL adds a source to a node contributed earlier', async () => {
  const ws = workspace('two-urls');
  const opts = options(ws, { rebuild: false });
  const p1 = await preview({ url: PAGE_URL, items: [ITEMS[0]] }, { ...opts, contributor: 'A' });
  await commit(p1, opts);
  // simulate the rebuild: the contributed node is now in the graph
  const frag = JSON.parse(readFileSync(ws.fragmentPath, 'utf8'));
  const g = structuredClone(GRAPH);
  g.nodes.push(...frag.nodes.filter((n) => n.attrs?.contributed));
  writeFileSync(ws.graphPath, JSON.stringify(g));
  const other = 'https://news.example.org/stxbp1-registry-launch';
  const page2 = '<html><head><title>News</title></head><body><p>Families can now join the STXBP1 Patient Registry, which collects medical histories from people with STXBP1-related disorders.</p><p>A new biobank for synaptic disorders opened in Leiden this year.</p><p>More text here so the page is not empty, with enough characters to look like a real article about the registry launch.</p></body></html>';
  const p2 = await preview(
    {
      url: other,
      items: [
        item({ name: 'STXBP1 Patient Registry', asset_kind: 'registry', quote: 'Families can now join the STXBP1 Patient Registry, which collects medical histories from people with STXBP1-related disorders.' }),
        item({ name: 'Leiden synaptic biobank', asset_kind: 'biobank', quote: 'A new biobank for synaptic disorders opened in Leiden this year.' }),
      ],
    },
    { ...opts, contributor: 'B', fetch: mockFetch({ [other]: () => html(page2) }) },
  );
  assert.equal(p2.items[0].status, 'duplicate');
  assert.equal(p2.items[0].duplicate_of.id, 'asset:stxbp1-patient-registry');
  assert.equal(p2.items[1].status, 'unlinked', 'no disease and no organisation: held back instead of floating');
  assert.ok(!p2.fragment.nodes.some((n) => n.id === 'asset:leiden-synaptic-biobank'));
  await commit(p2, opts);
  const node = JSON.parse(readFileSync(ws.fragmentPath, 'utf8')).nodes.find((n) => n.id === 'asset:stxbp1-patient-registry');
  assert.deepEqual(node.sources.map((s) => s.ref), [PAGE_URL, other]);
  assert.equal(node.attrs.contributed.by, 'A');
  assert.deepEqual(node.attrs.contributed_sources.map((c) => c.by), ['B']);
});

test('preview: a page the curated data already cites adds only new sentences, to existing edges', async () => {
  const regUrl = 'https://www.bagosfoundation.org/registry';
  const cited = 'Join the Baker-Gordon Syndrome registry to help research move faster.';
  const fresh = 'Our registry lets families with Baker-Gordon syndrome share medical history securely online.';
  const g = structuredClone(GRAPH);
  g.nodes.find((n) => n.id === 'asset:bagos-registry').sources = [web(regUrl, cited)];
  g.edges.push({ id: 'asset:bagos-registry|covers|disease:SYT1', source: 'asset:bagos-registry', target: 'disease:SYT1', type: 'covers', evidence_level: 'observational', status: 'supported', confidence: 0.85, evidence: [web(regUrl, cited)] });
  const ws = workspace('already-cited', g);
  const pageHtml = `<html><head><title>Registry</title></head><body><p>${cited}</p><p>${fresh}</p><p>Registration takes ten minutes and you can stop at any time; nothing is shared without your permission.</p></body></html>`;
  const items = [
    item({ name: 'BAGOS registry', asset_kind: 'registry', quote: cited }),
    item({ name: 'Baker-Gordon Syndrome Foundation registry', asset_kind: 'registry', quote: fresh }),
  ];
  const r = await preview({ url: regUrl, items }, options(ws, { fetch: mockFetch({ [regUrl]: () => html(pageHtml) }) }));
  assert.deepEqual(r.items.map((it) => [it.status, it.node_id, it.duplicate_of?.match]), [['duplicate', 'asset:bagos-registry', 'id'], ['duplicate', 'asset:bagos-registry', 'name']]);
  assert.equal(r.items[0].already_cited, true);
  assert.deepEqual(r.fragment.nodes.map((n) => [n.id, n.sources.map((s) => s.quote)]), [['asset:bagos-registry', [fresh]]]);
  assert.deepEqual(r.fragment.edges.map((e) => [e.id, e.evidence.map((x) => x.quote)]), [['asset:bagos-registry|covers|disease:SYT1', [fresh]]]);
  assert.equal(r.items[1].edges[0].status, 'adds_evidence', 'curated evidence from the same URL is not "our earlier contribution"');
  assert.equal(r.summary.new_edges, 0);
});

test('commit: refuses an empty contribution and an unknown preview', async () => {
  const ws = workspace('commit-errors');
  const opts = options(ws, { rebuild: false });
  const bad = await preview({ url: PAGE_URL, items: [ITEMS[3]] }, opts);
  assert.equal(bad.can_commit, false);
  await assert.rejects(commit(bad, opts), { code: 'nothing_to_commit', status: 422 });
  await assert.rejects(commit({ url: 'https://example.org/never-previewed' }, opts), { code: 'preview_expired', status: 409 });
  await assert.rejects(commit(null, opts), { code: 'invalid_preview' });
  assert.equal(readFileSync(ws.fragmentPath, 'utf8'), '{"nodes":[],"edges":[]}\n');
});

// ---------------------------------------------------------------------------
// Integration with pipeline/build_graph.py (on a temp copy of the pipeline and the fragments)
// ---------------------------------------------------------------------------

test('build_graph.py merges the committed fragment (temp copy of the real fragments)', async (t) => {
  try {
    execFileSync('python3', ['--version'], { stdio: 'ignore' });
  } catch {
    t.skip('python3 not available');
    return;
  }
  const copy = path.join(TMP, 'build');
  mkdirSync(path.join(copy, 'pipeline'), { recursive: true });
  cpSync(path.join(ROOT, 'pipeline', 'build_graph.py'), path.join(copy, 'pipeline', 'build_graph.py'));
  cpSync(path.join(ROOT, 'data', 'curated'), path.join(copy, 'data', 'curated'), { recursive: true });
  const ws = workspace('build-ws', JSON.parse(readFileSync(path.join(ROOT, 'data', 'graph.json'), 'utf8')));
  const fragmentPath = path.join(copy, 'data', 'curated', 'contributions.json');
  writeFileSync(fragmentPath, '{"nodes":[],"edges":[]}\n');
  const opts = options(ws, { fragmentPath, complete: fakeComplete(ITEMS, []), rebuild: false });
  const p = await preview({ url: PAGE_URL, diseaseId: 'disease:STXBP1' }, opts);
  await commit(p, { ...opts, contributor: 'STXBP1 Foundation' });

  execFileSync('python3', [path.join(copy, 'pipeline', 'build_graph.py')], { stdio: 'pipe' });
  const graph = JSON.parse(readFileSync(path.join(copy, 'data', 'graph.json'), 'utf8'));
  const nodes = new Map(graph.nodes.map((n) => [n.id, n]));
  const edges = new Map(graph.edges.map((e) => [e.id, e]));
  assert.equal(nodes.get('asset:stxbp1-patient-registry').attrs.contributed.by, 'STXBP1 Foundation');
  const org = nodes.get('org:stxbp1-foundation');
  assert.equal(org.label, 'STXBP1 Foundation');
  assert.ok(org.attrs.url, 'existing attrs kept');
  assert.ok(org.sources.some((s) => s.ref === PAGE_URL && s.extracted_by === 'openai:fake-model-1'), 'new supporting source merged into the existing node');
  assert.equal(org.attrs.contributed_sources[0].url, PAGE_URL);
  const covers = edges.get('asset:simons-searchlight|covers|disease:STXBP1');
  assert.equal(covers.status, 'supported', 'an existing edge keeps its curated status');
  assert.equal(covers.confidence, 0.85);
  assert.ok(covers.evidence.some((ev) => ev.ref === PAGE_URL));
  const fresh = edges.get('asset:stxbp1-patient-registry|covers|disease:STXBP1');
  assert.deepEqual([fresh.status, fresh.confidence], ['unverified', 0.5]);
  assert.equal(edges.get('study:NCT06555965|studies|disease:STXBP1').status, 'supported');
  const report = readFileSync(path.join(copy, 'data', 'build', 'report.md'), 'utf8');
  assert.match(report, /`contributions.json` \| \d+ \| \d+/);
  assert.ok(!/Dangling edges dropped[\s\S]*stxbp1-patient-registry/.test(report));
});

// ---------------------------------------------------------------------------
// Guard: the real data files are untouched
// ---------------------------------------------------------------------------

test('the real contributions.json and raw cache were not touched by these tests', () => {
  assert.deepEqual(snapshotReal(), realState);
});
