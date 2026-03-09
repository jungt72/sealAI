"use client";

import {
  CheckCircle2,
  RefreshCw,
  FileText,
  Shield,
  ClipboardCheck,
  FileDown,
  Factory,
  Layers,
} from "lucide-react";
import type { CaseWorkspaceProjection } from "@/lib/workspaceApi";
import { deriveLifecycleSteps, type LifecycleStep } from "@/lib/lifecycleSteps";

type Props = {
  workspace: CaseWorkspaceProjection;
};

const ICON_MAP: Record<string, React.ElementType> = {
  Layers,
  Shield,
  CheckCircle2,
  FileText,
  ClipboardCheck,
  FileDown,
  Factory,
};

const STATUS_STYLE = {
  done: { dot: "bg-emerald-500", text: "text-emerald-700", line: "bg-emerald-300" },
  active: { dot: "bg-blue-500 animate-pulse", text: "text-blue-700", line: "bg-slate-200" },
  pending: { dot: "bg-slate-300", text: "text-slate-400", line: "bg-slate-200" },
} as const;

export default function CaseLifecyclePanel({ workspace: ws }: Props) {
  const { cycle_info: cycle } = ws;
  const steps = deriveLifecycleSteps(ws);
  const isStale = cycle.derived_artifacts_stale;

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 backdrop-blur-sm p-4 space-y-3">
      {/* Header: Cycle / Revision */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          Case Lifecycle
        </p>
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span>C{cycle.current_assertion_cycle_id}</span>
          <span className="text-slate-300">·</span>
          <span>R{cycle.state_revision}</span>
        </div>
      </div>

      {/* Stale banner */}
      {isStale && (
        <div className="flex items-center gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 ring-1 ring-amber-200">
          <RefreshCw className="h-3 w-3 text-amber-600 shrink-0" />
          <span className="text-[11px] font-semibold text-amber-700">
            Artifacts stale
          </span>
          {cycle.stale_reason && (
            <span className="text-[10px] text-amber-500 ml-auto truncate max-w-[120px]">
              {cycle.stale_reason.replace(/_/g, " ")}
            </span>
          )}
        </div>
      )}

      {/* Timeline steps */}
      <div className="relative pl-4">
        {steps.map((step, i) => {
          const style = STATUS_STYLE[step.status];
          const Icon = ICON_MAP[step.iconName] || Layers;
          const isLast = i === steps.length - 1;

          return (
            <div key={step.label} className="relative flex items-start gap-2 pb-2.5 last:pb-0">
              {/* Vertical line */}
              {!isLast && (
                <div className={`absolute left-[5px] top-[14px] w-px h-[calc(100%-6px)] ${style.line}`} />
              )}
              {/* Dot */}
              <div className={`relative z-10 mt-[3px] h-[11px] w-[11px] rounded-full border-2 border-white ${style.dot} shrink-0`} />
              {/* Content */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <Icon className={`h-3 w-3 shrink-0 ${style.text}`} />
                  <span className={`text-[11px] font-semibold ${style.text}`}>
                    {step.label}
                  </span>
                </div>
                {step.detail && (
                  <p className="text-[10px] text-slate-400 mt-0.5 truncate capitalize">
                    {step.detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer: Profile revision binding */}
      <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-100 pt-2">
        <span>
          Profile rev. {cycle.asserted_profile_revision}
        </span>
        <span className={isStale ? "text-amber-500 font-semibold" : "text-emerald-500"}>
          {isStale ? "Needs revalidation" : "Fresh"}
        </span>
      </div>
    </div>
  );
}
