'use client';

import { signIn } from 'next-auth/react';
import { CheckCircle, Shield, Zap, BarChart4 } from 'lucide-react';
import dynamic from 'next/dynamic';

// KORREKTER Dynamic Import für verschobene Komponente!
const HeroBackground = dynamic(() => import('../components/HeroBackground'), { ssr: false });

export default function LandingPage() {
  return (
    <main className="min-h-screen flex flex-col bg-gradient-to-b from-white to-gray-50">
      {/* Header-Bar */}
      <header className="w-full flex items-center justify-between px-12 py-6">
        <div className="flex items-center">
          <img
            src="/logo_sai.svg"
            alt="SealAI Logo"
            className="h-16 md:h-20"
            style={{ minWidth: '64px' }}
          />
        </div>
        <nav>
          <ul className="flex space-x-8">
            <li className="text-gray-500 font-medium hover:text-blue-700 cursor-pointer transition">Demo</li>
            <li className="text-gray-500 font-medium hover:text-blue-700 cursor-pointer transition">Kontakt</li>
            <li>
              <button
                onClick={() => signIn(undefined, { callbackUrl: '/dashboard' })}
                className="px-5 py-2 rounded-xl bg-blue-700 hover:bg-blue-800 text-white font-semibold shadow transition"
              >
                Login
              </button>
            </li>
          </ul>
        </nav>
      </header>

      {/* Hero Section mit volumetrischem Background */}
      <section className="relative w-full py-14 md:py-20 flex flex-col items-center justify-center overflow-hidden">
        <HeroBackground />
        <div className="relative z-10 w-full flex flex-col items-center">
          <h1 className="text-5xl md:text-6xl font-extrabold text-gray-900 text-center tracking-tight mb-6">
            Dichtungstechnik.<br className="hidden md:block" />Neu gedacht.
          </h1>
          <p className="text-xl md:text-2xl text-gray-600 text-center mb-10 max-w-2xl">
            Deine KI-gestützte Fachberatung für Werkstoffauswahl, Dichtungsprofile und technische Innovation.
          </p>
          <button
            onClick={() => signIn(undefined, { callbackUrl: '/dashboard' })}
            className="px-8 py-4 rounded-2xl bg-blue-700 hover:bg-blue-800 text-white text-lg font-semibold shadow-xl transition mb-2"
          >
            Jetzt kostenlos testen
          </button>
        </div>
      </section>

      {/* USP Section */}
      <section className="w-full flex justify-center items-center py-6">
        <span className="bg-blue-50 text-blue-800 text-base md:text-lg rounded-xl px-6 py-2 font-medium shadow-sm">
          Für Industrie, Entwicklung & Einkauf: Schnell. Sicher. Expertengeführt.
        </span>
      </section>

      {/* Highlight-Kacheln */}
      <section className="w-full flex justify-center py-12 px-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8 max-w-6xl w-full">
          <Highlight
            icon={<Zap className="w-8 h-8 text-blue-600" />}
            title="Schnell & intelligent"
            desc="Sekundenschnelle Analyse & Beratung rund um die Uhr."
          />
          <Highlight
            icon={<CheckCircle className="w-8 h-8 text-blue-600" />}
            title="Technische Expertise"
            desc="Empfehlungen und Lösungen nach Industriestandard."
          />
          <Highlight
            icon={<Shield className="w-8 h-8 text-blue-600" />}
            title="Sicher & DSGVO-konform"
            desc="Deutsche Cloud, Datenschutz auf höchstem Niveau."
          />
          <Highlight
            icon={<BarChart4 className="w-8 h-8 text-blue-600" />}
            title="Transparente Ergebnisse"
            desc="Alle Schritte nachvollziehbar, Reports und Analysen für Ihr Team."
          />
        </div>
      </section>

      {/* Footer */}
      <footer className="w-full flex flex-col items-center justify-center py-6 text-xs text-gray-400 mt-6">
        <span>&copy; {new Date().getFullYear()} SealAI</span>
        <div className="space-x-4 mt-2">
          <a href="/impressum" className="underline hover:text-gray-600">Impressum</a>
          <a href="/datenschutz" className="underline hover:text-gray-600">Datenschutz</a>
        </div>
      </footer>
    </main>
  );
}

function Highlight({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="flex flex-col items-center bg-white rounded-2xl shadow-xl p-8 text-center h-full">
      <div className="mb-4">{icon}</div>
      <div className="font-bold text-lg mb-2">{title}</div>
      <div className="text-gray-500 text-sm">{desc}</div>
    </div>
  );
}
