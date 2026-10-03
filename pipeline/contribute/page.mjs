/**
 * Fetch a contributed web page and turn it into clean text. Dependency-free Node ESM.
 *
 * fetchPage(): a plain fetch first (redirects followed by hand, every hop checked to be a public
 * host). On a network error, an HTTP error or a bot wall, ONE request to Bright Data Web Unlocker
 * (POST https://api.brightdata.com/request with {zone, url, format:"raw"}). The page is cached under
 * data/raw/contributions/<sha>.json with its retrieval date. E-mail addresses are redacted before
 * anything is stored. The Bright Data token comes from the environment or .env.local and is never
 * logged, returned or written anywhere.
 *
 * htmlToText(): small HTML-to-text conversion (drops script/style, decodes entities, collapses
 * whitespace). selectExcerpt(): the most relevant ~12k characters of a long page.
 */
import { createHash } from 'node:crypto';
import { lookup as dnsLookup } from 'node:dns/promises';
import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const DEFAULT_RAW_DIR = path.join(ROOT, 'data', 'raw', 'contributions');
export const BRIGHTDATA_API = 'https://api.brightdata.com/request';
export const MAX_PAGE_BYTES = 5 * 1024 * 1024;
const MAX_REDIRECTS = 5;
const DIRECT_TIMEOUT_MS = 20_000;
const BRIGHTDATA_TIMEOUT_MS = 90_000;
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 rare-disease-atlas/0.1';
const EMAIL_RE = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
const INVISIBLE = /[­​-‍⁠﻿]/g;

// ---------------------------------------------------------------------------
// Errors and small helpers
// ---------------------------------------------------------------------------

/** Every error preview() and commit() throw. `status` is the HTTP status a web route should use. */
export class ContributeError extends Error {
  constructor(code, message, status = 400, details = {}) {
    super(message);
    this.name = 'ContributeError';
    this.code = code;
    this.status = status;
    this.details = details;
  }

  toJSON() {
    return { code: this.code, message: this.message, ...this.details };
  }
}

export const sha256 = (text) => createHash('sha256').update(String(text)).digest('hex');
export const today = (now = new Date()) => (now instanceof Date ? now : new Date(now)).toISOString().slice(0, 10);
export const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));
export const redactEmails = (text) => String(text ?? '').replace(EMAIL_RE, '[email-redacted]');

/** Write via a temp file + rename. The temp file lives in `tmpDir` (default: next to the target). */
export function writeTextAtomic(file, text, tmpDir = path.dirname(file)) {
  mkdirSync(path.dirname(file), { recursive: true });
  mkdirSync(tmpDir, { recursive: true });
  const tmp = path.join(tmpDir, `.${path.basename(file)}.tmp-${process.pid}-${Date.now()}`);
  writeFileSync(tmp, text);
  try {
    renameSync(tmp, file);
  } catch (error) {
    if (error.code !== 'EXDEV') throw error;
    writeFileSync(file, text); // different file systems: plain write
    unlinkSync(tmp);
  }
}

export const writeJsonAtomic = (file, value, tmpDir) => writeTextAtomic(file, `${JSON.stringify(value, null, 1)}\n`, tmpDir);

/** .env.local values (first non-empty wins), overridden by variables already set in the environment. */
export function projectEnv() {
  const env = {};
  let text = '';
  try {
    text = readFileSync(path.join(ROOT, '.env.local'), 'utf8');
  } catch {
    // no .env.local
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const eq = line.indexOf('=');
    if (!line || line.startsWith('#') || eq < 1) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
    if (value && env[key] === undefined) env[key] = value;
  }
  for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value;
  return env;
}

export function brightDataConfig(env) {
  const token = String(env?.BRIGHTDATA_API_TOKEN ?? '').trim();
  if (!token) return null;
  return { token, zone: String(env?.BRIGHTDATA_UNLOCKER_ZONE ?? '').trim() || 'web_unlocker1' };
}

// ---------------------------------------------------------------------------
// URLs
// ---------------------------------------------------------------------------

const TRACKING_PARAM = /^(utm_[a-z]+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|_hsenc|_hsmi|mkt_tok)$/i;

