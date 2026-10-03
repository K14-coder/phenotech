/**
 * Sign in with ChatGPT (SIWC): the open-source / local-app "ChatGPT plan usage" flow.
 * Dependency-free Node ESM (Node >= 20: global fetch, node:crypto JWK import).
 *
 * Implements, as documented on 2026-10-03:
 *   https://developers.openai.com/siwc/token-sharing-open-source/sign-in
 *   https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
 *   https://developers.openai.com/siwc/token-sharing-open-source/token-reference
 *   https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
 * Written from the docs; no code copied from OpenAI's devkit (it has a noncommercial licence).
 *
 * Public API (none of these ever return or log a token, except getAccessToken):
 *   beginLogin(opts)       start a loopback listener, return { authorizeUrl, redirectUri, completion, cancel }
 *   login(opts)            beginLogin + open the system browser + wait for completion
 *   getAccessToken()       access token for the active account, refreshed automatically near expiry
 *   refresh()              force a refresh_token grant now
 *   logout(opts)           revoke the refresh token remotely, then clear local tokens
 *   status()               read-only summary; never writes files, never makes network calls
 *   previewAuthorizeUrl()  dry run: the URL login() would open; no listener, no files written
 */

import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import {
  createHash,
  createPublicKey,
  randomBytes,
  randomUUID,
  timingSafeEqual,
  verify as verifySignature,
} from 'node:crypto';
import { chmod, mkdir, open, readFile, rename, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';

// ---------------------------------------------------------------------------
// Constants (values from the SIWC docs)
// ---------------------------------------------------------------------------

export const ISSUER = 'https://auth.openai.com';
export const RESOURCE = 'https://api.openai.com/v1';
export const PLAN_USAGE_SCOPE = 'chatgpt.tokens.use.direct';
export const SCOPES = `openid profile email offline_access resource.invoke ${PLAN_USAGE_SCOPE}`;
export const DYNAMIC_CLIENT_ID = 'dynamic_agent_client';
/** Path is fixed for the life of a registration ("/callback does not match /auth/callback"); only the port may vary. */
export const CALLBACK_PATH = '/auth/callback';
export const DEFAULT_CALLBACK_PORT = 1455;
export const MANAGE_USAGE_URL = 'https://chatgpt.com/settings/usage';
/**
 * Sent as agent_name_hint on first registration only. The docs ask for the app's actual name, used
 * consistently across installations. The user can edit it on the consent screen.
 */
export const APP_NAME = 'Rare Disease Atlas';

const DOCUMENTED_ENDPOINTS = Object.freeze({
  authorization_endpoint: `${ISSUER}/api/accounts/authorize`,
  token_endpoint: `${ISSUER}/api/accounts/oauth/token`,
  revocation_endpoint: `${ISSUER}/api/accounts/oauth/revoke`,
  jwks_uri: `${ISSUER}/.well-known/jwks.json`,
});

const REFRESH_MARGIN_MS = 60_000;
const LOGIN_TIMEOUT_MS = 10 * 60_000;
const CLOCK_SKEW_S = 30;
const TERMINAL_REFRESH_ERRORS = new Set([
  'invalid_grant',
  'invalid_refresh_token',
  'token_expired',
  'refresh_token_expired',
  'refresh_token_invalidated',
  'refresh_token_reused',
]);
const CLI = 'node integrations/openai/cli.mjs';

// ---------------------------------------------------------------------------
// Paths: <project root>/.secrets/openai-siwc.json (dir 700, file 600)
// ---------------------------------------------------------------------------

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = path.resolve(process.env.SIWC_PROJECT_ROOT || path.join(HERE, '..', '..'));
export const SECRETS_DIR = path.join(PROJECT_ROOT, '.secrets');
export const STORE_PATH = path.join(SECRETS_DIR, 'openai-siwc.json');
const LOCK_PATH = `${STORE_PATH}.lock`;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class SiwcError extends Error {
  constructor(code, message, { status, retryable = false, requestId, cause } = {}) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = 'SiwcError';
    this.code = code;
    this.retryable = retryable;
    if (status !== undefined) this.status = status;
    if (requestId) this.requestId = requestId;
  }
}

/** No usable ChatGPT session: never signed in, signed out, or the refresh token is no longer valid. */
export class LoginRequiredError extends SiwcError {
  constructor(message = `Not signed in with ChatGPT. Run: ${CLI} login`, options) {
    super('login_required', message, options);
    this.name = 'LoginRequiredError';
  }
}

/** Signed in, but the user did not grant chatgpt.tokens.use.direct. Do not attempt inference with it. */
export class PlanUsageNotGrantedError extends SiwcError {
  constructor(message = `ChatGPT plan usage was not granted. Run: ${CLI} login --reconsent`, options) {
    super('plan_usage_not_granted', message, options);
    this.name = 'PlanUsageNotGrantedError';
  }
}

/** The user cancelled or declined in the browser (error=access_denied). */
export class ConsentDeclinedError extends SiwcError {
  constructor(message = 'Sign-in was cancelled or declined in the browser (access_denied). Nothing was granted.', options) {
    super('access_denied', message, options);
    this.name = 'ConsentDeclinedError';
  }
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const randomValue = (bytes = 32) => randomBytes(bytes).toString('base64url');
const nowIso = () => new Date().toISOString();
const safeCode = (value) =>
  typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,100}$/.test(value) ? value : undefined;

function safeEqual(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  return left.length === right.length && timingSafeEqual(left, right);
}

