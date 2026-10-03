import type { Metadata } from "next";
import { DiseaseView } from "@/components/disease/DiseaseView";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  return { title: `${decodeURIComponent(id).replace(/^disease:/, "")} · Rare Disease Atlas` };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DiseaseView param={id} />;
}