/** The URL we fetch and cite: http(s) only, no credentials, no #fragment, no tracking parameters. */
export function canonicalUrl(input) {
  if (typeof input !== 'string' || !input.trim()) throw new ContributeError('invalid_url', 'Paste the address (URL) of a web page.');
  let raw = input.trim();
  if (raw.length > 2000) throw new ContributeError('invalid_url', 'That address is too long.');
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) raw = `https://${raw}`;
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new ContributeError('invalid_url', 'That is not a valid web address.');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new ContributeError('invalid_url', 'Only http:// and https:// pages can be contributed.');
  if (url.username || url.password) throw new ContributeError('invalid_url', 'The address must not contain a user name or password.');
  if (!url.hostname) throw new ContributeError('invalid_url', 'That is not a valid web address.');
  url.hash = '';
  for (const key of [...url.searchParams.keys()].filter((k) => TRACKING_PARAM.test(k))) url.searchParams.delete(key);
  return url.href;
}

const LOCAL_NAME = /(^|\.)(localhost|local|internal|intranet|lan|home|corp|localdomain|home\.arpa)$/i;

export function isPrivateAddress(ip) {
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split('.').map(Number);
    return a === 0 || a === 10 || a === 127 || (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254)
      || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 198 && (b === 18 || b === 19)) || a >= 224;
  }
  if (net.isIPv6(ip)) {
    const v = ip.toLowerCase();
    const mapped = v.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (mapped) return isPrivateAddress(mapped[1]);
    return v === '::' || v === '::1' || /^f[cd]/.test(v) || /^fe[89ab]/.test(v) || v.startsWith('ff');
  }
  return true;
}

/** Refuse local and private-network targets (the web route takes URLs from a browser). */
export async function assertPublicHost(href, { lookup = dnsLookup } = {}) {
  const host = new URL(href).hostname.replace(/^\[(.*)\]$/, '$1');
  const blocked = () => new ContributeError('blocked_host', `${host} is a local or private address. Only public web pages can be contributed.`);
  if (net.isIP(host)) {
    if (isPrivateAddress(host)) throw blocked();
    return;
  }
  if (!host.includes('.') || LOCAL_NAME.test(host)) throw blocked();
  if (!lookup) return;
  let addresses;
  try {
    addresses = await lookup(host, { all: true });
  } catch (error) {
    const err = new ContributeError('fetch_failed', `Could not find the website ${host} (${error?.code ?? 'DNS lookup failed'}).`, 502);
    err.fallbackOk = true; // Bright Data resolves names on its side
    throw err;
  }
  if (addresses.some((a) => isPrivateAddress(a.address))) throw blocked();
}

// ---------------------------------------------------------------------------
// Fetching
// ---------------------------------------------------------------------------

const tooLarge = () => new ContributeError('too_large', `The page is larger than ${MAX_PAGE_BYTES / 1024 / 1024} MB.`, 413);

function decodeBytes(bytes, contentType) {
  const declared = /charset=["']?([\w-]+)/i.exec(contentType ?? '')?.[1]
    ?? /<meta[^>]+charset=["']?([\w-]+)/i.exec(bytes.subarray(0, 4096).toString('latin1'))?.[1];
  let decoder;
  try {
    decoder = new TextDecoder(declared || 'utf-8');
  } catch {
    decoder = new TextDecoder('utf-8');
  }
  return decoder.decode(bytes);
}

async function readBody(response, maxBytes = MAX_PAGE_BYTES) {
  const declared = Number(response.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > maxBytes) throw tooLarge();
  if (!response.body) return '';
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) {
      await reader.cancel().catch(() => {});
      throw tooLarge();
    }
    chunks.push(value);
  }
  return decodeBytes(Buffer.concat(chunks), response.headers.get('content-type'));
}

function assertTextContent(contentType) {
  const type = String(contentType ?? '').split(';')[0].trim().toLowerCase();
  if (!type || type.startsWith('text/') || type.includes('html') || type.includes('xml')) return;
  if (type === 'application/pdf') {
    throw new ContributeError('unsupported_content', 'This link is a PDF. Paste the address of a web page instead (PDFs are not supported yet).', 415);
  }
  throw new ContributeError('unsupported_content', `This link is not a web page (${type}).`, 415);
}

