import { guardLocal, liveAIEnabled, notFound } from "@/lib/server/openai-local";
import { loadContribute, pathOptions, readJsonBody } from "@/lib/server/contribute-local";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST { preview, contributor?, include? } -> commit() from pipeline/contribute.
 * The backend recomputes everything from its own cache (a tampered preview can't inject quotes),
 * writes data/curated/contributions.json, rebuilds data/graph.json and re-syncs web/public/data.
 */
export async function POST(req: Request) {
  if (!liveAIEnabled()) return notFound();
  const denied = guardLocal(req, { write: true });
  if (denied) return denied;
  const parsed = await readJsonBody(req);
  if (!parsed.ok) return parsed.response;
  const { preview, contributor, include } = parsed.body as { preview?: unknown; contributor?: unknown; include?: unknown };
  const mod = await loadContribute();
  try {
    const result = await mod.commit(preview, {
      contributor: typeof contributor === "string" ? contributor : undefined,
      include: Array.isArray(include) ? include : undefined,
      ...pathOptions(),
    });
    return Response.json(result, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const { status, error } = mod.toHttpError(e);
    return Response.json({ error }, { status });
  }
}
