"use client";

// /mechanisms: compare diseases on six mechanistic axes (data/derived/mechsim.json, pipeline/derive/mechsim.py).
// Same genes · same pathway · same tissue · same mutation types · same protein fate · same protein structure,
// plus shared compounds (ChEMBL). Pick a disease, choose which axes count, and get its closest relatives.
import Link from "next/link";
import { useMemo, useState } from "react";
import { useDerived } from "@/lib/derived";
import { diseaseHref } from "@/lib/graph";
import { globalHref } from "@/lib/global";

type Axis = "gene" | "pathway" | "tissue" | "mutation" | "fate" | "structure" | "drugs";
const CORE: Axis[] = ["gene", "pathway", "tissue", "mutation", "fate", "structure"];
const ALL: Axis[] = [...CORE, "drugs"];
const AXIS_SHORT: Record<Axis, string> = {
  gene: "Genes",
  pathway: "Pathway",
  tissue: "Tissue",
  mutation: "Mutation types",
  fate: "Protein fate",
  structure: "Structure",
  drugs: "Shared compounds",
};
const AXIS_HELP: Record<Axis, string> = {
  gene: "Do the two umbrellas share clinical entities caused by the same genes (MONDO / OMIM)?",
  pathway: "Overlap of canonical pathways (Reactome, WikiPathways, KEGG, BioCarta, PID), plus a direct STRING interaction between the two proteins.",
  tissue: "Which tissues the symptoms point to (HPO, 20 organ anchors) and where the gene is expressed (GTEx v10).",
  mutation: "Mix of pathogenic ClinVar variant types: substitutions, deletions, duplications, insertions, indels, inversions, repeats, copy-number changes.",
  fate: "What variants do to the protein: no protein made, unstable and degraded, present but inactive, dominant negative, overactive, or accumulating.",
  structure: "3D fold (TM-align of AlphaFold models), sequence alignment, Pfam families and clans, channel type and gating.",
  drugs: "Compounds measured active (≤ 10 µM) on both proteins in ChEMBL 36, with the approved drugs among them. Not in the combined score.",
};
const FATE_SHORT: Record<string, string> = {
  absent: "No protein",
  degraded: "Degraded",
  inactive: "Inactive",
  dominant_negative: "Dominant negative",
  hyperactive: "Overactive",
  accumulates: "Accumulates",
};
const FATE_COLOR: Record<string, string> = {
  absent: "#9aa3ad",
  degraded: "#c58b4d",
  inactive: "#6c8fb8",
  dominant_negative: "#a05a8f",
  hyperactive: "#c4544c",
  accumulates: "#5f9a6b",
};

interface Profile {
  id: string;
  gene: string;
  kind: "atlas" | "channel_panel";
  label: string;
  family: string | null;
  channel: { gating: string; ions: string[] } | null;
  mondo: string[];
  diseases: string[];
  genes: string[];
  pathways: string[];
  n_pathways: number;
  tissue: { symptoms: [string, number][]; n_hpo_terms: number; expression_top: [string, number][]; hpa_specificity: string | null };
  mutation: { n: number; types: Record<string, number>; consequence: Record<string, number> };
  fate: { vector: number[]; unresolved: number; labels: string[]; evidence: string[]; n_null: number; n_altering: number };
  structure: {
    uniprot: string | null;
    length: number | null;
    pfam: string[];
    clans: string[];
    molecular_function: string[];
    fda_drug_target: boolean;
    pdb?: {
      n_pdb_entries?: number;
      pdb_entries?: string[];
      best_resolution?: { entity: string; entry: string; resolution: number | null; method: string | null; length: number | null } | null;
      longest_construct?: { entity: string; entry: string; resolution: number | null; method: string | null; length: number | null } | null;
      alphafold?: { id: string; url: string; mean_plddt: number; partial_model: boolean; residues_modelled: number };
    };
  };
  drugs: { n_active: number; approved: { id: string; name: string | null }[] };
  cluster: number;
}

interface MechsimFile {
  meta: { generated: string; entities: number; pairs: number; tmalign_pairs?: number; axis_label: Record<string, string> };
  pathway_sets: Record<string, { name: string; origin: string; url: string; size: number }>;
  pfam: Record<string, { name: string | null; clan: string | null; clan_name: string | null; description?: string } | null>;
  profiles: Profile[];
  clusters: { id: string; members: string[]; genes: string[]; label: string; strongest_axes: string[] }[];
  pair_fields: string[];
  pairs: (number | null)[][];
}

