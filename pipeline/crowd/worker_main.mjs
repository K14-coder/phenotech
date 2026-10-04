// ===========================================================================
// Rare Disease Atlas research worker (main loop). The code above this line is a copy of
// integrations/openai/siwc.mjs and llm.mjs, inlined by pipeline/crowd/build_worker.mjs.
// ===========================================================================

const WORKER_VERSION = '2026-10-04';
const ANTHROPIC_DEFAULT_MODEL = 'claude-sonnet-5-5';
const DEFAULT_SERVER = 'https://rare-disease-atlas-five.vercel.app';
const CONFIG_PATH = path.join(WORKER_HOME, 'config.json');
const SHORT = { mechanism: 'mechanism', process: 'process', therapies: 'therapies', phenotypes: 'phenotypes', natural_history: 'natural history', research_groups: 'research groups' };

const HELP = `Rare Disease Atlas research worker ${WORKER_VERSION}

Researches rare diseases from the atlas research queue with YOUR OpenAI access, in a loop until you stop it.
The atlas fetches the PubMed abstracts; your model extracts claims; the atlas verifies every quote.

Usage:
  node rare-atlas-worker.mjs [--server URL] [options]
  node rare-atlas-worker.mjs login [--reconsent] [--new-account]    sign in with ChatGPT (Plus/Pro) now
  node rare-atlas-worker.mjs status                                 show the ChatGPT sign-in and atlas token
  node rare-atlas-worker.mjs logout                                 sign out of ChatGPT and forget the atlas token

Options:
  --server URL      atlas site (default ${DEFAULT_SERVER})
  --model SLUG      model to use (default: ${DEFAULT_MODEL}, or the first model your ChatGPT plan lists)
  --api-key         use OPENAI_API_KEY (API billing) instead of your ChatGPT plan
  --provider P      openai (default) or anthropic (Claude; reads ANTHROPIC_API_KEY, default model ${ANTHROPIC_DEFAULT_MODEL})
  --max-tasks N     stop after N diseases (default: run until Ctrl-C or the queue is empty)
  --max-calls N     stop after N model calls (a cost cap; the current disease is handed back)
  --help

Atlas worker token: create one on <server>/research-queue while signed in. The worker asks for it once and
keeps it in ${CONFIG_PATH} (mode 600); or set RARE_ATLAS_TOKEN.
ChatGPT credentials are kept in ${path.join(WORKER_HOME, 'secrets')} (mode 600; RARE_ATLAS_SECRETS_DIR overrides).
Ctrl-C once: finish the current model call, hand the disease back with what was found, exit. Twice: exit now.`;

function parseArgv(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) out._.push(a);
    else if (a.includes('=')) out[a.slice(2, a.indexOf('='))] = a.slice(a.indexOf('=') + 1);
    else if (['server', 'model', 'max-tasks', 'max-calls', 'provider'].includes(a.slice(2))) out[a.slice(2)] = argv[++i];
    else out[a.slice(2)] = true;
  }
  return out;
}

const stamp = () => new Date().toTimeString().slice(0, 8);
const say = (...parts) => console.log(`[${stamp()}]`, ...parts);

async function readConfig() {
  try {
    return JSON.parse(await readFile(CONFIG_PATH, 'utf8'));
  } catch {
    return { tokens: {} };
  }
}
async function writeConfig(config) {
  await mkdir(WORKER_HOME, { recursive: true, mode: 0o700 });
  const tmp = `${CONFIG_PATH}.${process.pid}.tmp`;
  await writeFile(tmp, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
  await chmod(tmp, 0o600);
  await rename(tmp, CONFIG_PATH);
}

function serverUrl(raw) {
  let u;
  try {
    u = new URL(raw || DEFAULT_SERVER);
  } catch {
    throw new Error(`--server is not a URL: ${raw}`);
  }
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname);
  if (u.protocol !== 'https:' && !(local && u.protocol === 'http:')) throw new Error('--server must use https (http is allowed only for 127.0.0.1/localhost).');
  return u.origin;
}

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(question, (answer) => {
    rl.close();
    resolve(answer.trim());
  }));
}

