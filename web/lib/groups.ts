// Disease groups for Simple-mode guided search: a head disease ("Huntington disease"), its member types
// ("juvenile Huntington disease") and look-alike names that are different conditions ("Huntington
// disease-like 2"). Uses data/derived/global/groups.json when it exists; until then (or for a disease it
// does not list) a name-stem heuristic behind the same interface.
import { GLOBAL_BASE, normalizeTerm, type GlobalIndex, type GlobalRow } from "./global";
import { loadAvailableOnce } from "./population";

export interface GroupMember {
  row: GlobalRow;
  /** one line: what makes this type different */
  distinction: string;
}

export interface DiseaseGroup {
  head: GlobalRow;
  members: GroupMember[];
  lookalikes: GlobalRow[];
  /** "groups.json" or "name" (heuristic) */
  basis: "groups.json" | "name";
}

/** groups.json (data/derived/global): head_of {row -> head} and groups {head -> members, similar names}. */
export interface GroupsFile {
  groups?: Record<
    string,
    {
      name?: string;
      members?: (string | { id: string; distinction?: string; label?: string })[];
      lookalikes?: (string | { id: string })[];
      similar_names_different_conditions?: string[];
    }
  >;
  head_of?: Record<string, string>;
  member_of?: Record<string, string>;
}

const SKIP = /\b(modifier|susceptibility|obsolete)\b/i;
const ROMAN = /^(i|ii|iii|iv|v|vi|vii|viii|ix|x)$/;

interface NameIndex {
  byName: Map<string, GlobalRow>;
  tokens: Map<string, string[]>;
}
const nameCache = new WeakMap<GlobalIndex, NameIndex>();
function names(gi: GlobalIndex): NameIndex {
  let ix = nameCache.get(gi);
  if (!ix) {
    ix = { byName: new Map(), tokens: new Map() };
    for (const r of gi.rows) {
      const t = normalizeTerm(r.name);
      ix.tokens.set(r.id, t.split(" "));
      const prev = ix.byName.get(t);
      if (!prev || r.n > prev.n) ix.byName.set(t, r);
    }
    nameCache.set(gi, ix);
  }
  return ix;
}

/** index of `needle` as a contiguous word run inside `hay`, or -1 */
function wordIndex(hay: string[], needle: string[]): number {
  outer: for (let i = 0; i + needle.length <= hay.length; i++) {
    for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) continue outer;
    return i;
  }
  return -1;
}

function remainder(member: string[], head: string[]): string[] {
  const at = wordIndex(member, head);
  return at < 0 ? member : [...member.slice(0, at), ...member.slice(at + head.length)];
}

const isLike = (rest: string[], afterHead: string | undefined) => afterHead === "like" || rest[0] === "like";

/** The general disease this row is a type of (itself when it is the general one). */
export function headOf(gi: GlobalIndex, row: GlobalRow, data?: GroupsFile | null): GlobalRow {
  const viaFile = data?.head_of?.[row.id] ?? data?.member_of?.[row.id];
  if (viaFile && gi.byId.has(viaFile)) return gi.byId.get(viaFile)!;
  if (data?.groups?.[row.id]) return row;
  const ix = names(gi);
  const toks = ix.tokens.get(row.id) ?? [];
  let best: GlobalRow | null = null;
  let bestLen = Infinity;
  for (let len = 2; len < toks.length; len++) {
    for (let i = 0; i + len <= toks.length; i++) {
      const cand = ix.byName.get(toks.slice(i, i + len).join(" "));
      if (!cand || cand.id === row.id) continue;
      if (toks[i + len] === "like") continue; // "Huntington disease-like 2" is a different condition
      if (len < bestLen) {
        best = cand;
        bestLen = len;
      }
    }
    if (best) break;
  }
  return best ?? row;
}

const cap = (s: string) => s.replace(/\b[a-z]/, (c) => c.toUpperCase());

function distinctionFor(member: GlobalRow, head: GlobalRow, rest: string[]): string {
  const words = rest.map((w) => (ROMAN.test(w) ? w.toUpperCase() : w)).join(" ").replace(/\s+/g, " ").trim();
  const genes = member.genes.filter((g) => !head.genes.includes(g));
  const parts = [words ? cap(words) : "A named type"];
  if (genes.length && genes.length <= 3) parts.push(`linked to ${genes.join(", ")}`);
  return parts.join(", ");
}

export function groupFor(gi: GlobalIndex, rowOrHead: GlobalRow, data?: GroupsFile | null): DiseaseGroup {
  const head = headOf(gi, rowOrHead, data);
  const file = data?.groups?.[head.id];
  if (file?.members?.length) {
    const members: GroupMember[] = [];
    for (const m of file.members) {
      const id = typeof m === "string" ? m : m.id;
      const row = gi.byId.get(id);
      if (!row || row.id === head.id) continue;
      const given = typeof m === "string" ? undefined : (m.distinction ?? m.label);
      members.push({ row, distinction: given ? cap(given) : distinctionFor(row, head, remainder(names(gi).tokens.get(row.id) ?? [], names(gi).tokens.get(head.id) ?? [])) });
    }
    const lookalikes = (file.lookalikes ?? file.similar_names_different_conditions ?? []).map((l) => gi.byId.get(typeof l === "string" ? l : l.id)).filter((r): r is GlobalRow => !!r);
    return { head, members, lookalikes: lookalikes.length ? lookalikes : heuristic(gi, head).lookalikes, basis: "groups.json" };
  }
  return { ...heuristic(gi, head), head, basis: "name" };
}

function heuristic(gi: GlobalIndex, head: GlobalRow): { members: GroupMember[]; lookalikes: GlobalRow[] } {
  const ix = names(gi);
  const ht = ix.tokens.get(head.id) ?? [];
  // look-alike names by stem only for eponyms ("Huntington ..."), never for common words ("cystic ...")
  const eponym = /^[A-Z][a-z]/.test(head.name);
  const stem = eponym ? ht[0] : null;
  const members: GroupMember[] = [];
  const lookalikes: GlobalRow[] = [];
  for (const r of gi.rows) {
    if (r.id === head.id || SKIP.test(r.name)) continue;
    const t = ix.tokens.get(r.id) ?? [];
    const at = wordIndex(t, ht);
    if (at >= 0) {
      const rest = remainder(t, ht);
      // "Gaucher disease-ophthalmoplegia-... syndrome" is its own condition, not a type
      const ownSyndrome = rest.includes("syndrome") && !ht.includes("syndrome");
      if (isLike(rest, t[at + ht.length]) || ownSyndrome) lookalikes.push(r);
      else members.push({ row: r, distinction: distinctionFor(r, head, rest) });
    } else if (stem && t.includes(stem)) lookalikes.push(r);
  }
  members.sort((a, b) => b.row.n - a.row.n || a.row.name.length - b.row.name.length);
  lookalikes.sort((a, b) => b.n - a.n);
  return { members: members.slice(0, 8), lookalikes: lookalikes.slice(0, 8) };
}

/** groups.json when sync found it (web/available.json), else null: the heuristic answers. */
export async function loadGroups(): Promise<GroupsFile | null> {
  const a = await loadAvailableOnce();
  if (!a.groups) return null;
  const r = await fetch(`${GLOBAL_BASE}/groups.json`);
  return r.ok ? ((await r.json()) as GroupsFile) : null;
}
