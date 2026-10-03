# Agent report: OpenAI / Sign in with ChatGPT

Date: 2026-10-03. Scope: research and build only. Nothing outside `integrations/openai/`, `docs/openai-integration.md` and this file was touched.

## Outcome

- **Verdict: feasible for the local app, not for the hosted site.** OpenAI lets open-source and locally run apps use ChatGPT plan usage. Registration is self-serve at sign-in (`client_id=dynamic_agent_client`), with no secret, partner key or approval. The Vercel deployment counts as a remotely hosted app (waitlist only), so it should serve precomputed outputs only. Users need ChatGPT **Plus or Pro**; everyone else uses the `OPENAI_API_KEY` fallback.
- Full findings with links, risks and wiring instructions: `docs/openai-integration.md`.

## Files

- `integrations/openai/siwc.mjs`
  - Covers login (loopback listener on `127.0.0.1`, PKCE S256, state, nonce, persisted `ext_agent_host_id`, macOS `open`), the code exchange, RS256 ID-token verification against the JWKS, the `chatgpt.tokens.use.direct` check, auto-refresh with serialized rotation, revocation on logout, and a read-only `status()`.
  - Credentials go to `.secrets/openai-siwc.json` (directory 700, file 600).
- `integrations/openai/llm.mjs`
  - `complete({ instructions, input, schema?, model? })` uses the ChatGPT plan first, then `OPENAI_API_KEY`, else throws `NoLLMAvailableError`.
  - Calls the Responses API with `store:false` and `stream:true`.
  - JSON-schema structured output, with a prompted fallback if the plan route rejects `text.format`.
  - Typed errors with a UI `kind` (usage_limit, not_eligible, policy_or_region, …), and bounded retries for 503/5xx.
- `integrations/openai/cli.mjs` provides `login`, `status`, `test`, `models`, `refresh`, `logout`, and `url` (dry run).

## Decisions

- **Callback path is `/auth/callback`**, not the brief's `/callback`. It is the documented example and the devkit's value, and the docs require the path never to change for a registration. Port 1455 (the docs' example) is used, falling back to a free port; `--port` or `SIWC_PORT` overrides it.
- **Default model is `gpt-6.1-sol`**, the model in the SIWC docs. `OPENAI_MODEL` overrides it. On the ChatGPT path, if the account doesn't list it, the first listed model is used.
- **`id_token_hint` is not sent.** It is optional, and the URL becomes an argument to `open`, which other local users can read. `login_hint` (email) is sent on reauthorization.
- **No silent billing switch.** A temporary ChatGPT sign-in failure is thrown as is. The API-key fallback is used only when there is no usable sign-in or plan usage wasn't granted.
- **Written from the docs.** No code was copied from OpenAI's devkit, which has a noncommercial licence.

## Verification

- `node --check` passes on all three files. `cli.mjs status` and `cli.mjs url` were run in the repo; neither wrote anything (no `.secrets/` exists).
- 21 end-to-end checks passed against a mocked OpenAI, using real loopback HTTP and RSA-signed tokens. The test ran in a temporary directory, not in the repo.
- The CLI's `status`, `test`, `models` and `logout` output was checked against that mocked session.
- **Never signed in, never opened the authorize URL, never used or created an API key.**

## Open items

- **The user** runs `node integrations/openai/cli.mjs login`, then `test`. `test` shows whether the account gets native `json_schema` or the prompted fallback.
- **Web owner:** follow "How to wire into the app" in `docs/openai-integration.md`.
  - Run `next dev -H 127.0.0.1`.
  - Import the integration at runtime (bypassing the bundler) and add the loopback/same-origin guard.
  - Add the routes `status`, `login`, `logout` and a task route such as `claims`.
  - Put the UI states (Continue with ChatGPT, Using ChatGPT plan, Manage usage, usage-limit modal) in place.
  - On Vercel, show precomputed outputs only.
- **Pipeline owner:** prefer `OPENAI_AUTH=api_key` for the offline batch. A personal Plus plan has a five-hour shared limit, and using it to build published data is a grey area. Record `extracted_by: openai:<model>`.