class AtlasError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function atlas(server, token, route, method = 'GET', body) {
  let r;
  try {
    r = await fetch(`${server}${route}`, {
      method,
      headers: { authorization: `Bearer ${token}`, ...(body === undefined ? {} : { 'content-type': 'application/json' }), 'user-agent': `rare-atlas-worker/${WORKER_VERSION}` },
      body: body === undefined ? undefined : JSON.stringify(body),
      redirect: 'error',
      signal: AbortSignal.timeout(90_000),
    });
  } catch (error) {
    throw new AtlasError(`Could not reach ${server} (${error?.cause?.code ?? error.name}).`, 0);
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new AtlasError(j.error ?? `${route} returned HTTP ${r.status}`, r.status);
  return j;
}

/** The model's user message for one batch (same text as the browser runner, components/queue/queue-client.ts). */
function batchTexts(p) {
  const d = p.disease;
  const missing = p.checklist.filter((c) => !c.done);
  const head = [
    `Disease: ${d.name}${d.synonyms.length ? ` (also called: ${d.synonyms.join('; ')})` : ''}`,
    `Genes: ${d.genes.join(', ') || 'none recorded'}`,
    `Identifiers: ${[d.mondo, ...d.omim.map((o) => `OMIM:${o}`), ...d.orpha.map((o) => `ORPHA:${o}`)].filter(Boolean).join(', ')}`,
    `Already in the atlas: curated mechanism classes: ${p.known.mechanismClasses.join(', ') || 'none'}; DisMech mechanism chain: ${p.known.dismech ? 'yes' : 'no'}.`,
    missing.length
      ? `Still missing (focus here first): ${missing.map((c) => `${c.label} (have ${c.have} of ${c.need} ${c.unit})`).join('; ')}.`
      : 'The checklist is complete; add any further solid claims.',
    '',
    'Records:',
  ].join('\n');
  const out = [];
  for (let i = 0; i < p.abstracts.length; i += p.batchSize) {
    const recs = p.abstracts.slice(i, i + p.batchSize).map((a) => [
      `PMID: ${a.pmid}`,
      `Title: ${a.title}`,
      `Abstract: ${a.abstract}`,
      `Senior authors: ${a.senior_authors.map((s) => `${s.name} — ${s.affiliation || '(no affiliation listed)'}`).join('; ') || '(none listed)'}`,
    ].join('\n'));
    out.push(`${head}\n\n${recs.join('\n\n')}`);
  }
  return out;
}

const checklistLine = (items) => items.map((c) => `${SHORT[c.id] ?? c.id} ${c.have}/${c.need}${c.done ? ' ok' : ''}`).join(' · ');

async function ensureToken(server, args) {
  if (process.env.RARE_ATLAS_TOKEN) return process.env.RARE_ATLAS_TOKEN.trim();
  const config = await readConfig();
  if (config.tokens?.[server]) return config.tokens[server];
  if (!process.stdin.isTTY) throw new Error(`No atlas worker token. Create one on ${server}/research-queue and set RARE_ATLAS_TOKEN.`);
  console.log(`\nThis worker needs an atlas worker token so your verified claims carry your handle.\nSign in on ${server}/research-queue, click "Create a worker token" and paste it here.`);
  const token = await ask('Worker token: ');
  if (!/^rqw_[A-Za-z0-9_-]{30,80}$/.test(token)) throw new Error('That does not look like a worker token (it starts with rqw_).');
  config.tokens = { ...(config.tokens ?? {}), [server]: token };
  if (!args['no-save']) await writeConfig(config);
  return token;
}

async function forgetToken(server) {
  const config = await readConfig();
  if (config.tokens?.[server]) {
    delete config.tokens[server];
    await writeConfig(config);
  }
}

/** One Anthropic Messages call; strict JSON through a forced tool call whose input_schema is the claim schema. */
async function completeAnthropic({ instructions, input, schema, model, signal }) {
  let r;
  try {
    r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({
        model: model || ANTHROPIC_DEFAULT_MODEL,
        max_tokens: 8000,
        system: instructions,
        tools: [{ name: 'submit_claims', description: 'Submit the extracted claims and research groups.', input_schema: schema }],
        tool_choice: { type: 'tool', name: 'submit_claims' },
        messages: [{ role: 'user', content: input }],
      }),
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(DEFAULT_TIMEOUT_MS)]) : AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      redirect: 'error',
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw Object.assign(new Error(`Could not reach api.anthropic.com (${error?.cause?.code ?? error.name}).`), { kind: 'network' });
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const kind = r.status === 401 ? 'auth' : r.status === 429 ? 'rate_limited' : r.status === 404 ? 'model_not_found' : r.status >= 500 ? 'server_error' : 'invalid_request';
    throw Object.assign(new Error(`Anthropic: ${j.error?.message ?? `HTTP ${r.status}`}`), { kind });
  }
  const call = (j.content ?? []).find((c) => c.type === 'tool_use' && c.name === 'submit_claims');
  if (!call?.input) throw Object.assign(new Error(`Anthropic returned no tool call (stop reason ${j.stop_reason}).`), { kind: 'invalid_json' });
  return { json: call.input, model: j.model ?? model, usage: j.usage ?? null };
}

