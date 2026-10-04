import type { Metadata } from "next";
import { EmailPreview } from "@/components/community/EmailPreview";

export const metadata: Metadata = { title: "Email previews · Tasukeru", robots: { index: false } };

export default function Page() {
  return <EmailPreview />;
}
