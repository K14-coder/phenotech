import type { Metadata } from "next";
import { Suspense } from "react";
import { AtlasView } from "@/components/atlas/AtlasView";

export const metadata: Metadata = { title: "Atlas · Phenotech" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading the atlas…</div>}>
      <AtlasView />
    </Suspense>
  );
}
