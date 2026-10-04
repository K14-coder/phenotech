import type { Metadata } from "next";
import { ForgotView } from "@/components/community/EmailPages";

export const metadata: Metadata = { title: "Forgot your password · Rare Disease Atlas" };

export default function Page() {
  return <ForgotView />;
}