export function parseScopes(value) {
  if (Array.isArray(value)) return value.filter((scope) => typeof scope === 'string' && scope);
  return typeof value === 'string' ? value.split(/\s+/).filter(Boolean) : [];
}

/** PKCE (RFC 7636): 32 random bytes -> 43-char verifier; S256 challenge, base64url without padding. */
export function pkcePair() {
  const verifier = randomValue(32);
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  return { verifier, challenge };
}

async function fetchWithTimeout(url, init = {}, timeoutMs = 30_000) {
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  try {
    return await fetch(url, { ...init, signal, redirect: 'error' });
  } catch (error) {
    const reason = error?.cause?.code ?? error?.name ?? 'network error';
    throw new SiwcError('network_error', `Could not reach ${new URL(url).host} (${reason}).`, {
      retryable: true,
      cause: error,
    });
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// OIDC discovery (verified against the documented production values)
// ---------------------------------------------------------------------------

let endpointsPromise;

/** Endpoints from https://auth.openai.com/.well-known/openid-configuration, falling back to documented values. */
export function endpoints() {
  endpointsPromise ??= (async () => {
    const result = { ...DOCUMENTED_ENDPOINTS };
    try {
      const response = await fetchWithTimeout(`${ISSUER}/.well-known/openid-configuration`, {
        headers: { accept: 'application/json' },
      }, 15_000);
      const doc = await readJson(response);
      if (!response.ok || !isObject(doc) || doc.issuer !== ISSUER) return result;
      for (const key of Object.keys(DOCUMENTED_ENDPOINTS)) {
        // Only accept endpoints on the issuer's own origin.
        if (typeof doc[key] === 'string' && new URL(doc[key]).origin === ISSUER) result[key] = doc[key];
      }
    } catch {
      // Network trouble: the documented production endpoints are used.
    }
    return result;
  })();
  return endpointsPromise;
}

// ---------------------------------------------------------------------------
// Credential store (single JSON file, atomic writes, owner-only permissions)
//
// {
//   "version": 1,
//   "ext_agent_host_id": "urn:uuid:...",          stable per install; not a credential
//   "active_client_id": "oaiapp_...",
//   "accounts": { "<issued client_id>": <record> } record = documented fields + expires_at
// }
// ---------------------------------------------------------------------------

function emptyStore(hostId) {
  return { version: 1, ext_agent_host_id: hostId, active_client_id: null, accounts: {} };
}

async function readStore() {
  let raw;
  try {
    raw = await readFile(STORE_PATH, 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw new SiwcError('store_unreadable', `Could not read ${STORE_PATH} (${error.code}).`);
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new SiwcError('store_corrupt', `${STORE_PATH} is not valid JSON. Delete it and sign in again.`);
  }
  if (!isObject(data) || typeof data.ext_agent_host_id !== 'string') {
    throw new SiwcError('store_corrupt', `${STORE_PATH} has an unexpected format. Delete it and sign in again.`);
  }
  if (!isObject(data.accounts)) data.accounts = {};
  return data;
}

async function ensureSecretsDir() {
  await mkdir(SECRETS_DIR, { recursive: true, mode: 0o700 });
  await chmod(SECRETS_DIR, 0o700); // mkdir's mode is ignored for an existing dir and masked by umask
}

async function writeStore(data) {
  await ensureSecretsDir();
  const temporary = `${STORE_PATH}.${process.pid}.${randomValue(6)}.tmp`;
  const handle = await open(temporary, 'wx', 0o600);
  try {
    await handle.writeFile(`${JSON.stringify(data, null, 2)}\n`, 'utf8');
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    await chmod(temporary, 0o600);
    await rename(temporary, STORE_PATH);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
}

// Refresh tokens rotate, so refreshes must be serialized within this process and across processes
// (for example the CLI and the Next.js dev server). In-process queue + O_EXCL lock file.
let localQueue = Promise.resolve();

function withStoreLock(fn) {
  const run = localQueue.then(() => withFileLock(fn));
  localQueue = run.catch(() => {});
  return run;
}

async function withFileLock(fn, { waitMs = 20_000, staleMs = 90_000 } = {}) {
  await ensureSecretsDir();
  const started = Date.now();
  for (;;) {
    try {
      const handle = await open(LOCK_PATH, 'wx', 0o600);
      await handle.writeFile(`${process.pid}\n`);
      await handle.close();
      break;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const info = await stat(LOCK_PATH).catch(() => null);
      if (info && Date.now() - info.mtimeMs > staleMs) {
        await rm(LOCK_PATH, { force: true });
        continue;
      }
      if (Date.now() - started > waitMs) {
        throw new SiwcError('store_busy', 'Another process is updating the ChatGPT credentials. Try again shortly.', {
          retryable: true,
        });
      }
      await sleep(50 + Math.floor(Math.random() * 100));
    }
  }
  try {
    return await fn();
  } finally {
    await rm(LOCK_PATH, { force: true });
  }
}

async function ensureHostId() {
  const existing = await readStore();
  if (existing?.ext_agent_host_id) return existing.ext_agent_host_id;
  return withStoreLock(async () => {
    const current = await readStore();
    if (current?.ext_agent_host_id) return current.ext_agent_host_id;
    // Docs: choose and persist the host ID before the first sign-in. UUIDv4 as a urn:uuid: URI.
    const store = emptyStore(`urn:uuid:${randomUUID()}`);
    await writeStore(store);
    return store.ext_agent_host_id;
  });
}

function activeAccount(store) {
  if (!store?.active_client_id) return null;
  const account = store.accounts?.[store.active_client_id];
  return isObject(account) ? account : null;
}

const hasPlanUsage = (account) => parseScopes(account?.scopes).includes(PLAN_USAGE_SCOPE);

function expiresAtMs(account) {
  const time = Date.parse(account?.expires_at ?? '');
  return Number.isFinite(time) ? time : 0;
}

/** earliest_refresh_at's type is undocumented: accept Unix seconds, Unix ms or an ISO string. */
function earliestRefreshMs(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value > 1e12 ? value : value * 1000;
  if (typeof value === 'string' && value.trim()) {
    const number = Number(value);
    if (Number.isFinite(number)) return earliestRefreshMs(number);
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : 0;
  }
  return 0;
}

/** Drop tokens but keep the registration (client_id, subject, email) and host ID for a later sign-in. */
function withoutTokens(account, status) {
  const {
    access_token: _access,
    refresh_token: _refresh,
    id_token: _id,
    token_type: _type,
    expires_in: _expiresIn,
    expires_at: _expiresAt,
    earliest_refresh_at: _earliest,
    ...rest
  } = account;
  return { ...rest, scopes: [], status, saved_at: nowIso() };
}

// ---------------------------------------------------------------------------
// Token endpoint + ID token verification (RS256 against OpenAI's JWKS, no dependencies)
// ---------------------------------------------------------------------------

function oauthErrorCode(body) {
  if (!isObject(body)) return undefined;
  if (typeof body.error === 'string') return safeCode(body.error);
  if (isObject(body.error)) return safeCode(body.error.code) ?? safeCode(body.error.type);
  return safeCode(body.code);
}

async function tokenRequest(params) {
  const { token_endpoint: tokenEndpoint } = await endpoints();
  const response = await fetchWithTimeout(tokenEndpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
    body: new URLSearchParams(params),
  });
  const requestId = response.headers.get('x-request-id') ?? response.headers.get('openai-request-id') ?? undefined;
  const data = await readJson(response);
  if (!response.ok) {
    const code = oauthErrorCode(data) ?? `http_${response.status}`;
    throw new SiwcError(code, `The OpenAI token endpoint returned HTTP ${response.status} (${code}).`, {
      status: response.status,
      retryable: response.status >= 500,
      requestId,
    });
  }
  if (!isObject(data)) {
    throw new SiwcError('invalid_token_response', 'The OpenAI token endpoint returned an unexpected body.', { requestId });
  }
  return data;
}

function credentialFields(data, { requireRefresh }) {
  const invalid = (what) => new SiwcError('invalid_token_response', `The token response ${what}. Sign in again.`);
  if (typeof data.access_token !== 'string' || !data.access_token) throw invalid('did not include an access token');
  if (typeof data.token_type !== 'string' || data.token_type.toLowerCase() !== 'bearer') throw invalid('had an unexpected token_type');
  const expiresIn = Number(data.expires_in);
  if (!Number.isFinite(expiresIn) || expiresIn <= 0) throw invalid('had no valid expires_in');
  const hasRefresh = typeof data.refresh_token === 'string' && data.refresh_token.length > 0;
  if (requireRefresh && !hasRefresh) throw invalid('did not include a refresh token although offline_access was granted');
  const receivedAt = Date.now();
  return {
    access_token: data.access_token,
    ...(hasRefresh ? { refresh_token: data.refresh_token } : {}),
    token_type: 'Bearer',
    expires_in: expiresIn,
    expires_at: new Date(receivedAt + expiresIn * 1000).toISOString(),
    ...(data.earliest_refresh_at !== undefined && data.earliest_refresh_at !== null
      ? { earliest_refresh_at: data.earliest_refresh_at }
      : {}),
    saved_at: new Date(receivedAt).toISOString(),
  };
}

let jwksCache = { uri: '', keys: [], fetchedAt: 0 };

async function signingKeys({ force = false } = {}) {
  const { jwks_uri: jwksUri } = await endpoints();
  const fresh = Date.now() - jwksCache.fetchedAt < 60 * 60_000;
  if (!force && jwksCache.uri === jwksUri && jwksCache.keys.length && fresh) return jwksCache.keys;
  let response;
  try {
    response = await fetchWithTimeout(jwksUri, { headers: { accept: 'application/json' } }, 15_000);
  } catch (error) {
    throw new SiwcError('jwks_unavailable', 'Could not download OpenAI signing keys to verify the ID token.', {
      retryable: true,
      cause: error,
    });
  }
  const body = await readJson(response);
  if (!response.ok || !isObject(body) || !Array.isArray(body.keys)) {
    throw new SiwcError('jwks_unavailable', 'OpenAI signing keys were unavailable. Try again shortly.', { retryable: true });
  }
  jwksCache = { uri: jwksUri, keys: body.keys.filter(isObject), fetchedAt: Date.now() };
  return jwksCache.keys;
}

const decodeSegment = (segment) => JSON.parse(Buffer.from(segment, 'base64url').toString('utf8'));

/** Verify signature (RS256 via JWKS), iss, aud/azp, exp, iat and (when given) nonce. Returns the claims. */
export async function verifyIdToken(idToken, { clientId, nonce } = {}) {
  const invalid = (why) => new SiwcError('invalid_id_token', `The ChatGPT ID token failed verification (${why}).`);
  if (typeof idToken !== 'string' || !idToken) throw invalid('missing');
  const parts = idToken.split('.');
  if (parts.length !== 3) throw invalid('format');
  let header;
  let payload;
  try {
    header = decodeSegment(parts[0]);
    payload = decodeSegment(parts[1]);
  } catch {
    throw invalid('encoding');
  }
  if (!isObject(header) || !isObject(payload) || header.alg !== 'RS256') throw invalid('algorithm');

  const pick = (keys) =>
    keys.find(
      (key) =>
        key.kid === header.kid && key.kty === 'RSA' && (!key.use || key.use === 'sig') && (!key.alg || key.alg === 'RS256'),
    );
  let jwk = pick(await signingKeys());
  if (!jwk) jwk = pick(await signingKeys({ force: true })); // unfamiliar kid: refresh keys once
  if (!jwk) throw invalid('unknown signing key');

  let signatureOk = false;
  try {
    const key = createPublicKey({ key: { kty: 'RSA', n: jwk.n, e: jwk.e }, format: 'jwk' });
    signatureOk = verifySignature(
      'RSA-SHA256',
      Buffer.from(`${parts[0]}.${parts[1]}`),
      key,
      Buffer.from(parts[2], 'base64url'),
    );
  } catch {
    signatureOk = false;
  }
  if (!signatureOk) throw invalid('signature');

  const now = Math.floor(Date.now() / 1000);
  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (payload.iss !== ISSUER) throw invalid('issuer');
  if (!clientId || !audiences.includes(clientId)) throw invalid('audience');
  if (payload.azp !== undefined && payload.azp !== clientId) throw invalid('authorized party');
  if (audiences.length > 1 && payload.azp !== clientId) throw invalid('authorized party');
  if (typeof payload.exp !== 'number' || payload.exp + CLOCK_SKEW_S < now) throw invalid('expired');
  if (typeof payload.iat !== 'number' || payload.iat - CLOCK_SKEW_S > now) throw invalid('issued in the future');
  if (nonce !== undefined && payload.nonce !== nonce) throw invalid('nonce');
  if (typeof payload.sub !== 'string' || !payload.sub) throw invalid('subject');
  return payload;
}

// ---------------------------------------------------------------------------
// Authorization URL + loopback callback listener
// ---------------------------------------------------------------------------

/** Build the authorize URL exactly as the sign-in guide's parameter table describes. */
export function buildAuthorizeUrl({
  authorizationEndpoint = DOCUMENTED_ENDPOINTS.authorization_endpoint,
  clientId = DYNAMIC_CLIENT_ID,
  redirectUri,
  state,
  nonce,
  codeChallenge,
  hostId,
  agentNameHint = APP_NAME,
  loginHint,
  reconsent = false,
}) {
  if (!redirectUri || !state || !nonce || !codeChallenge || !hostId) {
    throw new TypeError('buildAuthorizeUrl: redirectUri, state, nonce, codeChallenge and hostId are required.');
  }
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    scope: SCOPES,
    resource: RESOURCE,
    state,
    nonce,
    code_challenge_method: 'S256',
    code_challenge: codeChallenge,
    ext_agent_host_id: hostId,
  });
  // agent_name_hint only on initial dynamic registration; omit it when reauthorizing an issued client.
  if (clientId === DYNAMIC_CLIENT_ID) params.set('agent_name_hint', agentNameHint);
  // login_hint (saved email) only for reauthorization. id_token_hint is deliberately not sent: it is
  // optional, and the URL is passed to `open` as a process argument, which other local users can read.
  if (loginHint && clientId !== DYNAMIC_CLIENT_ID) params.set('login_hint', loginHint);
  // Re-request consent after an earlier decline (docs: prompt=consent until force_reconsent is confirmed).
  if (reconsent) params.set('prompt', 'consent');
  const url = new URL(authorizationEndpoint);
  url.search = params.toString();
  return url.toString();
}

const PAGE_SCRIPT = 'history.replaceState(null, "", "/auth/complete");';
const PAGE_SCRIPT_HASH = createHash('sha256').update(PAGE_SCRIPT).digest('base64');

function sendPage(response, status, title, body) {
  // title/body are constants from this file; no request data is reflected into the page.
  response.writeHead(status, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
    'referrer-policy': 'no-referrer',
    'content-security-policy': `default-src 'none'; script-src 'sha256-${PAGE_SCRIPT_HASH}'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`,
  });
  response.end(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title>` +
      '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:15vh auto;padding:0 20px;color:#1f2328}h1{font-size:22px}</style></head>' +
      `<body><h1>${title}</h1><p>${body}</p><script>${PAGE_SCRIPT}</script></body></html>`,
  );
}

async function startCallbackListener({ port, allowPortFallback, state, savedClientId }) {
  let settled = false;
  let settle;
  const result = new Promise((resolve, reject) => {
    settle = (error, value) => (error ? reject(error) : resolve(value));
  });
  result.catch(() => {});
  const finish = (error, value) => {
    if (settled) return;
    settled = true;
    settle(error, value);
  };
  let boundPort = port;

  const server = createServer((request, response) => {
    let url;
    try {
      url = new URL(request.url ?? '/', `http://127.0.0.1:${boundPort}`);
    } catch {
      response.writeHead(400).end();
      return;
    }
    // Exact loopback host (blocks DNS rebinding) and exact callback path.
    if (request.method !== 'GET' || request.headers.host !== `127.0.0.1:${boundPort}` || url.pathname !== CALLBACK_PATH) {
      response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' }).end('Not found');
      return;
    }
    if (settled) {
      sendPage(response, 410, 'Sign-in already handled', 'This sign-in attempt has finished. You can close this tab.');
      return;
    }
    const states = url.searchParams.getAll('state');
    if (states.length !== 1 || !safeEqual(states[0], state)) {
      // A stale or unrelated request must not consume the pending attempt.
      sendPage(response, 400, 'Sign-in could not be verified', 'This page does not belong to the current sign-in attempt. Return to the tab that started sign-in.');
      return;
    }
    const error = url.searchParams.get('error');
    if (error) {
      if (error === 'access_denied') {
        sendPage(response, 200, 'Sign-in cancelled', 'No access was granted. You can close this tab.');
        finish(new ConsentDeclinedError());
      } else {
        const code = safeCode(error) ?? 'authorization_error';
        sendPage(response, 400, 'Sign-in failed', 'ChatGPT returned an error. Return to the app for details.');
        finish(new SiwcError(code, `Authorization failed (${code}).`));
      }
      return;
    }
    const codes = url.searchParams.getAll('code');
    const returnedIds = url.searchParams.getAll('client_id');
    const returnedClientId = returnedIds[0] ?? null;
    const clientId = returnedClientId ?? savedClientId ?? null;
    const mismatch = Boolean(savedClientId && returnedClientId && returnedClientId !== savedClientId);
    if (
      codes.length !== 1 ||
      !codes[0] ||
      returnedIds.length > 1 ||
      !clientId ||
      clientId === DYNAMIC_CLIENT_ID ||
      !/^[A-Za-z0-9_-]{1,200}$/.test(clientId) ||
      mismatch
    ) {
      sendPage(response, 400, 'Sign-in incomplete', 'ChatGPT did not complete app registration. Return to the app and try again.');
      finish(
        new SiwcError(
          'registration_incomplete',
          mismatch
            ? 'The callback returned a different client ID than the saved registration, so the result was rejected.'
            : 'ChatGPT did not return an authorization code and an issued client ID. Try signing in again.',
        ),
      );
      return;
    }
    sendPage(response, 200, 'Signed in with ChatGPT', 'You can close this tab and return to the app.');
    finish(null, { code: codes[0], clientId, isNewRegistration: !savedClientId });
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;

  const listen = (candidate) =>
    new Promise((resolve, reject) => {
      const onError = (error) => {
        server.off('listening', onListening);
        reject(error);
      };
      const onListening = () => {
        server.off('error', onError);
        resolve();
      };
      server.once('error', onError);
      server.once('listening', onListening);
      server.listen({ port: candidate, host: '127.0.0.1', exclusive: true });
    });

  try {
    await listen(port);
  } catch (error) {
    if (!(allowPortFallback && error.code === 'EADDRINUSE')) {
      throw new SiwcError('callback_port_unavailable', `Port ${port} on 127.0.0.1 is unavailable (${error.code}). Pass --port or set SIWC_PORT.`);
    }
    await listen(0); // any free port; the docs allow the port (only) to vary between attempts
  }
  boundPort = server.address().port;
  server.on('error', () => finish(new SiwcError('callback_failed', 'The local sign-in listener stopped. Try again.')));

  return {
    redirectUri: `http://127.0.0.1:${boundPort}${CALLBACK_PATH}`,
    result,
    fail: (error) => finish(error),
    close: () => {
      server.close();
      server.closeAllConnections?.();
    },
  };
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

let pendingLogin = null;

/**
 * Start a sign-in attempt without opening a browser (a web UI can open authorizeUrl itself).
 * Returns { authorizeUrl, redirectUri, completion: Promise<LoginResult>, cancel() }.
 * Only one attempt runs per process; a second call returns the pending one.
 *
 * Options: newAccount (register another ChatGPT account instead of reauthorizing the saved one),
 *          reconsent (prompt=consent, to enable plan usage after an earlier decline), port, timeoutMs.
 */
export function beginLogin(options = {}) {
  if (pendingLogin) return pendingLogin;
  pendingLogin = startLogin(options);
  pendingLogin.catch(() => {
    pendingLogin = null;
  });
  return pendingLogin;
}

async function startLogin({ newAccount = false, reconsent = false, port, timeoutMs = LOGIN_TIMEOUT_MS } = {}) {
  const hostId = await ensureHostId();
  const previous = newAccount ? null : activeAccount(await readStore());
  const savedClientId =
    previous?.client_id && previous.client_id !== DYNAMIC_CLIENT_ID ? previous.client_id : undefined;
  const { authorization_endpoint: authorizationEndpoint } = await endpoints();

  // Fresh state, nonce and PKCE verifier for every attempt.
  const state = randomValue();
  const nonce = randomValue();
  const { verifier, challenge } = pkcePair();

  const envPort = process.env.SIWC_PORT !== undefined && process.env.SIWC_PORT !== '' ? Number(process.env.SIWC_PORT) : undefined;
  const explicitPort = port ?? envPort;
  if (explicitPort !== undefined && (!Number.isInteger(explicitPort) || explicitPort < 0 || explicitPort > 65535)) {
    throw new TypeError(`Invalid callback port: ${explicitPort}`);
  }
  const listener = await startCallbackListener({
    port: explicitPort ?? DEFAULT_CALLBACK_PORT,
    allowPortFallback: explicitPort === undefined,
    state,
    savedClientId,
  });

  let authorizeUrl;
  try {
    authorizeUrl = buildAuthorizeUrl({
      authorizationEndpoint,
      clientId: savedClientId ?? DYNAMIC_CLIENT_ID,
      redirectUri: listener.redirectUri,
      state,
      nonce,
      codeChallenge: challenge,
      hostId,
      loginHint: savedClientId ? previous?.email : undefined,
      reconsent,
    });
  } catch (error) {
    listener.close();
    throw error;
  }

  const timer = setTimeout(
    () => listener.fail(new SiwcError('login_timeout', 'Timed out waiting for the browser sign-in to finish.')),
    timeoutMs,
  );

  const completion = (async () => {
    try {
      const callback = await listener.result;

      // Save the issued client ID before the one-time code exchange, so a failed exchange is retried
      // with the same registration instead of registering a new client. It only becomes the active
      // account now if there is no other signed-in account (a new attempt stays separate until verified).
      if (callback.isNewRegistration) {
        await withStoreLock(async () => {
          const store = (await readStore()) ?? emptyStore(hostId);
          const existing = store.accounts[callback.clientId];
          store.accounts[callback.clientId] = {
            ...(isObject(existing) ? existing : { status: 'registered', scopes: [] }),
            client_id: callback.clientId,
            issuer: ISSUER,
            ext_agent_host_id: store.ext_agent_host_id,
            saved_at: nowIso(),
          };
          const active = activeAccount(store);
          if (!active || (!active.access_token && !active.refresh_token)) store.active_client_id = callback.clientId;
          await writeStore(store);
        });
      }

      const tokens = await tokenRequest({
        grant_type: 'authorization_code',
        client_id: callback.clientId,
        code: callback.code,
        code_verifier: verifier,
        redirect_uri: listener.redirectUri,
        resource: RESOURCE,
      });

      if (typeof tokens.id_token !== 'string' || !tokens.id_token) {
        throw new SiwcError('invalid_id_token', 'The token response did not include an ID token.');
      }
      const claims = await verifyIdToken(tokens.id_token, { clientId: callback.clientId, nonce });
      const prior = (await readStore())?.accounts?.[callback.clientId];
      if (isObject(prior) && prior.subject && prior.subject !== claims.sub) {
        throw new SiwcError(
          'account_mismatch',
          `This sign-in returned a different ChatGPT account than the saved one. Use \`${CLI} login --new-account\` to add another account.`,
        );
      }
      // Docs: decide on plan usage from the token response's granted scopes, not the callback.
      if (typeof tokens.scope !== 'string') {
        throw new SiwcError('invalid_token_response', 'The token response did not confirm the granted scopes. Sign in again.');
      }
      const scopes = parseScopes(tokens.scope);
      const hasAccess = typeof tokens.access_token === 'string' && tokens.access_token.length > 0;
      const fields = hasAccess ? credentialFields(tokens, { requireRefresh: scopes.includes('offline_access') }) : {};
      const planUsage = hasAccess && scopes.includes(PLAN_USAGE_SCOPE);
      const firstPlanUsageSignIn = planUsage && !prior?.plan_usage_first_enabled_at;

      const record = {
        email: typeof claims.email === 'string' ? claims.email : (prior?.email ?? null),
        ...(typeof claims.name === 'string' ? { name: claims.name } : {}),
        issuer: ISSUER,
        subject: claims.sub,
        client_id: callback.clientId,
        ext_agent_host_id: hostId,
        id_token: tokens.id_token,
        ...fields,
        scopes,
        status: 'connected',
        plan_usage_first_enabled_at: prior?.plan_usage_first_enabled_at ?? (planUsage ? nowIso() : undefined),
        saved_at: nowIso(),
      };

      await withStoreLock(async () => {
        const store = (await readStore()) ?? emptyStore(hostId);
        store.accounts[callback.clientId] = record;
        store.active_client_id = callback.clientId;
        await writeStore(store);
      });

      return {
        email: record.email,
        name: record.name ?? null,
        clientId: record.client_id,
        newRegistration: callback.isNewRegistration,
        scopes,
        planUsage,
        firstPlanUsageSignIn,
        accessTokenExpiresAt: record.expires_at ?? null,
        manageUsageUrl: MANAGE_USAGE_URL,
      };
    } finally {
      clearTimeout(timer);
      listener.close();
      pendingLogin = null;
    }
  })();
  completion.catch(() => {});

  return {
    authorizeUrl,
    redirectUri: listener.redirectUri,
    completion,
    cancel: () => listener.fail(new SiwcError('cancelled', 'Sign-in was cancelled.')),
  };
}

/** Open a URL in the system browser (macOS `open`; xdg-open / rundll32 elsewhere). */
export function openInBrowser(url) {
  const command = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'rundll32' : 'xdg-open';
  const args = process.platform === 'win32' ? ['url.dll,FileProtocolHandler', url] : [url];
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'ignore', shell: false });
    child.once('error', (error) => reject(new SiwcError('browser_unavailable', `Could not run ${command}: ${error.code ?? error.message}`)));
    child.once('exit', (code) =>
      code === 0 ? resolve() : reject(new SiwcError('browser_unavailable', `${command} exited with code ${code}.`)),
    );
  });
}

