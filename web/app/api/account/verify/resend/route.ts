export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, requireUser, sendVerification } from "@/lib/server/community";
import { baseUrl } from "@/lib/server/email";

/** Sends the confirmation link again to the signed-in member. */
export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "verify-resend", 3);
    const u = await requireUser();
    await sendVerification(u, baseUrl(req));
    return Response.json({ ok: true });
  } catch (e) {
    return jsonError(e);
  }
}
