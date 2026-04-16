"use client";

import Link from "next/link";
import { Sparkles, ArrowRight } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface px-6">
      <div className="mb-10 flex flex-col items-center">
        <Sparkles size={64} className="sparkle-icon mb-6" />
        <h1 className="gemini-gradient text-5xl md:text-7xl font-medium tracking-tight text-center mb-4">
          Gemini
        </h1>
        <p className="text-xl md:text-2xl text-muted-foreground font-medium text-center max-w-2xl leading-relaxed">
          Unlock your potential with the next generation of AI.
        </p>
      </div>

      <Link
        href="/dashboard/new"
        className="group flex items-center gap-3 rounded-full bg-gemini-blue px-8 py-4 text-lg font-medium text-white shadow-lg transition-all hover:opacity-90 active:scale-95"
      >
        <span>Get started</span>
        <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
      </Link>

      <div className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl">
        {[
          { title: "Understand", desc: "Get answers to your most complex questions." },
          { title: "Create", desc: "Generate text, code, and images in seconds." },
          { title: "Analyze", desc: "Process large amounts of data effortlessly." },
        ].map((feat) => (
          <div key={feat.title} className="rounded-3xl border border-border p-8 bg-muted/50">
            <h3 className="text-xl font-bold mb-2">{feat.title}</h3>
            <p className="text-muted-foreground leading-relaxed">{feat.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
