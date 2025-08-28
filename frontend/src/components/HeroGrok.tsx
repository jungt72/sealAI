// src/components/HeroGrok.tsx — Hero (100dvh) mit Gradients & Spotlights, ohne Nebel
"use client";

import React from "react";
import { signIn } from "next-auth/react";
import Starfield from "./Starfield";

export default function HeroGrok() {
  return (
    <section className="relative overflow-hidden h-[100dvh] min-h-[100dvh] flex">
      {/* Sternenhimmel */}
      <Starfield />

      {/* Sehr dunkler, fast schwarzer Blauverlauf von oben */}
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-b
                   from-[#040815] via-[#0A1328]/80 to-transparent"
        aria-hidden
      />

      {/* Spotlight rechts (volumetrisch, atmend) */}
      <div
        className="pointer-events-none absolute right-[-18%] top-1/2 -translate-y-1/2
                   w-[70vw] h-[70vw]
                   bg-[radial-gradient(closest-side,rgba(255,255,255,0.9),rgba(99,102,241,0.35),transparent_70%)]
                   blur-3xl opacity-80 animate-glow-pulse"
        aria-hidden
      />

      {/* Sekundäres leises Spotlight links */}
      <div
        className="pointer-events-none absolute left-[-25%] top-1/2 -translate-y-1/2
                   w-[55vw] h-[55vw]
                   bg-[radial-gradient(closest-side,rgba(37,99,235,0.35),rgba(59,130,246,0.18),transparent_70%)]
                   blur-3xl opacity-35 animate-glow-pulse"
        aria-hidden
      />

      {/* Horizontaler Light-Sweep rechts */}
      <div
        className="pointer-events-none absolute inset-y-0 right-[8%] w-[60vw]
                   bg-[linear-gradient(90deg,transparent,rgba(180,200,255,0.25)_40%,transparent)]
                   blur-2xl opacity-60 animate-glow-sweep"
        aria-hidden
      />

      {/* Boden-Glow (Gradient statt Nebel; Video kommt später hier drüber) */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[46svh]
                   bg-gradient-to-t from-[#1b2142]/70 via-[#121936]/35 to-transparent"
        aria-hidden
      />

      {/* Platzhalter-Layer für späteres Video (wabernder Nebel) */}
      <div className="pointer-events-none absolute inset-0 z-[5]" aria-hidden />

      {/* Inhalt zentriert */}
      <div className="relative z-10 mx-auto max-w-7xl px-6 w-full h-full flex">
        <div className="max-w-4xl m-auto text-center flex flex-col items-center justify-center gap-6">
          <p className="text-xs uppercase tracking-widest text-zinc-400 mx-auto">SealAI</p>

          <h1
            className="text-[16vw] leading-none font-semibold text-white/90
                       sm:text-[12vw] md:text-[10vw] lg:text-[9vw]
                       [text-shadow:0_0_30px_rgba(120,140,255,0.18),0_0_10px_rgba(255,255,255,0.05)]"
          >
            SealAI
          </h1>

          <p className="max-w-2xl text-lg text-zinc-300">
            Dein Assistent für Werkstoffauswahl, Profile und Konstruktion – mit Echtzeit-Recherche,
            fundierter Beratung und Integration in deinen Workflow.
          </p>

          {/* Eingabe-Box */}
          <div className="mt-2 max-w-2xl w-full mx-auto rounded-2xl border border-white/10 bg-black/50 backdrop-blur">
            <div className="flex items-center">
              <input
                readOnly
                value="What do you want to know?"
                className="w-full bg-transparent px-5 py-4 text-sm text-zinc-400 outline-none"
              />
              <button
                onClick={() => signIn(undefined, { callbackUrl: "/dashboard" })}
                className="m-2 inline-flex items-center justify-center rounded-xl border border-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/10"
                aria-label="Try SealAI"
              >
                →
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Scroll-Hinweis */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/40 text-xl animate-bounce">▾</div>
    </section>
  );
}
