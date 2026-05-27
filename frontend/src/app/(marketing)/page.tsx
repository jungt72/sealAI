import { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Beaker,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileText,
  Gauge,
  LockKeyhole,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { createMetadata } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Dichtungsfall klären, bevor du fragst",
  description:
    "sealingAI hilft dir, deine Dichtungssituation zu verstehen, offene Punkte zu erkennen und souverän mit Herstellern zu sprechen.",
  path: "/",
});

const proofPoints = [
  "Herstellerneutral",
  "Keine heimliche Weitergabe",
  "Fallbezogene Rückfragen",
  "Anfragebasis statt Scheinsicherheit",
];

const cockpitItems = [
  { label: "Medium", value: "Heisswasser / Additive", tone: "bg-cyan-100 text-cyan-950" },
  { label: "Temperatur", value: "95 C dauerhaft", tone: "bg-amber-100 text-amber-950" },
  { label: "Bewegung", value: "Dynamisch, Hub 42 mm", tone: "bg-emerald-100 text-emerald-950" },
];

const reasons = [
  {
    icon: ShieldCheck,
    title: "Souveränität",
    desc: "Du gehst informiert ins Hersteller- oder Senior-Gespräch, statt mit einem halben Bauchgefühl zu starten.",
  },
  {
    icon: Clock3,
    title: "Tempo & Klarheit",
    desc: "sealingAI priorisiert die nächste sinnvolle Frage, damit aus vielen Unbekannten ein bearbeitbarer Fall wird.",
  },
  {
    icon: CheckCircle2,
    title: "Neutralität",
    desc: "Technische Orientierung ohne Produktbias, Ranking-Logik oder Verkäuferdruck.",
  },
  {
    icon: ClipboardCheck,
    title: "Übergabefähig",
    desc: "Bekanntes, Geschätztes und Offenes bleiben unterscheidbar, bevor du den Fall weitergibst.",
  },
];

