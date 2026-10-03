import { guardLocal, liveAIEnabled, notFound } from "@/lib/server/openai-local";
import { loadContribute, pathOptions, readJsonBody } from "@/lib/server/contribute-local";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST { url, diseaseId?, contributor?, items? } -> preview() from pipeline/contribute.
 * Local only: it fetches pages (Bright Data fallback), may call OpenAI, and writes the page cache.
 * `items` is the hand-entered mode (no AI): verified exactly like model output.
 */
export async function POST(req: Request) {
  if (!liveAIEnabled()) return notFound();
  const denied = guardLocal(req, { write: true });
  if (denied) return denied;
  const parsed = await readJsonBody(req, 400_000);
  if (!parsed.ok) return parsed.response;
  const { url, diseaseId, contributor, items } = parsed.body as { url?: unknown; diseaseId?: unknown; contributor?: unknown; items?: unknown };
  const mod = await loadContribute();
  try {
    const result = await mod.preview(
      { url, diseaseId: typeof diseaseId === "string" && diseaseId ? diseaseId : null, ...(Array.isArray(items) && items.length ? { items } : {}) },
      { contributor: typeof contributor === "string" ? contributor : undefined, ...pathOptions() },
    );
    return Response.json(result, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const { status, error } = mod.toHttpError(e);
    return Response.json({ error }, { status });
  }
}
