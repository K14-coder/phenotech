"use client";

// /join: three short steps with progress dots, then a welcome screen.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { WithGraph } from "../GraphProvider";
import { SearchBox } from "../search/SearchBox";
import { ACCOUNT_KEY, api, loadAccount, refreshAccount, type AccountState } from "@/lib/account-client";
import { COUNTRIES, DISEASE_ID, ROLES, looksInstitutional, type Role } from "@/lib/community";
import type { GraphIndex } from "@/lib/graph";
import { GLOBAL_INDEX_KEY, loadGlobalIndex, type GlobalIndex } from "@/lib/global";
import { useResource } from "@/lib/resource";
import { capFirst } from "@/lib/text";

export function JoinView() {
  return <WithGraph>{(idx) => <Join idx={idx} />}</WithGraph>;
}

export function useDiseaseName(idx: GraphIndex) {
  const gres = useResource<GlobalIndex>(GLOBAL_INDEX_KEY, loadGlobalIndex);
  return (id: string) => idx.nodeById.get(id)?.label ?? (gres?.data?.byId.get(id)?.name ? capFirst(gres.data.byId.get(id)!.name) : id);
}

const BTN = "inline-flex min-h-[48px] items-center justify-center rounded-xl px-5 text-[16px] font-medium";

function Join({ idx }: { idx: GraphIndex }) {
  const params = useSearchParams();
  const first = params.get("disease");
  const acct = useResource<AccountState>(ACCOUNT_KEY, loadAccount);
  const name = useDiseaseName(idx);
  const [step, setStep] = useState(1);
  const [role, setRole] = useState<Role | null>(null);
  const [diseases, setDiseases] = useState<string[]>(() => (first && DISEASE_ID.test(first) ? [first] : []));
  const [country, setCountry] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [trials, setTrials] = useState(false);
  const [contact, setContact] = useState(false);
  const [digest, setDigest] = useState(false);
  const [groupForms, setGroupForms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const a = acct?.data;
  if (!a) return <p className="mx-auto max-w-[560px] px-4 py-16 text-ink-3">One moment…</p>;
  if (a.mode === "off")
    return (
      <Shell>
        <h1 className="text-[26px] font-semibold text-ink">Sign-up opens soon</h1>
        <p className="mt-3 text-[17px] text-ink-2">Accounts are not switched on for this site yet. Everything else works without one.</p>
      </Shell>
    );
  if (a.user && !done)
    return (
      <Shell>
        <h1 className="text-[26px] font-semibold text-ink">You already have an account</h1>
        <Link href="/me" className={`${BTN} mt-5 bg-accent-700 text-white hover:bg-accent-900`}>
          Go to my atlas
        </Link>
      </Shell>
    );

  if (done)
    return (
      <Shell>
        <h1 className="text-[26px] font-semibold text-ink">Welcome. You’re part of the community now.</h1>
        <ul className="mt-5 space-y-3 text-[16px] text-ink-2">
          {emailSent && <li>We’ve emailed you a link to confirm your address. Until you confirm, notices appear only in My atlas.</li>}
          {diseases.length > 0 && <li>You follow {diseases.map(name).join(", ")}. New studies and resources for {diseases.length > 1 ? "them" : "it"} appear in your inbox.</li>}
          <li>You are counted anonymously, so researchers can see that families exist and where. They never see your email.</li>
          {trials && <li>When a study starts recruiting for a disease you follow, you’ll see it first in your inbox.</li>}
          {contact ? <li>Researchers can send you a message through the atlas. You decide whether to reply.</li> : <li>Researchers cannot contact you. You can change this anytime.</li>}
          {role === "researcher" && (
            <li>
              Your researcher account is {looksInstitutional(email) ? "marked verified (institutional email)" : "unverified for now"}. Verified accounts can announce studies; every
              announcement is reviewed before families see it.
            </li>
          )}
        </ul>
        <Link href="/me" className={`${BTN} mt-6 bg-accent-700 text-white hover:bg-accent-900`}>
          Go to my atlas
        </Link>
      </Shell>
    );

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ emailSent?: boolean }>("/api/account/signup", "POST", { role, diseases, country: country || null, email, password, consentTrials: trials, consentContact: contact, weeklyDigest: digest, groupForms, labels: Object.fromEntries(diseases.map((d) => [d, name(d)])) });
      refreshAccount();
      setEmailSent(!!r.emailSent);
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <div className="flex items-center gap-2" aria-label={`Step ${step} of 3`}>
        {[1, 2, 3].map((n) => (
          <span key={n} className={`h-2.5 rounded-full transition-all ${n === step ? "w-8 bg-accent-700" : n < step ? "w-2.5 bg-accent-500" : "w-2.5 bg-line"}`} aria-hidden="true" />
        ))}
        <span className="ml-2 text-sm text-ink-3">Step {step} of 3</span>
      </div>

      {step === 1 && (
        <section className="mt-6">
          <h1 className="text-[24px] font-semibold text-ink">Who are you?</h1>
          <ul className="mt-4 space-y-2">
            {ROLES.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setRole(r.id)}
                  aria-pressed={role === r.id}
                  className={`block w-full rounded-xl border px-4 py-3 text-left ${role === r.id ? "border-accent-700 bg-accent-50" : "border-line hover:border-accent-500"}`}
                >
                  <span className="block text-[16px] font-medium text-ink">{r.label}</span>
                  <span className="block text-sm text-ink-3">{r.hint}</span>
                </button>
              </li>
            ))}
          </ul>
          <button type="button" disabled={!role} onClick={() => setStep(2)} className={`${BTN} mt-5 w-full bg-accent-700 text-white hover:bg-accent-900 disabled:opacity-40 sm:w-auto`}>
            Continue
          </button>
        </section>
      )}

      {step === 2 && (
        <section className="mt-6">
          <h1 className="text-[24px] font-semibold text-ink">Which disease would you like to follow?</h1>
          <p className="mt-1 text-[15px] text-ink-3">You can follow more than one, and change this later.</p>
          {diseases.length > 0 && (
            <ul className="mt-4 flex flex-wrap gap-2">
              {diseases.map((d) => (
                <li key={d} className="inline-flex items-center gap-2 rounded-full border border-accent-200 bg-accent-50 px-3 py-1.5 text-[15px] text-ink">
                  {name(d)}
                  <button type="button" onClick={() => setDiseases((s) => s.filter((x) => x !== d))} aria-label={`Stop following ${name(d)}`} className="text-ink-3 hover:text-ink">
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4">
            <SearchBox
              variant="field"
              shortcut={false}
              label="Add a disease"
              placeholder="Search a disease or gene"
              onPick={(n) => n.type === "disease" && setDiseases((s) => [...new Set([...s, n.id])])}
              onPickGlobal={(r) => setDiseases((s) => [...new Set([...s, r.id])])}
            />
          </div>
          <label className="mt-5 block">
            <span className="text-[15px] font-medium text-ink">Country (optional)</span>
            <select value={country} onChange={(e) => setCountry(e.target.value)} className="mt-1 h-11 w-full rounded-lg border border-line bg-white px-3 text-[16px] sm:w-auto">
              <option value="">Prefer not to say</option>
              {COUNTRIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-sm text-ink-3">Only used for anonymous counts (groups of 5 or more), never shown on its own.</span>
          </label>
          <div className="mt-6 flex gap-3">
            <button type="button" onClick={() => setStep(1)} className={`${BTN} border border-line text-ink-2`}>
              Back
            </button>
            <button type="button" onClick={() => setStep(3)} className={`${BTN} flex-1 bg-accent-700 text-white hover:bg-accent-900 sm:flex-none`}>
              Continue
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <h1 className="text-[24px] font-semibold text-ink">Create your account</h1>
          <label className="block">
            <span className="text-[15px] font-medium text-ink">Email</span>
            <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px]" />
          </label>
          <label className="block">
            <span className="text-[15px] font-medium text-ink">Password (at least 10 characters)</span>
            <input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 h-11 w-full rounded-lg border border-line px-3 text-[16px]" />
          </label>
          <fieldset className="space-y-2.5 rounded-xl border border-line px-4 py-3">
            <legend className="px-1 text-sm text-ink-3">You choose (all off unless you tick them)</legend>
            <Check on={trials} set={setTrials} label="Tell me when a clinical trial starts recruiting for a disease I follow" />
            <Check on={contact} set={setContact} label="Researchers may contact me through the atlas (they never see my email)" />
            <Check on={groupForms} set={setGroupForms} label="Tell me when a patient group forms for a disease I follow" />
            <Check on={digest} set={setDigest} label="A weekly summary instead of single notices" />
          </fieldset>
          {error && (
            <p className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2 text-[15px] text-warn-ink" role="alert">
              {error}
            </p>
          )}
          <p className="text-sm text-ink-3">
            We never sell or share your contact details. Read our{" "}
            <Link href="/privacy" className="underline">
              privacy page
            </Link>
            .
          </p>
          <div className="flex gap-3">
            <button type="button" onClick={() => setStep(2)} className={`${BTN} border border-line text-ink-2`}>
              Back
            </button>
            <button type="submit" disabled={busy} className={`${BTN} flex-1 bg-accent-700 text-white hover:bg-accent-900 disabled:opacity-50 sm:flex-none`}>
              {busy ? "Creating…" : "Create account"}
            </button>
          </div>
          <p className="text-sm text-ink-3">
            Already have an account?{" "}
            <Link href="/me" className="text-accent-700 underline">
              Sign in
            </Link>
          </p>
        </form>
      )}
    </Shell>
  );
}

function Check({ on, set, label }: { on: boolean; set: (b: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 text-[15px] text-ink">
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-[#1f5a96]" />
      {label}
    </label>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-[560px] px-4 pb-24 pt-8 sm:pt-14">{children}</div>;
}
