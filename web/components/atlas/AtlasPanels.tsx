"use client";

import Link from "next/link";
import { useState } from "react";
import { clustersOf, clusterSlot, diseaseHref, gapsAbout, neighbors, pathHref, type GraphIndex, type Neighbor } from "@/lib/graph";
import { explain } from "@/lib/glossary";
import { clusterColor } from "@/lib/style";
import {
  ASSET_KIND_LABEL,
  HPO_FREQUENCY,
  THERAPY_MODALITY_LABEL,
  THERAPY_STAGE_LABEL,
  TYPE_LABEL,
  isPlaceholderUrl,
  plural,
  relationName,
} from "@/lib/text";
import type { AtlasNode, Cluster, RelationType } from "@/lib/types";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { Term } from "../Term";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { SourceCard } from "../evidence/EvidencePanel";
import { MapLegend } from "./LeftRail";
import { ContributedBadge, contributionsOf } from "../ContributedBadge";
import { bridgesOf } from "@/lib/bridges";
import { Glance } from "./Glance";

const INVERSE_NAME: Partial<Record<RelationType, string>> = {
  causes: "Caused by",
  variant_in: "Gene change types",
  has_effect: "Caused by gene changes",
  participates_in: "Genes involved",
  driven_by: "Diseases driven by this",
  has_phenotype: "Seen in",
  serves: "Patient groups",
  maintains: "Maintained by",
  covers: "Resources",
  studies: "Studies and trials",
  tests: "Tested in",
  targets: "Therapies aimed at this",
  developed_for: "Therapies in development",
  works_on: "Researchers",
  authored: "Authors",
  funds: "Funded by",
  about: "Grants",
};

function groupName(n: Neighbor) {
  if (n.edge.type === "shares_mechanism" || n.edge.type === "similar_phenotype") return relationName(n.edge.type);
  return n.dir === "out" ? relationName(n.edge.type) : INVERSE_NAME[n.edge.type] ?? relationName(n.edge.type);
}

const sectionTitle = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

// ---------- Node ----------

