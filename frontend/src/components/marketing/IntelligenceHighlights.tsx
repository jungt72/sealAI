import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { highlights } from "@/lib/marketing/homeContent";

function KnowledgeImage() {
  return (
    <div className="relative h-full overflow-hidden bg-[linear-gradient(180deg,#efefef_0%,#f7f7f7_100%)]">
      <div className="absolute inset-x-0 top-0 h-1/2 bg-[linear-gradient(180deg,rgba(214,214,214,0.95),rgba(246,246,246,0))]" />
      <div className="absolute left-1/2 top-[46%] h-[34%] w-[58%] -translate-x-1/2 -translate-y-1/2 [transform-style:preserve-3d]">
        {Array.from({ length: 5 }).map((_, index) => (
          <div
            key={index}
            className="absolute inset-x-0 h-[46%] rounded-[10px] border border-white/80 bg-[#FAFAF9]/42 shadow-[0_12px_28px_rgba(15,23,42,0.08)]"
            style={{ bottom: `${index * 10}%`, transform: "skewX(-18deg)" }}
          />
        ))}
        <div className="absolute left-1/2 top-[28%] grid h-[42%] w-[66%] -translate-x-1/2 grid-cols-3 gap-2 opacity-80 [transform:skewX(-18deg)]">
          {Array.from({ length: 9 }).map((_, index) => (
            <span key={index} className="rounded-[5px] bg-[#FAFAF9]/72 shadow-inner" />
          ))}
        </div>
        <span className="absolute left-1/2 top-[37%] -translate-x-1/2 text-[22px] font-semibold tracking-[0.08em] text-white drop-shadow-[0_2px_10px_rgba(0,0,0,0.16)]">
          SEAL
        </span>
      </div>
    </div>
  );
}

function MaterialImage() {
  return (
    <div className="relative h-full overflow-hidden bg-[radial-gradient(circle_at_35%_72%,rgba(55,128,230,0.38),transparent_28%),linear-gradient(180deg,#f0f0f0_0%,#fafafa_100%)]">
      <div className="absolute left-1/2 top-1/2 grid h-24 w-24 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[22px] border border-black/8 bg-[#FAFAF9]/70 shadow-[0_18px_60px_rgba(15,23,42,0.12)] backdrop-blur-md">
        <span className="text-[54px] leading-none text-[#151515]">+</span>
      </div>
      <span className="absolute left-[8%] top-[36%] grid h-10 w-10 place-items-center rounded-full bg-[#36a3ff] text-[20px] text-white shadow-[0_14px_34px_rgba(54,163,255,0.32)]">I</span>
      <span className="absolute right-[15%] top-[24%] grid h-9 w-9 place-items-center rounded-[9px] bg-[linear-gradient(135deg,#39a2ff,#4b5ee8)] text-[13px] font-bold text-white shadow-[0_14px_30px_rgba(47,100,221,0.26)]">W</span>
      <span className="absolute left-[20%] bottom-[24%] grid h-9 w-9 place-items-center rounded-[9px] bg-[linear-gradient(135deg,#48d699,#1c8fd4)] text-[13px] font-bold text-white shadow-[0_14px_30px_rgba(39,160,144,0.22)]">X</span>
      <span className="absolute right-[18%] bottom-[24%] grid h-10 w-10 place-items-center rounded-full bg-[linear-gradient(135deg,#ef3d6a,#f7a63b)] text-[13px] font-bold text-white shadow-[0_14px_32px_rgba(229,77,92,0.24)]">P</span>
      <span className="absolute left-[43%] top-[24%] grid h-10 w-10 place-items-center rounded-full bg-[#ffda2f] text-[16px] text-black shadow-[0_14px_34px_rgba(230,188,0,0.22)]">OK</span>
      <span className="absolute right-[8%] top-[46%] grid h-12 w-12 place-items-center rounded-full bg-[#21a8ff]/80 text-[24px] shadow-[0_14px_34px_rgba(33,168,255,0.22)]">G</span>
      <span className="absolute left-[54%] bottom-[19%] h-8 w-8 rounded-[8px] bg-[#c79a55]/70 blur-[1px]" />
    </div>
  );
}

