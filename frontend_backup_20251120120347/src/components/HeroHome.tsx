// frontend/src/components/HeroHome.tsx

import type { HomepageHero } from "@/lib/strapi";

type HeroHomeProps = {
  hero: HomepageHero | null;
};

export default function HeroHome({ hero }: HeroHomeProps) {
  const eyebrow = hero?.eyebrow ?? "SealAI";
  const title = hero?.title ?? "SealAI – KI für Dichtungstechnik";
  const description =
    hero?.description ??
    "Dein Assistent für Werkstoffauswahl, Profile und Konstruktion – mit Echtzeit-Recherche, fundierter Beratung und Integration in deinen Workflow.";
  const imageUrl = hero?.imageUrl;
  const imageAlt = hero?.imageAlt ?? "SealAI Hero";

  return (
    <section className="relative overflow-hidden min-h-[80vh] flex items-center bg-slate-950 text-white">
      {/* Hintergrundbild direkt aus Strapi */}
      {imageUrl && (
        <div className="absolute inset-0 -z-20">
          <img
            src={imageUrl}
            alt={imageAlt}
            className="h-full w-full object-cover"
          />
        </div>
      )}

      {/* Overlay-Gradient für bessere Lesbarkeit */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-slate-950/80 via-slate-950/70 to-slate-950/95" />

      {/* Inhalt */}
      <div className="relative z-10 mx-auto flex w-full max-w-6xl flex-col gap-12 px-6 py-16">
        {/* Top-Navigation (statisch) */}
        <header className="flex items-center justify-between text-sm text-slate-200/80">
          <div className="font-semibold tracking-[0.2em] uppercase text-xs">
            SealAI
          </div>
          <nav className="hidden gap-6 md:flex">
            <a href="#products" className="hover:text-white">
              Products
            </a>
            <a href="#api" className="hover:text-white">
              API
            </a>
            <a href="#company" className="hover:text-white">
              Company
            </a>
            <a href="#cases" className="hover:text-white">
              Cases
            </a>
          </nav>
          <a
            href="#try"
            className="rounded-full border border-white/20 px-4 py-1.5 text-xs font-medium hover:bg-white/10"
          >
            Try SealAI
          </a>
        </header>

        {/* Hero-Text aus Strapi */}
        <div className="max-w-2xl space-y-6">
          <p className="text-xs font-medium uppercase tracking-[0.25em] text-slate-300">
            {eyebrow}
          </p>
          <h1 className="text-4xl font-semibold leading-tight text-white sm:text-5xl md:text-6xl">
            {title}
          </h1>
          <p className="text-sm text-slate-200/90 sm:text-base">
            {description}
          </p>

          <div className="mt-6 flex flex-wrap gap-3 text-xs">
            <a
              href="#try"
              className="rounded-full bg-white px-5 py-2 font-medium text-slate-900 hover:bg-slate-100"
            >
              Try SealAI
            </a>
            <a
              href="#products"
              className="rounded-full border border-white/20 px-5 py-2 font-medium text-slate-100 hover:bg-white/5"
            >
              Mehr über die Produkte
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