export function NodePanel({
  idx,
  node,
  onSelectNode,
  onSelectCluster,
  onFocus,
}: {
  idx: GraphIndex;
  node: AtlasNode;
  onSelectNode: (id: string) => void;
  onSelectCluster: (id: string) => void;
  /** narrow the map to this node's neighbourhood */
  onFocus?: () => void;
}) {
  const clusters = clustersOf(idx, node.id);
  const nbs = idx.adjacency.get(node.id) ?? [];
  const groups = new Map<string, Neighbor[]>();
  for (const n of nbs) {
    const k = groupName(n);
    const arr = groups.get(k);
    if (arr) arr.push(n);
    else groups.set(k, [n]);
  }
  const linkedDisease =
    node.type === "gene"
      ? neighbors(idx, node.id, { relations: ["causes"], direction: "out" }).map((x) => idx.nodeById.get(x.other)).find(Boolean)
      : undefined;
  const termTip = node.type === "mechanism" || node.type === "phenotype" ? explain(node.label) : undefined;
  const gaps = gapsAbout(idx, [node.id]);

  return (
    <div className="space-y-6 px-5 py-5">
      <div>
        <div className="flex items-center gap-2 text-xs text-ink-3">
          <NodeTypeIcon type={node.type} size={12} />
          <span>{TYPE_LABEL[node.type]?.one ?? node.type}</span>
        </div>
        <h2 className="mt-1.5 text-xl font-semibold leading-snug tracking-tight text-ink">{node.label}</h2>
        <ContributedBadge stamps={contributionsOf(node)} className="mt-1.5" />
        {node.synonyms && node.synonyms.length > 0 && (
          <p className="mt-1 text-sm text-ink-3">Also called {node.synonyms.slice(0, 4).join(", ")}</p>
        )}
        {clusters.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {clusters.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelectCluster(c.id)}
                className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-2 hover:border-accent-500"
              >
                <span className="h-2 w-2 rounded-full" style={{ background: clusterColor(clusterSlot(idx, c.id)) }} aria-hidden="true" />
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <Glance idx={idx} node={node} onSelectNode={onSelectNode} />

      {(node.summary || termTip) && (
        <div className="space-y-2">
          {node.summary && <p className="text-[15px] leading-relaxed text-ink-2">{node.summary}</p>}
          {termTip && termTip !== node.summary && <p className="text-sm leading-relaxed text-ink-3">In plain words: {termTip}</p>}
        </div>
      )}

      <KeyFacts idx={idx} node={node} />

      <div className="flex flex-wrap gap-2">
        {node.type === "disease" && (
          <Link href={diseaseHref(node.id)} className="rounded-md bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-900">
            Open action page →
          </Link>
        )}
        {linkedDisease && (
          <Link href={diseaseHref(linkedDisease.id)} className="rounded-md bg-accent-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-900">
            {linkedDisease.label} →
          </Link>
        )}
        {onFocus && (
          <button type="button" onClick={onFocus} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink">
            Focus the map here
          </button>
        )}
        <Link href={pathHref(node.id)} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent-500 hover:text-ink">
          Find a path from here
        </Link>
      </div>

      {gaps.length > 0 && (
        <div className="rounded-lg border border-line bg-subtle px-4 py-3">
          <p className="text-xs font-semibold text-ink">Open question</p>
          {gaps.map((g) => (
            <p key={g.id} className="mt-1 text-sm leading-relaxed text-ink-2">
              {g.question}
            </p>
          ))}
        </div>
      )}

      <section aria-labelledby="conn-h">
        <h3 id="conn-h" className={sectionTitle}>
          Connections ({nbs.length})
        </h3>
        <p className="mt-1 text-xs text-ink-3">Click a connection’s badge to see its evidence.</p>
        <div className="mt-3 space-y-4">
          {[...groups.entries()].map(([name, list]) => (
            <ConnectionGroup key={name} idx={idx} name={name} list={list} onSelectNode={onSelectNode} />
          ))}
          {!nbs.length && <p className="text-sm text-ink-3">No connections recorded.</p>}
        </div>
      </section>

      <details className="group">
        <summary className="cursor-pointer list-none text-sm font-medium text-ink-2 hover:text-ink">
          <span className="mr-1.5 inline-block transition-transform group-open:rotate-90" aria-hidden="true">
            ›
          </span>
          Details and identifiers
        </summary>
        <div className="mt-3 space-y-4">
          <Xrefs node={node} />
          {node.sources && node.sources.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-ink-2">Where this comes from</p>
              {node.sources.map((s, i) => (
                <SourceCard key={i} ev={s} />
              ))}
            </div>
          )}
          <p className="break-all text-[11px] text-ink-3">ID: {node.id}</p>
        </div>
      </details>
    </div>
  );
}

function ConnectionGroup({
  idx,
  name,
  list,
  onSelectNode,
}: {
  idx: GraphIndex;
  name: string;
  list: Neighbor[];
  onSelectNode: (id: string) => void;
}) {
  const [all, setAll] = useState(false);
  const sorted = [...list].sort((a, b) => b.edge.confidence - a.edge.confidence);
  const shown = all ? sorted : sorted.slice(0, 5);
  return (
    <div>
      <p className="text-xs font-medium text-ink-2">
        {name} <span className="font-normal text-ink-3">{list.length}</span>
      </p>
      <ul className="mt-1.5 space-y-1">
        {shown.map((n) => {
          const other = idx.nodeById.get(n.other);
          if (!other) return null;
          const freq = n.edge.type === "has_phenotype" ? HPO_FREQUENCY[String(n.edge.attrs?.frequency ?? "")] : undefined;
          return (
            <li key={n.edge.id} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onSelectNode(other.id)}
                className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 text-left text-sm text-ink hover:bg-subtle"
              >
                <NodeTypeIcon type={other.type} size={11} className="shrink-0" />
                <span className="truncate">{other.label}</span>
                {freq && <span className="shrink-0 text-xs text-ink-3">{freq.split(" (")[0]}</span>}
              </button>
              <EvidenceChip edge={n.edge} />
            </li>
          );
        })}
      </ul>
      {list.length > 5 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-1 text-xs text-accent-700 hover:underline">
          {all ? "Show fewer" : `Show all ${list.length}`}
        </button>
      )}
    </div>
  );
}

function Fact({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5 text-sm">
      <dt className="w-28 shrink-0 text-ink-3">{k}</dt>
      <dd className="min-w-0 flex-1 text-ink">{children}</dd>
    </div>
  );
}

