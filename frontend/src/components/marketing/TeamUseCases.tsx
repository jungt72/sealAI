"use client";

import { useRef } from "react";
import type { KeyboardEvent } from "react";
import { ArrowLeft, ArrowRight, ClipboardCheck, Factory, PhoneCall, ShoppingCart, Users, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { teamUseCases } from "@/lib/marketing/homeContent";

const ICONS: Record<string, LucideIcon> = {
  engineering: Users,
  einkauf: ShoppingCart,
  instandhaltung: Wrench,
  hersteller: Factory,
  vertrieb: PhoneCall,
  qualitaet: ClipboardCheck,
};

const CONTAINER = "mx-auto max-w-[1240px] px-5 sm:px-8";

/**
 * "Für jedes Team. Jede Aufgabe." — premium horizontal use-case showcase.
 * Native CSS scroll-snap (no carousel dependency) with arrow buttons and a
 * keyboard-operable scroll region — deliberately simpler than a full roving
 * tabindex grid since cards carry no individually-focusable controls.
 */
export function TeamUseCases() {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  function scrollByCards(direction: 1 | -1) {
    const el = scrollerRef.current;
    if (!el) return;
    const firstCard = el.querySelector<HTMLElement>("[data-carousel-item]");
    const step = firstCard ? firstCard.offsetWidth + 20 : el.clientWidth * 0.8;
    el.scrollBy({ left: direction * step, behavior: "smooth" });
  }

  function onScrollerKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      scrollByCards(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      scrollByCards(-1);
    }
  }

  return (
    <section
      id={teamUseCases.id}
      data-header-theme="light"
      className="section-anchor border-t border-border bg-[#FAFAFB]"
    >
      <div className={`${CONTAINER} py-20 lg:py-28`}>
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-[clamp(2rem,3.4vw,2.9rem)] font-normal leading-[1.08] tracking-[-0.025em] text-foreground">
            {teamUseCases.headlineLines.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </h2>
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground">{teamUseCases.subline}</p>
        </div>

        <div className="mt-10 flex items-center justify-end gap-2">
          <button
            type="button"
            aria-label="Vorherige Karte"
            onClick={() => scrollByCards(-1)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border bg-white text-foreground transition-colors hover:border-seal-blue/40"
          >
            <ArrowLeft size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Nächste Karte"
            onClick={() => scrollByCards(1)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border bg-white text-foreground transition-colors hover:border-seal-blue/40"
          >
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>

        <div
          ref={scrollerRef}
          role="group"
          aria-label="Anwendungsfälle nach Team"
          tabIndex={0}
          onKeyDown={onScrollerKeyDown}
          className="snap-row mt-5 flex gap-5 overflow-x-auto rounded-[18px] pb-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-seal-blue/40"
        >
          {teamUseCases.cards.map((card) => {
            const Icon = ICONS[card.key] ?? Users;
            return (
              <article
                key={card.key}
                data-carousel-item
                className="snap-item w-[260px] shrink-0 rounded-[18px] border border-border bg-white shadow-[0_4px_18px_rgba(15,23,42,0.06)] sm:w-[300px]"
              >
                <div className="flex h-36 items-center justify-center rounded-t-[18px] bg-[linear-gradient(160deg,#F4F5F6_0%,#EBEDEF_100%)]">
                  <Icon size={30} strokeWidth={1.4} className="text-seal-blue/70" aria-hidden="true" />
                </div>
                <div className="px-5 py-5">
                  <h3 className="text-[15px] font-medium text-foreground">{card.title}</h3>
                  <p className="mt-2 text-[13px] leading-6 text-muted-foreground">{card.text}</p>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
