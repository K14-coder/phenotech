"use client";

// The selected-node summary from the brief's concept mockup, kept compact: centrality for every node;
// for diseases also key investigators, cross-cluster bridges, active patient groups and the action page.
import Link from "next/link";
import { useId, useState } from "react";
import { diseaseHref, type GraphIndex } from "@/lib/graph";
import { bridgeCaption, bridgesFor } from "@/lib/bridges";
import { centralityOf, investigatorsFor, patientGroupsFor, type ActiveGroup } from "@/lib/glance";
import { TYPE_LABEL, plural, relationName } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { Term } from "../Term";
import { EvidenceChip } from "../evidence/EvidenceBits";

type Row = "people" | "bridges" | "groups";

export function Glance({ idx, node, onSelectNode }: { idx: GraphIndex; node: AtlasNode; onSelectNode: (id: string) => void }) {
  const [open, setOpen] = useState<Set<Row>>(() => new Set());
  const uid = useId();
  const c = centralityOf(node);
  if (node.type !== "disease") return c === null ? null : <Centrality value={c} node={node} />;

  const toggle = (r: Row) =>
    setOpen((s) => {
      const next = new Set(s);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  const inv = investigatorsFor(idx, node.id);
  const bridges = bridgesFor(idx, node.id);
  const groups = patientGroupsFor(idx, node.id);
  const groupCount = groups.orgs.length + groups.registries.length + groups.studies.length;
  const groupSummary = [
    plural(groups.orgs.length, "organization"),
    plural(groups.registries.length, "registry", "registries"),
    ...(groups.studies.length ? [plural(groups.studies.length, "natural history study", "natural history studies")] : []),
  ].join(", ");

  return (
    <div className="space-y-3">
      {c !== null && <Centrality value={c} node={node} />}
      <div className="divide-y divide-line-2 border-y border-line-2">
        <GlanceRow
          id={`${uid}-people`}
          label="Key investigators"
          summary={inv.people.length ? `${plural(inv.people.length, "researcher")}, ${plural(inv.institutions.length, "institution")}` : "none recorded yet"}
          count={inv.people.length}
          open={open.has("people")}
          onToggle={() => toggle("people")}
        >
          <ShowMore
            items={inv.people}
            limit={6}
            render={(p) => (
              <li key={p.researcher.id}>
                <ItemButton node={p.researcher} onSelect={onSelectNode} detail={p.institution ?? undefined} />
              </li>
            )}
          />
        </GlanceRow>
        <GlanceRow
          id={`${uid}-bridges`}
          label={<Term k="cross-cluster bridge">Cross-cluster bridges</Term>}
          summary={bridges.length ? `${plural(bridges.length, "connection")} worth exploring` : "none in the atlas yet"}
          count={bridges.length}
          open={open.has("bridges")}
          onToggle={() => toggle("bridges")}
        >
          <ul className="space-y-2.5">
            {bridges.map((g) => (
              <li key={g.other.id}>
                <ItemButton node={g.other} onSelect={onSelectNode} />
                <p className="ml-[26px] text-xs leading-snug text-ink-3">{bridgeCaption(idx, node.id, g)}</p>
                <div className="ml-[26px] mt-1 flex flex-wrap gap-1.5">
                  {g.bridges.map((b) => (
                    <EvidenceChip key={b.edge.id} edge={b.edge} label={relationName(b.edge.type)} className="min-h-[24px] px-2 py-0.5" />
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </GlanceRow>
        <GlanceRow
          id={`${uid}-groups`}
          label="Patient groups active"
          summary={groupCount ? groupSummary : "none recorded yet"}
          count={groupCount}
          open={open.has("groups")}
          onToggle={() => toggle("groups")}
        >
          <div className="space-y-2.5">
            <GroupList title="Organizations" items={groups.orgs} onSelect={onSelectNode} />
            <GroupList title="Registries" items={groups.registries} onSelect={onSelectNode} />
            <GroupList title="Natural history studies" items={groups.studies} onSelect={onSelectNode} />
          </div>
        </GlanceRow>
      </div>
      <Link href={`${diseaseHref(node.id)}#shares`} className="inline-block text-sm font-medium text-accent-700 hover:underline">
        Explore connections →
      </Link>
    </div>
  );
}

function Centrality({ value, node }: { value: number; node: AtlasNode }) {
  const v = Math.round(value);
  const what = node.type === "disease" ? "this disease" : `this ${(TYPE_LABEL[node.type]?.one ?? "item").toLowerCase()}`;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-ink-3">
          <Term k="centrality">Centrality</Term>
        </span>
        <span className="font-medium tabular-nums text-ink">
          {v}
          <span className="font-normal text-ink-3">/100</span>
        </span>
      </div>
      <div
        className="mt-1.5 h-1 overflow-hidden rounded-full bg-line"
        role="meter"
        aria-label="Centrality"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
      >
        <div className="h-full rounded-full bg-accent-700" style={{ width: `${v}%` }} />
      </div>
      <p className="mt-1 text-xs text-ink-3">How much {what} connects others in the atlas.</p>
    </div>
  );
}

function GlanceRow({
  id,
  label,
  summary,
  count,
  open,
  onToggle,
  children,
}: {
  id: string;
  label: React.ReactNode;
  summary: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  if (!count)
    return (
      <p className="py-2 text-sm text-ink-3">
        {label}: {summary}
      </p>
    );
  return (
    <div className="py-2">
      <div className="flex items-baseline gap-1.5 text-sm">
        <span className="shrink-0 text-ink-3">{label}:</span>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={id}
          className="group flex min-w-0 flex-1 items-baseline gap-1 text-left"
        >
          <span className="text-accent-700 group-hover:underline">{summary}</span>
          <span aria-hidden="true" className={`ml-auto shrink-0 text-ink-3 transition-transform ${open ? "rotate-90" : ""}`}>
            ›
          </span>
        </button>
      </div>
      {open && (
        <div id={id} className="mt-2">
          {children}
        </div>
      )}
    </div>
  );
}

function ItemButton({ node, detail, onSelect }: { node: AtlasNode; detail?: string; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(node.id)}
      className="flex w-full min-w-0 items-center gap-2 rounded px-1 py-0.5 text-left text-sm text-ink hover:bg-subtle"
      title={`${node.label}: show on the map`}
    >
      <NodeTypeIcon type={node.type} size={11} className="shrink-0" />
      <span className="min-w-0 truncate">{node.label}</span>
      {detail && <span className="min-w-0 shrink-[3] truncate text-xs text-ink-3">{detail}</span>}
    </button>
  );
}

function GroupList({ title, items, onSelect }: { title: string; items: ActiveGroup[]; onSelect: (id: string) => void }) {
  if (!items.length) return null;
  const detail = (n: AtlasNode) => (n.type === "patient_org" ? n.attrs?.country : undefined);
  return (
    <div>
      <p className="text-xs font-medium text-ink-2">{title}</p>
      <ShowMore
        items={items}
        limit={5}
        render={(g) => (
          <li key={g.node.id}>
            <ItemButton node={g.node} onSelect={onSelect} detail={detail(g.node)} />
          </li>
        )}
      />
    </div>
  );
}

function ShowMore<T>({ items, limit, render }: { items: T[]; limit: number; render: (x: T) => React.ReactNode }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, limit);
  return (
    <>
      <ul className="mt-1 space-y-0.5">{shown.map(render)}</ul>
      {items.length > limit && (
        <button type="button" onClick={() => setAll(!all)} className="mt-1 text-xs text-accent-700 hover:underline">
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}