function ExtLink({ url, children }: { url?: string; children?: React.ReactNode }) {
  if (isPlaceholderUrl(url)) return <span className="text-ink-3">No link (placeholder)</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-accent-700 hover:underline">
      {children ?? "Open"} ↗
    </a>
  );
}

function KeyFacts({ idx, node }: { idx: GraphIndex; node: AtlasNode }) {
  const rows: React.ReactNode[] = [];
  switch (node.type) {
    case "disease": {
      const genes = neighbors(idx, node.id, { relations: ["causes"], direction: "in" }).map((g) => idx.nodeById.get(g.other)?.label);
      if (genes.length) rows.push(<Fact key="g" k="Gene">{genes.join(", ")}</Fact>);
      if (node.attrs?.inheritance) rows.push(<Fact key="i" k="Inheritance">{node.attrs.inheritance}</Fact>);
      if (node.attrs?.onset) rows.push(<Fact key="o" k="Onset">{node.attrs.onset}</Fact>);
      if (node.attrs?.prevalence) rows.push(<Fact key="p" k="Prevalence">{node.attrs.prevalence}</Fact>);
      if (node.attrs?.approved_treatment !== undefined)
        rows.push(<Fact key="t" k="Approved treatment">{node.attrs.approved_treatment ? "Yes" : "None known"}</Fact>);
      break;
    }
    case "gene":
      if (node.attrs?.protein) rows.push(<Fact key="p" k="Protein">{node.attrs.protein}</Fact>);
      if (node.attrs?.function) rows.push(<Fact key="f" k="Job">{node.attrs.function}</Fact>);
      break;
    case "variant_group":
      if (node.attrs?.consequence) rows.push(<Fact key="c" k="Kind of change"><Term>{node.attrs.consequence}</Term></Fact>);
      if (node.attrs?.example_variants?.length) rows.push(<Fact key="e" k="Examples">{node.attrs.example_variants.slice(0, 4).join(", ")}</Fact>);
      break;
    case "mechanism":
      if (node.attrs?.kind) rows.push(<Fact key="k" k="Kind">{node.attrs.kind === "effect" ? "What goes wrong with the protein" : "Biological process"}</Fact>);
      break;
    case "phenotype": {
      const ic = node.attrs?.ic;
      if (typeof ic === "number")
        rows.push(
          <Fact key="ic" k="Specificity">
            {ic >= idx.maxIc * 0.6 ? "Distinctive" : "Common"} <span className="text-ink-3">(<Term k="information content">information</Term> {ic.toFixed(1)})</span>
          </Fact>,
        );
      break;
    }
    case "patient_org":
      if (node.attrs?.scope) rows.push(<Fact key="s" k="Serves">{node.attrs.scope}</Fact>);
      if (node.attrs?.country) rows.push(<Fact key="c" k="Country">{node.attrs.country}</Fact>);
      rows.push(<Fact key="u" k="Website"><ExtLink url={node.attrs?.url} /></Fact>);
      break;
    case "asset":
      if (node.attrs?.kind) rows.push(<Fact key="k" k="Type">{ASSET_KIND_LABEL[node.attrs.kind] ?? node.attrs.kind}</Fact>);
      if (node.attrs?.status) rows.push(<Fact key="s" k="Status">{node.attrs.status}</Fact>);
      if (node.attrs?.access) rows.push(<Fact key="a" k="Access">{node.attrs.access}</Fact>);
      rows.push(<Fact key="u" k="Link"><ExtLink url={node.attrs?.url} /></Fact>);
      break;
    case "study":
      if (node.attrs?.status) rows.push(<Fact key="s" k="Status">{node.attrs.status}</Fact>);
      if (node.attrs?.study_type) rows.push(<Fact key="t" k="Type">{node.attrs.study_type}{node.attrs.phase ? `, ${node.attrs.phase}` : ""}</Fact>);
      if (node.attrs?.sponsor) rows.push(<Fact key="sp" k="Sponsor">{node.attrs.sponsor}</Fact>);
      if (node.attrs?.enrollment) rows.push(<Fact key="e" k="Enrollment">{node.attrs.enrollment}</Fact>);
      rows.push(<Fact key="u" k="Record"><ExtLink url={node.attrs?.url} /></Fact>);
      break;
    case "therapy":
      if (node.attrs?.modality) rows.push(<Fact key="m" k="Approach">{THERAPY_MODALITY_LABEL[node.attrs.modality] ?? node.attrs.modality}</Fact>);
      if (node.attrs?.stage) rows.push(<Fact key="s" k="Stage">{THERAPY_STAGE_LABEL[node.attrs.stage] ?? node.attrs.stage}</Fact>);
      break;
    case "researcher":
      if (node.attrs?.affiliation) rows.push(<Fact key="a" k="Affiliation">{node.attrs.affiliation}</Fact>);
      if (node.attrs?.orcid) rows.push(<Fact key="o" k="ORCID">{node.attrs.orcid}</Fact>);
      if (node.attrs?.url) rows.push(<Fact key="u" k="Profile"><ExtLink url={node.attrs.url} /></Fact>);
      break;
    case "grant":
      if (node.attrs?.title) rows.push(<Fact key="t" k="Title">{node.attrs.title}</Fact>);
      if (node.attrs?.org) rows.push(<Fact key="o" k="Funder">{node.attrs.org}</Fact>);
      if (node.attrs?.fiscal_year) rows.push(<Fact key="y" k="Year">{node.attrs.fiscal_year}</Fact>);
      rows.push(<Fact key="u" k="Record"><ExtLink url={node.attrs?.url} /></Fact>);
      break;
    case "publication":
      if (node.attrs?.title) rows.push(<Fact key="t" k="Title">{node.attrs.title}</Fact>);
      if (node.attrs?.year) rows.push(<Fact key="y" k="Year">{node.attrs.year}</Fact>);
      if (node.attrs?.journal) rows.push(<Fact key="j" k="Journal">{node.attrs.journal}</Fact>);
      rows.push(<Fact key="u" k="Link"><ExtLink url={node.attrs?.url} /></Fact>);
      break;
  }
  if (!rows.length) return null;
  return <dl className="divide-y divide-line-2 border-y border-line-2">{rows}</dl>;
}

