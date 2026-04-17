import { Metadata } from "next";
import { getSiteUrl } from "@/lib/site";

const SITE_NAME = "SealingAI";
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
    openGraph: {
      title: fullTitle,
      description: fullDescription,
      url,
      siteName: SITE_NAME,
      type,
      images: image ? [{ url: image }] : [],
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description: fullDescription,
      images: image ? [image] : [],
    },
  };
}
