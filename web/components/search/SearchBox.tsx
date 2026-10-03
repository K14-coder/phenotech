"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAtlas } from "../GraphProvider";
import { NodeTypeIcon } from "../NodeTypeIcon";
import { clustersOf, clusterSlot, neighbors, nodeHref, type GraphIndex } from "@/lib/graph";
import { MATCH_KIND_LABEL, type SearchHit } from "@/lib/search";
import { clusterColor } from "@/lib/style";
import { TYPE_LABEL } from "@/lib/text";
import type { AtlasNode } from "@/lib/types";
import { looksLikeVariant } from "@/lib/variant";

interface Props {
  variant?: "hero" | "compact" | "field";
  /** called instead of navigating (used by pickers) */
  onPick?: (node: AtlasNode) => void;
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
  // a pasted report line ("STXBP1 R388X", "c.1162C>T", "NM_...(GENE):c...") gets a top "Look up this variant" option
  const variantOption = variant !== "field" && looksLikeVariant(q);
  const total = hits.length + (variantOption ? 1 : 0);
  const active = Math.min(rawActive, Math.max(total - 1, 0));

  // a new focusKey (example chip, ?q= deep link, guided tour) opens the list even if no focus event fires
  const [seenFocusKey, setSeenFocusKey] = useState(0);
  if (focusKey && focusKey !== seenFocusKey) {
    setSeenFocusKey(focusKey);
    setOpen(true);
  }
  useEffect(() => {
    if (focusKey) inputRef.current?.focus();
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
    if (variantOption && i === 0) pickVariant();
    else pick(hits[i - (variantOption ? 1 : 0)]);
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
  const idx = atlas.status === "ready" ? atlas.idx : null;

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
          }}
          onFocus={() => openOnFocus && setOpen(true)}
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
              {hits.map((h, j) => {
                const i = j + (variantOption ? 1 : 0);
                return (
                  <li
                    key={h.node.id}
                    id={`${listId}-opt-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseEnter={() => setActive(i)}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      pick(h);
                    }}
                    className={`cursor-pointer px-3 ${hero ? "py-2.5" : "py-2"} ${i === active ? "bg-subtle" : ""}`}
                  >
                    {idx && <HitRow idx={idx} hit={h} detailed={hero} />}
                  </li>
                );
              })}
            </ul>
          ) : (
            <div id={`${listId}-list`} role="listbox" aria-label="Search results" className="px-4 py-4 text-sm text-ink-3">
              No match for “{q.trim()}”. Try a gene from a genetic report, a protein name, or a symptom.
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

function SearchGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" className="shrink-0 text-ink-3">
      <circle cx="8.5" cy="8.5" r="5.75" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <line x1="13" y1="13" x2="17.5" y2="17.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
