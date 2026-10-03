"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAtlas } from "./GraphProvider";
import { SearchBox } from "./search/SearchBox";
import { ViewingAs } from "./ViewingAs";

const NAV = [
  { href: "/", label: "Search" },
  { href: "/atlas", label: "Atlas" },
  { href: "/path", label: "Path" },
  { href: "/method", label: "How we know" },
  { href: "/impact", label: "Why 10×" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const atlas = useAtlas();
  const sample = atlas.status === "ready" && atlas.idx.graph.meta.sample;
  const isHome = pathname === "/";
  // the atlas shows the same switch next to its selection panel instead (brief's mockup)
  const onAtlas = pathname.startsWith("/atlas");

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white">
      <div className="flex h-14 items-center gap-6 px-5">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink">
          <Mark />
          Rare Disease Atlas
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1">
          {NAV.map((n) => {
            const active = n.href === "/" ? isHome : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                  active ? "bg-subtle font-medium text-ink" : "text-ink-3 hover:text-ink"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          {!onAtlas && <ViewingAs />}
          {!isHome && atlas.status === "ready" && (
            <div className="w-[300px] xl:w-[340px]">
              <SearchBox variant="compact" />
            </div>
          )}
          {sample && <SampleBadge />}
        </div>
      </div>
    </header>
  );
}

export function SampleBadge() {
  return (
    <span
      className="term inline-flex items-center gap-1.5 rounded-full border border-warn-line bg-warn-bg px-2.5 py-1 text-xs font-medium text-warn-ink no-underline"
      tabIndex={0}
      style={{ textDecoration: "none" }}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-warn-ink" aria-hidden="true" />
      Sample data
      <span className="term-tip" role="tooltip" style={{ left: "auto", right: 0 }}>
        This is placeholder data for demonstrating the interface. Evidence entries are not real sources and nothing
        here should be read as medical fact.
      </span>
    </span>
  );
}

function Mark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <line x1="4" y1="14" x2="10" y2="5" stroke="#a3a9b3" strokeWidth="1.2" />
      <line x1="10" y1="5" x2="16" y2="12" stroke="#a3a9b3" strokeWidth="1.2" />
      <line x1="4" y1="14" x2="16" y2="12" stroke="#a3a9b3" strokeWidth="1.2" strokeDasharray="2 2" />
      <circle cx="4" cy="14" r="2.4" fill="#C27C3A" />
      <circle cx="10" cy="5" r="2.8" fill="#1f5a96" />
      <circle cx="16" cy="12" r="2.4" fill="#5A9873" />
    </svg>
  );
}
