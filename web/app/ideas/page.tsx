import type { Metadata } from "next";
import { IdeasView } from "@/components/ideas/IdeasView";

export const metadata: Metadata = { title: "Ideas worth testing · Phenotech" };

export default function Page() {
  return <IdeasView />;
}
