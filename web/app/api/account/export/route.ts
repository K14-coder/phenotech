export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import { exportMe, jsonError, requireUser } from "@/lib/server/community";

/** "Export my data": everything the atlas holds about this account, as JSON. */
export async function GET() {
  try {
    const u = await requireUser();
    return new Response(JSON.stringify(await exportMe(u), null, 2), {
      headers: { "Content-Type": "application/json", "Content-Disposition": 'attachment; filename="my-atlas-data.json"', "Cache-Control": "no-store" },
    });
  } catch (e) {
    return jsonError(e);
  }
}
