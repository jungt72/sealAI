import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldCheck, Factory, Beaker, BookOpen, Settings } from "lucide-react";
import { createMetadata } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Sealing Intelligence — Technische Dichtungsanalyse",
  description: "Der strukturierte Weg von unklaren Dichtungsproblemen zur belastbaren, herstellerfähigen Anfrage. Neutral, fachlich präzise, effizient.",
  path: "/",
});

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* 1. HERO SECTION */}
      <section className="relative overflow-hidden py-24 md:py-32">
        <div className="mx-auto max-w-7xl px-6">
          <div className="max-w-3xl">
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-seal-blue mb-6">
              Sealing Intelligence.
            </h1>
            <p className="text-xl md:text-2xl text-muted-foreground font-medium leading-relaxed mb-10">
              Der strukturierte Weg von unklaren Dichtungsproblemen zur belastbaren, herstellerfähigen Anfrage.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                href="/dashboard/new"
                className="group flex items-center gap-3 rounded-full bg-seal-blue px-8 py-4 text-lg font-bold text-white shadow-xl transition-all hover:opacity-90 active:scale-95"
              >
                Fall analysieren
                <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/medien"
                className="flex items-center gap-2 rounded-full border border-border bg-white px-8 py-4 text-lg font-medium text-foreground transition-all hover:bg-slate-50 active:scale-95"
              >
                Medien prüfen
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 2. REQUEST TYPE ENTRY */}
      <section className="bg-slate-50 py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mb-12">
            <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">Einstieg nach Bedarf</span>
            <h2 className="mt-2 text-3xl font-bold text-foreground">Wie möchten Sie starten?</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              { 
                title: "Neuauslegung", 
                desc: "Technische Vorqualifizierung für neue Designs und Erstausrüstungen.",
                type: "new_design" 
              },
              { 
                title: "Retrofit / Optimierung", 
                desc: "Anpassung bestehender Systeme an geänderte Betriebsbedingungen.",
                type: "retrofit" 
              },
              { 
                title: "Schadensanalyse (RCA)", 
                desc: "Systematische Ursachenforschung bei vorzeitigem Dichtungsausfall.",
                type: "rca" 
              },
            ].map((item) => (
              <Link 
                key={item.type}
                href={`/dashboard/new?request_type=${item.type}`}
                className="group relative flex flex-col justify-between rounded-2xl border border-border bg-white p-8 transition-all hover:border-seal-blue hover:shadow-lg"
              >
                <div>
                  <h3 className="text-xl font-bold text-seal-blue mb-3">{item.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{item.desc}</p>
                </div>
                <div className="mt-8 flex items-center gap-2 text-sm font-bold text-seal-blue opacity-0 transition-opacity group-hover:opacity-100">
                  Workbench öffnen <ArrowRight size={14} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* 3. TRUST BLOCK */}
      <section className="py-20 border-y border-border/50">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            <div className="flex items-start gap-4">
              <ShieldCheck className="text-seal-blue shrink-0" size={32} />
              <div>
                <h4 className="font-bold text-foreground mb-1">Herstellerneutral</h4>
                <p className="text-sm text-muted-foreground">Keine verdeckte Produktbevorzugung. Fokus auf technische Eignung.</p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <Settings className="text-seal-blue shrink-0" size={32} />
              <div>
                <h4 className="font-bold text-foreground mb-1">Engineering-first</h4>
                <p className="text-sm text-muted-foreground">Datengesteuerte Analyse entlang technischer Normen und Beständigkeiten.</p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle2 className="text-seal-blue shrink-0" size={32} />
              <div>
                <h4 className="font-bold text-foreground mb-1">Transparente Freigabe</h4>
                <p className="text-sm text-muted-foreground">Klare Kommunikation der Systemgrenzen. Herstellerfreigabe bleibt letzte Instanz.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. MVP FOKUS & 5. MEDIUM INTELLIGENCE */}
      <section className="py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            <div className="rounded-3xl border border-border p-10 flex flex-col justify-between">
              <div>
                <Factory className="text-seal-blue mb-6" size={40} />
                <h3 className="text-2xl font-bold text-seal-blue mb-4">Gleitringdichtungen für Pumpensysteme</h3>
                <p className="text-muted-foreground leading-relaxed mb-8 text-[17px]">
                  Spezialisierte Vorqualifizierung für GLRD nach p·v-Werten, Werkstoffpaarungen und Medienkontext.
                </p>
              </div>
              <Link href="/wissen/gleitringdichtung-grundlagen" className="text-sm font-bold text-seal-blue flex items-center gap-2 hover:underline">
                Grundlagen verstehen <ArrowRight size={14} />
              </Link>
            </div>
            <div className="rounded-3xl border border-border p-10 flex flex-col justify-between bg-seal-blue text-white">
              <div>
                <Beaker className="text-seal-light-blue mb-6" size={40} />
                <h3 className="text-2xl font-bold mb-4">Medienverträglichkeit verstehen</h3>
                <p className="opacity-80 leading-relaxed mb-8 text-[17px]">
                  Prüfen Sie chemische Beständigkeiten von über 10.000 Medienkombinationen gegenüber Dichtungswerkstoffen.
                </p>
              </div>
              <Link href="/medien" className="text-sm font-bold text-seal-light-blue flex items-center gap-2 hover:underline">
                Mediendatenbank öffnen <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 6. HOW IT WORKS */}
      <section className="bg-slate-50 py-24">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <h2 className="text-3xl font-bold text-foreground mb-16">Der Analyse-Prozess</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { step: "1", label: "Problem beschreiben", desc: "Erfassung der Ausgangssituation via Chat." },
              { step: "2", label: "Parameter klären", desc: "Systematische Bestimmung technischer Daten." },
              { step: "3", label: "Risiken erkennen", desc: "Identifikation kritischer Einsatzgrenzen." },
              { step: "4", label: "Anfrage erzeugen", desc: "Belastbare Basis für Herstelleranfragen." },
            ].map((item) => (
              <div key={item.step} className="flex flex-col items-center">
                <div className="w-12 h-12 rounded-full border-2 border-seal-blue text-seal-blue flex items-center justify-center font-bold text-lg mb-6">
                  {item.step}
                </div>
                <h4 className="font-bold text-foreground mb-2">{item.label}</h4>
                <p className="text-sm text-muted-foreground px-4">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 7. FINAL CTA */}
      <section className="py-32 text-center">
        <div className="mx-auto max-w-3xl px-6">
          <BookOpen className="text-seal-blue mx-auto mb-8" size={48} />
          <h2 className="text-4xl font-bold text-seal-blue mb-8">Starten Sie Ihre Analyse</h2>
          <p className="text-xl text-muted-foreground mb-12">
            Nutzen Sie Sealing Intelligence für Ihre nächste Dichtungsauslegung oder Schadensbewertung.
          </p>
          <Link
            href="/dashboard/new"
            className="inline-flex items-center gap-3 rounded-full bg-seal-blue px-10 py-5 text-xl font-bold text-white shadow-2xl transition-all hover:scale-105 active:scale-95"
          >
            Workbench öffnen
            <ArrowRight size={22} />
          </Link>
        </div>
      </section>
    </div>
  );
}
