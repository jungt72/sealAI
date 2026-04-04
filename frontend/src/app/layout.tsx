import type { Metadata } from "next";
import { Inter, Syne, DM_Sans } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Providers } from "@/components/Providers";
import { getSiteOrigin } from "@/lib/site";

const inter = Inter({
  subsets: ["latin"],
  // CSS-Variable erlaubt Tailwind-Klasse font-sans und Überschreibung per CSS
  variable: "--font-inter",
  // Metric-matched Fallback verhindert CLS beim ersten Render
  adjustFontFallback: true,
  // Kein FOIT — Text wird sofort mit Fallback angezeigt
  display: "swap",
});

// Landing-Page Headlines
const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  display: "swap",
});

// Landing-Page Body
const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});
const siteOrigin = getSiteOrigin();

export const metadata: Metadata = {
  title: "SealAI | Industrial AI Orchestration",
  description: "High-Performance Agent Supervisor for Hydrogen Sealing Tech.",
  metadataBase: siteOrigin,
  openGraph: {
    title: "SealAI | Industrial AI Orchestration",
    description: "High-Performance Agent Supervisor for Hydrogen Sealing Tech.",
    url: siteOrigin,
    siteName: "SealAI",
    locale: "en_US",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={cn(inter.variable, syne.variable, dmSans.variable, "font-sans bg-slate-950 text-slate-100 antialiased")}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
