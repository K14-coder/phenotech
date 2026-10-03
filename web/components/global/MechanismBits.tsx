"use client";

// Curated mechanism data that sits beside the atlas's own evidence:
//  - MechanismLayer: data/derived/global/mechanism/<b>.json + clusters.json (G2P / ClinGen / Reactome).
//  - DisMechChain: an independently curated mechanism chain from DisMech (Monarch Initiative, BSD-3),
//    with one verbatim evidence snippet per step and attribution. Loaded only when opened.
import Link from "next/link";
import { useCallback, useState } from "react";
import { GLOBAL_BASE, bucketOf, globalHref, type GlobalIndex } from "@/lib/global";
import { loadDismechSnippets } from "@/lib/population";
import { useResource } from "@/lib/resource";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";
const CLASS_LABEL: Record<string, string> = {
  "mech:loss-of-function": "Loss of function",
  "mech:haploinsufficiency": "Haploinsufficiency",
  "mech:dominant-negative": "Dominant negative",
  "mech:gain-of-function": "Gain of function",
};

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
  return (await r.json()) as T;
}

interface MechEntry {
  mechanisms?: { class: string | null; source: string; label_verbatim: string; url: string; confidence?: string; gene?: string }[];
  validity?: { classification: string; moi?: string; gene?: string; url: string; gcep?: string; date?: string }[];
  pathways?: string[];
  cluster_id?: string;
  mechanism_neighbours?: { id: string; gene?: string; shared_pathways?: string[]; shared_mechanisms?: string[] }[];
}
interface MechShard {
  p: Record<string, string>;
  d: Record<string, MechEntry>;
}
interface ClustersFile {
  clusters: { id: string; label: string; size: number; members: string[]; rationale?: string }[];
}

const loadClusters = () => getJson<ClustersFile>(`${GLOBAL_BASE}/clusters.json`);

