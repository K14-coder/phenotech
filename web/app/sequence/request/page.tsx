import type { Metadata } from "next";
import { Suspense } from "react";
import { RequestView } from "@/components/sequence/RequestView";

export const metadata: Metadata = {
  title: "Don’t have a DNA file? Request one · Phenotech",
  description: "How to get the data from a genetic test you already had, or how to get tested: lab request routes, your rights, a request letter, and testing programmes.",
};

export default function Page() {
  return (
    <Suspense fallback={null}>
      <RequestView />
    </Suspense>
  );
}
