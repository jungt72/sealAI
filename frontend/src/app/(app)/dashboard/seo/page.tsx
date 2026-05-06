import fs from "node:fs/promises";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileText,
  KeyRound,
  ListChecks,
  Radar,
  RefreshCw,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { getAllSlugs } from "@/lib/content/loader";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "SEO Cockpit | SealingAI",
  robots: {
    index: false,
    follow: false,
  },
};

type StatusTone = "ready" | "attention" | "quiet";

type ReportSummary = {
  name: string;
  path: string;
  modifiedAt: string;
  title: string;
  summary: string;
};

type RoadmapRow = {
  phase: number;
  path: string;
  status: "online" | "planned";
  cluster: string;
  primaryKeyword: string;
  intent: string;
  priority: "hoch" | "mittel";
};

const ROADMAP: RoadmapRow[] = [
  {
    phase: 1,
    path: "/wissen/wellendichtring",
    status: "online",
    cluster: "Radialwellendichtringe",
    primaryKeyword: "wellendichtring",
    intent: "Terminologie, Grenzen und Anfrageparameter verstehen",
    priority: "hoch",
  },
  {
    phase: 1,
    path: "/werkstoffe/fkm",
    status: "online",
    cluster: "Werkstoffe",
    primaryKeyword: "fkm dichtung",
    intent: "FKM/Viton technisch einordnen, ohne finale Freigabe zu behaupten",
    priority: "hoch",
  },
  {
    phase: 1,
    path: "/werkstoffe/ptfe",
    status: "online",
    cluster: "Werkstoffe",
    primaryKeyword: "ptfe dichtung",
    intent: "Chemische und thermische Grenzen als RFQ-Prüfbasis strukturieren",
    priority: "hoch",
  },
  {
    phase: 1,
    path: "/werkstoffe/nbr",
    status: "online",
    cluster: "Werkstoffe",
    primaryKeyword: "nbr dichtung",
    intent: "Ölnahe Anwendungen, Temperatur und FKM-Vergleich einordnen",
    priority: "hoch",
  },
  {
    phase: 1,
    path: "/werkstoffe/epdm",
    status: "online",
    cluster: "Werkstoffe",
    primaryKeyword: "epdm dichtung",
    intent: "EPDM, Dampf/Wasserstoff und kritische Medien sauber abgrenzen",
    priority: "hoch",
  },
  {
    phase: 2,
    path: "/wissen/radialwellendichtring-din-3760",
    status: "online",
    cluster: "Normen & Maße",
    primaryKeyword: "radialwellendichtring din 3760",
    intent: "Norm- und Maßkontext vor einer Anfrage klären",
    priority: "hoch",
  },
  {
    phase: 2,
    path: "/medien/dichtung-oel",
    status: "online",
    cluster: "Medien",
    primaryKeyword: "dichtung öl",
    intent: "Öltyp, Additive, Temperatur, Druck und Dynamik strukturiert aufnehmen",
    priority: "hoch",
  },
  {
    phase: 2,
    path: "/medien/dichtung-dampf",
    status: "online",
    cluster: "Medien",
    primaryKeyword: "dichtung dampf",
    intent: "Dampf als kritisches Medium über Druck, Temperatur und Zyklen qualifizieren",
    priority: "mittel",
  },
  {
    phase: 2,
    path: "/wissen/wellendichtring-undicht",
    status: "online",
    cluster: "Fehleraufnahme",
    primaryKeyword: "wellendichtring undicht",
    intent: "Leckageursachen eingrenzen und Herstellerklärung vorbereiten",
    priority: "hoch",
  },
  {
    phase: 3,
    path: "/anfrage/dichtung-auslegen-lassen",
    status: "online",
    cluster: "RFQ",
    primaryKeyword: "dichtung auslegen lassen",
    intent: "Kommerzielle Anfrage in geregelte RFQ-Qualifizierung überführen",
    priority: "hoch",
  },
];

