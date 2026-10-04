import type { Metadata } from "next";
import { QueueHome } from "@/components/queue/QueueHome";

export const metadata: Metadata = {
  title: "Research queue · Tasukeru",
  description: "Volunteers research rare diseases in parallel with their own OpenAI access; every quote is verified against PubMed.",
};

export default function Page() {
  return <QueueHome />;
}
