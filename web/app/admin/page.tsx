import type { Metadata } from "next";
import { AdminView } from "@/components/community/AdminView";

export const metadata: Metadata = { title: "Moderation · Tasukeru", robots: { index: false } };

export default function Page() {
  return <AdminView />;
}
