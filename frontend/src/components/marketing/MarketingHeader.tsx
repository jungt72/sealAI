"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";

import { TrackedLink } from "@/components/analytics/TrackedLink";
import { ANALYZE_HREF } from "@/lib/marketing/homeContent";

const LOGIN_HREF = "/login";

const navLinks: [string, string][] = [
  ["Für Anwender", "/#fuer-anwender"],
  ["Für Hersteller", "/#fuer-hersteller"],
  ["So funktioniert", "/#so-funktioniert"],
  ["Fragen zu sealingAI", "/#website-guide"],
];

export function MarketingHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-[#FAFAF9]/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1240px] items-center justify-between px-5 sm:px-8">
        <Link href="/" aria-label="sealingAI Startseite" className="flex items-center">
          <span className="text-[16px] font-semibold tracking-[0.28em] text-seal-blue">sealingAI</span>
        </Link>

        <nav className="hidden items-center gap-7 lg:flex" aria-label="Hauptnavigation">
          {navLinks.map(([label, href]) => (
            <Link
              key={label}
              href={href}
              className="text-[13.5px] font-medium text-muted-foreground transition-colors hover:text-seal-blue"
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href={LOGIN_HREF}
            className="hidden h-9 items-center rounded-full px-4 text-[13px] font-medium text-muted-foreground transition-colors hover:text-seal-blue sm:inline-flex"
          >
            Login
          </Link>
          <TrackedLink
            href={ANALYZE_HREF}
            analyticsEvent="landing_cta_clicked"
            analyticsPayload={{ cta: "header_analyze", location: "header" }}
            className="inline-flex h-9 items-center gap-1.5 rounded-full bg-seal-blue px-4 text-[13px] font-semibold text-white transition-all hover:bg-seal-blue/92 active:translate-y-px"
          >
            Kostenlos analysieren
            <ArrowRight size={14} />
          </TrackedLink>
          <button
            type="button"
            aria-label={open ? "Menü schließen" : "Menü öffnen"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border text-muted-foreground lg:hidden"
          >
            {open ? <X size={16} /> : <Menu size={16} />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="border-t border-border bg-[#FAFAF9] lg:hidden" aria-label="Mobile Navigation">
          <div className="mx-auto flex max-w-[1240px] flex-col px-5 py-3 sm:px-8">
            {navLinks.map(([label, href]) => (
              <Link
                key={label}
                href={href}
                onClick={() => setOpen(false)}
                className="py-2.5 text-[14px] font-medium text-foreground/80"
              >
                {label}
              </Link>
            ))}
            <Link href={LOGIN_HREF} onClick={() => setOpen(false)} className="py-2.5 text-[14px] font-medium text-foreground/80">
              Login
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}