const BOT_WALL = [
  /<title>\s*Just a moment\.\.\.\s*<\/title>/i,
  /cf-browser-verification|cf_chl_opt|challenge-platform\/h\//i,
  /Attention Required! \| Cloudflare/i,
  /Enable JavaScript and cookies to continue/i,
  /within\.website\/x\/cmd\/anubis|anubis_challenge|Making sure you(?:'|&#39;|’)re not a bot/i,
  /Incapsula incident ID|_Incapsula_Resource|Request unsuccessful\. Incapsula/i,
  /Pardon Our Interruption/i,
  /captcha-delivery\.com|px-captcha/i,
  /Access Denied[\s\S]{0,300}You don't have permission to access/i,
  /Please verify you are a human|Verify you are human/i,
];

/** Why a response is not usable page content (an HTTP error, a bot wall, an empty JS shell), or null. */
export function blockReason({ status, html, bodyText }) {
  if (status >= 400) return `HTTP ${status}`;
  const head = String(html ?? '').slice(0, 30_000);
  if (BOT_WALL.some((re) => re.test(head))) return 'a bot-check page';
  const visible = String(bodyText ?? '').replace(/\s+/g, ' ').trim();
  if (visible.length < 200) return 'almost no text (the page may need JavaScript)';
  if (visible.length < 1500 && /captcha/i.test(head)) return 'a captcha page';
  return null;
}

function networkProblem(error) {
  if (error?.name === 'TimeoutError') return 'timed out';
  return error?.cause?.code ?? error?.code ?? error?.message ?? 'network error';
}

async function directFetch(url, { fetchImpl, lookup }) {
  let current = url;
  for (let hop = 0; ; hop += 1) {
    await assertPublicHost(current, { lookup });
    const response = await fetchImpl(current, {
      method: 'GET',
      redirect: 'manual',
      headers: { 'user-agent': USER_AGENT, accept: 'text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8,*/*;q=0.5', 'accept-language': 'en' },
      signal: AbortSignal.timeout(DIRECT_TIMEOUT_MS),
    });
    const location = response.status >= 300 && response.status < 400 ? response.headers.get('location') : null;
    if (location) {
      await response.body?.cancel().catch(() => {});
      if (hop >= MAX_REDIRECTS) throw new Error('too many redirects');
      current = new URL(location, current).href;
      continue;
    }
    return { status: response.status, finalUrl: current, contentType: response.headers.get('content-type') ?? '', body: await readBody(response) };
  }
}

/** One Web Unlocker request. Error messages never contain the token. */
export async function brightDataFetch(url, { token, zone }, { fetchImpl = globalThis.fetch } = {}) {
  const scrub = (text) => String(text).split(token).join('[redacted]');
  let response;
  try {
    response = await fetchImpl(BRIGHTDATA_API, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', accept: '*/*' },
      body: JSON.stringify({ zone, url, format: 'raw' }),
      signal: AbortSignal.timeout(BRIGHTDATA_TIMEOUT_MS),
      redirect: 'error',
    });
  } catch (error) {
    throw new ContributeError('fetch_failed', scrub(`Bright Data could not be reached (${networkProblem(error)}).`), 502);
  }
  const body = await readBody(response);
  const brdError = response.headers.get('x-brd-error') ?? response.headers.get('x-luminati-error');
  if (!response.ok || brdError) {
    const detail = body.replace(/\s+/g, ' ').trim().slice(0, 200);
    throw new ContributeError('fetch_failed', scrub(`Bright Data returned HTTP ${response.status}${brdError ? ` (${brdError})` : ''}${detail ? `: ${detail}` : ''}`), 502);
  }
  // Web Unlocker reports the target site's own status and the URL it was redirected to
  const targetStatus = Number(response.headers.get('x-brd-status-code')) || null;
  const redirectedTo = response.headers.get('x-unblocker-redirected-to');
  return { status: response.status, targetStatus, redirectedTo, contentType: response.headers.get('content-type') ?? '', body };
}

const NOT_FOUND_TITLE = /^(?:404|not found)\b|\b(?:page not found|404 not found|error 404|page (?:cannot|can't|could not) be found|page (?:does not|doesn't) exist)\b/i;

/** Soft 404s: sites (and Bright Data) often answer 200 with a "Page not found" page. */
function assertFound(status, html) {
  const title = oneLine(decodeEntities(/<title\b[^>]*>([\s\S]*?)<\/title\s*>/i.exec(String(html ?? ''))?.[1] ?? ''));
  if (status === 404 || status === 410 || NOT_FOUND_TITLE.test(title)) {
    throw new ContributeError('not_found', `The page was not found (${status === 404 || status === 410 ? `HTTP ${status}` : `"${title}"`}). Check the address.`, 404);
  }
}

const urlSha = (url) => sha256(url).slice(0, 24);
export const pageCachePath = (url, rawDir = DEFAULT_RAW_DIR) => path.join(rawDir, `${urlSha(url)}.json`);
export const extractionCachePath = (url, rawDir = DEFAULT_RAW_DIR) => path.join(rawDir, `${urlSha(url)}.extraction.json`);

/** The cached page for `url` (the canonical requested URL), or null. */
export function loadCachedPage(url, rawDir = DEFAULT_RAW_DIR) {
  const file = pageCachePath(url, rawDir);
  if (!existsSync(file)) return null;
  try {
    const record = readJson(file);
    if (record?.url !== url || typeof record.html !== 'string') return null;
    if (typeof record.text !== 'string') Object.assign(record, htmlToText(record.html));
    return { ...record, from_cache: true, cache_file: file };
  } catch {
    return null;
  }
}

/**
 * The page at `url` (already canonical) as { url, final_url, via, retrieved, title, text, html, ... }.
 * Options: fetchImpl, lookup (DNS; tests inject one), env, rawDir, refresh, now.
 */
export async function fetchPage(url, options = {}) {
  const { fetchImpl = globalThis.fetch, lookup = dnsLookup, rawDir = DEFAULT_RAW_DIR, refresh = false, now = new Date() } = options;
  if (!refresh) {
    const cached = loadCachedPage(url, rawDir);
    if (cached) return cached;
  }

  let record = null;
  let directProblem = null;
  try {
    const res = await directFetch(url, { fetchImpl, lookup });
    if (res.status === 404 || res.status === 410 || res.status < 400) assertFound(res.status, res.body);
    if (res.status < 400) assertTextContent(res.contentType);
    directProblem = blockReason({ status: res.status, html: res.body, bodyText: htmlToText(res.body).body });
    if (!directProblem) record = { via: 'direct', status: res.status, final_url: canonicalUrl(res.finalUrl), content_type: res.contentType, html: res.body };
  } catch (error) {
    if (error instanceof ContributeError && !error.fallbackOk) throw error;
    directProblem = error instanceof ContributeError ? error.message : networkProblem(error);
  }

  if (!record) {
    const creds = brightDataConfig(options.env ?? projectEnv());
    if (!creds) {
      throw new ContributeError('fetch_failed', `The page could not be read directly (${directProblem}), and the Bright Data fallback is not configured (BRIGHTDATA_API_TOKEN).`, 502);
    }
    const res = await brightDataFetch(url, creds, { fetchImpl });
    if (/application\/pdf/i.test(res.contentType)) assertTextContent(res.contentType);
    assertFound(res.targetStatus, res.body);
    const reason = blockReason({ status: res.targetStatus ?? res.status, html: res.body, bodyText: htmlToText(res.body).body });
    if (reason) {
      throw new ContributeError('fetch_failed', `The page could not be read directly (${directProblem}) or through Bright Data (${reason}).`, 502);
    }
    let finalUrl = url;
    try {
      if (res.redirectedTo) finalUrl = canonicalUrl(new URL(res.redirectedTo, url).href);
    } catch {
      // keep the requested URL
    }
    record = { via: 'brightdata', status: res.targetStatus ?? res.status, final_url: finalUrl, content_type: res.contentType, html: res.body, direct_problem: directProblem };
  }

  const html = redactEmails(record.html);
  const { title, text } = htmlToText(html);
  const stored = {
    url,
    final_url: record.final_url,
    via: record.via,
    ...(record.direct_problem ? { direct_problem: record.direct_problem } : {}),
    status: record.status,
    content_type: record.content_type,
    retrieved: today(now),
    fetched_at: (now instanceof Date ? now : new Date(now)).toISOString(),
    emails_redacted: true,
    html_sha256: sha256(html),
    text_sha256: sha256(text),
    title,
    text,
    html,
  };
  const file = pageCachePath(url, rawDir);
  writeJsonAtomic(file, stored);
  return { ...stored, from_cache: false, cache_file: file };
}

// ---------------------------------------------------------------------------
// HTML -> text
// ---------------------------------------------------------------------------

const NAMED = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", ensp: ' ', emsp: ' ', thinsp: ' ', zwnj: '‌',
  zwj: '‍', lrm: '‎', rlm: '‏', ndash: '–', mdash: '—', lsquo: '‘', rsquo: '’', sbquo: '‚', ldquo: '“',
  rdquo: '”', bdquo: '„', dagger: '†', Dagger: '‡', bull: '•', hellip: '…', permil: '‰', prime: '′', Prime: '″',
  lsaquo: '‹', rsaquo: '›', euro: '€', trade: '™', larr: '←', uarr: '↑', rarr: '→', darr: '↓', harr: '↔', minus: '−',
  le: '≤', ge: '≥', ne: '≠', asymp: '≈', infin: '∞', alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', Delta: 'Δ',
  epsilon: 'ε', kappa: 'κ', lambda: 'λ', mu: 'μ', pi: 'π', sigma: 'σ', tau: 'τ', omega: 'ω', check: '✓',
};
// U+00A0..U+00FF in order
'nbsp iexcl cent pound curren yen brvbar sect uml copy ordf laquo not shy reg macr deg plusmn sup2 sup3 acute micro para middot cedil sup1 ordm raquo frac14 frac12 frac34 iquest Agrave Aacute Acirc Atilde Auml Aring AElig Ccedil Egrave Eacute Ecirc Euml Igrave Iacute Icirc Iuml ETH Ntilde Ograve Oacute Ocirc Otilde Ouml times Oslash Ugrave Uacute Ucirc Uuml Yacute THORN szlig agrave aacute acirc atilde auml aring aelig ccedil egrave eacute ecirc euml igrave iacute icirc iuml eth ntilde ograve oacute ocirc otilde ouml divide oslash ugrave uacute ucirc uuml yacute thorn yuml'
  .split(' ')
  .forEach((name, i) => { NAMED[name] = String.fromCodePoint(0xa0 + i); });
// Numeric references 128-159 mean Windows-1252 characters in practice (as browsers decode them)
const CP1252 = {
  0x80: '€', 0x82: '‚', 0x83: 'ƒ', 0x84: '„', 0x85: '…', 0x86: '†', 0x87: '‡', 0x88: 'ˆ', 0x89: '‰', 0x8a: 'Š', 0x8b: '‹',
  0x8c: 'Œ', 0x8e: 'Ž', 0x91: '‘', 0x92: '’', 0x93: '“', 0x94: '”', 0x95: '•', 0x96: '–', 0x97: '—', 0x98: '˜', 0x99: '™',
  0x9a: 'š', 0x9b: '›', 0x9c: 'œ', 0x9e: 'ž', 0x9f: 'Ÿ',
};

export function decodeEntities(text) {
  return String(text ?? '').replace(/&(?:#[xX]([0-9a-fA-F]{1,6});?|#(\d{1,7});?|([a-zA-Z][a-zA-Z0-9]{1,31});)/g, (whole, hex, dec, name) => {
    if (name) return NAMED[name] ?? whole;
    const code = hex ? parseInt(hex, 16) : parseInt(dec, 10);
    if (CP1252[code]) return CP1252[code];
    if (!code || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return '�';
    return String.fromCodePoint(code);
  });
}

const DROP_ELEMENTS = /<(script|style|noscript|template|svg|math|iframe|object|canvas|select|head)\b[^>]*>[\s\S]*?<\/\1\s*>/gi;
const TAG = /<\/?([a-zA-Z][a-zA-Z0-9:-]*)\b(?:[^>"']|"[^"]*"|'[^']*')*>/g;
const BLOCK_TAGS = new Set(
  'address article aside blockquote br caption dd details dialog div dl dt fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr li main nav ol p pre section summary table tbody td tfoot th thead tr ul'.split(' '),
);
const oneLine = (text) => String(text ?? '').replace(INVISIBLE, '').replace(/\s+/g, ' ').trim();

function metaContent(html, name) {
  for (const match of html.matchAll(/<meta\b(?:[^>"']|"[^"]*"|'[^']*')*>/gi)) {
    const tag = match[0];
    const key = /\b(?:name|property)\s*=\s*["']?([^"'\s>]+)/i.exec(tag)?.[1]?.toLowerCase();
    if (key !== name) continue;
    const content = /\bcontent\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(tag);
    if (content) return oneLine(decodeEntities(content[1] ?? content[2]));
  }
  return '';
}

/**
 * HTML -> { title, description, body, text }. `text` = title, meta description (unless the body
 * repeats it) and the visible body text, one block per line. Script, style, head, comments and
 * similar are dropped; entities are decoded; whitespace is collapsed.
 */
export function htmlToText(html) {
  const source = String(html ?? '');
  const title = oneLine(decodeEntities(/<title\b[^>]*>([\s\S]*?)<\/title\s*>/i.exec(source)?.[1] ?? ''));
  const description = metaContent(source, 'description') || metaContent(source, 'og:description');
  let s = source
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(DROP_ELEMENTS, '\n')
    .replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, ' ')
    .replace(/<![^>]*>|<\?[^>]*>/g, ' ');
  s = s.replace(TAG, (_, name) => (BLOCK_TAGS.has(name.toLowerCase()) ? '\n' : ''));
  s = decodeEntities(s).replace(INVISIBLE, '');
  const body = s
    .split(/\r\n|\r|\n/)
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join('\n');
  const header = [title, description && !body.includes(description) ? description : ''].filter(Boolean);
  return { title, description, body, text: [...header, body].filter(Boolean).join('\n') };
}

// ---------------------------------------------------------------------------
// Relevant excerpt for the model
// ---------------------------------------------------------------------------

const RELEVANT = /registr|natural history|biobank|biorepositor|sample|specimen|tissue|mouse|mice|\brats?\b|zebrafish|animal model|knock-?in|knock-?out|cell lines?|iPSC|stem cell|organoid|fibroblast|outcome measure|endpoint|\bscale|assay|biomarker|platform|database|dataset|data shar|grant|fund|award|enrol|enroll|participat|sign up|join|consent|access|request|apply|eligib|stud(?:y|ies)|trial|clinical|NCT\d{8}|foundation|association|alliance|consortium|network|famil|patient|caregiver|research/gi;

function splitLong(line, target = 800) {
  const pieces = [];
  let current = '';
  for (const sentence of line.split(/(?<=[.!?])\s+/)) {
    for (let start = 0; start < sentence.length; start += 1000) {
      const part = sentence.slice(start, start + 1000);
      if (current && current.length + part.length + 1 > target) {
        pieces.push(current);
        current = part;
      } else current = current ? `${current} ${part}` : part;
    }
  }
  if (current) pieces.push(current);
  return pieces;
}

/**
 * At most `maxChars` of `text` for the model. Short pages go whole. Long pages keep the title lines
 * and the blocks with the most resource keywords (registry, biobank, enrol, NCT...) and, via `score`,
 * atlas disease/gene names; repeated blocks (menus, footers) are dropped; order is preserved.
 */
export function selectExcerpt(text, { maxChars = 12_000, score } = {}) {
  const source = String(text ?? '');
  if (source.length <= maxChars) return { excerpt: source, truncated: false };
  const blocks = [];
  const seen = new Set();
  for (const line of source.split('\n')) {
    for (const piece of line.length > 1200 ? splitLong(line) : [line]) {
      if (seen.has(piece)) continue;
      seen.add(piece);
      blocks.push(piece);
    }
  }
  const base = blocks.map((b) => (b.match(RELEVANT)?.length ?? 0) + (score ? 3 * score(b) : 0));
  const weight = blocks.map((b, i) => (base[i] + 0.5 * ((base[i - 1] ?? 0) + (base[i + 1] ?? 0))) * Math.min(1, b.length / 80) + (i < 2 ? 1000 : 0));
  const order = blocks.map((_, i) => i).sort((a, b) => weight[b] - weight[a] || a - b);
  const chosen = [];
  let used = 0;
  for (const i of order) {
    const cost = blocks[i].length + 1;
    if (used + cost > maxChars) continue;
    chosen.push(i);
    used += cost;
  }
  chosen.sort((a, b) => a - b);
  return { excerpt: chosen.map((i) => blocks[i]).join('\n'), truncated: true };
}
