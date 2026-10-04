import type { Metadata } from "next";
import { CohortView } from "@/components/research/CohortView";

export const metadata: Metadata = { title: "Cohort view · Tasukeru" };

export default function Page() {
  return <CohortView />;
}
