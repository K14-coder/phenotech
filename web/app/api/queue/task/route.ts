export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError } from "@/lib/server/community";
import { myTask, volunteer } from "@/lib/server/queue";

/** The task packet of the lease you hold, if any (to resume after a reload). */
export async function GET(req: Request) {
  try {
    const v = await volunteer(req, { write: false });
    return Response.json({ packet: await myTask(v) }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
