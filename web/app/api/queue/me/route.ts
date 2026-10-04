export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError, rateLimit, readBody } from "@/lib/server/community";
import { setHandle, volunteer } from "@/lib/server/queue";

/** Choose the public handle shown on the leaderboard and next to your verified claims. */
export async function POST(req: Request) {
  try {
    await rateLimit(req, "queue-handle", 10);
    const v = await volunteer(req, { write: true });
    if (v.via !== "session") return Response.json({ error: "Change your handle on the website." }, { status: 403 });
    const body = await readBody(req);
    return Response.json({ handle: await setHandle(v.uid, body.handle) });
  } catch (e) {
    return jsonError(e);
  }
}
