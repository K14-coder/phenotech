# OpenAI integration: Sign in with ChatGPT, with an API-key fallback

Researched on 2026-10-03. Sources: the Markdown version of every page under `developers.openai.com/siwc/`, the cookbook article, the source of OpenAI's official devkit, and OpenAI's live OIDC discovery document. The feature is labelled a **preview**, so check the pages again before the demo.

Code: `integrations/openai/` (`siwc.mjs`, `llm.mjs`, `cli.mjs`). It has no dependencies and runs on Node 20 or later (we use Node 26).

---

## Feasibility for us

**Verdict: feasible for the local app, not for the hosted site.**

| Scenario | OK? | Why |
|---|---|---|
| A user clones our open-source repo, runs `npm run dev` and clicks **Continue with ChatGPT** | **Yes** | ChatGPT plan usage is offered to open-source projects and to personal or locally hosted apps. The open-source flow registers a client during sign-in (`client_id=dynamic_agent_client`), with no client secret, partner key or approval step ([quickstart](https://developers.openai.com/siwc/quickstart), [overview](https://developers.openai.com/siwc/token-sharing-open-source), [sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [cookbook](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt#usage-policy-and-terms)). |
| The Vercel deployment calls the model with visitors' ChatGPT plans | **No** | Paid or remotely hosted apps must go through the [interest form or waitlist](https://openai.com/form/sign-in-with-chatgpt-interest/). The hosted "website" flow is for selected commercial partners only ([website](https://developers.openai.com/siwc/website), [request a client ID](https://developers.openai.com/siwc/request-client-id)). The `127.0.0.1` callback also only reaches the machine running the browser ([self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)). |
| The Vercel deployment shows outputs we generated offline with OpenAI models | **Yes** | It makes no live calls, so no Sign in with ChatGPT is involved. See [How to wire into the app](#how-to-wire-into-the-app). |
| A user without Plus or Pro (Free, or some work workspaces) | **Fallback** | Plan usage is for eligible ChatGPT **Plus and Pro** users ([quickstart](https://developers.openai.com/siwc/quickstart)). Anyone else needs `OPENAI_API_KEY`, or sees the precomputed outputs. |

Main risks (details in [Risks](#risks)):

- It is a preview.
- Structured outputs on the plan route are not documented.
- Plus plans have a shared five-hour usage limit.
- `next dev` listens on every network interface by default.
- Using someone's personal plan to generate the published dataset is a policy grey area.

---

## (a) Can an open-source tool use it without approval? Terms, registration, branding

**Availability**

- The [quickstart](https://developers.openai.com/siwc/quickstart) says identity-only sign-in is a limited commercial trial, and ChatGPT plan usage is open to all open-source partners and to selected private clients.
- The [overview](https://developers.openai.com/siwc/token-sharing-open-source) covers open-source and locally hosted apps. It sends paid or remotely hosted apps to the interest form.
- The cookbook's [usage policy section](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt#usage-policy-and-terms) says the same: open-source tools and personal projects that run locally can use it now; paid or remotely hosted apps must join the waitlist before offering it.

**Registration (self-serve, at sign-in time).** [Sign-in guide](https://developers.openai.com/siwc/token-sharing-open-source/sign-in):

- The first authorization uses `client_id=dynamic_agent_client`, plus `agent_name_hint` (the app's real name, the same on every installation) and `ext_agent_host_id`.
- The callback returns an **issued** `client_id` (`oaiapp_…`). Save it and reuse it for later sign-ins to that account. Never save `dynamic_agent_client` as the ID.
- The flow needs no client secret and no partner API key.

**Host ID** ([overview](https://developers.openai.com/siwc/token-sharing-open-source#a-client-vs-an-agent-host)):

- `ext_agent_host_id` is required. It must be stable for each install, opaque (not an email address or user ID), and persisted **before** the first sign-in.
- Accepted formats are `urn:ietf:params:oauth:jwk-thumbprint:…` (recommended), `urn:uuid:<uuidv4>` (supported; this is what we use) and `did:key:…`.
- It identifies the host. It is not a credential.

**Branding and UX requirements** ([UI/UX guidelines](https://developers.openai.com/siwc/ui-ux-guidelines), [website: button formats](https://developers.openai.com/siwc/website), [quickstart](https://developers.openai.com/siwc/quickstart#make-sign-in-recognizable)):

- Label the sign-in action **Continue with ChatGPT**. Use one of the approved button formats ("Continue with ChatGPT" or "Sign in with ChatGPT", black or white, with the ChatGPT logo), approved OpenAI branding, and the [OpenAI brand guidelines](https://openai.com/brand/). Give it about the same prominence as other sign-in options.
- After the **first** sign-in with plan usage enabled, show a one-time confirmation ("You're using your ChatGPT plan" with a **Got it** button).
- When requests use the plan, show **Using ChatGPT plan** with a **Manage usage** link to <https://chatgpt.com/settings/usage>.
- On a usage-limit error, make **Manage usage** the primary action.
- Show which of the app's own plans support ChatGPT plan usage. This doesn't apply to us (the app is free), but don't imply otherwise.
- Keep ChatGPT plan usage clearly separate from any charges of our own.

**Terms and licences**

- Review [OpenAI's terms and policies](https://openai.com/policies/) before distributing ([cookbook](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt#usage-policy-and-terms)).
- The [official devkit](https://github.com/openai/sign-in-with-chatgpt-devkit) is under a **noncommercial** licence, and its brand assets fall under the OpenAI brand guidelines. We **did not copy devkit code**: `integrations/openai/` is written from the protocol docs, so our repo's licence is unaffected. If we use the devkit's button SVGs (`assets/brand/`), follow the brand guidelines.

## (b) Does a locally run web app count?

**Yes, as we read the docs.**

- The docs cover "open-source and locally hosted apps", and the cookbook covers "personal projects that run locally". The devkit describes itself as being for open-source apps that run on the user's own machine.
- A Next.js server that the user starts with `npm run dev` on their own machine, from our public repo, fits that description. The docs never mention web servers specifically, so this is our reading, not an explicit statement.

Constraints that follow:

1. The loopback callback (`http://127.0.0.1:<port>/auth/callback`) must be served on the machine that runs the browser. Our module starts its own listener on `127.0.0.1`, separate from Next.js on port 3000.
2. Tokens must stay **server-side**. The docs say to keep tokens out of browser storage, URLs, logs and analytics ([credential security](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions#credential-security)). Our Next.js routes must never send a token to the browser.
3. Any **remotely hosted** copy, Vercel included, is out of scope without OpenAI's approval.

## (c) Inference with the token

Source: [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference) and [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

| Item | Value |
|---|---|
| API | **Responses API**, `POST https://api.openai.com/v1/responses`. This public endpoint only. Do **not** use ChatGPT's `backend-api`. |
| Headers | `Authorization: Bearer <OAuth access token>`, `Content-Type: application/json`. We also send `Accept: text/event-stream`, as the devkit does. |
| Required body fields | `"store": false`, `"stream": true`, and `input` as an **array** of messages. Put system guidance in `instructions` or `developer` messages. `system` role items are rejected; `llm.mjs` turns them into `developer` messages. |
| Unsupported fields (omit) | `background`, `conversation`, `max_output_tokens`, `max_tool_calls`, `metadata`, `moderation`, `multi_agent`, `prompt`, `prompt_cache_retention`, `safety_identifier`, `temperature`, `top_logprobs`, `top_p`, `truncation`, `user`. Over HTTP, also `previous_response_id` (send the full history in `input` instead). |
| Tools | Function and custom tools must be grouped in namespaces. Web search depends on the model and policy. Image generation, file search, Code Interpreter, computer use, hosted MCP/connectors and `tool_search` are **not supported**. |
| Inputs | Text, images and files if the model accepts them. Audio and video input, the Files upload API and transcription are not supported. |
| Models | The available models depend on the account. List them with `GET https://api.openai.com/v1/models` and the same bearer token. The response is `{ "models": [{ "slug", "display_name", "visibility" }] }`. Show models with `visibility == "list"` in the server's order and pass the `slug` as `model`. The docs' examples use **`gpt-6.1-sol`**. |
| Streaming | Read the server-sent events to the end. Success means **only** `response.completed`. A usage-limit error can arrive as `response.failed` after streaming has begun. Treat `response.incomplete`, errors and a stream that ends early as failures. |
| Structured outputs (JSON Schema) | **Not documented for this route**: neither listed as supported nor as unsupported (`text` is not on the unsupported list). On the normal API it is `text: { format: { type: "json_schema", name, schema, strict: true } }` ([Structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)). `llm.mjs` sends that first. If the plan route answers `subscription_sharing_unsupported_capability` with `param` `text…`, it retries once with the schema in `instructions` and validates the JSON locally. The result's `structuredMode` says which way was used. |

**Default model.** `llm.mjs` uses `gpt-6.1-sol` (the model in the SIWC docs; OpenAI's [model guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra) calls it the balanced GPT-6 option). On the ChatGPT path, if the account's model list doesn't include it, the first listed model is used instead. You can override the model with `OPENAI_MODEL` or `complete({ model })`.

**Codex app-server** is another supported client ([codex-app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)). We don't need it.

## (d) Token refresh and storage

Source: [Token reference](https://developers.openai.com/siwc/token-sharing-open-source/token-reference) and [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions).

- **Lifetimes.** Access tokens last 1 hour (`expires_in: 3600`). Refresh tokens last 30 days and **rotate**: each refresh returns a new refresh token with a fresh 30 days, and there is no fixed limit on the chain.
- **Token response fields:** `access_token`, `refresh_token` (only when `offline_access` is granted), `id_token`, `token_type`, `expires_in`, `scope`, `earliest_refresh_at`.
- **Refresh request.** Refresh near expiry with a form-encoded `POST https://auth.openai.com/api/accounts/oauth/token` containing `grant_type=refresh_token`, the **issued** `client_id`, `refresh_token` and `resource=https://api.openai.com/v1`. Omit `scope` to keep the existing grant.
- **After a refresh.** Replace the access token, expiry, scopes and refresh token together. **Serialize refreshes** so two processes never race on a rotating token.
- **Refresh errors that need a new sign-in:** `invalid_grant`, `invalid_refresh_token`, `token_expired`, `refresh_token_expired`, `refresh_token_invalidated` and `refresh_token_reused`. Clear the tokens and run OAuth again with the saved client ID. `invalid_client` means the client configuration needs fixing ([refresh errors](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery#refresh-errors)).
- **Storage.** Keep one record per issued client ID and verified identity. The record holds email, issuer, subject, `client_id`, `ext_agent_host_id`, `id_token`, `access_token`, `refresh_token`, `token_type`, `expires_in`, `scopes` and `saved_at`. Write it atomically with owner-only permissions (`0600`). Never commit or log it, and keep it out of browser storage and URLs ([sign-in §5](https://developers.openai.com/siwc/token-sharing-open-source/sign-in#5-store-credentials-in-a-local-file)).
- **Sign-out.**
  - Revoke at the `revocation_endpoint` from [discovery](https://auth.openai.com/.well-known/openid-configuration) (`https://auth.openai.com/api/accounts/oauth/revoke`) with `token=<refresh_token>`, `token_type_hint=refresh_token` and `client_id`. An empty HTTP 200 means success.
  - Then clear the tokens locally, but keep the client registration and host ID.
  - If revocation can't be confirmed, say so: the user can disconnect the app in ChatGPT settings ([end the renewable session](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions#end-the-renewable-session)).
- **Disconnections.** OpenAI does not notify the app when a user disconnects it in ChatGPT. The app finds out when a request or refresh fails ([disconnection](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery#disconnection)).

**What we do.** Credentials are stored in `<repo>/.secrets/openai-siwc.json`. The directory is set to mode 700 and the file to 600 (`.secrets/` is gitignored). Writes go to a temp file followed by a rename. Refreshes are serialized with an in-process queue plus an `O_EXCL` lock file, which covers the CLI and the dev server running at the same time.

## (e) Error cases and recommended UX

Source: [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery) and the [UI/UX guidelines](https://developers.openai.com/siwc/ui-ux-guidelines#offer-options-when-users-reach-a-usage-limit). OpenAI never switches a failed plan request to another billing path. Keep the HTTP status, error code and request ID.

| Situation | How it shows up | Recommended UX | `llm.mjs` result |
|---|---|---|---|
| User cancels or declines consent | Callback has `error=access_denied` | Validate `state`, stop, don't exchange a code | `ConsentDeclinedError` |
| Signed in, but plan usage **not enabled** | Token response `scope` lacks `chatgpt.tokens.use.direct` | Keep the sign-in, mark plan usage as off, and offer a choice: enable it (OAuth again with the saved client ID, the full scope set and `prompt=consent`; [details](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery#chatgpt-plan-use-isnt-enabled)) or use an API key | `PlanUsageNotGrantedError` internally. `complete()` falls back to `OPENAI_API_KEY`, or throws `NoLLMAvailableError` |
| User **not eligible** (plan, workspace or policy) | 403 `subscription_sharing_user_not_eligible` | Explain the restriction. Don't repeat the request or loop through OAuth | `LLMRequestError` with `kind: 'not_eligible'` |
| **Allowance used up** (plan or this app's limit) | 429 `subscription_sharing_usage_limit_exceeded`, possibly mid-stream as `response.failed` | Pause plan requests. Primary action: **Manage usage** (<https://chatgpt.com/settings/usage>). Don't guess a reset time | `kind: 'usage_limit'`, with `manageUsageUrl` |
| Usage can't be checked right now | 503 `subscription_sharing_usage_unavailable` | Keep the credentials and retry later with bounded backoff | `kind: 'temporarily_unavailable'`, retried twice |
| **Region** or policy block before the request starts | 403 with a body like `{"detail": "..."}` (diagnostic text, not a code) | Show the restriction | `kind: 'policy_or_region'`, `serverMessage` |
| Identity or permission not accepted | 401 before the request starts | Check the selected account and granted scopes | `kind: 'auth'` |
| Direct routing unavailable or not enabled | 503 before the request starts | Keep the credentials and back off | `kind: 'temporarily_unavailable'` |
| Unsupported parameter, tool, model or tier | 400 `subscription_sharing_unsupported_capability` with `param` | Remove the item named in `param`. Don't resend the same body | `kind: 'unsupported_capability'` |
| Wrong route | 403 `subscription_sharing_route_not_supported` | Use `POST /v1/responses` only | `kind: 'unsupported_route'` |
| Subscriber context invalid | 401 `subscription_sharing_invalid_user` | Note the request ID. Sign in again after a confirmed revocation | `kind: 'auth'` |
| Grant doesn't authorize the operation | 403 `chatpass_v2_scope_not_authorized` or `chatpass_v2_invalid_authorization_context` | Check the client and grant configuration | `kind: 'not_authorized'` |
| Account or workspace data temporarily unavailable | 503 `subscription_sharing_user_unavailable` | Back off | `kind: 'temporarily_unavailable'` |
| Refresh token unusable | Refresh errors listed in (d) | Sign in again with the saved client ID | `LoginRequiredError`, then fallback or `NoLLMAvailableError` |

`describeError(err)` in `llm.mjs` turns any of these into `{ kind, message, action? }` for the UI.

## (f) Rate limits and per-app caps

- **Plus:** a **five-hour usage limit shared by every app** that uses the person's plan (open-source and private clients alike). No app gets its own allowance. **Pro:** the five-hour limit doesn't apply ([tracking usage](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions#tracking-usage)).
- **Per-app caps set by the user:** in ChatGPT Settings → Usage, users can review each app's usage and manage its access. The docs' illustration shows a per-app weekly limit (10–100% of the plan) and a switch for continuing with credits after the plan limit. A usage-limit error can come from that **app-specific** limit as well as the plan ([errors](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery#structured-responses-errors)).
- **Hosts:** all hosts of one client (laptop, VM) share that client's usage settings and limits ([overview](https://developers.openai.com/siwc/token-sharing-open-source#a-client-vs-an-agent-host)).
- **No published RPM or TPM numbers** for this route. `max_output_tokens` is not supported, so output length can't be capped on the plan route: keep prompts asking for short answers.

---

## Risks

1. **Preview feature.** The parameters, error codes and eligibility rules may change during the hackathon. Check the [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) page again before the demo.
2. **Who can demo it.** It needs a personal ChatGPT **Plus or Pro** account in an eligible region. Work workspaces or other regions may get `not_eligible` or a 403. Keep `OPENAI_API_KEY` and precomputed outputs as backups.
3. **Structured outputs are unverified on the plan route.** We have a fallback, but prompted JSON is less reliable than native strict mode. Run `cli.mjs test` once to see which mode the account gets.
4. **Plus users' five-hour limit is shared with their own ChatGPT use.** Bulk extraction (hundreds of abstracts) can use it up. Keep live AI features to single, user-triggered requests.
5. **Using a personal plan to build the published dataset is a grey area.** The docs allow local or personal use. Generating content we then publish on Vercel isn't addressed. **Prefer an API key (for example hackathon credits) for the offline batch.** If someone's plan is used, keep the batch small and check [OpenAI's policies](https://openai.com/policies/).
6. **Exposure on the local network.** `next dev` listens on all interfaces by default, so anyone on the same Wi-Fi could call our AI routes and use the signed-in plan. Run `next dev -H 127.0.0.1` and keep the loopback and same-origin checks shown below. Other websites could also send cross-site POSTs to `127.0.0.1:3000`; the same checks and the JSON-only content type block that.
7. **Bundling.** Next.js 16 (Turbopack) bundles imports by default. `llm.mjs` finds `.secrets/` through `import.meta.url`, so import it at runtime as shown below, or set `SIWC_PROJECT_ROOT`. This is untested inside Next.js.
8. **Policy fit for a local web app is our interpretation.** No page explicitly says a local web server is fine. Every page does say local or open-source apps are fine and remotely hosted ones are not.
9. **Branding.** Use the approved button and logo. Don't present the app as made or endorsed by OpenAI.

## Assumptions we could not verify (we never signed in to a real account)

- That the authorization server accepts our exact URL. The parameters match the [sign-in table](https://developers.openai.com/siwc/token-sharing-open-source/sign-in#2-start-authorization) one-to-one, and `cli.mjs url` prints them. Callback path: we use `/auth/callback`, the documented example and the devkit's value. The brief said `/callback`; the docs only require that the path stays the same for the life of a registration.
- That `ext_agent_host_id` is accepted. The docs mark it required. The devkit sends it only behind a `sendHostId` switch, with a comment that ties the switch to authorization deployments that support it.
- The type of `earliest_refresh_at`, which is undocumented. We accept Unix seconds, milliseconds or an ISO date.
- Whether `text.format` json_schema works on the plan route (see Risks 3).
- Whether `reasoning.effort` is accepted on the plan route. It isn't on the unsupported list, and we only send it when the caller asks.
- Which models a given account lists. Our default falls back to the first listed one.
- The devkit's error table also lists `subscription_sharing_v2_client_not_enabled`, which suggests a client could need enabling. The docs don't mention it. We map it to `kind: 'client_not_enabled'`.

What *was* verified:

- 21 end-to-end checks against a mocked OpenAI, using real loopback HTTP and RSA-signed ID tokens checked against a JWKS. They covered:
  - authorize parameters
  - state and Host checks
  - PKCE exchange
  - ID-token signature, issuer, audience and nonce checks
  - 600/700 file and directory modes
  - one refresh for five concurrent callers, with the rotated token saved
  - reauthorization reusing the issued client ID
  - account and client mismatch rejection, `access_denied`, missing scope, `prompt=consent`
  - terminal refresh errors
  - logout and revocation
  - streaming parsed across chunk and CRLF boundaries
  - native and prompted structured output
  - error mapping and bounded retries
- The live discovery document confirms the endpoints (`authorize`, `oauth/token`, `oauth/revoke`, `jwks.json`, RS256, S256).

---

## Our module

| File | What it does |
|---|---|
| `integrations/openai/siwc.mjs` | `beginLogin()`, `login()`, `getAccessToken()` (auto-refresh), `refresh()`, `logout()`, `status()` (read-only, no tokens), `previewAuthorizeUrl()` (dry run), plus `verifyIdToken()` and `buildAuthorizeUrl()` |
| `integrations/openai/llm.mjs` | `complete({ instructions, input, schema?, schemaName?, model?, reasoningEffort?, authMode?, signal?, onDelta? })`, `listModels()`, `describeAuth()` (safe for the browser), `describeError()`, and the error classes `NoLLMAvailableError`, `LLMRequestError` and `LLMOutputError` |
| `integrations/openai/cli.mjs` | `login`, `status`, `test`, `models`, `refresh`, `logout`, `url` |

`complete()` returns `{ text, json?, model, authPath: 'chatgpt'|'api_key', structuredMode, usage, responseId, requestId, note? }`.

Auth order: a ChatGPT sign-in with plan usage, then `OPENAI_API_KEY`, then `NoLLMAvailableError`. A *temporary* sign-in failure (for example a network error during refresh) is thrown as is, never silently switched to the API key. To force a path, set `OPENAI_AUTH=chatgpt|api_key`.

Strict JSON Schema rules for `schema`: every object needs `additionalProperties: false` and must list **all** of its properties in `required`. Use `"type": ["string", "null"]` for optional fields.

## How to log in and test

```bash
cd /Users/khezanirani/Desktop/hacknation
node integrations/openai/cli.mjs url      # optional dry run: shows the exact authorize URL; writes nothing
node integrations/openai/cli.mjs login    # opens the browser
# In the browser: sign in with a ChatGPT Plus or Pro account, pick the personal workspace,
# keep the "use your ChatGPT plan" permission ticked and approve. Then close the tab.
node integrations/openai/cli.mjs status   # expect: plan usage ENABLED, auth path chatgpt
node integrations/openai/cli.mjs test     # plain prompt + structured-output prompt, prints the auth path
node integrations/openai/cli.mjs models   # what this account can use
node integrations/openai/cli.mjs logout   # revoke + delete local tokens (keeps registration + host ID)
```

If plan usage shows **NOT GRANTED**, run `node integrations/openai/cli.mjs login --reconsent`.

If port 1455 is busy, a free port is picked automatically. `--port N` or `SIWC_PORT` forces one.

API-key path: `OPENAI_API_KEY=... OPENAI_AUTH=api_key node integrations/openai/cli.mjs test`.

---

## How to wire into the app

Plan:

- **Local mode** (`npm run dev`): server routes call `llm.mjs`, and the UI shows **Continue with ChatGPT** plus an API-key fallback.
- **Vercel**: precomputed outputs only, generated offline with OpenAI.

### Local mode (Next.js 16 server routes)

1. **Bind the dev server to loopback:** `npx next dev -H 127.0.0.1`. Changing the `dev` script needs the web owner's sign-off.
2. **Load the integration at runtime**, skipping the bundler, so `import.meta.url` resolves to the real file. Also add a loopback guard:

```ts
// web/lib/openai-local.ts (server only)
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = process.env.SIWC_PROJECT_ROOT ?? path.resolve(process.cwd(), ".."); // web/ -> repo root

export const liveAIEnabled = () => !process.env.VERCEL && process.env.AI_MODE !== "precomputed";

export async function loadOpenAI() {
  const url = (file: string) => pathToFileURL(path.join(ROOT, "integrations/openai", file)).href;
  const [llm, siwc] = await Promise.all([
    import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url("llm.mjs")),
    import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url("siwc.mjs")),
  ]);
  return { llm, siwc };
}

// Serve AI routes only to the local user's own pages: loopback Host + same-origin.
export function isLocalRequest(req: Request) {
  const host = req.headers.get("host") ?? "";
  if (!/^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/.test(host)) return false;
  const origin = req.headers.get("origin");
  if (origin && origin !== `http://${host}`) return false;
  const site = req.headers.get("sec-fetch-site");
  return !site || site === "same-origin" || site === "none";
}
```

3. **Routes.** All of them export `runtime = "nodejs"` and `dynamic = "force-dynamic"`, and none returns a token:

```ts
// web/app/api/ai/status/route.ts — what the UI should show (safe to expose: no tokens)
export async function GET(req: Request) {
  if (!liveAIEnabled()) return Response.json({ mode: "precomputed" });
  if (!isLocalRequest(req)) return new Response("Forbidden", { status: 403 });
  const { llm } = await loadOpenAI();
  return Response.json({ mode: "live", ...(await llm.describeAuth()) });
  // -> { path: "chatgpt"|"api_key"|null, chatgpt: { signedIn, planUsage, email, planUsageFirstEnabledAt }, apiKeyConfigured, model, manageUsageUrl }
}

// web/app/api/ai/login/route.ts — "Continue with ChatGPT"
export async function POST(req: Request) {
  if (!liveAIEnabled()) return new Response("Not found", { status: 404 });
  if (!isLocalRequest(req) || !(req.headers.get("content-type") ?? "").startsWith("application/json")) return new Response("Forbidden", { status: 403 });
  const { reconsent = false } = await req.json().catch(() => ({}));
  const { siwc } = await loadOpenAI();
  const attempt = await siwc.beginLogin({ reconsent: Boolean(reconsent) }); // starts the 127.0.0.1 callback listener
  attempt.completion.catch(() => {});                // the UI polls /api/ai/status for the outcome
  await siwc.openInBrowser(attempt.authorizeUrl).catch(() => {}); // same machine, so the system browser works
  return Response.json({ authorizeUrl: attempt.authorizeUrl });   // fallback link if no window opened
}

// web/app/api/ai/logout/route.ts — POST: if (!liveAIEnabled() || !isLocalRequest(req)) 404/403;
// then `const { siwc } = await loadOpenAI(); return Response.json(await siwc.logout());`

// web/app/api/ai/claims/route.ts — task-specific, fixed instructions (don't expose a generic prompt proxy)
export async function POST(req: Request) {
  if (!liveAIEnabled()) return new Response("Not found", { status: 404 });
  if (!isLocalRequest(req) || !(req.headers.get("content-type") ?? "").startsWith("application/json")) return new Response("Forbidden", { status: 403 });
  const { abstract } = await req.json();
  if (typeof abstract !== "string" || !abstract.trim() || abstract.length > 20_000) {
    return Response.json({ error: { kind: "invalid_input", message: "abstract required" } }, { status: 400 });
  }
  const { llm } = await loadOpenAI();
  try {
    const out = await llm.complete({ instructions: CLAIM_INSTRUCTIONS, input: abstract, schema: CLAIM_SCHEMA, schemaName: "claims" });
    return Response.json({ claims: out.json.claims, extracted_by: `openai:${out.model}`, authPath: out.authPath });
  } catch (error) {
    const info = llm.describeError(error); // { kind, message, action? } (no secrets)
    const status = ["no_llm_available", "login_required", "plan_usage_not_granted"].includes(info.kind) ? 401
      : info.kind === "usage_limit" ? 429 : 502;
    return Response.json({ error: info }, { status });
  }
}
```

Example claim schema (strict-mode compliant). Per `docs/SCHEMA.md`, quotes must be **verbatim**. Set `verified: true` only after string-matching the quote against the abstract, and never invent PMIDs:

```js
const CLAIM_SCHEMA = {
  type: "object", additionalProperties: false, required: ["claims"],
  properties: { claims: { type: "array", items: {
    type: "object", additionalProperties: false,
    required: ["subject", "predicate", "object", "quote", "study_type"],
    properties: {
      subject: { type: "string" }, predicate: { type: "string" }, object: { type: "string" },
      quote: { type: "string", description: "exact sentence copied from the abstract" },
      study_type: { type: ["string", "null"], enum: ["clinical_trial", "case_report", "case_series", "cohort", "functional_study", "animal_model", "review", null] },
    } } } },
};
```

4. **UI states**, from the [UI/UX guidelines](https://developers.openai.com/siwc/ui-ux-guidelines):
   - **Not connected:** an approved **Continue with ChatGPT** button that calls `POST /api/ai/login`. Show "If nothing opened, open this link" with `authorizeUrl`, then poll `/api/ai/status` every 2 s for up to 10 minutes. Underneath: "or use an API key: put `OPENAI_API_KEY=...` in `.env.local` and restart".
   - **First sign-in with plan usage:** a one-time "You're using your ChatGPT plan" modal with **Got it**. Use `chatgpt.planUsageFirstEnabledAt` and a `localStorage` flag holding that value.
   - **Connected:** **Using ChatGPT plan** + **Manage usage** (<https://chatgpt.com/settings/usage>) beside the AI action, plus the account email and a sign-out link.
   - **`plan_usage_not_granted`:** "Enable ChatGPT plan usage" (`POST /api/ai/login` with `{ reconsent: true }`) or the API key.
   - **`usage_limit`:** "Usage limit reached" with **Manage usage** as the primary button.
   - **`not_eligible` / `policy_or_region`:** explain, and offer the API key or the precomputed outputs.

### Deployed mode (Vercel): precomputed outputs only

- Vercel sets `VERCEL=1`, so `liveAIEnabled()` is false: the AI routes return 404 (or `{ mode: "precomputed" }`), and the UI hides **Continue with ChatGPT**.
- **Do not set `OPENAI_API_KEY` on Vercel.** The deployed site makes no model calls.
- The UI reads the AI fields straight from `data/graph.json`. Label them "Generated offline with OpenAI (`extracted_by: openai:<model>`)" and show their evidence and confidence according to `docs/SCHEMA.md`. LLM-proposed items below 0.3 are drawn dashed and never presented as fact.

### Offline precompute (pipeline)

```js
// pipeline/<area>/extract-claims.mjs (sketch)
import { complete } from "../../integrations/openai/llm.mjs";
const out = await complete({ instructions: CLAIM_INSTRUCTIONS, input: abstractText, schema: CLAIM_SCHEMA, schemaName: "claims" });
// write out.json.claims into data/curated/*.json with extracted_by: `openai:${out.model}`,
// keep only quotes that string-match the stored abstract (verified: true), never invent IDs
```

Run it with `OPENAI_AUTH=api_key` when hackathon or API credits exist (see Risks 4 and 5). Otherwise run it after `cli.mjs login`. Run sequentially. Handle `usage_limit` by stopping and resuming later, and `temporarily_unavailable` by backing off. Commit the generated JSON, not the credentials.