/**
 * Full interactive login: listener + browser + wait. Resolves with a LoginResult (no tokens).
 * onAuthorizeUrl(url) is called before the browser opens (print it as a fallback);
 * pass openBrowser: false to only print/return the URL.
 */
export async function login({ openBrowser = true, onAuthorizeUrl, onBrowserError, ...options } = {}) {
  const attempt = await beginLogin(options);
  onAuthorizeUrl?.(attempt.authorizeUrl, attempt.redirectUri);
  if (openBrowser) {
    try {
      await openInBrowser(attempt.authorizeUrl);
    } catch (error) {
      if (onBrowserError) onBrowserError(error, attempt.authorizeUrl);
      else {
        attempt.cancel();
        throw error;
      }
    }
  }
  return attempt.completion;
}

// ---------------------------------------------------------------------------
// Tokens: refresh + access
// ---------------------------------------------------------------------------

async function refreshAccount(store, account) {
  let data;
  try {
    data = await tokenRequest({
      grant_type: 'refresh_token',
      client_id: account.client_id, // the issued client ID, never dynamic_agent_client
      refresh_token: account.refresh_token,
      resource: RESOURCE, // scope omitted to retain the grant
    });
  } catch (error) {
    if (error instanceof SiwcError && TERMINAL_REFRESH_ERRORS.has(error.code)) {
      store.accounts[account.client_id] = withoutTokens(account, 'reauth_required');
      await writeStore(store);
      throw new LoginRequiredError(
        `Your ChatGPT session can no longer be renewed (${error.code}). Sign in again: ${CLI} login`,
        { cause: error, status: error.status },
      );
    }
    if (error instanceof SiwcError && error.code === 'invalid_client') {
      throw new SiwcError('invalid_client', `OpenAI rejected the saved client registration (invalid_client). Run: ${CLI} login --new-account`, {
        cause: error,
        status: error.status,
      });
    }
    throw error; // temporary failure: keep credentials (docs: never erase them on a transient error)
  }

  const scopes = typeof data.scope === 'string' ? parseScopes(data.scope) : parseScopes(account.scopes);
  const fields = credentialFields(data, { requireRefresh: false });
  let identity = {};
  if (typeof data.id_token === 'string' && data.id_token) {
    try {
      const claims = await verifyIdToken(data.id_token, { clientId: account.client_id });
      if (account.subject && claims.sub !== account.subject) {
        throw new SiwcError('account_mismatch', 'The refreshed ChatGPT identity does not match the saved account.');
      }
      identity = { id_token: data.id_token, ...(typeof claims.email === 'string' ? { email: claims.email } : {}) };
    } catch (error) {
      if (!(error instanceof SiwcError && error.code === 'jwks_unavailable')) {
        store.accounts[account.client_id] = withoutTokens(account, 'reauth_required');
        await writeStore(store);
        throw new LoginRequiredError(`The refreshed ChatGPT identity could not be verified (${error.code ?? 'error'}). Sign in again: ${CLI} login`, {
          cause: error,
        });
      }
      // Signing keys temporarily unreachable. The old refresh token is already consumed, so keep the
      // new credentials (they came straight from the token endpoint) and keep the previous ID token.
    }
  }

  const { earliest_refresh_at: _previousEarliest, ...base } = account;
  // Replace access token, expiry, scopes and the rotated refresh token together.
  const updated = {
    ...base,
    ...identity,
    ...fields,
    refresh_token: fields.refresh_token ?? account.refresh_token,
    scopes,
    status: 'connected',
  };
  store.accounts[account.client_id] = updated;
  await writeStore(store);
  return updated;
}

