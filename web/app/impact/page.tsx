import type { Metadata } from "next";
import { ImpactView } from "@/components/impact/ImpactView";

export const metadata: Metadata = { title: "Why this could be 10× faster · Rare Disease Atlas" };

export default function Page() {
  return <ImpactView />;
}
