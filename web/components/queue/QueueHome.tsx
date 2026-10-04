"use client";

// /research-queue: what the crowd research queue is, live numbers, the next 20 diseases, the leaderboard,
// "Start researching" (in the browser with an OpenAI API key, or the local ChatGPT worker) and worker setup.
import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { ACCOUNT_KEY, loadAccount, type AccountState } from "@/lib/account-client";
import { useResource } from "@/lib/resource";
import { SHORT, fmtInt, qapi, type QueueStats } from "./queue-client";

const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";
const H2 = "mt-1 text-[22px] font-semibold tracking-tight text-ink";
const BTN = "inline-flex min-h-[44px] items-center justify-center rounded-lg px-4 text-[15px] font-medium";

export function QueueHome() {
  const acct = useResource<AccountState>(ACCOUNT_KEY, loadAccount);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const origin = useSyncExternalStore(
    noop,
    () => window.location.origin,
    () => "https://rare-disease-atlas-five.vercel.app",
  );

  const refresh = useCallback(() => {
    qapi<QueueStats>("/api/queue/stats")
      .then((s) => {
        setStats(s);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 20_000);
    return () => clearInterval(t);
  }, [refresh]);

  const signedIn = !!acct?.data?.user;
  const off = acct?.data?.mode === "off";

  return (
    <div className="pb-24">
      <header className="border-b border-line">
        <div className="mx-auto max-w-[1120px] px-4 pb-8 pt-7 sm:px-8">
          <p className={EYEBROW}>Research queue</p>
          <h1 className="mt-2 max-w-[760px] text-[30px] font-semibold leading-tight tracking-[-0.02em] text-ink">
            Read the literature for one rare disease. Many people, each with their own AI.
          </h1>
          <p className="mt-3 max-w-[760px] text-[16px] leading-relaxed text-ink-2">
            The atlas maps 45 diseases in depth. About {stats ? fmtInt(stats.total) : "7,750"} more have a known gene but no evidence-graded page. Here, volunteers
            take one disease at a time: the atlas fetches up to 15 PubMed abstracts, your own AI model (OpenAI or Anthropic Claude) extracts claims with exact quotes, and the server keeps
            only claims whose quote appears word for word in an abstract it fetched itself. Everything lands on the disease page labelled{" "}
            <span className="font-medium text-ink">unreviewed</span>, ready for experts to check.
          </p>
          {error && <p className="mt-4 text-sm text-warn-ink">Live numbers could not be loaded: {error}</p>}
          <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat k="Diseases in the queue" v={stats?.inQueue} />
            <Stat k="Being researched now" v={stats?.leasedNow} />
            <Stat k="Completed" v={stats?.completed} sub={stats?.retired ? `${fmtInt(stats.retired)} more done with gaps` : undefined} />
            <Stat k="Claims verified" v={stats ? stats.claimsVerified + stats.groupsVerified : undefined} sub={stats?.rejected ? `${fmtInt(stats.rejected)} rejected` : undefined} />
            <Stat k="Volunteers" v={stats?.volunteers} />
          </dl>
        </div>
      </header>

      <div className="mx-auto max-w-[1120px] space-y-14 px-4 pt-10 sm:px-8">
        <section aria-labelledby="start-h">
          <p className={EYEBROW}>Take part</p>
          <h2 id="start-h" className={H2}>
            Start researching
          </h2>
          {off ? (
            <p className="mt-3 text-[15px] text-ink-2">Accounts are not switched on for this site yet, so the queue is closed.</p>
          ) : !signedIn ? (
            <p className="mt-3 max-w-[760px] text-[15px] text-ink-2">
              You need a free atlas account so your verified claims carry your handle and so the queue can be rate-limited. Anonymous use is refused.{" "}
              <Link href="/join" className="font-medium text-accent-700 hover:underline">
                Create an account
              </Link>{" "}
              or{" "}
              <Link href="/me" className="font-medium text-accent-700 hover:underline">
                sign in
              </Link>
              .
            </p>
          ) : (
            <MePanel stats={stats} onChange={refresh} />
          )}
          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <div className="rounded-xl border border-line p-5">
              <h3 className="text-[17px] font-semibold text-ink">In your browser, with your OpenAI or Anthropic API key</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">
                Your key stays in this browser tab and goes only to api.openai.com or api.anthropic.com, never to the atlas. It uses <span className="font-medium">your own API credits</span>:
                a task is about 3 model calls and roughly 15,000 input and 5,000 output tokens; the runner shows the estimate for your model before you start.
              </p>
              <Link href="/research-queue/run" className={`${BTN} mt-4 bg-accent-700 text-white hover:bg-accent-900`}>
                Open the browser runner
              </Link>
            </div>
            <div className="rounded-xl border border-line p-5">
              <h3 className="text-[17px] font-semibold text-ink">With a ChatGPT Plus or Pro plan, via a small local worker</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">
                One file, no dependencies, Node 20 or newer. It signs you in with ChatGPT on your own machine (a 127.0.0.1 loopback page), then claims diseases,
                extracts and submits in a loop until you stop it. It counts against your plan&apos;s usage limits.
              </p>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-subtle px-3 py-2.5 text-[12.5px] leading-relaxed text-ink">
                <code>
                  curl -fsSLO {origin}/worker/rare-atlas-worker.mjs{"\n"}node rare-atlas-worker.mjs --server {origin}
                </code>
              </pre>
              <p className="mt-2 text-xs text-ink-3">
                The worker asks for a worker token on first run (create one below). It can use <code>OPENAI_API_KEY</code> instead of ChatGPT with{" "}
                <code>--api-key</code>, or Claude with <code>--provider anthropic</code> and <code>ANTHROPIC_API_KEY</code>. With Claude Code, just ask it to run
                this worker, or to research a task through the two API calls documented in the atlas repo (docs/agent-reports/research-queue.md). Stop it with Ctrl-C: it hands the current disease back with what it found.{" "}
                <a href="/worker/rare-atlas-worker.mjs" className="text-accent-700 hover:underline">
                  Read the source
                </a>
                .
              </p>
              {signedIn && <WorkerToken />}
            </div>
          </div>
        </section>

        <div className="grid gap-12 lg:grid-cols-[1fr_320px]">
          <section aria-labelledby="next-h">
            <p className={EYEBROW}>Up next</p>
            <h2 id="next-h" className={H2}>
              The next 20 diseases
            </h2>
            <p className="mt-1.5 text-sm text-ink-3">
              Ranked by usefulness: trials or patient groups, a known prevalence, no curated mechanism chain yet, and closeness to a disease the atlas maps in depth.
              Diseases that came back with gaps go first.
            </p>
            <ol className="mt-4 divide-y divide-line-2 border-y border-line-2">
              {(stats?.next ?? []).map((d, i) => (
                <li key={d.id} className="flex gap-3 py-2.5">
                  <span className="w-6 shrink-0 text-right text-sm tabular-nums text-ink-4">{i + 1}</span>
                  <div className="min-w-0">
                    <Link href={`/d/${encodeURIComponent(d.id)}`} className="text-[15px] font-medium text-ink hover:text-accent-700 hover:underline">
                      {d.name}
                    </Link>
                    <span className="ml-2 text-xs text-ink-3">{d.genes.join(", ")}</span>
                    {d.returning && (
                      <span className="ml-2 rounded bg-warn-bg px-1.5 py-0.5 text-xs font-medium text-warn-ink">
                        round {d.round}
                        {d.gaps?.length ? `: needs ${d.gaps.map((g) => SHORT[g] ?? g).join(", ")}` : ""}
                      </span>
                    )}
                    <p className="text-xs text-ink-3">{d.why.join(" · ")}</p>
                  </div>
                </li>
              ))}
              {!stats && <li className="py-3 text-sm text-ink-3">Loading…</li>}
            </ol>
          </section>

          <aside className="space-y-10">
            <section aria-labelledby="board-h">
              <p className={EYEBROW}>Leaderboard</p>
              <h2 id="board-h" className={H2}>
                Verified claims
              </h2>
              {stats && !stats.leaderboard.length ? (
                <p className="mt-3 text-sm text-ink-3">No verified claims yet. Be the first.</p>
              ) : (
                <ol className="mt-3 divide-y divide-line-2 border-y border-line-2">
                  {(stats?.leaderboard ?? []).map((r, i) => (
                    <li key={r.handle} className="flex justify-between py-2 text-sm">
                      <span className="text-ink">
                        <span className="mr-2 tabular-nums text-ink-4">{i + 1}</span>
                        {r.handle}
                      </span>
                      <span className="tabular-nums text-ink-2">{fmtInt(r.verified)}</span>
                    </li>
                  ))}
                </ol>
              )}
              <p className="mt-2 text-xs text-ink-3">Handles only. Rejected and duplicate claims do not count.</p>
              {!!stats?.byProvider.length && (
                <div className="mt-5">
                  <h3 className="text-sm font-semibold text-ink">By model provider</h3>
                  <ul className="mt-2 space-y-1 text-sm text-ink-2">
                    {stats.byProvider.map((p) => (
                      <li key={p.provider} className="flex justify-between">
                        <span>{p.provider === "openai" ? "OpenAI" : p.provider === "anthropic" ? "Anthropic Claude" : "Other"}</span>
                        <span className="tabular-nums">
                          {fmtInt(p.accepted)} verified · {fmtInt(p.rejected)} rejected
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
            {!!stats?.recentlyCompleted.length && (
              <section aria-labelledby="recent-h">
                <p className={EYEBROW}>Recently completed</p>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {stats.recentlyCompleted.map((d) => (
                    <li key={d.id}>
                      <Link href={`/d/${encodeURIComponent(d.id)}`} className="text-accent-700 hover:underline">
                        {d.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        </div>

        <section aria-labelledby="how-h" className="max-w-[860px]">
          <p className={EYEBROW}>How it works</p>
          <h2 id="how-h" className={H2}>
            Leases, a checklist and a server that trusts nobody
          </h2>
          <ol className="mt-4 list-decimal space-y-2.5 pl-5 text-[15px] leading-relaxed text-ink-2">
            <li>
              <span className="font-medium text-ink">Claim.</span> You get the next disease for {stats?.leaseHours ?? 7} hours. Two volunteers never get the same disease
              at once (an atomic pop from a sorted set plus a lease lock).
            </li>
            <li>
              <span className="font-medium text-ink">Read.</span> The server assembles the task: names, genes, identifiers, what the atlas already knows, the checklist
              of what is missing, and up to 15 PubMed abstracts it fetched itself.
            </li>
            <li>
              <span className="font-medium text-ink">Extract.</span> Your model returns claims in a strict JSON schema: subject, relation, object, one verbatim sentence,
              PMID, study type, species, certainty and whether the sentence negates the claim.
            </li>
            <li>
              <span className="font-medium text-ink">Verify.</span> Every quote must be a verbatim sentence of that PMID&apos;s abstract (after whitespace and Unicode
              normalisation), the PMID must be in your task, and the schema must hold. Anything else is rejected and counted.
            </li>
            <li>
              <span className="font-medium text-ink">Hand back.</span> When you click &ldquo;I&apos;m done&rdquo; or the lease runs out, the server scores the checklist.
              Complete diseases leave the queue; incomplete ones return to the top with their gaps listed, for the next volunteer (up to {stats?.maxRounds ?? 3}{" "}
              rounds).
            </li>
          </ol>
          <h3 className="mt-6 text-[16px] font-semibold text-ink">The checklist</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px] text-ink-2">
            {(stats?.checklist ?? []).map((c) => (
              <li key={c.id}>
                {c.label} <span className="text-ink-3">(at least {c.need} {c.unit})</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-3">
            Accepted claims are stored as &ldquo;{stats?.statusLabel ?? "community-researched, AI-extracted, quote-verified, unreviewed"}&rdquo; with your handle and the
            model name you report. Research groups are senior authors exactly as PubMed lists them, with their affiliation; never emails or contact details.
          </p>
        </section>
      </div>
    </div>
  );
}

const noop = () => () => undefined;

function Stat({ k, v, sub }: { k: string; v?: number; sub?: string }) {
  return (
    <div className="rounded-lg border border-line px-4 py-3">
      <dt className="text-xs text-ink-3">{k}</dt>
      <dd className="mt-1 text-[24px] font-semibold tabular-nums text-ink">{v === undefined ? "…" : fmtInt(v)}</dd>
      {sub && <dd className="text-xs text-ink-3">{sub}</dd>}
    </div>
  );
}

function MePanel({ stats, onChange }: { stats: QueueStats | null; onChange: () => void }) {
  const me = stats?.me;
  const [editing, setEditing] = useState(false);
  const [handle, setHandle] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  if (!me) return <p className="mt-3 text-sm text-ink-3">Loading your queue profile…</p>;
  const save = async () => {
    try {
      await qapi("/api/queue/me", "POST", { handle });
      setEditing(false);
      setMsg(null);
      onChange();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg bg-subtle px-4 py-3 text-sm text-ink-2">
      <span>
        Researching as{" "}
        {editing ? (
          <span className="inline-flex items-center gap-1.5">
            <input
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              aria-label="New handle"
              className="w-40 rounded border border-line bg-white px-2 py-1 text-sm text-ink"
              maxLength={24}
            />
            <button type="button" onClick={save} className="rounded border border-line px-2 py-1 text-xs hover:border-accent-500">
              Save
            </button>
          </span>
        ) : (
          <>
            <span className="font-medium text-ink">{me.handle}</span>{" "}
            <button
              type="button"
              onClick={() => {
                setHandle(me.handle);
                setEditing(true);
              }}
              className="text-xs text-accent-700 hover:underline"
            >
              change
            </button>
          </>
        )}
      </span>
      <span>
        {fmtInt(me.accepted)} verified · {fmtInt(me.rejected)} rejected · {fmtInt(me.tasks)} task{me.tasks === 1 ? "" : "s"}
      </span>
      {me.lease && (
        <span>
          You hold <span className="font-medium text-ink">{me.lease.name}</span> until {new Date(me.lease.expiresAt).toLocaleTimeString()} ·{" "}
          <Link href="/research-queue/run" className="text-accent-700 hover:underline">
            continue
          </Link>
        </span>
      )}
      {msg && <span className="text-warn-ink">{msg}</span>}
    </div>
  );
}

function WorkerToken() {
  const [token, setToken] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const create = async () => {
    try {
      const r = await qapi<{ token: string; expires: string }>("/api/queue/token", "POST", {});
      setToken(r.token);
      setMsg(`Valid until ${new Date(r.expires).toLocaleDateString()}. It is shown once; paste it when the worker asks.`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  const revoke = async () => {
    try {
      const r = await qapi<{ revoked: number }>("/api/queue/token", "DELETE");
      setToken(null);
      setMsg(`Revoked ${r.revoked} token${r.revoked === 1 ? "" : "s"}.`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  return (
    <div className="mt-4 border-t border-line-2 pt-3">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={create} className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink">
          Create a worker token
        </button>
        <button type="button" onClick={revoke} className="rounded-lg px-3 py-1.5 text-sm text-ink-3 hover:text-ink">
          Revoke my tokens
        </button>
      </div>
      {token && (
        <input
          readOnly
          value={token}
          onFocus={(e) => e.currentTarget.select()}
          aria-label="Worker token"
          className="mt-2 w-full rounded border border-line bg-subtle px-2 py-1.5 font-mono text-xs text-ink"
        />
      )}
      {msg && <p className="mt-1.5 text-xs text-ink-3">{msg}</p>}
    </div>
  );
}
