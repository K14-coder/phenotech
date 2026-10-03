import type { Metadata } from "next";
import { Suspense } from "react";
import { GuidedStart } from "@/components/guided/GuidedStart";

export const metadata: Metadata = { title: "Let’s find the right information · Rare Disease Atlas" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <GuidedStart />
    </Suspense>
  );
}
