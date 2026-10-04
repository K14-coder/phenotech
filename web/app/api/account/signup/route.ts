export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { baseUrl } from "@/lib/server/email";
import { assertSameOrigin, jsonError, rateLimit, readBody, requireStore, signup } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "signup", 5);
    return Response.json(await signup(await readBody(req), baseUrl(req)));
  } catch (e) {
    return jsonError(e);
  }
}
