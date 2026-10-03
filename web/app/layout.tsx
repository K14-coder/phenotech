import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { GraphProvider } from "@/components/GraphProvider";
import { EvidenceProvider } from "@/components/evidence/EvidenceProvider";
import { SiteHeader } from "@/components/SiteHeader";
import { AiProvider } from "@/components/ai/AiProvider";
import { TourProvider } from "@/components/tour/TourProvider";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Rare Disease Atlas",
  description:
    "Find who shares your disease's biology, what useful work already exists, and what to do together, with the evidence for every connection.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="flex min-h-full flex-col bg-white text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[100] focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow"
        >
          Skip to content
        </a>
        <GraphProvider>
          <EvidenceProvider>
            <AiProvider>
              <TourProvider>
                <SiteHeader />
                <main id="main" className="flex flex-1 flex-col">
                  {children}
                </main>
              </TourProvider>
            </AiProvider>
          </EvidenceProvider>
        </GraphProvider>
      </body>
    </html>
  );
}
