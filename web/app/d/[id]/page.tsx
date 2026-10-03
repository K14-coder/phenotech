import type { Metadata } from "next";
import { GlobalDiseaseView } from "@/components/global/GlobalDiseaseView";

// Any rare disease outside the mapped families (basic data). The page sets the disease name as the
// title once the index has loaded in the browser.
export const metadata: Metadata = { title: "Rare disease (basic data) · Rare Disease Atlas" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GlobalDiseaseView param={id} />;
}
