export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, communityInterest, jsonError, rateLimit, readBody, requireUser } from "@/lib/server/community";

export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "interest", 30);
    const u = await requireUser();
    const body = await readBody(req);
    const diseases = Array.isArray(body.diseases) ? body.diseases.filter((x): x is string => typeof x === "string") : [];
    return Response.json({ interest: await communityInterest(u, diseases) });
  } catch (e) {
    return jsonError(e);
  }
}