async function ensureOpenAI(args) {
  if (args.provider === 'anthropic') {
    if (!process.env.ANTHROPIC_API_KEY) throw new Error('--provider anthropic needs ANTHROPIC_API_KEY in the environment.');
    say(`Using Anthropic Claude (${args.model || ANTHROPIC_DEFAULT_MODEL}) with ANTHROPIC_API_KEY (your API credits).`);
    return;
  }
  if (args.provider && args.provider !== 'openai') throw new Error('--provider must be openai or anthropic.');
  if (args['api-key']) {
    if (!process.env.OPENAI_API_KEY) throw new Error('--api-key needs OPENAI_API_KEY in the environment.');
    process.env.OPENAI_AUTH = AUTH_API_KEY;
    say('Using OPENAI_API_KEY (API billing).');
    return;
  }
  process.env.OPENAI_AUTH = AUTH_CHATGPT;
  const st = await status();
  if (st.signedIn && st.planUsage) {
    say(`Using your ChatGPT plan${st.email ? ` (${st.email})` : ''}. Usage and limits: ${MANAGE_USAGE_URL}`);
    return;
  }
  say('Signing in with ChatGPT. A browser window opens; approve "use your ChatGPT plan". The callback is a 127.0.0.1 page on this machine.');
  const result = await login({
    reconsent: Boolean(st.signedIn && !st.planUsage),
    onAuthorizeUrl: (url) => console.log(`If no browser opens, visit:\n${url}\n`),
    onBrowserError: () => console.log('Could not open a browser automatically; use the link above.'),
  });
  if (!result.planUsage) throw new Error('ChatGPT plan usage was not granted, so the worker cannot use your plan. Run again with: node rare-atlas-worker.mjs login --reconsent');
  say(`Signed in${result.email ? ` as ${result.email}` : ''}.`);
}

async function runTask(server, token, packet, model, control, provider) {
  const batches = batchTexts(packet);
  say(`Researching ${packet.disease.name} (${packet.disease.id}; ${packet.disease.genes.join(', ')}), round ${packet.lease.round}/${packet.lease.maxRounds}, ${packet.abstracts.length} abstracts, lease until ${new Date(packet.lease.expiresAt).toLocaleTimeString()}`);
  say(`  checklist: ${checklistLine(packet.checklist)}`);
  const totals = { accepted: 0, rejected: 0 };
  for (let i = 0; i < batches.length; i += 1) {
    if (control.stop) break;
    if (control.calls >= control.maxCalls) {
      say(`  reached --max-calls ${control.maxCalls}; handing the disease back.`);
      control.stop = true;
      break;
    }
    control.calls += 1;
    const started = Date.now();
    let out;
    try {
      const call = provider === 'anthropic' ? completeAnthropic : complete;
      out = await call({ instructions: packet.instructions, input: batches[i], schema: packet.schema, schemaName: 'claims', model, signal: control.abort.signal });
    } catch (error) {
      if (control.stop) break;
      throw error;
    }
    const res = await atlas(server, token, '/api/queue/submit', 'POST', {
      token: packet.lease.token,
      provider,
      model: out.model,
      claims: out.json?.claims ?? [],
      research_groups: out.json?.research_groups ?? [],
    });
    totals.accepted += res.accepted + res.acceptedGroups;
    totals.rejected += res.rejected.length;
    say(`  batch ${i + 1}/${batches.length} (${out.model}, ${((Date.now() - started) / 1000).toFixed(0)}s): ${res.accepted} claims + ${res.acceptedGroups} groups verified, ${res.rejected.length} rejected${res.duplicates ? `, ${res.duplicates} duplicates` : ''}`);
    for (const r of res.rejected.slice(0, 3)) say(`    rejected ${r.kind} #${r.index + 1}: ${r.reason}`);
    say(`  checklist: ${checklistLine(res.checklist)}`);
  }
  const done = await atlas(server, token, '/api/queue/done', 'POST', { token: packet.lease.token });
  const gaps = done.missing.map((m) => SHORT[m] ?? m).join(', ');
  say(done.status === 'complete'
    ? `Done: ${packet.disease.name} is complete and leaves the queue.`
    : done.status === 'retired'
      ? `Handed back: ${packet.disease.name} leaves the queue after ${done.rounds} rounds, still missing ${gaps}.`
      : `Handed back: ${packet.disease.name} returns to the top of the queue; still missing ${gaps}.`);
  return totals;
}

