/**
 * complete(): one OpenAI Responses API call using whichever credential is available, in this order:
 *   1. Sign in with ChatGPT: the user's ChatGPT Plus/Pro plan (signed in, plan-usage scope granted)
 *   2. process.env.OPENAI_API_KEY: standard API billing
 *   3. neither: throws NoLLMAvailableError
 * Set OPENAI_AUTH=chatgpt|api_key|auto (default auto) to force a path.
 *
 * Both paths call POST https://api.openai.com/v1/responses with store:false and stream:true, as
 * ChatGPT plan usage requires (https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).
 * Dependency-free Node ESM.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import {
  LoginRequiredError,
  MANAGE_USAGE_URL,
  PROJECT_ROOT,
  PlanUsageNotGrantedError,
  getAccessToken,
  status as siwcStatus,
} from './siwc.mjs';

// Settings such as OPENAI_API_KEY and OPENAI_MODEL can live in <project root>/.env.local (gitignored).
// Variables already set in the environment win.
loadEnvFile(path.join(PROJECT_ROOT, '.env.local'));

function loadEnvFile(file) {
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch {
    return;
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const eq = line.indexOf('=');
    if (!line || line.startsWith('#') || eq < 1) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
    if (value && process.env[key] === undefined) process.env[key] = value;
  }
}

export const API_BASE = 'https://api.openai.com/v1';
/** Model used in the SIWC inference docs; also an API model. Override with OPENAI_MODEL or complete({ model }). */
export const DEFAULT_MODEL = 'gpt-6.1-sol';
export const AUTH_CHATGPT = 'chatgpt';
export const AUTH_API_KEY = 'api_key';

const DEFAULT_TIMEOUT_MS = 5 * 60_000;
const MAX_ATTEMPTS = 3;
const CLI = 'node integrations/openai/cli.mjs';

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** Neither a usable ChatGPT sign-in nor OPENAI_API_KEY. `reasons` says why for each path. */
export class NoLLMAvailableError extends Error {
  constructor(reasons = []) {
    super(`No OpenAI credentials available. ${reasons.join(' ')}`.trim());
    this.name = 'NoLLMAvailableError';
    this.code = 'no_llm_available';
    this.reasons = reasons;
  }
}

/**
 * The API rejected or failed the request. `kind` is a stable category for UI decisions:
 * usage_limit | not_eligible | temporarily_unavailable | unsupported_capability | unsupported_route |
 * auth | not_authorized | client_not_enabled | policy_or_region | model_not_found | rate_limited |
 * quota | invalid_request | server_error | network | stream_interrupted | request_failed
 */
export class LLMRequestError extends Error {
  constructor({ kind, code, status, param, requestId, authPath, retryable = false, hint, serverMessage, phase, retryAfterMs }) {
    const parts = [hint ?? 'The OpenAI request failed.'];
    if (code) parts.push(`[${code}]`);
    if (status) parts.push(`(HTTP ${status})`);
    if (param) parts.push(`param=${param}`);
    super(parts.join(' '));
    this.name = 'LLMRequestError';
    Object.assign(this, { kind, code: code ?? null, status: status ?? null, param: param ?? null, requestId: requestId ?? null });
    Object.assign(this, { authPath, retryable, phase });
    if (serverMessage) this.serverMessage = serverMessage;
    if (retryAfterMs !== undefined) this.retryAfterMs = retryAfterMs;
    if (kind === 'usage_limit') this.manageUsageUrl = MANAGE_USAGE_URL;
  }
}

/** The request completed but the output is unusable: refusal | incomplete | invalid_json | schema_mismatch. */
export class LLMOutputError extends Error {
  constructor(code, message, extra = {}) {
    super(message);
    this.name = 'LLMOutputError';
    this.code = code;
    Object.assign(this, extra);
  }
}

