"use client";

import { useEffect, useState } from "react";
import type { GraphIndex } from "@/lib/graph";
import { aiTargetId, generate, generateLive, hasPrecomputed, loadPrecomputed, type AIResult, type AiProgressEvent } from "@/lib/ai";
import { AiConnect, ContinueWithChatGPT } from "./AiConnect";
import { AiDocView, AiMeta, docToText } from "./AiDocView";
import { useAi } from "./AiProvider";

/**
 * One AI action (button + result). Shows a precomputed result when one exists (instant, no usage),
 * otherwise generates live when the local server has a usable sign-in. Handles every error state.
 * On the deployed site (precomputed only) the action is not rendered at all when no precomputed
 * result exists for this target, so there is never a button that cannot produce anything.
 */
export function AiAction({
  idx,
  kind,
  payload,
  label,
  busyLabel = "Writing…",
}: {
  idx: GraphIndex;
  kind: "proposal" | "explain-path" | "compare-questions" | "experiment" | "outreach";
  payload: Record<string, unknown>;
  label: string;
  busyLabel?: string;
}) {
  const ai = useAi();
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AIResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const targetId = aiTargetId(kind, payload);
  const key = targetId ? `${kind}|${targetId}` : null;
  const [checked, setChecked] = useState<{ key: string; ok: boolean } | null>(null);
  useEffect(() => {
    if (!key || !targetId) return;
    let alive = true;
    void hasPrecomputed(kind, targetId).then((ok) => alive && setChecked({ key, ok }));
    return () => {
      alive = false;
    };
  }, [key, kind, targetId]);
  const available = !key ? false : checked?.key === key ? checked.ok : null;

  const onEvent = (e: AiProgressEvent) =>
    setProgress((p) => {
      const base = p ?? { phase: "collect" as const, startedAt: Date.now() };
      if (e.type === "progress") return { ...base, sentences: e.sentences, chars: e.chars };
      if (e.phase === "collect") return { ...base, phase: "collect", connections: e.connections };
      if (e.phase === "draft") return { ...base, phase: "draft", model: e.model };
      return { ...base, phase: "check" };
    });

  const run = async (opts: { fresh?: boolean } = {}) => {
    setBusy(true);
    setCopied(false);
    setProgress(null);
    const r = opts.fresh ? await generateLive(kind, payload, onEvent) : await generate(kind, payload, { live: ai.canGenerateLive, onEvent });
    setProgress(null);
    setRes(r);
    setBusy(false);
    if (r.error && ["no_llm_available", "login_required", "plan_usage_not_granted", "auth"].includes(r.error.kind)) void ai.refresh();
  };

  const showPrecomputed = async () => {
    const pre = await loadPrecomputed(kind, payload);
    setRes(pre ?? { status: "not_connected", source: "none", text: "No precomputed version exists for this yet." });
  };

  // precomputed-only (deployed) site: show the action only where a precomputed result exists
  if (!ai.canGenerateLive && (!ai.loaded || available !== true)) return null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={() => run()}
          disabled={busy}
          className="rounded-md bg-accent-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-900 disabled:opacity-60"
        >
          {busy ? busyLabel : label}
        </button>
        <AiConnect />
      </div>

      <div aria-live="polite">
        {busy && <ProgressSteps progress={progress} />}

        {!busy && res?.status === "ok" && res.doc && (
          <div className="rounded-lg border border-line px-5 py-4">
            <AiDocView idx={idx} result={res} />
            <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-line pt-3 text-xs">
              <button
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(docToText(res.doc!));
                    setCopied(true);
                  } catch {
                    /* clipboard unavailable */
                  }
                }}
                className="font-medium text-accent-700 hover:underline"
              >
                {copied ? "Copied" : "Copy text"}
              </button>
              {res.source === "precomputed" && ai.canGenerateLive && (
                <button type="button" onClick={() => run({ fresh: true })} className="font-medium text-accent-700 hover:underline">
                  Generate a fresh version
                </button>
              )}
              <span className="text-ink-3">Numbered marks open the evidence. Muted text is AI framing with no direct source.</span>
            </div>
          </div>
        )}

        {!busy && res?.status === "ok" && !res.doc && res.text && (
          <div className="rounded-lg border border-line px-5 py-4">
            <AiMeta result={res} />
            <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-2">{res.text}</p>
          </div>
        )}

        {!busy && res?.status === "not_connected" && (
          <p className="rounded-lg border border-dashed border-ink-4 px-4 py-3 text-sm leading-relaxed text-ink-2">{res.text}</p>
        )}

        {!busy && res?.status === "error" && res.error && <AiErrorPanel res={res} onRetry={() => run()} onShowPrecomputed={showPrecomputed} />}
      </div>
    </div>
  );
}

interface Progress {
  phase: "collect" | "draft" | "check";
  startedAt: number;
  connections?: number;
  model?: string;
  sentences?: number;
  chars?: number;
}

