import type { Metadata } from "next";
import { MechanismsView } from "@/components/mechanisms/MechanismsView";

export const metadata: Metadata = { title: "Mechanistic similarity · Rare Disease Atlas" };

export default function Page() {
  return <MechanismsView />;
}
