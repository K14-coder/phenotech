import type { Metadata } from "next";
import { ForgotView } from "@/components/community/EmailPages";

export const metadata: Metadata = { title: "Forgot your password · Phenotech" };

export default function Page() {
  return <ForgotView />;
}
