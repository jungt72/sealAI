"use client";

import {
  ArrowRight,
  CheckCircle2,
  FileDown,
  Loader2,
  RefreshCw,
  Zap,
  HelpCircle,
} from "lucide-react";
import type { CaseWorkspaceProjection } from "@/lib/workspaceApi";

type Props = {
  workspace: CaseWorkspaceProjection;
  onConfirmRfq: () => void;
  isConfirmingRfq: boolean;
  onGeneratePdf: () => void;
  isGeneratingPdf: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
  onHandover: () => void;
  isHandingOver: boolean;
};

type Action = {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  variant: "primary" | "secondary" | "warning" | "success";
  onClick?: () => void;
  isLoading?: boolean;
  disabled?: boolean;
};

export default function NextBestActionPanel({
  workspace: ws,
  onConfirmRfq,
  isConfirmingRfq,
  onGeneratePdf,
  isGeneratingPdf,
  onRefresh,
  isRefreshing,
  onHandover,
  isHandingOver,
}: Props) {
  const { rfq_status: rfq, artifact_status: art, cycle_info: cycle, completeness: comp } = ws;

  const actions: Action[] = [];

  // 1. Stale Artifacts (Critical)
  if (cycle.derived_artifacts_stale) {
    actions.push({
      id: "refresh",
      label: "Recalculate Workspace",
      description: "Technical data has changed. Update artifacts to proceed.",
      icon: RefreshCw,
      variant: "warning",
      onClick: onRefresh,
      isLoading: isRefreshing,
    });
  }
  // 2. Missing Critical Data (Discovery Phase)
  else if (comp.missing_critical_parameters.length > 0) {
    actions.push({
      id: "discovery",
      label: "Provide Missing Data",
      description: `Need: ${comp.missing_critical_parameters.slice(0, 2).join(", ")}${comp.missing_critical_parameters.length > 2 ? "..." : ""}`,
      icon: HelpCircle,
      variant: "secondary",
      disabled: true,
    });
  }
  // 3. Confirm RFQ (Ready for Operation)
  else if (art.has_rfq_draft && !rfq.rfq_confirmed && rfq.release_status !== "inadmissible") {
    actions.push({
      id: "confirm_rfq",
      label: "Confirm RFQ Package",
      description: "Technical validation complete. Seal the package for partners.",
      icon: CheckCircle2,
      variant: "primary",
      onClick: onConfirmRfq,
      isLoading: isConfirmingRfq,
    });
  }
  // 4. Generate Document (After Confirmation)
  else if (rfq.rfq_confirmed && !rfq.has_html_report) {
    actions.push({
      id: "generate_doc",
      label: "Generate RFQ Document",
      description: "Create the official technical PDF for manufacturers.",
      icon: FileDown,
      variant: "primary",
      onClick: onGeneratePdf,
      isLoading: isGeneratingPdf,
    });
  }
  // 5. Matching Ready (Selection Phase)
  else if (ws.partner_matching.matching_ready && !ws.partner_matching.selected_partner_id) {
    actions.push({
      id: "matching",
      label: "Select Partner",
      description: "Matching active. Choose a material candidate to finalize selection.",
      icon: ArrowRight,
      variant: "primary",
      disabled: true,
    });
  }
  // 6. Handover Ready
  else if (rfq.handover_ready && !rfq.handover_initiated) {
    actions.push({
      id: "handover",
      label: "Send RFQ to Partner",
      description: "Final step: Hand over the technical package to the selected manufacturer.",
      icon: Zap,
      variant: "success",
      onClick: onHandover,
      isLoading: isHandingOver,
    });
  }
  // 7. Selection Complete / Handover Initiated
  else if (rfq.handover_initiated) {
    actions.push({
      id: "complete",
      label: "RFQ Submitted",
      description: `Technical package sent to: ${ws.partner_matching.selected_partner_id}`,
      icon: CheckCircle2,
      variant: "secondary",
      disabled: true,
    });
  }
  else if (ws.partner_matching.selected_partner_id) {
    actions.push({
      id: "complete",
      label: "Partner Selected",
      description: `Case finalized with partner/material: ${ws.partner_matching.selected_partner_id}`,
      icon: CheckCircle2,
      variant: "secondary",
      disabled: true,
    });
  }

  if (actions.length === 0) return null;

  const topAction = actions[0];

  return (
    <div className="rounded-2xl border-2 border-blue-100 bg-blue-50/50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 rounded-lg bg-blue-100 text-blue-600">
          <Zap className="h-4 w-4 fill-current" />
        </div>
        <p className="text-xs font-bold uppercase tracking-wider text-blue-700">Next Recommended Action</p>
      </div>

      <div className="space-y-3">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-bold text-slate-900">{topAction.label}</h3>
          <p className="text-[11px] text-slate-500 leading-relaxed">{topAction.description}</p>
        </div>

        {topAction.onClick ? (
          <button
            onClick={topAction.onClick}
            disabled={topAction.disabled || topAction.isLoading}
            className={`w-full flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-all ${
              topAction.variant === "success"
                ? "bg-emerald-600 text-white hover:bg-emerald-700 shadow-md shadow-emerald-100"
                : topAction.variant === "primary"
                ? "bg-blue-600 text-white hover:bg-blue-700 shadow-md shadow-blue-200"
                : topAction.variant === "warning"
                ? "bg-amber-500 text-white hover:bg-amber-600 shadow-md shadow-amber-100"
                : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50"
            } disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]`}
          >
            {topAction.isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <topAction.icon className="h-4 w-4" />
            )}
            {topAction.isLoading ? "Processing..." : topAction.label}
          </button>
        ) : (
          <div className="flex items-center gap-2 text-[11px] font-medium text-slate-400 bg-slate-100/50 rounded-lg px-3 py-2 italic border border-slate-100">
            <topAction.icon className="h-3.5 w-3.5" />
            {topAction.id === "discovery" ? "Waiting for user input in chat..." : "Process step reached."}
          </div>
        )}
      </div>
    </div>
  );
}
