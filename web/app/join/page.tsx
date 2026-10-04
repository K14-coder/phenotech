import type { Metadata } from "next";
import { Suspense } from "react";
import { JoinView } from "@/components/community/JoinView";

export const metadata: Metadata = { title: "Join the community · Rare Disease Atlas" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <JoinView />
    </Suspense>
  );
}