const isConnected = (account) =>
  Boolean(account && account.status === 'connected' && (account.access_token || account.refresh_token || account.id_token));

function assertUsable(account) {
  if (!isConnected(account)) {
    throw new LoginRequiredError(
      account?.status === 'reauth_required'
        ? `Your ChatGPT session expired or was revoked. Sign in again: ${CLI} login`
        : undefined,
    );
  }
  if (!hasPlanUsage(account) || (!account.access_token && !account.refresh_token)) {
    throw new PlanUsageNotGrantedError(
      `Signed in${account.email ? ` as ${account.email}` : ''}, but ChatGPT plan usage (${PLAN_USAGE_SCOPE}) was not granted. To enable it: ${CLI} login --reconsent`,
    );
  }
}

/**
 * Access token for the active account with plan usage granted, refreshed when it is within
 * minValidityMs of expiry. Throws LoginRequiredError / PlanUsageNotGrantedError when unusable.
 * Never log or return this token to a browser.
 */
export async function getAccessToken({ minValidityMs = REFRESH_MARGIN_MS } = {}) {
  const account = activeAccount(await readStore());
  assertUsable(account);
  if (account.access_token && expiresAtMs(account) - Date.now() > minValidityMs) return account.access_token;

  return withStoreLock(async () => {
    const store = await readStore();
    const current = activeAccount(store);
    assertUsable(current);
    const remaining = expiresAtMs(current) - Date.now();
    if (current.access_token && remaining > minValidityMs) return current.access_token; // refreshed meanwhile
    const earliest = earliestRefreshMs(current.earliest_refresh_at);
    if (current.access_token && remaining > 0 && earliest > Date.now()) return current.access_token;
    if (!current.refresh_token) {
      store.accounts[current.client_id] = withoutTokens(current, 'reauth_required');
      await writeStore(store);
      throw new LoginRequiredError(`Your ChatGPT session expired. Sign in again: ${CLI} login`);
    }
    const updated = await refreshAccount(store, current);
    assertUsable(updated);
    return updated.access_token;
  });
}

