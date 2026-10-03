#!/usr/bin/env node
/**
 * node integrations/openai/cli.mjs <command> [flags]
 *
 *   login [--new-account] [--reconsent] [--no-open] [--port N]
 *                Sign in with ChatGPT in the browser (loopback callback on 127.0.0.1)
 *   status [--json]
 *                Saved session, granted scopes and which auth path complete() would use (read-only)
 *   test [--quick] [--model M]
 *                Tiny plain prompt + tiny structured-output prompt; prints the auth path used
 *   models       Models available to the current credentials
 *   refresh      Force a token refresh (to check refresh works)
 *   logout [--no-revoke]
 *                Revoke the ChatGPT session and remove local tokens
 *   url [--new-account] [--reconsent] [--port N]
 *                Dry run: print the authorize URL login would open (no listener, no files written)
 */

import {
  APP_NAME,
  ConsentDeclinedError,
  MANAGE_USAGE_URL,
  beginLogin,
  logout,
  openInBrowser,
  previewAuthorizeUrl,
  refresh,
  status as siwcStatus,
} from './siwc.mjs';
import { DEFAULT_MODEL, LLMOutputError, LLMRequestError, NoLLMAvailableError, complete, describeAuth, listModels } from './llm.mjs';

const CLI = 'node integrations/openai/cli.mjs';

function parseFlags(args) {
  const flags = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith('--')) continue;
    const [name, inline] = arg.slice(2).split('=', 2);
    if (inline !== undefined) flags[name] = inline;
    else if (args[index + 1] !== undefined && !args[index + 1].startsWith('--') && ['port', 'model'].includes(name)) flags[name] = args[++index];
    else flags[name] = true;
  }
  return flags;
}

const line = (label, value) => console.log(`  ${label.padEnd(23)}${value}`);

function printError(error) {
  console.error(`\nError: ${error.message}`);
  if (error instanceof LLMRequestError) {
    console.error(`  kind: ${error.kind}${error.code ? `   code: ${error.code}` : ''}${error.status ? `   http: ${error.status}` : ''}${error.requestId ? `   request id: ${error.requestId}` : ''}`);
    if (error.serverMessage) console.error(`  server said: ${error.serverMessage}`);
    if (error.kind === 'usage_limit') console.error(`  Manage usage: ${MANAGE_USAGE_URL}`);
  } else if (error instanceof LLMOutputError && error.text) {
    console.error(`  raw output: ${error.text}`);
  } else if (error?.code && error.code !== 'login_required') {
    console.error(`  code: ${error.code}`);
  }
}

async function cmdLogin(flags) {
  const port = flags.port !== undefined ? Number(flags.port) : undefined;
  const attempt = await beginLogin({ newAccount: Boolean(flags['new-account']), reconsent: Boolean(flags.reconsent), port });
  const cancel = () => {
    attempt.cancel();
  };
  process.once('SIGINT', cancel);

  console.log(`Sign in with ChatGPT (${APP_NAME})`);
  console.log(`  Callback listener: ${attempt.redirectUri}`);
  if (flags['no-open']) {
    console.log(`\nOpen this URL in your browser:\n\n${attempt.authorizeUrl}\n`);
  } else {
    try {
      await openInBrowser(attempt.authorizeUrl);
      console.log('  Opened your browser. Finish signing in there.');
      console.log(`  If nothing opened, paste this URL into your browser:\n\n${attempt.authorizeUrl}\n`);
    } catch (error) {
      console.log(`  Could not open a browser (${error.message}). Open this URL yourself:\n\n${attempt.authorizeUrl}\n`);
    }
  }
  console.log('Waiting for the browser to come back to the callback (Ctrl-C to cancel)...');

  try {
    const result = await attempt.completion;
    console.log(`\nSigned in${result.email ? ` as ${result.email}` : ''}${result.newRegistration ? ' (new app registration)' : ''}.`);
    line('granted scopes:', result.scopes.join(' ') || '(none)');
    if (result.planUsage) {
      line('ChatGPT plan usage:', 'ENABLED (chatgpt.tokens.use.direct granted)');
      if (result.firstPlanUsageSignIn) {
        console.log("\nYou're using your ChatGPT plan.");
        console.log(`  Eligible AI requests in ${APP_NAME} now use your ChatGPT plan. Manage usage: ${MANAGE_USAGE_URL}`);
      }
      console.log(`\nNext: ${CLI} test`);
    } else {
      line('ChatGPT plan usage:', 'NOT GRANTED');
      console.log('\nYou are signed in, but AI requests cannot use your ChatGPT plan. Either:');
      console.log(`  - enable it:   ${CLI} login --reconsent`);
      console.log('  - or set OPENAI_API_KEY to use the standard API instead.');
    }
  } catch (error) {
    if (error instanceof ConsentDeclinedError) {
      console.log(`\n${error.message}`);
      console.log(`Run \`${CLI} login\` again when ready, or set OPENAI_API_KEY to use the standard API.`);
      process.exitCode = 1;
      return;
    }
    throw error;
  } finally {
    process.off('SIGINT', cancel);
  }
}

