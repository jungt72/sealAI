"use client";

import { motion, type Variants } from "framer-motion";
import { Zap, ShieldCheck, Activity } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type Feature = {
  icon: LucideIcon;
  iconColor: string;
  iconBg: string;
  title: string;
  description: string;
};

const features: Feature[] = [
  {
    icon: Zap,
    iconColor: "text-seal-action",
    iconBg: "bg-seal-action/10",
    title: "Real-Time Reasoning",
    description:
      "Observe agent thought processes as they execute standard operating procedures.",
  },
  {
    icon: ShieldCheck,
    iconColor: "text-emerald-400",
    iconBg: "bg-emerald-400/10",
    title: "Safety Guardrails",
    description:
      "Automated verification of hydrogen compatibility and pressure limits.",
  },
  {
    icon: Activity,
    iconColor: "text-amber-400",
    iconBg: "bg-amber-400/10",
    title: "Live Telemetry",
    description:
      "Connect to industrial sensors via MCP protocol for live data ingestion.",
  },
];

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.13, duration: 0.48, ease: "easeOut" },
  }),
};

export default function FeatureCards() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-6 pb-28">
      {/* Section label */}
      <div className="mb-10 border-l-2 border-seal-action pl-4">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-seal-action">
          Platform Capabilities
        </p>
        <h2 className="mt-1 font-syne text-3xl font-bold text-white">
          Engineered for precision
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {features.map((feature, i) => {
          const Icon = feature.icon;
          return (
            <motion.div
              key={feature.title}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-60px" }}
              variants={cardVariants}
              className="group relative overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.025] p-7 backdrop-blur-sm transition-all duration-300 hover:border-seal-action/25 hover:bg-white/[0.05] hover:shadow-[0_0_48px_rgba(0,122,255,0.07)]"
            >
              {/* Icon */}
              <div
                className={`mb-5 inline-flex h-11 w-11 items-center justify-center rounded-xl ${feature.iconBg} ${feature.iconColor}`}
              >
                <Icon className="h-5 w-5" />
              </div>

              {/* Text */}
              <h3 className="font-syne text-base font-semibold text-white">
                {feature.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                {feature.description}
              </p>

              {/* Bottom accent line — slides in on hover */}
              <div className="absolute bottom-0 left-0 h-px w-0 bg-seal-action transition-all duration-500 group-hover:w-full" />
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
