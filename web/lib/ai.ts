// Browser-side AI entry points.
//
//   generate(kind, payload, { live })  -> Promise<AIResult>
//   loadPrecomputed(kind, payload)     -> Promise<AIResult | null>
//   aiStatus() / aiLogin() / aiLogout()
//
// kind: "proposal" (payload {id}) or "explain-path" (payload {from, to, includeHypotheses?}).
// Live calls go to /api/ai/generate (local dev server only; tokens stay on the server).
// Precomputed outputs live at public/data/ai/<kind>--<safe id>.json in the same shape:
//   { kind, id, title, sections: [{ heading, sentences: [{ text, edge_ids }] }], model, generated_at }
// Older files with a plain `text` field are still shown, as unstructured text.
import {
  PRECOMPUTED_STATUS,
  aiFileName,
  compareAiId,
  pathAiId,
  type AiDoc,
  type AiDocFile,
  type AiErrorInfo,
  type AiStatusPayload,
} from "./ai-shared";

export { aiFileName, compareAiId, pathAiId } from "./ai-shared";
export type { AiDoc, AiErrorInfo, AiStatusPayload } from "./ai-shared";

export type AIStatus = "ok" | "not_connected" | "error";

export interface AIResult {
  status: AIStatus;
  source: "live" | "precomputed" | "none";
  doc?: AiDoc;
  /** legacy unstructured text (precomputed files without sections) */
  text?: string;
  model?: string;
  generatedAt?: string;
  authPath?: "chatgpt" | "api_key";
  error?: AiErrorInfo;
}

/** The id an output is stored under, for a given kind and payload. */
export function aiTargetId(kind: string, payload: unknown): string | undefined {
  const p = (payload ?? {}) as { id?: unknown; from?: unknown; to?: unknown; includeHypotheses?: unknown; a?: unknown; b?: unknown };
  if (kind === "compare-questions") {
    return typeof p.a === "string" && typeof p.b === "string" ? compareAiId(p.a, p.b) : undefined;
  }
  if (kind === "explain-path") {
    return typeof p.from === "string" && typeof p.to === "string" ? pathAiId(p.from, p.to, p.includeHypotheses === true) : undefined;
  }
  return typeof p.id === "string" && p.id ? p.id : undefined;
}

function isDoc(d: unknown): d is AiDoc {
  return !!d && typeof d === "object" && Array.isArray((d as AiDoc).sections);
}

function fromFile(data: unknown, source: AIResult["source"]): AIResult | null {
  if (isDoc(data)) {
    const f = data as AiDocFile;
    return {
      status: "ok",
      source,
      doc: { title: typeof f.title === "string" ? f.title : "", sections: f.sections },
      model: typeof f.model === "string" ? f.model : undefined,
      generatedAt: typeof f.generated_at === "string" ? f.generated_at : undefined,
      authPath: f.auth_path,
    };
  }
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const text = [d.text, d.markdown, d.content, d.output_text].find((v): v is string => typeof v === "string" && !!v.trim());
    if (text) {
      return {
        status: "ok",
        source,
        text,
        model: typeof d.model === "string" ? d.model : undefined,
        generatedAt: typeof d.generated_at === "string" ? d.generated_at : undefined,
      };
    }
  }
  return null;
}

// public/data/ai/index.json (written by scripts/sync-data.mjs) lists the files that exist,
// so missing outputs are never fetched (no 404 noise in the console)
let available: Promise<Set<string>> | null = null;
function availableFiles(): Promise<Set<string>> {
  if (!available) {
    available = fetch("/data/ai/index.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : { files: [] }))
      .then((d: { files?: unknown }) => new Set(Array.isArray(d.files) ? d.files.filter((f): f is string => typeof f === "string") : []))
      .catch(() => new Set<string>());
  }
  return available;
}

/** True when a precomputed output exists for this kind and id. */
export async function hasPrecomputed(kind: string, id: string): Promise<boolean> {
  return (await availableFiles()).has(aiFileName(kind, id));
}

export async function loadPrecomputed(kind: string, payload: unknown): Promise<AIResult | null> {
  const id = aiTargetId(kind, payload);
  if (!id) return null;
  const listed = await availableFiles();
  const names = [...new Set([aiFileName(kind, id), `${kind}--${encodeURIComponent(id)}.json`])].filter((n) => listed.has(n));
  for (const name of names) {
    try {
      const r = await fetch(`/data/ai/${name}`, { cache: "no-cache" });
      if (!r.ok || !(r.headers.get("content-type") ?? "").includes("json")) continue;
      const res = fromFile(await r.json(), "precomputed");
      if (res) return res;
    } catch {
      // try the next name
    }
  }
  return null;
}

async function postJson(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}

/** Real progress from the server while a live draft is written. */
export type AiProgressEvent =
  | { type: "phase"; phase: "collect"; connections: number }
  | { type: "phase"; phase: "draft"; model: string }
  | { type: "phase"; phase: "check" }
  | { type: "progress"; chars: number; sentences: number };

async function readStream(r: Response, onEvent: (e: AiProgressEvent) => void): Promise<AIResult> {
  const reader = r.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let final: AIResult | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line) continue;
      let ev: { type?: string; data?: unknown; error?: AiErrorInfo };
      try {
        ev = JSON.parse(line);
      } catch {
        continue;
      }
      if (ev.type === "result") final = fromFile(ev.data, "live");
      else if (ev.type === "error" && ev.error) final = { status: "error", source: "live", error: ev.error };
      else onEvent(ev as AiProgressEvent);
    }
  }
  return final ?? { status: "error", source: "live", error: { kind: "stream_interrupted", message: "The AI response ended early. Try again.", retryable: true } };
}

