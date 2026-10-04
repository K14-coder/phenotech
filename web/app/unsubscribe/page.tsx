import type { Metadata } from "next";
import { Suspense } from "react";
import { UnsubscribeView } from "@/components/community/EmailPages";

export const metadata: Metadata = { title: "Unsubscribe · Tasukeru", robots: { index: false } };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <UnsubscribeView />
    </Suspense>
  );
}
