/**
 * Deterministic matching against the atlas graph: quote verification, disease and gene
 * reconciliation, and duplicate detection for patient organisations, assets and studies.
 * No network and no model calls. Dependency-free Node ESM.
 */

const INVISIBLE = /[­​-‍⁠﻿]/g;

// ---------------------------------------------------------------------------
// Quote verification
// ---------------------------------------------------------------------------

/**
 * NFKC, invisible characters removed, dash and curly-quote folding, whitespace collapsed. Case and
 * everything else are preserved (same folding as pipeline/openai/common.mjs norm()).
 */
export function norm(text) {
  return String(text ?? '')
    .normalize('NFKC')
    .replace(INVISIBLE, '')
    .replace(/[‐-―−]/g, '-')
    .replace(/[‘’‚‛′]/g, "'")
    .replace(/[“”„‟″]/g, '"')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
}

export const QUOTE_MIN_CHARS = 20;
export const QUOTE_MAX_CHARS = 800;

/**
 * Is `quote` a verbatim substring of the page text after normalisation? The quote itself is never
 * edited. Returns { ok, verbatim, reason } with reason one of: missing_quote, quote_too_short,
 * quote_too_long, not_on_page.
 */
export function verifyQuote(quote, pageText, { normalized = false } = {}) {
  if (typeof quote !== 'string' || !quote.trim()) return { ok: false, verbatim: false, reason: 'missing_quote' };
  const q = norm(quote);
  const verbatim = (normalized ? pageText : norm(pageText)).includes(q);
  if (!verbatim) return { ok: false, verbatim, reason: 'not_on_page' };
  if (q.length < QUOTE_MIN_CHARS) return { ok: false, verbatim, reason: 'quote_too_short' };
  if (q.length > QUOTE_MAX_CHARS) return { ok: false, verbatim, reason: 'quote_too_long' };
  return { ok: true, verbatim, reason: null };
}

// ---------------------------------------------------------------------------
// Keys
// ---------------------------------------------------------------------------