export async function generateLive(kind: string, payload: unknown, onEvent?: (e: AiProgressEvent) => void): Promise<AIResult> {
  try {
    const r = await fetch("/api/ai/generate", {
      method: "POST",
      headers: { "content-type": "application/json", accept: onEvent ? "application/x-ndjson" : "application/json" },
      body: JSON.stringify({ kind, payload }),
      cache: "no-store",
    });
    if (onEvent && r.ok && r.body && (r.headers.get("content-type") ?? "").includes("ndjson")) return await readStream(r, onEvent);
    const data = (await r.json().catch(() => null)) as (AiDocFile & { error?: AiErrorInfo }) | null;
    if (r.ok && data) {
      const res = fromFile(data, "live");
      if (res) return res;
    }
    const error: AiErrorInfo = data?.error ?? {
      kind: r.status === 404 ? "live_disabled" : "error",
      message: r.status === 404 ? "Live AI is not available here. Showing precomputed results only." : `The AI request failed (HTTP ${r.status}).`,
    };
    return { status: "error", source: "live", error };
  } catch (err) {
    return {
      status: "error",
      source: "live",
      error: { kind: "network", message: `Could not reach the local AI service: ${err instanceof Error ? err.message : String(err)}`, retryable: true },
    };
  }
}

/**
 * Precomputed output first (instant, uses no one's plan), then a live call when `live` is true,
 * otherwise a clear "AI not connected" result.
 */
export async function generate(
  kind: string,
  payload: unknown,
  opts: { live?: boolean; preferLive?: boolean; onEvent?: (e: AiProgressEvent) => void } = {},
): Promise<AIResult> {
  if (!opts.preferLive) {
    const pre = await loadPrecomputed(kind, payload);
    if (pre) return pre;
  }
  if (opts.live) return generateLive(kind, payload, opts.onEvent);
  if (opts.preferLive) {
    const pre = await loadPrecomputed(kind, payload);
    if (pre) return pre;
  }
  return {
    status: "not_connected",
    source: "none",
    text: "AI not connected. Precomputed results only, and none exists for this yet. Nothing here was generated.",
  };
}

// ---------- auth state (local dev only) ----------

export async function aiStatus(): Promise<AiStatusPayload> {
  try {
    const r = await fetch("/api/ai/status", { cache: "no-store" });
    if (!r.ok && r.status !== 500) return PRECOMPUTED_STATUS;
    const data = (await r.json()) as AiStatusPayload;
    return data && typeof data === "object" && "mode" in data ? data : PRECOMPUTED_STATUS;
  } catch {
    return PRECOMPUTED_STATUS;
  }
}

export async function aiLogin(reconsent = false): Promise<{ authorizeUrl?: string; error?: AiErrorInfo }> {
  try {
    const r = await postJson("/api/ai/login", { reconsent });
    return (await r.json()) as { authorizeUrl?: string; error?: AiErrorInfo };
  } catch (err) {
    return { error: { kind: "network", message: err instanceof Error ? err.message : String(err) } };
  }
}

export async function aiLogout(): Promise<{ signedOut?: boolean; revoked?: boolean; message?: string; error?: AiErrorInfo }> {
  try {
    const r = await postJson("/api/ai/logout", {});
    return (await r.json()) as { signedOut?: boolean; revoked?: boolean; message?: string; error?: AiErrorInfo };
  } catch (err) {
    return { error: { kind: "network", message: err instanceof Error ? err.message : String(err) } };
  }
}