function SituationImage() {
  const rows = ["RWDR", "FKM", "PTFE", "EPDM"];

  return (
    <div className="relative h-full overflow-hidden bg-[linear-gradient(90deg,#d9d9d9_0%,#f8f8f8_36%,#eeeeee_100%)]">
      <div className="absolute inset-y-0 right-0 w-[42%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.72))]" />
      <div className="absolute left-[12%] top-[10%] w-[72%] border border-white/70 bg-[#FAFAF9]/58 p-4 shadow-[0_22px_60px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-[11px] font-medium text-[#1f1f1f]">Monitor Setup</p>
        <h3 className="mt-6 text-[19px] font-semibold text-[#171717]">Dichtungstypen</h3>
        <div className="mt-4 space-y-2">
          {rows.map((row, index) => (
            <div key={row} className="flex items-center gap-3 bg-[#FAFAF9]/62 px-3 py-2 text-[13px] font-medium text-[#2b2b2b]">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-[#f5f5f7] text-[10px]">{index + 1}</span>
              <span>{row}</span>
            </div>
          ))}
        </div>
        <h4 className="mt-7 text-[15px] font-semibold text-[#202020]">Parameter</h4>
        <div className="mt-3 space-y-2">
          {["Medium & Temperatur", "Druck & Bewegung", "Werkstoffprofil"].map((row) => (
            <div key={row} className="bg-[#FAFAF9]/62 px-3 py-2 text-[12px] font-medium text-[#505050]">
              {row}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FitImage() {
  const states = ["!", "o", "-", "ok", "ok", "x", "ok", "ok"];

  return (
    <div className="relative h-full overflow-hidden bg-[linear-gradient(90deg,#d8d8d8_0%,#f8f8f8_34%,#eeeeee_100%)]">
      <div className="absolute inset-y-0 right-0 w-[45%] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,0.76))]" />
      <div className="absolute left-[10%] top-[10%] w-[82%] border border-white/70 bg-[#FAFAF9]/58 p-4 shadow-[0_22px_60px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <div className="flex items-center gap-2 text-[11px] font-medium text-[#252525]">
          <span className="grid h-4 w-4 place-items-center rounded-full bg-[#ffd327] text-[10px]">ok</span>
          Hersteller-Fit
        </div>
        <button className="mt-5 bg-[#FAFAF9] px-3 py-1.5 text-[11px] font-medium text-[#202020] shadow-sm">Anfrage prüfen</button>
        <div className="mt-5 space-y-1.5 text-[11px] text-[#4a4a4a]">
          {states.map((state, index) => (
            <div key={index} className="grid grid-cols-[22px_64px_1fr] items-center gap-2 bg-[#FAFAF9]/44 px-2 py-1.5">
              <span className={state === "ok" ? "text-[#32b45d]" : state === "!" ? "text-[#ff3b30]" : "text-[#7d8790]"}>{state}</span>
              <span className="text-[#8b8b8b]">SAI-{String(index + 41).padStart(3, "0")}</span>
              <span className="truncate font-medium text-[#363636]">Kompetenzprofil und Rückfragen abstimmen</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function HighlightImage({ itemKey }: { itemKey: string }) {
  if (itemKey === "materialvergleich") return <MaterialImage />;
  if (itemKey === "dichtungssituation") return <SituationImage />;
  if (itemKey === "hersteller-fit") return <FitImage />;
  return <KnowledgeImage />;
}

/** Reference-style highlight grid with original dummy product/UX imagery. */
export function IntelligenceHighlights() {
  return (
    <section id={highlights.id} data-header-theme="light" className="section-anchor bg-[#FAFAF9]">
      <div className="marketing-section py-16 lg:py-24">
        <div className="max-w-[720px]">
          <h2 className="text-[clamp(2.2rem,3.8vw,3.5rem)] font-normal leading-[1.04] tracking-[-0.03em] text-foreground">
            {highlights.headline}
          </h2>
          <p className="mt-5 max-w-[620px] text-[15px] leading-7 text-muted-foreground">{highlights.intro}</p>
        </div>

        <div className="mt-14 grid gap-x-7 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
          {highlights.cards.map((card) => (
            <article key={card.key} className="min-w-0">
              <div className="aspect-[4/5] w-full bg-[#f1f1f1]">
                <HighlightImage itemKey={card.key} />
              </div>
              <h3 className="mt-5 text-[18px] font-medium leading-6 text-foreground">{card.title}</h3>
              <p className="mt-5 text-[15px] leading-6 text-muted-foreground">{card.text}</p>
              <Link
                href="/#intelligence"
                className="mt-6 inline-flex items-center gap-1 text-[14px] leading-6 text-muted-foreground transition-colors hover:text-foreground"
              >
                Mehr erfahren
                <ArrowUpRight size={15} aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
