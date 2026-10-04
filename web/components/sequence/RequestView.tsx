"use client";

// /sequence/request: "Don't have a DNA file? Request one". A short guided flow for families:
//   1. Have you already had a genetic test? Yes / No / Not sure
//   Yes      → which files to ask for, how each lab releases data (lab cards), your rights and an
//              editable request letter (copy / print), labelled general information, not legal advice.
//   No       → a doctor or genetic counsellor first, then sponsored and research programmes by region,
//              and what consumer tests can and can't tell you.
//   Not sure → questions to ask your doctor.
// Content comes from data/curated/testing_options.json (every item sourced, quotes string-verified).
// No companies are named beyond that file.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { loadAvailableOnce } from "@/lib/population";
import { useResource } from "@/lib/resource";

interface Source {
  url: string;
  quotes?: string[];
  retrieved?: string;
  source_note?: string;
}
interface FileType {
  format: string;
  plain: string;
  source?: Source;
}
interface Lab {
  id: string;
  lab: string;
  region: string;
  what_they_provide?: string[];
  who_can_ask?: string;
  how_to_request?: string;
  cost_as_stated?: string;
  caveats?: string;
  invitae_note?: string;
  source: Source;
  extra_sources?: Source[];
}
interface Right {
  id: string;
  name: string;
  region: string;
  plain: string;
  source: Source;
  extra_sources?: Source[];
}
interface Route {
  id: string;
  route_type: string;
  name: string;
  organisation?: string;
  region: string[];
  also_covers?: string;
  status?: string;
  referral_needed?: "yes" | "no" | string;
  referral_note?: string;
  eligibility_in_source_words?: string;
  sponsorship_as_stated?: string;
  data_sharing_as_stated?: string;
  counselling_as_stated?: string;
  source: Source;
  extra_sources?: Source[];
}
interface Section {
  id: string;
  title: string;
  summary: string;
  file_types?: FileType[];
  labs?: Lab[];
  rights?: Right[];
  request_letter_template?: { label: string; title: string; how_to_use: string; body: string };
  route_types?: Record<string, string>;
  routes?: Route[];
  not_recommendations?: string;
  points?: { plain: string; source: Source }[];
}
export interface TestingOptions {
  meta: { title: string; retrieved: string; disclaimer: string; legal_note: string; verification: string };
  sections: Section[];
}

async function loadTesting(): Promise<TestingOptions | null> {
  const a = await loadAvailableOnce();
  if (!a.testing_options) return null;
  const r = await fetch("/data/curated/testing_options.json");
  return r.ok ? ((await r.json()) as TestingOptions) : null;
}

/** Opens a plain page with just this text and the print dialog (so the site menus are not printed). */
function printText(title: string, text: string) {
  const w = window.open("", "_blank", "width=800,height=900");
  if (!w) return window.print();
  const esc = (x: string) => x.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
  w.document.write(
    `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title></head><body style="margin:2.5cm;font:12pt/1.55 Georgia,serif;color:#000"><pre style="white-space:pre-wrap;font:inherit">${esc(text)}</pre></body></html>`,
  );
  w.document.close();
  w.focus();
  w.print();
}

type Answer = "yes" | "no" | "unsure";
const ANSWERS: [Answer, string, string][] = [
  ["yes", "Yes", "A gene panel, exome or genome through a doctor or hospital"],
  ["no", "No", "Not yet, or only a consumer DNA kit"],
  ["unsure", "Not sure", "We’ll help you find out"],
];
const REGIONS = ["All", "US", "UK", "EU"] as const;
type Region = (typeof REGIONS)[number];

const BTN = "inline-flex min-h-[44px] items-center justify-center rounded-lg px-4 text-[15px] font-medium";
const H2 = "text-[21px] font-semibold text-ink";
const host = (u: string) => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
};

