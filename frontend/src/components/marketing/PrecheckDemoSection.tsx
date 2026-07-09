import { HeroPrecheckCard } from "@/components/marketing/HeroPrecheckCard";
import { sealingIntelligence } from "@/lib/marketing/homeContent";

/** Final live demo section for the deterministic Dichtungssituation precheck. */
export function PrecheckDemoSection() {
  return (
    <section id="precheck-demo" data-header-theme="light" className="section-anchor bg-[#f5f5f7]">
      <div className="marketing-section py-20 lg:py-28">
        <div className="marketing-copy-center text-center">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-seal-blue">
            {sealingIntelligence.demo.eyebrow}
          </p>
          <h2 className="mt-2 text-[clamp(1.75rem,3vw,2.5rem)] font-normal leading-[1.08] tracking-[-0.025em] text-foreground">
            {sealingIntelligence.demo.headline}
          </h2>
          <p className="mt-3 text-[14px] leading-6 text-muted-foreground">{sealingIntelligence.demo.subline}</p>
        </div>
        <div className="mx-auto mt-10 max-w-md">
          <HeroPrecheckCard />
        </div>
      </div>
    </section>
  );
}
