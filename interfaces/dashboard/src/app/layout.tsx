import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { DemoBanner } from "@/components/DemoBanner";
import { Topbar } from "@/components/Topbar";

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Su₹aksha — Cyber Risk Quantification",
  description:
    "Rupee-denominated cyber risk (Expected Annual Loss, Value at Risk) derived from security telemetry via Open FAIR and Monte Carlo simulation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${poppins.variable} ${inter.variable}`}>
      <body>
        <DemoBanner />
        <AppShell>
          <main>
            <Topbar />
            {children}
          </main>
        </AppShell>
      </body>
    </html>
  );
}
