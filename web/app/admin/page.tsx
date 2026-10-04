import type { Metadata } from "next";
import { AdminView } from "@/components/community/AdminView";

export const metadata: Metadata = { title: "Moderation · Rare Disease Atlas", robots: { index: false } };

export default function Page() {
  return <AdminView />;
}
