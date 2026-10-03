import type { Metadata } from "next";
import { MethodView } from "@/components/method/MethodView";

export const metadata: Metadata = { title: "How we know · Rare Disease Atlas" };

export default function Page() {
  return <MethodView />;
}
