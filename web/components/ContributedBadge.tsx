import type { AtlasEdge, AtlasNode } from "@/lib/types";

export interface ContributionStamp {
  by?: string;
  date?: string;
  url?: string;
}

/** attrs.contributed (a contributed node or edge) plus attrs.contributed_sources (new sources on an existing node). */
export function contributionsOf(x: AtlasNode | AtlasEdge | undefined): ContributionStamp[] {
  const a = (x?.attrs ?? {}) as { contributed?: unknown; contributed_sources?: unknown };
  const out: ContributionStamp[] = [];
  if (a.contributed && typeof a.contributed === "object") out.push(a.contributed as ContributionStamp);
  if (Array.isArray(a.contributed_sources)) out.push(...(a.contributed_sources.filter((s) => s && typeof s === "object") as ContributionStamp[]));
  return out;
}

export function ContributedBadge({ stamps, className = "" }: { stamps: ContributionStamp[]; className?: string }) {
  if (!stamps.length) return null;
  const s = stamps[0];
  const who = s.by && s.by !== "community" ? s.by : "the community";
  return (
    <span
      className={`inline-flex items-center rounded border border-dashed border-ink-4 bg-white px-1.5 py-px text-[11px] font-medium text-ink-2 ${className}`}
      title={`Added by ${who}${s.date ? ` on ${s.date}` : ""}${stamps.length > 1 ? ` (+${stamps.length - 1} more)` : ""}. Not yet reviewed by an expert.`}
    >
      Community-contributed · not yet reviewed
    </span>
  );
}
