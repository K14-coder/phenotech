import type { Metadata } from "next";
import { Suspense } from "react";
import { ContributeView } from "@/components/contribute/ContributeView";

export const metadata: Metadata = { title: "Contribute what you know · Tasukeru" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading…</div>}>
      <ContributeView />
    </Suspense>
  );
}
