import type { Metadata } from "next";
import { MethodView } from "@/components/method/MethodView";

export const metadata: Metadata = { title: "How we know · Tasukeru" };

export default function Page() {
  return <MethodView />;
}
