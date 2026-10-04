import type { Metadata } from "next";
import { MeView } from "@/components/community/MeView";

export const metadata: Metadata = { title: "My atlas · Phenotech" };

export default function Page() {
  return <MeView />;
}
