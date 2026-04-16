import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Providers } from "@/components/Providers";
import { getSiteOrigin } from "@/lib/site";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  adjustFontFallback: true,
  display: "swap",
});

const siteOrigin = getSiteOrigin();

export const metadata: Metadata = {
  title: "Gemini",
  description: "Experience the next generation of AI.",
  metadataBase: siteOrigin,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="light">
      <body className={cn(inter.variable, "font-sans bg-[#F8F9FA] text-[#1F1F1F] antialiased")}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
