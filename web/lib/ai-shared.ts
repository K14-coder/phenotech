// Types and constants shared by the browser (lib/ai.ts, components/ai/*) and the AI routes.

export const MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage";
export const BILLING_URL = "https://platform.openai.com/settings/organization/billing/";

export interface AiSentence {
  text: string;
  /** graph edge ids this sentence relies on; empty = AI framing, no direct source */
  edge_ids: string[];
}

export interface AiDoc {
  title: string;
  sections: { heading: string; sentences: AiSentence[] }[];
}

/** What /api/ai/generate returns and what precomputed files contain. */
export interface AiDocFile extends AiDoc {
  kind: string;
  id: string;
  model: string;
  generated_at: string;
  auth_path?: "chatgpt" | "api_key";
  structured_mode?: string | null;
  dropped_citations?: number;
}

export interface AiErrorInfo {
  kind: string;
  message: string;
  action?: { label: string; url: string };
  retryable?: boolean;
  authPath?: "chatgpt" | "api_key" | null;
}

export interface AiStatusPayload {
  mode: "live" | "precomputed";
  /** true on Vercel or when AI_MODE=precomputed */
  liveDisabled: boolean;
  authPath: "chatgpt" | "api_key" | "none";
  signedIn: boolean;
  email: string | null;
  planUsage: boolean;
  planUsageFirstEnabledAt: string | null;
  apiKeyConfigured: boolean;
  model: string | null;
  manageUsageUrl: string;
  billingUrl: string;
  login: { status: "idle" | "pending" | "done" | "failed"; authorizeUrl?: string; error?: { kind: string; message: string } };
  error?: AiErrorInfo;
}

export const PRECOMPUTED_STATUS: AiStatusPayload = {
  mode: "precomputed",
  liveDisabled: true,
  authPath: "none",
  signedIn: false,
  email: null,
  planUsage: false,
  planUsageFirstEnabledAt: null,
  apiKeyConfigured: false,
  model: null,
  manageUsageUrl: MANAGE_USAGE_URL,
  billingUrl: BILLING_URL,
  login: { status: "idle" },
};

/** File name for precomputed output: `<kind>--<id>.json`, id with characters outside [A-Za-z0-9._-] as "_". */
export function aiFileName(kind: string, id: string): string {
  return `${kind}--${id.replace(/[^A-Za-z0-9._-]/g, "_")}.json`;
}

/** Id for a compare-questions output: "<a>__vs__<b>" in page order (a = your disease). */
export function compareAiId(a: string, b: string) {
  return `${a}__vs__${b}`;
}

/** Id for an explain-path output (and its precomputed file). */
export function pathAiId(from: string, to: string, includeHypotheses = false) {
  return `${from}__to__${to}${includeHypotheses ? "__hyp" : ""}`;
}
