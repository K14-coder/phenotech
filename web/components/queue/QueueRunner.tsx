"use client";

// /research-queue/run: research diseases in the browser with your own OpenAI API key (BYOK).
// The key lives in this component's memory (and sessionStorage only if "remember for this tab" is ticked).
// It is sent to https://api.openai.com only, never to the atlas server.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ACCOUNT_KEY, loadAccount, type AccountState } from "@/lib/account-client";
import { useResource } from "@/lib/resource";
import {
  OpenAIError,
  SHORT,
  TYPICAL_TASK,
  batchTexts,
  callAnthropic,
  callOpenAI,
  estimateTokens,
  fmtInt,
  listOpenAIModels,
  qapi,
  type CoverageItem,
  type Packet,
  type SubmitResult,
} from "./queue-client";

type ProviderId = "openai" | "anthropic";
const PROVIDERS: Record<ProviderId, { name: string; keyPrefix: string; defaultModel: string; models: string[]; pricing: string; keys: string; host: string }> = {
  openai: { name: "OpenAI", keyPrefix: "sk-", defaultModel: "gpt-6.1-sol", models: [], pricing: "https://platform.openai.com/docs/pricing", keys: "platform.openai.com", host: "api.openai.com" },
  anthropic: {
    name: "Anthropic (Claude)",
    keyPrefix: "sk-ant-",
    defaultModel: "claude-sonnet-5-5",
    models: ["claude-sonnet-5-5", "claude-opus-5-5"],
    pricing: "https://www.anthropic.com/pricing#api",
    keys: "console.anthropic.com",
    host: "api.anthropic.com",
  },
};
const keyStore = (p: ProviderId) => `rq-${p}-key`;
const BTN = "inline-flex min-h-[44px] items-center justify-center rounded-lg px-4 text-[15px] font-medium disabled:opacity-50";

type Phase = "idle" | "claiming" | "running" | "finishing" | "error";
interface LogLine {
  t: string;
  text: string;
  tone?: "ok" | "warn";
}

function readStoredKey(p: ProviderId = "openai"): string {
  if (typeof window === "undefined") return "";
  try {
    return sessionStorage.getItem(keyStore(p)) ?? "";
  } catch {
    return "";
  }
}

