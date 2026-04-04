"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Cog,
  Download,
  Droplets,
  FileText,
  Gauge,
  HelpCircle,
  Info,
  Thermometer,
  XCircle,
} from "lucide-react";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import { getUnavailableRfqActions } from "@/lib/workspaceActionAvailability";

type Props = {
  workspace: WorkspaceView;
};

const READINESS_STYLES: Record<
  string,
  { bg: string; text: string; label: string; icon: React.ElementType }
> = {
  inadmissible: {
    bg: "bg-slate-100 ring-1 ring-slate-300",
    text: "text-slate-600",
    label: "Not RFQ-Ready",
    icon: XCircle,
  },
  precheck_only: {
    bg: "bg-amber-50 ring-1 ring-amber-300",
    text: "text-amber-700",
    label: "Precheck Only",
    icon: AlertTriangle,
  },
  manufacturer_validation_required: {
    bg: "bg-blue-50 ring-1 ring-blue-300",
    text: "text-blue-700",
    label: "Mfr. Validation Required",
    icon: AlertTriangle,
  },
  rfq_ready: {
    bg: "bg-emerald-50 ring-1 ring-emerald-300",
    text: "text-emerald-700",
    label: "RFQ Ready",
    icon: CheckCircle2,
  },
};

const CONTEXT_ICONS: Record<string, React.ElementType> = {
  medium: Droplets,
  pressure_bar: Gauge,
  temperature_C: Thermometer,
  speed_rpm: Cog,
  shaft_diameter: Cog,
  dynamic_type: Cog,
};

function formatContextKey(key: string): string {
  const map: Record<string, string> = {
    medium: "Medium",
    pressure_bar: "Pressure (bar)",
    temperature_C: "Temperature (°C)",
    shaft_diameter: "Shaft Dia. (mm)",
    speed_rpm: "Speed (rpm)",
    dynamic_type: "Motion Type",
    shaft_runout: "Shaft Runout",
    shaft_hardness: "Shaft Hardness",
    seal_material: "Seal Material",
    normative_references: "Norms",
  };
  return map[key] || key.replace(/_/g, " ");
}

