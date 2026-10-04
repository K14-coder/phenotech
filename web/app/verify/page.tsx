import type { Metadata } from "next";
import { Suspense } from "react";
import { VerifyView } from "@/components/community/EmailPages";

export const metadata: Metadata = { title: "Confirm your email · Tasukeru", robots: { index: false } };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <VerifyView />
    </Suspense>
  );
}
