import type { Metadata } from "next";
import { Suspense } from "react";
import { CompareView } from "@/components/compare/CompareView";

export const metadata: Metadata = { title: "Before we join forces · Phenotech" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading…</div>}>
      <CompareView />
    </Suspense>
  );
}
