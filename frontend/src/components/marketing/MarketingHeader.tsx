"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";

import { PARTNER_HREF, REGISTER_HREF } from "@/lib/marketing/homeContent";

const LOGIN_HREF = "/login";

/** Must match the header's rendered height (h-[76px] below) and the
 * `.section-anchor { scroll-margin-top }` value in globals.css. */
const HEADER_HEIGHT = 76;

type HeaderState = "hero" | "solid-light" | "solid-dark";

const LEFT_NAV: [string, string][] = [
  ["Plattform", "/#intelligence"],
  ["Wissen", "/wissen"],
  ["Sicherheit", "/#neutralitaet"],
];

const RIGHT_NAV: [string, string][] = [["Hersteller", PARTNER_HREF]];

const DRAWER_LINKS: [string, string][] = [
  ["Plattform", "/#intelligence"],
  ["Wissen", "/wissen"],
  ["Hersteller", PARTNER_HREF],
  ["Sicherheit", "/#neutralitaet"],
];

export function MarketingHeader() {
  // SSR / no-JS-safe default: a legible light-glass header, never a fully
  // transparent header sitting directly on a white page. JS flips this to
  // "hero" within one frame of mount when the hero section is on screen.
  const [state, setState] = useState<HeaderState>("solid-light");
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  // Scroll-aware header theme: whichever `[data-header-theme]` section
  // currently sits directly under the fixed header decides the header's
  // visual state. Uses IntersectionObserver (not a scrollY threshold) with a
  // rootMargin collapsed to the header height, so the "detection line" always
  // matches where the header actually sits — no flicker at section borders.
  useEffect(() => {
    const active = new Map<Element, { theme: string; top: number }>();
    let observer: IntersectionObserver | null = null;

    function resolve() {
      let best: { theme: string; top: number } | null = null;
      for (const entry of active.values()) {
        if (!best || entry.top < best.top) best = entry;
      }
      if (best) {
        setState(best.theme === "hero" ? "hero" : best.theme === "dark" ? "solid-dark" : "solid-light");
      }
    }

    function setup() {
      observer?.disconnect();
      active.clear();
      const bottomMargin = -(window.innerHeight - HEADER_HEIGHT);
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const theme = (entry.target as HTMLElement).dataset.headerTheme ?? "light";
            if (entry.isIntersecting) {
              active.set(entry.target, { theme, top: entry.boundingClientRect.top });
            } else {
              active.delete(entry.target);
            }
          }
          resolve();
        },
        { root: null, rootMargin: `0px 0px ${bottomMargin}px 0px`, threshold: 0 },
      );
      document.querySelectorAll<HTMLElement>("[data-header-theme]").forEach((el) => observer!.observe(el));
    }

    setup();
    window.addEventListener("resize", setup);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", setup);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    closeButtonRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <header data-state={state} className="marketing-header fixed inset-x-0 top-0 z-50">
      <div className="marketing-wide relative flex h-[76px] items-center justify-between">
        <nav className="hidden items-center gap-8 lg:flex" aria-label="Hauptnavigation">
          {LEFT_NAV.map(([label, href]) => (
            <Link
              key={label}
              href={href}
              className="text-[13.5px] font-medium text-current/75 transition-colors hover:text-current"
            >
              {label}
            </Link>
          ))}
        </nav>

        <Link
          href="/"
          aria-label="sealingAI Startseite"
          className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[19px] font-medium tracking-[0.14em] text-current"
        >
          sealingAI
        </Link>

        <div className="flex items-center gap-3">
          <nav className="hidden items-center gap-8 lg:flex" aria-label="Herstellernavigation">
            {RIGHT_NAV.map(([label, href]) => (
              <Link
                key={label}
                href={href}
                className="text-[13.5px] font-medium text-current/75 transition-colors hover:text-current"
              >
                {label}
              </Link>
            ))}
          </nav>
          <Link
            href={LOGIN_HREF}
            className="hidden text-[13px] font-medium text-current/75 transition-colors hover:text-current lg:inline-flex"
          >
            Login
          </Link>
          <Link
            href={REGISTER_HREF}
            className="hidden h-9 items-center rounded-full border border-current/35 px-4 text-[13px] font-medium text-current transition-colors hover:bg-current/8 hover:border-current/55 lg:inline-flex"
          >
            Registrieren
          </Link>
          <button
            ref={menuButtonRef}
            type="button"
            aria-label={open ? "Menü schließen" : "Menü öffnen"}
            aria-expanded={open}
            aria-controls="marketing-mobile-drawer"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-current/25 text-current lg:hidden"
          >
            {open ? <X size={16} /> : <Menu size={16} />}
          </button>
        </div>
      </div>

      {open && (
        <div id="marketing-mobile-drawer" role="dialog" aria-modal="true" aria-label="Mobile Navigation" className="lg:hidden">
          <button
            type="button"
            aria-label="Menü schließen"
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => setOpen(false)}
          />
          <div className="fixed inset-x-0 top-[76px] z-40 border-t border-border bg-[#FAFAF9] shadow-xl">
            <div className="marketing-wide flex items-center justify-between py-3">
              <span className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">Menü</span>
              <button
                ref={closeButtonRef}
                type="button"
                aria-label="Menü schließen"
                onClick={() => setOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border text-foreground"
              >
                <X size={15} />
              </button>
            </div>
            <nav className="marketing-wide flex flex-col pb-4" aria-label="Mobile Navigation">
              {DRAWER_LINKS.map(([label, href]) => (
                <Link
                  key={label}
                  href={href}
                  onClick={() => setOpen(false)}
                  className="py-2.5 text-[14px] font-medium text-foreground/85"
                >
                  {label}
                </Link>
              ))}
              <div className="mt-2 flex flex-col gap-2 border-t border-border pt-3">
                <Link
                  href={LOGIN_HREF}
                  onClick={() => setOpen(false)}
                  className="py-2 text-[14px] font-medium text-foreground/85"
                >
                  Login
                </Link>
                <Link
                  href={REGISTER_HREF}
                  onClick={() => setOpen(false)}
                  className="inline-flex h-11 items-center justify-center rounded-full border border-seal-blue/30 text-[14px] font-semibold text-seal-blue"
                >
                  Registrieren
                </Link>
              </div>
            </nav>
          </div>
        </div>
      )}
    </header>
  );
}
