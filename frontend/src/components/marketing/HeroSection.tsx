import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { heroContent } from "@/lib/marketing/homeContent";

/**
 * Full-viewport intelligence hero. Server component (no client JS needed) so
 * the hero text/background never wait on hydration — keeps LCP fast.
 *
 * Background is a cropped, heavily dark-graded detail from the existing
 * sealing-intelligence-hero.png stock asset (technical dimension drawing +
 * O-ring seals, cropped clear of any person/laptop), composited entirely via
 * CSS (`.hero-technical-bg` + `.hero-technical-tint`). See the comment above
 * `.hero-technical-bg` in globals.css for the full asset-selection rationale
 * and the TODO pointing at where a final purpose-shot/rendered hero asset
 * should later replace it.
 */
export function HeroSection() {
  return (
    <section
      id="hero"
      data-header-theme="hero"
      className="hero-viewport section-anchor relative isolate -mt-[76px] overflow-hidden bg-[#04070d] text-white"
    >
      <div className="hero-technical-bg absolute inset-0" aria-hidden="true" />
      <div className="hero-technical-tint absolute inset-0" aria-hidden="true" />
      <div className="hero-technical-rings absolute inset-0" aria-hidden="true" />

      {/* Top scrim — keeps the transparent header legible over the image. */}
      <div
        className="absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-black/70 to-transparent"
        aria-hidden="true"
      />
      {/* Bottom scrim — keeps the bottom-anchored hero text legible. */}
      <div
        className="absolute inset-x-0 bottom-0 h-[58%] bg-gradient-to-t from-black/90 via-black/40 to-transparent"
        aria-hidden="true"
      />
      {/* Subtle vignette. */}
      <div
        className="pointer-events-none absolute inset-0 shadow-[inset_0_0_180px_60px_rgba(0,0,0,0.55)]"
        aria-hidden="true"
      />

      <div className="hero-fade-up absolute inset-x-0 bottom-0 z-10 flex flex-col items-center px-5 pb-16 text-center sm:px-8 sm:pb-20 lg:pb-24">
        <h1 className="max-w-[16ch] text-[clamp(2.35rem,6vw,4.75rem)] font-normal leading-[1.04] tracking-[-0.03em] text-white [text-wrap:balance]">
          {heroContent.headline}
        </h1>
        <p className="mt-5 max-w-[36ch] text-[clamp(1rem,1.6vw,1.2rem)] font-normal leading-relaxed text-white/78 [text-wrap:balance]">
          {heroContent.subline}
        </p>
        <Link
          href="#highlights"
          className="mt-8 inline-flex h-11 items-center gap-2 rounded-full bg-white px-6 text-[14px] font-semibold text-[#0a121f] transition-all hover:bg-white/90 active:translate-y-px"
        >
          {heroContent.cta}
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}
