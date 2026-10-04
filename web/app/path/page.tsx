import type { Metadata } from "next";
import { Suspense } from "react";
import { PathView } from "@/components/path/PathView";

export const metadata: Metadata = { title: "Path · Phenotech" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading…</div>}>
      <PathView />
    </Suspense>
  );
}