function formatContextValue(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export default function RfqPackagePanel({ workspace: ws }: Props) {
  const { rfq, governance, manufacturerQuestions, conflicts, completeness } = ws;
  const pkg = rfq.package;
  const unavailableActions = getUnavailableRfqActions(ws);

  const effectiveStatus = rfq.releaseStatus || governance.releaseStatus || "inadmissible";
  const style = READINESS_STYLES[effectiveStatus] || READINESS_STYLES.inadmissible;
  const StatusIcon = style.icon;

  const hasContext = Object.keys(pkg.operatingContextRedacted).length > 0;
  const hasMandatoryQuestions =
    pkg.manufacturerQuestionsMandatory.length > 0 || manufacturerQuestions.mandatory.length > 0;
  const hasBlockers = rfq.blockers.length > 0;
  const hasOpenConflicts = conflicts.open > 0;
  const hasAssumptions =
    pkg.buyerAssumptionsAcknowledged.length > 0 || governance.assumptions.length > 0;
  const hasDisclaimers = governance.requiredDisclaimers.length > 0;

  const allMandatory = Array.from(
    new Set([...pkg.manufacturerQuestionsMandatory, ...manufacturerQuestions.mandatory]),
  );
  const allAssumptions = Array.from(
    new Set([...pkg.buyerAssumptionsAcknowledged, ...governance.assumptions]),
  );

  return (
    <div className="space-y-3 rounded-2xl border border-slate-200/70 bg-white/60 p-4 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          RFQ Package
        </p>
        {rfq.hasDraft && (
          <span className="text-[10px] font-medium text-slate-400">{pkg.rfqId || "Draft"}</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${style.bg} ${style.text}`}
        >
          <StatusIcon className="h-3 w-3" />
          {style.label}
        </span>
        {rfq.confirmed && (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600">
            <CheckCircle2 className="h-3 w-3" /> Confirmed
          </span>
        )}
      </div>

      {hasContext && (
        <section>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <FileText className="h-3.5 w-3.5" />
            Technical Context (Redacted)
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {Object.entries(pkg.operatingContextRedacted).map(([key, value]) => {
              const Icon = CONTEXT_ICONS[key] || Info;
              return (
                <div key={key} className="flex items-center gap-1.5 text-[11px] leading-tight">
                  <Icon className="h-3 w-3 shrink-0 text-slate-400" />
                  <span className="truncate text-slate-500">{formatContextKey(key)}</span>
                  <span className="ml-auto shrink-0 font-medium text-slate-700">
                    {formatContextValue(value)}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {(hasBlockers || hasOpenConflicts || rfq.openPoints.length > 0) && (
        <section>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <AlertTriangle className="h-3.5 w-3.5" />
            Unresolved
          </div>
          {hasBlockers && (
            <ul className="mb-1 space-y-0.5">
              {rfq.blockers.map((blocker, index) => (
                <li key={index} className="flex items-center gap-1 text-[11px] text-rose-600">
                  <XCircle className="h-3 w-3 shrink-0" />
                  <span className="truncate">{blocker}</span>
                </li>
              ))}
            </ul>
          )}
          {hasOpenConflicts && (
            <p className="text-[10px] text-slate-500">
              {conflicts.open} open conflict{conflicts.open !== 1 ? "s" : ""} (see Case
              Governance)
            </p>
          )}
        </section>
      )}

      {hasMandatoryQuestions && (
        <section>
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
              <HelpCircle className="h-3.5 w-3.5" />
              Partner Clarifications
            </div>
            <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 ring-1 ring-amber-200">
              {allMandatory.length}
            </span>
          </div>
          <ul className="space-y-1">
            {allMandatory.slice(0, 4).map((question, index) => (
              <li key={index} className="truncate text-[11px] leading-tight text-slate-600">
                <span className="mr-1 font-bold text-rose-500">!</span>
                {question}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(hasAssumptions || hasDisclaimers) && (
        <section className="border-t border-slate-100 pt-2">
          {hasAssumptions && (
            <div className="mb-1">
              <span className="text-[10px] font-semibold text-slate-500">Assumptions: </span>
              <span className="text-[10px] text-slate-400">
                {allAssumptions.slice(0, 3).join(", ")}
                {allAssumptions.length > 3 && ` +${allAssumptions.length - 3}`}
              </span>
            </div>
          )}
          {hasDisclaimers && (
            <p className="text-[10px] leading-snug text-amber-600">
              <span className="font-semibold">Disclaimer: </span>
              {governance.requiredDisclaimers[0]}
            </p>
          )}
        </section>
      )}

      {rfq.hasHtmlReport && rfq.documentUrl && (
        <section className="border-t border-slate-100 pt-3">
          <a
            href={rfq.documentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-slate-100 px-3 py-2 text-[12px] font-semibold text-slate-700 transition-colors hover:bg-slate-200"
          >
            <Download className="h-3.5 w-3.5" />
            Open RFQ Document
          </a>
        </section>
      )}

      {unavailableActions.length > 0 && (
        <section className="border-t border-slate-100 pt-3">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <AlertTriangle className="h-3.5 w-3.5" />
            Pending Platform Actions
          </div>
          <div className="space-y-2">
            {unavailableActions.map((action) => (
              <div key={action.id} className="rounded-xl border border-slate-200 bg-slate-50 p-2.5">
                <button
                  type="button"
                  disabled
                  aria-disabled="true"
                  className="flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-lg bg-slate-200 px-3 py-2 text-[12px] font-semibold text-slate-500 opacity-80"
                >
                  <Ban className="h-3.5 w-3.5" />
                  {action.label} unavailable
                </button>
                <p className="mt-1.5 text-[10px] leading-snug text-slate-500">{action.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="flex items-center justify-between border-t border-slate-100 pt-2 text-[10px] text-slate-400">
        <span>Coverage {completeness.coveragePercent}%</span>
        <span>{rfq.confirmed ? "Confirmed" : rfq.hasDraft ? "Draft ready" : "No draft"}</span>
      </div>
    </div>
  );
}
