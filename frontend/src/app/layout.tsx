import type { Metadata } from "next";
import "@fontsource-variable/google-sans-flex/standard.css";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Providers } from "@/components/Providers";
import { GoogleMarketingTags } from "@/components/analytics/GoogleMarketingTags";
import { RybbitAnalytics } from "@/components/analytics/RybbitAnalytics";
import { getSiteOrigin } from "@/lib/site";

const siteOrigin = getSiteOrigin();

export const metadata: Metadata = {
  title: "SealingAI — Sealing Intelligence",
  description: "Professionelle technische Vorqualifizierung und Analyse für industrielle Dichtungslösungen.",
  metadataBase: siteOrigin,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de" className="light" suppressHydrationWarning>
      <body className={cn("font-sans bg-background text-[#1F1F1F] antialiased")}>
        <RybbitAnalytics />
        <GoogleMarketingTags />
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
