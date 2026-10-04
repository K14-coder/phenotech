export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { currentUser, deleteMe, inboxFor, jsonError, myAnnouncements, rateLimit, readBody, requireUser, assertSameOrigin, updateMe } from "@/lib/server/community";
import { storeMode } from "@/lib/server/store";

/** Who am I: the store mode (so the UI can say "Sign-up opens soon"), the account, inbox and own announcements. */
export async function GET() {
  try {
    const mode = storeMode();
    const u = mode === "off" ? null : await currentUser();
    if (!u) return Response.json({ mode, user: null });
    const { hash: _h, salt: _s, ...user } = u;
    void _h;
    void _s;
    const announcements = u.role === "researcher" || u.role === "industry" ? await myAnnouncements(u) : [];
    return Response.json({ mode, user, inbox: await inboxFor(u), announcements }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return jsonError(e);
  }
}

export async function PATCH(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "update", 60);
    const u = await requireUser();
    return Response.json({ user: await updateMe(u, await readBody(req)) });
  } catch (e) {
    return jsonError(e);
  }
}

export async function DELETE(req: Request) {
  try {
    assertSameOrigin(req);
    await rateLimit(req, "delete", 10);
    const u = await requireUser();
    await deleteMe(u);
    return Response.json({ deleted: true });
  } catch (e) {
    return jsonError(e);
  }
}