/** Force a refresh_token grant for the active account. Resolves with a summary (no tokens). */
export async function refresh() {
  if (!activeAccount(await readStore())?.refresh_token) throw new LoginRequiredError();
  return withStoreLock(async () => {
    const store = await readStore();
    const account = activeAccount(store);
    if (!account?.refresh_token) throw new LoginRequiredError();
    const updated = await refreshAccount(store, account);
    return {
      email: updated.email ?? null,
      scopes: parseScopes(updated.scopes),
      planUsage: hasPlanUsage(updated),
      accessTokenExpiresAt: updated.expires_at ?? null,
    };
  });
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

async function revokeRefreshToken(account) {
  const { revocation_endpoint: revocationEndpoint } = await endpoints();
  let problem = 'unknown error';
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (attempt) await sleep(400 * attempt);
    try {
      const response = await fetchWithTimeout(revocationEndpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          token: account.refresh_token,
          token_type_hint: 'refresh_token',
          client_id: account.client_id,
        }),
      }, 10_000);
      await response.body?.cancel().catch(() => {});
      if (response.status === 200) return { revoked: true }; // empty 200, also for already-invalid tokens
      problem = `HTTP ${response.status}`;
      if (response.status < 500) break; // only network errors and 5xx are retried
    } catch (error) {
      problem = error.code ?? 'network error';
    }
  }
  return { revoked: false, problem };
}