// [kind, retryable, hint]. Codes and recovery advice from
// https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
const KNOWN_CODES = {
  subscription_sharing_user_not_eligible: ['not_eligible', false, 'ChatGPT plan usage is not available for this account, workspace or policy (needs an eligible Plus or Pro plan). Use an OpenAI API key instead.'],
  subscription_sharing_usage_limit_exceeded: ['usage_limit', false, `The ChatGPT plan or this app's usage limit was reached. Review usage and limits at ${MANAGE_USAGE_URL}`],
  subscription_sharing_usage_unavailable: ['temporarily_unavailable', true, 'ChatGPT usage could not be checked right now. Try again shortly.'],
  subscription_sharing_user_unavailable: ['temporarily_unavailable', true, 'ChatGPT account information is temporarily unavailable. Try again shortly.'],
  subscription_sharing_unsupported_capability: ['unsupported_capability', false, 'ChatGPT plan usage does not support a parameter, tool or model in this request (see param).'],
  subscription_sharing_route_not_supported: ['unsupported_route', false, 'Only POST /v1/responses is supported with ChatGPT plan usage.'],
  subscription_sharing_invalid_user: ['auth', false, `ChatGPT could not validate the subscriber context. If this persists, sign in again (${CLI} login).`],
  chatpass_v2_scope_not_authorized: ['not_authorized', false, 'The granted ChatGPT permissions do not authorize this request. Check the client and grant.'],
  chatpass_v2_invalid_authorization_context: ['not_authorized', false, 'The ChatGPT authorization context does not permit this request. Check the client and grant.'],
  subscription_sharing_v2_client_not_enabled: ['client_not_enabled', false, 'This app registration is not enabled for ChatGPT plan usage.'],
  model_not_found: ['model_not_found', false, `This model is not available for these credentials. Set OPENAI_MODEL or list models with: ${CLI} models`],
  insufficient_quota: ['quota', false, 'The OpenAI API key has no remaining quota or billing.'],
  credit_balance_exhausted: ['quota', false, 'The OpenAI API account has no credits left. Add credits at https://platform.openai.com/settings/organization/billing/ or use Sign in with ChatGPT.'],
  invalid_api_key: ['auth', false, 'OPENAI_API_KEY was rejected.'],
  rate_limit_exceeded: ['rate_limited', true, 'Rate limited by the OpenAI API.'],
};
// Older spellings seen in the reference SDK; keep the server's exact code on the error.
const LEGACY_CODES = {
  subscription_sharing_v2_user_not_eligible: 'subscription_sharing_user_not_eligible',
  subscription_sharing_v2_route_not_supported: 'subscription_sharing_route_not_supported',
  subscription_sharing_v2_invalid_user: 'subscription_sharing_invalid_user',
  subscription_sharing_v2_user_unavailable: 'subscription_sharing_user_unavailable',
};

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const shortText = (value, max = 300) =>
  typeof value === 'string' && value ? (value.length > max ? `${value.slice(0, max)}...` : value) : undefined;

function errorFromBody(body, { status, requestId, authPath, phase, retryAfterMs }) {
  let detail = isObject(body) ? body : {};
  for (let depth = 0; depth < 4; depth += 1) {
    if (isObject(detail.response) && isObject(detail.response.error)) detail = detail.response.error;
    else if (isObject(detail.error)) detail = detail.error;
    else if (isObject(detail.detail)) detail = detail.detail;
    else break;
  }
  const rawCode =
    typeof detail.code === 'string' ? detail.code : typeof detail.error === 'string' ? detail.error : undefined;
  const code = rawCode && /^[A-Za-z0-9_.:-]{1,100}$/.test(rawCode) ? rawCode : undefined;
  // Direct-admission failures can be {"detail": "..."}: diagnostic text, not a machine-readable code.
  const serverMessage = shortText(detail.message) ?? shortText(isObject(body) ? body.detail : undefined) ?? shortText(detail.detail);
  const param = typeof detail.param === 'string' ? detail.param : undefined;
  let [kind, retryable, hint] = KNOWN_CODES[LEGACY_CODES[code] ?? code] ?? [];
  if (!kind) {
    const plan = authPath === AUTH_CHATGPT;
    if (status === 401) [kind, retryable, hint] = ['auth', false, plan ? 'The ChatGPT credential or plan permission was not accepted. Check the signed-in account and granted scopes, or sign in again.' : 'OPENAI_API_KEY was rejected.'];
    else if (status === 403) [kind, retryable, hint] = ['policy_or_region', false, 'A policy or permission check, such as the permitted serving region, prevented this request.'];
    else if (status === 429) [kind, retryable, hint] = plan ? ['rate_limited', false, `Too many requests. Wait before retrying; usage limits: ${MANAGE_USAGE_URL}`] : ['rate_limited', true, 'Rate limited by the OpenAI API.'];
    else if (status === 503) [kind, retryable, hint] = ['temporarily_unavailable', true, plan ? 'ChatGPT plan routing is unavailable or not enabled right now. Try again later.' : 'The OpenAI API is temporarily unavailable.'];
    else if (status >= 500) [kind, retryable, hint] = ['server_error', true, 'OpenAI returned a server error. Try again shortly.'];
    else if (status === 400 || status === 404 || status === 422) [kind, retryable, hint] = ['invalid_request', false, 'OpenAI rejected the request. Check the model, input and parameters.'];
    else [kind, retryable, hint] = ['request_failed', false, 'The OpenAI request failed.'];
  }
  return new LLMRequestError({ kind, code, status, param, requestId, authPath, retryable, hint, serverMessage, phase, retryAfterMs });
}

