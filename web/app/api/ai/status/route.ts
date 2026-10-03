import { BILLING_URL, MANAGE_USAGE_URL, PRECOMPUTED_STATUS, type AiStatusPayload } from "@/lib/ai-shared";
import { getLoginState, guardLocal, liveAIEnabled, loadOpenAI } from "@/lib/server/openai-local";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const noStore = { "cache-control": "no-store" };

/** What the UI should show. Contains no tokens. */
export async function GET(req: Request) {
  if (!liveAIEnabled()) return Response.json(PRECOMPUTED_STATUS, { headers: noStore });
  const denied = guardLocal(req, { write: false });
  if (denied) return denied;
  const login = getLoginState();
  try {
    const { llm } = await loadOpenAI();
    const a = await llm.describeAuth();
    const body: AiStatusPayload = {
      mode: "live",
      liveDisabled: false,
      authPath: a.path ?? "none",
      signedIn: !!a.chatgpt.signedIn,
      email: a.chatgpt.email ?? null,
      planUsage: !!a.chatgpt.planUsage,
      planUsageFirstEnabledAt: a.chatgpt.planUsageFirstEnabledAt ?? null,
      apiKeyConfigured: !!a.apiKeyConfigured,
      model: a.model ?? null,
      manageUsageUrl: a.manageUsageUrl ?? MANAGE_USAGE_URL,
      billingUrl: BILLING_URL,
      login: {
        status: login.status,
        ...(login.status === "pending" ? { authorizeUrl: login.authorizeUrl } : {}),
        ...(login.error ? { error: login.error } : {}),
      },
    };
    return Response.json(body, { headers: noStore });
  } catch (err) {
    const body: AiStatusPayload = {
      ...PRECOMPUTED_STATUS,
      mode: "live",
      liveDisabled: false,
      error: { kind: "integration_unavailable", message: `The OpenAI integration could not be loaded: ${err instanceof Error ? err.message : String(err)}` },
    };
    return Response.json(body, { status: 500, headers: noStore });
  }
}
