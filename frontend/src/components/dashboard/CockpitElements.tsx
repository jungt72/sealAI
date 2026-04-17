"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { 
  ClipboardList, 
  AlertTriangle, 
  BarChart3, 
  FileText, 
  Layers 
} from "lucide-react";

/* --- TABS --- */
export type CockpitTabType = "clarification" | "parameters" | "risks" | "rfq" | "documents";

interface CockpitTabsProps {
  activeTab: CockpitTabType;
  onTabChange: (tab: CockpitTabType) => void;
}

export function CockpitTabs({ activeTab, onTabChange }: CockpitTabsProps) {
  const tabs: { id: CockpitTabType; label: string; icon: any }[] = [
    { id: "clarification", label: "Klärung", icon: Layers },
    { id: "parameters", label: "Parameter", icon: ClipboardList },
    { id: "risks", label: "Risiken & Offene Punkte", icon: AlertTriangle },
    { id: "rfq", label: "Anfrage / RFQ", icon: BarChart3 },
    { id: "documents", label: "Dokumente", icon: FileText },
  ];

  return (
    <div className="flex items-center border-b border-border bg-white px-4">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-all",
              isActive 
                ? "border-seal-blue text-seal-blue" 
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/* --- CARDS --- */
interface CockpitCardProps {
  title: string;
  children: React.ReactNode;
  icon?: any;
  status?: "default" | "warning" | "error" | "success";
  className?: string;
}

export function CockpitCard({ title, children, icon: Icon, status = "default", className }: CockpitCardProps) {
  const statusColors = {
    default: "border-border",
    warning: "border-amber-200 bg-amber-50/20",
    error: "border-rose-200 bg-rose-50/20",
    success: "border-emerald-200 bg-emerald-50/20",
  };

  return (
    <div className={cn("rounded-xl border p-4 shadow-sm bg-white transition-all", statusColors[status], className)}>
      <div className="mb-3 flex items-center justify-between border-b border-border/50 pb-2">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={14} className="text-muted-foreground" />}
          <h3 className="text-[11px] font-bold text-foreground uppercase tracking-widest">{title}</h3>
        </div>
      </div>
      <div className="text-sm text-muted-foreground leading-relaxed">
        {children}
      </div>
    </div>
  );
}

/* --- HELPERS --- */
export function ParameterRow({ label, value, unit, origin, isMandatory }: { 
  label: string; 
  value: any; 
  unit?: string;
  origin?: string;
  isMandatory?: boolean;
}) {
  const hasValue = value !== null && value !== undefined && value !== "";
  
  return (
    <div className="flex items-center justify-between py-1 border-b border-border/30 last:border-0 group">
      <div className="flex items-center gap-1.5 overflow-hidden">
        {isMandatory && !hasValue && (
          <div className="h-1 w-1 rounded-full bg-rose-400 shrink-0" title="Pflichtfeld" />
        )}
        <span className="text-[12px] opacity-70 truncate" title={label}>{label}</span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0 ml-2">
        <span className={cn(
          "text-[12px] font-medium",
          hasValue ? "text-seal-blue" : "text-muted-foreground italic opacity-40"
        )}>
          {hasValue ? `${value}${unit ? ` ${unit}` : ""}` : "offen"}
        </span>
      </div>
    </div>
  );
}

export function StatusBadge({ label, variant = "default" }: { 
  label: string; 
  variant?: "default" | "warning" | "error" | "success" | "info";
}) {
  const variants = {
    default: "bg-slate-100 text-slate-600 border-slate-200",
    warning: "bg-amber-100 text-amber-700 border-amber-200",
    error: "bg-rose-100 text-rose-700 border-rose-200",
    success: "bg-emerald-100 text-emerald-700 border-emerald-200",
    info: "bg-blue-100 text-blue-700 border-blue-200",
  };

  return (
    <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border", variants[variant])}>
      {label}
    </span>
  );
}

/* --- PANEL --- */
export function CockpitPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full bg-slate-50/50 border-l border-border w-[380px] shrink-0 custom-scrollbar">
      {children}
    </div>
  );
}
