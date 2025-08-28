// src/app/page.tsx — x.ai/Grok-Stil, Sektionen ohne harte Übergänge (transparent)
"use client";

import { signIn } from "next-auth/react";
import HeroGrok from "../components/HeroGrok";

function Header() {
  return (
    <header className="absolute top-0 left-0 right-0 z-50 bg-transparent">
      <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
        <a href="/" className="flex items-center gap-3">
          <img src="/logo_sai.svg" alt="SealAI" className="h-6 w-auto" />
          <span className="sr-only">SealAI</span>
        </a>
        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-8 text-sm text-zinc-300">
            <li><a href="#products" className="hover:text-white">Products</a></li>
            <li><a href="#api" className="hover:text-white">API</a></li>
            <li><a href="#company" className="hover:text-white">Company</a></li>
            <li><a href="#careers" className="hover:text-white">Careers</a></li>
            <li><a href="#news" className="hover:text-white">News</a></li>
          </ul>
        </nav>
        <div className="flex items-center gap-3">
          <a
            href="/auth/signin"
            onClick={(e) => { e.preventDefault(); signIn(undefined, { callbackUrl: "/dashboard" }); }}
            className="inline-flex items-center rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/10"
          >
            Try SealAI
          </a>
        </div>
      </div>
    </header>
  );
}

export default function Landing() {
  return (
    // bg-transparent: globaler SiteBackground scheint durch (kein Übergang)
    <main className="min-h-[100dvh] bg-transparent text-zinc-200">
      <Header />

      {/* Hero (Gradients + Spotlights, 100dvh) */}
      <HeroGrok />

      {/* Products — ohne border, transparenter Bereich */}
      <section id="products" className="relative bg-transparent">
        {/* ganz dezente weiche Trennung via Schattenverlauf (kein harter Strich) */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-10 bg-gradient-to-b from-black/0 via-black/0 to-black/10" aria-hidden />

        <div className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
          <h2 className="text-2xl font-medium text-white">Products</h2>
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <Card title="Advisor" desc="Fachberater für Dichtungstechnik mit Retrieval, Tools und Reports." cta="Use now" href="/auth/signin" />
            <Card id="api" title="API" desc="Nutze SealAI programmatically. Secure auth, streaming, webhooks." cta="Build now" href="/api" secondary />
            <Card title="Developer Docs" desc="Schnellstart, Beispiele und Best Practices für Integration." cta="Learn more" href="/docs" secondary />
          </div>
        </div>
      </section>

      {/* News — ohne border, transparent */}
      <section id="news" className="relative bg-transparent">
        <div className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
          <h2 className="text-2xl font-medium text-white">Latest news</h2>
          <ul className="mt-6 space-y-6">
            <li className="flex flex-col sm:flex-row sm:items-baseline gap-2">
              <span className="text-sm text-zinc-400 w-32 shrink-0">July 2025</span>
              <a href="#" className="text-zinc-100 hover:underline">
                SealAI Advisor v0.9 – neue Material- und Profilagenten, schnellere Streams.
              </a>
            </li>
            <li className="flex flex-col sm:flex-row sm:items-baseline gap-2">
              <span className="text-sm text-zinc-400 w-32 shrink-0">June 2025</span>
              <a href="#" className="text-zinc-100 hover:underline">
                API Preview – Auth via Keycloak, LangGraph Streaming, Redis Checkpointer.
              </a>
            </li>
          </ul>
        </div>
      </section>

      {/* Footer — ohne border, transparent */}
      <footer id="company" className="relative bg-transparent mt-8">
        <div className="mx-auto max-w-7xl px-6 py-12 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-8 text-sm">
          <div className="col-span-2">
            <img src="/logo_sai.svg" alt="SealAI" className="h-6 w-auto mb-4" />
            <p className="text-zinc-400">© {new Date().getFullYear()} SealAI</p>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Products</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="#products" className="hover:text-white">Advisor</a></li>
              <li><a href="#api" className="hover:text-white">API</a></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Company</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="#company" className="hover:text-white">About</a></li>
              <li><a href="#careers" className="hover:text-white">Careers</a></li>
              <li><a href="/impressum" className="hover:text-white">Impressum</a></li>
              <li><a href="/datenschutz" className="hover:text-white">Datenschutz</a></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Resources</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="/status" className="hover:text-white">Status</a></li>
              <li><a href="/docs" className="hover:text-white">Docs</a></li>
            </ul>
          </div>
        </div>
      </footer>
    </main>
  );
}

function Card({
  title, desc, cta, href, secondary, id
}: {
  title: string; desc: string; cta: string; href: string; secondary?: boolean; id?: string
}) {
  return (
    <a
      id={id}
      href={href}
      className={[
        "group block rounded-2xl border p-6 transition bg-white/[0.03]",
        secondary ? "border-white/15 hover:bg-white/5" : "border-white/20 hover:bg-white/[0.06]",
      ].join(" ")}
    >
      <div className="text-base font-medium text-white">{title}</div>
      <p className="mt-2 text-sm text-zinc-400">{desc}</p>
      <div className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-white">
        {cta}
        <svg className="size-4 opacity-70 group-hover:translate-x-0.5 transition" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 12h14M13 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </a>
  );
}
