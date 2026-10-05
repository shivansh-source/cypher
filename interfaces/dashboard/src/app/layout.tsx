import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { DemoBanner } from "@/components/DemoBanner";
import { getSessionClaims } from "@/lib/session";
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
  title: "Cypher",
  description:
    "Rupee-denominated cyber risk (Expected Annual Loss, Value at Risk) derived from security telemetry via Open FAIR and Monte Carlo simulation.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Local token check, no network: the layout renders on every navigation.
  const claims = await getSessionClaims();
  const org = claims?.orgName ? { name: claims.orgName, entityType: claims.entityType } : null;
  return (
    <html lang="en" className={`${poppins.variable} ${inter.variable}`} suppressHydrationWarning>
      {/* Extensions (Grammarly, password managers) add attributes to <body> before React loads. */}
      <body suppressHydrationWarning>
        <DemoBanner />
        <AppShell org={org}>
          <main>
            <Topbar />
            {children}
          </main>
        </AppShell>
      </body>
    </html>
  );
}
