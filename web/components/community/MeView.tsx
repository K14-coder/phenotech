"use client";

// /me: the member home. Followed diseases, inbox (approved study announcements, relayed researcher
// messages, and studies recruiting now from the atlas data), saved items, privacy settings, export and
// a real "delete my account". Researcher accounts also get the community tools.
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { SearchBox } from "../search/SearchBox";
import { ACCOUNT_KEY, api, loadAccount, refreshAccount, type AccountState } from "@/lib/account-client";
import { COUNTRIES, K_ANON, ROLES, type PublicUser } from "@/lib/community";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { globalHref } from "@/lib/global";
import { loadChannels, loadScale, type ChannelsFile, type ScaleEntry } from "@/lib/population";
import { useResource } from "@/lib/resource";
import { Shell, useDiseaseName } from "./JoinView";

const H2 = "text-[19px] font-semibold text-ink";
const BTN = "inline-flex min-h-[44px] items-center justify-center rounded-lg px-4 text-[15px] font-medium";

export function MeView() {
  return <WithGraph>{(idx) => <Me idx={idx} />}</WithGraph>;
}

function Me({ idx }: { idx: GraphIndex }) {
  const acct = useResource<AccountState>(ACCOUNT_KEY, loadAccount);
  const a = acct?.data;
  if (!a) return <p className="mx-auto max-w-[560px] px-4 py-16 text-ink-3">One moment…</p>;
  if (a.mode === "off")
    return (
      <Shell>
        <h1 className="text-[26px] font-semibold text-ink">Sign-up opens soon</h1>
        <p className="mt-3 text-[17px] text-ink-2">Accounts are not switched on for this site yet.</p>
      </Shell>
    );
  if (!a.user) return <SignIn />;
  return <Home idx={idx} a={a} u={a.user} />;
}

function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Shell>
      <h1 className="text-[26px] font-semibold text-ink">Sign in</h1>
      <form
        className="mt-5 space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api("/api/account/login", "POST", { email, password });
            refreshAccount();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="block">
          <span className="text-[15px] font-medium text-ink">Email</span>
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px]" />
        </label>
        <label className="block">
          <span className="text-[15px] font-medium text-ink">Password</span>
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px]" />
        </label>
        {error && (
          <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-[15px] text-warn-ink" role="alert">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-4">
          <button type="submit" disabled={busy} className={`${BTN} w-full bg-accent-700 text-white hover:bg-accent-900 sm:w-auto`}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <Link href="/forgot" className="text-[15px] text-accent-700 underline">
            Forgot password?
          </Link>
        </div>
      </form>
      <p className="mt-6 text-[15px] text-ink-2">
        New here?{" "}
        <Link href="/join" className="font-medium text-accent-700 underline">
          Create an account
        </Link>
      </p>
    </Shell>
  );
}

interface Notice {
  key: string;
  disease: string;
  title: string;
  url: string;
  meta: string;
}

