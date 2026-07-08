import { BookOpen, Gauge, HeartHandshake, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { highlights } from "@/lib/marketing/homeContent";

const ICONS: Record<string, LucideIcon> = {
  wissenshub: BookOpen,
  materialvergleich: Layers,
  dichtungssituation: Gauge,
  "hersteller-fit": HeartHandshake,
};

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
      <div className="marketing-wide py-20 lg:py-28">
        <div className="marketing-copy">
          <h2 className="text-[clamp(2rem,3.4vw,2.9rem)] font-normal leading-[1.08] tracking-[-0.025em] text-foreground">
            {highlights.headline}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground">{highlights.intro}</p>
        </div>

        <div className="mt-14 highlights-grid">
          {highlights.cards.map((card) => {
            const Icon = ICONS[card.key] ?? BookOpen;
            return (
              <article
                key={card.key}
                className="flex flex-col rounded-[20px] border border-border bg-white p-2 shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-shadow hover:shadow-[0_8px_24px_rgba(15,23,42,0.10)]"
              >
                <div className="flex h-60 items-center justify-center rounded-[16px] bg-[linear-gradient(160deg,#F4F5F6_0%,#EBEDEF_100%)] sm:h-72 lg:h-80">
                  <Icon size={56} strokeWidth={1.2} className="text-seal-blue/70" aria-hidden="true" />
                </div>
                <div className="px-5 pb-6 pt-5">
                  <h3 className="text-[18px] font-medium text-foreground">{card.title}</h3>
                  <p className="mt-2.5 text-[14px] leading-6 text-muted-foreground">{card.text}</p>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