/** UI helper: { kind, message, action?: { label, url } } for any error thrown by complete(). */
export function describeError(error) {
  if (error instanceof NoLLMAvailableError) {
    return { kind: 'no_llm_available', message: error.message, action: { label: 'Continue with ChatGPT', command: `${CLI} login` } };
  }
  if (error instanceof LLMRequestError) {
    const action = error.kind === 'usage_limit' || error.kind === 'rate_limited' ? { label: 'Manage usage', url: MANAGE_USAGE_URL } : undefined;
    return { kind: error.kind, message: error.message, ...(action ? { action } : {}), retryable: error.retryable };
  }
  if (error instanceof LLMOutputError) return { kind: error.code, message: error.message };
  if (error instanceof LoginRequiredError || error instanceof PlanUsageNotGrantedError) {
    return { kind: error.code, message: error.message, action: { label: 'Continue with ChatGPT', command: `${CLI} login` } };
  }
  return { kind: 'error', message: error?.message ?? String(error) };
}

// ---------------------------------------------------------------------------
// Auth selection
// ---------------------------------------------------------------------------

function authMode(value) {
  const mode = String(value ?? process.env.OPENAI_AUTH ?? 'auto').toLowerCase();
  if (!['auto', AUTH_CHATGPT, AUTH_API_KEY].includes(mode)) throw new TypeError(`OPENAI_AUTH must be auto, chatgpt or api_key (got ${mode}).`);
  return mode;
}

/** Internal: returns { path, token }. Never expose the token to a browser or a log. */
async function resolveAuth(preference) {
  const mode = authMode(preference);
  const reasons = [];
  if (mode !== AUTH_API_KEY) {
    try {
      return { path: AUTH_CHATGPT, token: await getAccessToken() };
    } catch (error) {
      const notUsable = error instanceof LoginRequiredError || error instanceof PlanUsageNotGrantedError;
      // A temporary sign-in problem is surfaced instead of silently switching to another billing path.
      if (!notUsable) throw error;
      if (mode === AUTH_CHATGPT) throw new NoLLMAvailableError([`ChatGPT: ${error.message}`, '(OPENAI_AUTH=chatgpt)']);
      reasons.push(`ChatGPT: ${error.message}`);
    }
  }
  if (mode !== AUTH_CHATGPT) {
    const key = process.env.OPENAI_API_KEY?.trim();
    if (key) return { path: AUTH_API_KEY, token: key, note: reasons.join(' ') || undefined };
    reasons.push('API key: OPENAI_API_KEY is not set.');
  }
  throw new NoLLMAvailableError(reasons);
}

/**
 * What complete() would use right now, without network calls or token refreshes. Safe to send to a
 * browser: contains no tokens.
 */