function Home({ idx, a, u }: { idx: GraphIndex; a: AccountState; u: PublicUser }) {
  const name = useDiseaseName(idx);
  const channels = useResource<ChannelsFile | null>("pop:channels", loadChannels);
  const globalIds = useMemo(() => u.diseases.filter((d) => !d.startsWith("disease:")), [u.diseases]);
  const loadScaleAll = useCallback(async () => {
    const out: Record<string, ScaleEntry | null> = {};
    for (const d of globalIds) out[d] = await loadScale(d).catch(() => null);
    return out;
  }, [globalIds]);
  const scale = useResource<Record<string, ScaleEntry | null>>(globalIds.length ? `me:scale:${globalIds.join(",")}` : null, loadScaleAll);
  const [msg, setMsg] = useState<string | null>(null);

  const recruiting: Notice[] = useMemo(() => {
    const out: Notice[] = [];
    for (const d of u.diseases) {
      if (d.startsWith("disease:")) {
        const by = channels?.data?.by_disease[d];
        for (const id of (by?.recruiting_trial ?? []).slice(0, 3)) {
          const c = channels?.data?.channels.find((x) => x.id === id);
          if (c) out.push({ key: `${d}-${id}`, disease: d, title: c.name, url: c.url ?? "#", meta: [c.status?.toLowerCase().replace(/_/g, " "), c.phase, c.sponsor].filter(Boolean).join(" · ") });
        }
      } else {
        for (const st of (scale?.data?.[d]?.studies ?? []).filter((s) => ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"].includes(s.st)).slice(0, 3))
          out.push({ key: `${d}-${st.id}`, disease: d, title: st.t, url: st.u, meta: [st.st.toLowerCase().replace(/_/g, " "), st.sp].filter(Boolean).join(" · ") });
      }
    }
    return out;
  }, [u.diseases, channels, scale]);

  const save = async (patch: Record<string, unknown>, ok = "Saved.") => {
    try {
      await api("/api/account", "PATCH", patch);
      refreshAccount();
      setMsg(ok);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };
  const href = (d: string) => (d.startsWith("disease:") ? diseaseHref(d) : globalHref(d));
  const researcher = u.role === "researcher" || u.role === "industry";

  return (
    <div className="mx-auto w-full max-w-[860px] space-y-10 px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-ink-3">My atlas</p>
          <h1 className="text-[26px] font-semibold text-ink">{ROLES.find((r) => r.id === u.role)?.label ?? "Member"}</h1>
          <p className="text-sm text-ink-3">
            {u.email}
            {researcher && (u.verified ? " · verified (institutional email)" : " · unverified researcher account")}
          </p>
        </div>
        <button
          type="button"
          onClick={async () => {
            await api("/api/account/logout", "POST", {});
            refreshAccount();
          }}
          className={`${BTN} border border-line text-ink-2`}
        >
          Sign out
        </button>
      </header>
      {msg && (
        <p className="rounded-lg bg-subtle px-3 py-2 text-[15px] text-ink-2" role="status">
          {msg}
        </p>
      )}
      {!u.emailVerified && a.emailMode !== "disabled" && <ConfirmBanner />}

      <section aria-labelledby="follow-h">
        <h2 id="follow-h" className={H2}>
          Diseases I follow
        </h2>
        {u.diseases.length ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {u.diseases.map((d) => (
              <li key={d} className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1.5 text-[15px]">
                <Link href={href(d)} className="text-ink hover:text-accent-700">
                  {name(d)}
                </Link>
                <button type="button" aria-label={`Stop following ${name(d)}`} onClick={() => void save({ diseases: u.diseases.filter((x) => x !== d) }, "Updated.")} className="text-ink-3 hover:text-ink">
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[15px] text-ink-3">You don’t follow a disease yet.</p>
        )}
        <div className="mt-3 max-w-[420px]">
          <SearchBox
            variant="field"
            shortcut={false}
            label="Follow another disease"
            placeholder="Follow another disease"
            onPick={(n) => n.type === "disease" && void save({ diseases: [...new Set([...u.diseases, n.id])], labels: { [n.id]: n.label } }, "Following.")}
            onPickGlobal={(r) => void save({ diseases: [...new Set([...u.diseases, r.id])], labels: { [r.id]: r.name } }, "Following.")}
          />
        </div>
      </section>

      <section aria-labelledby="inbox-h">
        <h2 id="inbox-h" className={H2}>
          Inbox
        </h2>
        <ul className="mt-3 space-y-3">
          {(a.inbox ?? []).map((m) => (
            <li key={m.id} className="rounded-xl border border-line px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.06em] text-ink-3">
                {m.kind === "announcement"
                  ? "Study announcement (reviewed)"
                  : m.kind === "contact"
                    ? "Message from a researcher"
                    : m.kind === "trial"
                      ? "New study · ClinicalTrials.gov"
                      : m.kind === "grant"
                        ? "New research · NIH RePORTER"
                        : "Notice"}
              </p>
              {m.url ? (
                <a href={m.url} target="_blank" rel="noopener noreferrer" className="mt-1 block text-[16px] font-medium text-accent-700 hover:underline">
                  {m.title} ↗
                </a>
              ) : (
                <p className="mt-1 text-[16px] font-medium text-ink">{m.title}</p>
              )}
              <p className="mt-1 whitespace-pre-line text-[15px] text-ink-2">{m.body}</p>
              {m.extra && (
                <dl className="mt-2 space-y-0.5 text-sm text-ink-3">
                  {Object.entries(m.extra).map(([k, v]) => (
                    <div key={k}>
                      <dt className="inline">{k === "ethics" ? "Ethics / IRB" : k[0].toUpperCase() + k.slice(1)}: </dt>
                      <dd className="inline text-ink-2">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className="mt-1 text-xs text-ink-3">
                {m.diseases.map(name).join(", ")} · {new Date(m.created).toLocaleDateString()}
              </p>
            </li>
          ))}
          {recruiting.map((n) => (
            <li key={n.key} className="rounded-xl border border-line px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-[0.06em] text-ink-3">Study recruiting now · {name(n.disease)}</p>
              <a href={n.url} target="_blank" rel="noopener noreferrer" className="mt-1 block text-[16px] font-medium text-accent-700 hover:underline">
                {n.title} ↗
              </a>
              {n.meta && <p className="text-sm text-ink-3">{n.meta}</p>}
            </li>
          ))}
          {!(a.inbox ?? []).length && !recruiting.length && <p className="text-[15px] text-ink-3">Nothing yet. Follow a disease to see studies and news for it here.</p>}
        </ul>
      </section>

      <section aria-labelledby="saved-h">
        <h2 id="saved-h" className={H2}>
          Saved
        </h2>
        {u.saved.length ? (
          <ul className="mt-3 space-y-1.5">
            {u.saved.map((s) => (
              <li key={s.href} className="flex items-center justify-between gap-3 text-[15px]">
                <Link href={s.href} className="text-accent-700 hover:underline">
                  {s.title}
                </Link>
                <button type="button" onClick={() => void save({ unsave: s.href }, "Removed.")} className="text-sm text-ink-3 hover:text-ink">
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[15px] text-ink-3">Use “Save to my atlas” on a disease page to keep your questions and the doctor printout here.</p>
        )}
      </section>

      <section aria-labelledby="privacy-h" className="space-y-3">
        <h2 id="privacy-h" className={H2}>
          Privacy and notifications
        </h2>
        {(
          [
            ["trials", "Email me about new recruiting studies and newly funded research for a disease I follow"],
            ["researcherContact", "Researchers may contact me through the atlas (they never see my email)"],
            ["groupForms", "Tell me when a patient group forms for a disease I follow"],
            ["weeklyDigest", "A weekly summary instead of single notices"],
          ] as const
        ).map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-start gap-3 text-[15px] text-ink">
            <input type="checkbox" checked={u.consent[k]} onChange={(e) => void save({ consent: { [k]: e.target.checked } }, "Updated.")} className="mt-0.5 h-5 w-5 shrink-0 accent-[#1f5a96]" />
            {label}
          </label>
        ))}
        <label className="block">
          <span className="text-[15px] text-ink">Country (for anonymous counts only)</span>
          <select value={u.country ?? ""} onChange={(e) => void save({ country: e.target.value || null }, "Updated.")} className="mt-1 h-11 w-full rounded-lg border border-line bg-white px-3 text-[16px] sm:w-auto">
            <option value="">Prefer not to say</option>
            {COUNTRIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="flex cursor-pointer items-start gap-3 text-[15px] text-ink">
          <input type="checkbox" checked={!u.emailOptOut} onChange={(e) => void save({ emails: e.target.checked }, "Updated.")} className="mt-0.5 h-5 w-5 shrink-0 accent-[#1f5a96]" />
          <span>
            Email me these notices
            <span className="block text-sm text-ink-3">
              {a.emailMode === "disabled"
                ? "This site doesn’t send email yet; notices appear here."
                : u.emailVerified
                  ? "Every notice also appears here. Each email has a one-click unsubscribe link."
                  : "Confirm your email first; until then, notices appear only here."}
            </span>
          </span>
        </label>
        <p className="text-sm text-ink-3">
          <Link href="/privacy" className="underline">
            How we handle your data
          </Link>
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <a href="/api/account/export" className={`${BTN} border border-line text-ink-2`}>
            Export my data
          </a>
          <DeleteAccount />
        </div>
      </section>

      {researcher && <ResearcherTools idx={idx} a={a} u={u} />}
    </div>
  );
}

function ConfirmBanner() {
  const [state, setState] = useState<"idle" | "busy" | "sent" | string>("idle");
  return (
    <div className="rounded-xl border border-line bg-accent-50 px-4 py-3 text-[15px] text-ink-2" role="status">
      <p>
        <span className="font-medium text-ink">Please confirm your email.</span> We sent you a link when you signed up. Until you confirm, notices appear only here and we send no study emails.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={state === "busy" || state === "sent"}
          onClick={async () => {
            setState("busy");
            try {
              await api("/api/account/verify/resend", "POST", {});
              setState("sent");
            } catch (e) {
              setState(e instanceof Error ? e.message : String(e));
            }
          }}
          className="min-h-[44px] rounded-lg border border-line bg-white px-4 font-medium text-accent-700 disabled:opacity-60"
        >
          {state === "busy" ? "Sending…" : state === "sent" ? "Sent. Check your inbox" : "Send the link again"}
        </button>
        {state !== "idle" && state !== "busy" && state !== "sent" && <span className="text-warn-ink">{state}</span>}
      </div>
    </div>
  );
}

function DeleteAccount() {
  const [ask, setAsk] = useState(false);
  if (!ask)
    return (
      <button type="button" onClick={() => setAsk(true)} className={`${BTN} border border-warn-line text-warn-ink`}>
        Delete my account
      </button>
    );
  return (
    <span className="flex flex-wrap items-center gap-2 rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-[15px] text-warn-ink">
      This deletes your account, what you follow, your inbox and saved items. It cannot be undone.
      <button
        type="button"
        onClick={async () => {
          await api("/api/account", "DELETE");
          refreshAccount();
        }}
        className={`${BTN} bg-warn-ink text-white`}
      >
        Delete permanently
      </button>
      <button type="button" onClick={() => setAsk(false)} className="px-2 underline">
        Keep it
      </button>
    </span>
  );
}

function ResearcherTools({ idx, a, u }: { idx: GraphIndex; a: AccountState; u: PublicUser }) {
  const name = useDiseaseName(idx);
  const deep = useMemo(() => idx.graph.nodes.filter((n) => n.type === "disease").map((n) => n.id), [idx]);
  const [form, setForm] = useState({ disease: u.diseases[0] ?? deep[0] ?? "", title: "", organisation: "", summary: "", eligibility: "", contact: "", ethics: "" });
  const [out, setOut] = useState<string | null>(null);
  const [contact, setContact] = useState({ disease: u.diseases[0] ?? deep[0] ?? "", organisation: "", message: "" });
  const loadInterest = useCallback(() => api<{ interest: { disease: string; total: number | null; byCountry: { country: string; n: number }[]; withheld: boolean }[] }>("/api/research/interest", "POST", { diseases: [...new Set([...u.diseases, ...deep])] }), [u.diseases, deep]);
  const interest = useResource(`me:interest:${u.id}`, loadInterest);
  const options = [...new Set([...u.diseases, ...deep])];
  const field = (k: keyof typeof form, label: string, rows = 1, hint?: string) => (
    <label className="block">
      <span className="text-[15px] font-medium text-ink">{label}</span>
      {rows > 1 ? (
        <textarea rows={rows} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-[15px]" />
      ) : (
        <input value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[15px]" />
      )}
      {hint && <span className="mt-0.5 block text-sm text-ink-3">{hint}</span>}
    </label>
  );
  return (
    <section aria-labelledby="rt-h" className="space-y-8 border-t border-line pt-8">
      <div>
        <h2 id="rt-h" className="text-[22px] font-semibold text-ink">
          Researcher tools
        </h2>
        {!u.verified && (
          <p className="mt-2 rounded-lg bg-warn-bg px-3 py-2 text-sm text-warn-ink">
            Unverified account: your email domain does not look institutional. Verification would work by a confirmation link sent to an
            institutional address, or an ORCID sign-in; until then every announcement is labelled unverified and reviewed by hand.
          </p>
        )}
      </div>

      <div>
        <h3 className={H2}>Community interest</h3>
        <p className="mt-1 text-sm text-ink-3">Members following each disease, by country. Groups smaller than {K_ANON} are never shown.</p>
        {interest?.status === "loading" ? (
          <p className="mt-2 text-sm text-ink-3">Loading…</p>
        ) : (
          <ul className="mt-3 space-y-1.5 text-[15px]">
            {(interest?.data?.interest ?? [])
              .filter((r) => r.total != null)
              .map((r) => (
                <li key={r.disease}>
                  <b className="font-medium text-ink">{name(r.disease)}</b>: {r.total} members
                  {r.byCountry.length > 0 && <span className="text-ink-3"> ({r.byCountry.map((c) => `${c.country} ${c.n}`).join(", ")})</span>}
                </li>
              ))}
            {!(interest?.data?.interest ?? []).some((r) => r.total != null) && (
              <li className="text-ink-3">No disease has {K_ANON} or more members yet, so nothing is shown. This protects early members.</li>
            )}
          </ul>
        )}
      </div>

      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/api/research/announce", "POST", { ...form, diseases: [form.disease] });
            setOut("Sent for review. It reaches followers’ inboxes once a moderator approves it.");
            setForm({ ...form, title: "", summary: "", eligibility: "", contact: "", ethics: "" });
            refreshAccount();
          } catch (err) {
            setOut(err instanceof Error ? err.message : String(err));
          }
        }}
      >
        <h3 className={H2}>Announce a study to a community</h3>
        <label className="block">
          <span className="text-[15px] font-medium text-ink">Disease</span>
          <select value={form.disease} onChange={(e) => setForm({ ...form, disease: e.target.value })} className="mt-1 h-11 w-full rounded-lg border border-line bg-white px-3 text-[15px]">
            {options.map((d) => (
              <option key={d} value={d}>
                {name(d)}
              </option>
            ))}
          </select>
        </label>
        {field("title", "Study title")}
        {field("organisation", "Organisation", 1, "Shown to families instead of your name or email.")}
        {field("summary", "Plain-language summary", 4, "Short sentences a family can follow: what the study does, how long, what taking part involves.")}
        {field("eligibility", "Who can take part", 2)}
        {field("contact", "How to get in touch", 1, "A study website or a study team address, not a personal one.")}
        {field("ethics", "Ethics / IRB reference", 1, "For example the approval number or ClinicalTrials.gov ID.")}
        <button type="submit" className={`${BTN} bg-accent-700 text-white hover:bg-accent-900`}>
          Send for review
        </button>
        {out && (
          <p className="text-[15px] text-ink-2" role="status">
            {out}
          </p>
        )}
        {(a.announcements ?? []).length > 0 && (
          <ul className="mt-3 space-y-1 text-[15px]">
            {(a.announcements ?? []).map((x) => (
              <li key={x.id}>
                {x.title} · <span className={x.status === "approved" ? "text-ok" : x.status === "rejected" ? "text-warn-ink" : "text-ink-3"}>{x.status === "pending" ? "pending review" : x.status}</span>
              </li>
            ))}
          </ul>
        )}
      </form>

      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const r = await api<{ delivered: number | null; note: string | null }>("/api/research/contact", "POST", contact);
            setOut(r.delivered != null ? `Delivered to ${r.delivered} members who opted in.` : (r.note ?? "Delivered."));
            setContact({ ...contact, message: "" });
          } catch (err) {
            setOut(err instanceof Error ? err.message : String(err));
          }
        }}
      >
        <h3 className={H2}>Request contact</h3>
        <p className="text-sm text-ink-3">Your message reaches only members who opted in to researcher contact. You never see their email; they reply if they choose.</p>
        <select value={contact.disease} onChange={(e) => setContact({ ...contact, disease: e.target.value })} className="h-11 w-full rounded-lg border border-line bg-white px-3 text-[15px]">
          {options.map((d) => (
            <option key={d} value={d}>
              {name(d)}
            </option>
          ))}
        </select>
        <input placeholder="Organisation" value={contact.organisation} onChange={(e) => setContact({ ...contact, organisation: e.target.value })} className="h-11 w-full rounded-lg border border-line px-3 text-[15px]" />
        <textarea rows={4} placeholder="Your message (plain language)" value={contact.message} onChange={(e) => setContact({ ...contact, message: e.target.value })} className="w-full rounded-lg border border-line px-3 py-2 text-[15px]" />
        <button type="submit" className={`${BTN} border border-line text-ink`}>
          Send through the atlas
        </button>
      </form>
    </section>
  );
}
