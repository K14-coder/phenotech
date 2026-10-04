import type { Metadata } from "next";
import { MeView } from "@/components/community/MeView";

export const metadata: Metadata = { title: "My atlas · Rare Disease Atlas" };

export default function Page() {
  return <MeView />;
}
