export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError, rateLimit } from "@/lib/server/community";
import { createWorkerToken, revokeWorkerTokens, volunteer } from "@/lib/server/queue";

/** Create a worker token for the local ChatGPT worker (shown once; valid 30 days). Session only. */
export async function POST(req: Request) {
  try {
    await rateLimit(req, "queue-token", 10);
    const v = await volunteer(req, { write: true });
    return Response.json(await createWorkerToken(v), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}

/** Revoke all of your worker tokens. */
export async function DELETE(req: Request) {
  try {
    const v = await volunteer(req, { write: true });
    if (v.via !== "session") return Response.json({ error: "Revoke tokens from the website." }, { status: 403 });
    return Response.json({ revoked: await revokeWorkerTokens(v) });
  } catch (e) {
    return jsonError(e);
  }
}
