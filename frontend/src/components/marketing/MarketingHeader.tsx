"use client";

import Link from "next/link";
import { ArrowRight, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { TrackedLink } from "@/components/analytics/TrackedLink";

const loginHref = "/dashboard";

const navLinks = [
  ["Produkt", "/werkstoffe"],
  ["Lösungen", "/medien"],
  ["Wissen", "/wissen"],
  ["Cockpit", loginHref],
  ["Anfrage", "/anfrage/dichtung-auslegen-lassen"],
];

export function MarketingHeader() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 24);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  const navText = scrolled ? "text-[#536879] hover:text-[#2f4559]" : "text-white/88 hover:text-white";

  return (
    <header
      className={`fixed top-0 z-50 w-full transition-all duration-300 ${
        scrolled
          ? "border-b border-[#536879]/12 bg-[#FAFAF9]/76 text-[#536879] shadow-[0_14px_40px_rgba(17,32,45,0.08)] backdrop-blur-xl"
          : "border-b border-transparent bg-transparent text-white"
      }`}
    >
      <div className="relative mx-auto flex h-16 max-w-[1480px] items-center px-4 sm:px-6">
        <div className="flex flex-1 items-center">
          <nav className="hidden items-center gap-6 lg:flex" aria-label="Hauptnavigation">
            {navLinks.map(([label, href]) => (
              <Link
                key={label}
                href={href}
                className={`text-[14px] font-normal transition-colors ${navText}`}
              >
                {label}
              </Link>
            ))}
          </nav>
          <button
            type="button"
            aria-label="Menü öffnen"
            className={`inline-flex h-8 w-8 items-center justify-center rounded-full border transition-colors lg:hidden ${
              scrolled ? "border-[#536879]/22 text-[#536879]" : "border-white/25 text-white"
            }`}
          >
            <Menu size={16} />
          </button>
        </div>

        <Link
          href="/"
          aria-label="sealingAI Startseite"
          className="absolute left-1/2 flex h-9 -translate-x-1/2 items-center justify-center"
        >
          <span
            className={`text-[15px] font-semibold tracking-[0.34em] transition-colors duration-300 sm:text-[16px] ${
              scrolled ? "text-[#2f4559]" : "text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.28)]"
            }`}
          >
            sealingAI
          </span>
        </Link>

        <div className="flex flex-1 items-center justify-end">
          <TrackedLink
            href={loginHref}
            analyticsEvent="landing_cta_clicked"
            analyticsPayload={{ cta: "header_login", location: "header" }}
            className={`inline-flex h-9 items-center gap-1.5 rounded-full px-5 text-[13px] font-semibold transition-all active:translate-y-px ${
              scrolled
                ? "border border-[#536879]/18 bg-white/62 text-[#2f4559] shadow-[0_8px_22px_rgba(17,32,45,0.08)] hover:bg-white/82"
                : "border border-white/25 bg-white/14 text-white backdrop-blur-md hover:bg-white/22"
            }`}
          >
            Login
            <ArrowRight size={14} />
          </TrackedLink>
        </div>
      </div>
    </header>
  );
}