const KEYWORD_CLUSTERS = [
  {
    cluster: "Radial shaft seals",
    keywords: "radialwellendichtring, wellendichtring, rwdr, din 3760",
    intent: "Identify/compare/design basics",
  },
  {
    cluster: "Materials",
    keywords: "fkm dichtung, ptfe dichtung, nbr dichtung, epdm dichtung",
    intent: "Material suitability orientation",
  },
  {
    cluster: "Media compatibility",
    keywords: "dichtung öl, dichtung dampf, dichtung chemikalienbeständig",
    intent: "Compatibility pre-check",
  },
  {
    cluster: "RFQ preparation",
    keywords: "dichtung anfrage vorbereiten, dichtung auslegen lassen",
    intent: "Commercial technical intent",
  },
  {
    cluster: "Failure intake",
    keywords: "dichtung undicht ursache, wellendichtring ausfall",
    intent: "Problem diagnosis",
  },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function pathExists(candidate: string) {
  try {
    await fs.access(candidate);
    return true;
  } catch {
    return false;
  }
}

async function collectMarkdownFiles(root: string): Promise<string[]> {
  if (!(await pathExists(root))) {
    return [];
  }
  const entries = await fs.readdir(root, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const nextPath = path.join(root, entry.name);
      if (entry.isDirectory()) {
        return collectMarkdownFiles(nextPath);
      }
      return entry.isFile() && entry.name.endsWith(".md") ? [nextPath] : [];
    }),
  );
  return nested.flat();
}

function extractReportSummary(markdown: string) {
  const withoutFrontmatter = markdown.replace(/^---[\s\S]*?---\s*/, "");
  const title = withoutFrontmatter.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? "SEO Report";
  const summarySection = withoutFrontmatter.match(/## Executive Summary\s+([\s\S]*?)(?:\n## |\n# |$)/);
  const summary = summarySection?.[1]
    ?.split("\n")
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(" ")
    || "Report vorhanden. Details im Markdown-Report prüfen.";
  return { title, summary };
}

async function latestReports(): Promise<ReportSummary[]> {
  const candidates = [
    process.env.SEO_REPORT_DIR,
    "/var/seo/reports",
    "/home/thorsten/var/seo/reports",
    path.resolve(process.cwd(), "..", "seo", "reports"),
  ].filter(Boolean) as string[];
  const files = (await Promise.all(candidates.map((candidate) => collectMarkdownFiles(candidate)))).flat();
  const uniqueFiles = Array.from(new Set(files));
  const reports = await Promise.all(
    uniqueFiles.map(async (filePath) => {
      const [stat, markdown] = await Promise.all([
        fs.stat(filePath),
        fs.readFile(filePath, "utf-8").catch(() => ""),
      ]);
      const { title, summary } = extractReportSummary(markdown);
      return {
        name: path.basename(filePath),
        path: filePath,
        modifiedAt: stat.mtime.toISOString(),
        title,
        summary,
      };
    }),
  );
  return reports
    .sort((a, b) => new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime())
    .slice(0, 5);
}

async function seoStackStatus() {
  const repoRoot = path.resolve(process.cwd(), "..");
  const checks = await Promise.all([
    pathExists(path.join(repoRoot, "seo", "scripts", "run_gsc_sync.sh")),
    pathExists(path.join(repoRoot, "seo", "scripts", "run_dataforseo_keyword_refresh.sh")),
    pathExists(path.join(repoRoot, "seo", "systemd", "sealai-seo-gsc-sync.timer")),
    pathExists(path.join(repoRoot, "seo", "systemd", "sealai-seo-weekly-report.timer")),
    pathExists(path.join(repoRoot, "seo", "migrations", "001_init.sql")),
  ]);
  return {
    gscScript: checks[0],
    dataForSeoScript: checks[1],
    gscTimer: checks[2],
    weeklyTimer: checks[3],
    sqliteSchema: checks[4],
  };
}

function StatusPill({ tone, children }: { tone: StatusTone; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        tone === "ready" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "attention" && "border-amber-200 bg-amber-50 text-amber-700",
        tone === "quiet" && "border-[#DDE6F2] bg-white text-[#64748B]",
      )}
    >
      {children}
    </span>
  );
}

