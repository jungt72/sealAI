// frontend/types.ts
// Zentrale Typdefinitionen für das Landing-Page-CMS (Strapi)
//
// Aktuell bewusst generisch gehalten, damit der Build stabil läuft,
// auch wenn sich die Strapi-Struktur noch ändert oder mockData leicht anderes Shape hat.
// Wenn du möchtest, können wir das später gezielt verfeinern.

export interface LandingPageData {
  // Basisfelder, die eine Landing Page typischerweise enthält.
  // Du kannst diese Liste später beliebig erweitern oder konkretisieren.
  id?: number | string;
  slug?: string;

  title?: string;
  subtitle?: string;
  heroTitle?: string;
  heroSubtitle?: string;
  heroCtaLabel?: string;
  heroCtaHref?: string;

  // Abschnitt(e) oben/unten, z. B. Features, Sections etc.
  sections?: Array<Record<string, unknown>>;
  features?: Array<Record<string, unknown>>;

  // FAQs, Testimonials, usw.
  faqs?: Array<Record<string, unknown>>;
  testimonials?: Array<Record<string, unknown>>;

  // SEO / Metadaten
  seo?: {
    title?: string;
    description?: string;
    keywords?: string[];
    [key: string]: unknown;
  };

  // Catch-all, damit wir nicht am Typ scheitern, wenn Strapi mehr liefert.
  [key: string]: unknown;
}

