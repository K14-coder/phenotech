"use client";

import { Fragment, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtlas } from "../GraphProvider";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { clustersOf, clusterSlot, neighbors, nodeHref, type GraphIndex } from "@/lib/graph";
import { headOf, loadGroups, type GroupsFile } from "@/lib/groups";
import { usePersona } from "@/lib/persona";
import { capFirst } from "@/lib/text";
import { GLOBAL_INDEX_KEY, ensureGlobalIndex, mappedAtlasId, normalizeTerm, rowHref, searchGlobal, type GlobalHit, type GlobalIndex, type GlobalRow } from "@/lib/global";
import { ensure, useResourceValue } from "@/lib/resource";
import { MATCH_KIND_LABEL, type SearchHit } from "@/lib/search";
import { clusterColor } from "@/lib/style";
import { TYPE_LABEL } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";
import { looksLikeVariant } from "@/lib/variant";

type Option = { kind: "atlas"; hit: SearchHit } | { kind: "global"; hit: GlobalHit };
type Group = { kind: "atlas" | "global"; options: Option[] };

interface Props {
  variant?: "hero" | "compact" | "field";
  /** called instead of navigating (used by pickers) */
  onPick?: (node: AtlasNode) => void;
  /** pickers that accept diseases outside the mapped families (basic data); without it a picker lists atlas results only */
  onPickGlobal?: (row: GlobalRow) => void;
  value?: string;
  onChange?: (q: string) => void;
  placeholder?: string;
  label?: string;
  /** "/" focuses this box */
  shortcut?: boolean;
  autoFocus?: boolean;
  openOnFocus?: boolean;
  /** bump to focus the input and open the result list (e.g. after an example chip is clicked) */
  focusKey?: number;
}

