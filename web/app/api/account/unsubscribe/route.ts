export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { jsonError, rateLimit, requireStore, unsubscribe } from "@/lib/server/community";

/**
 * One-click unsubscribe. Mail clients POST here (RFC 8058, List-Unsubscribe-Post), and the
 * /unsubscribe page POSTs here when a person opens the link from an email. The signed token is
 * the only credential, so there is no same-origin check. A plain GET changes nothing (link
 * scanners prefetch links); it forwards to the confirmation page instead.
 */
export async function POST(req: Request) {
  try {
    requireStore();
    await rateLimit(req, "unsub", 30);
    const url = new URL(req.url);
    let t = url.searchParams.get("t");
    if (!t && req.headers.get("content-type")?.includes("application/json")) {
      const body = (await req.json().catch(() => ({}))) as { token?: unknown };
      t = typeof body.token === "string" ? body.token : null;
    }
    await unsubscribe(t);
    return Response.json({ ok: true });
  } catch (e) {
    return jsonError(e);
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const t = url.searchParams.get("t") ?? "";
  return Response.redirect(new URL(`/unsubscribe?t=${encodeURIComponent(t)}`, url.origin), 303);
}
