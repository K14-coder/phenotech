import { guardLocal, liveAIEnabled, loadOpenAI, notFound, setLoginState } from "@/lib/server/openai-local";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * "Continue with ChatGPT": starts the 127.0.0.1 loopback sign-in on this machine, opens the system
 * browser, and returns at once. The UI polls /api/ai/status for the outcome. Returns no tokens.
 */
export async function POST(req: Request) {
  if (!liveAIEnabled()) return notFound();
  const denied = guardLocal(req, { write: true });
  if (denied) return denied;
  const body = (await req.json().catch(() => ({}))) as { reconsent?: unknown };
  try {
    const { siwc } = await loadOpenAI();
    const attempt = await siwc.beginLogin({ reconsent: body?.reconsent === true });
    setLoginState({ status: "pending", authorizeUrl: attempt.authorizeUrl, startedAt: Date.now() });
    attempt.completion.then(
      () => setLoginState({ status: "done" }),
      (err: { code?: string; message?: string }) =>
        setLoginState({ status: "failed", error: { kind: err?.code ?? "login_failed", message: err?.message ?? "Sign-in did not finish." } }),
    );
    await siwc.openInBrowser(attempt.authorizeUrl).catch(() => {}); // same machine; the UI also shows the link
    return Response.json({ authorizeUrl: attempt.authorizeUrl }, { headers: { "cache-control": "no-store" } });
  } catch (err) {
    const e = err as { code?: string; message?: string };
    return Response.json({ error: { kind: e?.code ?? "login_failed", message: e?.message ?? "Could not start sign-in." } }, { status: 500 });
  }
}
