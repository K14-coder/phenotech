// Browser side of the research queue: API calls, the direct OpenAI call (bring your own key) and cost estimates.
// The OpenAI key never goes to the atlas server: callOpenAI() talks to api.openai.com directly
// (api.openai.com answers CORS preflights with Access-Control-Allow-Origin: *, checked 2026-10-04).
import type { CoverageItem, Packet, Rejection, StoredClaim, StoredGroup } from "@/lib/server/queue";

export type { CoverageItem, Packet, Rejection, StoredClaim, StoredGroup };

export interface QueueStats {
  total: number;
  inQueue: number;
  leasedNow: number;
  completed: number;
  retired: number;
  claimsVerified: number;
  groupsVerified: number;
  rejected: number;
  submissions: number;
  volunteers: number;
  byProvider: { provider: string; accepted: number; rejected: number }[];
  next: { id: string; name: string; genes: string[]; returning: boolean; round: number; gaps: string[] | null; why: string[] }[];
  leaderboard: { handle: string; verified: number }[];
  recentlyCompleted: { id: string; name: string; at: string }[];
  me: { handle: string; accepted: number; rejected: number; duplicates: number; tasks: number; lease: { diseaseId: string; name: string; expiresAt: string } | null } | null;
  leaseHours: number;
  maxRounds: number;
  checklist: { id: string; label: string; need: number; unit: string }[];
  statusLabel: string;
}

export interface SubmitResult {
  accepted: number;
  acceptedGroups: number;
  duplicates: number;
  rejected: Rejection[];
  checklist: CoverageItem[];
  missing: string[];
  complete: boolean;
}

export interface DiseaseResearch {
  id: string;
  inQueue: boolean;
  status: string | null;
  claims: StoredClaim[];
  groups: StoredGroup[];
  checklist: CoverageItem[];
  rounds: number;
  statusLabel: string;
}

export async function qapi<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal,
  });
  const j = (await r.json().catch(() => ({}))) as T & { error?: string };
  if (!r.ok) throw Object.assign(new Error(j.error ?? `Request failed (${r.status})`), { status: r.status });
  return j;
}

export const SHORT: Record<string, string> = {
  mechanism: "Mechanism",
  process: "Biological process",
  therapies: "Therapies",
  phenotypes: "Phenotypes",
  natural_history: "Natural history",
  research_groups: "Research groups",
};

/** The model's user message for one batch of abstracts (same text as the local worker sends). */
export function batchTexts(p: Packet): string[] {
  const d = p.disease;
  const missing = p.checklist.filter((c) => !c.done);
  const head = [
    `Disease: ${d.name}${d.synonyms.length ? ` (also called: ${d.synonyms.join("; ")})` : ""}`,
    `Genes: ${d.genes.join(", ") || "none recorded"}`,
    `Identifiers: ${[d.mondo, ...d.omim.map((o) => `OMIM:${o}`), ...d.orpha.map((o) => `ORPHA:${o}`)].filter(Boolean).join(", ")}`,
    `Already in the atlas: curated mechanism classes: ${p.known.mechanismClasses.join(", ") || "none"}; DisMech mechanism chain: ${p.known.dismech ? "yes" : "no"}.`,
    missing.length
      ? `Still missing (focus here first): ${missing.map((c) => `${c.label} (have ${c.have} of ${c.need} ${c.unit})`).join("; ")}.`
      : "The checklist is complete; add any further solid claims.",
    "",
    "Records:",
  ].join("\n");
  const out: string[] = [];
  for (let i = 0; i < p.abstracts.length; i += p.batchSize) {
    const recs = p.abstracts.slice(i, i + p.batchSize).map((a) =>
      [
        `PMID: ${a.pmid}`,
        `Title: ${a.title}`,
        `Abstract: ${a.abstract}`,
        `Senior authors: ${a.senior_authors.map((s) => `${s.name} — ${s.affiliation || "(no affiliation listed)"}`).join("; ") || "(none listed)"}`,
      ].join("\n"),
    );
    out.push(`${head}\n\n${recs.join("\n\n")}`);
  }
  return out;
}

/** Rough token estimate: about 4 characters per token for English text. */
export function estimateTokens(p: Packet): { input: number; output: number; calls: number } {
  const batches = batchTexts(p);
  const input = batches.reduce((s, b) => s + Math.ceil((b.length + p.instructions.length + JSON.stringify(p.schema).length) / 4), 0);
  return { input, output: batches.length * 1800, calls: batches.length };
}

/** A typical task when no packet is loaded yet: 15 abstracts in 3 calls. */
export const TYPICAL_TASK = { input: 3 * 4800, output: 3 * 1800, calls: 3 };

