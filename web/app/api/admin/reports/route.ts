export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { HttpError, assertSameOrigin, jsonError, readBody, requireAdmin, requireStore } from "@/lib/server/community";
import { pendingReports, resolveReport } from "@/lib/server/reports";

/** Contact reports waiting for review (ADMIN_TOKEN). */
export async function GET(req: Request) {
  try {
    requireStore();
    requireAdmin(req);
    return Response.json({ reports: await pendingReports() }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}

export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    requireAdmin(req);
    const body = await readBody(req);
    if (typeof body.id !== "string" || !body.id) throw new HttpError(400, "id is required.");
    await resolveReport(body.id);
    return Response.json({ ok: true });
  } catch (e) {
    return jsonError(e);
  }
}