async function cmdStatus(flags) {
  const [session, auth] = await Promise.all([siwcStatus(), describeAuth()]);
  if (flags.json) {
    console.log(JSON.stringify({ chatgpt: session, completeWouldUse: auth.path, mode: auth.mode, apiKeyConfigured: auth.apiKeyConfigured, model: auth.model }, null, 2));
    return;
  }
  console.log('Sign in with ChatGPT');
  line('signed in:', session.signedIn ? `yes${session.email ? ` (${session.email})` : ''}` : `no${session.accountStatus ? ` (${session.accountStatus})` : ''}`);
  if (session.signedIn) {
    line('plan usage:', session.planUsage ? 'ENABLED (chatgpt.tokens.use.direct granted)' : `NOT GRANTED (run: ${CLI} login --reconsent)`);
    line('granted scopes:', session.scopes.join(' ') || '(none)');
    line('access token:', session.accessTokenExpiresAt ? `${session.accessTokenValid ? 'valid' : 'expired'} until ${session.accessTokenExpiresAt}${session.canRefresh ? ' (auto-refreshes)' : ''}` : 'none');
    line('refresh token:', session.canRefresh ? 'present' : 'missing');
    line('client id:', session.clientId ?? '-');
  }
  line('host id:', session.hostId ?? '(created on first login)');
  line('credentials file:', `${session.storePath}${session.storeFileMode ? ` (mode ${session.storeFileMode})` : ' (not created yet)'}`);
  if (session.storeFileMode && session.storeFileMode !== '600') console.log(`  WARNING: credentials file should be mode 600 (chmod 600 "${session.storePath}")`);
  if (session.otherSavedAccounts) line('other accounts:', String(session.otherSavedAccounts));
  console.log('API key fallback');
  line('OPENAI_API_KEY:', auth.apiKeyConfigured ? 'set' : 'not set');
  console.log('complete() would use');
  line('auth path:', auth.path === 'chatgpt' ? 'chatgpt (your ChatGPT plan)' : auth.path === 'api_key' ? 'api_key (OPENAI_API_KEY)' : `none (NoLLMAvailableError)${auth.mode !== 'auto' ? `, OPENAI_AUTH=${auth.mode}` : ''}`);
  line('model:', `${auth.model}${process.env.OPENAI_MODEL ? ' (OPENAI_MODEL)' : ' (default; on the ChatGPT path, swapped for the first listed model if the account lacks it)'}`);
  line('manage usage:', MANAGE_USAGE_URL);
}

