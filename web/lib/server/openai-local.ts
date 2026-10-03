// Server-only helpers for the local OpenAI integration (integrations/openai/).
// Imported only by app/api/ai/* route handlers. Nothing here ever returns a token.
import path from "node:path";
import { pathToFileURL } from "node:url";

/** Repo root (web/ -> ..). Override with SIWC_PROJECT_ROOT. */
const ROOT = process.env.SIWC_PROJECT_ROOT ?? path.resolve(process.cwd(), "..");

/** Live AI runs only on the user's own machine. Vercel (VERCEL=1) is precomputed-only. */
export const liveAIEnabled = () => !process.env.VERCEL && process.env.AI_MODE !== "precomputed";

// ---------- integration module types (the .mjs files have no .d.ts) ----------

export interface DescribedError {
  kind: string;
  message: string;
  action?: { label: string; url?: string; command?: string };
  retryable?: boolean;
}

export interface DescribeAuth {
  path: "chatgpt" | "api_key" | null;
  mode: string;
  apiKeyConfigured: boolean;
  model: string;
  chatgpt: {
    signedIn: boolean;
    planUsage: boolean;
    email: string | null;
    accountStatus: string | null;
    planUsageFirstEnabledAt: string | null;
    error?: string;
  };
  manageUsageUrl: string;
}

export interface CompleteResult {
  text: string;
  json?: unknown;
  model: string;
  authPath: "chatgpt" | "api_key";
  structuredMode: null | "json_schema" | "prompted";
  requestId: string | null;
}

export interface LlmModuleLike {
  complete(options: {
    instructions?: string;
    input: string;
    schema?: object;
    schemaName?: string;
    signal?: AbortSignal;
    timeoutMs?: number;
    onDelta?: (delta: string) => void;
  }): Promise<CompleteResult>;
  describeAuth(): Promise<DescribeAuth>;
  describeError(error: unknown): DescribedError;
  listModels(): Promise<{ slug: string; displayName: string }[]>;
}
type LlmModule = LlmModuleLike;

interface LoginAttempt {
  authorizeUrl: string;
  completion: Promise<{ planUsage: boolean; firstPlanUsageSignIn: boolean; email: string | null }>;
}

interface SiwcModule {
  beginLogin(options?: { reconsent?: boolean }): Promise<LoginAttempt>;
  openInBrowser(url: string): Promise<void>;
  logout(): Promise<{ signedOut: boolean; revoked: boolean; message: string }>;
}

let loaded: Promise<{ llm: LlmModule; siwc: SiwcModule }> | null = null;

/**
 * Loads llm.mjs / siwc.mjs at runtime from their real location, skipping the bundler, so their
 * import.meta.url (used to find <repo>/.secrets/) resolves to the real files. Node's module cache
 * makes this one shared instance per server process.
 */
export function loadOpenAI(): Promise<{ llm: LlmModule; siwc: SiwcModule }> {
  if (!loaded) {
    const url = (file: string) => pathToFileURL(path.join(ROOT, "integrations", "openai", file)).href;
    loaded = Promise.all([
      import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url("llm.mjs")),
      import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url("siwc.mjs")),
    ]).then(([llm, siwc]) => ({ llm: llm as LlmModule, siwc: siwc as SiwcModule }));
    loaded.catch(() => {
      loaded = null;
    });
  }
  return loaded;
}

// ---------- request guard ----------

const LOOPBACK_HOST = /^(127\.0\.0\.1|localhost|\[::1\])$/;

function deny(message: string, status = 403) {
  return Response.json({ error: { kind: "forbidden", message } }, { status });
}

/**
 * Serve AI routes only to this machine's own pages:
 * - Host must be a loopback name on the app's port (blocks LAN access and DNS rebinding),
 * - Origin must be same-origin (required on writes), Sec-Fetch-Site same-origin when present,
 * - writes must be JSON (a cross-site form post can't send that without a CORS preflight we never answer).
 * Returns a Response to send back when the request is rejected, or null when it may proceed.
 */
export function guardLocal(req: Request, { write }: { write: boolean }): Response | null {
  const host = (req.headers.get("host") ?? "").toLowerCase();
  const m = /^(\[[^\]]+\]|[^:]+)(?::(\d+))?$/.exec(host);
  const port = process.env.PORT ?? "3000";
  if (!m || !LOOPBACK_HOST.test(m[1]) || (m[2] ?? "80") !== port) return deny("AI routes only answer on this computer.");
  const origin = req.headers.get("origin");
  const expected = `http://${host}`;
  if (write ? origin !== expected : origin !== null && origin !== expected) return deny("Cross-origin request refused.");
  const site = req.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return deny("Cross-site request refused.");
  if (write && !(req.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    return deny("Send application/json.", 415);
  }
  return null;
}

export const notFound = () => Response.json({ mode: "precomputed", error: { kind: "not_found", message: "Live AI is disabled here." } }, { status: 404 });

// ---------- login attempt state (shared across route modules via globalThis) ----------

export interface LoginState {
  status: "idle" | "pending" | "done" | "failed";
  authorizeUrl?: string;
  startedAt?: number;
  error?: { kind: string; message: string };
}

const store = globalThis as unknown as { __atlasLogin?: LoginState };
export const getLoginState = (): LoginState => store.__atlasLogin ?? { status: "idle" };
export const setLoginState = (s: LoginState) => {
  store.__atlasLogin = s;
};

/** HTTP status for a described error from complete(). */
export function statusForError(kind: string): number {
  if (["no_llm_available", "login_required", "plan_usage_not_granted", "auth"].includes(kind)) return 401;
  if (kind === "credits_exhausted") return 402;
  if (kind === "usage_limit" || kind === "rate_limited") return 429;
  if (kind === "not_eligible" || kind === "policy_or_region" || kind === "not_authorized") return 403;
  if (kind === "temporarily_unavailable") return 503;
  return 502;
}
