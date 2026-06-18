import { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Beaker,
  BookOpen,
  CheckCircle2,
  Database,
  FileCheck2,
  LockKeyhole,
  MessageSquareText,
  Network,
  ShieldCheck,
} from "lucide-react";
import { TrackedLink } from "@/components/analytics/TrackedLink";
import { AosMiniStack, AosScrollStack } from "@/components/marketing/AosScrollStack";
import { createMetadata } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Dichtungsfall klären, bevor du anfragst",
  description:
    "sealingAI macht aus unvollständigen Dichtungsfällen eine klare Anfragebasis: bekannte Daten, offene Lücken, nächste Frage und neutrale Herstellerübergabe.",
  path: "/",
});

const insightCards = [
  {
    title: "Fall-Cockpit",
    text: "Medium, Temperatur, Bewegung, Einbauraum und Schadensbild werden getrennt erfasst, statt in einer schnellen Werkstoffvermutung zu verschwinden.",
  },
  {
    title: "Lückenlogik",
    text: "sealingAI priorisiert die eine Frage, die den Fall wirklich weiterbringt, bevor Zeit in Nebendetails oder falsche Anfragen fließt.",
  },
  {
    title: "Anfragebasis",
    text: "Bekanntes, Geschätztes und Offenes werden so vorbereitet, dass Hersteller und Spezialisten schneller prüfen können.",
  },
  {
    title: "Sichere Orientierung",
    text: "Technische Einordnung bleibt klar von Freigabe, Produktempfehlung und Herstellerverantwortung getrennt.",
  },
];

const practices = [
  "Instandhaltung",
  "Technischer Einkauf",
  "Engineering",
  "Qualität",
  "Anlagenbau",
];

const stats = [
  ["1", "entscheidende nächste Frage statt zehn unklare Vermutungen"],
  ["0", "verdeckte Produktpräferenz oder heimliche Weitergabe"],
  ["3", "saubere Zustände: bekannt, geschätzt und offen"],
];

const governance = [
  "Keine verdeckte Produktpräferenz",
  "Keine Freigabe ohne Herstellerprüfung",
  "Fallkontext bleibt nachvollziehbar",
  "Übergabe nur nach bewusster Zustimmung",
  "Technische Claims bleiben evidenzgebunden",
];

const loginHref = "/dashboard";
const startCaseHref = "/dashboard";

const sectionLinks = [
  ["Home", "/"],
  ["Produkt", "/werkstoffe"],
  ["Lösungen", "/medien"],
  ["Sicherheit", "/wissen"],
  ["Wissen", "/wissen"],
  ["Kontakt", "/kontakt"],
  ["Login", loginHref],
  ["Fall starten", startCaseHref],
];

