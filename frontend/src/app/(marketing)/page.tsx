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
    <div className="overflow-x-clip bg-[#FAFAF9]">
      <section className="relative flex h-[100svh] min-h-[640px] items-end justify-center overflow-hidden bg-[#111719] px-5 pb-[clamp(2.25rem,7vh,5.25rem)] text-center">
        <Image
          src="/images/marketing/sealing-intelligence-hero.png"
          alt=""
          fill
          priority
          sizes="100vw"
          className="object-cover object-[58%_50%]"
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(6,10,12,0.58)_0%,rgba(6,10,12,0.18)_26%,rgba(6,10,12,0.1)_58%,rgba(6,10,12,0.62)_100%)]" />
        <div className="relative z-10 mx-auto w-full max-w-[1120px]">
          <h1 className="mx-auto max-w-[1080px] text-[clamp(2.2rem,4.85vw,5.35rem)] font-normal leading-[1.04] text-white [text-wrap:balance] drop-shadow-[0_8px_34px_rgba(0,0,0,0.45)]">
            Sealing technologies, without limits.
          </h1>
          <p className="mx-auto mt-5 max-w-[760px] text-[clamp(0.88rem,1.15vw,1.1rem)] font-normal leading-[1.55] text-white/88 [text-wrap:pretty] drop-shadow-[0_4px_20px_rgba(0,0,0,0.35)]">
            Dichtungstechnik verstehen, auslegen und vergleichen — von Werkstoffwahl bis Herstelleranfrage. Schnell, strukturiert und nachvollziehbar.
          </p>
        </div>
      </section>

      <nav className="border-b border-[#17201f]/10 bg-[#FAFAF9]" aria-label="Seitenbereiche">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between overflow-x-auto px-4 py-4 text-[11px] font-semibold text-[#17201f]/42 sm:px-8">
          {sectionLinks.map(([label, href]) => (
            <Link key={label} href={href} className="shrink-0 px-3 hover:text-[#002A5B]">
              {label}
            </Link>
          ))}
        </div>
      </nav>

      <section className="bg-[#FAFAF9] px-5 pb-20 pt-32 text-center sm:px-8 sm:pb-24 sm:pt-40 lg:pb-28 lg:pt-48">
        <p className="text-[14px] font-semibold text-[#17201f]/86">Introducing the sealingAI aOS™</p>
        <h1 className="mx-auto mt-5 max-w-[1040px] text-[clamp(2rem,3.45vw,3.75rem)] font-medium leading-[1.05] text-[#17201f] [text-wrap:balance]">
          Das Sealing Intelligence System für die Dichtungstechnik
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
                          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#FAFAF9] text-[#002A5B] shadow-sm"
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
            <div className="absolute right-[12%] top-[18%] h-[64%] w-[42%] rounded-sm bg-[#FAFAF9]/72 shadow-[0_24px_70px_rgba(23,32,31,0.12)]" />
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

      <section className="bg-[#FAFAF9] px-5 py-16 sm:px-8 lg:py-24">
        <div className="mx-auto flex max-w-[980px] flex-col overflow-hidden border border-[#002A5B] bg-[#002A5B] text-white sm:flex-row">
          <div className="flex flex-1 flex-col justify-between p-8">
            <h2 className="max-w-sm text-2xl font-medium leading-tight">
              Klär deinen nächsten Dichtungsfall in einem geführten Workspace.
            </h2>
            <TrackedLink
              href={startCaseHref}
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "navy_demo_card", location: "bottom_card" }}
              className="mt-10 w-fit rounded-full bg-[#FAFAF9] px-4 py-2 text-[12px] font-semibold text-[#002A5B]"
            >
              Fall starten
            </TrackedLink>
          </div>
          <div className="min-h-[240px] flex-1 bg-[#FAFAF9] p-8 text-[#17201f]">
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
