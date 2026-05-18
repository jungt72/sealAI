import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  EyeOff,
  Fingerprint,
  ListChecks,
  LockKeyhole,
  Radar,
  ShieldCheck,
} from "lucide-react";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Analytics | SealingAI",
  robots: {
    index: false,
    follow: false,
  },
};

type StatusTone = "ready" | "attention" | "quiet";

type StatusCard = {
  title: string;
  value: string;
  description: string;
  tone: StatusTone;
};

const trackedEvents = [
  "landing_cta_clicked",
  "register_started",
  "register_completed",
  "case_started",
  "case_first_input_added",
  "case_step_completed",
  "case_summary_viewed",
  "handover_clicked",
  "sealingpedia_article_viewed",
  "pedia_to_case_clicked",
] as const;

const funnelSteps = [
  "Startseite",
  "Dichtungsfall klären",
  "Login / Registrierung",
  "Fall gestartet",
  "Erste Eingabe",
  "Zusammenfassung",
  "Übergabe / Export",
] as const;

function statusClasses(tone: StatusTone) {
  if (tone === "ready") {
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }
  if (tone === "attention") {
    return "border-amber-200 bg-amber-50 text-amber-950";
  }
  return "border-slate-200 bg-white text-slate-800";
}

export default function AnalyticsDashboardPage() {
  const siteId = process.env.NEXT_PUBLIC_RYBBIT_SITE_ID?.trim() || "";
  const scriptSrc =
    process.env.NEXT_PUBLIC_RYBBIT_SCRIPT_SRC?.trim() || "https://analytics.sealingai.com/api/script.js";
  const dashboardUrl = process.env.NEXT_PUBLIC_RYBBIT_DASHBOARD_URL?.trim() || "";
  const rybbitEnabled = process.env.NEXT_PUBLIC_RYBBIT_ENABLED !== "false" && Boolean(siteId);
  const externalDashboardReady = rybbitEnabled && Boolean(dashboardUrl);

  const statusCards: StatusCard[] = [
    {
      title: "Rybbit Script",
      value: rybbitEnabled ? "aktiv" : "vorbereitet",
      description: rybbitEnabled
        ? "Tracking wird mit Site-ID geladen."
        : "Deaktiviert, bis NEXT_PUBLIC_RYBBIT_ENABLED und Site-ID gesetzt sind.",
      tone: rybbitEnabled ? "ready" : "attention",
    },
    {
      title: "Privacy Guard",
      value: "aktiv",
      description: "Dashboard-, Login- und Account-Pfade sind maskiert; Inputs und Freitexte werden ignoriert.",
      tone: "ready",
    },
    {
      title: "Externe Konsole",
      value: externalDashboardReady ? "verbunden" : "nicht verbunden",
      description: externalDashboardReady
        ? "Der externe Rybbit-Link ist für diese Umgebung konfiguriert."
        : "Kein externer Dashboard-Link, solange Service und DNS nicht belastbar live sind.",
      tone: externalDashboardReady ? "ready" : "attention",
    },
    {
      title: "Datenminimierung",
      value: "erzwungen",
      description: "Events enthalten nur erlaubte Metadaten. Falltexte, Medien, Kundennamen und Dokumentinhalte bleiben außen vor.",
      tone: "ready",
    },
  ];

  return (
    <main className="h-full overflow-y-auto bg-slate-50/80 px-7 py-8 text-slate-950">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-7">
        <section className="flex flex-col gap-5 border-b border-slate-200 pb-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-seal-blue">
              <Activity size={16} />
              Product Analytics
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-normal text-slate-950">Analytics Cockpit</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Privacy-first Produktanalyse für den Weg vom Interesse zum belastbaren Dichtungsfall. Die linke
              Navigation bleibt stabil in der App; externe Tools werden erst verlinkt, wenn sie vollständig
              bereitgestellt sind.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {externalDashboardReady ? (
              <Link
                href={dashboardUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-10 items-center gap-2 rounded-full bg-seal-blue px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-seal-blue/90"
              >
                Rybbit öffnen
                <ArrowUpRight size={16} />
              </Link>
            ) : (
              <span
                aria-disabled="true"
                className="inline-flex h-10 items-center gap-2 rounded-full border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-500"
              >
                Externes Dashboard nicht aktiv
                <LockKeyhole size={16} />
              </span>
            )}
            <Link
              href="/dashboard/new"
              className="inline-flex h-10 items-center gap-2 rounded-full border border-slate-200 bg-white px-4 text-sm font-semibold text-seal-blue shadow-sm transition-colors hover:bg-slate-100"
            >
              Zum Workspace
            </Link>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {statusCards.map((card) => (
            <article key={card.title} className={`rounded-lg border p-4 shadow-sm ${statusClasses(card.tone)}`}>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-xs font-semibold uppercase tracking-[0.16em]">{card.title}</h2>
                {card.tone === "ready" ? <CheckCircle2 size={17} /> : <Radar size={17} />}
              </div>
              <p className="mt-4 text-2xl font-semibold tracking-normal">{card.value}</p>
              <p className="mt-2 text-sm leading-5 opacity-80">{card.description}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <ListChecks size={18} className="text-seal-blue" />
              Funnel
            </div>
            <div className="mt-5 grid gap-2 md:grid-cols-7">
              {funnelSteps.map((step, index) => (
                <div key={step} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                  <div className="text-xs font-semibold text-seal-blue">{String(index + 1).padStart(2, "0")}</div>
                  <div className="mt-2 text-sm font-medium leading-5 text-slate-800">{step}</div>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <EyeOff size={18} className="text-seal-blue" />
              Nicht tracken
            </div>
            <div className="mt-5 grid gap-2 text-sm text-slate-700">
              {[
                "Fall-Freitexte und Problembeschreibungen",
                "konkrete Medien-, Maschinen- oder Kundendaten",
                "Hersteller- und Projektnamen",
                "hochgeladene Dokumente und Zeichnungen",
                "technische Rohwerte außerhalb freigegebener Metadaten",
              ].map((item) => (
                <div key={item} className="flex items-start gap-2 rounded-md bg-slate-50 px-3 py-2">
                  <ShieldCheck size={16} className="mt-0.5 shrink-0 text-emerald-700" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <Fingerprint size={18} className="text-seal-blue" />
              Konfiguration
            </div>
            <dl className="mt-5 grid gap-3 text-sm">
              <div className="rounded-md bg-slate-50 p-3">
                <dt className="font-semibold text-slate-500">Site-ID</dt>
                <dd className="mt-1 text-slate-900">{siteId ? "gesetzt" : "nicht gesetzt"}</dd>
              </div>
              <div className="rounded-md bg-slate-50 p-3">
                <dt className="font-semibold text-slate-500">Script</dt>
                <dd className="mt-1 break-all text-slate-900">{scriptSrc}</dd>
              </div>
              <div className="rounded-md bg-slate-50 p-3">
                <dt className="font-semibold text-slate-500">Dashboard URL</dt>
                <dd className="mt-1 break-all text-slate-900">{dashboardUrl || "nicht gesetzt"}</dd>
              </div>
            </dl>
          </article>

          <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <Activity size={18} className="text-seal-blue" />
              Produkt-Events
            </div>
            <div className="mt-5 grid gap-2 md:grid-cols-2">
              {trackedEvents.map((eventName) => (
                <div
                  key={eventName}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800"
                >
                  {eventName}
                </div>
              ))}
            </div>
          </article>
        </section>
      </div>
    </main>
  );
}
