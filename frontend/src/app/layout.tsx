import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Providers } from "@/components/Providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SealAI | Industrial AI Orchestration",
  description: "High-Performance Agent Supervisor for Hydrogen Sealing Tech.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={cn(inter.className, "bg-slate-950 text-slate-100 antialiased")}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
