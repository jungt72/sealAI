// frontend/src/components/HeroGrok.tsx

"use client";

import React from "react";
import HeroBackground from "./HeroBackground";

type HeroGrokProps = {
  eyebrow?: string | null;
  title?: string | null;
  description?: string | null;
  imageUrl?: string | null;
};

const DEFAULT_EYEBROW = "SealAI";
const DEFAULT_TITLE = "SealAI – KI für Dichtungstechnik";
const DEFAULT_DESCRIPTION =
  "Dein Assistent für Werkstoffauswahl, Profile und Konstruktion – mit Echtzeit-Recherche, fundierter Beratung und Integration in deinen Workflow.";

export default function HeroGrok({
  eyebrow,
  title,
  description,
  imageUrl,
}: HeroGrokProps) {
  const eyebrowText = eyebrow ?? DEFAULT_EYEBROW;
  const titleText = title ?? DEFAULT_TITLE;
  const descriptionText = description ?? DEFAULT_DESCRIPTION;

  return (
    <section className="relative overflow-hidden">
      {/* Hintergrund mit optionalem Strapi-Bild */}
      <HeroBackground imageUrl={imageUrl} />

      <div className="relative mx-auto flex min-h-[80vh] max-w-7xl items-center px-6 py-16 sm:min-h-[90vh] sm:py-24">
        <div className="max-w-3xl space-y-6">
          {/* Eyebrow aus Strapi */}
          <p className="text-xs font-medium uppercase tracking-[0.25em] text-zinc-400">
            {eyebrowText}
          </p>

          {/* Titel aus Strapi */}
          <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl lg:text-6xl">
            {titleText}
          </h1>

          {/* Beschreibung aus Strapi */}
          <p className="text-base leading-relaxed text-zinc-300 sm:text-lg">
            {descriptionText}
          </p>

          {/* einfache Call-to-Action */}
          <div className="mt-4 flex flex-wrap gap-4">
            <a
              href="/auth/signin"
              className="inline-flex items-center justify-center rounded-full bg-white px-5 py-2.5 text-sm font-medium text-slate-900 shadow-sm hover:bg-zinc-100"
            >
              Try SealAI
            </a>
            <a
              href="#products"
              className="inline-flex items-center justify-center rounded-full border border-white/20 px-5 py-2.5 text-sm font-medium text-zinc-200 hover:border-white/40 hover:bg-white/5"
            >
              Mehr über die Produkte
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
