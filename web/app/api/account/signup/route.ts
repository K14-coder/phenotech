export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, readBody, requireStore, signup } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "signup", 5);
    return Response.json({ user: await signup(await readBody(req)) });
  } catch (e) {
    return jsonError(e);
  }
}
