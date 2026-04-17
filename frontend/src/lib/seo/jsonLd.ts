import { getSiteUrl } from "@/lib/site";

const SITE_NAME = "SealingAI";
const DEFAULT_LOGO = `${getSiteUrl()}/images/logo-sealingai.png`;

export function generateOrganizationSchema() {
  const siteUrl = getSiteUrl();
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": SITE_NAME,
    "url": siteUrl,
    "logo": DEFAULT_LOGO,
    "description": "Sealing Intelligence — Professionelle technische Analyse und Vorqualifizierung von Dichtungslösungen.",
  };
}

export function generateArticleSchema({
  title,
  description,
  path,
  datePublished,
  author = SITE_NAME,
}: {
  title: string;
  description: string;
  path: string;
  datePublished?: string;
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
  };
}

export function generateTechArticleSchema({
  title,
  description,
  path,
  category,
}: {
  title: string;
  description: string;
  path: string;
  category: string;
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
  };
}
