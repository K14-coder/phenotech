export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { HttpError, assertSameOrigin, jsonError, rateLimit, requireAdmin, requireUser } from "@/lib/server/community";
import { sendEmail, testEmail } from "@/lib/server/email";

/**
 * Admin only: send a test email to the signed-in admin's OWN address (never to an address from the request).
 * Needs the ADMIN_TOKEN header and a signed-in, confirmed account. Reports the transport and a short result code.
 */
export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    requireAdmin(req);
    await rateLimit(req, "test-email", 5);
    const u = await requireUser();
    if (!u.emailVerified) throw new HttpError(400, "Confirm your own email address first, then try again.");
    const r = await sendEmail(testEmail(u.email));
    return Response.json({ transport: r.mode, sent: r.sent, error: r.error ?? null }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
