// Server-only loader for pipeline/contribute/contribute.mjs (the "contribute what you know" backend).
// Loaded at runtime outside the bundler, exactly like integrations/openai/llm.mjs.
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = process.env.SIWC_PROJECT_ROOT ?? path.resolve(process.cwd(), "..");

export interface ContributeModule {
  preview(req: { url: unknown; diseaseId?: unknown; items?: unknown }, options?: Record<string, unknown>): Promise<Record<string, unknown>>;
  commit(preview: unknown, options?: Record<string, unknown>): Promise<Record<string, unknown>>;
  toHttpError(error: unknown): { status: number; error: { code: string; message: string; [k: string]: unknown } };
}

let loaded: Promise<ContributeModule> | null = null;

export function loadContribute(): Promise<ContributeModule> {
  if (!loaded) {
    const url = pathToFileURL(path.join(ROOT, "pipeline", "contribute", "contribute.mjs")).href;
    loaded = import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url).then((m) => m as ContributeModule);
    loaded.catch(() => {
      loaded = null;
    });
  }
  return loaded;
}

/**
 * Optional server-side overrides for testing against scratch copies (never read from the request):
 * CONTRIBUTE_RAW_DIR, CONTRIBUTE_FRAGMENT_PATH, CONTRIBUTE_GRAPH_PATH, CONTRIBUTE_REBUILD=0.
 */
export function pathOptions(): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  if (process.env.CONTRIBUTE_RAW_DIR) o.rawDir = process.env.CONTRIBUTE_RAW_DIR;
  if (process.env.CONTRIBUTE_FRAGMENT_PATH) o.fragmentPath = process.env.CONTRIBUTE_FRAGMENT_PATH;
  if (process.env.CONTRIBUTE_GRAPH_PATH) o.graphPath = process.env.CONTRIBUTE_GRAPH_PATH;
  if (process.env.CONTRIBUTE_REBUILD === "0") o.rebuild = false;
  return o;
}

/** Read a JSON body with a size cap (the commit body carries the whole preview). */
export async function readJsonBody(req: Request, max = 4_000_000): Promise<{ ok: true; body: Record<string, unknown> } | { ok: false; response: Response }> {
  const raw = await req.text();
  if (raw.length > max) return { ok: false, response: Response.json({ error: { code: "too_large", message: "Request too large." } }, { status: 413 }) };
  try {
    const body = JSON.parse(raw);
    if (!body || typeof body !== "object") throw new Error("not an object");
    return { ok: true, body };
  } catch {
    return { ok: false, response: Response.json({ error: { code: "invalid_request", message: "Send a JSON object." } }, { status: 400 }) };
  }
}