async function main() {
  const args = parseArgv(process.argv.slice(2));
  if (args.help || args.h) {
    console.log(HELP);
    return;
  }
  const command = args._[0];
  const server = serverUrl(args.server);
  if (command === 'login') {
    const r = await login({ reconsent: Boolean(args.reconsent), newAccount: Boolean(args['new-account']), onAuthorizeUrl: (url) => console.log(`If no browser opens, visit:\n${url}\n`), onBrowserError: () => {} });
    console.log(`Signed in${r.email ? ` as ${r.email}` : ''}; plan usage ${r.planUsage ? 'granted' : 'NOT granted (run login --reconsent)'}.`);
    return;
  }
  if (command === 'logout') {
    console.log((await logout()).message);
    await forgetToken(server);
    console.log(`Forgot the atlas token for ${server}.`);
    return;
  }
  if (command === 'status') {
    const st = await status();
    const config = await readConfig();
    console.log(`ChatGPT: ${st.signedIn ? `signed in${st.email ? ` as ${st.email}` : ''}, plan usage ${st.planUsage ? 'granted' : 'not granted'}` : 'not signed in'}`);
    console.log(`Atlas token for ${server}: ${process.env.RARE_ATLAS_TOKEN || config.tokens?.[server] ? 'present' : 'none'}`);
    return;
  }
  if (command) throw new Error(`Unknown command "${command}". Try --help.`);

  console.log(`Rare Disease Atlas research worker ${WORKER_VERSION} -> ${server}`);
  const token = await ensureToken(server, args);
  await ensureOpenAI(args);
  const maxTasks = args['max-tasks'] ? Math.max(1, Number(args['max-tasks'])) : Infinity;
  const model = typeof args.model === 'string' ? args.model : undefined;

  const maxCalls = args['max-calls'] ? Math.max(1, Number(args['max-calls'])) : Infinity;
  const control = { stop: false, abort: new AbortController(), interrupts: 0, calls: 0, maxCalls };
  process.on('SIGINT', () => {
    control.interrupts += 1;
    if (control.interrupts > 1) {
      console.log('\nExiting now. Your lease expires on its own and the disease returns to the queue.');
      process.exit(130);
    }
    control.stop = true;
    console.log('\nStopping: handing the current disease back (Ctrl-C again to exit immediately)…');
    control.abort.abort();
  });

  const session = { tasks: 0, accepted: 0, rejected: 0 };
  while (!control.stop && session.tasks < maxTasks) {
    let claim;
    try {
      claim = await atlas(server, token, '/api/queue/claim', 'POST', {});
    } catch (error) {
      if (error.status === 401) {
        await forgetToken(server);
        throw new Error(`${error.message} (the saved token was removed; run again to paste a new one).`);
      }
      if (error.status === 429 || error.status === 503 || error.status === 0) {
        say(`${error.message} Waiting 60 s…`);
        await sleep(60_000);
        continue;
      }
      throw error;
    }
    if (!claim.packet) {
      say(claim.message ?? 'The queue is empty. Thank you!');
      break;
    }
    try {
      const t = await runTask(server, token, claim.packet, model, control, args.provider === 'anthropic' ? 'anthropic' : 'openai');
      session.tasks += 1;
      session.accepted += t.accepted;
      session.rejected += t.rejected;
      say(`Session: ${session.tasks} disease(s), ${session.accepted} verified, ${session.rejected} rejected.`);
    } catch (error) {
      const info = error?.kind && !(error instanceof LLMRequestError) ? { kind: error.kind, message: error.message } : describeError(error);
      say(`Stopped: ${info.message}`);
      if (info.action?.url) say(`  ${info.action.label}: ${info.action.url}`);
      try {
        await atlas(server, token, '/api/queue/done', 'POST', { token: claim.packet.lease.token });
        say('  The disease was handed back with what was found so far.');
      } catch {
        // the lease expires on its own
      }
      const fatal = ['usage_limit', 'not_eligible', 'auth', 'not_authorized', 'client_not_enabled', 'quota', 'model_not_found', 'no_llm_available', 'login_required', 'plan_usage_not_granted'];
      if (fatal.includes(info.kind) || error instanceof AtlasError) process.exitCode = 1;
      if (fatal.includes(info.kind) || error instanceof AtlasError || control.stop) break;
      await sleep(5_000);
    }
  }
  say(`Bye. ${session.tasks} disease(s), ${session.accepted} verified claims this session.`);
}

main().catch((error) => {
  console.error(`Error: ${error?.message ?? error}`);
  process.exit(1);
});
