"use client";

// Building blocks for Devon's pages (docs/persona-spec.md): calm, plain, one column that works on a
// phone. Every fact carries a "How do we know this?" that opens its evidence or names its source.
import Link from "next/link";
import { useId, useState } from "react";
import { useEvidence } from "../evidence/EvidenceProvider";
import { PlainText } from "../PlainText";
import { SaveButton } from "../community/AccountBits";
import { ContactLine } from "../contacts/ContactLine";
import { orgContact, trialContact, useContacts } from "@/lib/contacts";

export interface SourceLink {
  label: string;
  url: string;
}

/** Where a fact comes from: a graph edge (opens the evidence panel) and/or a short note with links. */
export interface How {
  edge?: string;
  note?: string;
  links?: SourceLink[];
}

export function HowWeKnow({ how, className = "" }: { how?: How | null; className?: string }) {
  const { openEdge } = useEvidence();
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!how || (!how.edge && !how.note && !how.links?.length)) return null;
  if (how.edge && !how.note && !how.links?.length)
    return (
      <button type="button" onClick={() => openEdge(how.edge!)} className={`text-sm text-accent-700 underline decoration-accent-200 underline-offset-4 hover:decoration-accent-700 ${className}`}>
        How do we know this?
      </button>
    );
  return (
    <span className={className}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
        className="text-sm text-accent-700 underline decoration-accent-200 underline-offset-4 hover:decoration-accent-700"
      >
        How do we know this?
      </button>
      {open && (
        <span id={id} className="mt-2 block rounded-md bg-subtle px-3 py-2.5 text-sm leading-relaxed text-ink-2">
          {how.note && <span className="block">{how.note}</span>}
          {how.links?.map((l) => (
            <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" className="mr-3 inline-block text-accent-700 hover:underline">
              {l.label} ↗
            </a>
          ))}
          {how.edge && (
            <button type="button" onClick={() => openEdge(how.edge!)} className="block text-accent-700 hover:underline">
              See the evidence →
            </button>
          )}
        </span>
      )}
    </span>
  );
}

export function SafetyNote() {
  return (
    <p className="rounded-lg border border-line bg-white px-4 py-3 text-[15px] leading-relaxed text-ink-2">
      This is information, not medical advice. A doctor or <PlainText text="genetic counsellor" /> is the right person for decisions.
    </p>
  );
}

export function DevonSection({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`${id}-h`} id={id} data-tour={id} className="scroll-mt-20">
      <h2 id={`${id}-h`} className="text-[21px] font-semibold leading-snug tracking-tight text-ink sm:text-[23px]">
        {title}
      </h2>
      <div className="mt-3 space-y-3 text-[17px] leading-relaxed text-ink-2">{children}</div>
    </section>
  );
}

export interface Contact {
  key: string;
  name: string;
  url: string | null;
  country?: string | null;
  /** what they offer, in their own or the directory's words */
  offers?: string[];
  blurb?: string | null;
  how?: How;
}

export function ContactCard({ c, cta = "Visit website" }: { c: Contact; cta?: string }) {
  const contacts = useContacts();
  const point = orgContact(contacts, { id: c.key, url: c.url, name: c.name });
  return (
    <li className="rounded-xl border border-line bg-white px-4 py-4">
      <p className="text-[17px] font-semibold leading-snug text-ink">{c.name}</p>
      {c.country && <p className="mt-0.5 text-sm text-ink-3">{c.country}</p>}
      {c.offers && c.offers.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {c.offers.map((o) => (
            <li key={o} className="rounded-full bg-subtle px-2.5 py-0.5 text-sm text-ink-2">
              {o}
            </li>
          ))}
        </ul>
      )}
      {c.blurb && <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{c.blurb}</p>}
      <ContactLine p={point} />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] items-center rounded-lg bg-accent-700 px-4 text-[15px] font-medium text-white hover:bg-accent-900"
          >
            {cta} ↗
          </a>
        )}
        <HowWeKnow how={c.how} />
      </div>
    </li>
  );
}

export interface Study {
  key: string;
  title: string;
  kind: string;
  detail?: string | null;
  sponsor?: string | null;
  url: string;
  how?: How;
}

/** ClinicalTrials.gov study type and phase, in plain words */
export function studyKind(type?: string | null, phase?: string | string[] | null): string {
  const t = (type ?? "").toLowerCase();
  const ph = (Array.isArray(phase) ? phase.join("/") : (phase ?? "")).toUpperCase();
  if (t.startsWith("observational")) return "A study that follows people over time. No treatment is given.";
  if (t.startsWith("expanded")) return "Access to a treatment outside a trial (expanded access).";
  if (ph.includes("PHASE3")) return "A large treatment study, usually the last step before approval.";
  if (ph.includes("PHASE2")) return "A treatment study that tests whether it helps.";
  if (ph.includes("PHASE1")) return "An early treatment study that mainly checks safety.";
  if (t.startsWith("interventional")) return "A study that tests a treatment or care approach.";
  return "A research study.";
}

