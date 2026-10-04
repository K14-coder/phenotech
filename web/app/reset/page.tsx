import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetView } from "@/components/community/EmailPages";

export const metadata: Metadata = { title: "Choose a new password · Phenotech", robots: { index: false } };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ResetView />
    </Suspense>
  );
}
