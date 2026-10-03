import { AI_DOC_SCHEMA, buildTask, sanitizeDoc, type AiTask } from "@/lib/ai-tasks";
import { BILLING_URL, type AiDocFile, type AiErrorInfo } from "@/lib/ai-shared";
import { guardLocal, liveAIEnabled, loadOpenAI, notFound, statusForError, type LlmModuleLike } from "@/lib/server/openai-local";
import { serverGraph } from "@/lib/server/graph-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST {kind, payload}. payload is a target, not evidence: {id} for "proposal",
 * {from, to, includeHypotheses?} for "explain-path". The prompt context is rebuilt here from
 * public/data/graph.json, and the model's citations are validated against it.
 *
 * With `Accept: application/x-ndjson` the response streams real progress events:
 *   {type:"phase", phase:"collect", connections} -> {type:"phase", phase:"draft", model}
 *   -> {type:"progress", chars, sentences}* -> {type:"phase", phase:"check"} -> {type:"result", data} | {type:"error", error}
 * Otherwise it returns the finished JSON document (used by scripts/precompute-ai.mjs).
 */
export async function POST(req: Request) {
  if (!liveAIEnabled()) return notFound();
  const denied = guardLocal(req, { write: true });
  if (denied) return denied;

  const raw = await req.text();
  if (raw.length > 4000) return bad("Request too large.", 413);
  let body: { kind?: unknown; payload?: unknown };
  try {
    body = JSON.parse(raw);
  } catch {
    return bad("Invalid JSON.", 400);
  }
  if (typeof body.kind !== "string") return bad("kind is required.", 400);

  const idx = await serverGraph();
  const built = buildTask(idx, body.kind, body.payload);
  if ("error" in built) return bad(built.error, built.status);
  const { task } = built;
  const { llm } = await loadOpenAI();

  if (!(req.headers.get("accept") ?? "").includes("application/x-ndjson")) {
    try {
      return Response.json(await run(llm, task, req.signal), { headers: { "cache-control": "no-store" } });
    } catch (error) {
      const info = errorInfo(llm.describeError(error), error);
      return Response.json({ error: info }, { status: statusForError(info.kind) });
    }
  }

  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (o: unknown) => {
        try {
          controller.enqueue(enc.encode(`${JSON.stringify(o)}\n`));
        } catch {
          // client went away
        }
      };
      try {
        send({ type: "phase", phase: "collect", connections: task.refs.size });
        send({ type: "phase", phase: "draft", model: await predictModel(llm) });
        let text = "";
        let last = 0;
        const data = await run(llm, task, req.signal, (delta) => {
          text += delta;
          const now = Date.now();
          if (now - last > 350) {
            last = now;
            send({ type: "progress", chars: text.length, sentences: (text.match(/"text"\s*:/g) ?? []).length });
          }
        }, () => send({ type: "phase", phase: "check" }));
        send({ type: "result", data });
      } catch (error) {
        const info = errorInfo(llm.describeError(error), error);
        send({ type: "error", error: info, status: statusForError(info.kind) });
      } finally {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    headers: { "content-type": "application/x-ndjson; charset=utf-8", "cache-control": "no-store", "x-accel-buffering": "no" },
  });
}

async function run(llm: LlmModuleLike, task: AiTask, signal: AbortSignal, onDelta?: (d: string) => void, onCheck?: () => void): Promise<AiDocFile> {
  const out = await llm.complete({
    instructions: task.instructions,
    input: task.input,
    schema: AI_DOC_SCHEMA,
    schemaName: "atlas_doc",
    signal,
    onDelta,
  });
  onCheck?.();
  const { doc, dropped } = sanitizeDoc(out.json, task.refs);
  return {
    kind: task.kind,
    id: task.id,
    ...doc,
    model: out.model,
    generated_at: new Date().toISOString(),
    auth_path: out.authPath,
    structured_mode: out.structuredMode,
    dropped_citations: dropped,
  };
}

/** The model complete() will pick (mirrors llm.mjs chooseModel), as a display name. */
async function predictModel(llm: LlmModuleLike): Promise<string> {
  const pretty = (slug: string) =>
    slug
      .split("-")
      .map((p) => (/^gpt$/i.test(p) ? "GPT" : p.charAt(0).toUpperCase() + p.slice(1)))
      .join("-");
  if (process.env.OPENAI_MODEL) return pretty(process.env.OPENAI_MODEL);
  try {
    const auth = await llm.describeAuth();
    if (auth.path === "chatgpt") {
      const models = await llm.listModels();
      const pick = models.find((m) => m.slug === auth.model) ?? models[0];
      if (pick) return pick.displayName && pick.displayName !== pick.slug ? pick.displayName : pretty(pick.slug);
    }
    return pretty(auth.model);
  } catch {
    return "the OpenAI model";
  }
}

function bad(message: string, status: number) {
  return Response.json({ error: { kind: "invalid_request", message } satisfies AiErrorInfo }, { status });
}

/** Safe, UI-ready error (no tokens, no shell commands). Adds the API-credit case llm.mjs doesn't name. */
function errorInfo(d: { kind: string; message: string; action?: { label: string; url?: string }; retryable?: boolean }, error: unknown): AiErrorInfo {
  const e = (error ?? {}) as { code?: unknown; authPath?: unknown };
  const authPath = e.authPath === "chatgpt" || e.authPath === "api_key" ? e.authPath : null;
  if (e.code === "credit_balance_exhausted" || e.code === "insufficient_quota" || d.kind === "quota") {
    return {
      kind: "credits_exhausted",
      message: "The OpenAI API key has no credits left, so this request could not run. Add credits, or continue with your ChatGPT plan instead.",
      action: { label: "Manage billing", url: BILLING_URL },
      authPath,
    };
  }
  return {
    kind: d.kind,
    message: d.message,
    ...(d.action?.url ? { action: { label: d.action.label, url: d.action.url } } : {}),
    retryable: d.retryable,
    authPath,
  };
}