export function MechanismLayer({ id, gi }: { id: string; gi?: GlobalIndex }) {
  const load = useCallback(() => getJson<MechShard>(`${GLOBAL_BASE}/mechanism/${bucketOf(id)}.json`), [id]);
  const shard = useResource<MechShard>(`global:mechanism:${bucketOf(id)}`, load);
  const e = shard?.data?.d[id];
  const clusters = useResource<ClustersFile>(e?.cluster_id ? "global:clusters" : null, loadClusters);
  if (shard?.status === "loading") return <p className="text-sm text-ink-3">Loading the curated mechanism records…</p>;
  if (!e) return null;
  const cl = e.cluster_id ? clusters?.data?.clusters.find((c) => c.id === e.cluster_id) : undefined;
  const name = (x: string) => gi?.byId.get(x)?.name ?? x;
  return (
    <section aria-labelledby="mech-h" className="max-w-[760px]">
      <p className={EYEBROW}>Mechanism</p>
      <h2 id="mech-h" className={`mt-1 ${H2}`}>
        How it happens, from curated records
      </h2>
      <p className="mt-1.5 text-sm text-ink-3">Gene2Phenotype, ClinGen and Reactome records, joined to this disease. Computed grouping, not evidence of a shared treatment.</p>
      <div className="mt-4 space-y-4 text-sm">
        {!!e.mechanisms?.length && (
          <ul className="space-y-1.5">
            {e.mechanisms.map((m, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2">
                <span className="rounded-full border border-line px-2 py-0.5 text-xs text-ink">{m.class ? (CLASS_LABEL[m.class] ?? m.class) : "unclassified"}</span>
                <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                  {m.source}: “{m.label_verbatim}” ↗
                </a>
                <span className="text-ink-3">
                  {[m.gene, m.confidence].filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        {!!e.validity?.length && (
          <p className="text-ink-2">
            {e.validity.map((v, i) => (
              <a key={i} href={v.url} target="_blank" rel="noopener noreferrer" className="mr-3 text-accent-700 hover:underline">
                ClinGen: {v.classification}
                {v.moi ? ` (${v.moi})` : ""}
                {v.gene ? `, ${v.gene}` : ""} ↗
              </a>
            ))}
          </p>
        )}
        {!!e.pathways?.length && (
          <p className="text-ink-2">
            <span className="text-ink-3">Pathways: </span>
            {e.pathways.map((p, i) => (
              <span key={p}>
                {i > 0 && " · "}
                <a href={`https://reactome.org/content/detail/${p}`} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                  {shard?.data?.p[p] ?? p}
                </a>
              </span>
            ))}
          </p>
        )}
        {cl && (
          <p className="text-ink-2">
            <span className="text-ink-3">Mechanism family: </span>
            {cl.label} <span className="text-ink-3">({cl.size} diseases)</span>
          </p>
        )}
        {!!e.mechanism_neighbours?.length && (
          <div>
            <p className="text-ink-3">Same mechanism family, sharing a pathway and a mechanism class:</p>
            <ul className="mt-1 space-y-0.5">
              {e.mechanism_neighbours.slice(0, 6).map((n) => (
                <li key={n.id}>
                  <Link href={globalHref(n.id)} className="text-accent-700 hover:underline">
                    {name(n.id)}
                  </Link>
                  <span className="text-ink-3">
                    {n.gene ? ` · ${n.gene}` : ""}
                    {n.shared_mechanisms?.length ? ` · ${n.shared_mechanisms.map((m) => CLASS_LABEL[m] ?? m).join(", ")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

// ---------- DisMech ----------

interface DismechStep {
  i: number;
  label: string;
  sec: string;
  type: string;
  role?: string;
}
interface DismechEntry {
  name: string;
  description?: string;
  steps: DismechStep[];
  chains?: number[][];
  attribution?: { page_url?: string; file_url?: string };
  treatments?: { name: string }[];
}
interface DismechShard {
  attribution?: { text?: string; license?: string; commit?: string };
  d: Record<string, DismechEntry[]>;
}
interface DismechLinks {
  links: { atlas_id: string; mondo: string; dismech_name: string; page_url?: string }[];
}

const loadLinks = () => getJson<DismechLinks>(`${GLOBAL_BASE}/dismech_atlas_links.json`);

/** For a disease mapped in depth: finds its DisMech entry through dismech_atlas_links.json. */
export function DisMechForAtlas({ atlasId }: { atlasId: string }) {
  const links = useResource<DismechLinks>("global:dismech-links", loadLinks);
  const link = links?.data?.links.find((l) => l.atlas_id === atlasId);
  if (!link) return null;
  return <DisMechChain mondo={link.mondo} />;
}

export function DisMechChain({ mondo }: { mondo: string }) {
  const [open, setOpen] = useState(false);
  const load = useCallback(() => getJson<DismechShard>(`${GLOBAL_BASE}/dismech/${bucketOf(mondo)}.json`), [mondo]);
  const loadSnips = useCallback(() => loadDismechSnippets(mondo), [mondo]);
  const shard = useResource<DismechShard>(open ? `global:dismech:${bucketOf(mondo)}` : null, load);
  const snips = useResource(open ? `web:dismech-snippets:${mondo}` : null, loadSnips);
  const entry = shard?.data?.d[mondo]?.[0];
  const chain = entry ? (entry.chains?.length ? [...entry.chains].sort((a, b) => b.length - a.length)[0] : entry.steps.map((s) => s.i)) : [];
  const steps = chain.map((i) => entry!.steps.find((s) => s.i === i)).filter((s): s is DismechStep => !!s);
  return (
    <section aria-labelledby={`dm-${mondo}`} className="max-w-[760px] rounded-lg border border-line px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={`dm-${mondo}`} className="text-[17px] font-semibold text-ink">
          Independently curated mechanism
        </h2>
        <span className="text-xs text-ink-3">DisMech, Monarch Initiative · BSD-3-Clause</span>
      </div>
      <p className="mt-1 text-sm text-ink-3">A mechanism chain curated outside this atlas, each step with a verbatim evidence snippet.</p>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-3 inline-flex min-h-[40px] items-center rounded-md border border-line px-3 text-sm text-ink-2 hover:border-accent-500 hover:text-ink"
        >
          Show the chain
        </button>
      ) : shard?.status !== "ready" ? (
        <p className="mt-3 text-sm text-ink-3">{shard?.status === "error" ? "The DisMech record could not be loaded." : "Loading…"}</p>
      ) : !entry ? (
        <p className="mt-3 text-sm text-ink-3">No DisMech record for this disease.</p>
      ) : (
        <>
          <p className="mt-3 text-sm font-medium text-ink">{entry.name}</p>
          <ol className="mt-2 space-y-2">
            {steps.map((s, k) => {
              const sn = snips?.data?.[String(s.i)];
              return (
                <li key={s.i} className="flex gap-3 text-sm">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line text-[11px] tabular-nums text-ink-3">{k + 1}</span>
                  <span className="min-w-0">
                    <span className="text-ink">{s.label}</span>
                    <span className="ml-2 text-xs text-ink-3">{s.sec === "pathophysiology" ? (s.role ?? "mechanism").replace(/_/g, " ") : s.sec}</span>
                    {sn && (
                      <span className="mt-0.5 block text-ink-3">
                        “{sn[1]}”{" "}
                        {sn[0].startsWith("PMID:") ? (
                          <a href={`https://pubmed.ncbi.nlm.nih.gov/${sn[0].slice(5)}/`} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                            {sn[0]} ↗
                          </a>
                        ) : (
                          <span>{sn[0]}</span>
                        )}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            {shard.data?.attribution?.text ?? "From DisMech (Monarch Initiative), BSD-3-Clause."}{" "}
            {entry.attribution?.page_url && (
              <a href={entry.attribution.page_url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
                Open in DisMech ↗
              </a>
            )}
          </p>
        </>
      )}
    </section>
  );
}

const loadDismechIndex = () =>
  getJson<{ rows: unknown[][] }>(`${GLOBAL_BASE}/dismech_index.json`).then((j) => new Set(j.rows.map((r) => String(r[0]))));

/** Shows the DisMech chain only for diseases DisMech covers (dismech_index.json, 220 KB, loaded once). */
export function DisMechIfAny({ mondo }: { mondo: string }) {
  const ix = useResource<Set<string>>("global:dismech-index", loadDismechIndex);
  if (!ix?.data?.has(mondo)) return null;
  return <DisMechChain mondo={mondo} />;
}
