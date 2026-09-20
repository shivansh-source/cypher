import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { DemoBanner } from "@/components/DemoBanner";
import { Nav } from "@/components/Nav";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Su₹aksha — Cyber Risk Quantification",
  description:
    "Rupee-denominated cyber risk (Expected Annual Loss, Value at Risk) derived from security telemetry via Open FAIR and Monte Carlo simulation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        <DemoBanner />
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
            <div>
              <p className="text-base font-semibold tracking-tight text-ink">
                Su<span className="text-accent">₹</span>aksha
              </p>
              <p className="text-xs text-faint">
                Cyber risk, denominated in rupees
              </p>
            </div>
            <Nav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
          {children}
        </main>
        <footer className="border-t border-line px-6 py-4">
          <p className="mx-auto max-w-7xl text-xs leading-relaxed text-faint">
            Figures are produced by a deterministic Open FAIR + Monte Carlo
            engine, never by a model. They rest on the modelling assumptions in{" "}
            <code className="text-muted">core/assumptions.py</code>, which are
            uncalibrated placeholders — read any figure alongside{" "}
            <code className="text-muted">docs/ASSUMPTIONS.md</code>.
          </p>
        </footer>
      </body>
    </html>
  );
}
