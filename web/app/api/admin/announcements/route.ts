export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { HttpError, assertSameOrigin, jsonError, moderate, pendingAnnouncements, readBody, requireAdmin, requireStore } from "@/lib/server/community";

/** Moderation queue, protected by the ADMIN_TOKEN env var (sent as x-admin-token). */
export async function GET(req: Request) {
  try {
    requireStore();
    requireAdmin(req);
    return Response.json({ pending: await pendingAnnouncements() }, { headers: { "Cache-Control": "no-store" } });
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
    const id = typeof body.id === "string" ? body.id : "";
    const decision = body.decision === "approved" || body.decision === "rejected" ? body.decision : null;
    if (!id || !decision) throw new HttpError(400, "id and decision are required.");
    await moderate(id, decision);
    return Response.json({ ok: true });
  } catch (e) {
    return jsonError(e);
  }
}
