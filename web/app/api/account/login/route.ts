export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, login, rateLimit, readBody, requireStore } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "login", 10);
    return Response.json({ user: await login(await readBody(req)) });
  } catch (e) {
    return jsonError(e);
  }
}
