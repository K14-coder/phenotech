export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, readBody, requestContact, requireUser } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "contact", 3);
    const u = await requireUser();
    return Response.json(await requestContact(u, await readBody(req)));
  } catch (e) {
    return jsonError(e);
  }
}
