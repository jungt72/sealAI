import { CheckCircle2 } from "lucide-react";

import { trustNeutrality } from "@/lib/marketing/homeContent";

/** "Neutralität und Vertrauen" — dark reduced trust section. */
export function TrustNeutralitySection() {
  return (
    <section
      id={trustNeutrality.id}
      data-header-theme="dark"
      className="section-anchor bg-[#0D1016] text-white"
    >
      <div className="marketing-wide py-20 lg:py-28">
        <div className="marketing-copy">
          <h2 className="text-[clamp(2rem,3.6vw,3rem)] font-normal leading-[1.1] tracking-[-0.03em]">
            {trustNeutrality.headline}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-white/72">{trustNeutrality.text}</p>
        </div>
        <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {trustNeutrality.points.map((point) => (
            <li
              key={point}
              className="flex items-start gap-2.5 rounded-[14px] border border-white/12 bg-white/[0.04] px-4 py-3.5 text-[13.5px] leading-6 text-white/85"
            >
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-white/60" aria-hidden="true" />
              {point}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
