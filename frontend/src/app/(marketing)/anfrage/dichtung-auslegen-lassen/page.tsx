import { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CheckCircle2, FileText, Gauge, SearchCheck, ShieldCheck } from "lucide-react";
import { createMetadata } from "@/lib/seo/metadata";

export const metadata: Metadata = createMetadata({
  title: "Dichtung Anfrage vorbereiten: Fall klären vor Herstellerkontakt",
  description:
    "sealingAI klärt deinen Dichtungsfall, macht offene Punkte sichtbar und bereitet eine herstellerprüfbare Anfragebasis vor. Keine finale Auslegungsfreigabe.",
  path: "/anfrage/dichtung-auslegen-lassen",
});

const requiredFields = [
  "Anwendung und Dichtungsart",
  "Medium, Konzentration und Additive",
  "Temperatur im Dauerbetrieb und Spitzen",
  "Druck, Bewegung und Geschwindigkeit",
  "Bauraum, Abmessungen und Normbezug",
  "Werkstoffwunsch oder bisherige Lösung",
  "Fehlerbild bei Ersatz oder Optimierung",
  "Menge, Zeithorizont und Prüfbedarf",
];

const steps = [
  {
    icon: SearchCheck,
    title: "Fall klären",
    text: "sealingAI macht sichtbar, worum es technisch geht, welche Angaben belastbar sind und was noch offen ist.",
  },
  {
    icon: Gauge,
    title: "Nächsten Schritt finden",
    text: "Statt langer Mängellisten priorisiert sealingAI die nächste Frage, die deinen Fall wirklich weiterbringt.",
  },
  {
    icon: FileText,
    title: "Souverän übergeben",
    text: "Aus deinem Fall entsteht eine bessere Anfragebasis. Nichts geht an Hersteller, solange du es nicht freigibst.",
  },
];

export default function DichtungAuslegenLassenPage() {
  return (
    <div className="flex flex-col">
      <section className="border-b border-border/50 py-20 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
              Dichtungsfall vor der Anfrage klären
            </span>
            <h1 className="mt-4 max-w-4xl text-4xl font-bold tracking-tight text-seal-blue md:text-6xl">
              Dichtung Anfrage vorbereiten, bevor du den Hersteller fragst
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground md:text-xl">
              sealingAI hilft dir, deinen Dichtungsfall zu verstehen, offene Punkte zu erkennen und
              aussagefähig ins Gespräch zu gehen. Ziel ist keine Schnellfreigabe, sondern eine
              klare, herstellerprüfbare Anfragebasis.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link
                href="/dashboard/new?request_type=new_design"
                className="group inline-flex items-center gap-3 rounded-full bg-seal-blue px-8 py-4 text-lg font-bold text-white shadow-xl transition-all hover:opacity-90 active:scale-95"
              >
                Fall jetzt klären
                <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/wissen/wellendichtring"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-white px-8 py-4 text-lg font-medium text-foreground transition-all hover:bg-slate-50 active:scale-95"
              >
                Dichtungswissen ansehen
              </Link>
            </div>
          </div>

          <aside className="rounded-2xl border border-border bg-slate-50 p-8">
            <div className="flex items-start gap-4">
              <ShieldCheck className="mt-1 shrink-0 text-seal-blue" size={32} />
              <div>
                <h2 className="text-xl font-bold text-seal-blue">Keine Scheinsicherheit</h2>
                <p className="mt-3 leading-relaxed text-muted-foreground">
                  sealingAI wählt keine Dichtung final aus und gibt keine Materialeignung frei. Die
                  Plattform macht dich aussagefähig und bereitet die Herstellerprüfung vor.
                </p>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div className="max-w-3xl">
            <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
              Souveränität, Tempo und Klarheit
            </span>
            <h2 className="mt-3 text-3xl font-bold text-foreground">
              Eine gute Anfrage beginnt vor dem Herstellerkontakt
            </h2>
            <p className="mt-5 text-[17px] leading-relaxed text-muted-foreground">
              Viele Anfragen starten mit einer Abmessung, einem Werkstoffnamen oder einem Schadensbild.
              Für eine technische Prüfung braucht der Hersteller aber den Betriebsfall. sealingAI hilft,
              diese Informationen schnell zu sortieren, ohne blinde Flecken zu verstecken.
            </p>
          </div>

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="rounded-2xl border border-border p-7">
                  <Icon className="text-seal-blue" size={30} />
                  <h3 className="mt-5 text-xl font-bold text-seal-blue">{step.title}</h3>
                  <p className="mt-3 leading-relaxed text-muted-foreground">{step.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="bg-slate-50 py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <span className="text-sm font-bold uppercase tracking-widest text-seal-blue/60">
              Anfragebasis
            </span>
            <h2 className="mt-3 text-3xl font-bold text-foreground">
              Was du dem Hersteller schon sagen kannst und was noch fehlt
            </h2>
            <p className="mt-5 text-[17px] leading-relaxed text-muted-foreground">
              Nicht jede Anfrage ist vollständig. Entscheidend ist, bekannte Angaben, Annahmen und offene
              Punkte sauber zu unterscheiden. So wird aus Unsicherheit ein besseres Gesprächsniveau.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {requiredFields.map((field) => (
              <div key={field} className="flex items-start gap-3 rounded-xl bg-white p-4">
                <CheckCircle2 className="mt-0.5 shrink-0 text-seal-blue" size={20} />
                <span className="text-sm font-medium leading-relaxed text-foreground">{field}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-8 md:grid-cols-3">
            <Link
              href="/werkstoffe/fkm"
              className="rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
            >
              <h3 className="text-lg font-bold text-seal-blue">Materialfrage einordnen</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                FKM, NBR, EPDM oder PTFE sind keine fertigen Antworten. Erst der Fall macht sie prüfbar.
              </p>
            </Link>
            <Link
              href="/medien/dichtung-oel"
              className="rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
            >
              <h3 className="text-lg font-bold text-seal-blue">Medium genauer klären</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                Öl, Reiniger, Dampf oder Chemikalie sind oft zu ungenau. Details verändern die Prüfung.
              </p>
            </Link>
            <Link
              href="/wissen/wellendichtring-undicht"
              className="rounded-2xl border border-border p-7 transition-all hover:border-seal-blue hover:shadow-lg"
            >
              <h3 className="text-lg font-bold text-seal-blue">Ausfallbild festhalten</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                Bei Leckage zählt nicht nur das Ersatzteil, sondern was davor im Betrieb passiert ist.
              </p>
            </Link>
          </div>
        </div>
      </section>

      <section className="bg-seal-blue py-20 text-white">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 px-6 md:flex-row md:items-center">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-bold">Klär den Fall, bevor du fragst.</h2>
            <p className="mt-4 text-lg leading-relaxed text-seal-light-blue">
              Starte mit dem, was bekannt ist. sealingAI führt dich zum nächsten sinnvollen Schritt und hält deinen Fall fest.
            </p>
          </div>
          <Link
            href="/dashboard/new?request_type=new_design"
            className="inline-flex shrink-0 items-center gap-3 rounded-full bg-white px-8 py-4 text-lg font-bold text-seal-blue transition-all hover:bg-seal-light-blue active:scale-95"
          >
            Dichtungsfall klären
            <ArrowRight size={20} />
          </Link>
        </div>
      </section>
    </div>
  );
}
