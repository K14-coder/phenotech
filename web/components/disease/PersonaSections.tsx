"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Term } from "../Term";
import { EvidenceChip } from "../evidence/EvidenceBits";
import { approachHref, neighbors, type GraphIndex } from "@/lib/graph";
import { diseaseContext, diseasesFor, type DiseaseContext, type ExistingItem, type OrgPartner } from "@/lib/insights";
import { isPlaceholderUrl, plural } from "@/lib/text";
import type { AtlasEdge, AtlasNode } from "@/lib/types";

const H2 = "text-[22px] font-semibold tracking-tight text-ink";
const EYEBROW = "text-xs font-semibold uppercase tracking-[0.08em] text-ink-3";

// ---------- Researcher: mechanisms first, and who works on them across gene names ----------

interface Person {
  node: AtlasNode;
  diseases: Set<string>;
  edges: AtlasEdge[];
}

export function ResearcherMechanisms({ idx, ctx }: { idx: GraphIndex; ctx: DiseaseContext }) {
  const mechs = useMemo(() => [...ctx.mechanisms.values()].sort((a, b) => b.strength - a.strength), [ctx]);
  const [pick, setPick] = useState(mechs[0]?.mechanism.id ?? "");
  const data = useMemo(() => {
    if (!pick) return null;
    // every disease whose evidence includes this mechanism, across gene names
    const diseases = idx.graph.nodes.filter((n) => n.type === "disease" && diseaseContext(idx, n.id)?.mechanisms.has(pick));
    const ids = new Set(diseases.map((d) => d.id));
    const people = new Map<string, Person>();
    for (const r of idx.graph.nodes) {
      if (r.type !== "researcher") continue;
      for (const nb of neighbors(idx, r.id, { relations: ["works_on"], direction: "out" })) {
        const t = idx.nodeById.get(nb.other);
        if (!t) continue;
        for (const d of diseasesFor(idx, t)) {
          if (!ids.has(d)) continue;
          const p = people.get(r.id) ?? { node: r, diseases: new Set<string>(), edges: [] };
          p.diseases.add(d);
          if (!p.edges.includes(nb.edge)) p.edges.push(nb.edge);
          people.set(r.id, p);
        }
      }
    }
    const geneOf = (dId: string) => diseaseContext(idx, dId)?.genes[0]?.label ?? dId.replace(/^disease:/, "");
    const groups = diseases
      .map((d) => ({
        gene: geneOf(d.id),
        disease: d,
        people: [...people.values()]
          .filter((p) => p.diseases.has(d.id))
          .sort((a, b) => b.diseases.size - a.diseases.size || a.node.label.localeCompare(b.node.label)),
      }))
      .filter((g) => g.people.length)
      .sort((a, b) => Number(b.disease.id === ctx.disease.id) - Number(a.disease.id === ctx.disease.id) || b.people.length - a.people.length);
    return { diseases, groups, bridging: [...people.values()].filter((p) => p.diseases.size >= 2).length };
  }, [idx, pick, ctx]);

  if (!mechs.length) return null;
  return (
    <section aria-labelledby="mech-h" className="scroll-mt-20">
      <p className={EYEBROW}>For researchers</p>
      <h2 id="mech-h" className={`mt-1 ${H2}`}>
        Mechanisms first
      </h2>
      <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Mechanisms">
        {mechs.map((m) => (
          <button
            key={m.mechanism.id}
            type="button"
            role="tab"
            aria-selected={pick === m.mechanism.id}
            onClick={() => setPick(m.mechanism.id)}
            className={`rounded-md border px-3 py-1.5 text-sm ${pick === m.mechanism.id ? "border-accent-700 bg-accent-50 text-ink" : "border-line text-ink-2 hover:border-accent-500"}`}
          >
            {m.mechanism.label}
          </button>
        ))}
      </div>
      {data && (
        <div className="mt-5">
          <p className="text-sm text-ink-2">
            Seen in {plural(data.diseases.length, "disease")} across gene names:{" "}
            {data.diseases.map((d) => diseaseContext(idx, d.id)?.genes[0]?.label ?? d.label).join(", ")}.
            {data.bridging > 0 && <span className="text-ink-3"> {plural(data.bridging, "researcher")} already work on 2 or more of them.</span>}
          </p>
          <h3 className="mt-5 text-[15px] font-semibold text-ink">Who else works on this mechanism, across gene names</h3>
          <p className="mt-1 text-xs text-ink-3">Grouped by gene. Links go to their papers, grants or institutional pages only.</p>
          {data.groups.length ? (
            <div className="mt-3 grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
              {data.groups.slice(0, 6).map((g) => (
                <div key={g.disease.id}>
                  <p className="text-sm font-semibold text-ink">
                    {g.gene} <span className="font-normal text-ink-3">· {plural(g.people.length, "person", "people")}</span>
                  </p>
                  <ul className="mt-1.5 space-y-1.5">
                    {g.people.slice(0, 5).map((p) => {
                      const url = p.node.type === "researcher" ? p.node.attrs?.url : undefined;
                      return (
                        <li key={p.node.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                          <span className={p.diseases.size >= 2 ? "font-medium text-ink" : "text-ink-2"}>{p.node.label}</span>
                          {p.node.type === "researcher" && p.node.attrs?.affiliation && <span className="text-xs text-ink-3">{p.node.attrs.affiliation}</span>}
                          {p.diseases.size >= 2 && (
                            <span className="rounded border border-accent-200 bg-accent-50 px-1.5 py-px text-[11px] font-medium text-accent-900">
                              {p.diseases.size} diseases
                            </span>
                          )}
                          <EvidenceChip edge={p.edges[0]} label="Paper" />
                          {!isPlaceholderUrl(url) && (
                            <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent-700 hover:underline">
                              Publications ↗
                            </a>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-3">No researchers are linked to diseases with this mechanism yet.</p>
          )}
        </div>
      )}
    </section>
  );
}

// ---------- Biotech: mechanism and unmet need first ----------

export function BiotechNeed({
  ctx,
  items,
  ownOrgs,
  umbrellaOrgs,
}: {
  ctx: DiseaseContext;
  items: ExistingItem[];
  ownOrgs: OrgPartner[];
  umbrellaOrgs: OrgPartner[];
}) {
  const d = ctx.disease;
  const mechs = [...ctx.mechanisms.values()].sort((a, b) => b.strength - a.strength);
  const own = items.filter((i) => i.own);
  const trials = own.filter((i) => i.node.type === "study" && i.node.attrs?.study_type === "interventional");
  const count = (k: string) => own.filter((i) => i.node.type === "asset" && i.node.attrs?.kind === k).length;
  const models = count("animal_model") + count("cell_model");
  const variants = ctx.variantGroups.reduce(
    (t, v) => t + (v.type === "variant_group" ? Object.values(v.attrs?.clinvar_counts ?? {}).reduce((a, n) => a + (typeof n === "number" ? n : 0), 0) : 0),
    0,
  );
  const approved = d.type === "disease" ? d.attrs?.approved_treatment : undefined;
  const facts: [string, string][] = [
    ["Approved treatment", approved === true ? "Yes" : approved === false ? "None known" : "Not recorded"],
    ["Interventional trials", trials.length ? `${trials.length}: ${trials.slice(0, 2).map((t) => t.node.label).join("; ")}${trials.length > 2 ? "…" : ""}` : "None registered in the sources searched"],
    ["Community", `${plural(ownOrgs.length, "dedicated patient group")}${umbrellaOrgs.length ? `, ${plural(umbrellaOrgs.length, "umbrella group")}` : ""}${variants ? ` · ${variants} reported variants (ClinVar)` : ""}`],
    ["Infrastructure", `${count("registry")} registries · ${count("natural_history_study")} natural history studies · ${count("outcome_measure")} outcome measures · ${models} models`],
  ];
  return (
    <section aria-labelledby="need-h" className="scroll-mt-20">
      <p className={EYEBROW}>For biotech and pharma</p>
      <h2 id="need-h" className={`mt-1 ${H2}`}>
        Mechanism and unmet need
      </h2>
      <div className="mt-5 grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <p className="text-sm font-semibold text-ink">Mechanisms, strongest evidence first</p>
          <ul className="mt-2 space-y-2">
            {mechs.map((m) => {
              const href = approachHref(m.mechanism.id);
              return (
                <li key={m.mechanism.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Term>{m.mechanism.label}</Term>
                  <EvidenceChip edge={m.edges[m.edges.length - 1]} />
                  {href && (
                    <Link href={href} className="text-xs font-medium text-accent-700 hover:underline">
                      Therapy approaches →
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
        <dl className="divide-y divide-line-2 border-y border-line-2">
          {facts.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[150px_minmax(0,1fr)] gap-3 py-2.5 text-sm">
              <dt className="text-ink-3">{k}</dt>
              <dd className="text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
