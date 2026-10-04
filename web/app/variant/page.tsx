import type { Metadata } from "next";
import { Suspense } from "react";
import { VariantView } from "@/components/variant/VariantView";

export const metadata: Metadata = { title: "Variant lookup · Tasukeru" };

export default function Page() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-3">Loading…</div>}>
      <VariantView />
    </Suspense>
  );
}