/**
 * Sign out of the active account: revoke the renewable session, then clear access/refresh/ID tokens.
 * The registration (issued client_id) and this host's ext_agent_host_id are kept for a later sign-in.
 */
export async function logout({ revoke = true } = {}) {
  const hasTokens = (account) => Boolean(account && (account.access_token || account.refresh_token || account.id_token));
  const notSignedIn = { signedOut: false, revoked: false, message: 'Not signed in.' };
  if (!hasTokens(activeAccount(await readStore()))) return notSignedIn;
  return withStoreLock(async () => {
    const store = await readStore();
    const account = activeAccount(store);
    if (!hasTokens(account)) return notSignedIn;
    let outcome = { revoked: false, problem: revoke ? 'no refresh token to revoke' : 'revocation skipped' };
    if (revoke && account.refresh_token) outcome = await revokeRefreshToken(account);
    store.accounts[account.client_id] = withoutTokens(account, 'signed_out');
    await writeStore(store);
    return {
      signedOut: true,
      revoked: outcome.revoked,
      ...(outcome.revoked ? {} : { revokeProblem: outcome.problem }),
      message: outcome.revoked
        ? 'Signed out and revoked the ChatGPT session.'
        : 'Local tokens were removed, but remote revocation was not confirmed. You can disconnect the app in ChatGPT Settings.',
    };
  });
}

