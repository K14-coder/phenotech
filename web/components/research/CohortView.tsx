"use client";

// /research: the cohort view of every disease mapped in depth (docs/persona-spec.md). How many people are
// dealing with which problems, and where a trial looks feasible. Sortable; filterable by family and mechanism.
import Link from "next/link";
import { useMemo, useState } from "react";
import { WithGraph } from "../GraphProvider";
import { familyName } from "@/lib/bridges";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { usePersona } from "@/lib/persona";
import {
  loadChannels,
  loadPrevalence,
  loadReadiness,
  type ChannelsFile,
  type PrevalenceFile,
  type ReadinessFile,
} from "@/lib/population";
import { useResource } from "@/lib/resource";

type ColKey = "unmet" | "affected" | "recruiting" | "registry" | "orgs" | "readiness" | "mechanism";

interface Row {
  id: string;
  label: string;
  family: string;
  affectedText: string;
  affectedSort: number;
  recruiting: number;
  registries: string[];
  orgs: number;
  readiness: number | null;
  readinessOf: number;
  approved: "yes" | "partial" | "no" | null;
  mechanisms: string[];
}

const COLS: Record<ColKey, { label: string; hint: string }> = {
  unmet: { label: "Unmet need", hint: "Whether an approved therapy exists (readiness.json, approved therapy)" },
  affected: { label: "Est. affected", hint: "Rough worldwide range from Orphanet prevalence classes; not a count" },
  recruiting: { label: "Recruiting studies", hint: "Studies recruiting now (channels.json, sponsor level)" },
  registry: { label: "Registry", hint: "Registries, natural history studies or data platforms" },
  orgs: { label: "Patient orgs", hint: "Patient organisations serving this disease" },
  readiness: { label: "Readiness", hint: "Trial-readiness tally out of 8 (readiness.json)" },
  mechanism: { label: "Mechanism class", hint: "How the variants act, from the atlas graph" },
};

const MECH_SHORT: Record<string, string> = {
  "mech:haploinsufficiency": "Haploinsufficiency",
  "mech:loss-of-function": "Loss of function",
  "mech:gain-of-function": "Gain of function",
  "mech:dominant-negative": "Dominant negative",
};

const compact = (n: number) => (n >= 1e6 ? `${+(n / 1e6).toPrecision(2)}M` : n >= 1e3 ? `${+(n / 1e3).toPrecision(2)}k` : `${Math.round(n)}`);
/** 810k–4M, up to 3k, or — */
function compactRange(lo: number | null, hi: number | null): string {
  if (hi != null && (lo == null || lo <= 0)) return `up to ${compact(hi)}`;
  if (lo != null && hi != null) return `${compact(lo)}–${compact(hi)}`;
  if (lo != null) return `>${compact(lo)}`;
  return "—";
}

export function CohortView() {
  return <WithGraph>{(idx) => <Cohort idx={idx} />}</WithGraph>;
}

