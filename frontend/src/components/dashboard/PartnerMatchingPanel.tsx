"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Factory,
  Info,
  Shield,
  XCircle,
} from "lucide-react";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import { getUnavailableMatchingActions } from "@/lib/workspaceActionAvailability";

type Props = {
  workspace: WorkspaceView;
};

const CLUSTER_STYLE: Record<string, { bg: string; icon: React.ElementType }> = {
  viable: { bg: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: CheckCircle2 },
  manufacturer_validation: { bg: "bg-blue-50 text-blue-700 ring-blue-200", icon: Factory },
};

function specificityLabel(value: string): string {
  const map: Record<string, string> = {
    compound_required: "Compound",
    product_family_required: "Product Family",
    subfamily: "Subfamily",
    family_only: "Family",
  };
  return map[value] || value.replace(/_/g, " ");
}

export default function PartnerMatchingPanel({ workspace: ws }: Props) {
  const { matching } = ws;
  const unavailableActions = getUnavailableMatchingActions(ws);

  return (
    <div className="space-y-3 rounded-2xl border border-slate-200/70 bg-white/60 p-4 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          Partner Matching
        </p>
        <span className="text-[10px] font-medium capitalize text-slate-400">
          {matching.dataSource.replace(/_/g, " ")}
        </span>
      </div>

      {matching.ready ? (
        <div className="flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-[11px] font-bold text-emerald-600 ring-1 ring-emerald-200">
          <CheckCircle2 className="h-4 w-4" />
          Matching technically available
        </div>
      ) : (
        <div className="rounded-lg bg-slate-50 px-2.5 py-2 ring-1 ring-slate-200">
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-bold text-slate-500">
            <XCircle className="h-4 w-4 text-slate-400" />
            Selection not active
          </div>
          <ul className="space-y-0.5">
            {matching.notReadyReasons.map((reason, index) => (
              <li key={index} className="flex items-center gap-1 text-[10px] text-slate-400">
                <Info className="h-2.5 w-2.5 shrink-0" />
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {matching.items.length > 0 && (
        <section>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <Shield className="h-3.5 w-3.5" />
            Candidate Matches
          </div>
          <div className="space-y-2">
            {matching.items.map((item, index) => {
              const clusterStyle = CLUSTER_STYLE[item.cluster] || CLUSTER_STYLE.viable;
              const Icon = clusterStyle.icon;
              const isSelected = matching.selectedPartnerId === item.material;

              return (
                <div
                  key={index}
                  className={`flex flex-col gap-1.5 rounded-xl border p-3 ${
                    isSelected
                      ? "border-blue-200 bg-blue-50 ring-2 ring-blue-500/20"
                      : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <div className={`rounded-md p-1 ${clusterStyle.bg}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <span className="text-[13px] font-bold text-slate-700">{item.material}</span>
                    </div>
                    {isSelected && (
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-600">
                        Selected
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 pl-7">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                      {specificityLabel(item.specificity)}
                    </span>
                    {item.requiresValidation && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-blue-600">
                        <AlertTriangle className="h-3 w-3" />
                        Validation Needed
                      </span>
                    )}
                  </div>

                  {item.groundedFacts.length > 0 && (
                    <div className="mt-2 space-y-1 pl-7">
                      {item.groundedFacts.map((fact, factIndex) => (
                        <div key={factIndex} className="flex flex-col gap-0.5">
                          <div className="flex items-start gap-1.5 text-[9px] leading-tight">
                            <div className="mt-1 h-1 w-1 shrink-0 rounded-full bg-blue-400" />
                            <div className="flex flex-col">
                              <span className="text-slate-500">
                                <span className="font-semibold text-slate-700">{fact.name}:</span>{" "}
                                {fact.value}
                                {fact.unit ? ` ${fact.unit}` : ""}
                              </span>
                              {fact.source && (
                                <span className="text-[8px] italic text-slate-400">
                                  Source: {fact.source}
                                </span>
                              )}
                            </div>
                            {fact.isDivergent && (
                              <div className="ml-auto flex items-center gap-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-amber-600 ring-1 ring-amber-200">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                <span className="text-[7px] font-bold uppercase">Divergence</span>
                              </div>
                            )}
                          </div>

                          {fact.isDivergent && fact.variants.length > 0 && (
                            <div className="ml-2.5 mt-0.5 flex flex-col gap-0.5 border-l border-amber-100 pl-2">
                              {fact.variants.map((variant, variantIndex) => (
                                <span
                                  key={variantIndex}
                                  className="text-[8px] leading-tight text-amber-500"
                                >
                                  Alternative: {variant.value}
                                  {fact.unit ? ` ${fact.unit}` : ""} (via {variant.source})
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                </div>
              );
            })}
          </div>
        </section>
      )}

      {unavailableActions.length > 0 && (
        <section className="border-t border-slate-100 pt-2">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <Ban className="h-3.5 w-3.5" />
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
        <span>
          {matching.items.length} matched material{matching.items.length !== 1 ? "s" : ""}
        </span>
        {matching.selectedPartnerId && (
          <span className="font-bold text-emerald-500">Partner Selected</span>
        )}
      </div>
    </div>
  );
}
