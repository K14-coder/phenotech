"use client";

import Link from "next/link";
import { useDerived, type ResearchRecsData, type ResearchRecDisease } from "@/lib/derived";
import { diseaseHref } from "@/lib/graph";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";
const CARD = "rounded-lg border border-line px-5 py-4";
const LABEL = "text-xs font-semibold uppercase tracking-[0.06em] text-ink-3";

const MARKER_LABEL: Record<string, string> = {
  mutation: "Mutation type",
  fate: "Molecular consequence",
  structure: "3D structure",
};
const FATE_TEXT: Record<string, string> = {
  absent: "no protein made",
  degraded: "unstable protein",
  inactive: "inactive protein",
  dominant_negative: "dominant-negative protein",
  hyperactive: "overactive protein",
  accumulates: "accumulating protein",
};

const pct = (x: number) => `${Math.round(x * 100)}`;

/** Closest atlas disease per category (mechanism, funding, tissue / delivery, symptoms), computed offline by
 *  pipeline/derive/research_recs.py. Everything here is inferred; treatment ideas are for the clinician. */
export function ResearchRecommendations({ diseaseId, short }: { diseaseId: string; short: string }) {
  const data = useDerived<ResearchRecsData>("research");
  if (data.status !== "ready") return null;
  const gene = diseaseId.replace(/^disease:/, "");
  const rec = data.data.diseases[gene];
  if (!rec) return null;
  const labelOf = (g: string) => data.data.diseases[g]?.label ?? g;
  return (
    <section id="research-recs" aria-labelledby="research-recs-h" className="scroll-mt-20">
      <p className={EYEBROW}>Computed suggestions</p>
      <h2 id="research-recs-h" className={`mt-1 ${H2}`}>
        Research recommendations <span className="text-ink-3">(inferred, not evidence)</span>
      </h2>
      <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-3">
        The closest disease in the atlas for four different questions. Mechanism means how the gene breaks: what kind of mutations,
        what happens to the protein, and how alike the protein structures are. Each card says why.{" "}
        <Link href="/mechanisms" className="font-medium text-accent-700 hover:underline">
          Full rankings →
        </Link>
      </p>
      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <MechanisticCard rec={rec} />
        <FundingCard rec={rec} short={short} />
        <TissueCard rec={rec} short={short} />
        <SymptomCard rec={rec} />
      </div>
      <StructureNote rec={rec} />
      {rec.cluster && rec.cluster.size > 1 && (
        <p className="mt-3 text-sm text-ink-2">
          <span className="text-ink-3">Mechanistic cluster: </span>
          {rec.cluster.members
            .filter((g) => g !== gene)
            .map((g, i, arr) => (
              <span key={g}>
                <Link href={diseaseHref(`disease:${g}`)} className="text-accent-700 hover:underline" title={labelOf(g)}>
                  {g}
                </Link>
                {i < arr.length - 1 ? ", " : ""}
              </span>
            ))}
          <span className="text-ink-3"> (average linkage on mechanistic closeness ≥ {data.data.meta.cluster_min})</span>
        </p>
      )}
      <p className="mt-3 max-w-[760px] text-xs leading-relaxed text-ink-3">{data.data.meta.not_advice}</p>
    </section>
  );
}