interface Index {
  file: MechsimFile;
  /** pair row by "i|j" (i < j) */
  row: Map<string, (number | null)[]>;
  col: Record<string, number>;
  /** mid-rank percentile of a raw score, per axis */
  pct: Record<Axis, (v: number) => number>;
}

function buildIndex(file: MechsimFile): Index {
  const col: Record<string, number> = {};
  file.pair_fields.forEach((f, k) => (col[f] = k));
  const row = new Map<string, (number | null)[]>();
  for (const r of file.pairs) row.set(`${r[0]}|${r[1]}`, r);
  const pct = {} as Record<Axis, (v: number) => number>;
  for (const a of ALL) {
    const vals = file.pairs.map((r) => r[col[a]]).filter((v): v is number => v != null).sort((x, y) => x - y);
    const lower = (v: number) => {
      let lo = 0,
        hi = vals.length;
      while (lo < hi) {
        const m = (lo + hi) >> 1;
        if (vals[m] < v) lo = m + 1;
        else hi = m;
      }
      return lo;
    };
    const upper = (v: number) => {
      let lo = 0,
        hi = vals.length;
      while (lo < hi) {
        const m = (lo + hi) >> 1;
        if (vals[m] <= v) lo = m + 1;
        else hi = m;
      }
      return lo;
    };
    pct[a] = (v: number) => (lower(v) + upper(v)) / 2 / Math.max(vals.length, 1);
  }
  return { file, row, col, pct };
}

const pctText = (p: number) => `more alike than ${Math.round(p * 100)}% of pairs`;
const prettyPathway = (s: string) => s;
const tissueName = (s: string) => s.replace(/_/g, " ").replace(/\s+/g, " ");

export function MechanismsView() {
  const data = useDerived<MechsimFile>("mechsim");
  if (data.status === "loading") return <p className="p-8 text-sm text-ink-3">Loading the mechanistic comparison…</p>;
  if (data.status === "missing")
    return (
      <p className="p-8 text-sm text-ink-3">
        The mechanistic comparison is not built yet. Run <code>python3 pipeline/derive/mechsim.py</code> and sync the data.
      </p>
    );
  return <Explorer file={data.data} />;
}

