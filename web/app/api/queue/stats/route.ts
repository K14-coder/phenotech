export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { HttpError, jsonError } from "@/lib/server/community";
import { stats, volunteer, type Volunteer } from "@/lib/server/queue";

/** Public queue statistics, the next 20 diseases and the leaderboard (handles only); plus "me" when signed in. */
export async function GET(req: Request) {
  try {
    let v: Volunteer | null = null;
    try {
      v = await volunteer(req, { write: false });
    } catch (e) {
      if (!(e instanceof HttpError) || e.status !== 401) throw e;
    }
    return Response.json(await stats(v), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
