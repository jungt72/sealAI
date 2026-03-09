"use client";

import {
  Factory,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Shield,
  XCircle,
  Info,
  ChevronRight,
  Loader2,
} from "lucide-react";
import type { CaseWorkspaceProjection } from "@/lib/workspaceApi";

type Props = {
  workspace: CaseWorkspaceProjection;
  onSelectPartner?: (partnerId: string) => void;
  isSelectingPartner?: boolean;
};

const CLUSTER_STYLE: Record<string, { bg: string; icon: React.ElementType; label: string }> = {
  viable: { bg: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: CheckCircle2, label: "Viable" },
  manufacturer_validation: { bg: "bg-blue-50 text-blue-700 ring-blue-200", icon: Factory, label: "Mfr. Validation" },
};

function specificityLabel(s: string): string {
  const map: Record<string, string> = {
    compound_required: "Compound",
    product_family_required: "Product Family",
    subfamily: "Subfamily",
    family_only: "Family",
  };
  return map[s] || s.replace(/_/g, " ");
}

export default function PartnerMatchingPanel({ workspace: ws, onSelectPartner, isSelectingPartner }: Props) {
  const { partner_matching: pm } = ws;

  const handleSelect = (partnerId: string) => {
    if (pm.matching_ready && onSelectPartner && !isSelectingPartner) {
      onSelectPartner(partnerId);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 backdrop-blur-sm p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          Partner Matching
        </p>
        <span className="text-[10px] font-medium text-slate-400 capitalize">
          {pm.data_source.replace(/_/g, " ")}
        </span>
      </div>

      {/* Readiness */}
      {pm.matching_ready ? (
        <div className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1.5 rounded-lg ring-1 ring-emerald-200">
          <CheckCircle2 className="h-4 w-4" />
          Ready for partner selection
        </div>
      ) : (
        <div className="bg-slate-50 px-2.5 py-2 rounded-lg ring-1 ring-slate-200">
          <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 mb-1">
            <XCircle className="h-4 w-4 text-slate-400" />
            Selection not active
          </div>
          <ul className="space-y-0.5">
            {pm.not_ready_reasons.map((r, i) => (
              <li key={i} className="text-[10px] text-slate-400 flex items-center gap-1">
                <Info className="h-2.5 w-2.5 shrink-0" />
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Material Fit Items / Selection Cards */}
      {pm.material_fit_items.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">
            <Shield className="h-3.5 w-3.5" />
            Candidate Matches
          </div>
          <div className="space-y-2">
            {pm.material_fit_items.map((item, i) => {
              const isSelected = pm.selected_partner_id === item.material;
              const cs = CLUSTER_STYLE[item.cluster] || CLUSTER_STYLE.viable;
              const Icon = cs.icon;
              const canSelect = pm.matching_ready && !isSelected;

              return (
                <button
                  key={i}
                  disabled={!canSelect || isSelectingPartner}
                  onClick={() => handleSelect(item.material)}
                  className={`w-full text-left flex flex-col gap-1.5 rounded-xl border p-3 transition-all ${
                    isSelected
                      ? "bg-blue-50 border-blue-200 ring-2 ring-blue-500/20"
                      : canSelect
                        ? "bg-white border-slate-200 hover:border-blue-300 hover:shadow-sm"
                        : "bg-slate-50 border-slate-100 opacity-80 cursor-not-allowed"
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-2">
                      <div className={`p-1 rounded-md ${cs.bg}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <span className={`text-[13px] font-bold ${isSelected ? "text-blue-700" : "text-slate-700"}`}>
                        {item.material}
                      </span>
                    </div>
                    {isSelected && (
                      <span className="text-[10px] font-bold text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full uppercase tracking-wider">
                        Selected
                      </span>
                    )}
                    {canSelect && !isSelectingPartner && (
                      <ChevronRight className="h-4 w-4 text-slate-300" />
                    )}
                    {isSelected && isSelectingPartner && (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
                    )}
                  </div>
                  
                  <div className="flex items-center gap-3 pl-7">
                    <span className="text-[10px] text-slate-500 font-medium bg-slate-100 px-1.5 py-0.5 rounded">
                      {specificityLabel(item.specificity)}
                    </span>
                    {item.requires_validation && (
                      <span className="text-[10px] text-blue-600 font-bold flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        Validation Needed
                      </span>
                    )}
                  </div>

                  {/* Grounded Facts section */}
                  {item.grounded_facts && item.grounded_facts.length > 0 && (
                    <div className="mt-2 pl-7 space-y-1">
                      {item.grounded_facts.map((fact, fi) => (
                        <div key={fi} className="flex flex-col gap-0.5">
                          <div className="flex items-start gap-1.5 text-[9px] leading-tight">
                            <div className="w-1 h-1 rounded-full bg-blue-400 mt-1 shrink-0" />
                            <div className="flex flex-col">
                              <span className="text-slate-500">
                                <span className="font-semibold text-slate-700">{fact.name}:</span> {fact.value}{fact.unit ? ` ${fact.unit}` : ""}
                              </span>
                              {fact.source && (
                                <span className="text-[8px] text-slate-400 italic">Source: {fact.source}</span>
                              )}
                            </div>
                            
                            {/* Patch C2: Divergence Badge */}
                            {fact.is_divergent && (
                              <div className="ml-auto flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600 ring-1 ring-amber-200 animate-pulse">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                <span className="font-bold text-[7px] uppercase">Divergence</span>
                              </div>
                            )}
                          </div>

                          {/* Variants display */}
                          {fact.is_divergent && fact.variants && fact.variants.length > 0 && (
                            <div className="ml-2.5 mt-0.5 pl-2 border-l border-amber-100 flex flex-col gap-0.5">
                              {fact.variants.map((v, vi) => (
                                <span key={vi} className="text-[8px] text-amber-500 leading-tight">
                                  Alternative: {v.value}{fact.unit ? ` ${fact.unit}` : ""} (via {v.source})
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {!isSelected && canSelect && (
                    <div className="mt-1 pl-7 flex items-center gap-1 text-[10px] font-bold text-blue-600 uppercase tracking-wide opacity-0 group-hover:opacity-100 transition-opacity">
                      Select Partner <ArrowRightIcon className="h-2.5 w-2.5" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-100 pt-2">
        <span>{pm.material_fit_items.length} matched material{pm.material_fit_items.length !== 1 ? "s" : ""}</span>
        {pm.matching_ready && !pm.selected_partner_id && <span className="text-amber-500 font-bold">Awaiting selection</span>}
        {pm.selected_partner_id && <span className="text-emerald-500 font-bold">Partner Selected</span>}
      </div>
    </div>
  );
}

function ArrowRightIcon(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}
