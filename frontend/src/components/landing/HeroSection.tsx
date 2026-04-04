"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";

const TERMINAL_LINES = [
  { text: "> Initializing governed reasoning session...", style: "text-slate-500" },
  { text: "> Gate: GOVERNED [✓]", style: "text-emerald-400" },
  { text: "> Session zone: governed", style: "text-slate-400" },
  { text: "> State: Observed → Normalized → Asserted", style: "text-slate-400" },
  { text: "> RAG query: PTFE Compound Matrix v1.3", style: "text-slate-400" },
  { text: "> Governance class: B [sealed]", style: "text-slate-400" },
  { text: "> RFQ admissibility: PASS", style: "text-emerald-400" },
  { text: "> Response: governed_recommendation [✓]", style: "text-emerald-400" },
];

export default function HeroSection() {
  return (
    <section className="relative mx-auto max-w-6xl px-6 pb-24 pt-36">
      <div className="grid grid-cols-1 gap-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        {/* ── Left: Text block ── */}
        <motion.div
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        >
          <div className="mb-7">
            <Badge
              variant="success"
              className="border-emerald-500/20 bg-emerald-500/10 text-emerald-400 normal-case tracking-normal"
            >
              <span className="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              System Operational · v3.1 Platinum
            </Badge>
          </div>

          <h1 className="font-syne text-5xl font-bold leading-[1.06] tracking-tight text-white xl:text-[3.75rem]">
            Industrial AI
            <br />
            <span className="text-seal-action">Orchestration</span>
          </h1>

          <p className="mt-6 max-w-lg text-base leading-relaxed text-slate-400">
            Autonomous multi-agent supervision for high-pressure sealing
            environments. Monitor reasoning streams, verify material
            compatibility, and ensure ISO compliance in real-time.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <Link href="/dashboard/new">
              <Button variant="primary" size="lg">
                Enter Supervisor Dashboard
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Button
              variant="ghost"
              size="lg"
              disabled
              className="cursor-not-allowed text-slate-600"
            >
              View Documentation
            </Button>
          </div>
        </motion.div>

        {/* ── Right: Terminal widget ── */}
        <motion.div
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.65, ease: "easeOut", delay: 0.15 }}
          className="relative"
        >
          {/* Glow aura */}
          <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-seal-action/[0.07] blur-2xl" />

          <div className="relative overflow-hidden rounded-2xl border border-white/[0.09] bg-[#070d14] shadow-[0_32px_80px_rgba(0,0,0,0.6)]">
            {/* Chrome bar */}
            <div className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-3">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-500/60" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/60" />
              <span className="ml-4 font-mono text-xs text-slate-700">
                sealai-runtime · session #4821
              </span>
            </div>

            {/* Terminal body */}
            <div className="space-y-2 p-6 font-mono text-[13px] leading-relaxed">
              {TERMINAL_LINES.map((line, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.5 + i * 0.2, duration: 0.25 }}
                  className={line.style}
                >
                  {line.text}
                </motion.div>
              ))}

              {/* Blinking cursor */}
              <motion.span
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "steps(1, end)" }}
                className="mt-1 inline-block h-[14px] w-[8px] bg-seal-action align-middle"
              />
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
