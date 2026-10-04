export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { assertSameOrigin, jsonError, rateLimit, readBody, requireStore } from "@/lib/server/community";
import { fileReport } from "@/lib/server/reports";

/** Public: report a wrong contact or ask for one to be removed. Goes to the admin moderation queue. */
export async function POST(req: Request) {
  try {
    requireStore();
    assertSameOrigin(req);
    await rateLimit(req, "contact-report", 5);
    return Response.json(await fileReport(await readBody(req)));
  } catch (e) {
    return jsonError(e);
  }
}
