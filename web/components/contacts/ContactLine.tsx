"use client";

// Phone (tel:) and email (mailto:) for an organisation or a recruiting study, with where it came from.
import type { ContactPoint } from "@/lib/contacts";

export function ContactLine({ p, size = "md" }: { p: ContactPoint | null; size?: "sm" | "md" }) {
  if (!p) return null;
  const sm = size === "sm";
  const link = `inline-flex items-center gap-1.5 ${sm ? "text-xs" : "min-h-[40px] text-[15px]"} font-medium text-accent-700 underline-offset-4 hover:underline break-all`;
  return (
    <div className={sm ? "mt-1" : "mt-2"}>
      <div className={`flex flex-wrap ${sm ? "gap-x-3" : "gap-x-5"}`}>
        {p.phones.map((x) => (
          <a key={x.tel} href={`tel:${x.tel}`} className={link}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M5.2 2.5 3.4 2.7c-.5.1-.9.5-.9 1 .2 5.3 4.5 9.6 9.8 9.8.5 0 .9-.4 1-.9l.2-1.8-2.6-1.2-1.3 1.3a7 7 0 0 1-3.6-3.6L7.3 6 6.1 3.4z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            {x.display}
          </a>
        ))}
        {p.emails.map((e) => (
          <a key={e} href={`mailto:${e}`} className={link}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <rect x="2" y="3.5" width="12" height="9" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
              <path d="m2.5 4.5 5.5 4 5.5-4" fill="none" stroke="currentColor" strokeWidth="1.3" />
            </svg>
            {e}
          </a>
        ))}
      </div>
      <p className={`${sm ? "text-[11px]" : "text-xs"} text-ink-3`}>
        {p.source === "ctgov" ? (
          <>
            From ClinicalTrials.gov{p.retrieved ? ` · retrieved ${p.retrieved}` : ""}
          </>
        ) : (
          <>
            From their website{p.retrieved ? ` · retrieved ${p.retrieved}` : ""}
          </>
        )}
      </p>
    </div>
  );
}
