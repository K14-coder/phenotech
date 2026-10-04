import type { Metadata } from "next";
import { Suspense } from "react";
import { ApproachView } from "@/components/approach/ApproachView";

export const metadata: Metadata = { title: "Therapy approaches · Phenotech" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading…</div>}>
      <ApproachView />
    </Suspense>
  );
}
