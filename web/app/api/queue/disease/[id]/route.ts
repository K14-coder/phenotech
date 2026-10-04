export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError } from "@/lib/server/community";
import { diseaseResearch } from "@/lib/server/queue";

/** Public: accepted community-researched claims for one disease (shown on /d/<id>). */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const clean = decodeURIComponent(id).trim();
    if (!/^(MONDO|OMIM|ORPHA):\d{1,9}$/.test(clean)) return Response.json({ error: "Unknown disease id." }, { status: 400 });
    return Response.json(await diseaseResearch(clean), { headers: { "Cache-Control": "public, max-age=30" } });
  } catch (e) {
    return jsonError(e);
  }
}
