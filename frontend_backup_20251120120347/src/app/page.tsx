// frontend/src/app/page.tsx

import HeroHome from "@/components/HeroHome";
import { getHomepageHero } from "@/lib/strapi";

export default async function HomePage() {
  const hero = await getHomepageHero();

  return (
    <main className="bg-slate-950 text-white min-h-screen">
      <HeroHome hero={hero} />

      <section
        id="products"
        className="mx-auto max-w-6xl px-6 py-16 text-sm text-slate-200/90"
      >
        <h2 className="mb-4 text-xl font-semibold text-white">
          Produkte &amp; Schnittstellen
        </h2>
        <p className="max-w-3xl">
          Hier kannst du deine bestehenden Produkt-Sektionen, Feature-Cards
          oder Integrationsbeschreibungen einfügen. Wichtig ist nur: Der
          Hero-Bereich oben wird jetzt vollständig über Strapi gesteuert.
        </p>
        <div className="mt-8">
          <a
            href="/dashboard"
            className="inline-flex items-center justify-center rounded-md bg-blue-600 px-6 py-3 text-base font-medium text-white shadow-sm hover:bg-blue-700"
          >
            Zum Dashboard
          </a>
        </div>
      </section>
    </main>
  );
}