// ---------------------------------------------------------------------------
// Status + dry run (read-only)
// ---------------------------------------------------------------------------

/** Read-only summary of the saved session. Never returns tokens, never writes, never uses the network. */
export async function status() {
  const store = await readStore();
  const account = activeAccount(store);
  const signedIn = isConnected(account);
  let storeFileMode = null;
  try {
    storeFileMode = ((await stat(STORE_PATH)).mode & 0o777).toString(8);
  } catch {
    // no file yet
  }
  return {
    storePath: STORE_PATH,
    storeFileMode,
    hostId: store?.ext_agent_host_id ?? null,
    signedIn,
    planUsage: signedIn && hasPlanUsage(account),
    accountStatus: account?.status ?? null,
    email: account?.email ?? null,
    name: account?.name ?? null,
    clientId: account?.client_id ?? null,
    scopes: parseScopes(account?.scopes),
    accessTokenExpiresAt: account?.expires_at ?? null,
    accessTokenValid: signedIn && expiresAtMs(account) > Date.now(),
    canRefresh: Boolean(account?.refresh_token),
    savedAt: account?.saved_at ?? null,
    /** UI: show the one-time "You're using your ChatGPT plan" confirmation once per value of this. */
    planUsageFirstEnabledAt: account?.plan_usage_first_enabled_at ?? null,
    otherSavedAccounts: Object.keys(store?.accounts ?? {}).filter((id) => id !== store?.active_client_id).length,
    manageUsageUrl: MANAGE_USAGE_URL,
  };
}

