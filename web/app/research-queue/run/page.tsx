import type { Metadata } from "next";
import { QueueRunner } from "@/components/queue/QueueRunner";

export const metadata: Metadata = { title: "Research in your browser · Rare Disease Atlas" };

export default function Page() {
  return <QueueRunner />;
}