const flows = [
  {
    icon: MessageSquareText,
    title: "Fall beschreiben",
    desc: "Du schreibst in normalen Worten, was du weißt. Unvollständige Angaben sind ausdrücklich okay.",
  },
  {
    icon: Gauge,
    title: "Lücke priorisieren",
    desc: "Die wichtigste offene Information wird sichtbar, bevor du Zeit in Nebendetails verlierst.",
  },
  {
    icon: FileText,
    title: "Anfragebasis erhalten",
    desc: "Der Fall wird so strukturiert, dass Hersteller oder Spezialisten schneller prüfen können.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-col bg-[#f7f8fa] text-[#1b2430]">
      <section className="relative isolate overflow-hidden border-b border-slate-200 bg-[#eef3f7]">
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[linear-gradient(90deg,rgba(15,23,42,0.07)_1px,transparent_1px),linear-gradient(180deg,rgba(15,23,42,0.06)_1px,transparent_1px)] bg-[size:72px_72px]"
        />
        <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-40 bg-white/55" />

        <div className="relative mx-auto grid min-h-[calc(100svh-4rem)] max-w-7xl content-center px-6 py-16 lg:px-8">
          <div className="max-w-4xl">
            <div className="mb-7 inline-flex items-center gap-2 border border-slate-300 bg-white/75 px-3 py-2 text-sm font-semibold text-seal-blue shadow-sm backdrop-blur">
              <Sparkles size={16} />
              Technische Dichtungsfälle schneller klären
            </div>

            <h1 className="flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 text-seal-blue">
              <span className="text-5xl font-semibold uppercase tracking-[0.16em] sm:text-6xl lg:text-[72px]">
                SEALING
              </span>
              <span className="h-12 w-0.5 bg-seal-blue sm:h-14 lg:h-[58px]" aria-hidden="true" />
              <span className="pt-1 text-3xl font-medium tracking-normal sm:text-4xl lg:text-[38px]">
                Intelligence
              </span>
            </h1>
            <p className="mt-7 max-w-2xl text-xl font-medium leading-8 text-slate-700 sm:text-2xl sm:leading-9">
              Beschreibe die Situation. sealingAI macht sichtbar, was bekannt ist, was fehlt und welche Frage als Nächstes zählt.
            </p>

            <div className="mt-10 flex flex-wrap gap-3">
              <Link
                href="/dashboard/new"
                className="inline-flex items-center gap-3 bg-seal-blue px-7 py-4 text-base font-bold text-white shadow-lg shadow-slate-400/30 transition hover:bg-[#082b64] active:scale-[0.98]"
              >
                Dichtungsfall klären
                <ArrowRight size={19} />
              </Link>
              <Link
                href="/werkstoffe"
                className="inline-flex items-center gap-3 border border-slate-300 bg-white/85 px-7 py-4 text-base font-bold text-seal-blue shadow-sm backdrop-blur transition hover:bg-white active:scale-[0.98]"
              >
                Werkstoffe einordnen
                <Beaker size={19} />
              </Link>
            </div>

            <div className="mt-9 flex flex-wrap gap-x-5 gap-y-3 text-sm font-semibold text-slate-700">
              {proofPoints.map((item) => (
                <span key={item} className="inline-flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-700" />
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-12 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="border border-slate-300 bg-white/90 p-5 shadow-xl shadow-slate-400/20 backdrop-blur">
              <div className="mb-4 flex items-center justify-between border-b border-slate-200 pb-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">Fall-Cockpit</p>
                  <h2 className="mt-1 text-xl font-bold text-seal-blue">Pumpendichtung, Anfrage in Vorbereitung</h2>
                </div>
                <span className="bg-amber-100 px-3 py-1 text-xs font-bold text-amber-950">2 Lücken offen</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {cockpitItems.map((item) => (
                  <div key={item.label} className="border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
                    <p className="mt-3 text-sm font-bold text-slate-900">{item.value}</p>
                    <span className={`mt-4 inline-flex px-2 py-1 text-[11px] font-bold ${item.tone}`}>plausibel</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-seal-blue bg-seal-blue p-5 text-white shadow-xl shadow-slate-500/20">
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-seal-light-blue">Nächste Frage</p>
              <h2 className="mt-3 text-2xl font-bold">Liegt Reinigungschemie oder ein Konzentrationswechsel vor?</h2>
              <p className="mt-4 leading-7 text-white/78">
                Diese Information entscheidet stärker über Material- und Freigabeweg als eine vorschnelle NBR/FKM-Auswahl.
              </p>
              <div className="mt-6 flex items-center gap-3 border-t border-white/20 pt-5 text-sm font-semibold text-seal-light-blue">
                <LockKeyhole size={17} />
                Bleibt privat, bis du den Fall freigibst.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white py-20">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="max-w-3xl">
            <p className="text-sm font-bold uppercase tracking-[0.24em] text-seal-blue/65">Warum sealingAI</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
              Weniger Rätselraten. Mehr prüfbare Anfragebasis.
            </h2>
          </div>
          <div className="mt-12 grid gap-px overflow-hidden border border-slate-200 bg-slate-200 md:grid-cols-2 lg:grid-cols-4">
            {reasons.map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="bg-white p-7">
                  <Icon className="text-seal-blue" size={30} />
                  <h3 className="mt-7 text-lg font-bold text-slate-950">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{item.desc}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="border-y border-slate-200 bg-[#f1f5f7] py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.24em] text-seal-blue/65">Ablauf</p>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
              Aus Unsicherheit wird ein technischer Gesprächsstand.
            </h2>
              <p className="mt-5 text-lg leading-8 text-slate-600">
              sealingAI ersetzt keine Freigabe. Es sortiert deinen Fall so, dass die eigentliche Prüfung schneller und sauberer beginnen kann.
            </p>
          </div>
          <div className="grid gap-4">
            {flows.map((item, index) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="grid grid-cols-[56px_1fr] gap-5 border border-slate-300 bg-white p-6">
                  <div className="flex h-14 w-14 items-center justify-center bg-seal-blue text-white">
                    <Icon size={24} />
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Schritt {index + 1}</p>
                    <h3 className="mt-1 text-xl font-bold text-seal-blue">{item.title}</h3>
                    <p className="mt-2 leading-7 text-slate-600">{item.desc}</p>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="bg-white py-20">
        <div className="mx-auto grid max-w-7xl gap-5 px-6 lg:grid-cols-3 lg:px-8">
          <Link href="/dashboard/new" className="group border border-slate-300 bg-white p-8 transition hover:border-seal-blue hover:bg-slate-50">
            <MessageSquareText className="text-seal-blue" size={34} />
            <h3 className="mt-7 text-2xl font-bold text-seal-blue">Dichtungsfall klären</h3>
            <p className="mt-4 leading-7 text-slate-600">
              Starte mit deinem konkreten Problem und erhalte eine priorisierte nächste Frage.
            </p>
            <span className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-seal-blue">
              Fall starten <ArrowRight size={16} className="transition group-hover:translate-x-1" />
            </span>
          </Link>

          <Link href="/werkstoffe" className="group border border-slate-300 bg-seal-blue p-8 text-white transition hover:bg-[#082b64]">
            <Beaker className="text-seal-light-blue" size={34} />
            <h3 className="mt-7 text-2xl font-bold">Materialfrage stellen</h3>
            <p className="mt-4 leading-7 text-white/78">
              Ordne FKM, EPDM, NBR oder PTFE im Kontext von Medium, Temperatur und Anwendung ein.
            </p>
            <span className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-seal-light-blue">
              Werkstoffe ansehen <ArrowRight size={16} className="transition group-hover:translate-x-1" />
            </span>
          </Link>

          <Link href="/wissen" className="group border border-slate-300 bg-white p-8 transition hover:border-seal-blue hover:bg-slate-50">
            <BookOpen className="text-seal-blue" size={34} />
            <h3 className="mt-7 text-2xl font-bold text-seal-blue">SealingPedia</h3>
            <p className="mt-4 leading-7 text-slate-600">
              Fachliche Artikel zu Medien, Schadensbildern und Anfrageparametern.
            </p>
            <span className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-seal-blue">
              Wissen öffnen <ArrowRight size={16} className="transition group-hover:translate-x-1" />
            </span>
          </Link>
        </div>
      </section>

      <section className="bg-seal-blue py-20 text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="max-w-2xl">
            <p className="text-sm font-bold uppercase tracking-[0.24em] text-seal-light-blue">Bereit für den nächsten Fall?</p>
            <h2 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">Klär die entscheidende Lücke, bevor du anfragst.</h2>
          </div>
          <Link
            href="/dashboard/new"
            className="inline-flex w-fit items-center gap-3 bg-white px-8 py-4 text-base font-bold text-seal-blue shadow-lg transition hover:bg-seal-light-blue active:scale-[0.98]"
          >
            Dichtungsfall klären
            <ArrowRight size={19} />
          </Link>
        </div>
      </section>
    </div>
  );
}
