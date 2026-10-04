import type { Metadata } from "next";
import { Suspense } from "react";
import { HelpView } from "@/components/help/HelpView";

export const metadata: Metadata = { title: "We couldn’t find that yet · Tasukeru" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <HelpView />
    </Suspense>
  );
}