function Cohort({ idx }: { idx: GraphIndex }) {
  const persona = usePersona();
  const prev = useResource<PrevalenceFile | null>("pop:prevalence", loadPrevalence);
  const ready = useResource<ReadinessFile | null>("pop:readiness", loadReadiness);
  const ch = useResource<ChannelsFile | null>("pop:channels", loadChannels);
  const order: ColKey[] =
    persona === "biotech"
      ? ["unmet", "readiness", "affected", "recruiting", "registry", "orgs", "mechanism"]
      : ["affected", "recruiting", "registry", "orgs", "readiness", "mechanism"];
  const [sort, setSort] = useState<{ key: ColKey | "label"; dir: 1 | -1 }>(() => (persona === "biotech" ? { key: "unmet", dir: -1 } : { key: "affected", dir: -1 }));
  const [family, setFamily] = useState("");
  const [mech, setMech] = useState("");

  const families = useMemo(() => idx.graph.clusters.filter((c) => c.basis === "pathway"), [idx]);
  const rows = useMemo((): Row[] => {
    return idx.graph.nodes
      .filter((n) => n.type === "disease")
      .map((n) => {
        const fam = families.find((c) => c.members.includes(n.id));
        const dp = prev?.data?.deep[n.id];
        const ww = dp?.estimated_people?.worldwide;
        const rd = ready?.data?.diseases[n.id];
        const by = ch?.data?.by_disease[n.id] ?? {};
        const regIds = [...(by.registry ?? []), ...(by.natural_history_study ?? []), ...(by.data_platform ?? [])];
        // how the variants act (effect mechanisms); otherwise the process that fails
        const driven = (idx.adjacency.get(n.id) ?? []).filter((x) => x.edge.type === "driven_by" && x.dir === "out");
        const effects = driven.filter((x) => MECH_SHORT[x.other]).map((x) => MECH_SHORT[x.other]);
        const mechanisms = effects.length ? effects : driven.slice(0, 1).map((x) => (idx.nodeById.get(x.other)?.label ?? x.other).split(" (")[0]);
        return {
          id: n.id,
          label: n.label,
          family: fam ? familyName(fam) : "—",
          affectedText: ww ? compactRange(ww.low, ww.high) : "not estimable",
          affectedSort: ww?.high ?? ww?.low ?? -1,
          recruiting: by.recruiting_trial?.length ?? 0,
          registries: regIds.map((id) => ch?.data?.channels.find((c) => c.id === id)?.name ?? id),
          orgs: by.patient_org?.length ?? 0,
          readiness: rd ? rd.tally : null,
          readinessOf: rd?.tally_of ?? 8,
          approved: rd?.components.approved_therapy?.status ?? null,
          mechanisms: [...new Set(mechanisms)],
        };
      });
  }, [idx, families, prev, ready, ch]);

  const allMechs = useMemo(() => [...new Set(rows.flatMap((r) => r.mechanisms))].sort(), [rows]);
  const shown = useMemo(() => {
    const val = (r: Row, k: ColKey | "label"): number | string => {
      switch (k) {
        case "label":
          return r.label.toLowerCase();
        case "unmet":
          return r.approved === "no" ? 2 : r.approved === "partial" ? 1 : r.approved === "yes" ? 0 : -1;
        case "affected":
          return r.affectedSort;
        case "recruiting":
          return r.recruiting;
        case "registry":
          return r.registries.length;
        case "orgs":
          return r.orgs;
        case "readiness":
          return r.readiness ?? -1;
        case "mechanism":
          return r.mechanisms.join(",");
      }
    };
    return rows
      .filter((r) => (!family || r.family === family) && (!mech || r.mechanisms.includes(mech)))
      .sort((a, b) => {
        const x = val(a, sort.key);
        const y = val(b, sort.key);
        const c = x < y ? -1 : x > y ? 1 : 0;
        // ties: higher readiness, then name
        return c * sort.dir || (b.readiness ?? -1) - (a.readiness ?? -1) || a.label.localeCompare(b.label);
      });
  }, [rows, family, mech, sort]);

  const loading = [prev, ready, ch].some((r) => r?.status === "loading");
  const missing = [
    !prev?.data && prev?.status === "ready" ? "prevalence" : null,
    !ready?.data && ready?.status === "ready" ? "readiness" : null,
    !ch?.data && ch?.status === "ready" ? "channels" : null,
  ].filter(Boolean);
  const head = (k: ColKey | "label", label: string, hint?: string) => (
    <th key={k} scope="col" className="whitespace-nowrap px-3 py-2 text-left font-medium" aria-sort={sort.key === k ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        title={hint}
        onClick={() => setSort((s) => (s.key === k ? { key: k, dir: (s.dir * -1) as 1 | -1 } : { key: k, dir: k === "label" ? 1 : -1 }))}
        className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-ink"
      >
        {label}
        <span aria-hidden="true">{sort.key === k ? (sort.dir === 1 ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
  const cell = (r: Row, k: ColKey) => {
    switch (k) {
      case "unmet":
        return r.approved === "yes" ? <span className="text-ink-3">Approved therapy</span> : r.approved === "partial" ? <span className="text-warn-ink">Partial</span> : r.approved === "no" ? <span className="font-medium text-ink">No approved therapy</span> : "—";
      case "affected":
        return <span className="whitespace-nowrap tabular-nums">{r.affectedText}</span>;
      case "recruiting":
        return <span className="tabular-nums">{r.recruiting}</span>;
      case "registry":
        return r.registries.length ? (
          <span title={r.registries.join("\n")} className="block max-w-[220px] truncate">
            {r.registries.length > 1 ? `${r.registries.length}: ` : ""}
            {r.registries[0]}
          </span>
        ) : (
          <span className="text-ink-3">none found</span>
        );
      case "orgs":
        return <span className="tabular-nums">{r.orgs}</span>;
      case "readiness":
        return r.readiness == null ? (
          "—"
        ) : (
          <span className="inline-flex items-center gap-2">
            <span className="h-1.5 w-14 overflow-hidden rounded-full bg-line">
              <span className="block h-full rounded-full bg-accent-700" style={{ width: `${(r.readiness / r.readinessOf) * 100}%` }} />
            </span>
            <span className="tabular-nums">{r.readiness}</span>
          </span>
        );
      case "mechanism":
        return r.mechanisms.length ? r.mechanisms.join(", ") : <span className="text-ink-3">not curated</span>;
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 pb-24 pt-8 sm:px-8">
      <p className="text-xs font-semibold uppercase tracking-[0.08em] text-ink-3">Cohort view</p>
      <h1 className="mt-1 text-[28px] font-semibold tracking-[-0.02em] text-ink">Where could a trial work?</h1>
      <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-ink-3">
        The {rows.length} diseases the atlas maps in depth: how many people are estimated to live with each, who is recruiting, which registries and
        organisations exist, and how trial-ready each one is. Estimates are rough ranges from Orphanet prevalence classes, not counts.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2 text-ink-3">
          Family
          <select value={family} onChange={(e) => setFamily(e.target.value)} className="h-9 rounded-md border border-line bg-white px-2 text-ink">
            <option value="">All families</option>
            {families.map((f) => (
              <option key={f.id} value={familyName(f)}>
                {familyName(f)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-ink-3">
          Mechanism
          <select value={mech} onChange={(e) => setMech(e.target.value)} className="h-9 rounded-md border border-line bg-white px-2 text-ink">
            <option value="">All mechanisms</option>
            {allMechs.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <span className="text-ink-3">
          {shown.length} of {rows.length}
          {loading ? " · loading population data…" : ""}
          {missing.length ? ` · not available yet: ${missing.join(", ")}` : ""}
        </span>
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[960px] border-collapse text-sm">
          <thead className="border-b border-line bg-subtle">
            <tr>
              {head("label", "Disease")}
              <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-ink-3">
                Family
              </th>
              {order.map((k) => head(k, COLS[k].label, COLS[k].hint))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="border-b border-line-2 last:border-0 hover:bg-subtle/60">
                <td className="px-3 py-2">
                  <Link href={diseaseHref(r.id)} className="font-medium text-ink hover:text-accent-700 hover:underline">
                    {r.label}
                  </Link>
                </td>
                <td className="px-3 py-2 text-ink-3">{r.family}</td>
                {order.map((k) => (
                  <td key={k} className="px-3 py-2 text-ink-2">
                    {cell(r, k)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink-3">
        Sources: Orphanet prevalence (Orphadata, CC BY 4.0), ClinicalTrials.gov, patient-organisation directories and the atlas graph. Open a disease
        for its full scorecard with evidence.
      </p>
    </div>
  );
}
