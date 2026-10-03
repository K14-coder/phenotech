"use client";

// Devon's diagnosis page, in the spec's order. The same layout serves a disease mapped in depth
// (/disease/<id>) and any other rare disease (/d/<id>); builders fill a DevonModel from real data only.
import Link from "next/link";
import { useState } from "react";
import { PlainText } from "../PlainText";
import {
  Checklist,
  ContactCard,
  ContributeLine,
  DevonSection,
  DoctorQuestions,
  HowWeKnow,
  LearnMore,
  SafetyNote,
  StudyCard,
  type Contact,
  type How,
  type SourceLink,
  type Study,
} from "./DevonBits";

export interface DevonModel {
  name: string;
  /** short name for sentences: the gene, or the disease name */
  short: string;
  plain: { text: string; how?: How }[];
  approved?: { text: string; how?: How } | null;
  people: { text: string | null; how?: How; groups: number };
  groups: Contact[];
  umbrella: Contact[];
  registries: Contact[];
  studies: Study[];
  /** total open studies we know about (may exceed the cards shown) */
  openStudies: number;
  studiesMoreUrl?: string | null;
  questions: string[];
  sources: SourceLink[];
  related: Contact[];
  contributeHref: string;
  /** loading flags for optional layers, so the page can say "loading" rather than "none" */
  loading?: boolean;
}

/** Shows the first few cards; the rest wait behind one calm button. */
function MoreList<T>({ items, first, noun, plural, render }: { items: T[]; first: number; noun: string; plural?: string; render: (x: T) => React.ReactNode }) {
  const [all, setAll] = useState(false);
  const rest = items.length - first;
  return (
    <>
      <ul className="space-y-3">{(all ? items : items.slice(0, first)).map(render)}</ul>
      {rest > 0 && (
        <button
          type="button"
          onClick={() => setAll((a) => !a)}
          className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-4 text-[15px] text-ink-2 hover:border-accent-500 hover:text-ink"
        >
          {all ? "Show fewer" : `Show ${rest} more ${rest === 1 ? noun : (plural ?? `${noun}s`)}`}
        </button>
      )}
    </>
  );
}

