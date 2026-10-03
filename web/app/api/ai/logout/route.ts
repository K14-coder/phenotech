import { guardLocal, liveAIEnabled, loadOpenAI, notFound, setLoginState } from "@/lib/server/openai-local";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Revokes the ChatGPT session and clears local tokens (keeps the client registration and host ID). */
export async function POST(req: Request) {
  if (!liveAIEnabled()) return notFound();
  const denied = guardLocal(req, { write: true });
  if (denied) return denied;
  try {
    const { siwc } = await loadOpenAI();
    const out = await siwc.logout();
    setLoginState({ status: "idle" });
    return Response.json({ signedOut: out.signedOut, revoked: out.revoked, message: out.message });
  } catch (err) {
    return Response.json({ error: { kind: "logout_failed", message: err instanceof Error ? err.message : String(err) } }, { status: 500 });
  }
}
