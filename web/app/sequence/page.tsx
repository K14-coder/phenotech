import type { Metadata } from "next";
import { Suspense } from "react";
import { SequenceView } from "@/components/sequence/SequenceView";

export const metadata: Metadata = { title: "Check a DNA sequence or VCF file · Rare Disease Atlas" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <SequenceView />
    </Suspense>
  );
}