/** Lower case, accents and punctuation removed: "STXBP1-related Disorders" -> "stxbp1 related disorders". */
export function keyOf(text) {
  return String(text ?? '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9+]+/g, ' ')
    .split(' ')
    .filter((t) => t && t !== '+')
    .join(' ');
}

const padded = (text) => ` ${text} `;

export function slugify(text, max = 60) {
  return String(text ?? '')
    .replace(/[øØ]/g, 'o').replace(/[æÆ]/g, 'ae').replace(/ß/g, 'ss')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
    .slice(0, max)
    .replace(/-+$/g, '');
}

/** Comparable form of a URL: no scheme, no "www.", no trailing slash or index page, no fragment. */
export function urlKey(href) {
  try {
    const url = new URL(String(href ?? '').trim());
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    const pathname = url.pathname.replace(/\/index\.(html?|php|aspx?)$/i, '').replace(/\/+$/, '');
    return `${host}${pathname}${url.search}`;
  } catch {
    return String(href ?? '').trim().toLowerCase();
  }
}

export function hostOf(href) {
  try {
    return new URL(href).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Disease / gene reconciliation
// ---------------------------------------------------------------------------

function addTo(map, key, value) {
  if (!map.has(key)) map.set(key, new Set());
  map.get(key).add(value);
}

function diseaseLabelVariants(label) {
  const out = [];
  const bare = label.replace(/\s*\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
  if (bare && bare !== label) out.push(bare);
  for (const m of label.matchAll(/\(([^)]+)\)/g)) out.push(m[1].trim());
  return out;
}

/**
 * Index of the graph's disease names. A mention reconciles to a disease through:
 *   - the disease label (and its parenthetical parts, e.g. "Baker-Gordon syndrome"),
 *   - a disease synonym that is specific to it: it contains a number ("DEE4", "CMS18"), the gene
 *     symbol or a gene name ("GAT-1 deficiency"), or is part of the label. Broad clinical names that
 *     many genes cause ("Doose syndrome", "GEFS+", "myoclonic-atonic epilepsy") are left out,
 *   - the causative gene's symbol ("STXBP1", also "Stxbp1") or a gene name with a number
 *     ("Munc18-1", "SNAP-25"), via the graph's `causes` edges.
 * A name that points to more than one disease is ambiguous and never used. Names of 4+ characters
 * also match inside a longer mention ("children with STXBP1 variants"); shorter ones ("NSF") only
 * when they are the whole mention.
 */
export function buildDiseaseIndex(graph) {
  const nodes = new Map((graph?.nodes ?? []).map((n) => [n.id, n]));
  const diseases = (graph?.nodes ?? []).filter((n) => n.type === 'disease');
  const genesOf = new Map();
  for (const e of graph?.edges ?? []) {
    if (e.type === 'causes' && nodes.get(e.source)?.type === 'gene' && nodes.get(e.target)?.type === 'disease') addTo(genesOf, e.target, e.source);
  }
  for (const d of diseases) if (d.attrs?.gene && nodes.get(`gene:${d.attrs.gene}`)?.type === 'gene') addTo(genesOf, d.id, `gene:${d.attrs.gene}`);

  const exact = new Map(); // key -> Map(diseaseId -> { term, via })
  const add = (term, diseaseId, via) => {
    const key = keyOf(term);
    if (key.replace(/ /g, '').length < 2) return;
    if (!exact.has(key)) exact.set(key, new Map());
    if (!exact.get(key).has(diseaseId)) exact.get(key).set(diseaseId, { term, via });
  };
  for (const d of diseases) {
    const geneTerms = [];
    for (const geneId of genesOf.get(d.id) ?? []) {
      const gene = nodes.get(geneId);
      geneTerms.push({ term: gene.label, via: 'gene_symbol' });
      for (const s of gene.synonyms ?? []) {
        const k = keyOf(s);
        if (/\d/.test(k) && k.replace(/ /g, '').length >= 4) geneTerms.push({ term: s, via: 'gene_name' });
      }
    }
    const geneKeys = geneTerms.map((t) => keyOf(t.term)).filter((k) => k.replace(/ /g, '').length >= 4);
    const labelKey = padded(keyOf(d.label));
    add(d.label, d.id, 'label');
    for (const v of diseaseLabelVariants(d.label)) add(v, d.id, 'label');
    for (const s of d.synonyms ?? []) {
      const k = keyOf(s);
      const specific = /\d/.test(k) || geneKeys.some((g) => padded(k).includes(padded(g))) || labelKey.includes(padded(k));
      if (specific) add(s, d.id, 'synonym');
    }
    for (const t of geneTerms) add(t.term, d.id, t.via);
  }

  const ambiguous = new Set();
  for (const [key, hits] of exact) {
    if (hits.size > 1) {
      ambiguous.add(key);
      exact.delete(key);
    }
  }
  const scan = [...exact]
    .filter(([key]) => key.replace(/ /g, '').length >= 4)
    .map(([key, hits]) => {
      const [[diseaseId, info]] = [...hits];
      return { key, diseaseId, ...info };
    })
    .sort((a, b) => b.key.length - a.key.length);
  return { exact, scan, ambiguous, diseases: new Map(diseases.map((d) => [d.id, d])) };
}

const matchOf = (index, diseaseId, info) => ({ id: diseaseId, label: index.diseases.get(diseaseId)?.label ?? diseaseId, via: info.via, term: info.term });

/** Atlas diseases named anywhere in `text` (4+ character names, whole words). */
export function findDiseases(text, index) {
  const hay = padded(keyOf(text));
  const out = new Map();
  for (const t of index.scan) {
    if (!out.has(t.diseaseId) && hay.includes(padded(t.key))) out.set(t.diseaseId, matchOf(index, t.diseaseId, t));
  }
  return [...out.values()];
}

/** One mention -> { mention, status: reconciled|ambiguous|unreconciled, matches: [{id, label, via, term}] }. */
export function reconcileMention(mention, index) {
  const key = keyOf(mention);
  if (!key) return { mention, status: 'unreconciled', matches: [] };
  const hit = index.exact.get(key);
  if (hit) return { mention, status: 'reconciled', matches: [...hit].map(([id, info]) => matchOf(index, id, info)) };
  const found = findDiseases(mention, index);
  if (found.length) return { mention, status: 'reconciled', matches: found };
  return { mention, status: index.ambiguous.has(key) ? 'ambiguous' : 'unreconciled', matches: [] };
}

// ---------------------------------------------------------------------------
// Duplicate detection (patient_org, asset, study)
// ---------------------------------------------------------------------------

const NAME_STOP = new Set(['the', 'a', 'an', 'of', 'for', 'and', 'in', 'on', 'at', 'to', 'with', 'by', 'from', 'inc', 'ltd', 'llc', 'gmbh', 'ev']);
// Words that cannot identify a resource on their own ("Natural history study" names nothing specific).
// Tokens are compared after plural folding, so singular forms suffice.
const GENERIC = new Set([
  'registry', 'patient', 'family', 'familie', 'natural', 'history', 'study', 'biobank', 'biorepository', 'foundation', 'program',
  'programme', 'network', 'consortium', 'center', 'centre', 'platform', 'data', 'database', 'research', 'model', 'mouse', 'mice',
  'cell', 'line', 'alliance', 'association', 'society', 'organization', 'organisation', 'group', 'project', 'collaboration',
  'initiative', 'trial', 'clinical', 'outcome', 'measure', 'assay', 'grant', 'fund', 'funding', 'rare', 'disease', 'disorder',
  'syndrome', 'online', 'community', 'support', 'advocacy', 'parent', 'care', 'children', 'child', 'genetic', 'gene', 'therapy',
]);
const fold = (t) => (t.length > 4 && t.endsWith('ies') ? `${t.slice(0, -3)}y` : t.length > 3 && t.endsWith('s') && !t.endsWith('ss') ? t.slice(0, -1) : t);
export const GENERIC_HOSTS = new Set([
  'facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'wixsite.com', 'wordpress.com',
  'blogspot.com', 'google.com', 'sites.google.com', 'github.io', 'medium.com', 'clinicaltrials.gov', 'ncbi.nlm.nih.gov',
  'pubmed.ncbi.nlm.nih.gov', 'orpha.net', 'globalgenes.org', 'rarediseases.org',
]);

export function nameTokens(name) {
  return keyOf(name).split(' ').filter((t) => t && !NAME_STOP.has(t) && !(t.length === 1 && /[a-z]/.test(t))).map(fold);
}
export const nameKey = (name) => nameTokens(name).join(' ');
/** At least one word that is not generic (and, when `geneTokens` is given, not a gene symbol either). */
export const isDistinctive = (tokens, geneTokens = null) => tokens.some((t) => !GENERIC.has(t) && !geneTokens?.has(t));
const isAcronym = (s) => /^[A-Za-z0-9][A-Za-z0-9.+-]{1,15}$/.test(s) && (s.match(/[A-Z]/g)?.length ?? 0) >= 2;

/**
 * Comparable name keys for a node: the label and synonyms, plus derived names: the label without
 * parentheses, the parts of "A / B", "A – B" and "A: B" labels, and acronyms in parentheses ("(MDA)").
 * Keys need one distinctive word. A derived name made only of gene symbols and generic words
 * ("STXBP1 patient registry" from "STXBP1 patient registry (University Hospital Heidelberg)") is
 * not added: the part that was cut off is what identified the resource.
 */
export function nameVariants(label, synonyms = [], geneTokens = null) {
  const out = new Set();
  const addName = (s, derived) => {
    const tokens = nameTokens(s);
    if (tokens.length && isDistinctive(tokens, derived ? geneTokens : null)) out.add(tokens.join(' '));
  };
  for (const s of [label, ...synonyms]) {
    if (!s) continue;
    addName(s, false);
    const bare = s.replace(/\s*\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
    if (bare !== s) addName(bare, true);
    for (const part of bare.split(/\s+[/–—-]\s+|:\s+/)) {
      if (part !== bare && (nameTokens(part).length >= 2 || isAcronym(part.trim()))) addName(part, true);
    }
    for (const m of s.matchAll(/\(([^)]+)\)/g)) if (isAcronym(m[1].trim())) addName(m[1], true);
  }
  return out;
}

const NODE_TYPES = new Set(['patient_org', 'asset', 'study']);

/**
 * Existing patient_org / asset / study nodes, ready for duplicate checks. Nodes created by an earlier
 * contribution of `excludeContributedUrl` are left out: committing that URL again replaces them.
 */
export function buildNodeIndex(graph, { excludeContributedUrl = null } = {}) {
  const exclude = excludeContributedUrl ? urlKey(excludeContributedUrl) : null;
  const geneTokens = new Set((graph?.nodes ?? []).filter((n) => n.type === 'gene').flatMap((n) => nameTokens(n.label)));
  const excluded = new Set();
  const entries = [];
  for (const n of graph?.nodes ?? []) {
    if (exclude && n.attrs?.contributed?.url && urlKey(n.attrs.contributed.url) === exclude) {
      excluded.add(n.id);
      continue;
    }
    if (!NODE_TYPES.has(n.type)) continue;
    const ncts = new Set();
    if (n.type === 'study' && /^study:NCT\d{8}$/i.test(n.id)) ncts.add(n.id.slice(6).toUpperCase());
    for (const v of [n.xrefs?.NCT].flat()) if (v) ncts.add(String(v).toUpperCase());
    entries.push({
      id: n.id,
      type: n.type,
      node: n,
      names: nameVariants(n.label ?? '', n.synonyms ?? [], geneTokens),
      url: n.attrs?.url ? urlKey(n.attrs.url) : null,
      host: n.attrs?.url ? hostOf(n.attrs.url) : null,
      ncts,
    });
  }
  const byId = new Map((graph?.nodes ?? []).filter((n) => !excluded.has(n.id)).map((n) => [n.id, n]));
  return { entries, byId, excluded, geneTokens };
}

function jaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter += 1;
  return inter / (a.size + b.size - inter);
}

const bestJaccard = (tokens, entry) => Math.max(0, ...[...entry.names].map((k) => jaccard(tokens, new Set(k.split(' ')))));

function duplicateOf(entry, match, pageUrl) {
  const page = urlKey(pageUrl);
  const citesPage = entry.url === page || (entry.node.sources ?? []).some((s) => urlKey(s.ref || s.url || '') === page);
  return { id: entry.id, label: entry.node.label, type: entry.type, match, already_cites_url: citesPage };
}

/**
 * Is this item something the atlas already has? Checked in order:
 *   nct           the NCT number of a study node, or of an asset's xrefs
 *   name          same name after normalisation (label, synonyms, label parts, acronyms)
 *   url           the page is the node's own page (attrs.url) and the item fits it
 *   similar_name  80%+ word overlap with a distinctive name
 * Returns { id, label, type, match, already_cites_url } or null.
 */
export function findDuplicate({ type, name, assetKind = null, nct = null }, { nodeIndex, pageUrl, sameTypeOnPage = 1 }) {
  const entries = nodeIndex.entries;
  if (nct) {
    const hit = entries.find((e) => e.type === type && e.ncts.has(nct))
      ?? entries.find((e) => e.type === 'study' && e.ncts.has(nct))
      ?? entries.find((e) => e.ncts.has(nct));
    if (hit) return duplicateOf(hit, 'nct', pageUrl);
  }
  const tokens = nameTokens(name);
  const key = tokens.join(' ');
  if (key && isDistinctive(tokens)) {
    const hit = entries.find((e) => e.type === type && e.names.has(key));
    if (hit) return duplicateOf(hit, 'name', pageUrl);
  }
  const tokenSet = new Set(tokens);
  const page = urlKey(pageUrl);
  for (const e of entries) {
    if (e.type !== type || e.url !== page) continue;
    const kindFits = type !== 'asset' || (assetKind && e.node.attrs?.kind === assetKind);
    if ((sameTypeOnPage === 1 && kindFits) || bestJaccard(tokenSet, e) >= 0.5) return duplicateOf(e, 'url', pageUrl);
  }
  if (tokenSet.size >= 2 && isDistinctive(tokens)) {
    let best = null;
    for (const e of entries) {
      if (e.type !== type) continue;
      const score = bestJaccard(tokenSet, e);
      if (score >= 0.8 && (!best || score > best.score)) best = { e, score };
    }
    if (best) return duplicateOf(best.e, 'similar_name', pageUrl);
  }
  return null;
}