export function StudyCard({ s }: { s: Study }) {
  const contacts = useContacts();
  const point = trialContact(contacts, `${s.key} ${s.url}`);
  return (
    <li className="rounded-xl border border-line bg-white px-4 py-4">
      <p className="text-[16px] font-medium leading-snug text-ink">{s.title}</p>
      <p className="mt-1 text-[15px] text-ink-2">{s.kind}</p>
      {(s.detail || s.sponsor) && (
        <p className="mt-1 text-sm text-ink-3">
          {s.detail}
          {s.detail && s.sponsor ? " · " : ""}
          {s.sponsor ? `Run by ${s.sponsor}` : ""}
        </p>
      )}
      <p className="mt-1 text-sm text-ink-3">Ages, places and how to join are on the study page.</p>
      <ContactLine p={point} />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <a
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] font-medium text-ink hover:border-accent-500"
        >
          See it on ClinicalTrials.gov ↗
        </a>
        <HowWeKnow how={s.how} />
      </div>
    </li>
  );
}

export function Checklist({ items }: { items: { text: React.ReactNode; key: string }[] }) {
  const [done, setDone] = useState<Set<string>>(() => new Set());
  return (
    <ul className="space-y-2">
      {items.map((it) => {
        const on = done.has(it.key);
        return (
          <li key={it.key}>
            <label className="flex min-h-[44px] cursor-pointer items-start gap-3 rounded-lg border border-line bg-white px-3.5 py-3">
              <input
                type="checkbox"
                checked={on}
                onChange={() =>
                  setDone((s) => {
                    const n = new Set(s);
                    if (n.has(it.key)) n.delete(it.key);
                    else n.add(it.key);
                    return n;
                  })
                }
                className="mt-1 h-5 w-5 shrink-0 accent-[#1f5a96]"
              />
              <span className={`text-[16px] leading-relaxed ${on ? "text-ink-3 line-through" : "text-ink"}`}>{it.text}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

/** Questions for the doctor, with a one-page printable version (print CSS in globals.css). */
export function DoctorQuestions({ name, questions, sources }: { name: string; questions: string[]; sources: SourceLink[] }) {
  return (
    <>
      <ol className="list-decimal space-y-2.5 pl-6 text-[17px] leading-relaxed text-ink">
        {questions.map((q) => (
          <li key={q}>
            <PlainText text={q} />
          </li>
        ))}
      </ol>
      <button
        type="button"
        onClick={() => window.print()}
        className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] font-medium text-ink hover:border-accent-500"
      >
        Print for your appointment
      </button>
      <SaveButton title={`Questions for the doctor: ${name}`} kind="questions" />
      <div className="print-sheet" aria-hidden="true">
        <h1 style={{ fontSize: "18pt", fontWeight: 600 }}>Questions for our appointment</h1>
        <p style={{ marginTop: "4pt" }}>About: {name}</p>
        <ol style={{ marginTop: "12pt", paddingLeft: "18pt", listStyle: "decimal" }}>
          {questions.map((q) => (
            <li key={q} style={{ marginBottom: "14pt" }}>
              {q}
              <div style={{ borderBottom: "1px solid #999", height: "28pt" }} />
            </li>
          ))}
        </ol>
        <p style={{ marginTop: "12pt", fontSize: "9pt" }}>
          This is information, not medical advice. Prepared with Tasukeru, a rare-disease atlas. Sources:{" "}
          {sources.map((s) => `${s.label} (${s.url})`).join("; ") || "see the atlas page"}.
        </p>
      </div>
    </>
  );
}

export function LearnMore({ children, label = "Learn more" }: { children: React.ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="border-t border-line pt-6">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex min-h-[44px] w-full items-center justify-between rounded-lg border border-line px-4 text-left text-[17px] font-medium text-ink hover:border-accent-500"
      >
        {label}
        <span className={`text-ink-3 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden="true">
          ›
        </span>
      </button>
      <p className="mt-2 text-sm text-ink-3">The detailed view: how it works in the body, related diseases and research ideas.</p>
      {open && <div className="mt-6">{children}</div>}
    </section>
  );
}

export function ContributeLine({ href }: { href: string }) {
  return (
    <p className="text-[15px] text-ink-2">
      Know a group we missed?{" "}
      <Link href={href} className="font-medium text-accent-700 hover:underline">
        Tell us about it →
      </Link>
    </p>
  );
}

/** Simple view: a gentle tip above contact cards, shown only when at least one card has a phone or email. */
export function ContactTip({ items }: { items: Contact[] }) {
  const contacts = useContacts();
  if (!items.some((c) => orgContact(contacts, { id: c.key, url: c.url, name: c.name }))) return null;
  return (
    <p className="rounded-lg bg-subtle px-3.5 py-2.5 text-[15px] text-ink-2">
      When you call or write, it helps to mention the gene name and that you found them through Tasukeru, a rare-disease atlas.
    </p>
  );
}
