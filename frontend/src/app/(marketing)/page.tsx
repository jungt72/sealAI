import { Metadata } from "next";

import { FinalCtaSection } from "@/components/marketing/FinalCtaSection";
import { HeroSection } from "@/components/marketing/HeroSection";
import { IntelligenceHighlights } from "@/components/marketing/IntelligenceHighlights";
import { SealingIntelligenceSection } from "@/components/marketing/SealingIntelligenceSection";
import { TeamUseCases } from "@/components/marketing/TeamUseCases";
import { TrustNeutralitySection } from "@/components/marketing/TrustNeutralitySection";
import { createMetadata } from "@/lib/seo/metadata";
import { generateOrganizationSchema, generateWebApplicationSchema, generateWebSiteSchema } from "@/lib/seo/jsonLd";

const OG_IMAGE = "/images/marketing/sealing-intelligence-hero.png";

const base = createMetadata({
  title: "Sealing Intelligence — Wissen, Bewertung und Orientierung in der Dichtungstechnik",
  description:
    "sealingAI ist die zentrale Anlaufstelle für Wissen, Bewertung und Orientierung in der industriellen Dichtungstechnik — neutral, strukturiert und nachvollziehbar.",
  path: "/",
  image: OG_IMAGE,
});

export const metadata: Metadata = {
  ...base,
  title: "sealingAI — Sealing Intelligence",
  openGraph: {
    ...base.openGraph,
    title: "sealingAI — Sealing Intelligence",
    description:
      "Die zentrale Anlaufstelle für Wissen, Bewertung und Orientierung in der industriellen Dichtungstechnik.",
  },
  twitter: {
    ...base.twitter,
    title: "sealingAI — Sealing Intelligence",
    description:
      "Die zentrale Anlaufstelle für Wissen, Bewertung und Orientierung in der industriellen Dichtungstechnik.",
  },
};

/**
 * No FAQPage JSON-LD here: this IA has no visible FAQ section on the
 * homepage, and structured data for non-visible content is discouraged.
 * (`generateFAQPageSchema` / `faqItems` still exist for the standalone
 * `WebsiteGuide` component — see homeContent.ts doc comments.)
 */
function JsonLd() {
  const schemas = [generateOrganizationSchema(), generateWebSiteSchema(), generateWebApplicationSchema()];
  return (
    <>
      {schemas.map((schema, i) => (
        <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
      ))}
    </>
  );
}

export default function LandingPage() {
  return (
    <div className="bg-background">
      <JsonLd />
      <HeroSection />
      <IntelligenceHighlights />
      <TeamUseCases />
      <SealingIntelligenceSection />
      <TrustNeutralitySection />
      <FinalCtaSection />
    </div>
  );
}
