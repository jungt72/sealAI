import { BookOpen, Database, FileCheck2, Gauge, MessageCircleQuestion, Factory, FlaskConical, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { HeroPrecheckCard } from "@/components/marketing/HeroPrecheckCard";
import { sealingIntelligence } from "@/lib/marketing/homeContent";

const ICONS: Record<string, LucideIcon> = {
  fachwissen: BookOpen,
  materialdaten: FlaskConical,
  anwendungsdaten: Database,
  situation: Gauge,
  bewertung: MessageCircleQuestion,
  herstellerkompetenz: Factory,
  dokumentation: FileCheck2,
  sicherheit: ShieldCheck,
};

const CONTAINER = "mx-auto max-w-[1240px] px-5 sm:px-8";

/**
 * "Introducing Sealing Intelligence" — platform/system explainer. The
 * interactive `HeroPrecheckCard` (deterministic, no LLM, no recommendation)
 * lives here as a live demonstration of the "Dichtungssituation" module,
 * relocated out of the hero per the no-RFQ-in-hero positioning rule.
 */
export function SealingIntelligenceSection() {
  return (
    <section
      id={sealingIntelligence.id}
      data-header-theme="light"
      className="section-anchor border-t border-border bg-background"
    >
      <div className={`${CONTAINER} py-20 lg:py-28`}>
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-[clamp(2rem,3.4vw,2.9rem)] font-normal leading-[1.08] tracking-[-0.025em] text-foreground">
            {sealingIntelligence.headline}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground">{sealingIntelligence.subline}</p>
        </div>

        <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {sealingIntelligence.modules.map((module) => {
            const Icon = ICONS[module.key] ?? BookOpen;
            return (
              <div key={module.key} className="rounded-[14px] border border-border bg-[#FAFAFB] p-5">
                <Icon size={20} strokeWidth={1.6} className="text-seal-blue/70" aria-hidden="true" />
                <h3 className="mt-3 text-[14px] font-medium text-foreground">{module.title}</h3>
                <p className="mt-1.5 text-[13px] leading-5 text-muted-foreground">{module.text}</p>
              </div>
            );
          })}
        </div>

        <div className="mt-16 rounded-[24px] border border-border bg-[#FAFAFB] p-6 sm:p-10">
          <div className="mx-auto max-w-xl text-center">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-seal-blue">
              {sealingIntelligence.demo.eyebrow}
            </p>
            <h3 className="mt-2 text-[22px] font-medium text-foreground">{sealingIntelligence.demo.headline}</h3>
            <p className="mt-2 text-[14px] leading-6 text-muted-foreground">{sealingIntelligence.demo.subline}</p>
          </div>
          <div className="mx-auto mt-8 max-w-md">
            <HeroPrecheckCard />
          </div>
        </div>
      </div>
    </section>
  );
}
