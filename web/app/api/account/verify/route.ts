export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, readBody, requireStore, verifyEmail } from "@/lib/server/community";

/** Confirms an email address from the signed link (the /verify page posts the token here). */
export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "verify", 20);
    const body = await readBody(req);
    return Response.json(await verifyEmail(body.token));
  } catch (e) {
    return jsonError(e);
  }
}