function Explorer({ file }: { file: MechsimFile }) {
  const ix = useMemo(() => buildIndex(file), [file]);
  const P = file.profiles;
  const [sel, setSel] = useState(() => Math.max(0, P.findIndex((p) => p.gene === "SCN1A")));
  const [axes, setAxes] = useState<Set<Axis>>(() => new Set(CORE));
  const [scope, setScope] = useState<"all" | "atlas" | "channels">("all");
  const [open, setOpen] = useState<number | null>(null);

  const ranked = useMemo(() => {
    const out: { j: number; score: number; pcts: Partial<Record<Axis, number>>; raws: Partial<Record<Axis, number>> }[] = [];
    for (let j = 0; j < P.length; j++) {
      if (j === sel) continue;
      if (scope === "atlas" && P[j].kind !== "atlas") continue;
      if (scope === "channels" && !P[j].channel) continue;
      const r = ix.row.get(sel < j ? `${sel}|${j}` : `${j}|${sel}`);
      if (!r) continue;
      const pcts: Partial<Record<Axis, number>> = {};
      const raws: Partial<Record<Axis, number>> = {};
      let sum = 0,
        n = 0;
      for (const a of ALL) {
        const v = r[ix.col[a]];
        if (v == null) continue;
        raws[a] = v;
        pcts[a] = ix.pct[a](v);
        if (axes.has(a)) {
          sum += pcts[a]!;
          n++;
        }
      }
      if (n) out.push({ j, score: sum / n, pcts, raws });
    }
    return out.sort((x, y) => y.score - x.score).slice(0, 40);
  }, [ix, P, sel, axes, scope]);

  const groups = useMemo(() => {
    const atlas = P.map((p, i) => ({ p, i })).filter((x) => x.p.kind === "atlas");
    const panel = P.map((p, i) => ({ p, i })).filter((x) => x.p.kind !== "atlas");
    const fam = new Map<string, { p: Profile; i: number }[]>();
    for (const x of atlas) {
      const f = x.p.family ?? "other";
      fam.set(f, [...(fam.get(f) ?? []), x]);
    }
    return { fam, panel };
  }, [P]);

  const me = P[sel];
  return (
    <div className="mx-auto max-w-7xl px-5 py-8">
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Mechanistic similarity</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          Every pair of {file.meta.entities} gene-defined disorders compared on six mechanistic axes: the 45 diseases mapped in
          depth, plus every Mendelian ion-channel gene ({P.filter((p) => p.kind !== "atlas").length} more channelopathies) so that
          structurally related channels in other tissues show up. Pick a disorder, choose which axes count, and see its closest
          relatives. All scores are computed from public data and are a prompt for expert review, not a finding.
        </p>
      </header>

      <div className="mt-6 grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-5">
          <label className="block text-sm">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Disorder</span>
            <select
              className="mt-1.5 w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm"
              value={sel}
              onChange={(e) => {
                setSel(Number(e.target.value));
                setOpen(null);
              }}
            >
              {[...groups.fam.entries()].map(([f, xs]) => (
                <optgroup key={f} label={`Atlas · ${f}`}>
                  {xs.map(({ p, i }) => (
                    <option key={p.id} value={i}>
                      {p.gene} · {p.label}
                    </option>
                  ))}
                </optgroup>
              ))}
              <optgroup label="Channelopathy panel (outside the atlas)">
                {groups.panel.map(({ p, i }) => (
                  <option key={p.id} value={i}>
                    {p.gene}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Axes that count</legend>
            <ul className="mt-2 space-y-1.5">
              {ALL.map((a) => (
                <li key={a}>
                  <label className="flex cursor-pointer items-start gap-2 text-sm text-ink-2" title={AXIS_HELP[a]}>
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={axes.has(a)}
                      onChange={() =>
                        setAxes((s) => {
                          const next = new Set(s);
                          if (next.has(a)) next.delete(a);
                          else next.add(a);
                          return next.size ? next : s;
                        })
                      }
                    />
                    <span>
                      {AXIS_SHORT[a]}
                      <span className="block text-xs text-ink-3">{AXIS_HELP[a]}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Compare with</legend>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(
                [
                  ["all", "Everything"],
                  ["atlas", "Atlas diseases"],
                  ["channels", "Channelopathies"],
                ] as const
              ).map(([k, l]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setScope(k)}
                  className={`rounded-md border px-2 py-1 text-xs ${scope === k ? "border-ink bg-subtle font-medium text-ink" : "border-line text-ink-3 hover:text-ink"}`}
                >
                  {l}
                </button>
              ))}
            </div>
          </fieldset>

          <ProfileCard p={me} file={file} />
        </aside>

        <section aria-label="Closest relatives" className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">
            Closest to {me.gene} on {axes.size === CORE.length && !axes.has("drugs") ? "all six axes" : [...axes].map((a) => AXIS_SHORT[a].toLowerCase()).join(", ")}
          </h2>
          <p className="mt-1 text-xs text-ink-3">
            Bars show the percentile among all {file.meta.pairs.toLocaleString()} pairs (darker = more alike). Click a row for the reasons.
          </p>
          <div className="mt-3 overflow-x-auto rounded-md border border-line">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-subtle text-left text-xs text-ink-3">
                <tr>
                  <th className="px-3 py-2 font-medium">Disorder</th>
                  <th className="px-2 py-2 font-medium">Score</th>
                  {ALL.map((a) => (
                    <th key={a} className={`px-2 py-2 font-medium ${axes.has(a) ? "text-ink-2" : "opacity-50"}`} title={AXIS_HELP[a]}>
                      {AXIS_SHORT[a]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ranked.map(({ j, score, pcts, raws }) => {
                  const o = P[j];
                  const isOpen = open === j;
                  return (
                    <FragmentRow
                      key={o.id}
                      o={o}
                      me={me}
                      score={score}
                      pcts={pcts}
                      raws={raws}
                      axes={axes}
                      isOpen={isOpen}
                      onToggle={() => setOpen(isOpen ? null : j)}
                      file={file}
                      pair={ix.row.get(sel < j ? `${sel}|${j}` : `${j}|${sel}`)!}
                      col={ix.col}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
          <Clusters file={file} onPick={(i) => setSel(i)} />
        </section>
      </div>
    </div>
  );
}

function Bar({ p, on }: { p: number | undefined; on: boolean }) {
  if (p == null) return <span className="text-xs text-ink-3">–</span>;
  return (
    <span className={`block h-2 w-16 rounded-sm bg-line ${on ? "" : "opacity-40"}`} title={pctText(p)}>
      <span className="block h-2 rounded-sm" style={{ width: `${Math.round(p * 100)}%`, background: `rgba(31,90,150,${0.25 + 0.75 * p})` }} />
    </span>
  );
}

function FragmentRow(props: {
  o: Profile;
  me: Profile;
  score: number;
  pcts: Partial<Record<Axis, number>>;
  raws: Partial<Record<Axis, number>>;
  axes: Set<Axis>;
  isOpen: boolean;
  onToggle: () => void;
  file: MechsimFile;
  pair: (number | null)[];
  col: Record<string, number>;
}) {
  const { o, score, pcts, axes, isOpen, onToggle } = props;
  return (
    <>
      <tr className="cursor-pointer border-t border-line hover:bg-subtle/60" onClick={onToggle} aria-expanded={isOpen}>
        <td className="px-3 py-2">
          <span className="font-medium text-ink">{o.gene}</span>{" "}
          <span className="text-xs text-ink-3">
            {o.kind === "atlas" ? o.label : o.diseases.slice(0, 2).join("; ")}
            {o.channel ? ` · ${o.channel.gating} ${o.channel.ions.join("/")} channel` : ""}
          </span>
        </td>
        <td className="px-2 py-2 tabular-nums text-ink-2">{Math.round(score * 100)}</td>
        {ALL.map((a) => (
          <td key={a} className="px-2 py-2">
            <Bar p={pcts[a]} on={axes.has(a)} />
          </td>
        ))}
      </tr>
      {isOpen && (
        <tr className="border-t border-line bg-subtle/40">
          <td colSpan={2 + ALL.length} className="px-4 py-3">
            <PairDetail {...props} />
          </td>
        </tr>
      )}
    </>
  );
}

function PairDetail({ o, me, pcts, raws, file, pair, col }: Parameters<typeof FragmentRow>[0]) {
  const sharedGenes = me.genes.filter((g) => o.genes.includes(g));
  const sharedPw = me.pathways.filter((s) => o.pathways.includes(s)).slice(0, 6);
  const tissA = me.tissue.symptoms.map(([t]) => t);
  const tissB = o.tissue.symptoms.map(([t]) => t);
  const sharedPfam = me.structure.pfam.filter((x) => o.structure.pfam.includes(x));
  const sharedDrugs = me.drugs.approved.filter((d) => o.drugs.approved.some((e) => e.id === d.id));
  const tm = pair[col.tm_score];
  const seq = pair[col.sequence_score];
  const line = (a: Axis, body: React.ReactNode) => (
    <li className="grid grid-cols-[150px_minmax(0,1fr)] gap-3">
      <span className="text-xs font-medium text-ink-2">
        {AXIS_SHORT[a]}
        {pcts[a] != null && <span className="block font-normal text-ink-3">{Math.round(pcts[a]! * 100)}th pct · {raws[a]!.toFixed(2)}</span>}
      </span>
      <span className="text-xs leading-relaxed text-ink-2">{body}</span>
    </li>
  );
  return (
    <div>
      <ul className="space-y-2.5">
        {line("gene", sharedGenes.length ? <>Shared disease genes: {sharedGenes.join(", ")}</> : <>No clinical entity shares a gene.</>)}
        {line(
          "pathway",
          <>
            {sharedPw.length ? (
              <>
                Shared pathways:{" "}
                {sharedPw.map((s, k) => (
                  <span key={s}>
                    {k ? "; " : ""}
                    <a href={file.pathway_sets[s]?.url} className="text-accent-700 hover:underline" target="_blank" rel="noreferrer">
                      {prettyPathway(file.pathway_sets[s]?.name ?? s)}
                    </a>
                  </span>
                ))}
              </>
            ) : (
              "No shared pathway among the most specific ones listed."
            )}
            {pair[col.string_score] ? ` · STRING interaction ${pair[col.string_score]!.toFixed(2)}` : ""}
          </>,
        )}
        {line(
          "tissue",
          <>
            Symptoms point to {tissA.join(", ") || "–"} vs {tissB.join(", ") || "–"}
            {pair[col.expression_correlation] != null && <> · GTEx expression correlation {pair[col.expression_correlation]!.toFixed(2)}</>}
            {" · "}expressed most in {me.tissue.expression_top.map(([t]) => tissueName(t)).slice(0, 2).join(", ")} vs{" "}
            {o.tissue.expression_top.map(([t]) => tissueName(t)).slice(0, 2).join(", ")}
          </>,
        )}
        {line("mutation", <MutationCompare a={me} b={o} />)}
        {line("fate", <FateCompare a={me} b={o} />)}
        {line(
          "structure",
          <>
            {tm != null && (
              <>
                AlphaFold models superpose with TM-score {tm.toFixed(2)}
                {tm >= 0.5 ? " (same fold)" : ""}.{" "}
              </>
            )}
            {seq != null && <>Sequence alignment {seq.toFixed(2)} of self-alignment. </>}
            {sharedPfam.length > 0 && (
              <>Shared Pfam: {sharedPfam.map((x) => `${file.pfam[x]?.name ?? x} (${x})`).join(", ")}. </>
            )}
            {me.channel && o.channel && (
              <>
                {me.channel.gating === o.channel.gating ? `Both ${me.channel.gating}` : `${me.channel.gating} vs ${o.channel.gating}`} channels (
                {me.channel.ions.join("/")} vs {o.channel.ions.join("/")}).
              </>
            )}
          </>,
        )}
        {line(
          "drugs",
          sharedDrugs.length ? (
            <>
              Approved drugs active on both proteins in ChEMBL: {sharedDrugs.map((d) => (d.name ?? d.id).toLowerCase()).join(", ")}. A
              hypothesis to discuss with clinicians and researchers, not a treatment suggestion.
            </>
          ) : (
            <>No approved drug is recorded as active on both proteins.</>
          ),
        )}
      </ul>
      <p className="mt-3 text-xs">
        <Link href={o.kind === "atlas" ? diseaseHref(o.id) : o.mondo[0] ? globalHref(o.mondo[0]) : "#"} className="text-accent-700 hover:underline">
          Open {o.gene}
        </Link>
      </p>
    </div>
  );
}

function MutationCompare({ a, b }: { a: Profile; b: Profile }) {
  const fmt = (p: Profile) =>
    p.mutation.n
      ? Object.entries(p.mutation.types)
          .slice(0, 4)
          .map(([t, c]) => `${t} ${Math.round((100 * c) / p.mutation.n)}%`)
          .join(", ")
      : "no ClinVar P/LP variants";
  return (
    <>
      {a.gene} ({a.mutation.n}): {fmt(a)}. {b.gene} ({b.mutation.n}): {fmt(b)}.
    </>
  );
}

function FateBar({ p }: { p: Profile }) {
  const labels = p.fate.labels;
  return (
    <span className="inline-flex h-2.5 w-40 overflow-hidden rounded-sm bg-line align-middle" title={labels.map((l, k) => `${FATE_SHORT[l]} ${Math.round(100 * p.fate.vector[k])}%`).join(", ")}>
      {labels.map((l, k) => (
        <span key={l} style={{ width: `${100 * p.fate.vector[k]}%`, background: FATE_COLOR[l] }} />
      ))}
    </span>
  );
}

function FateCompare({ a, b }: { a: Profile; b: Profile }) {
  const top = (p: Profile) =>
    p.fate.labels
      .map((l, k) => [l, p.fate.vector[k]] as const)
      .filter(([, v]) => v >= 0.05)
      .sort((x, y) => y[1] - x[1])
      .map(([l, v]) => `${FATE_SHORT[l].toLowerCase()} ${Math.round(100 * v)}%`)
      .join(", ");
  return (
    <span className="flex flex-col gap-1">
      <span>
        <FateBar p={a} /> {a.gene}: {top(a) || "not resolved"}
      </span>
      <span>
        <FateBar p={b} /> {b.gene}: {top(b) || "not resolved"}
      </span>
    </span>
  );
}

function ProfileCard({ p, file }: { p: Profile; file: MechsimFile }) {
  const pdb = p.structure.pdb;
  return (
    <section className="rounded-md border border-line p-4 text-sm">
      <h2 className="font-semibold text-ink">
        {p.gene}
        <span className="ml-1 font-normal text-ink-3">{p.kind === "atlas" ? "· atlas disease" : "· channelopathy panel"}</span>
      </h2>
      <p className="mt-1 text-xs text-ink-3">{p.kind === "atlas" ? p.label : p.diseases.slice(0, 4).join("; ")}</p>
      <dl className="mt-3 space-y-2 text-xs text-ink-2">
        {p.channel && (
          <div>
            <dt className="text-ink-3">Channel</dt>
            <dd>
              {p.channel.gating}, {p.channel.ions.join("/")}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-ink-3">Tissues (symptoms → expression)</dt>
          <dd>
            {p.tissue.symptoms.map(([t, v]) => `${t} ${Math.round(100 * v)}%`).join(", ") || "too few HPO terms"} →{" "}
            {p.tissue.expression_top.map(([t]) => tissueName(t)).join(", ")}
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Protein fate</dt>
          <dd className="mt-0.5">
            <FateBar p={p} />
            <span className="mt-1 flex flex-wrap gap-x-2">
              {p.fate.labels.map((l) => (
                <span key={l} className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm" style={{ background: FATE_COLOR[l] }} />
                  {FATE_SHORT[l]}
                </span>
              ))}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Protein families (Pfam)</dt>
          <dd>{p.structure.pfam.map((x) => file.pfam[x]?.name ?? x).join(", ") || "–"}</dd>
        </div>
        <div>
          <dt className="text-ink-3">Structures</dt>
          <dd>
            {pdb?.n_pdb_entries ? (
              <>
                {pdb.n_pdb_entries} PDB entries
                {pdb.best_resolution && (
                  <>
                    {" "}· best{" "}
                    <a className="text-accent-700 hover:underline" href={`https://www.rcsb.org/structure/${pdb.best_resolution.entry}`} target="_blank" rel="noreferrer">
                      {pdb.best_resolution.entry}
                    </a>
                    {pdb.best_resolution.resolution != null ? ` (${pdb.best_resolution.resolution} Å)` : ""}
                  </>
                )}
                {pdb.longest_construct && pdb.longest_construct.entry !== pdb.best_resolution?.entry && (
                  <>
                    {" "}· most complete{" "}
                    <a className="text-accent-700 hover:underline" href={`https://www.rcsb.org/structure/${pdb.longest_construct.entry}`} target="_blank" rel="noreferrer">
                      {pdb.longest_construct.entry}
                    </a>
                  </>
                )}
              </>
            ) : (
              "no experimental structure"
            )}
            {pdb?.alphafold && (
              <>
                {" "}·{" "}
                <a className="text-accent-700 hover:underline" href={pdb.alphafold.url} target="_blank" rel="noreferrer">
                  AlphaFold
                </a>{" "}
                (pLDDT {pdb.alphafold.mean_plddt}
                {pdb.alphafold.partial_model ? ", first 1,400 residues only" : ""})
              </>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Compounds (ChEMBL, ≤ 10 µM)</dt>
          <dd>
            {p.drugs.n_active} active
            {p.drugs.approved.length > 0 && <>, approved: {p.drugs.approved.slice(0, 8).map((d) => (d.name ?? d.id).toLowerCase()).join(", ")}</>}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Clusters({ file, onPick }: { file: MechsimFile; onPick: (i: number) => void }) {
  const byId = new Map(file.profiles.map((p, i) => [p.id, i]));
  return (
    <section className="mt-8" aria-labelledby="mc-h">
      <h2 id="mc-h" className="text-sm font-semibold text-ink">
        Mechanistic clusters
      </h2>
      <p className="mt-1 text-xs text-ink-3">Average-linkage clustering on the six axes combined. Atlas diseases in bold.</p>
      <ul className="mt-3 grid gap-3 md:grid-cols-2">
        {file.clusters.slice(0, 16).map((c) => (
          <li key={c.id} className="rounded-md border border-line p-3">
            <p className="text-xs text-ink-3">
              {c.id} · {c.label}
            </p>
            <p className="mt-1.5 flex flex-wrap gap-1.5">
              {c.members.map((m, k) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => onPick(byId.get(m)!)}
                  className={`rounded border border-line px-1.5 py-0.5 text-xs hover:bg-subtle ${m.startsWith("disease:") ? "font-semibold text-ink" : "text-ink-2"}`}
                >
                  {c.genes[k]}
                </button>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
