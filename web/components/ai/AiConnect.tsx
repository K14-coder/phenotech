"use client";

import { useAi } from "./AiProvider";

/** Approved label, black button format. The official ChatGPT logo can be added at the marked slot. */
export function ContinueWithChatGPT({ onClick, disabled, label = "Continue with ChatGPT" }: { onClick: () => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-9 items-center gap-2 rounded-full bg-black px-4 text-sm font-medium text-white transition-colors hover:bg-[#222] disabled:opacity-60"
    >
      {/* logo slot: official ChatGPT mark per OpenAI brand guidelines (not bundled) */}
      {label}
    </button>
  );
}

export function UsingPlanIndicator({ manageUsageUrl }: { manageUsageUrl: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
      Using ChatGPT plan ·
      <a href={manageUsageUrl} target="_blank" rel="noopener noreferrer" className="font-medium text-accent-700 hover:underline">
        Manage usage
      </a>
    </span>
  );
}

/** Auth state beside an AI action: indicator when connected, "Continue with ChatGPT" when not. */
export function AiConnect() {
  const { status, loaded, pending, authorizeUrl, message, login, logout } = useAi();
  if (!loaded) return null;

  if (status.mode !== "live") {
    return <p className="text-xs text-ink-3">Precomputed results only. Live AI runs when the atlas is run locally.</p>;
  }

  if (status.authPath === "chatgpt") {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <UsingPlanIndicator manageUsageUrl={status.manageUsageUrl} />
        {status.email && <span className="text-xs text-ink-3">{status.email}</span>}
        <button type="button" onClick={logout} className="text-xs text-ink-3 underline-offset-2 hover:text-ink hover:underline">
          Sign out
        </button>
        {message && <span className="text-xs text-ink-3">{message}</span>}
      </div>
    );
  }

  if (status.authPath === "api_key" && status.signedIn && status.planUsage) {
    return <p className="text-xs text-ink-3">Using an OpenAI API key (OPENAI_AUTH=api_key), although ChatGPT is connected.</p>;
  }

  return (
    <div className="space-y-2">
      {status.signedIn && !status.planUsage ? (
        <div className="space-y-2">
          <p className="text-xs text-ink-2">
            Signed in{status.email ? ` as ${status.email}` : ""}, but ChatGPT plan usage is not enabled.
          </p>
          <ContinueWithChatGPT onClick={() => login(true)} disabled={pending} label="Enable ChatGPT plan usage" />
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <ContinueWithChatGPT onClick={() => login(false)} disabled={pending} />
          <span className="text-xs text-ink-3">
            {status.authPath === "api_key" ? "Using an OpenAI API key until you connect." : "Precomputed results only until you connect."}
          </span>
        </div>
      )}
      {pending && (
        <p className="text-xs text-ink-2" role="status">
          Finish signing in in the browser window that opened.{" "}
          {authorizeUrl && (
            <>
              If nothing opened,{" "}
              <a href={authorizeUrl} target="_blank" rel="noopener noreferrer" className="font-medium text-accent-700 hover:underline">
                open the sign-in page
              </a>
              .
            </>
          )}
        </p>
      )}
      {message && <p className="text-xs text-warn-ink">{message}</p>}
      {!pending && status.authPath === "none" && (
        <p className="text-xs text-ink-3">Or use an API key: set OPENAI_API_KEY in the repository’s .env.local and restart.</p>
      )}
    </div>
  );
}
