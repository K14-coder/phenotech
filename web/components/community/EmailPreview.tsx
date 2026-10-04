"use client";

// /admin/emails: every email template with sample data, rendered in sandboxed iframes (no scripts), so the
// layout can be checked without sending anything. Needs the ADMIN_TOKEN, typed here and never stored.
import Link from "next/link";
import { useState } from "react";

interface Preview {
  name: string;
  subject: string;
  html: string;
  text: string;
}

export function EmailPreview() {
  const [token, setToken] = useState("");
  const [list, setList] = useState<Preview[] | null>(null);
  const [active, setActive] = useState(0);
  const [width, setWidth] = useState<600 | 390>(600);
  const [showText, setShowText] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const r = await fetch("/api/admin/email-preview", { method: "POST", headers: { "x-admin-token": token, "Content-Type": "application/json" }, body: "{}" });
      const j = (await r.json()) as { emails?: Preview[]; error?: string };
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setList(j.emails ?? []);
      setActive(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const cur = list?.[active];

  return (
    <div className="mx-auto w-full max-w-[1100px] space-y-5 px-4 pb-24 pt-10">
      <p className="text-sm">
        <Link href="/admin" className="text-accent-700 hover:underline">
          ← Moderation
        </Link>
      </p>
      <h1 className="text-[26px] font-semibold text-ink">Email previews</h1>
      <p className="text-[15px] text-ink-3">Every email Phenotech sends, with sample data. Nothing is sent from this page.</p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <input type="password" placeholder="Admin token" value={token} onChange={(e) => setToken(e.target.value)} className="h-11 min-w-0 flex-1 rounded-lg border border-line px-3 text-[15px]" />
        <button type="submit" className="h-11 rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white">
          Show previews
        </button>
      </form>
      {error && (
        <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-warn-ink" role="alert">
          {error}
        </p>
      )}
      {list && cur && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
          <ul className="flex flex-wrap gap-2 lg:flex-col" aria-label="Templates">
            {list.map((p, i) => (
              <li key={p.name}>
                <button
                  type="button"
                  aria-pressed={i === active}
                  onClick={() => setActive(i)}
                  className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${i === active ? "border-accent-700 bg-accent-50 font-medium text-accent-900" : "border-line text-ink-2 hover:border-accent-500"}`}
                >
                  {p.name}
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0 space-y-3">
            <p className="text-sm text-ink-2">
              <span className="text-ink-3">Subject:</span> <b className="font-medium text-ink">{cur.subject}</b>
            </p>
            <div className="flex flex-wrap gap-2 text-sm">
              {([600, 390] as const).map((w) => (
                <button key={w} type="button" aria-pressed={width === w && !showText} onClick={() => { setWidth(w); setShowText(false); }} className={`rounded-full border px-3 py-1 ${width === w && !showText ? "border-accent-700 bg-accent-50" : "border-line"}`}>
                  {w === 600 ? "Desktop" : "Phone"}
                </button>
              ))}
              <button type="button" aria-pressed={showText} onClick={() => setShowText(true)} className={`rounded-full border px-3 py-1 ${showText ? "border-accent-700 bg-accent-50" : "border-line"}`}>
                Plain text
              </button>
            </div>
            {showText ? (
              <pre className="whitespace-pre-wrap rounded-lg border border-line bg-subtle p-4 font-mono text-[13px] text-ink-2">{cur.text}</pre>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-line bg-subtle p-2">
                <iframe title={`Preview: ${cur.name}`} srcDoc={cur.html} sandbox="" style={{ width, maxWidth: "100%", height: 900, border: 0, background: "#fff" }} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