function Metric({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof BarChart3;
}) {
  return (
    <div className="rounded-[16px] border border-[#E3EAF4] bg-white/80 px-4 py-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7A8699]">{label}</div>
        <Icon size={18} className="text-[#0B57D0]" />
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-tight text-[#111827]">{value}</div>
      <div className="mt-1 text-sm leading-5 text-[#64748B]">{detail}</div>
    </div>
  );
}

export default async function SeoDashboardPage() {
  const [wissen, werkstoffe, medien, reports, stack] = await Promise.all([
    getAllSlugs("wissen"),
    getAllSlugs("werkstoffe"),
    getAllSlugs("medien"),
    latestReports(),
    seoStackStatus(),
  ]);
  const publishedCount = wissen.length + werkstoffe.length + medien.length + 1;
  const onlineRoadmap = ROADMAP.filter((row) => row.status === "online").length;
  const reportsReady = reports.length > 0;
  const automationReady = stack.gscScript && stack.dataForSeoScript && stack.gscTimer && stack.weeklyTimer;

  const actions = [
    {
      title: reportsReady ? "Aktuellen GSC-Report prüfen" : "Ersten GSC-Report erzeugen",
      detail: reportsReady
        ? "Quick-Win- und Anomaly-Reports liegen vor und sollten in die Content-Priorisierung einfließen."
        : "Noch keine Markdown-Reports gefunden. Nächster Schritt: GSC-Sync und Daily/Weekly Reports laufen lassen.",
      command: "PYTHONPATH=seo/src python -m sealai_seo.cli sync-gsc && PYTHONPATH=seo/src python -m sealai_seo.cli report-weekly",
      tone: reportsReady ? "ready" : "attention",
    },
    {
      title: "Keyword Foundation schärfen",
      detail: "Seed-Cluster stehen. DataForSEO-Volumen sollten kostenkontrolliert aktualisiert und gegen GSC-Queries gemappt werden.",
      command: "PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-budget-check --planned-cost 0.10",
      tone: stack.dataForSeoScript ? "ready" : "attention",
    },
    {
      title: "Content-Architektur gegen V8-Claim-Boundary prüfen",
      detail: "Alle Seiten müssen Orientierung und Anfragequalität liefern, aber keine finale Material- oder Herstellerfreigabe behaupten.",
      command: "PYTHONPATH=seo/src python -m sealai_seo.cli report-content-roadmap",
      tone: "quiet",
    },
  ] as const;

  return (
    <main className="h-full overflow-y-auto bg-[#F5F7FB] px-5 py-5 text-[#111827]">
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-5">
        <section className="flex flex-wrap items-start justify-between gap-4 border-b border-[#E4EAF3] pb-5">
          <div>
            <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-[#0B57D0]">
              <Radar size={16} />
              Interne SEO-Zentrale
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">SEO Cockpit</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#5E6B7E]">
              Automatisierter Überblick für GSC, DataForSEO, Content-Roadmap, technische Hygiene und priorisierte nächste Schritte.
              Die Seite ist Teil des geschützten Dashboards und wird nicht indexiert.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusPill tone={stack.sqliteSchema ? "ready" : "attention"}>
              <ShieldCheck size={13} /> SQLite Schema
            </StatusPill>
            <StatusPill tone={stack.gscScript ? "ready" : "attention"}>
              <Search size={13} /> GSC Stack
            </StatusPill>
            <StatusPill tone={stack.dataForSeoScript ? "ready" : "attention"}>
              <KeyRound size={13} /> DataForSEO
            </StatusPill>
            <StatusPill tone={reportsReady ? "ready" : "attention"}>
              <FileText size={13} /> Reports
            </StatusPill>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Public Content" value={String(publishedCount)} detail={`${wissen.length} Wissen, ${werkstoffe.length} Werkstoffe, ${medien.length} Medien, 1 RFQ-Landingpage`} icon={FileText} />
          <Metric label="Run-0 Roadmap" value={`${onlineRoadmap}/${ROADMAP.length}`} detail="erste Keyword- und Content-Architektur online abbildbar" icon={ListChecks} />
          <Metric label="Automation" value={automationReady ? "bereit" : "offen"} detail="GSC/DataForSEO Skripte und Report-Timer im SEO-Stack" icon={Workflow} />
          <Metric label="Letzter Report" value={reports[0] ? formatDate(reports[0].modifiedAt) : "noch keiner"} detail={reports[0]?.name ?? "GSC-Reports nach erstem Sync sichtbar"} icon={Clock3} />
        </section>

        <section className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="rounded-[18px] border border-[#E3EAF4] bg-white/80 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Keyword- und Content-Map</h2>
                <p className="mt-1 text-sm text-[#64748B]">Run-0 Priorisierung mit V8-Grenze: Orientierung und RFQ-Qualifizierung statt finaler Auslegung.</p>
              </div>
              <Link href="/wissen" className="inline-flex items-center gap-1.5 rounded-full border border-[#D9E5F7] bg-white px-3 py-1.5 text-sm font-semibold text-[#0B57D0] hover:bg-[#F8FBFF]">
                Content ansehen <ArrowUpRight size={14} />
              </Link>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-[#E6ECF5] text-[11px] uppercase tracking-[0.12em] text-[#7A8699]">
                    <th className="py-3 pr-4">Phase</th>
                    <th className="py-3 pr-4">Pfad</th>
                    <th className="py-3 pr-4">Keyword</th>
                    <th className="py-3 pr-4">Cluster</th>
                    <th className="py-3 pr-4">Intent</th>
                    <th className="py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ROADMAP.map((row) => (
                    <tr key={row.path} className="border-b border-[#EEF2F7] align-top last:border-0">
                      <td className="py-3 pr-4 font-semibold text-[#0B57D0]">{row.phase}</td>
                      <td className="py-3 pr-4">
                        <Link href={row.path} className="font-medium text-[#111827] hover:text-[#0B57D0]">{row.path}</Link>
                      </td>
                      <td className="py-3 pr-4 font-medium">{row.primaryKeyword}</td>
                      <td className="py-3 pr-4 text-[#4B5563]">{row.cluster}</td>
                      <td className="py-3 pr-4 text-[#4B5563]">{row.intent}</td>
                      <td className="py-3">
                        <StatusPill tone={row.status === "online" ? "ready" : "attention"}>
                          {row.status}
                        </StatusPill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="flex flex-col gap-5">
            <section className="rounded-[18px] border border-[#E3EAF4] bg-white/80 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <h2 className="text-lg font-semibold">Nächste Schritte</h2>
              <div className="mt-4 space-y-3">
                {actions.map((action) => (
                  <div key={action.title} className="rounded-[14px] border border-[#E7ECF3] bg-[#FBFCFE] p-3">
                    <div className="flex items-start gap-2">
                      {action.tone === "ready" ? <CheckCircle2 size={17} className="mt-0.5 text-emerald-600" /> : <AlertTriangle size={17} className="mt-0.5 text-amber-600" />}
                      <div>
                        <div className="font-semibold">{action.title}</div>
                        <p className="mt-1 text-sm leading-5 text-[#64748B]">{action.detail}</p>
                        <code className="mt-2 block rounded-[10px] bg-[#F1F5FA] px-2.5 py-2 text-[11px] leading-4 text-[#475569]">
                          {action.command}
                        </code>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-[18px] border border-[#E3EAF4] bg-white/80 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
              <h2 className="text-lg font-semibold">Letzte Reports</h2>
              <div className="mt-4 space-y-3">
                {reports.length ? reports.map((report) => (
                  <div key={report.path} className="rounded-[14px] border border-[#E7ECF3] bg-[#FBFCFE] p-3">
                    <div className="text-sm font-semibold">{report.title}</div>
                    <div className="mt-1 text-[12px] text-[#7A8699]">{formatDate(report.modifiedAt)} · {report.name}</div>
                    <p className="mt-2 text-sm leading-5 text-[#4B5563]">{report.summary}</p>
                  </div>
                )) : (
                  <div className="rounded-[14px] border border-amber-200 bg-amber-50 p-3 text-sm leading-5 text-amber-800">
                    Noch keine generierten Markdown-Reports gefunden. Sobald `report-daily`, `report-weekly` oder `report-keyword-foundation` laufen, erscheinen sie hier automatisch.
                  </div>
                )}
              </div>
            </section>
          </aside>
        </section>

        <section className="rounded-[18px] border border-[#E3EAF4] bg-white/80 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-[#0B57D0]" />
            <h2 className="text-lg font-semibold">Keyword-Cluster</h2>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            {KEYWORD_CLUSTERS.map((cluster) => (
              <div key={cluster.cluster} className="rounded-[14px] border border-[#E7ECF3] bg-[#FBFCFE] p-3">
                <div className="font-semibold">{cluster.cluster}</div>
                <p className="mt-2 text-sm leading-5 text-[#4B5563]">{cluster.keywords}</p>
                <div className="mt-3 text-[12px] font-medium text-[#0B57D0]">{cluster.intent}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[18px] border border-[#D9E5F7] bg-[#F8FBFF] p-4 text-sm leading-6 text-[#4B5563]">
          <div className="font-semibold text-[#111827]">Governance-Regel für alle SEO-Inhalte</div>
          SealingAI darf technische Orientierung, strukturierte Rückfragen und eine prüfbare Anfragebasis liefern.
          Die Seite darf keine finale Materialeignung, Dichtungsauslegung oder Herstellerfreigabe behaupten.
        </section>
      </div>
    </main>
  );
}