export function SearchBox({
  variant = "compact",
  onPick,
  onPickGlobal,
  value,
  onChange,
  placeholder,
  label = "Search the atlas",
  shortcut = variant !== "field",
  autoFocus,
  openOnFocus = true,
  focusKey,
}: Props) {
  const atlas = useAtlas();
  const router = useRouter();
  const [inner, setInner] = useState("");
  const q = value ?? inner;
  const setQ = (s: string) => (onChange ? onChange(s) : setInner(s));
  const [open, setOpen] = useState(false);
  const [rawActive, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const hits: SearchHit[] = useMemo(
    () => (atlas.status === "ready" ? atlas.search(q, variant === "hero" ? 8 : 7) : []),
    [atlas, q, variant],
  );
  const idx = atlas.status === "ready" ? atlas.idx : null;

  // every other rare disease (basic data): index.json loads on the first focus or keystroke
  const globalRes = useResourceValue<GlobalIndex>(GLOBAL_INDEX_KEY);
  const gi = globalRes?.status === "ready" ? (globalRes.data ?? null) : null;
  const globalAllowed = !onPick || !!onPickGlobal;
  const groups = useMemo((): Group[] => {
    let atlasHits = [...hits];
    const otherHits: GlobalHit[] = [];
    if (gi && idx && q.trim().length >= 2) {
      const seen = new Set(hits.map((h) => h.node.id));
      for (const g of searchGlobal(gi, q, 16)) {
        const node = g.row.atlas ? idx.nodeById.get(g.row.atlas) : undefined;
        if (node) {
          // a mapped disease found by a name only the global index knows: route to its atlas page
          if (seen.has(node.id)) continue;
          seen.add(node.id);
          atlasHits.push({ node, matched: g.kind === "name" ? g.row.name : g.matched, kind: g.kind === "gene" ? "gene" : g.kind === "id" ? "xref" : "synonym", score: 0.05 });
        } else if (globalAllowed) otherHits.push(g);
      }
    }
    // with other diseases to offer, drop the atlas's loosest fuzzy matches ("Rett" -> a researcher's name)
    if (otherHits.length) atlasHits = atlasHits.filter((h) => h.score <= 0.3);
    // mapped results stay on top when they are real matches. A clearly better match among all rare
    // diseases goes first so Enter opens it: an exact name ("Dravet" -> Dravet syndrome, over a grant
    // that mentions Dravet), or a whole-word prefix when the atlas only has loose fuzzy matches
    const atlasBest = Math.min(...atlasHits.map((h) => h.score), 1);
    const globalBest = Math.min(...otherHits.map((g) => g.rank), 9);
    const globalFirst = (globalBest <= 1 && atlasBest > 0.01) || (globalBest <= 2 && atlasBest > 0.1);
    const atlasGroup: Group = { kind: "atlas", options: atlasHits.map((hit) => ({ kind: "atlas", hit })) };
    const globalGroup: Group = {
      kind: "global",
      options: otherHits.slice(0, atlasHits.length ? 5 : 8).map((hit) => ({ kind: "global", hit })),
    };
    const ordered = globalFirst ? [globalGroup, atlasGroup] : [atlasGroup, globalGroup];
    return ordered.filter((g) => g.options.length);
  }, [hits, gi, idx, q, globalAllowed]);
  const allOptions = groups.flatMap((g) => g.options);

  // Simple mode: ONE clear answer (the general disease), then a guided start page; "See all matches" opens the list
  const persona = usePersona();
  const [showAll, setShowAll] = useState(false);
  const groupsRes = useResourceValue<GroupsFile | null>("global:groups");
  const guidedOn = persona === "family" && !onPick && !showAll;
  const guided = useMemo((): { id: string; label: string; via?: string } | null => {
    if (!guidedOn || !idx || q.trim().length < 2) return null;
    const disease = hits.find((h) => h.node.type === "disease" && h.score <= 0.1);
    if (disease) return { id: disease.node.id, label: disease.node.label, via: disease.kind !== "label" ? disease.matched : undefined };
    const gene = hits.find((h) => h.node.type === "gene" && h.score <= 0.05);
    const caused = gene ? neighbors(idx, gene.node.id, { relations: ["causes"], direction: "out" })[0] : undefined;
    if (caused) {
      const d = idx.nodeById.get(caused.other)!;
      return { id: d.id, label: d.label };
    }
    const top = gi ? searchGlobal(gi, q, 1)[0] : undefined;
    if (!top) return null;
    const head = headOf(gi!, top.row, groupsRes?.data);
    const mapped = mappedAtlasId(head, idx);
    if (mapped) return { id: mapped, label: idx.nodeById.get(mapped)!.label, via: top.matched };
    return { id: head.id, label: capFirst(head.name), via: top.kind !== "name" || head.id !== top.row.id ? top.matched : undefined };
  }, [guidedOn, idx, q, hits, gi, groupsRes]);
  const options = guided ? [] : allOptions;

  // a pasted report line ("STXBP1 R388X", "c.1162C>T", "NM_...(GENE):c...") gets a top "Look up this variant" option
  const variantOption = variant !== "field" && looksLikeVariant(q);
  const offset = variantOption ? 1 : 0;
  const total = offset + (guided ? 1 : options.length);
  const active = Math.min(rawActive, Math.max(total - 1, 0));
  const startGlobal = () => {
    if (globalAllowed) ensureGlobalIndex();
    if (persona === "family") ensure("global:groups", loadGroups);
  };

  // Home's big search box: fetch the index when the browser is idle, so the first keystroke finds everything
  useEffect(() => {
    if (variant !== "hero") return;
    // Safari has no requestIdleCallback
    const w = window as Omit<Window, "requestIdleCallback"> & { requestIdleCallback?: Window["requestIdleCallback"] };
    if (w.requestIdleCallback) {
      const h = w.requestIdleCallback(() => ensureGlobalIndex(), { timeout: 5000 });
      return () => window.cancelIdleCallback(h);
    }
    const t = setTimeout(() => ensureGlobalIndex(), 2500);
    return () => clearTimeout(t);
  }, [variant]);

  // a new focusKey (example chip, ?q= deep link, guided tour) opens the list even if no focus event fires
  const [seenFocusKey, setSeenFocusKey] = useState(0);
  if (focusKey && focusKey !== seenFocusKey) {
    setSeenFocusKey(focusKey);
    setOpen(true);
  }
  useEffect(() => {
    if (!focusKey) return;
    // a deep link or chip opens the list with text in it: make sure every rare disease is searchable
    ensureGlobalIndex();
    inputRef.current?.focus();
  }, [focusKey]);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const pickVariant = () => {
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
    router.push(`/variant?q=${encodeURIComponent(q.trim())}`);
  };

  const pickAt = (i: number) => {
    if (variantOption && i === 0) return pickVariant();
    if (guided) return pickGuided();
    const o = options[i - offset];
    if (o?.kind === "atlas") pick(o.hit);
    else if (o?.kind === "global") pickGlobal(o.hit);
  };

  const pickGlobal = (hit: GlobalHit | undefined) => {
    if (!hit) return;
    setOpen(false);
    setQ("");
    if (onPickGlobal) {
      onPickGlobal(hit.row);
      return;
    }
    inputRef.current?.blur();
    router.push(rowHref(hit.row, idx));
  };

  const pickGuided = () => {
    if (!guided) return;
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
    router.push(`/start?d=${encodeURIComponent(guided.id)}`);
  };

  const pick = (hit: SearchHit | undefined) => {
    if (!hit) return;
    setOpen(false);
    if (onPick) {
      onPick(hit.node);
      setQ("");
      return;
    }
    setQ("");
    inputRef.current?.blur();
    router.push(nodeHref(hit.node));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, Math.max(total - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      if (open && total) {
        e.preventDefault();
        pickAt(active);
      }
    } else if (e.key === "Escape") {
      if (open) setOpen(false);
      else setQ("");
    }
  };

  const showList = open && q.trim().length >= 2;
  const hero = variant === "hero";
  const globalLoading = globalAllowed && (!globalRes || globalRes.status === "loading");

  return (
    <div ref={wrapRef} className="relative w-full">
      <label className="sr-only" htmlFor={`${listId}-input`}>
        {label}
      </label>
      <div
        className={`flex items-center gap-3 rounded-lg border bg-white transition-colors focus-within:border-accent-700 ${
          hero ? "h-14 border-ink-4/70 px-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]" : "h-9 border-line px-3"
        }`}
      >
        <SearchGlyph size={hero ? 18 : 15} />
        <input
          ref={inputRef}
          id={`${listId}-input`}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={`${listId}-list`}
          aria-autocomplete="list"
          aria-activedescendant={showList && total ? `${listId}-opt-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          autoFocus={autoFocus}
          value={q}
          placeholder={
            placeholder ??
            (hero ? "Search a disease, gene, protein, symptom or patient group" : "Search diseases, genes, symptoms…")
          }
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
            setOpen(true);
            setShowAll(false);
            startGlobal();
          }}
          onFocus={() => {
            startGlobal();
            if (openOnFocus) setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className={`w-full bg-transparent text-ink placeholder:text-ink-3 focus:outline-none ${
            hero ? "text-[17px]" : "text-sm"
          }`}
          style={{ outline: "none" }}
        />
        {shortcut && !q && (
          <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 font-sans text-[11px] text-ink-3 sm:block">
            /
          </kbd>
        )}
      </div>

      {showList && (
        <div
          data-tour-extend
          className={`absolute left-0 right-0 z-50 mt-1.5 overflow-hidden rounded-lg border border-line bg-white shadow-[0_8px_24px_rgba(16,24,40,0.08)] ${
            hero ? "" : "min-w-[380px]"
          }`}
        >
          {total ? (
            <ul id={`${listId}-list`} role="listbox" aria-label="Search results" className="max-h-[420px] overflow-auto py-1 panel-scroll">
              {variantOption && (
                <li
                  id={`${listId}-opt-0`}
                  role="option"
                  aria-selected={active === 0}
                  onMouseEnter={() => setActive(0)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pickVariant();
                  }}
                  className={`cursor-pointer border-b border-line-2 px-3 ${hero ? "py-2.5" : "py-2"} ${active === 0 ? "bg-subtle" : ""}`}
                >
                  <p className="text-sm font-medium text-ink">Look up this variant</p>
                  <p className="truncate text-xs text-ink-3">“{q.trim()}” · find it in ClinVar and see what it points to</p>
                </li>
              )}
              {guided && (
                <>
                  <li
                    id={`${listId}-opt-${offset}`}
                    role="option"
                    aria-selected={active === offset}
                    onMouseEnter={() => setActive(offset)}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      pickGuided();
                    }}
                    className={`cursor-pointer px-4 py-3.5 ${active === offset ? "bg-subtle" : ""}`}
                  >
                    <p className="text-[17px] font-semibold text-ink">{guided.label}</p>
                    <p className="mt-0.5 text-sm text-ink-3">
                      {guided.via && normalizeTerm(guided.via) !== normalizeTerm(guided.label) ? `Also called ${guided.via}. ` : ""}
                      Tap to continue
                    </p>
                  </li>
                  <li role="presentation" className="border-t border-line-2 px-4 py-2">
                    <button
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        setShowAll(true);
                      }}
                      className="text-sm text-accent-700 hover:underline"
                    >
                      Not it? See all matches
                    </button>
                  </li>
                </>
              )}
              {!guided && groups.map((g, gi2) => {
                const start = offset + groups.slice(0, gi2).reduce((n, x) => n + x.options.length, 0);
                const label = g.kind === "global" ? "Other rare diseases (basic data)" : groups.length > 1 ? "In the atlas (mapped in depth)" : null;
                return (
                  <Fragment key={g.kind}>
                    {label && <GroupLabel border={gi2 > 0 || variantOption}>{label}</GroupLabel>}
                    {g.options.map((o, j) => {
                      const i = start + j;
                      return (
                        <li
                          key={o.kind === "atlas" ? o.hit.node.id : o.hit.row.id}
                          id={`${listId}-opt-${i}`}
                          role="option"
                          aria-selected={i === active}
                          onMouseEnter={() => setActive(i)}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            pickAt(i);
                          }}
                          className={`cursor-pointer px-3 ${hero ? "py-2.5" : "py-2"} ${i === active ? "bg-subtle" : ""}`}
                        >
                          {o.kind === "atlas" ? idx && <HitRow idx={idx} hit={o.hit} detailed={hero} /> : <GlobalHitRow hit={o.hit} />}
                        </li>
                      );
                    })}
                  </Fragment>
                );
              })}
            </ul>
          ) : (
            <div id={`${listId}-list`} role="listbox" aria-label="Search results" className="px-4 py-4 text-sm text-ink-3">
              {globalLoading && globalRes ? (
                <>Searching every rare disease for “{q.trim()}”…</>
              ) : (
                <>
                  No match for “{q.trim()}”{gi && globalAllowed ? ` in the atlas or among ${gi.rows.length.toLocaleString("en-US")} rare diseases` : ""}. Try a gene from a genetic
                  report, a protein name, or a symptom.
                </>
              )}
            </div>
          )}
          <div className="flex gap-4 border-t border-line-2 px-3 py-1.5 text-[11px] text-ink-3">
            <span>↑↓ move</span>
            <span>Enter open</span>
            <span>Esc close</span>
          </div>
        </div>
      )}
    </div>
  );
}

function HitRow({ idx, hit, detailed }: { idx: GraphIndex; hit: SearchHit; detailed: boolean }) {
  const n = hit.node;
  const c = clustersOf(idx, n.id)[0];
  const color = c ? clusterColor(clusterSlot(idx, c.id)) : undefined;
  const resolved = hit.kind !== "label";
  const linkedDisease =
    detailed && n.type === "gene"
      ? neighbors(idx, n.id, { relations: ["causes"], direction: "out" })
          .map((x) => idx.nodeById.get(x.other)?.label)
          .filter(Boolean)[0]
      : undefined;
  return (
    <div className="flex items-start gap-3">
      <NodeTypeIcon type={n.type} color={color} size={14} className="mt-[3px] shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          {resolved ? (
            <span className="truncate text-sm text-ink">
              <span className="text-ink-3">“{hit.matched}”</span>
              <span className="mx-1.5 text-ink-3" aria-label="resolves to">
                →
              </span>
              <span className="font-medium">{n.label}</span>
            </span>
          ) : (
            <span className="truncate text-sm font-medium text-ink">{n.label}</span>
          )}
          <span className="shrink-0 text-xs text-ink-3">{TYPE_LABEL[n.type]?.one ?? n.type}</span>
        </div>
        {resolved && <div className="text-xs text-ink-3">Matched {MATCH_KIND_LABEL[hit.kind]}</div>}
        {detailed && n.summary && <div className="mt-0.5 line-clamp-1 text-xs text-ink-3">{n.summary}</div>}
        {linkedDisease && <div className="mt-0.5 text-xs text-ink-2">Linked disease: {linkedDisease}</div>}
      </div>
    </div>
  );
}

function GroupLabel({ children, border = false }: { children: React.ReactNode; border?: boolean }) {
  return (
    <li role="presentation" className={`px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3 ${border ? "mt-1 border-t border-line-2" : ""}`}>
      {children}
    </li>
  );
}

/** A disease outside the mapped families: name (or "synonym → name"), genes, and that it is basic data. */
function GlobalHitRow({ hit }: { hit: GlobalHit }) {
  const r = hit.row;
  const resolved = hit.kind !== "name";
  const genes = r.genes.slice(0, 3).join(", ") + (r.genes.length > 3 ? ` +${r.genes.length - 3}` : "");
  return (
    <div className="flex items-start gap-3">
      <span className="mt-[5px] h-[11px] w-[11px] shrink-0 rounded-full border-[1.5px] border-ink-4" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {resolved ? (
          <p className="truncate text-sm text-ink">
            <span className="text-ink-3">“{hit.matched}”</span>
            <span className="mx-1.5 text-ink-3" aria-label="resolves to">
              →
            </span>
            <span className="font-medium">{r.name}</span>
          </p>
        ) : (
          <p className="truncate text-sm font-medium text-ink">{r.name}</p>
        )}
        <p className="truncate text-xs text-ink-3">
          {genes ? `${genes} · ` : ""}
          {r.n >= 5 ? `${r.n} annotated symptoms` : "few annotated symptoms"}
        </p>
      </div>
    </div>
  );
}

function SearchGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" className="shrink-0 text-ink-3">
      <circle cx="8.5" cy="8.5" r="5.75" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <line x1="13" y1="13" x2="17.5" y2="17.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
