import type { Metadata } from "next";
import { QueueRunner } from "@/components/queue/QueueRunner";

export const metadata: Metadata = { title: "Research in your browser · Tasukeru" };

export default function Page() {
  return <QueueRunner />;
}