function Partner({ gene, label, score, scoreLabel }: { gene: string; label: string; score: number; scoreLabel: string }) {
  return (
    <p className="mt-1.5">
      <Link href={diseaseHref(`disease:${gene}`)} className="text-[15px] font-semibold text-accent-700 hover:underline">
        {label}
      </Link>
      <span className="ml-2 text-xs text-ink-3">
        {scoreLabel} {score.toFixed(2)}
      </span>
    </p>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-sm text-ink-3">{children}</p>;
}

function MechanisticCard({ rec }: { rec: ResearchRecDisease }) {
  const m = rec.best.mechanistic;
  return (
    <div className={CARD}>
      <p className={LABEL}>Closest by mechanism</p>
      {m ? (
        <>
          <Partner gene={m.partner} label={m.partner_label} score={m.score} scoreLabel="closeness" />
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{m.explanation}</p>
          <table className="mt-3 w-full text-left text-xs">
            <thead className="text-ink-3">
              <tr className="border-b border-line">
                <th className="py-1 pr-2 font-medium">Marker</th>
                <th className="py-1 pr-2 font-medium">Weight</th>
                <th className="py-1 pr-2 font-medium">Raw</th>
                <th className="py-1 font-medium">Percentile</th>
              </tr>
            </thead>
            <tbody className="text-ink-2">
              {(["mutation", "fate", "structure"] as const).map((k) => {
                const mk = m.markers[k];
                return (
                  <tr key={k} className="border-b border-line align-top">
                    <td className="py-1.5 pr-2">
                      {MARKER_LABEL[k]}
                      {k === "fate" && mk?.a && (
                        <span className="block text-ink-3">
                          {FATE_TEXT[mk.a] ?? mk.a} vs {FATE_TEXT[mk.b ?? ""] ?? mk.b}
                        </span>
                      )}
                      {k === "structure" && mk?.model_a && (
                        <span className="block text-ink-3">
                          TM-score: {mk.model_a} vs {mk.model_b}
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2">{m.weights[k].toFixed(2)}</td>
                    <td className="py-1.5 pr-2">{mk ? mk.raw.toFixed(2) : "–"}</td>
                    <td className="py-1.5">{mk ? `${pct(mk.pct)}%` : "not scored"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {m.missing.length > 0 && (
            <p className="mt-2 text-xs text-ink-3">Missing markers are left out and the other weights renormalised; no value is filled in.</p>
          )}
        </>
      ) : (
        <Empty>No atlas disease could be scored on these markers.</Empty>
      )}
    </div>
  );
}

function FundingCard({ rec, short }: { rec: ResearchRecDisease; short: string }) {
  const f = rec.best.funding;
  return (
    <div className={CARD}>
      <p className={LABEL}>Closest by signalling pathway (funding)</p>
      {f ? (
        <>
          <Partner gene={f.partner} label={f.partner_label} score={f.score} scoreLabel="pathway overlap" />
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{f.explanation}</p>
          {f.partner_funders_missing.length > 0 ? (
            <p className="mt-2 text-sm text-ink-2">
              <span className="text-ink-3">Funds {f.partner} work but not yet {short} work: </span>
              {f.partner_funders_missing.map((x, i) => (
                <span key={x.funder}>
                  {x.records[0]?.url ? (
                    <a href={x.records[0].url} target="_blank" rel="noreferrer" className="text-accent-700 hover:underline" title={x.records[0].title ?? ""}>
                      {x.funder}
                    </a>
                  ) : (
                    x.funder
                  )}
                  {x.n > 1 ? ` (${x.n})` : ""}
                  {i < f.partner_funders_missing.length - 1 ? ", " : ""}
                </span>
              ))}
            </p>
          ) : (
            <p className="mt-2 text-sm text-ink-3">The atlas has no funder record for {f.partner} that {short} lacks.</p>
          )}
          {f.funders_via_pathway_partners.length > 0 && (
            <p className="mt-1.5 text-xs text-ink-3">
              Other candidate funders through pathway neighbours:{" "}
              {f.funders_via_pathway_partners
                .slice(0, 5)
                .map((x) => `${x.funder} (via ${x.via.slice(0, 3).join(", ")})`)
                .join("; ")}
            </p>
          )}
        </>
      ) : (
        <Empty>No atlas disease shares a canonical pathway with {short}.</Empty>
      )}
    </div>
  );
}

function TissueCard({ rec, short }: { rec: ResearchRecDisease; short: string }) {
  const t = rec.best.tissue;
  const d = rec.delivery;
  return (
    <div className={CARD}>
      <p className={LABEL}>Closest by tissue (drug delivery)</p>
      {t ? (
        <>
          <Partner gene={t.partner} label={t.partner_label} score={t.score} scoreLabel="tissue match" />
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{t.explanation}</p>
        </>
      ) : (
        <Empty>No tissue match could be scored.</Empty>
      )}
      <div className="mt-3 rounded-md bg-subtle px-3 py-2.5 text-sm text-ink-2">
        <p>
          <span className="font-medium">Delivery for {short}: {d.class}</span>
          <span className="text-ink-3"> (rule-based, inferred)</span>
        </p>
        <ul className="mt-1 list-disc pl-5 text-ink-2">
          {d.options.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
        {d.aav_cds_fits !== null && (
          <p className="mt-1 text-xs text-ink-3">
            {d.aav_cds_fits
              ? `Coding sequence (${d.cds_length_bp?.toLocaleString()} bp) fits one AAV vector.`
              : `Coding sequence (${d.cds_length_bp?.toLocaleString()} bp) is too long for one AAV vector (~4.7 kb): dual vectors, ASO or editing instead.`}
          </p>
        )}
      </div>
    </div>
  );
}

function SymptomCard({ rec }: { rec: ResearchRecDisease }) {
  const s = rec.best.symptoms;
  return (
    <div className={CARD}>
      <p className={LABEL}>Closest by symptoms</p>
      {s ? (
        <>
          <Partner gene={s.partner} label={s.partner_label} score={s.score} scoreLabel="symptom overlap" />
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{s.explanation}</p>
          {s.shared_distinctive.length > 0 && (
            <p className="mt-2 text-xs leading-relaxed text-ink-3">
              Shared distinctive features: {s.shared_distinctive.slice(0, 6).map((t) => t.name).join(", ")}
            </p>
          )}
        </>
      ) : (
        <Empty>No shared HPO features with another atlas disease.</Empty>
      )}
    </div>
  );
}

function StructureNote({ rec }: { rec: ResearchRecDisease }) {
  const s = rec.structure_model;
  return (
    <p className="mt-4 max-w-[860px] text-xs leading-relaxed text-ink-3">
      <span className="font-medium text-ink-2">Structure used for {rec.gene}: </span>
      {s.kind === "experimental_mutant" ? (
        <>
          experimental PDB structure{" "}
          <a href={`https://www.rcsb.org/structure/${s.pdb_entity?.split("_")[0]}`} target="_blank" rel="noreferrer" className="text-accent-700 hover:underline">
            {s.pdb_entity}
          </a>{" "}
          carrying the ClinVar pathogenic change {s.mutations?.join(", ")}
          {s.engineered_mutations?.length ? ` (plus engineered ${s.engineered_mutations.join(", ")})` : ""}, residues {s.residues?.[0]}–{s.residues?.[1]}.
        </>
      ) : (
        <>
          {s.label}; mutant model {s.mutant_model}.
        </>
      )}
      {s.note ? ` ${s.note}.` : ""}
    </p>
  );
}