export function QueueRunner() {
  const acct = useResource<AccountState>(ACCOUNT_KEY, loadAccount);
  const [key, setKey] = useState(() => readStoredKey());
  const [remember, setRemember] = useState(() => !!readStoredKey());
  const [provider, setProvider] = useState<ProviderId>("openai");
  const [model, setModel] = useState(PROVIDERS.openai.defaultModel);
  const [models, setModels] = useState<string[]>([]);
  const [priceIn, setPriceIn] = useState("0.50");
  const [priceOut, setPriceOut] = useState("2.00");
  const [packet, setPacket] = useState<Packet | null>(null);
  const [checklist, setChecklist] = useState<CoverageItem[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState<{ done: number; total: number }>({ done: 0, total: 0 });
  const [log, setLog] = useState<LogLine[]>([]);
  const [auto, setAuto] = useState(false);
  const [spent, setSpent] = useState({ input: 0, output: 0 });
  const [session, setSession] = useState({ accepted: 0, rejected: 0, tasks: 0 });
  const stopRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      if (remember && key) sessionStorage.setItem(keyStore(provider), key);
      else sessionStorage.removeItem(keyStore(provider));
    } catch {
      /* storage blocked */
    }
  }, [remember, key, provider]);
  const prov = PROVIDERS[provider];
  const switchProvider = (p: ProviderId) => {
    setProvider(p);
    setModel(PROVIDERS[p].defaultModel);
    setModels(PROVIDERS[p].models);
    const k = readStoredKey(p);
    setKey(k);
    setRemember(!!k);
    if (p === "anthropic") {
      setPriceIn("3.00");
      setPriceOut("15.00");
    } else {
      setPriceIn("0.50");
      setPriceOut("2.00");
    }
  };

  const say = useCallback((text: string, tone?: LogLine["tone"]) => {
    setLog((l) => [{ t: new Date().toLocaleTimeString(), text, tone }, ...l].slice(0, 200));
  }, []);

  // a lease you already hold (after a reload)
  const signedIn = !!acct?.data?.user;
  useEffect(() => {
    if (!signedIn) return;
    qapi<{ packet: Packet | null }>("/api/queue/task")
      .then((r) => {
        if (r.packet) {
          setPacket(r.packet);
          setChecklist(r.packet.checklist);
        }
      })
      .catch(() => undefined);
  }, [signedIn]);

  const pIn = Number(priceIn) || 0;
  const pOut = Number(priceOut) || 0;
  const est = packet ? estimateTokens(packet) : TYPICAL_TASK;
  const cost = (est.input * pIn + est.output * pOut) / 1e6;
  const spentCost = (spent.input * pIn + spent.output * pOut) / 1e6;

  const handBack = useCallback(
    async (p: Packet) => {
      setPhase("finishing");
      const d = await qapi<{ status: string; checklist: CoverageItem[]; missing: string[]; rounds: number; maxRounds: number }>("/api/queue/done", "POST", {
        token: p.lease.token,
      });
      setChecklist(d.checklist);
      say(
        d.status === "complete"
          ? `${p.disease.name}: checklist complete. It leaves the queue. Thank you!`
          : d.status === "retired"
            ? `${p.disease.name}: handed back after ${d.rounds} rounds; it leaves the queue with gaps: ${d.missing.map((m) => SHORT[m] ?? m).join(", ")}.`
            : `${p.disease.name}: handed back. It returns to the top of the queue for the next volunteer, who will look for: ${d.missing.map((m) => SHORT[m] ?? m).join(", ")}.`,
        "ok",
      );
      setSession((s) => ({ ...s, tasks: s.tasks + 1 }));
      setPacket(null);
    },
    [say],
  );

  const runTask = useCallback(
    async (held: Packet | null): Promise<boolean> => {
      let p = held;
      if (!p) {
        setPhase("claiming");
        say("Claiming the next disease…");
        const r = await qapi<{ packet?: Packet; empty?: boolean; resumed?: boolean; message?: string }>("/api/queue/claim", "POST", {});
        if (!r.packet) {
          say(r.message ?? "The queue is empty.", "ok");
          setPhase("idle");
          return false;
        }
        p = r.packet;
        say(`${r.resumed ? "Resuming" : "Claimed"} ${p.disease.name} (round ${p.lease.round} of ${p.lease.maxRounds}); ${p.abstracts.length} PubMed abstracts.`);
      }
      setPacket(p);
      setChecklist(p.checklist);
      setPhase("running");
      const batches = batchTexts(p);
      setProgress({ done: 0, total: batches.length });
      if (!batches.length) say("PubMed returned no abstracts for this disease. Handing it back.", "warn");
      for (let i = 0; i < batches.length; i++) {
        if (stopRef.current) break;
        say(`Batch ${i + 1} of ${batches.length}: asking ${model}…`);
        const ac = new AbortController();
        abortRef.current = ac;
        const out = await (provider === "anthropic" ? callAnthropic : callOpenAI)(key.trim(), model.trim(), p, batches[i], ac.signal);
        setSpent((s) => ({ input: s.input + (out.usage?.input_tokens ?? 0), output: s.output + (out.usage?.output_tokens ?? 0) }));
        const res = await qapi<SubmitResult>("/api/queue/submit", "POST", { token: p.lease.token, provider, model: out.model, claims: out.claims, research_groups: out.research_groups });
        setChecklist(res.checklist);
        setSession((s) => ({ ...s, accepted: s.accepted + res.accepted + res.acceptedGroups, rejected: s.rejected + res.rejected.length }));
        say(
          `Batch ${i + 1}: ${res.accepted} claims and ${res.acceptedGroups} research groups verified, ${res.rejected.length} rejected${res.duplicates ? `, ${res.duplicates} duplicates` : ""}.`,
          res.rejected.length ? "warn" : "ok",
        );
        for (const r of res.rejected.slice(0, 4)) say(`  rejected ${r.kind} #${r.index + 1}: ${r.reason}`, "warn");
        setProgress({ done: i + 1, total: batches.length });
      }
      await handBack(p);
      return true;
    },
    [handBack, key, model, provider, say],
  );

  const start = async () => {
    if (!key.trim().startsWith(prov.keyPrefix)) {
      say(`Paste ${prov.name} API key (it starts with ${prov.keyPrefix}).`, "warn");
      return;
    }
    stopRef.current = false;
    try {
      let held = packet;
      for (;;) {
        const more = await runTask(held);
        held = null;
        if (!more || !auto || stopRef.current) break;
      }
      setPhase("idle");
    } catch (e) {
      setPhase("error");
      if ((e as Error).name === "AbortError") say("Stopped.", "warn");
      else if (e instanceof OpenAIError) {
        say(`${prov.name}: ${e.message}`, "warn");
        if (e.status === 401) say(`The key was not accepted. Check it on ${prov.keys}.`, "warn");
        if (e.status === 429) say("Rate limit or no credits left on this key. Your lease is kept; try again later or click “I’m done”.", "warn");
        if (e.status === 0) say("If the browser cannot reach the model provider, use the local worker instead (see /research-queue).", "warn");
      } else say((e as Error).message, "warn");
    }
  };

  const stopAndHandBack = async () => {
    stopRef.current = true;
    abortRef.current?.abort();
    if (!packet) return;
    try {
      await handBack(packet);
      setPhase("idle");
    } catch (e) {
      say((e as Error).message, "warn");
    }
  };

  const loadModels = async () => {
    if (provider === "anthropic") {
      setModels(PROVIDERS.anthropic.models);
      say("Claude models: claude-sonnet-5-5 (default) or claude-opus-5-5.");
      return;
    }
    try {
      const m = await listOpenAIModels(key.trim());
      setModels(m);
      say(`Your key can use ${m.length} chat models.`);
    } catch (e) {
      say(`Could not list models: ${(e as Error).message}`, "warn");
    }
  };

  if (!acct?.data) return <p className="mx-auto max-w-[760px] px-4 py-16 text-ink-3">One moment…</p>;
  if (!signedIn)
    return (
      <div className="mx-auto max-w-[760px] px-4 py-16">
        <h1 className="text-[26px] font-semibold text-ink">Sign in to research</h1>
        <p className="mt-3 text-[16px] text-ink-2">
          The research queue needs a free atlas account, so your verified claims carry your handle and the queue can be rate-limited. Anonymous use is refused.
        </p>
        <div className="mt-5 flex gap-3">
          <Link href="/join" className={`${BTN} bg-accent-700 text-white hover:bg-accent-900`}>
            Create an account
          </Link>
          <Link href="/me" className={`${BTN} border border-line text-ink-2 hover:border-accent-500`}>
            Sign in
          </Link>
        </div>
      </div>
    );

  const busy = phase === "claiming" || phase === "running" || phase === "finishing";
  return (
    <div className="mx-auto max-w-[1120px] px-4 pb-24 pt-7 sm:px-8">
      <nav aria-label="Breadcrumb" className="text-xs text-ink-3">
        <Link href="/research-queue" className="hover:text-ink">
          Research queue
        </Link>
        <span className="mx-1.5">/</span>
        <span>Browser runner</span>
      </nav>
      <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.02em] text-ink">Research in your browser</h1>
      <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-ink-2">
        Your browser calls OpenAI or Anthropic directly with your key, then sends only the extracted claims to the atlas, which verifies every quote against PubMed.
      </p>

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <section className="rounded-xl border border-line p-5">
            <h2 className="text-[17px] font-semibold text-ink">1. Your model provider and API key</h2>
            <div className="mt-2 flex gap-2" role="radiogroup" aria-label="Model provider">
              {(Object.keys(PROVIDERS) as ProviderId[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={provider === p}
                  disabled={busy}
                  onClick={() => switchProvider(p)}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${provider === p ? "border-accent-500 bg-accent-50 text-accent-900" : "border-line text-ink-2 hover:border-accent-500"}`}
                >
                  {PROVIDERS[p].name}
                </button>
              ))}
            </div>
            <p className="mt-2 text-sm text-ink-2">
              It uses <span className="font-medium">your own API credits</span>. The key stays in this tab&apos;s memory and is sent only to {prov.host}, never to the
              atlas server. Use a key with a spending limit.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={`${prov.keyPrefix}…`}
                autoComplete="off"
                spellCheck={false}
                aria-label={`${prov.name} API key`}
                className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 font-mono text-sm text-ink"
              />
              <button type="button" onClick={loadModels} disabled={!key} className="rounded-lg border border-line px-3 py-2 text-sm text-ink-2 hover:border-accent-500 disabled:opacity-50">
                List my models
              </button>
            </div>
            <label className="mt-2 flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Remember for this tab (sessionStorage; cleared when the tab closes)
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <label htmlFor="rq-model" className="text-ink-2">
                Model
              </label>
              <input
                id="rq-model"
                list="rq-models"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-56 rounded-lg border border-line px-3 py-1.5 font-mono text-sm text-ink"
              />
              <datalist id="rq-models">
                {models.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              <span className="text-xs text-ink-3">
                {provider === "anthropic" ? "Strict JSON through tool use (input_schema = the claim schema)." : "Needs structured outputs (json_schema)."}
              </span>
            </div>
          </section>

          <section className="rounded-xl border border-line p-5">
            <h2 className="text-[17px] font-semibold text-ink">2. Estimated cost per task</h2>
            <p className="mt-1.5 text-sm text-ink-2">
              {packet ? "This task" : "A typical task"}: {est.calls} calls, about {fmtInt(est.input)} input and {fmtInt(est.output)} output tokens.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
              <span>Price per million tokens: input $</span>
              <input value={priceIn} onChange={(e) => setPriceIn(e.target.value)} inputMode="decimal" aria-label="Input price" className="w-20 rounded border border-line px-2 py-1" />
              <span>output $</span>
              <input value={priceOut} onChange={(e) => setPriceOut(e.target.value)} inputMode="decimal" aria-label="Output price" className="w-20 rounded border border-line px-2 py-1" />
            </div>
            <p className="mt-2 text-[15px] text-ink">
              ≈ <span className="font-semibold">${cost < 0.01 ? cost.toFixed(4) : cost.toFixed(3)}</span> per task
              {spent.input ? ` · spent so far this session ≈ $${spentCost.toFixed(4)} (${fmtInt(spent.input)} in / ${fmtInt(spent.output)} out, as reported by ${prov.name})` : ""}
            </p>
            <p className="mt-1 text-xs text-ink-3">
              The prices above are examples. Enter your model&apos;s prices from{" "}
              <a href={prov.pricing} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                {prov.name}&apos;s pricing page
              </a>
              .
            </p>
          </section>

          <section className="rounded-xl border border-line p-5">
            <h2 className="text-[17px] font-semibold text-ink">3. Research</h2>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button type="button" onClick={start} disabled={busy} className={`${BTN} bg-accent-700 text-white hover:bg-accent-900`}>
                {packet ? "Continue this disease" : "Start researching"}
              </button>
              {packet && (
                <button type="button" onClick={stopAndHandBack} disabled={phase === "finishing"} className={`${BTN} border border-line text-ink-2 hover:border-accent-500`}>
                  I&apos;m done (hand it back)
                </button>
              )}
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
                Keep going with the next disease
              </label>
            </div>
            {progress.total > 0 && busy && (
              <div className="mt-4" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
                <div className="h-2 rounded bg-line-2">
                  <div className="h-2 rounded bg-accent-500 transition-all" style={{ width: `${(100 * progress.done) / progress.total}%` }} />
                </div>
                <p className="mt-1 text-xs text-ink-3">
                  {progress.done} of {progress.total} batches
                </p>
              </div>
            )}
            <p className="mt-3 text-sm text-ink-3">
              This session: {session.accepted} verified, {session.rejected} rejected, {session.tasks} disease{session.tasks === 1 ? "" : "s"} handed back.
            </p>
            <ol className="mt-3 max-h-[320px] space-y-1 overflow-y-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[12.5px]" aria-live="polite">
              {log.length === 0 && <li className="text-ink-3">Progress appears here.</li>}
              {log.map((l, i) => (
                <li key={i} className={l.tone === "warn" ? "text-warn-ink" : l.tone === "ok" ? "text-ok" : "text-ink-2"}>
                  <span className="text-ink-4">{l.t}</span> {l.text}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="space-y-6">
          <section className="rounded-xl border border-line p-5">
            <h2 className="text-[17px] font-semibold text-ink">{packet ? packet.disease.name : "No disease claimed yet"}</h2>
            {packet ? (
              <>
                <p className="mt-1 text-xs text-ink-3">
                  {packet.disease.genes.join(", ")} · {packet.disease.id} · round {packet.lease.round} of {packet.lease.maxRounds} · lease until{" "}
                  {new Date(packet.lease.expiresAt).toLocaleTimeString()}
                </p>
                <p className="mt-2 text-xs text-ink-3">
                  Already known: {packet.known.mechanismClasses.length ? packet.known.mechanismClasses.join(", ") : "no curated mechanism class"}; DisMech{" "}
                  {packet.known.dismech ? "yes" : "no"}; {packet.known.trials.byName} trials by name; {packet.known.patientOrganisations} patient groups.
                </p>
              </>
            ) : (
              <p className="mt-1 text-sm text-ink-3">Click Start researching to claim the next disease for 7 hours.</p>
            )}
            <h3 className="mt-4 text-sm font-semibold text-ink">Checklist</h3>
            <ul className="mt-2 space-y-2">
              {(checklist.length ? checklist : []).map((c) => (
                <li key={c.id} className="flex items-start gap-2 text-sm">
                  <span aria-hidden className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${c.done ? "bg-ok text-white" : "border border-ink-4"}`}>
                    {c.done ? "✓" : ""}
                  </span>
                  <span className={c.done ? "text-ink" : "text-ink-2"}>
                    {SHORT[c.id] ?? c.id}{" "}
                    <span className="text-xs text-ink-3">
                      {c.have}/{c.need} {c.unit}
                    </span>
                    <span className="sr-only">{c.done ? " (done)" : " (missing)"}</span>
                  </span>
                </li>
              ))}
              {!checklist.length && <li className="text-sm text-ink-3">Appears when a disease is claimed.</li>}
            </ul>
            {packet && (
              <Link href={packet.disease.url} className="mt-4 inline-block text-sm text-accent-700 hover:underline">
                Open the disease page →
              </Link>
            )}
          </section>
          {packet && (
            <section className="rounded-xl border border-line p-5">
              <h3 className="text-sm font-semibold text-ink">Abstracts in this task</h3>
              <ul className="mt-2 space-y-1.5 text-xs">
                {packet.abstracts.map((a) => (
                  <li key={a.pmid}>
                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                      PMID {a.pmid}
                    </a>{" "}
                    <span className="text-ink-2">{a.title}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
