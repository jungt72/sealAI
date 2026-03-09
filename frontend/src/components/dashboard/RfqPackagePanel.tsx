"use client";

import {
  FileText,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  XCircle,
  Gauge,
  Thermometer,
  Droplets,
  Cog,
  Info,
  Download,
} from "lucide-react";
import type { CaseWorkspaceProjection } from "@/lib/workspaceApi";

type Props = {
  workspace: CaseWorkspaceProjection;
  rfqDocumentUrl?: string;
};

// -- Readiness badge --
const READINESS_STYLES: Record<string, { bg: string; text: string; label: string; icon: React.ElementType }> = {
  inadmissible: { bg: "bg-slate-100 ring-1 ring-slate-300", text: "text-slate-600", label: "Not RFQ-Ready", icon: XCircle },
  precheck_only: { bg: "bg-amber-50 ring-1 ring-amber-300", text: "text-amber-700", label: "Precheck Only", icon: AlertTriangle },
  manufacturer_validation_required: { bg: "bg-blue-50 ring-1 ring-blue-300", text: "text-blue-700", label: "Mfr. Validation Required", icon: AlertTriangle },
  rfq_ready: { bg: "bg-emerald-50 ring-1 ring-emerald-300", text: "text-emerald-700", label: "RFQ Ready", icon: CheckCircle2 },
};

// -- Icons for redacted operating context keys --
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
    temperature_C: "Temperature (\u00b0C)",
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
  if (value == null) return "\u2014";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

export default function RfqPackagePanel({ workspace: ws, rfqDocumentUrl }: Props) {
  const { rfq_package: pkg, rfq_status: rfq, governance_status: gov, manufacturer_questions: mq, conflicts, completeness: comp, cycle_info: cycle } = ws;

  // Determine effective readiness from rfq_status (live admissibility)
  const effectiveStatus = rfq.release_status || gov.release_status || "inadmissible";
  const style = READINESS_STYLES[effectiveStatus] || READINESS_STYLES.inadmissible;
  const StatusIcon = style.icon;

  const hasContext = Object.keys(pkg.operating_context_redacted).length > 0;
  const hasMandatoryQuestions = pkg.manufacturer_questions_mandatory.length > 0 || mq.mandatory.length > 0;
  const hasBlockers = rfq.blockers.length > 0;
  const hasOpenConflicts = conflicts.open > 0;
  const hasAssumptions = pkg.buyer_assumptions_acknowledged.length > 0 || gov.assumptions_active.length > 0;
  const hasDisclaimers = gov.required_disclaimers.length > 0;

  // Merge mandatory questions from rfq_package and manufacturer_questions (dedupe)
  const allMandatory = Array.from(new Set([...pkg.manufacturer_questions_mandatory, ...mq.mandatory]));

  // Merge assumptions from rfq_package and governance
  const allAssumptions = Array.from(new Set([...pkg.buyer_assumptions_acknowledged, ...gov.assumptions_active]));

  const isConfirmed = rfq.rfq_confirmed;

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 backdrop-blur-sm p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">RFQ Package</p>
        {pkg.has_draft && (
          <span className="text-[10px] font-medium text-slate-400">
            {pkg.rfq_id || "Draft"}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${style.bg} ${style.text}`}>
          <StatusIcon className="h-3 w-3" />
          {style.label}
        </span>
        {isConfirmed && (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600">
            <CheckCircle2 className="h-3 w-3" /> Confirmed
          </span>
        )}
      </div>

      {/* Technical Context */}
      {hasContext && (
        <section>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">
            <FileText className="h-3.5 w-3.5" />
            Technical Context (Redacted)
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {Object.entries(pkg.operating_context_redacted).map(([key, value]) => {
              const Icon = CONTEXT_ICONS[key] || Info;
              return (
                <div key={key} className="flex items-center gap-1.5 text-[11px] leading-tight">
                  <Icon className="h-3 w-3 text-slate-400 shrink-0" />
                  <span className="text-slate-500 truncate">{formatContextKey(key)}</span>
                  <span className="font-medium text-slate-700 ml-auto shrink-0">{formatContextValue(value)}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Unresolved */}
      {(hasBlockers || hasOpenConflicts || rfq.open_points.length > 0) && (
        <section>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">
            <AlertTriangle className="h-3.5 w-3.5" />
            Unresolved
          </div>
          {hasBlockers && (
            <ul className="space-y-0.5 mb-1">
              {rfq.blockers.map((b, i) => (
                <li key={i} className="flex items-center gap-1 text-[11px] text-rose-600">
                  <XCircle className="h-3 w-3 shrink-0" />
                  <span className="truncate">{b}</span>
                </li>
              ))}
            </ul>
          )}
          {hasOpenConflicts && (
            <p className="text-[10px] text-slate-500">
              {conflicts.open} open conflict{conflicts.open !== 1 ? "s" : ""} (see Case Governance)
            </p>
          )}
        </section>
      )}

      {/* Partner Clarifications */}
      {hasMandatoryQuestions && (
        <section>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 uppercase tracking-wide">
              <HelpCircle className="h-3.5 w-3.5" />
              Partner Clarifications
            </div>
            <span className="text-[10px] font-medium text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded ring-1 ring-amber-200">
              {allMandatory.length}
            </span>
          </div>
          <ul className="space-y-1">
            {allMandatory.slice(0, 4).map((q, i) => (
              <li key={i} className="text-[11px] text-slate-600 leading-tight truncate">
                <span className="text-rose-500 font-bold mr-1">!</span>{q}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Assumptions / Disclaimers */}
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
            <p className="text-[10px] text-amber-600 leading-snug">
              <span className="font-semibold">Disclaimer: </span>
              {gov.required_disclaimers[0]}
            </p>
          )}
        </section>
      )}

      {/* RFQ Document Link */}
      {rfq.has_html_report && rfqDocumentUrl && (
        <section className="border-t border-slate-100 pt-3">
          <a
            href={rfqDocumentUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            Open RFQ Document
          </a>
        </section>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-100 pt-2">
        <span>Coverage {Math.round(comp.coverage_score * 100)}%</span>
        <span>{isConfirmed ? "Confirmed" : pkg.has_draft ? "Draft ready" : "No draft"}</span>
      </div>
    </div>
  );
}