export class OpenAIError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

export interface ModelOutput {
  claims: unknown[];
  research_groups: unknown[];
  model: string;
  usage: { input_tokens?: number; output_tokens?: number } | null;
}

/** One structured-output call straight from the browser to OpenAI with the volunteer's own key. */
export async function callOpenAI(key: string, model: string, p: Packet, input: string, signal?: AbortSignal): Promise<ModelOutput> {
  let r: Response;
  try {
    r = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        instructions: p.instructions,
        input: [{ role: "user", content: input }],
        text: { format: { type: "json_schema", name: "claims", schema: p.schema, strict: true } },
        store: false,
      }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new OpenAIError("Could not reach api.openai.com from this browser (network, an extension or a firewall). Try the local worker instead.", 0);
  }
  const j = (await r.json().catch(() => ({}))) as {
    error?: { message?: string; code?: string };
    model?: string;
    output?: { type?: string; content?: { type?: string; text?: string; refusal?: string }[] }[];
    usage?: { input_tokens?: number; output_tokens?: number };
    status?: string;
  };
  if (!r.ok) throw new OpenAIError(j.error?.message ?? `OpenAI returned HTTP ${r.status}`, r.status, j.error?.code);
  let text = "";
  let refusal = "";
  for (const item of j.output ?? []) {
    if (item.type !== "message") continue;
    for (const c of item.content ?? []) {
      if (c.type === "output_text" && c.text) text += c.text;
      if (c.type === "refusal" && c.refusal) refusal += c.refusal;
    }
  }
  if (!text) throw new OpenAIError(refusal ? `The model refused: ${refusal.slice(0, 200)}` : `The model returned no text (status ${j.status ?? "unknown"}).`, 200);
  let parsed: { claims?: unknown; research_groups?: unknown };
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new OpenAIError("The model did not return valid JSON.", 200);
  }
  return {
    claims: Array.isArray(parsed.claims) ? parsed.claims : [],
    research_groups: Array.isArray(parsed.research_groups) ? parsed.research_groups : [],
    model: j.model ?? model,
    usage: j.usage ?? null,
  };
}

/**
 * One call straight from the browser to Anthropic with the volunteer's own key. Strict JSON through tool use:
 * the model must call submit_claims, whose input_schema is the packet's claim schema (the server re-validates).
 */
export async function callAnthropic(key: string, model: string, p: Packet, input: string, signal?: AbortSignal): Promise<ModelOutput> {
  let r: Response;
  try {
    r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model,
        max_tokens: 8000,
        system: p.instructions,
        tools: [{ name: "submit_claims", description: "Submit the extracted claims and research groups.", input_schema: p.schema }],
        tool_choice: { type: "tool", name: "submit_claims" },
        messages: [{ role: "user", content: input }],
      }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new OpenAIError("Could not reach api.anthropic.com from this browser (network, an extension or a firewall). Try the local worker instead.", 0);
  }
  const j = (await r.json().catch(() => ({}))) as {
    error?: { message?: string; type?: string };
    model?: string;
    content?: { type: string; name?: string; input?: { claims?: unknown; research_groups?: unknown } }[];
    usage?: { input_tokens?: number; output_tokens?: number };
    stop_reason?: string;
  };
  if (!r.ok) throw new OpenAIError(j.error?.message ?? `Anthropic returned HTTP ${r.status}`, r.status, j.error?.type);
  const call = (j.content ?? []).find((c) => c.type === "tool_use" && c.name === "submit_claims");
  if (!call?.input) throw new OpenAIError(`The model returned no tool call (stop reason ${j.stop_reason ?? "unknown"}).`, 200);
  return {
    claims: Array.isArray(call.input.claims) ? call.input.claims : [],
    research_groups: Array.isArray(call.input.research_groups) ? call.input.research_groups : [],
    model: j.model ?? model,
    usage: j.usage ?? null,
  };
}

export async function listOpenAIModels(key: string): Promise<string[]> {
  const r = await fetch("https://api.openai.com/v1/models", { headers: { Authorization: `Bearer ${key}` } });
  const j = (await r.json().catch(() => ({}))) as { data?: { id: string }[]; error?: { message?: string } };
  if (!r.ok) throw new OpenAIError(j.error?.message ?? `OpenAI returned HTTP ${r.status}`, r.status);
  return (j.data ?? [])
    .map((m) => m.id)
    .filter((id) => /^(gpt|o\d)/.test(id) && !/audio|realtime|transcribe|tts|image|search|embedding/.test(id))
    .sort();
}

export const fmtInt = (n: number) => n.toLocaleString("en-US");
