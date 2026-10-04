export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

import { timingSafeEqual } from "node:crypto";
import { jsonError, requireStore } from "@/lib/server/community";
import { runDigest } from "@/lib/server/digest";
import { baseUrl } from "@/lib/server/email";

/**
 * Daily notices and weekly summaries (scheduled in vercel.json). Vercel Cron sends
 * "Authorization: Bearer <CRON_SECRET>"; an x-cron-secret header works too, for manual runs.
 * Without CRON_SECRET set, the endpoint is closed.
 */
function authorised(req: Request): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return false;
  const auth = req.headers.get("authorization");
  const got = auth?.startsWith("Bearer ") ? auth.slice(7) : (req.headers.get("x-cron-secret") ?? "");
  const a = Buffer.from(got);
  const b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function GET(req: Request) {
  try {
    if (!authorised(req)) return Response.json({ error: "Not allowed." }, { status: 401 });
    requireStore();
    return Response.json(await runDigest(baseUrl(req)), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}
