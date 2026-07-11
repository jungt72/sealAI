import { getSiteUrl } from "@/lib/site";

const SITE_NAME = "sealingAI";
const DEFAULT_LOGO = `${getSiteUrl()}/images/logo/sealingai-wordmark-seal-blue.svg`;

type BreadcrumbItem = {
  name: string;
  path: string;
};

export function generateOrganizationSchema() {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": SITE_NAME,
    "url": siteUrl,
    "logo": DEFAULT_LOGO,
    "description": "Sealing Intelligence — Professionelle technische Analyse und Vorqualifizierung von Dichtungslösungen.",
    // TODO(seo): add real external profile URLs here once they exist (LinkedIn
    // company page, Xing, etc.) — `sameAs` is an E-E-A-T entity-trust signal
    // and only helps when it points at independently verifiable profiles. A
    // self-referencing URL (the previous value) is a no-op, so it's omitted
    // rather than kept as a placeholder.
  };
}

export function generateArticleSchema({
  title,
  description,
  path,
  datePublished,
  dateModified,
  author = SITE_NAME,
}: {
  title: string;
  description: string;
  path: string;
  datePublished?: string;
  /** Falls back to `datePublished` — Google treats a missing dateModified as staler than one that just repeats the publish date. */
  dateModified?: string;
  author?: string;
}) {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": title,
    "description": description,
    "url": `${siteUrl}${path}`,
    "author": {
      "@type": "Organization",
      "name": author,
    },
    "publisher": {
      "@type": "Organization",
      "name": SITE_NAME,
      "logo": {
        "@type": "ImageObject",
        "url": DEFAULT_LOGO,
      },
    },
    "datePublished": datePublished,
    "dateModified": dateModified || datePublished,
  };
}

export function generateBreadcrumbSchema(items: BreadcrumbItem[]) {
  const siteUrl = getSiteUrl();

  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": items.map((item, index) => ({
      "@type": "ListItem",
      "position": index + 1,
      "name": item.name,
      "item": `${siteUrl}${item.path}`,
    })),
  };
}

export function generateCollectionPageSchema({
  title,
  description,
  path,
  items,
}: {
  title: string;
  description: string;
  path: string;
  items: BreadcrumbItem[];
}) {
  const siteUrl = getSiteUrl();

  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": title,
    "description": description,
    "url": `${siteUrl}${path}`,
    "isPartOf": {
      "@type": "WebSite",
      "name": SITE_NAME,
      "url": siteUrl,
    },
    "mainEntity": {
      "@type": "ItemList",
      "itemListElement": items.map((item, index) => ({
        "@type": "ListItem",
        "position": index + 1,
        "name": item.name,
        "url": `${siteUrl}${item.path}`,
      })),
    },
  };
}

export function generateTechArticleSchema({
  title,
  description,
  path,
  category,
  datePublished,
  dateModified,
}: {
  title: string;
  description: string;
  path: string;
  category: string;
  datePublished?: string;
  dateModified?: string;
}) {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    "headline": title,
    "description": description,
    "url": `${siteUrl}${path}`,
    "proficiencyLevel": "Expert",
    "about": {
      "@type": "Thing",
      "name": category,
    },
    "publisher": {
      "@type": "Organization",
      "name": SITE_NAME,
    },
    "datePublished": datePublished,
    "dateModified": dateModified || datePublished,
  };
}

export function generateWebSiteSchema() {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": SITE_NAME,
    "url": siteUrl,
    "inLanguage": "de-DE",
    "description":
      "sealingAI strukturiert Dichtungsfälle, erkennt fehlende Angaben und berechnet erste technische Kennwerte.",
    "publisher": {
      "@type": "Organization",
      "name": SITE_NAME,
      "url": siteUrl,
    },
  };
}

export function generateWebApplicationSchema() {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": SITE_NAME,
    "url": siteUrl,
    "applicationCategory": "BusinessApplication",
    "operatingSystem": "Web",
    "inLanguage": "de-DE",
    "description":
      "Technische Plattform für Dichtungstechnik: Dichtungsfälle strukturieren, fehlende Angaben erkennen, erste Kennwerte berechnen und qualifizierte Anfragen vorbereiten.",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "EUR",
      "description": "Kostenloser Vorcheck und kostenlose Analyse nach Login.",
    },
    "publisher": {
      "@type": "Organization",
      "name": SITE_NAME,
      "url": siteUrl,
    },
  };
}

/**
 * The free, deterministic precheck tool (src/lib/hero-precheck/precheck.ts —
 * no LLM, real physics calc, never recommends a material). Only real,
 * verifiable fields: no `aggregateRating`/`review` — none exist, and
 * fabricating one is a Google spam-policy violation, not a growth hack.
 */
export function generatePrecheckToolSchema() {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "sealingAI Dichtungsfall-Vorcheck",
    "url": `${siteUrl}/anfrage/dichtung-auslegen-lassen`,
    "applicationCategory": "UtilityApplication",
    "operatingSystem": "Web",
    "inLanguage": "de-DE",
    "description":
      "Kostenloser, deterministischer Vorcheck: strukturiert Dichtungstyp, Situation, Medium und Betriebsdaten, berechnet die Umfangsgeschwindigkeit und zeigt, welche Angaben für eine belastbare Bewertung noch fehlen. Keine Materialempfehlung, kein Login erforderlich.",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "EUR",
    },
    "publisher": {
      "@type": "Organization",
      "name": SITE_NAME,
      "url": siteUrl,
    },
  };
}

type FaqItem = {
  question: string;
  answer: string;
};

/** FAQPage schema — use ONLY for FAQ content that is visibly rendered on the page. */
export function generateFAQPageSchema(items: FaqItem[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": items.map((item) => ({
      "@type": "Question",
      "name": item.question,
      "acceptedAnswer": {
        "@type": "Answer",
        "text": item.answer,
      },
    })),
  };
}
