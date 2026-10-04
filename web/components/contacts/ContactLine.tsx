"use client";

// Contact details on group, registry and study cards, the same in every view:
//  - "Call" (tel:) and "Email" (mailto:) buttons with the number and address written out, and where they come from;
//  - named contact persons only when the organisation itself publishes them on its own site (never researchers);
//  - when nothing is published: "Visit website" plus "No phone or email published", so it is clear we looked.
import Link from "next/link";
import { orgChecked, orgContact, orgPeople, trialContact, useContacts, type ContactPerson, type ContactPoint } from "@/lib/contacts";

type Size = "sm" | "md";

function PhoneIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      <path d="M5.2 2.5 3.4 2.7c-.5.1-.9.5-.9 1 .2 5.3 4.5 9.6 9.8 9.8.5 0 .9-.4 1-.9l.2-1.8-2.6-1.2-1.3 1.3a7 7 0 0 1-3.6-3.6L7.3 6 6.1 3.4z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}
function MailIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      <rect x="2" y="3.5" width="12" height="9" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="m2.5 4.5 5.5 4 5.5-4" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

/** Call / Email buttons with the number and address written out. */
function Buttons({ phones, emails, size }: { phones: { display: string; tel: string }[]; emails: string[]; size: Size }) {
  const cls =
    size === "md"
      ? "inline-flex min-h-[44px] max-w-full items-center gap-2 rounded-lg border border-accent-700 bg-white px-3.5 text-[15px] text-accent-900 hover:bg-accent-50"
      : "inline-flex min-h-[32px] max-w-full items-center gap-1.5 rounded-md border border-accent-200 bg-white px-2.5 text-xs text-accent-900 hover:bg-accent-50";
  return (
    <div className={`flex flex-wrap ${size === "md" ? "gap-2" : "gap-1.5"}`}>
      {phones.map((p) => (
        <a key={p.tel} href={`tel:${p.tel}`} className={cls} aria-label={`Call ${p.display}`}>
          <PhoneIcon />
          <span className="font-semibold">Call</span>
          <span className="break-all tabular-nums">{p.display}</span>
        </a>
      ))}
      {emails.map((e) => (
        <a key={e} href={`mailto:${e}`} className={cls} aria-label={`Email ${e}`}>
          <MailIcon />
          <span className="font-semibold">Email</span>
          <span className="break-all">{e}</span>
        </a>
      ))}
    </div>
  );
}

function Provenance({ p, size }: { p: ContactPoint; size: Size }) {
  return (
    <p className={`mt-1 ${size === "md" ? "text-xs" : "text-[11px]"} text-ink-3`}>
      {p.source === "ctgov" ? "From ClinicalTrials.gov" : "From their website"}
      {p.retrieved ? ` · retrieved ${p.retrieved}` : ""}
    </p>
  );
}

/** Kept for existing callers: a contact point (organisation or study) as Call / Email buttons. */
export function ContactLine({ p, size = "md" }: { p: ContactPoint | null; size?: Size }) {
  if (!p) return null;
  return (
    <div className={size === "md" ? "mt-3" : "mt-1.5"}>
      <Buttons phones={p.phones} emails={p.emails} size={size} />
      <Provenance p={p} size={size} />
    </div>
  );
}

function Person({ person, orgName, size }: { person: ContactPerson; orgName: string; size: Size }) {
  return (
    <div className={`${size === "md" ? "mt-3 rounded-lg bg-subtle px-3 py-2.5" : "mt-1.5"}`}>
      <p className={size === "md" ? "text-[15px] text-ink" : "text-xs text-ink"}>
        <span className="text-ink-3">Contact person:</span> <b className="font-medium">{person.name}</b>
        {person.role ? `, ${person.role}` : ""}
      </p>
      {(person.phones.length > 0 || person.emails.length > 0) && (
        <div className="mt-1.5">
          <Buttons phones={person.phones} emails={person.emails} size={size} />
        </div>
      )}
      <p className={`mt-1 ${size === "md" ? "text-xs" : "text-[11px]"} leading-relaxed text-ink-3`}>
        Shown as published by {orgName} on{" "}
        {person.page ? (
          <a href={person.page} target="_blank" rel="noopener noreferrer" className="underline">
            their page
          </a>
        ) : (
          "their website"
        )}
        {person.retrieved ? ` (retrieved ${person.retrieved})` : ""}. To correct or remove, contact the organisation or{" "}
        <Link href="/privacy#report" className="underline">
          us
        </Link>
        .
      </p>
    </div>
  );
}

/**
 * Everything we can show for reaching an organisation. `website` adds a "Visit website" link when the card has
 * no website button of its own.
 */
export function OrgContact({ org, size = "md", website = false }: { org: { id?: string; url?: string | null; name: string }; size?: Size; website?: boolean }) {
  const idx = useContacts();
  if (!idx) return null;
  const p = orgContact(idx, org);
  const people = orgPeople(idx, org);
  if (!p && !people.length) {
    const checked = orgChecked(idx, org);
    return (
      <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${size === "md" ? "mt-3 text-sm" : "mt-1.5 text-xs"} text-ink-3`}>
        {website && org.url && (
          <a href={org.url} target="_blank" rel="noopener noreferrer" className="font-medium text-accent-700 hover:underline">
            Visit website ↗
          </a>
        )}
        <span>{checked ? "No phone or email published on their website." : "No phone or email published that we know of."}</span>
      </div>
    );
  }
  return (
    <div>
      {p && <ContactLine p={p} size={size} />}
      {people.map((x) => (
        <Person key={`${x.name}-${x.role}`} person={x} orgName={org.name} size={size} />
      ))}
    </div>
  );
}

/** A recruiting study's ClinicalTrials.gov central contact, or a pointer to the study page. */
export function StudyContact({ idOrUrl, size = "md" }: { idOrUrl: string; size?: Size }) {
  const idx = useContacts();
  if (!idx) return null;
  const p = trialContact(idx, idOrUrl);
  if (!p) return <p className={`${size === "md" ? "mt-2 text-sm" : "mt-1 text-xs"} text-ink-3`}>No central phone or email on ClinicalTrials.gov; the study page lists its sites.</p>;
  return <ContactLine p={p} size={size} />;
}
