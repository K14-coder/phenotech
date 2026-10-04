"use client";

// "Who you can contact now": general rare-disease help that is always valid, whatever the diagnosis.

const HELP: { name: string; what: string; url: string; where: string }[] = [
  { name: "NORD (National Organization for Rare Disorders)", what: "Disease information, patient assistance programmes and a directory of patient groups.", url: "https://rarediseases.org/", where: "US, open to all" },
  { name: "EURORDIS – Rare Diseases Europe", what: "The European alliance of rare-disease patient organisations; its member list helps you find a group.", url: "https://www.eurordis.org/", where: "Europe" },
  { name: "Global Genes – RARE Concierge", what: "Free one-to-one help finding information, support and resources for any rare disease.", url: "https://globalgenes.org/rare-concierge/", where: "Worldwide" },
  { name: "Genetic Alliance UK", what: "Support and information for families affected by genetic and rare conditions.", url: "https://geneticalliance.org.uk/", where: "UK" },
];

export function GeneralHelp({ compact = false }: { compact?: boolean }) {
  return (
    <section aria-labelledby="general-help-h" className={compact ? "" : "rounded-xl border border-line px-4 py-4"}>
      <h2 id="general-help-h" className="text-[19px] font-semibold text-ink">
        Who you can contact now
      </h2>
      <p className="mt-1 text-[15px] text-ink-3">These organisations help with any rare disease, even before a group exists for yours.</p>
      <ul className="mt-3 space-y-2.5">
        {HELP.map((h) => (
          <li key={h.name} className="rounded-lg bg-subtle px-3.5 py-3">
            <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-[16px] font-medium text-accent-700 hover:underline">
              {h.name} ↗
            </a>
            <p className="mt-0.5 text-[15px] text-ink-2">{h.what}</p>
            <p className="text-sm text-ink-3">{h.where}</p>
          </li>
        ))}
        <li className="rounded-lg bg-subtle px-3.5 py-3">
          <p className="text-[16px] font-medium text-ink">A genetic counsellor</p>
          <p className="mt-0.5 text-[15px] text-ink-2">They explain test results and what they mean for the family. Ask your doctor for a referral.</p>
        </li>
      </ul>
    </section>
  );
}