/**
 * Dry run: the authorize URL login() would open. Starts no listener and writes nothing; state, nonce
 * and the PKCE pair are throwaway, and the host ID is ephemeral unless one is already saved.
 */
export async function previewAuthorizeUrl({ newAccount = false, reconsent = false, port } = {}) {
  let store = null;
  try {
    store = await readStore();
  } catch {
    store = null;
  }
  const previous = newAccount ? null : activeAccount(store);
  const savedClientId = previous?.client_id && previous.client_id !== DYNAMIC_CLIENT_ID ? previous.client_id : undefined;
  const { authorization_endpoint: authorizationEndpoint } = await endpoints();
  const envPort = process.env.SIWC_PORT ? Number(process.env.SIWC_PORT) : undefined;
  const chosenPort = port ?? envPort ?? DEFAULT_CALLBACK_PORT;
  const hostId = store?.ext_agent_host_id ?? `urn:uuid:${randomUUID()}`;
  const url = buildAuthorizeUrl({
    authorizationEndpoint,
    clientId: savedClientId ?? DYNAMIC_CLIENT_ID,
    redirectUri: `http://127.0.0.1:${chosenPort}${CALLBACK_PATH}`,
    state: randomValue(),
    nonce: randomValue(),
    codeChallenge: pkcePair().challenge,
    hostId,
    loginHint: savedClientId ? previous?.email : undefined,
    reconsent,
  });
  return { url, hostIdPersisted: Boolean(store?.ext_agent_host_id), reauthorization: Boolean(savedClientId) };
}
