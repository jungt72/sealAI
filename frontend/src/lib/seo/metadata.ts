import { Metadata } from "next";
import { getSiteUrl } from "@/lib/site";

const SITE_NAME = "sealingAI";
const SITE_DESCRIPTION = "Professionelle technische Vorqualifizierung und Analyse für industrielle Dichtungslösungen.";

type SeoProps = {
  title?: string;
  description?: string;
  path?: string;
  type?: "website" | "article";
  image?: string;
};

export function createMetadata({
  title,
  description,
  path = "",
  type = "website",
  image,
}: SeoProps = {}): Metadata {
  const fullTitle = title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} — Sealing Intelligence`;
  const fullDescription = description || SITE_DESCRIPTION;
  const siteUrl = getSiteUrl();
  const url = `${siteUrl}${path.startsWith("/") ? path : `/${path}`}`;

  return {
    title: fullTitle,
    description: fullDescription,
    alternates: {
      canonical: url,
    },
    robots: {
      index: true,
      follow: true,
      "max-image-preview": "large",
    },
    openGraph: {
      title: fullTitle,
      description: fullDescription,
      url,
      siteName: SITE_NAME,
      type,
      locale: "de_DE",
      // Omit `images` entirely (not `[]`) when no explicit image is given —
      // an explicit-but-empty array overrides Next's file-convention
      // `opengraph-image.tsx` fallback instead of letting it fill the gap,
      // which silently dropped the per-article OG images this was meant to
      // enable.
      ...(image ? { images: [{ url: image }] } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description: fullDescription,
      ...(image ? { images: [image] } : {}),
    },
  };
}
