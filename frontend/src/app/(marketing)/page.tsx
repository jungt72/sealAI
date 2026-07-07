import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { TrackedLink } from "@/components/analytics/TrackedLink";
import { HeroPrecheckCard } from "@/components/marketing/HeroPrecheckCard";
import { LayerSection } from "@/components/marketing/LayerSection";
import { WebsiteGuide } from "@/components/marketing/WebsiteGuide";
import { createMetadata } from "@/lib/seo/metadata";
import {
  generateFAQPageSchema,
  generateOrganizationSchema,
  generateWebApplicationSchema,
  generateWebSiteSchema,
} from "@/lib/seo/jsonLd";
import {
  ANALYZE_HREF,
  PARTNER_HREF,
  anwender,
  branchenplattform,
  experienceLayer,
  faqItems,
  finalCta,
  guide,
  heroContent,
  hersteller,
  layerSection,
  nutzen,
  output,
  realityCheck,
  soFunktioniert,
  unterschied,
  vertrauen,
} from "@/lib/marketing/homeContent";

const OG_IMAGE = "/images/marketing/sealing-intelligence-hero.png";

const base = createMetadata({
  title: "Dichtungstechnik verstehen, strukturieren und qualifiziert anfragen",
  description:
    "sealingAI strukturiert Dichtungsfälle, erkennt fehlende Angaben, berechnet erste Kennwerte und erstellt technische Grundlagen für Auslegung, Beschaffung und Herstelleranfragen.",
  path: "/",
  image: OG_IMAGE,
});

export const metadata: Metadata = {
  ...base,
  title: "sealingAI – Dichtungstechnik verstehen, strukturieren und qualifiziert anfragen",
  openGraph: {
    ...base.openGraph,
    title: "sealingAI – Sealing Intelligence für Dichtungstechnik",
    description:
      "Aus unvollständigen Angaben wird ein technischer Fall. sealingAI macht Dichtungstechnik strukturiert, nachvollziehbar und besser anfragbar.",
  },
  twitter: {
    ...base.twitter,
    title: "sealingAI – Sealing Intelligence für Dichtungstechnik",
    description:
      "Aus unvollständigen Angaben wird ein technischer Fall. sealingAI macht Dichtungstechnik strukturiert, nachvollziehbar und besser anfragbar.",
  },
};

const CONTAINER = "mx-auto max-w-[1240px] px-5 sm:px-8";

