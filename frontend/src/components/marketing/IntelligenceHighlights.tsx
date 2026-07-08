import { BookOpen, Gauge, HeartHandshake, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { highlights } from "@/lib/marketing/homeContent";

const ICONS: Record<string, LucideIcon> = {
  wissenshub: BookOpen,
  materialvergleich: Layers,
  dichtungssituation: Gauge,
  "hersteller-fit": HeartHandshake,
};

const CONTAINER = "mx-auto max-w-[1240px] px-5 sm:px-8";

/**
 * "Sealing Intelligence Highlights" — light, airy precedent-style section.
 * Cards are deliberately abstract icon tiles, not fabricated product
 * screenshots or real manufacturer logos (none are rights-cleared yet).
 */
export function IntelligenceHighlights() {
  return (
    <section
      id={highlights.id}
      data-header-theme="light"
      className="section-anchor border-t border-border bg-background"
    >
      <div className={`${CONTAINER} py-20 lg:py-28`}>
        <div className="max-w-2xl">
          <h2 className="text-[clamp(2rem,3.4vw,2.9rem)] font-normal leading-[1.08] tracking-[-0.025em] text-foreground">
            {highlights.headline}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground">{highlights.intro}</p>
        </div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {highlights.cards.map((card) => {
            const Icon = ICONS[card.key] ?? BookOpen;
            return (
              <article
                key={card.key}
                className="rounded-[18px] border border-border bg-white p-2 shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-shadow hover:shadow-[0_8px_24px_rgba(15,23,42,0.10)]"
              >
                <div className="flex h-40 items-center justify-center rounded-[14px] bg-[linear-gradient(160deg,#F4F5F6_0%,#EBEDEF_100%)]">
                  <Icon size={34} strokeWidth={1.4} className="text-seal-blue/70" aria-hidden="true" />
                </div>
                <div className="px-4 pb-5 pt-4">
                  <h3 className="text-[16px] font-medium text-foreground">{card.title}</h3>
                  <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">{card.text}</p>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
