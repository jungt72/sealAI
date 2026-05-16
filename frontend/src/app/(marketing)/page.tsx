import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldCheck, Factory, Beaker, BookOpen, Settings, Clock3, GraduationCap, FolderClock } from "lucide-react";
import { HeroMotionBackground } from "@/components/marketing/HeroMotionBackground";
import { createMetadata } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Dichtungsfall klären, bevor du fragst",
  description: "sealingAI hilft dir, deine Dichtungssituation zu verstehen, offene Punkte zu erkennen und souverän mit Herstellern zu sprechen.",
  path: "/",
});

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* 1. HERO SECTION */}
      <section className="relative -mt-16 min-h-[82svh] overflow-hidden pb-20 pt-36 md:min-h-[76svh] md:pb-24 md:pt-44">
        <HeroMotionBackground />
        <div className="relative mx-auto max-w-7xl px-6">
          <div className="max-w-3xl">
            <h1 className="mb-6 max-w-2xl text-4xl font-bold text-seal-blue sm:text-5xl md:text-6xl">
              SEALING | Intelligence
            </h1>
            <p className="mb-10 max-w-2xl text-xl font-medium leading-relaxed text-slate-700 md:text-2xl">
              sealingAI hilft dir, deine Dichtungssituation zu verstehen, offene Punkte zu erkennen und souverän mit Herstellern zu sprechen.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link
                href="/dashboard/new"
                className="group flex items-center gap-3 rounded-full bg-seal-blue px-8 py-4 text-lg font-bold text-white shadow-xl transition-all hover:opacity-90 active:scale-95"
              >
                Dichtungsfall klären
                <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 2. USP BLOCK */}
      <section className="bg-slate-50 py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mb-12">
            <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">Warum sealingAI</span>
            <h2 className="mt-2 text-3xl font-bold text-foreground">Schneller zum Punkt, ohne Scheinsicherheit.</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
            {[
              {
                icon: ShieldCheck,
                title: "Souveränität",
                desc: "Geh informiert ins Hersteller- oder Senior-Gespräch, nicht ahnungslos.",
              },
              {
                icon: Clock3,
                title: "Tempo & Klarheit",
                desc: "Erkenne den nächsten sinnvollen Schritt und die wichtigste offene Lücke.",
              },
              {
                icon: CheckCircle2,
                title: "Neutralität",
                desc: "Technische Orientierung ohne Produktbias, Ranking-Logik oder Verkäuferdruck.",
              },
              {
                icon: GraduationCap,
                title: "Lerneffekt",
                desc: "Du verstehst, warum Angaben wichtig sind, und wirst mit jedem Fall besser.",
              },
              {
                icon: FolderClock,
                title: "Persistenz",
                desc: "Dein Fall bleibt erhalten: bekannte Daten, offene Punkte und nächster Stand.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
              <div
                key={item.title}
                className="rounded-2xl border border-border bg-white p-6"
              >
                <Icon className="text-seal-blue mb-5" size={28} />
                <h3 className="text-lg font-bold text-seal-blue mb-3">{item.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{item.desc}</p>
              </div>
              );
            })}
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
                <p className="text-sm text-muted-foreground">sealingAI bereitet das Gespräch vor. Die finale technische Prüfung bleibt beim Hersteller oder Spezialisten.</p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <Settings className="text-seal-blue shrink-0" size={32} />
              <div>
                <h4 className="font-bold text-foreground mb-1">Fallbezogen statt Lexikon</h4>
                <p className="text-sm text-muted-foreground">sealingAI fragt nach dem, was für deinen konkreten Dichtungsfall relevant ist.</p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle2 className="text-seal-blue shrink-0" size={32} />
              <div>
                <h4 className="font-bold text-foreground mb-1">Kontrollierte Übergabe</h4>
                <p className="text-sm text-muted-foreground">Hersteller sehen nichts, solange du es nicht explizit freigibst.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. MVP FOKUS & 5. MEDIUM INTELLIGENCE */}
      <section className="py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="rounded-3xl border border-border p-10 flex flex-col justify-between">
              <div>
                <Factory className="text-seal-blue mb-6" size={40} />
                <h3 className="text-2xl font-bold text-seal-blue mb-4">Dichtungsfall klären</h3>
                <p className="text-muted-foreground leading-relaxed mb-8 text-[17px]">
                  Beschreibe dein Problem in normalen Worten. sealingAI macht sichtbar, was bekannt ist, was fehlt und welche Frage zuerst geklärt werden sollte.
                </p>
              </div>
              <Link href="/dashboard/new" className="text-sm font-bold text-seal-blue flex items-center gap-2 hover:underline">
                Fall starten <ArrowRight size={14} />
              </Link>
            </div>
            <div className="rounded-3xl border border-border p-10 flex flex-col justify-between bg-seal-blue text-white">
              <div>
                <Beaker className="text-seal-light-blue mb-6" size={40} />
                <h3 className="text-2xl font-bold mb-4">Materialfrage gezielt stellen</h3>
                <p className="opacity-80 leading-relaxed mb-8 text-[17px]">
                  FKM, EPDM, NBR oder PTFE sind selten allein entscheidbar. sealingAI führt zur richtigen Anfragebasis, statt Scheinsicherheit zu verkaufen.
                </p>
              </div>
              <Link href="/werkstoffe" className="text-sm font-bold text-seal-light-blue flex items-center gap-2 hover:underline">
                Werkstoffe einordnen <ArrowRight size={14} />
              </Link>
            </div>
            <div className="rounded-3xl border border-border p-10 flex flex-col justify-between">
              <div>
                <BookOpen className="text-seal-blue mb-6" size={40} />
                <h3 className="text-2xl font-bold text-seal-blue mb-4">SealingPedia</h3>
                <p className="text-muted-foreground leading-relaxed mb-8 text-[17px]">
                  Fachliche Artikel zu Werkstoffen, Medien, Schadensbildern und Anfrageparametern, damit du Dichtungsfragen sauberer einordnen kannst.
                </p>
              </div>
              <Link href="/wissen" className="text-sm font-bold text-seal-blue flex items-center gap-2 hover:underline">
                SealingPedia öffnen <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 6. HOW IT WORKS */}
      <section className="bg-slate-50 py-24">
        <div className="mx-auto max-w-7xl px-6 text-center">
          <h2 className="text-3xl font-bold text-foreground mb-16">So wird aus Unsicherheit eine Anfragebasis</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { step: "1", label: "Fall beschreiben", desc: "Du startest mit dem, was du weißt. Auch unvollständige Angaben sind erlaubt." },
              { step: "2", label: "Nächste Lücke klären", desc: "sealingAI priorisiert, welche Information zuerst wirklich weiterhilft." },
              { step: "3", label: "Angaben einordnen", desc: "Bekanntes, Geschätztes, Offenes und Widersprüchliches werden unterscheidbar." },
              { step: "4", label: "Souverän fragen", desc: "Du gehst mit einer besseren Anfragebasis ins Hersteller- oder Teamgespräch." },
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
          <h2 className="text-4xl font-bold text-seal-blue mb-8">Klär deinen nächsten Dichtungsfall.</h2>
          <p className="text-xl text-muted-foreground mb-12">
            Stelle bessere Fragen, erkenne offene Punkte und halte deinen Fall fest, bevor du ihn weitergibst.
          </p>
          <Link
            href="/dashboard/new"
            className="inline-flex items-center gap-3 rounded-full bg-seal-blue px-10 py-5 text-xl font-bold text-white shadow-2xl transition-all hover:scale-105 active:scale-95"
          >
            Dichtungsfall klären
            <ArrowRight size={22} />
          </Link>
        </div>
      </section>
    </div>
  );
}
