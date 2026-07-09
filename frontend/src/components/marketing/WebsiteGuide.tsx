"use client";

/**
 * Website Guide — a static, deterministic FAQ/prompt-chip guide (NO LLM).
 * Answers only questions ABOUT sealingAI; deflects concrete technical sealing
 * questions to the free analysis via a fixed guardrail.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, MessageSquareText, Search } from "lucide-react";

import { resolveGuideAnswer, type GuideResolution } from "@/lib/marketing/guideClassifier";
import { ANALYZE_HREF, PARTNER_HREF, faqItems, guide } from "@/lib/marketing/homeContent";

type Chip = { label: string } & ({ kind: "faq"; query: string } | { kind: "link"; href: string });

const CHIPS: Chip[] = [
  { label: "Warum sealingAI nutzen?", kind: "faq", query: "Warum sollte ich sealingAI nutzen?" },
  { label: "Kostenlos starten", kind: "link", href: ANALYZE_HREF },
  { label: "Herstellerpartner werden", kind: "link", href: PARTNER_HREF },
  { label: "Ist sealingAI neutral?", kind: "faq", query: "Ist sealingAI neutral?" },
  { label: "Unterschied zu Katalogen", kind: "faq", query: "Was ist der Unterschied zu Katalogen?" },
  { label: "Was passiert nach dem Login?", kind: "faq", query: "Was passiert nach dem Login?" },
];

export function WebsiteGuide() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [resolution, setResolution] = useState<GuideResolution | null>(null);

  function ask(q: string) {
    if (!q.trim()) return;
    setResolution(resolveGuideAnswer(q, faqItems, guide.guardrail));
  }

  return (
    <div className="mx-auto max-w-[860px]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(query);
        }}
        className="flex items-center gap-2 rounded-full border border-border bg-[#FAFAF9] px-4 py-2"
        role="search"
        aria-label="Website-Guide"
      >
        <Search size={16} className="shrink-0 text-muted-foreground" aria-hidden />
        <label htmlFor="guide-input" className="sr-only">
          Frage zu sealingAI
        </label>
        <input
          id="guide-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={guide.placeholder}
          className="h-9 w-full bg-transparent text-[14px] text-foreground outline-none placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-seal-blue px-4 text-[13px] font-semibold text-white transition hover:bg-seal-blue/92"
        >
          Fragen
        </button>
      </form>

      <ul className="mt-4 flex flex-wrap justify-center gap-2">
        {CHIPS.map((chip) => (
          <li key={chip.label}>
            <button
              type="button"
              onClick={() => (chip.kind === "faq" ? ask(chip.query) : router.push(chip.href))}
              className="rounded-full border border-border bg-[#FAFAF9] px-3.5 py-1.5 text-[12px] font-medium text-muted-foreground transition hover:border-seal-blue/40 hover:text-seal-blue"
            >
              {chip.label}
            </button>
          </li>
        ))}
      </ul>

      {resolution && (
        <div className="mt-5 rounded-xl border border-border bg-[#FAFAF9] p-5" aria-live="polite">
          <div className="flex items-center gap-2 text-seal-blue">
            <MessageSquareText size={16} aria-hidden />
            <span className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
              Website-Guide
            </span>
          </div>
          <p className="mt-2 text-[14px] leading-7 text-foreground">{resolution.answer}</p>
          {resolution.isGuardrail && (
            <a
              href={ANALYZE_HREF}
              className="mt-4 inline-flex h-10 items-center gap-2 rounded-full bg-seal-accent px-5 text-[13px] font-semibold text-white transition hover:brightness-105"
            >
              Kostenlos analysieren
              <ArrowRight size={15} />
            </a>
          )}
        </div>
      )}

      <p className="mt-4 text-center text-[12px] leading-6 text-muted-foreground">{guide.clarifier}</p>
    </div>
  );
}
