export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

import { jsonError, readBody } from "@/lib/server/community";
import { submit, volunteer } from "@/lib/server/queue";

/** Submit extracted claims for the disease you hold. Every claim is verified server-side. */
export async function POST(req: Request) {
  try {
    const v = await volunteer(req, { write: true });
    return Response.json(await submit(v, await readBody(req, 400_000)), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