async function cmdTest(flags) {
  const model = typeof flags.model === 'string' ? flags.model : undefined;
  console.log('1) Plain prompt');
  const plain = await complete({
    instructions: 'You are a connectivity check. Follow the instruction exactly.',
    input: 'Reply with exactly: Token sharing works.',
    model,
  });
  line('auth path:', plain.authPath === 'chatgpt' ? 'chatgpt (ChatGPT plan via Sign in with ChatGPT)' : 'api_key (OPENAI_API_KEY)');
  line('model:', plain.model);
  line('response:', JSON.stringify(plain.text));
  if (plain.usage) line('usage:', JSON.stringify(plain.usage));
  if (plain.note) line('note:', plain.note);
  if (!plain.text.trim()) throw new Error('The completed response was empty.');
  if (flags.quick) return;

  console.log('\n2) Structured output (JSON Schema)');
  const schema = {
    type: 'object',
    additionalProperties: false,
    required: ['claims'],
    properties: {
      claims: {
        type: 'array',
        items: {
          type: 'object',
          additionalProperties: false,
          required: ['subject', 'statement', 'year'],
          properties: {
            subject: { type: 'string' },
            statement: { type: 'string' },
            year: { type: ['integer', 'null'] },
          },
        },
      },
    },
  };
  const structured = await complete({
    instructions: 'Extract every factual claim from the text. Use null when no year is stated.',
    input: 'Synthetic test text: The footbridge was painted blue in 2019. It was repainted red in 2023. It is 40 metres long.',
    schema,
    schemaName: 'claims',
    model,
  });
  line('auth path:', structured.authPath);
  line('structured mode:', structured.structuredMode === 'json_schema' ? 'json_schema (native Structured Outputs accepted)' : 'prompted (route rejected text.format; JSON validated locally)');
  console.log(JSON.stringify(structured.json, null, 2).replace(/^/gm, '  '));
}

async function cmdModels() {
  const models = await listModels();
  if (!models.length) {
    console.log('No models listed for these credentials.');
    return;
  }
  for (const model of models) console.log(`  ${model.slug.padEnd(28)}${model.displayName}${model.slug === DEFAULT_MODEL ? '   <- default' : ''}`);
}

async function cmdRefresh() {
  const result = await refresh();
  console.log(`Refreshed. Access token valid until ${result.accessTokenExpiresAt}. Plan usage: ${result.planUsage ? 'enabled' : 'not granted'}.`);
}

async function cmdLogout(flags) {
  const result = await logout({ revoke: !flags['no-revoke'] });
  console.log(result.message);
  if (result.signedOut && !result.revoked && result.revokeProblem) console.log(`  (revocation: ${result.revokeProblem}) Disconnect the app at ${MANAGE_USAGE_URL} if needed.`);
}

async function cmdUrl(flags) {
  const port = flags.port !== undefined ? Number(flags.port) : undefined;
  const preview = await previewAuthorizeUrl({ newAccount: Boolean(flags['new-account']), reconsent: Boolean(flags.reconsent), port });
  console.log('DRY RUN: no listener started, nothing written. state, nonce and PKCE values below are throwaway.');
  if (!preview.hostIdPersisted) console.log('ext_agent_host_id is ephemeral here; login persists a real one before opening the browser.');
  console.log(`\n${preview.url}\n`);
  for (const [key, value] of new URL(preview.url).searchParams) line(`${key}:`, value);
}

function usage() {
  console.log(`Usage: ${CLI} <login|status|test|models|refresh|logout|url> [flags]

  login [--new-account] [--reconsent] [--no-open] [--port N]   Sign in with ChatGPT in the browser
  status [--json]                                              Saved session + which auth path complete() uses
  test [--quick] [--model M]                                   Tiny prompt (+ structured output) and the auth path used
  models                                                       Models available to the current credentials
  refresh                                                      Force a token refresh
  logout [--no-revoke]                                         Revoke the session and delete local tokens
  url [--new-account] [--reconsent] [--port N]                 Dry run: print the authorize URL only

Env: OPENAI_API_KEY (fallback), OPENAI_MODEL (default ${DEFAULT_MODEL}), OPENAI_AUTH=auto|chatgpt|api_key, SIWC_PORT`);
}

const [command = 'help', ...rest] = process.argv.slice(2);
const flags = parseFlags(rest);
const commands = { login: cmdLogin, status: cmdStatus, test: cmdTest, models: cmdModels, refresh: cmdRefresh, logout: cmdLogout, url: cmdUrl };

if (!commands[command]) {
  usage();
  process.exitCode = command === 'help' || command === '--help' || command === '-h' ? 0 : 2;
} else {
  try {
    await commands[command](flags);
  } catch (error) {
    printError(error);
    if (error instanceof NoLLMAvailableError) console.error(`\nTo fix: ${CLI} login   (or export OPENAI_API_KEY=...)`);
    process.exitCode = 1;
  }
}
