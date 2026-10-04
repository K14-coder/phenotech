export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError, readBody } from "@/lib/server/community";
import { done, volunteer } from "@/lib/server/queue";

/** "I'm done": end your lease now. Coverage is computed and the disease is completed, requeued or retired. */
export async function POST(req: Request) {
  try {
    const v = await volunteer(req, { write: true });
    return Response.json(await done(v, await readBody(req)), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