const XREF_URL: Record<string, (id: string) => string> = {
  OMIM: (id) => `https://omim.org/entry/${id.replace(/^OMIM:/, "")}`,
  HGNC: (id) => `https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/${id}`,
  MONDO: (id) => `https://monarchinitiative.org/${id}`,
  ORPHA: (id) => `https://www.orpha.net/en/disease/detail/${id.replace(/^ORPHA:/, "")}`,
  HPO: (id) => `https://hpo.jax.org/browse/term/${id}`,
};

function Xrefs({ node }: { node: AtlasNode }) {
  const entries = Object.entries(node.xrefs ?? {});
  if (!entries.length) return null;
  return (
    <div>
      <p className="text-xs font-medium text-ink-2">Identifiers</p>
      <ul className="mt-1.5 flex flex-wrap gap-1.5">
        {entries.flatMap(([db, v]) =>
          (Array.isArray(v) ? v : [v]).map((id) => {
            const href = XREF_URL[db]?.(id);
            const label = id.includes(":") ? id : `${db}:${id}`;
            return (
              <li key={`${db}-${id}`}>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="rounded border border-line px-1.5 py-0.5 text-xs text-accent-700 hover:border-accent-500">
                    {label} ↗
                  </a>
                ) : (
                  <span className="rounded border border-line px-1.5 py-0.5 text-xs text-ink-2">{label}</span>
                )}
              </li>
            );
          }),
        )}
      </ul>
    </div>
  );
}

// ---------- Cluster ----------

