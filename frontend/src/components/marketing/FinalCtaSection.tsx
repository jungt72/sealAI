import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { TrackedLink } from "@/components/analytics/TrackedLink";
import { PARTNER_HREF, REGISTER_HREF, finalCta } from "@/lib/marketing/homeContent";

const CONTAINER = "mx-auto max-w-[1240px] px-5 sm:px-8";

/** Final CTA — light, reduced closing section. */
export function FinalCtaSection() {
  return (
    <section
      id={finalCta.id}
      data-header-theme="light"
      className="section-anchor border-t border-border bg-background"
    >
      <div className={`${CONTAINER} py-20 lg:py-28`}>
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-[clamp(2.1rem,3.8vw,3.2rem)] font-normal leading-[1.06] tracking-[-0.03em] text-foreground">
            {finalCta.headline}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground">{finalCta.subline}</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <TrackedLink
              href={REGISTER_HREF}
              analyticsEvent="register_started"
              analyticsPayload={{ method: "cta", source: "final_cta" }}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-all hover:bg-seal-blue/92 active:translate-y-px"
            >
              {finalCta.primaryCta}
              <ArrowRight size={16} aria-hidden="true" />
            </TrackedLink>
            <Link
              href={PARTNER_HREF}
              className="inline-flex h-11 items-center rounded-full border border-border bg-white px-6 text-[14px] font-semibold text-foreground transition-colors hover:border-seal-blue/40"
            >
              {finalCta.secondaryCta}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
