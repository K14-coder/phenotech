export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

import { jsonError, rateLimit } from "@/lib/server/community";
import { claim, volunteer } from "@/lib/server/queue";

/** Claim the next disease (or get back the one you already hold). Returns the task packet. */
export async function POST(req: Request) {
  try {
    await rateLimit(req, "queue-claim", 30);
    const v = await volunteer(req, { write: true });
    const out = await claim(v);
    if (!out.packet) return Response.json({ empty: true, message: "The queue is empty right now. Thank you!" });
    return Response.json({ packet: out.packet, resumed: out.resumed }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
