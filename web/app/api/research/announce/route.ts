export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { announce, assertSameOrigin, jsonError, rateLimit, readBody, requireUser } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "announce", 5);
    const u = await requireUser();
    return Response.json({ announcement: await announce(u, await readBody(req)) });
  } catch (e) {
    return jsonError(e);
  }
}