export default function LandingPage() {
  return (
    <div className="overflow-x-clip bg-white">
      <section className="relative flex min-h-[430px] items-end justify-center bg-[#d8d9d6] px-5 pb-16 text-center sm:min-h-[560px]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(250,250,247,0.62),rgba(214,215,212,0.9)_48%,rgba(50,54,52,0.55)_100%)]" />
        <div className="absolute left-1/2 top-[36%] h-4 w-48 -translate-x-1/2 rounded-full bg-white/70 blur-[2px]" />
        <div className="relative z-10 mx-auto max-w-2xl">
          <p className="text-[clamp(1.9rem,5vw,3.15rem)] font-medium leading-none text-white drop-shadow-sm">
            Dichtungsfälle klären, bevor du anfragst.
          </p>
          <p className="mt-3 text-[13px] font-medium text-white/82 sm:text-[15px]">
            Neutrale KI für Medien, Werkstoffe, Lücken und Herstellerübergaben
          </p>
          <TrackedLink
            href={startCaseHref}
            analyticsEvent="landing_cta_clicked"
            analyticsPayload={{ cta: "hero_demo", location: "legora_style_hero" }}
            className="mt-6 inline-flex h-11 items-center gap-2 rounded-full bg-[#134e5e] px-6 text-[14px] font-semibold text-white transition-all shadow-[6px_6px_13px_#b8b9be,-6px_-6px_13px_#ffffff] hover:bg-[#19616f] active:shadow-[inset_4px_4px_9px_rgba(0,0,0,0.55),inset_-4px_-4px_9px_rgba(255,255,255,0.14)] active:translate-y-px"
          >
            Dichtungsfall starten <ArrowRight size={15} />
          </TrackedLink>
        </div>
      </section>

      <nav className="border-b border-[#17201f]/10 bg-white" aria-label="Seitenbereiche">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between overflow-x-auto px-4 py-4 text-[11px] font-semibold text-[#17201f]/42 sm:px-8">
          {sectionLinks.map(([label, href]) => (
            <Link key={label} href={href} className="shrink-0 px-3 hover:text-[#004a2f]">
              {label}
            </Link>
          ))}
        </div>
      </nav>

      <section className="bg-white px-5 py-14 text-center sm:px-8">
        <p className="text-[15px] font-semibold text-[#17201f]">Introducing the sealingAI aOS™</p>
        <h1 className="mt-3 text-[clamp(1.55rem,3vw,2.75rem)] font-medium leading-tight text-[#17201f]">
          The agentic operating system for sealing work
        </h1>
      </section>

      <AosScrollStack />

      <section className="mx-auto flex max-w-[1480px] items-end justify-between px-6 py-8 text-[10px] text-[#17201f]/42 sm:px-8">
        <p className="max-w-xs">Ein Schichtenmodell fuer Fallkontext, Medienlogik, Werkstoffgrenzen, Luecken und pruefbare Anfragebasis.</p>
        <Link href="/wissen" className="rounded-full border border-[#17201f]/20 px-3 py-1 font-semibold text-[#17201f]/55">
          sealingAI aOS verstehen
        </Link>
      </section>

      <section className="px-5 py-16 sm:px-8 lg:py-24">
        <div className="mx-auto max-w-[1480px]">
          <div className="mb-8 grid gap-6 sm:grid-cols-[0.55fr_1fr]">
            <h2 className="text-2xl font-semibold text-[#17201f]">Pain points, gelöst</h2>
            <p className="max-w-2xl text-[13px] leading-6 text-[#17201f]/58">
              In der Dichtungstechnik sind die entscheidenden Informationen selten vollstaendig: Medium, Additive, Temperatur, Bewegung, Einbauraum, Reinigung und Schadensbild liegen verstreut. sealingAI macht daraus einen strukturierten technischen Gesprächsstand.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {insightCards.map((card, index) => (
              <article key={card.title} className="group">
                <div className="mb-4 flex aspect-[1.08] items-center justify-center overflow-hidden bg-[#ececea]">
                  {index === 0 ? (
                    <AosMiniStack />
                  ) : (
                    <div className="grid grid-cols-3 gap-3">
                      {Array.from({ length: 9 }).map((_, itemIndex) => (
                        <span
                          key={itemIndex}
                          className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-[#004a2f] shadow-sm"
                        >
                          {itemIndex % 3 === 0 ? <Beaker size={16} /> : itemIndex % 3 === 1 ? <Database size={16} /> : <FileCheck2 size={16} />}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <p className="text-[12px] font-semibold text-[#17201f]">{card.title}</p>
                <p className="mt-2 text-[12px] leading-5 text-[#17201f]/55">{card.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="px-5 py-16 text-center sm:px-8">
        <h2 className="text-[clamp(2rem,4vw,4rem)] font-medium leading-none text-[#17201f]">
          Every team.
          <br />
          Every sealing case.
        </h2>
        <p className="mx-auto mt-4 max-w-lg text-[13px] leading-6 text-[#17201f]/55">
          Ein gemeinsamer Workspace fuer Instandhaltung, Engineering, technischen Einkauf, Qualitaet und Herstellerkommunikation.
        </p>
        <div className="mx-auto mt-10 grid max-w-[1180px] grid-cols-2 gap-4 sm:grid-cols-5">
          {practices.map((practice, index) => (
            <div key={practice} className="text-left">
              <div className="mb-4 aspect-[0.78] overflow-hidden bg-[#e8e4dc]">
                {index === 2 ? (
                  <Image
                    src="/images/marketing/hero-background.png"
                    alt=""
                    width={1672}
                    height={941}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="h-full w-full bg-[linear-gradient(140deg,#d9d7cf,#f8f7f2_48%,#bfc8c5)]" />
                )}
              </div>
              <p className="text-[12px] font-semibold text-[#17201f]">{practice}</p>
              <p className="mt-1 text-[11px] leading-4 text-[#17201f]/48">Strukturierte Dichtungsarbeit fuer reale technische Gespräche.</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative min-h-[460px] overflow-hidden bg-[#17201f] text-white">
        <Image
          src="/images/marketing/hero-background.png"
          alt=""
          fill
          sizes="100vw"
          className="object-cover opacity-62"
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(23,32,31,0.12),rgba(23,32,31,0.88))]" />
        <div className="relative mx-auto flex min-h-[460px] max-w-[1480px] flex-col justify-between px-5 py-10 text-center sm:px-8">
          <p className="mx-auto max-w-xl text-lg font-medium">
            Warum Dichtungsfälle scheitern: nicht wegen zu wenig Daten, sondern wegen unklarer Lücken.
          </p>
          <div className="grid gap-8 text-left lg:grid-cols-[1.1fr_1fr] lg:items-end">
            <p className="max-w-2xl text-[15px] leading-7 text-white/78">
              Eine Dichtungsauswahl scheitert selten an einem fehlenden Werkstoffnamen. Sie scheitert an unklaren Betriebsbedingungen, Medienwechseln, Reinigungschemie, Bewegung, Normbezug oder einer Anfrage, die der Hersteller erst mühsam zurückfragen muss.
            </p>
            <div className="grid gap-6 sm:grid-cols-3 lg:grid-cols-1">
              {stats.map(([value, label]) => (
                <div key={value} className="border-t border-white/25 pt-4">
                  <p className="text-[clamp(2.2rem,5vw,5rem)] font-medium leading-none">{value}</p>
                  <p className="mt-2 text-[12px] leading-5 text-white/62">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid bg-[#e6e3dd] px-5 py-16 sm:px-8 lg:grid-cols-[0.5fr_1fr] lg:py-24">
        <h2 className="text-xl font-semibold text-[#17201f]">Our Vision</h2>
        <div className="mt-8 grid gap-8 lg:mt-0 lg:grid-cols-2">
          <p className="text-[13px] leading-6 text-[#17201f]/65">
            sealingAI soll sich anfühlen wie ein ruhiger technischer Partner: präzise genug für Engineering, zugänglich genug für unvollständige Fälle und konsequent genug, keine falsche Freigabesicherheit zu erzeugen.
          </p>
          <div className="relative aspect-[1.55] overflow-hidden bg-[#f7f4ee]">
            <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(224,219,208,0.68))]" />
            <div className="absolute left-[12%] top-[18%] h-[64%] w-[22%] border-l border-[#17201f]/18" />
            <div className="absolute left-[29%] top-[18%] h-[64%] w-[1px] bg-[#17201f]/12" />
            <div className="absolute right-[12%] top-[18%] h-[64%] w-[42%] rounded-sm bg-white/72 shadow-[0_24px_70px_rgba(23,32,31,0.12)]" />
            <div className="absolute right-[17%] top-[28%] h-[1px] w-[32%] bg-[#17201f]/16" />
            <div className="absolute right-[17%] top-[43%] h-[1px] w-[32%] bg-[#17201f]/12" />
            <div className="absolute bottom-[20%] left-[34%] h-[18%] w-[38%] rounded-full bg-[#c8c1b6]/42 blur-2xl" />
          </div>
        </div>
      </section>

      <section className="bg-[#080d12] px-5 py-16 text-white sm:px-8 lg:py-24">
        <div className="mx-auto max-w-[1480px]">
          <LockKeyhole className="mb-8 text-white/48" size={34} />
          <h2 className="max-w-3xl text-[clamp(1.9rem,4vw,4.7rem)] font-medium leading-[0.98]">
            Herstellerneutral, nachvollziehbar und bewusst vorsichtig, wo Freigaben nicht automatisiert werden dürfen.
          </h2>
          <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {governance.map((item) => (
              <div key={item} className="border-t border-white/15 pt-5">
                <ShieldCheck size={18} className="mb-8 text-white/42" />
                <p className="text-[13px] leading-5 text-white/72">{item}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white px-5 py-16 sm:px-8 lg:py-24">
        <div className="mx-auto flex max-w-[980px] flex-col overflow-hidden border border-[#004a2f] bg-[#004a2f] text-white sm:flex-row">
          <div className="flex flex-1 flex-col justify-between p-8">
            <h2 className="max-w-sm text-2xl font-medium leading-tight">
              Klär deinen nächsten Dichtungsfall in einem geführten Workspace.
            </h2>
            <TrackedLink
              href={startCaseHref}
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "green_demo_card", location: "bottom_card" }}
              className="mt-10 w-fit rounded-full bg-white px-4 py-2 text-[12px] font-semibold text-[#004a2f]"
            >
              Fall starten
            </TrackedLink>
          </div>
          <div className="min-h-[240px] flex-1 bg-white p-8 text-[#17201f]">
            <div className="flex h-full items-center justify-center border border-[#17201f]/15">
              <div className="grid grid-cols-3 gap-4">
                {[MessageSquareText, Network, CheckCircle2, BookOpen, ShieldCheck, FileCheck2].map((Icon, index) => (
                  <Icon key={index} size={34} strokeWidth={1.4} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