export function ClusterPanel({
  idx,
  cluster,
  onSelectNode,
}: {
  idx: GraphIndex;
  cluster: Cluster;
  onSelectNode: (id: string) => void;
}) {
  const color = clusterColor(clusterSlot(idx, cluster.id));
  const members = cluster.members.map((m) => idx.nodeById.get(m)).filter((n): n is AtlasNode => !!n);
  const diseases = members.filter((m) => m.type === "disease");
  const count = (rel: RelationType, types?: AtlasNode["type"][]) => {
    const s = new Set<string>();
    for (const d of diseases) for (const nb of neighbors(idx, d.id, { relations: [rel], direction: "in", types })) s.add(nb.other);
    return s.size;
  };
  const orgs = count("serves");
  const assets = count("covers");
  const studies = count("studies");
  const edges = cluster.edge_ids.map((id) => idx.edgeById.get(id)).filter((e): e is NonNullable<typeof e> => !!e);
  const byType = new Map<string, AtlasNode[]>();
  for (const m of members) {
    const k = TYPE_LABEL[m.type]?.many ?? m.type;
    const arr = byType.get(k);
    if (arr) arr.push(m);
    else byType.set(k, [m]);
  }
  const gaps = gapsAbout(idx, [cluster.id, ...cluster.members]);

  return (
    <div className="space-y-6 px-5 py-5">
      <div>
        <div className="flex items-center gap-2 text-xs text-ink-3">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} aria-hidden="true" />
          Cluster · grouped by shared {cluster.basis}
        </div>
        <h2 className="mt-1.5 text-xl font-semibold leading-snug tracking-tight text-ink">{cluster.label}</h2>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-2">{cluster.rationale}</p>
      </div>

      <dl className="grid grid-cols-4 gap-2 border-y border-line-2 py-3 text-center">
        {[
          ["Diseases", diseases.length],
          ["Patient groups", orgs],
          ["Resources", assets],
          ["Trials", studies],
        ].map(([k, v]) => (
          <div key={k as string}>
            <dd className="text-lg font-semibold tabular-nums text-ink">{v}</dd>
            <dt className="text-[11px] text-ink-3">{k}</dt>
          </div>
        ))}
      </dl>

      <section>
        <h3 className={sectionTitle}>Members</h3>
        <div className="mt-2 space-y-3">
          {[...byType.entries()].map(([k, list]) => (
            <div key={k}>
              <p className="text-xs font-medium text-ink-2">{k}</p>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {list.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => onSelectNode(m.id)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:border-accent-500 hover:text-ink"
                    >
                      <NodeTypeIcon type={m.type} color={color} size={11} />
                      {m.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className={sectionTitle}>Evidence for this grouping</h3>
        {edges.length ? (
          <ul className="mt-2 space-y-2">
            {edges.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-sm text-ink-2">
                  {idx.nodeById.get(e.source)?.label} <span className="text-ink-3">{relationName(e.type).toLowerCase()}</span>{" "}
                  {idx.nodeById.get(e.target)?.label}
                </span>
                <EvidenceChip edge={e} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-ink-3">No supporting connections listed for this cluster.</p>
        )}
      </section>

      {gaps.length > 0 && (
        <section className="rounded-lg border border-line bg-subtle px-4 py-3">
          <h3 className="text-xs font-semibold text-ink">What we don’t know yet</h3>
          <ul className="mt-1.5 space-y-1.5">
            {gaps.map((g) => (
              <li key={g.id} className="text-sm leading-relaxed text-ink-2">
                {g.question}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ---------- Nothing selected ----------

export function OverviewPanel({ idx, onSelectNode }: { idx: GraphIndex; onSelectNode: (id: string) => void }) {
  const top = idx.graph.nodes
    .filter((n) => n.type === "disease")
    .sort((a, b) => (idx.degree.get(b.id) ?? 0) - (idx.degree.get(a.id) ?? 0))
    .slice(0, 5);
  const shapes: AtlasNode["type"][] = ["disease", "gene", "mechanism", "phenotype", "patient_org", "asset", "study", "therapy"];
  return (
    <div className="space-y-7 px-5 py-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-ink">How to read this map</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-2">
          Each shape is a disease, gene, symptom or group. Lines are connections, and every line has evidence: click one to see
          where it comes from.
        </p>
      </div>
      <section>
        <h3 className={sectionTitle}>Shapes</h3>
        <ul className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-2">
          {shapes.map((t) => (
            <li key={t} className="flex items-center gap-2 text-sm text-ink-2">
              <NodeTypeIcon type={t} size={13} />
              {TYPE_LABEL[t].one}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs leading-relaxed text-ink-3">
          Colour shows the cluster; size shows how central it is in the atlas. Hover a shape to light up its neighbours.
        </p>
      </section>
      <section>
        <h3 className={sectionTitle}>Lines</h3>
        <MapLegend bridgeCount={bridgesOf(idx).size} />
      </section>
      {top.length > 0 && (
        <section>
          <h3 className={sectionTitle}>Start with a disease</h3>
          <ul className="mt-2 space-y-1">
            {top.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => onSelectNode(d.id)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm text-ink hover:bg-subtle"
                >
                  {d.label}
                  <span className="text-xs text-ink-3">{plural(idx.degree.get(d.id) ?? 0, "link")}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