export async function describeAuth() {
  const mode = authMode();
  let chatgpt;
  try {
    chatgpt = await siwcStatus();
  } catch (error) {
    chatgpt = { signedIn: false, planUsage: false, error: error.message };
  }
  const apiKeyConfigured = Boolean(process.env.OPENAI_API_KEY?.trim());
  let path = null;
  if (mode !== AUTH_API_KEY && chatgpt.signedIn && chatgpt.planUsage) path = AUTH_CHATGPT;
  else if (mode !== AUTH_CHATGPT && apiKeyConfigured) path = AUTH_API_KEY;
  return {
    path,
    mode,
    apiKeyConfigured,
    model: process.env.OPENAI_MODEL || DEFAULT_MODEL,
    chatgpt: {
      signedIn: chatgpt.signedIn,
      planUsage: chatgpt.planUsage,
      email: chatgpt.email ?? null,
      accountStatus: chatgpt.accountStatus ?? null,
      accessTokenExpiresAt: chatgpt.accessTokenExpiresAt ?? null,
      planUsageFirstEnabledAt: chatgpt.planUsageFirstEnabledAt ?? null,
      ...(chatgpt.error ? { error: chatgpt.error } : {}),
    },
    manageUsageUrl: MANAGE_USAGE_URL,
  };
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

let catalogCache = null;

/**
 * Models for the current credentials, in the server's order. On the ChatGPT path this is the
 * account's own catalog ({ models: [{ slug, display_name, visibility }] }, keeping visibility "list").
 */
export async function listModels({ authMode: preference } = {}) {
  return fetchCatalog(await resolveAuth(preference));
}

async function fetchCatalog(auth) {
  if (catalogCache && catalogCache.token === auth.token && Date.now() - catalogCache.at < 10 * 60_000) {
    return catalogCache.models;
  }
  let response;
  try {
    response = await fetch(`${API_BASE}/models`, {
      headers: { authorization: `Bearer ${auth.token}`, accept: 'application/json' },
      signal: AbortSignal.timeout(20_000),
      redirect: 'error',
    });
  } catch (error) {
    throw new LLMRequestError({ kind: 'network', authPath: auth.path, retryable: true, phase: 'admission', hint: `Could not reach api.openai.com (${error?.cause?.code ?? error.name}).` });
  }
  const requestId = response.headers.get('x-request-id') ?? undefined;
  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw errorFromBody(body, { status: response.status, requestId, authPath: auth.path, phase: 'admission' });
  let models = [];
  if (Array.isArray(body?.models)) {
    models = body.models
      .filter((model) => isObject(model) && model.visibility === 'list' && typeof model.slug === 'string' && model.slug)
      .map((model) => ({ slug: model.slug, displayName: typeof model.display_name === 'string' ? model.display_name : model.slug }));
  } else if (Array.isArray(body?.data)) {
    models = body.data
      .filter((model) => isObject(model) && typeof model.id === 'string')
      .map((model) => ({ slug: model.id, displayName: model.id }));
  }
  catalogCache = { token: auth.token, at: Date.now(), models };
  return models;
}

async function chooseModel(auth, requested) {
  if (requested) return requested;
  if (process.env.OPENAI_MODEL) return process.env.OPENAI_MODEL;
  if (auth.path === AUTH_CHATGPT) {
    // Plan usage only works with models available to the signed-in account: keep the default when the
    // account lists it, otherwise take the first listed model (server order). Best effort.
    try {
      const models = await fetchCatalog(auth);
      if (models.length && !models.some((model) => model.slug === DEFAULT_MODEL)) return models[0].slug;
    } catch {
      // fall back to the default
    }
  }
  return DEFAULT_MODEL;
}

// ---------------------------------------------------------------------------
// Responses API streaming
// ---------------------------------------------------------------------------

const STOP = Symbol('stop');

async function readEventStream(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let dataLines = [];
  const dispatch = () => {
    if (!dataLines.length) return undefined;
    const data = dataLines.join('\n');
    dataLines = [];
    if (data === '[DONE]') return undefined;
    let event;
    try {
      event = JSON.parse(data);
    } catch {
      throw new LLMRequestError({ kind: 'stream_interrupted', phase: 'stream', hint: 'The response stream contained an invalid event.' });
    }
    return isObject(event) ? onEvent(event) : undefined;
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const lines = buffer.split('\n');
      buffer = done ? '' : lines.pop();
      for (let line of lines) {
        if (line.endsWith('\r')) line = line.slice(0, -1);
        if (line === '') {
          if (dispatch() === STOP) return;
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).replace(/^ /, ''));
        } // comments (":"), event:, id: and retry: lines are ignored; the type is inside data
      }
      if (done) {
        dispatch();
        return;
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function outputFromResponse(response) {
  let text = '';
  let refusal = '';
  for (const item of Array.isArray(response?.output) ? response.output : []) {
    if (item?.type !== 'message' || !Array.isArray(item.content)) continue;
    for (const part of item.content) {
      if (part?.type === 'output_text' && typeof part.text === 'string') text += part.text;
      if (part?.type === 'refusal' && typeof part.refusal === 'string') refusal += part.refusal;
    }
  }
  return { text, refusal };
}

function parseRetryAfter(response) {
  const value = response.headers.get('retry-after');
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : undefined;
}

async function streamResponse(auth, body, { signal, onDelta, timeoutMs }) {
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response;
  try {
    response = await fetch(`${API_BASE}/responses`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${auth.token}`,
        'content-type': 'application/json',
        accept: 'text/event-stream',
      },
      body: JSON.stringify(body),
      signal: combined,
      redirect: 'error',
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new LLMRequestError({ kind: 'network', authPath: auth.path, retryable: true, phase: 'admission', hint: `Could not reach api.openai.com (${error?.cause?.code ?? error.name}).` });
  }
  const requestId = response.headers.get('x-request-id') ?? undefined;
  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined);
    throw errorFromBody(errorBody, { status: response.status, requestId, authPath: auth.path, phase: 'admission', retryAfterMs: parseRetryAfter(response) });
  }
  const contentType = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase();
  // The plan-usage route may omit Content-Type on a valid stream, so only reject a clearly wrong one.
  if (!response.body || (contentType && contentType !== 'text/event-stream')) {
    await response.body?.cancel().catch(() => {});
    throw new LLMRequestError({ kind: 'stream_interrupted', status: response.status, requestId, authPath: auth.path, phase: 'stream', hint: `Expected an event stream but got ${contentType ?? 'no body'}.` });
  }

  const state = { text: '', refusal: '', completed: null, failed: null, incomplete: null, sawDelta: false };
  try {
    await readEventStream(response.body, (event) => {
      switch (event.type) {
        case 'response.output_text.delta':
          if (typeof event.delta === 'string') {
            state.text += event.delta;
            state.sawDelta = true;
            onDelta?.(event.delta);
          }
          return undefined;
        case 'response.refusal.delta':
          if (typeof event.delta === 'string') state.refusal += event.delta;
          return undefined;
        case 'response.completed':
          state.completed = isObject(event.response) ? event.response : {};
          return STOP;
        case 'response.failed':
        case 'error':
          state.failed = event;
          return STOP;
        case 'response.incomplete':
          state.incomplete = isObject(event.response) ? event.response : {};
          return STOP;
        default:
          return undefined;
      }
    });
  } catch (error) {
    if (error instanceof LLMRequestError) throw Object.assign(error, { authPath: auth.path, requestId });
    if (signal?.aborted) throw error;
    throw new LLMRequestError({ kind: 'stream_interrupted', authPath: auth.path, requestId, retryable: false, phase: 'stream', hint: timeout.aborted ? `The response did not finish within ${Math.round(timeoutMs / 1000)}s.` : 'The connection was interrupted before the response completed.' });
  }

  if (state.failed) {
    const error = errorFromBody(state.failed, { requestId, authPath: auth.path, phase: 'stream' });
    error.emittedOutput = state.sawDelta;
    throw error;
  }
  if (state.incomplete) {
    const reason = state.incomplete.incomplete_details?.reason ?? 'unknown';
    throw new LLMOutputError('incomplete', `The response stopped before completing (${reason}).`, { partialText: state.text, authPath: auth.path });
  }
  // Only response.completed counts as success (docs).
  if (!state.completed) {
    throw new LLMRequestError({ kind: 'stream_interrupted', authPath: auth.path, requestId, phase: 'stream', hint: 'The stream ended without response.completed.' });
  }
  const fromOutput = outputFromResponse(state.completed);
  return {
    text: state.text || fromOutput.text,
    refusal: state.refusal || fromOutput.refusal,
    id: state.completed.id ?? null,
    model: state.completed.model ?? body.model,
    usage: state.completed.usage ?? null,
    requestId: requestId ?? null,
  };
}

async function streamWithRetry(auth, body, options) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await streamResponse(auth, body, options);
    } catch (error) {
      const retryable =
        error instanceof LLMRequestError &&
        error.retryable &&
        (error.phase === 'admission' || (error.kind === 'temporarily_unavailable' && !error.emittedOutput));
      if (!retryable || attempt >= MAX_ATTEMPTS || options.signal?.aborted) throw error;
      const backoff = error.retryAfterMs ?? 1000 * 3 ** (attempt - 1) + Math.random() * 500; // ~1s, ~3s
      await sleep(Math.min(backoff, 15_000));
    }
  }
}

// ---------------------------------------------------------------------------
// complete()
// ---------------------------------------------------------------------------

function normalizeInput(input) {
  if (typeof input === 'string') return [{ role: 'user', content: input }];
  const list = Array.isArray(input) ? input : isObject(input) ? [input] : null;
  if (!list || !list.length) throw new TypeError('complete(): input must be a non-empty string, message or array of messages.');
  return list.map((message) => {
    if (typeof message === 'string') return { role: 'user', content: message };
    if (!isObject(message)) throw new TypeError('complete(): each input item must be a string or an object.');
    // The plan-usage route rejects system message items; developer messages are the documented alternative.
    return message.role === 'system' ? { ...message, role: 'developer' } : message;
  });
}

const schemaFormatName = (name) => String(name || 'result').replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 64) || 'result';

function jsonOnlyInstruction(schema) {
  return [
    'Respond with a single JSON value only: no Markdown, no code fences, no commentary.',
    'It must validate against this JSON Schema:',
    JSON.stringify(schema),
  ].join('\n');
}

function parseJsonText(text) {
  let candidate = String(text ?? '').trim();
  const fenced = candidate.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) candidate = fenced[1];
  try {
    return JSON.parse(candidate);
  } catch {
    const start = candidate.search(/[[{]/);
    const end = Math.max(candidate.lastIndexOf('}'), candidate.lastIndexOf(']'));
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(candidate.slice(start, end + 1));
      } catch {
        // fall through
      }
    }
  }
  throw new LLMOutputError('invalid_json', 'The model did not return valid JSON.', { text: shortText(text, 2000) });
}

const TYPE_CHECKS = {
  null: (value) => value === null,
  array: Array.isArray,
  object: isObject,
  integer: Number.isInteger,
  number: (value) => typeof value === 'number' && Number.isFinite(value),
  string: (value) => typeof value === 'string',
  boolean: (value) => typeof value === 'boolean',
};

/**
 * Small JSON Schema check (type, enum, const, required, properties, additionalProperties:false,
 * items, anyOf). Used only when structured outputs had to fall back to prompting. No $ref support.
 */
export function validateJson(value, schema, at = '$') {
  if (!isObject(schema)) return [];
  if (Array.isArray(schema.anyOf)) {
    return schema.anyOf.some((option) => validateJson(value, option, at).length === 0) ? [] : [`${at}: matches none of anyOf`];
  }
  const problems = [];
  if (schema.const !== undefined && value !== schema.const) problems.push(`${at}: expected ${JSON.stringify(schema.const)}`);
  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) problems.push(`${at}: not one of ${schema.enum.map((v) => JSON.stringify(v)).join(', ')}`);
  const types = schema.type === undefined ? [] : Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.length && !types.some((type) => TYPE_CHECKS[type]?.(value))) return [...problems, `${at}: expected ${types.join(' | ')}`];
  if (isObject(value)) {
    const properties = isObject(schema.properties) ? schema.properties : {};
    for (const key of Array.isArray(schema.required) ? schema.required : []) {
      if (!(key in value)) problems.push(`${at}.${key}: missing`);
    }
    for (const [key, child] of Object.entries(properties)) {
      if (key in value) problems.push(...validateJson(value[key], child, `${at}.${key}`));
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) if (!(key in properties)) problems.push(`${at}.${key}: unexpected property`);
    }
  }
  if (Array.isArray(value) && isObject(schema.items)) {
    value.forEach((item, index) => problems.push(...validateJson(item, schema.items, `${at}[${index}]`)));
  }
  return problems;
}

/**
 * Run one model call.
 *
 * @param {object}   options
 * @param {string}   [options.instructions]   system-level guidance (sent as Responses `instructions`)
 * @param {string|object|object[]} options.input  user text, or Responses input message(s)
 * @param {object}   [options.schema]         JSON Schema for structured output. Strict mode rules apply:
 *                                            every object needs additionalProperties:false and must list
 *                                            all its properties in `required` (use ["string","null"] for optional)
 * @param {string}   [options.schemaName]     name for the schema (default "result")
 * @param {string}   [options.model]          overrides OPENAI_MODEL and the default
 * @param {string}   [options.reasoningEffort] e.g. "low" | "medium" | "high"; omitted unless set
 * @param {string}   [options.authMode]       "auto" | "chatgpt" | "api_key" (default OPENAI_AUTH or auto)
 * @param {AbortSignal} [options.signal]
 * @param {(delta: string) => void} [options.onDelta]  streamed text deltas
 * @param {number}   [options.timeoutMs]      whole-request timeout (default 5 minutes)
 * @returns {Promise<{ text: string, json?: any, model: string, authPath: 'chatgpt'|'api_key',
 *   structuredMode: null|'json_schema'|'prompted', usage: object|null, responseId: string|null,
 *   requestId: string|null, note?: string }>}
 */
export async function complete({
  instructions,
  input,
  schema,
  schemaName = 'result',
  model,
  reasoningEffort,
  authMode: preference,
  signal,
  onDelta,
  timeoutMs = DEFAULT_TIMEOUT_MS,
} = {}) {
  const messages = normalizeInput(input);
  const auth = await resolveAuth(preference);
  const modelId = await chooseModel(auth, model);

  const base = { model: modelId, input: messages, store: false, stream: true };
  if (instructions) base.instructions = instructions;
  if (reasoningEffort) base.reasoning = { effort: reasoningEffort };

  let structuredMode = null;
  let request = base;
  if (schema) {
    structuredMode = 'json_schema';
    request = { ...base, text: { format: { type: 'json_schema', name: schemaFormatName(schemaName), schema, strict: true } } };
  }

  const options = { signal, onDelta, timeoutMs };
  let result;
  try {
    result = await streamWithRetry(auth, request, options);
  } catch (error) {
    // Structured outputs are not listed as supported or unsupported for ChatGPT plan usage. If the
    // route rejects `text`, retry once with the schema in the instructions and validate locally.
    const textRejected =
      schema &&
      error instanceof LLMRequestError &&
      error.code === 'subscription_sharing_unsupported_capability' &&
      (!error.param || /^text/.test(error.param));
    if (!textRejected) throw error;
    structuredMode = 'prompted';
    request = { ...base, instructions: [instructions, jsonOnlyInstruction(schema)].filter(Boolean).join('\n\n') };
    result = await streamWithRetry(auth, request, options);
  }

  if (!result.text && result.refusal) {
    throw new LLMOutputError('refusal', `The model refused: ${shortText(result.refusal)}`, { refusal: result.refusal, authPath: auth.path, model: result.model });
  }

  let json;
  if (schema) {
    json = parseJsonText(result.text);
    if (structuredMode === 'prompted') {
      const problems = validateJson(json, schema);
      if (problems.length) {
        throw new LLMOutputError('schema_mismatch', `The JSON did not match the schema: ${problems.slice(0, 5).join('; ')}`, { json, text: shortText(result.text, 2000) });
      }
    }
  }

  return {
    text: result.text,
    ...(schema ? { json } : {}),
    model: result.model ?? modelId,
    authPath: auth.path,
    structuredMode,
    usage: result.usage,
    responseId: result.id,
    requestId: result.requestId,
    ...(auth.note ? { note: auth.note } : {}),
  };
}
