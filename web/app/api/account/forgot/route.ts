export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, forgotPassword, jsonError, rateLimit, readBody, requireStore } from "@/lib/server/community";
import { baseUrl } from "@/lib/server/email";

/** Emails a one-hour, single-use reset link. Answers the same whether or not the address has an account. */
export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "forgot", 5);
    return Response.json(await forgotPassword(await readBody(req), baseUrl(req)));
  } catch (e) {
    return jsonError(e);
  }
}
