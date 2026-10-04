export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

import { timingSafeEqual } from "node:crypto";
import { jsonError } from "@/lib/server/community";
import { reconcile, sweepExpired } from "@/lib/server/queue";

function authorised(req: Request): boolean {
  const secret = process.env.CRON_SECRET ?? "";
  const got = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (secret.length < 16 || !got) return false;
  const a = Buffer.from(secret);
  const b = Buffer.from(got);
  return a.length === b.length && timingSafeEqual(a, b);
}

/** Finalise expired leases (Vercel Cron sends GET with "Authorization: Bearer $CRON_SECRET"). ?reconcile=1 also re-adds orphans. */
async function handle(req: Request) {
  try {
    if (!authorised(req)) return Response.json({ error: "Not authorised (set CRON_SECRET and send it as a Bearer token)." }, { status: 401 });
    const swept = await sweepExpired(200);
    const url = new URL(req.url);
    const readded = url.searchParams.get("reconcile") === "1" ? await reconcile() : null;
    return Response.json({ swept, readded });
  } catch (e) {
    return jsonError(e);
  }
}
export const GET = handle;
export const POST = handle;
