export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, readBody, requireStore, resetPassword } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "reset", 10);
    return Response.json(await resetPassword(await readBody(req)));
  } catch (e) {
    return jsonError(e);
  }
}