export function DevonPage({ m, learnMore }: { m: DevonModel; learnMore?: React.ReactNode }) {
  const hasGroup = m.groups.length > 0;
  const firstGroup = m.groups[0];
  const firstRegistry = m.registries[0];
  const week: { key: string; text: React.ReactNode }[] = [];
  if (firstGroup)
    week.push({
      key: "group",
      text: (
        <>
          Get in touch with <b className="font-medium">{firstGroup.name}</b>, a group for families living with this diagnosis.
        </>
      ),
    });
  else if (m.umbrella[0] || m.related[0])
    week.push({
      key: "community",
      text: (
        <>
          Reach out to <b className="font-medium">{(m.umbrella[0] ?? m.related[0]).name}</b>, the closest community we found.
        </>
      ),
    });
  if (firstRegistry)
    week.push({
      key: "registry",
      text: (
        <>
          Ask about joining <b className="font-medium">{firstRegistry.name}</b>. Registries help researchers learn about the condition.
        </>
      ),
    });
  if (m.openStudies > 0)
    week.push({
      key: "studies",
      text: (
        <>
          Look at the {m.openStudies === 1 ? "study" : `${m.openStudies} studies`} looking for participants now (
          <a href="#studies" className="text-accent-700 underline underline-offset-4">
            below
          </a>
          ).
        </>
      ),
    });
  week.push({
    key: "doctor",
    text: (
      <>
        Write down your questions and take them to your next appointment (
        <a href="#questions" className="text-accent-700 underline underline-offset-4">
          ours are below
        </a>
        ).
      </>
    ),
  });

  return (
    <div className="mx-auto w-full max-w-[720px] space-y-10 px-4 pb-24 pt-6 sm:px-6 sm:pt-10">
      <header>
        <p className="text-sm text-ink-3">Your diagnosis</p>
        <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-[-0.01em] text-ink sm:text-[32px]">{m.name}</h1>
        <div className="mt-4">
          <SafetyNote />
        </div>
      </header>

      <DevonSection id="plain" title="What this means, in plain words">
        {m.plain.map((p, i) => (
          <p key={i}>
            <PlainText text={p.text} /> {p.how && <HowWeKnow how={p.how} />}
          </p>
        ))}
        {m.approved && (
          <p className="rounded-lg bg-subtle px-4 py-3 text-ink">
            {m.approved.text} <HowWeKnow how={m.approved.how} />
          </p>
        )}
      </DevonSection>

      <DevonSection id="not-alone" title="You are not alone">
        {m.people.text ? (
          <p>
            {m.people.text}{" "}
            <span className="rounded-full border border-line px-2 py-0.5 align-middle text-xs text-ink-3">estimated</span>{" "}
            <HowWeKnow how={m.people.how} />
          </p>
        ) : (
          <p>
            {m.loading ? "Looking up how many people live with this…" : "We don’t have a reliable count of how many people live with this yet."}{" "}
            <HowWeKnow how={m.people.how} />
          </p>
        )}
        {m.people.groups > 0 && (
          <p>
            {m.people.groups === 1 ? "One patient group supports" : `${m.people.groups} patient groups support`} families with this diagnosis.
          </p>
        )}
      </DevonSection>

      <DevonSection id="contact" title="People you can contact">
        {hasGroup ? (
          <MoreList items={m.groups} first={3} noun="group" render={(c) => <ContactCard key={c.key} c={c} />} />
        ) : (
          <p>{m.loading ? "Looking for patient groups…" : "We didn’t find a patient group just for this diagnosis (see below)."}</p>
        )}
        {m.registries.length > 0 && (
          <>
            <h3 className="pt-3 text-[18px] font-semibold text-ink" data-tour="registries">
              Registries you could join
            </h3>
            <p className="text-[15px]">A registry collects information from families, with their permission, so researchers can learn more.</p>
            <MoreList items={m.registries} first={2} noun="registry" plural="registries" render={(c) => <ContactCard key={c.key} c={c} cta="Learn about joining" />} />
          </>
        )}
        {hasGroup && <ContributeLine href={m.contributeHref} />}
      </DevonSection>

      <DevonSection id="this-week" title="Things you can do this week">
        <Checklist items={week} />
      </DevonSection>

      <DevonSection id="questions" title="Questions to bring to your doctor">
        <DoctorQuestions name={m.name} questions={m.questions} sources={m.sources} />
      </DevonSection>

      <DevonSection id="studies" title="Studies looking for participants">
        {m.studies.length ? (
          <>
            <ul className="space-y-3">
              {m.studies.map((s) => (
                <StudyCard key={s.key} s={s} />
              ))}
            </ul>
            {m.openStudies > m.studies.length && m.studiesMoreUrl && (
              <a href={m.studiesMoreUrl} target="_blank" rel="noopener noreferrer" className="inline-block text-[15px] text-accent-700 hover:underline">
                See all {m.openStudies} open studies on ClinicalTrials.gov ↗
              </a>
            )}
          </>
        ) : (
          <p>
            {m.loading ? "Looking for studies…" : "We didn’t find a study recruiting for this diagnosis right now."}{" "}
            {m.studiesMoreUrl && (
              <a href={m.studiesMoreUrl} target="_blank" rel="noopener noreferrer" className="text-accent-700 underline underline-offset-4">
                Search ClinicalTrials.gov yourself ↗
              </a>
            )}
          </p>
        )}
      </DevonSection>

      {!hasGroup && !m.loading && (
        <DevonSection id="no-group" title="If there’s no group yet">
          <p>We didn’t find a group just for this diagnosis. That happens with very rare conditions, and it is not your fault.</p>
          {m.umbrella.length + m.related.length > 0 ? (
            <>
              <p>These are the closest communities we found:</p>
              <ul className="space-y-3" data-tour="closest-community">
                {[...m.umbrella, ...m.related]
                  .filter((c, i, all) => all.findIndex((x) => x.name === c.name) === i)
                  .slice(0, 4)
                  .map((c) => (
                  <ContactCard key={c.key} c={c} />
                ))}
              </ul>
            </>
          ) : (
            <p>We didn’t find a close community either.</p>
          )}
          <p data-tour="help-build">
            Many groups started with a few families finding each other. If you know of a group, or start one,{" "}
            <Link href={m.contributeHref} className="font-medium text-accent-700 hover:underline">
              tell us so the next family finds it →
            </Link>
          </p>
        </DevonSection>
      )}

      {learnMore && <LearnMore>{learnMore}</LearnMore>}
    </div>
  );
}