function JsonLd() {
  const schemas = [
    generateOrganizationSchema(),
    generateWebSiteSchema(),
    generateWebApplicationSchema(),
    generateFAQPageSchema(faqItems),
  ];
  return (
    <>
      {schemas.map((schema, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
    </>
  );
}

export default function LandingPage() {
  return (
    <div className="bg-background">
      <JsonLd />

      {/* 1 — Hero */}
      <section className={`${CONTAINER} pb-16 pt-14 sm:pt-20 lg:pb-24 lg:pt-24`}>
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-14">
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-seal-blue">
              {heroContent.eyebrow}
            </p>
            <h1 className="mt-4 max-w-[15ch] text-[clamp(2.6rem,4.3vw,4rem)] font-medium leading-[1.05] tracking-[-0.035em] text-foreground [text-wrap:balance]">
              {heroContent.headline}
            </h1>
            <p className="mt-4 text-[clamp(1.1rem,1.6vw,1.35rem)] font-normal leading-snug text-seal-blue">
              {heroContent.subheadline}
            </p>
            <div className="mt-6 max-w-[54ch] space-y-4 text-[15px] leading-7 text-muted-foreground">
              {heroContent.description.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
            <p className="mt-6 text-[16px] font-medium leading-7 text-foreground">
              {heroContent.strongSentence}
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <TrackedLink
                href={ANALYZE_HREF}
                analyticsEvent="landing_cta_clicked"
                analyticsPayload={{ cta: "hero_analyze", location: "hero" }}
                className="inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-all hover:bg-seal-blue/92 active:translate-y-px"
              >
                Kostenlos analysieren
                <ArrowRight size={16} />
              </TrackedLink>
              <Link
                href="/#fuer-hersteller"
                className="inline-flex h-11 items-center rounded-full border border-border bg-white px-6 text-[14px] font-semibold text-foreground transition-colors hover:border-seal-blue/40"
              >
                Herstellerpartner werden
              </Link>
            </div>
            <p className="mt-5 text-[12px] leading-5 text-muted-foreground">{heroContent.trustLine}</p>
          </div>

          <div className="lg:pl-2">
            <HeroPrecheckCard />
          </div>
        </div>
      </section>

      {/* 2 — Reality Check */}
      <section id={realityCheck.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
                {realityCheck.headline}
              </h2>
              <div className="mt-6 space-y-2 text-[15px] leading-7 text-muted-foreground">
                {realityCheck.intro.map((line) => (
                  <p key={line} className={line.startsWith("„") ? "text-[18px] font-medium text-foreground" : ""}>
                    {line}
                  </p>
                ))}
              </div>
              <p className="mt-6 text-[15px] leading-7 text-muted-foreground">{realityCheck.lead}</p>
            </div>
            <div className="rounded-xl border border-border bg-[#FAFAFB] p-6 sm:p-8">
              <ul className="grid gap-3">
                {realityCheck.points.map((point) => (
                  <li key={point} className="flex items-start gap-3 text-[14px] leading-6 text-foreground">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-seal-blue" aria-hidden />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <p className="mt-10 max-w-3xl text-[clamp(1.15rem,2vw,1.5rem)] font-medium leading-snug text-foreground">
            {realityCheck.strong}
          </p>
          <p className="mt-3 text-[15px] text-muted-foreground">{realityCheck.closing}</p>
        </div>
      </section>

      {/* 3 — Nutzen */}
      <section id={nutzen.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <div className="grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
              {nutzen.headline}
            </h2>
            <div className="mt-6 space-y-4 text-[15px] leading-7 text-muted-foreground">
              {nutzen.text.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-white p-6 sm:p-8">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
              Sauber getrennte Zustände
            </p>
            <ul className="mt-4 flex flex-wrap gap-2">
              {nutzen.states.map((state) => (
                <li
                  key={state.label}
                  className="rounded-full border border-border bg-[#FAFAFB] px-3 py-1.5 text-[13px] font-medium text-foreground"
                >
                  {state.label}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* 4 — Konkreter Output */}
      <section id={output.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <h2 className="max-w-3xl text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
            {output.headline}
          </h2>
          <p className="mt-6 text-[15px] text-muted-foreground">{output.intro}</p>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-2">
            {output.items.map((item) => (
              <li key={item} className="flex items-center gap-3 rounded-[14px] border border-border bg-[#FAFAFB] px-4 py-3 text-[14px] text-foreground">
                <Check size={15} className="shrink-0 text-seal-blue" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
          <div className="mt-8 space-y-1 text-[15px] leading-7">
            {output.closing.map((line, i) => (
              <p key={line} className={i === output.closing.length - 1 ? "font-medium text-foreground" : "text-muted-foreground"}>
                {line}
              </p>
            ))}
          </div>
          <TrackedLink
            href={ANALYZE_HREF}
            analyticsEvent="landing_cta_clicked"
            analyticsPayload={{ cta: "output_analyze", location: "output" }}
            className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-all hover:bg-seal-blue/92"
          >
            {output.cta}
            <ArrowRight size={16} />
          </TrackedLink>
        </div>
      </section>

      {/* 5 — Anwender */}
      <section id={anwender.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <h2 className="max-w-3xl text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
          {anwender.headline}
        </h2>
        <p className="mt-5 max-w-3xl text-[15px] leading-7 text-muted-foreground">{anwender.intro}</p>
        <div className="mt-10 grid gap-5 sm:grid-cols-2">
          {anwender.cards.map((card) => (
            <article key={card.title} className="rounded-xl border border-border bg-white p-6">
              <h3 className="text-[19px] font-medium text-foreground">{card.title}</h3>
              <p className="mt-3 text-[14px] leading-6 text-muted-foreground">{card.text}</p>
              <p className="mt-4 border-t border-border pt-4 text-[13px] font-medium text-seal-blue">
                Nutzen: {card.nutzen}
              </p>
            </article>
          ))}
        </div>
        <TrackedLink
          href={ANALYZE_HREF}
          analyticsEvent="landing_cta_clicked"
          analyticsPayload={{ cta: "anwender_analyze", location: "anwender" }}
          className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-all hover:bg-seal-blue/92"
        >
          {anwender.cta}
          <ArrowRight size={16} />
        </TrackedLink>
      </section>

      {/* 6 — Hersteller */}
      <section id={hersteller.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <div className="grid gap-10 lg:grid-cols-[1fr_1fr]">
            <div>
              <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
                {hersteller.headline}
              </h2>
              <div className="mt-6 space-y-3 text-[15px] leading-7 text-muted-foreground">
                {hersteller.intro.map((line) => (
                  <p key={line} className={line.startsWith("„") ? "text-[17px] font-medium text-foreground" : ""}>
                    {line}
                  </p>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-[#FAFAFB] p-6 sm:p-8">
              <p className="text-[14px] font-medium text-foreground">{hersteller.briefingIntro}</p>
              <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
                {hersteller.briefing.map((item) => (
                  <li key={item} className="flex items-center gap-2 text-[13px] text-muted-foreground">
                    <Check size={13} className="shrink-0 text-seal-blue" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <p className="mt-8 max-w-3xl text-[clamp(1.1rem,1.8vw,1.4rem)] font-medium leading-snug text-foreground">
            {hersteller.strong}
          </p>
          <div className="mt-4 space-y-1 text-[14px] leading-6 text-muted-foreground">
            {hersteller.closing.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
          <Link
            href={PARTNER_HREF}
            className="mt-8 inline-flex h-11 items-center gap-2 rounded-full border border-seal-blue/25 bg-white px-6 text-[14px] font-semibold text-seal-blue transition-colors hover:bg-seal-light-blue"
          >
            {hersteller.cta}
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* 7 — Unterschied */}
      <section id={unterschied.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <h2 className="max-w-4xl text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
          {unterschied.headline}
        </h2>
        <div className="mt-10 grid gap-10 lg:grid-cols-[0.9fr_1.1fr]">
          <ul className="space-y-3">
            {unterschied.compare.map((line) => (
              <li key={line} className="text-[15px] leading-6 text-muted-foreground">
                {line}
              </li>
            ))}
            <li className="pt-3 text-[17px] font-medium text-foreground">{unterschied.strong}</li>
          </ul>
          <div className="rounded-xl border border-border bg-white p-6 sm:p-8">
            <p className="text-[14px] font-medium text-foreground">{unterschied.questionsIntro}</p>
            <ul className="mt-4 grid gap-3">
              {unterschied.questions.map((q) => (
                <li key={q} className="flex items-start gap-3 text-[14px] leading-6 text-muted-foreground">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-seal-accent" aria-hidden />
                  {q}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-8 max-w-3xl text-[15px] leading-7 text-muted-foreground">{unterschied.closing}</p>
      </section>

      {/* 8 — Layer section */}
      <section id={layerSection.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <h2 className="max-w-3xl text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
            {layerSection.headline}
          </h2>
          <p className="mt-5 max-w-3xl text-[15px] leading-7 text-muted-foreground">{layerSection.subline}</p>
          <div className="mt-10">
            <LayerSection />
          </div>
        </div>
      </section>

      {/* 9 — Website Guide */}
      <section id={guide.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <div className="text-center">
          <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
            {guide.headline}
          </h2>
          <p className="mx-auto mt-5 max-w-2xl text-[15px] leading-7 text-muted-foreground">{guide.subline}</p>
        </div>
        <div className="mt-10">
          <WebsiteGuide />
        </div>
      </section>

      {/* 10 — Experience layer */}
      <section id={experienceLayer.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <div className="grid gap-10 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
                {experienceLayer.headline}
              </h2>
              <div className="mt-6 space-y-4 text-[15px] leading-7 text-muted-foreground">
                {experienceLayer.text.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
              <p className="mt-6 text-[clamp(1.1rem,1.8vw,1.4rem)] font-medium leading-snug text-foreground">
                {experienceLayer.strong}
              </p>
            </div>
            <div className="rounded-xl border border-border bg-[#FAFAFB] p-6 sm:p-8">
              <ul className="grid gap-2.5">
                {experienceLayer.items.map((item) => (
                  <li key={item} className="flex items-center gap-3 text-[14px] text-foreground">
                    <Check size={15} className="shrink-0 text-seal-blue" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* 11 — So funktioniert */}
      <section id={soFunktioniert.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <h2 className="max-w-3xl text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
          {soFunktioniert.headline}
        </h2>
        <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {soFunktioniert.steps.map((step, i) => (
            <li key={step.title} className="rounded-xl border border-border bg-white p-6">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-seal-light-blue text-[13px] font-semibold text-seal-blue">
                {i + 1}
              </span>
              <h3 className="mt-4 text-[17px] font-medium text-foreground">{step.title}</h3>
              <p className="mt-2 text-[14px] leading-6 text-muted-foreground">{step.text}</p>
            </li>
          ))}
        </ol>
        <TrackedLink
          href={ANALYZE_HREF}
          analyticsEvent="landing_cta_clicked"
          analyticsPayload={{ cta: "how_analyze", location: "so_funktioniert" }}
          className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-all hover:bg-seal-blue/92"
        >
          {soFunktioniert.cta}
          <ArrowRight size={16} />
        </TrackedLink>
      </section>

      {/* 12 — Vertrauensversprechen (dark) */}
      <section id={vertrauen.id} className="bg-[#0D1016] text-white">
        <div className={`${CONTAINER} py-16 lg:py-28`}>
          <h2 className="max-w-3xl text-[clamp(1.9rem,3.4vw,3rem)] font-medium leading-[1.08] tracking-[-0.03em]">
            {vertrauen.headline}
          </h2>
          <div className="mt-6 max-w-2xl space-y-3 text-[15px] leading-7 text-white/72">
            {vertrauen.text.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </div>
          <p className="mt-6 text-[clamp(1.3rem,2.4vw,2rem)] font-medium leading-snug text-white">
            {vertrauen.strong}
          </p>
          <p className="mt-6 max-w-2xl text-[15px] leading-7 text-white/72">{vertrauen.detail}</p>
          <p className="mt-8 border-t border-white/15 pt-6 text-[15px] font-medium text-white/90">
            {vertrauen.closing}
          </p>
        </div>
      </section>

      {/* 13 — Branchenplattform */}
      <section id={branchenplattform.id} className={`${CONTAINER} py-16 lg:py-24`}>
        <h2 className="text-[clamp(1.9rem,3.1vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.03em] text-foreground">
          {branchenplattform.headline}
        </h2>
        <p className="mt-5 text-[15px] text-muted-foreground">{branchenplattform.intro}</p>
        <ul className="mt-6 flex flex-wrap gap-2">
          {branchenplattform.items.map((item) => (
            <li key={item} className="rounded-full border border-border bg-white px-3.5 py-1.5 text-[13px] font-medium text-foreground">
              {item}
            </li>
          ))}
        </ul>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {branchenplattform.tiers.map((tier) => (
            <div key={tier.name} className="rounded-xl border border-border bg-white p-5">
              <p className="text-[14px] font-semibold text-seal-blue">{tier.name}</p>
              <p className="mt-2 text-[13px] leading-6 text-muted-foreground">{tier.text}</p>
            </div>
          ))}
        </div>
        <p className="mt-8 max-w-3xl text-[15px] leading-7 text-muted-foreground">{branchenplattform.closing}</p>
      </section>

      {/* 14 — Final CTA */}
      <section id={finalCta.id} className="border-t border-border bg-white">
        <div className={`${CONTAINER} py-16 lg:py-24`}>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="flex flex-col rounded-xl border border-seal-blue bg-seal-blue p-8 text-white">
              <h2 className="text-[clamp(1.6rem,2.6vw,2.25rem)] font-medium leading-tight">{finalCta.headline}</h2>
              <p className="mt-4 text-[15px] leading-7 text-white/80">{finalCta.text}</p>
              <div className="mt-auto pt-8">
                <TrackedLink
                  href={ANALYZE_HREF}
                  analyticsEvent="landing_cta_clicked"
                  analyticsPayload={{ cta: "final_analyze", location: "final_cta" }}
                  className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-6 text-[14px] font-semibold text-seal-blue transition hover:bg-white/90"
                >
                  {finalCta.button}
                  <ArrowRight size={16} />
                </TrackedLink>
                <p className="mt-3 text-[12px] leading-5 text-white/65">{finalCta.smallLine}</p>
              </div>
            </div>
            <div className="flex flex-col rounded-xl border border-border bg-[#FAFAFB] p-8">
              <h2 className="text-[clamp(1.6rem,2.6vw,2.25rem)] font-medium leading-tight text-foreground">
                {finalCta.manufacturer.headline}
              </h2>
              <p className="mt-4 text-[15px] leading-7 text-muted-foreground">{finalCta.manufacturer.text}</p>
              <div className="mt-auto pt-8">
                <Link
                  href={PARTNER_HREF}
                  className="inline-flex h-11 items-center gap-2 rounded-full bg-seal-accent px-6 text-[14px] font-semibold text-white transition hover:brightness-105"
                >
                  {finalCta.manufacturer.button}
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
