import { Navbar } from "@/components/ui/Navbar";
import { SectionNav } from "@/components/ui/SectionNav";
import { IntroHeadline } from "@/components/ui/IntroHeadline";
import { ProductTabs } from "@/components/ui/ProductTabs";
import { FeatureGrid } from "@/components/ui/FeatureGrid";
import { CommunityBlock } from "@/components/ui/CommunityBlock";
import { NextSteps } from "@/components/ui/NextSteps";
import { ImageTextBlock } from "@/components/ui/ImageTextBlock";
import LandingCtaClient from "@/components/LandingCtaClient";
import { getLandingPageData } from "@/lib/strapi";
import type { Section } from "@/lib/types";

const slugify = (value?: string) =>
  (value ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");

const buildContentId = (section: Section) =>
  slugify(section.title) || `section-${section.id}`;

const normalizeSectionHref = (href?: string) => {
  if (!href) return "#products";
  if (href.startsWith("#")) return href;
  const trimmed = href.replace(/^\//, "");
  return trimmed ? `#${trimmed}` : "#products";
};

export default async function Page() {
  const data = await getLandingPageData();
  const { global, homepage } = data;

  const sectionNavItems =
    global?.sectionNavItems?.map((item) => ({
      ...item,
      href: normalizeSectionHref(item.href),
    })) ?? [];

  const productTabs = homepage?.productTabs ?? [];
  const features = homepage?.features ?? [];
  const sections = homepage?.contentSections ?? [];
  const nextSteps = homepage?.nextSteps ?? [];
  const community = homepage?.community;
  const introHeadline = homepage?.introHeadline ?? "";

  return (
    <>
      {global?.navbar && <Navbar data={global.navbar} />}
      <main className="min-h-[100dvh] bg-transparent text-zinc-200">
        <LandingCtaClient data={homepage?.hero} />
        {sectionNavItems.length > 0 && <SectionNav sections={sectionNavItems} />}
        {introHeadline && (
          <div className="scroll-mt-32">
            <IntroHeadline text={introHeadline} />
          </div>
        )}
        {productTabs.length > 0 && (
          <div id="products" className="scroll-mt-32">
            <ProductTabs tabs={productTabs} />
          </div>
        )}
        {features.length > 0 && (
          <div id="features" className="scroll-mt-32">
            <FeatureGrid features={features} />
          </div>
        )}
        {sections.map((section) => (
          <div
            id={buildContentId(section)}
            key={section.id}
            className="scroll-mt-32"
          >
            <ImageTextBlock data={section} />
          </div>
        ))}
        {nextSteps.length > 0 && (
          <div id="next-steps" className="scroll-mt-32">
            <NextSteps steps={nextSteps} />
          </div>
        )}
        {community && (
          <div id="community" className="scroll-mt-32">
            <CommunityBlock data={community} />
          </div>
        )}
        <footer className="bg-slate-950/80 border-t border-white/10 text-zinc-300 py-10">
          <div className="max-w-6xl mx-auto px-6 flex flex-col gap-2 text-sm">
            <div className="flex flex-wrap gap-4 text-xs uppercase tracking-widest text-zinc-400">
              <span>{global?.siteName || "SealAI"}</span>
              <span>© {new Date().getFullYear()}</span>
            </div>
            {global?.copyrightText && (
              <p className="text-xs text-zinc-500">{global.copyrightText}</p>
            )}
            <p className="text-xs text-zinc-500">
              Powered by Strapi-driven content.
            </p>
          </div>
        </footer>
      </main>
    </>
  );
}
