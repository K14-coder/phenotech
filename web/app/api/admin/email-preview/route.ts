export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { HttpError, assertSameOrigin, jsonError, readBody, requireAdmin } from "@/lib/server/community";
import { baseUrl, sampleEmails, writeOutbox } from "@/lib/server/email";

/**
 * Admin only (ADMIN_TOKEN): every email template rendered with sample data, for /admin/emails. Nothing is sent.
 * With {"outbox": true} on a local server (not on Vercel), the samples are also written to web/.data/outbox/.
 */
export async function POST(req: Request) {
  try {
    assertSameOrigin(req);
    requireAdmin(req);
    const body = await readBody(req).catch(() => ({}) as Record<string, unknown>);
    const samples = sampleEmails(baseUrl(req));
    let files: string[] = [];
    if (body.outbox === true) {
      if (process.env.VERCEL) throw new HttpError(400, "The outbox can only be written on a local server.");
      files = await Promise.all(samples.map((s, i) => writeOutbox(s.email, `sample-${String(i + 1).padStart(2, "0")}-${s.email.tag}`)));
    }
    return Response.json(
      { emails: samples.map((s) => ({ name: s.name, subject: s.email.subject, html: s.email.html, text: s.email.text })), files },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (e) {
    return jsonError(e);
  }
}