/** Calm progress that names the real steps the server is on. */
function ProgressSteps({ progress }: { progress: Progress | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!progress) return <p className="text-sm text-ink-3">Looking for a saved version first…</p>;
  const order = ["collect", "draft", "check"] as const;
  const at = order.indexOf(progress.phase);
  const state = (i: number) => (i < at ? "done" : i === at ? "active" : "todo");
  const secs = Math.max(0, Math.round((now - progress.startedAt) / 1000));
  const labels = [
    progress.connections ? `Collecting ${progress.connections} cited connections from the atlas` : "Collecting the cited connections",
    `Drafting with ${progress.model ?? "the model"}${progress.sentences ? ` · ${progress.sentences} sentence${progress.sentences === 1 ? "" : "s"} so far` : ""}`,
    "Checking every citation against the atlas",
  ];
  return (
    <div className="rounded-lg border border-line px-5 py-4" role="status" aria-live="polite">
      <ol className="space-y-2">
        {labels.map((l, i) => (
          <li key={i} className={`flex items-center gap-2.5 text-sm ${state(i) === "todo" ? "text-ink-3" : "text-ink-2"}`}>
            <StepDot state={state(i)} />
            {l}
            {state(i) === "active" && "…"}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-ink-3">{secs}s · usually 15 to 45 seconds. You can keep reading the page.</p>
    </div>
  );
}

function StepDot({ state }: { state: "done" | "active" | "todo" }) {
  if (state === "done")
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" className="shrink-0 text-ok">
        <circle cx="7" cy="7" r="6.5" fill="currentColor" />
        <path d="M4 7.2 6 9.2 10 5" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  if (state === "active") return <span className="h-3.5 w-3.5 shrink-0 animate-pulse rounded-full border-[3px] border-accent-200 bg-accent-700" aria-hidden="true" />;
  return <span className="h-3.5 w-3.5 shrink-0 rounded-full border border-ink-4" aria-hidden="true" />;
}

function AiErrorPanel({ res, onRetry, onShowPrecomputed }: { res: AIResult; onRetry: () => void; onShowPrecomputed: () => void }) {
  const ai = useAi();
  const e = res.error!;
  const primary = "rounded-md bg-ink px-3.5 py-1.5 text-sm font-medium text-white hover:bg-black";
  const secondary = "text-sm font-medium text-accent-700 hover:underline";

  let title = "The AI request didn’t work";
  let body = e.message;
  let actions: React.ReactNode = (
    <button type="button" onClick={onRetry} className={primary}>
      Try again
    </button>
  );

  switch (e.kind) {
    case "usage_limit":
    case "rate_limited":
      title = "Usage limit reached";
      body = "Your ChatGPT plan, or this app’s share of it, has reached its usage limit. Nothing was charged. Review your limits, then try again later.";
      actions = (
        <a href={e.action?.url ?? ai.status.manageUsageUrl} target="_blank" rel="noopener noreferrer" className={primary}>
          Manage usage
        </a>
      );
      break;
    case "credits_exhausted":
      title = "API credits used up";
      body = e.message;
      actions = (
        <>
          <a href={e.action?.url ?? ai.status.billingUrl} target="_blank" rel="noopener noreferrer" className={primary}>
            Manage billing
          </a>
          {ai.status.mode === "live" && !ai.status.planUsage && <ContinueWithChatGPT onClick={() => ai.login(false)} disabled={ai.pending} />}
        </>
      );
      break;
    case "not_eligible":
    case "policy_or_region":
    case "not_authorized":
    case "client_not_enabled":
      title = "ChatGPT plan usage isn’t available for this account";
      body = `${e.message} You can still use an OpenAI API key (OPENAI_API_KEY in the repository’s .env.local) or the precomputed results.`;
      actions = null;
      break;
    case "plan_usage_not_granted":
      title = "ChatGPT plan usage is not enabled";
      actions = <ContinueWithChatGPT onClick={() => ai.login(true)} disabled={ai.pending} label="Enable ChatGPT plan usage" />;
      break;
    case "no_llm_available":
    case "login_required":
    case "auth":
      title = "Connect to generate this";
      body = "Sign in with ChatGPT to generate it live, or use the precomputed results.";
      actions = <ContinueWithChatGPT onClick={() => ai.login(false)} disabled={ai.pending} />;
      break;
    case "live_disabled":
      title = "Precomputed results only";
      actions = null;
      break;
  }

  return (
    <div className="rounded-lg border border-warn-line bg-warn-bg px-4 py-3.5" role="alert">
      <p className="text-sm font-semibold text-warn-ink">{title}</p>
      <p className="mt-1 text-sm leading-relaxed text-warn-ink">{body}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {actions}
        <button type="button" onClick={onShowPrecomputed} className={secondary}>
          Show precomputed version if available
        </button>
      </div>
    </div>
  );
}