function SourceLinks({ source, extra }: { source: Source; extra?: Source[] }) {
  const all = [source, ...(extra ?? [])];
  const quotes = all.flatMap((s) => (s.quotes ?? []).filter((q) => q.length > 25 && !/^Content current as of/.test(q)).map((q) => ({ q, url: s.url })));
  return (
    <div className="mt-3 text-sm">
      <p className="flex flex-wrap gap-x-3 gap-y-1">
        <span className="text-ink-3">Source:</span>
        {all.map((s, i) => {
          const h = host(s.url);
          const n = all.slice(0, i + 1).filter((x) => host(x.url) === h).length;
          return (
            <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="break-all text-accent-700 underline">
              {h}
              {n > 1 ? ` (page ${n})` : ""} ↗
            </a>
          );
        })}
      </p>
      {quotes.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-ink-3 hover:text-ink">What the page says</summary>
          <ul className="mt-2 space-y-1.5 border-l-2 border-line pl-3 text-ink-2">
            {quotes.map((x) => (
              <li key={x.q}>“{x.q}”</li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-ink-3">Quoted word for word{source.retrieved ? ` on ${source.retrieved}` : ""}. Check the page before relying on it.</p>
        </details>
      )}
    </div>
  );
}

function RegionPicker({ value, onChange, label }: { value: Region; onChange: (r: Region) => void; label: string }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      <span className="text-sm text-ink-3">{label}</span>
      {REGIONS.map((r) => (
        <button
          key={r}
          type="button"
          aria-pressed={value === r}
          onClick={() => onChange(r)}
          className={`min-h-[36px] rounded-full border px-3 text-sm ${value === r ? "border-accent-700 bg-accent-50 font-medium text-accent-900" : "border-line text-ink-2 hover:border-accent-500"}`}
        >
          {r === "All" ? "Everywhere" : r}
        </button>
      ))}
    </div>
  );
}

const labIn = (l: Lab, r: Region) => r === "All" || l.region.startsWith(r);
const routeIn = (x: Route, r: Region) => r === "All" || x.region.includes(r) || x.region.includes("worldwide");
const rightIn = (x: Right, r: Region) => r === "All" || x.region === r;

export function RequestView() {
  const params = useSearchParams();
  const initial = params.get("a");
  const [answer, setAnswer] = useState<Answer | null>(initial === "yes" || initial === "no" || initial === "unsure" ? initial : null);
  const [region, setRegion] = useState<Region>("All");
  const res = useResource<TestingOptions | null>("testing-options", loadTesting);
  const data = res?.data ?? null;
  const sec = useMemo(() => Object.fromEntries((data?.sections ?? []).map((s) => [s.id, s])) as Record<string, Section | undefined>, [data]);

  const choose = (a: Answer) => {
    setAnswer(a);
    try {
      window.history.replaceState(null, "", `?a=${a}`);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="mx-auto w-full max-w-[760px] px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
      <p className="text-sm">
        <Link href="/sequence" className="text-accent-700 hover:underline">
          ← Check a DNA sequence or VCF file
        </Link>
      </p>
      <h1 className="mt-3 text-[28px] font-semibold leading-tight text-ink sm:text-[32px]">{data?.meta.title ?? "Don’t have a DNA file? Request one"}</h1>
      <p className="mt-3 text-[16px] leading-relaxed text-ink-2">
        If your family has had a genetic test, the lab usually still holds the data behind the report, and you can ask for a copy. If not, here are the
        usual ways to get tested.
      </p>
      <p className="mt-2 text-sm text-ink-3">{data?.meta.disclaimer ?? "Information only. Talk to your doctor or a genetic counsellor about which test is right."}</p>

      <section aria-labelledby="q1" className="mt-8">
        <h2 id="q1" className={H2}>
          Have you already had a genetic test?
        </h2>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {ANSWERS.map(([id, label, hint]) => (
            <button
              key={id}
              type="button"
              aria-pressed={answer === id}
              onClick={() => choose(id)}
              className={`rounded-xl border px-4 py-3 text-left ${answer === id ? "border-accent-700 bg-accent-50" : "border-line hover:border-accent-500"}`}
            >
              <span className="block text-[17px] font-semibold text-ink">{label}</span>
              <span className="mt-0.5 block text-sm text-ink-3">{hint}</span>
            </button>
          ))}
        </div>
      </section>

      {answer && !data && res?.status !== "loading" && (
        <p className="mt-8 rounded-lg bg-subtle px-4 py-3 text-[15px] text-ink-2">
          The detailed guide isn’t in this version of the site yet. A doctor or genetic counsellor can tell you which test you had and how to get a copy of
          the data.
        </p>
      )}

      {answer === "yes" && sec.get_your_data && <HaveTest s={sec.get_your_data} legal={data?.meta.legal_note ?? ""} region={region} setRegion={setRegion} />}
      {answer === "no" && sec.if_no_testing && <NoTest s={sec.if_no_testing} consumer={sec.consumer_tests} region={region} setRegion={setRegion} />}
      {answer === "unsure" && (
        <NotSure
          onPick={(a) => {
            choose(a);
            document.getElementById("q1")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      )}

      {data && (
        <p className="mt-12 border-t border-line pt-4 text-xs leading-relaxed text-ink-3">
          {data.meta.verification} Checked {data.meta.retrieved}.
        </p>
      )}
    </div>
  );
}

function HaveTest({ s, legal, region, setRegion }: { s: Section; legal: string; region: Region; setRegion: (r: Region) => void }) {
  const labs = (s.labs ?? []).filter((l) => labIn(l, region));
  const rights = (s.rights ?? []).filter((r) => rightIn(r, region));
  return (
    <div className="mt-10 space-y-10">
      <section aria-labelledby="have-h">
        <h2 id="have-h" className={H2}>
          {s.title}
        </h2>
        <p className="mt-2 text-[16px] leading-relaxed text-ink-2">{s.summary}</p>
        {s.file_types?.length ? (
          <>
            <h3 className="mt-6 text-[17px] font-semibold text-ink">Which files to ask for</h3>
            <dl className="mt-2 divide-y divide-line-2 border-y border-line-2">
              {s.file_types.map((f) => (
                <div key={f.format} className="grid gap-1 py-3 sm:grid-cols-[90px_minmax(0,1fr)]">
                  <dt className="font-mono text-[15px] font-semibold text-ink">{f.format}</dt>
                  <dd className="text-[15px] text-ink-2">
                    {f.plain}
                    {f.source && (
                      <a href={f.source.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-sm text-accent-700 underline">
                        {host(f.source.url)} ↗
                      </a>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-sm text-ink-3">
              A VCF is the file{" "}
              <Link href="/sequence" className="text-accent-700 underline">
                the sequence checker
              </Link>{" "}
              reads, in your browser.
            </p>
          </>
        ) : null}
      </section>

      <section aria-labelledby="labs-h">
        <h2 id="labs-h" className={H2}>
          How labs release data
        </h2>
        <p className="mt-1 text-[15px] text-ink-3">What each lab’s own pages say. Your lab may not be listed: ask the doctor who ordered the test.</p>
        <RegionPicker value={region} onChange={setRegion} label="Where was the test done?" />
        {labs.length ? (
          <ul className="mt-4 space-y-3">
            {labs.map((l) => (
              <li key={l.id} className="rounded-xl border border-line px-4 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <h3 className="text-[17px] font-semibold text-ink">{l.lab}</h3>
                  <span className="text-sm text-ink-3">{l.region}</span>
                </div>
                {l.what_they_provide?.length ? (
                  <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Files they provide">
                    {l.what_they_provide.map((w) => (
                      <li key={w} className="rounded-full bg-subtle px-2.5 py-0.5 text-sm text-ink-2">
                        {w}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <dl className="mt-3 space-y-2 text-[15px]">
                  {l.who_can_ask && (
                    <div>
                      <dt className="font-medium text-ink">Who can ask</dt>
                      <dd className="text-ink-2">{l.who_can_ask}</dd>
                    </div>
                  )}
                  {l.how_to_request && (
                    <div>
                      <dt className="font-medium text-ink">How to ask</dt>
                      <dd className="text-ink-2">{l.how_to_request}</dd>
                    </div>
                  )}
                  {l.cost_as_stated && (
                    <div>
                      <dt className="font-medium text-ink">Cost, as stated</dt>
                      <dd className="text-ink-2">{l.cost_as_stated}</dd>
                    </div>
                  )}
                  {l.caveats && (
                    <div>
                      <dt className="font-medium text-ink">Good to know</dt>
                      <dd className="text-ink-2">{l.caveats}</dd>
                    </div>
                  )}
                  {l.invitae_note && <dd className="text-sm text-ink-3">{l.invitae_note}</dd>}
                </dl>
                <SourceLinks source={l.source} extra={l.extra_sources} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-[15px] text-ink-3">No lab pages for this region in our list yet. The doctor who ordered the test can request the data for you.</p>
        )}
      </section>

      {s.rights?.length ? (
        <section aria-labelledby="rights-h">
          <h2 id="rights-h" className={H2}>
            Your rights
          </h2>
          <p className="mt-1 text-sm font-medium text-warn-ink">{legal || "General information, not legal advice."}</p>
          {rights.length ? (
            <ul className="mt-3 space-y-3">
              {rights.map((r) => (
                <li key={r.id} className="rounded-xl border border-line px-4 py-4">
                  <h3 className="text-[16px] font-semibold text-ink">{r.name}</h3>
                  <p className="mt-1 text-[15px] leading-relaxed text-ink-2">{r.plain}</p>
                  <SourceLinks source={r.source} extra={r.extra_sources} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[15px] text-ink-3">We have not described the rules for this region. Choose “Everywhere” to see the ones we have.</p>
          )}
        </section>
      ) : null}

      {s.request_letter_template && <Letter t={s.request_letter_template} />}
    </div>
  );
}

function Letter({ t }: { t: NonNullable<Section["request_letter_template"]> }) {
  const [text, setText] = useState(t.body);
  const [copied, setCopied] = useState(false);
  return (
    <section aria-labelledby="letter-h">
      <h2 id="letter-h" className={H2}>
        A letter you can send
      </h2>
      <p className="mt-1 text-sm font-medium text-warn-ink">{t.label}</p>
      <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{t.how_to_use}</p>
      <label className="mt-3 block">
        <span className="sr-only">{t.title}</span>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setCopied(false);
          }}
          rows={18}
          spellCheck
          className="w-full rounded-xl border border-line bg-white px-4 py-3 font-mono text-[14px] leading-relaxed text-ink"
        />
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
            } catch {
              setCopied(false);
            }
          }}
          className={`${BTN} bg-accent-700 text-white hover:bg-accent-900`}
        >
          {copied ? "Copied" : "Copy the letter"}
        </button>
        <button type="button" onClick={() => printText(t.title, text)} className={`${BTN} border border-line text-ink-2`}>
          Print
        </button>
        {text !== t.body && (
          <button type="button" onClick={() => setText(t.body)} className={`${BTN} text-ink-3 underline`}>
            Start again
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-ink-3">Your edits stay in this page; nothing is sent or saved.</p>
    </section>
  );
}

function RouteCard({ x }: { x: Route }) {
  return (
    <li className="rounded-xl border border-line px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h4 className="text-[17px] font-semibold text-ink">{x.name}</h4>
        <span className="text-sm text-ink-3">
          {x.region.join(", ")}
          {x.also_covers ? `, ${x.also_covers}` : ""}
        </span>
      </div>
      {x.organisation && <p className="text-sm text-ink-3">{x.organisation}</p>}
      {x.status && <p className="mt-2 rounded-lg border border-warn-line bg-warn-bg px-3 py-1.5 text-sm text-warn-ink">Status: {x.status}</p>}
      <p className="mt-2 text-[15px] font-medium text-ink">{x.referral_needed === "yes" ? "A doctor needs to be involved" : x.referral_needed === "no" ? "You can contact them yourself" : ""}</p>
      {x.referral_note && <p className="text-[15px] text-ink-2">{x.referral_note}</p>}
      <dl className="mt-2 space-y-2 text-[15px]">
        {x.eligibility_in_source_words && (
          <div>
            <dt className="font-medium text-ink">Who it’s for, in their words</dt>
            <dd className="text-ink-2">“{x.eligibility_in_source_words}”</dd>
          </div>
        )}
        {x.sponsorship_as_stated && (
          <div>
            <dt className="font-medium text-ink">Who pays</dt>
            <dd className="text-ink-2">“{x.sponsorship_as_stated}”</dd>
          </div>
        )}
        {x.data_sharing_as_stated && x.data_sharing_as_stated !== x.eligibility_in_source_words && (
          <div>
            <dt className="font-medium text-ink">What happens to the data</dt>
            <dd className="text-ink-2">“{x.data_sharing_as_stated}”</dd>
          </div>
        )}
        {x.counselling_as_stated && (
          <div>
            <dt className="font-medium text-ink">Support with results</dt>
            <dd className="text-ink-2">“{x.counselling_as_stated}”</dd>
          </div>
        )}
      </dl>
      <SourceLinks source={x.source} extra={x.extra_sources} />
    </li>
  );
}

function NoTest({ s, consumer, region, setRegion }: { s: Section; consumer?: Section; region: Region; setRegion: (r: Region) => void }) {
  const order = ["doctor_or_counsellor", "sponsored_no_cost", "research"];
  const routes = (s.routes ?? []).filter((x) => routeIn(x, region));
  const intro: Record<string, string> = {
    doctor_or_counsellor: "Start here. A doctor or genetic counsellor can tell you which test fits, order it, and explain the result.",
    sponsored_no_cost: "Some testing is free because a company or charity pays for it. A doctor usually orders it, and the sponsor may receive data without your name.",
    research: "Research programmes can test families when routine tests found nothing. Places are limited.",
  };
  return (
    <div className="mt-10 space-y-10">
      <section aria-labelledby="no-h">
        <h2 id="no-h" className={H2}>
          {s.title}
        </h2>
        <p className="mt-2 text-[16px] leading-relaxed text-ink-2">{s.summary}</p>
        <RegionPicker value={region} onChange={setRegion} label="Where do you live?" />
      </section>
      {order.map((type, i) => {
        const list = routes.filter((x) => x.route_type === type);
        return (
          <section key={type} aria-labelledby={`route-${type}`}>
            <h3 id={`route-${type}`} className="text-[19px] font-semibold text-ink">
              {i + 1}. {s.route_types?.[type] ?? type}
            </h3>
            <p className="mt-1 text-[15px] text-ink-2">{intro[type]}</p>
            {list.length ? (
              <ul className="mt-3 space-y-3">
                {list.map((x) => (
                  <RouteCard key={x.id} x={x} />
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-[15px] text-ink-3">Nothing listed for this region yet. Your doctor can tell you what is available locally.</p>
            )}
          </section>
        );
      })}
      {consumer && (
        <section aria-labelledby="consumer-h" className="rounded-xl border border-warn-line bg-warn-bg px-4 py-4 sm:px-5">
          <h3 id="consumer-h" className="text-[18px] font-semibold text-warn-ink">
            {consumer.title}
          </h3>
          <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{consumer.summary}</p>
          <ul className="mt-3 space-y-3">
            {(consumer.points ?? []).map((p) => (
              <li key={p.plain} className="text-[15px] text-ink-2">
                {p.plain}
                <a href={p.source.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-sm text-accent-700 underline">
                  {host(p.source.url)} ↗
                </a>
              </li>
            ))}
          </ul>
          {consumer.not_recommendations && <p className="mt-3 text-sm font-medium text-warn-ink">{consumer.not_recommendations}</p>}
        </section>
      )}
    </div>
  );
}

function NotSure({ onPick }: { onPick: (a: Answer) => void }) {
  const qs = [
    "Has my child (or have I) had a genetic test? Which kind: a gene panel, an exome or a genome?",
    "Which lab did the test, and when? Is there a reference number?",
    "Can I have a copy of the report?",
    "Can the lab send us the data files too, such as the VCF? Who needs to ask for them?",
    "If no test was done: would one help, and which one? Could we see a genetic counsellor?",
    "If the test found nothing: is it worth looking at the data again, or joining a research programme?",
  ];
  return (
    <section aria-labelledby="unsure-h" className="mt-10">
      <h2 id="unsure-h" className={H2}>
        Questions to ask your doctor
      </h2>
      <p className="mt-2 text-[16px] leading-relaxed text-ink-2">Genetic tests are often ordered in hospital, and families aren’t always told. These questions help find out.</p>
      <ol className="mt-4 space-y-2">
        {qs.map((q, i) => (
          <li key={q} className="grid grid-cols-[26px_minmax(0,1fr)] gap-1 text-[16px] text-ink">
            <span className="tabular-nums text-ink-3">{i + 1}.</span>
            <span>{q}</span>
          </li>
        ))}
      </ol>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={() => printText("Questions to ask your doctor", ["Questions to ask your doctor", "", ...qs.map((q, i) => `${i + 1}. ${q}`), "", "Notes:"].join("\n"))} className={`${BTN} border border-line text-ink-2`}>
          Print these questions
        </button>
      </div>
      <p className="mt-6 text-[15px] text-ink-2">
        Found out?{" "}
        <button type="button" onClick={() => onPick("yes")} className="font-medium text-accent-700 underline">
          We had a test
        </button>{" "}
        ·{" "}
        <button type="button" onClick={() => onPick("no")} className="font-medium text-accent-700 underline">
          No test yet
        </button>
      </p>
    </section>
  );
}
