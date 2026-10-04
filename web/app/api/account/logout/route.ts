export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, clearSession, jsonError } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    await clearSession();
    return Response.json({ ok: true });
  } catch (e) {
    return jsonError(e);
  }
}
