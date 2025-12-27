// frontend/src/app/layout.tsx

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "../styles/globals.css"; // <- korrekter Pfad zur globalen CSS
import Providers from "./providers";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://sealai.net";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "SealAI – KI-Fachberater für Dichtungstechnik",
    template: "%s | SealAI",
  },
  description:
    "SealAI ist eine B2B-KI-Plattform für technische Bedarfsanalyse und Dichtungstechnik. Sie unterstützt bei Werkstoffauswahl, Profilgestaltung und der Erstellung technischer Reports.",
  alternates: {
    canonical: siteUrl,
  },
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "SealAI",
    title: "SealAI – KI-Fachberater für Dichtungstechnik",
    description:
      "Dein Assistent für Werkstoffauswahl, Profile und Konstruktion – mit Echtzeit-Recherche, fundierter Beratung und Integration in deinen Workflow.",
  },
  twitter: {
    card: "summary_large_image",
    title: "SealAI – KI-Fachberater für Dichtungstechnik",
    description:
      "Technische KI-Beratung für Dichtungstechnik: Werkstoffe, Profile, Konstruktion und Reports.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="de" className={inter.variable}>
      <body className="bg-black text-zinc-200 antialiased font-sans">
        {/* Hintergrund-Layer */}
        <div className="pointer-events-none fixed inset-0 z-[-3] bg-black" />
        <div
          className="pointer-events-none fixed inset-0 z-[-2] bg-gradient-to-b from-[#040815] via-[#0A1328] to-[#0B1020]"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none fixed inset-0 z-[-1] opacity-35"
          aria-hidden="true"
        >
          <canvas
            className="absolute inset-0 w-full h-full"
            aria-hidden="true"
          />
        </div>

        <Providers>
          <main className="min-h-[100dvh] bg-transparent text-zinc-200">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
