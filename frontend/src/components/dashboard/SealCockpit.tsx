"use client";

import { useState } from "react";
import { AlertTriangle, Calculator, CheckCircle2, CircleDot, ClipboardList } from "lucide-react";

import { DecisionUnderstandingPanel } from "@/components/dashboard/DecisionUnderstandingPanel";
import { ManufacturerFitPanel } from "@/components/dashboard/ManufacturerFitPanel";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import {
  type CalculationEvidenceMetric,
  type CockpitTabId,
  type CriticalDriver,
  type ParameterDataRow,
  type SealCockpitOverview,
} from "@/lib/engineering/sealCockpitViewModel";
import { cn } from "@/lib/utils";

export function CockpitTabs({
  tabs,
  activeTab,
  onTabChange,
}: {
  tabs: SealCockpitOverview["tabs"];
  activeTab: CockpitTabId;
  onTabChange: (tab: CockpitTabId) => void;
}) {
  return (
    <div role="tablist" aria-label="SealAI Cockpit" className="custom-scrollbar flex gap-1 overflow-x-auto border-b border-[#E5E7EB] px-4 pt-4">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "h-10 shrink-0 rounded-t-[12px] border border-b-0 px-3 text-sm font-semibold transition-colors",
              isActive
                ? "border-[#0B57D0] bg-[#0B57D0] text-white"
                : "border-transparent bg-[#FAFAFB] text-[#4B5563] hover:bg-[#F0F2F5] hover:text-[#111827]",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function CockpitStatusStrip({ items }: { items: SealCockpitOverview["statusStrip"] }) {
  return (
    <div className="grid grid-cols-1 gap-2 px-4 pt-4 sm:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="min-h-[78px] rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">{item.label}</div>
          <div className="mt-2 text-sm font-semibold leading-snug text-[#111827]">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function OverviewCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof ClipboardList;
  children: React.ReactNode;
}) {
  return (
    <section className="min-h-[276px] rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <h2 className="text-base font-semibold tracking-tight text-[#111827]">{title}</h2>
        <div className="grid h-9 w-9 place-items-center rounded-[14px] bg-[#F5F7FB] text-[#4B5563]">
          <Icon size={17} />
        </div>
      </div>
      {children}
    </section>
  );
}

export function ParameterDataCard({
  rows,
  warning,
}: {
  rows: ParameterDataRow[];
  warning: string;
}) {
  return (
    <OverviewCard title="Parameter & Datenlage" icon={ClipboardList}>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start justify-between gap-3 border-b border-[#F0F2F5] pb-2 last:border-b-0">
            <span className="text-sm text-[#6B7280]">{row.label}</span>
            <span className="max-w-[58%] text-right text-sm font-semibold text-[#111827]">{row.value}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-[12px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm font-medium text-[#9A3412]">
        {warning}
      </div>
    </OverviewCard>
  );
}

function riskTone(risk: CriticalDriver["risk"]) {
  switch (risk) {
    case "Hoch":
      return "border-[#FDECEC] bg-[#FDECEC] text-[#991B1B]";
    case "Mittel":
      return "border-[#FFF4E5] bg-[#FFF4E5] text-[#9A3412]";
    case "Gering":
      return "border-[#EAF7EE] bg-[#EAF7EE] text-[#166534]";
    case "Offen":
      return "border-[#E5E7EB] bg-[#F0F2F5] text-[#4B5563]";
  }
}

export function CriticalDriversCard({ drivers }: { drivers: CriticalDriver[] }) {
  return (
    <OverviewCard title="Kritische Treiber" icon={AlertTriangle}>
      <div className="space-y-2">
        {drivers.map((driver) => (
          <div key={driver.label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2.5">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[#111827]">{driver.label}</div>
              <div className="mt-1 text-sm text-[#4B5563]">{driver.consequence}</div>
            </div>
            <span className={cn("h-fit rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.08em]", riskTone(driver.risk))}>
              {driver.risk}
            </span>
          </div>
        ))}
      </div>
    </OverviewCard>
  );
}

export function SolutionConsequenceCard({ solution }: { solution: SealCockpitOverview["solution"] }) {
  return (
    <OverviewCard title="Lösung & Konsequenz" icon={CheckCircle2}>
      <div className="rounded-[14px] border border-[#CFE0FF] bg-[#EAF2FF] px-4 py-3">
        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#0B57D0]">{solution.assessmentTitle}</div>
        <p className="mt-2 text-sm font-medium leading-relaxed text-[#1F3B63]">{solution.assessment}</p>
      </div>
      <div className="mt-4 space-y-3">
        {solution.rows.map((row) => (
          <div key={row.label}>
            <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{row.label}</div>
            <div className="mt-1 text-sm leading-relaxed text-[#111827]">{row.value}</div>
          </div>
        ))}
      </div>
    </OverviewCard>
  );
}

function CalculationMetric({ metric }: { metric: CalculationEvidenceMetric }) {
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="text-[12px] font-semibold text-[#4B5563]">{metric.label}</div>
      <div className="mt-2 text-lg font-semibold tracking-tight text-[#111827]">{metric.value}</div>
      <div className="mt-2 space-y-1 text-[12px] text-[#6B7280]">
        {metric.limit && <div>{metric.limit}</div>}
        {metric.reserve && <div>{metric.reserve}</div>}
      </div>
      <div className="mt-3 inline-flex rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[#0B57D0]">
        {metric.status}
      </div>
    </div>
  );
}

export function CalculationsEvidenceCard({ metrics }: { metrics: CalculationEvidenceMetric[] }) {
  return (
    <OverviewCard title="Berechnungen & Nachweise" icon={Calculator}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {metrics.map((metric) => (
          <CalculationMetric key={metric.label} metric={metric} />
        ))}
      </div>
    </OverviewCard>
  );
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="mx-4 mt-4 rounded-[18px] border border-dashed border-[#D1D5DB] bg-[#FAFAFB] p-6 text-sm text-[#4B5563]">
      <div className="flex items-center gap-2 text-base font-semibold text-[#111827]">
        <CircleDot size={16} />
        {label}
      </div>
      <p className="mt-2 max-w-2xl leading-relaxed">
        Dieser Cockpit-Tab ist vorbereitet. Die Übersicht bleibt der aktuelle kompakte Arbeitsstand für Herstellerprüfung, offene Punkte und technische Konsequenzen.
      </p>
    </div>
  );
}

export function SealCockpit({ data, workspace }: { data: SealCockpitOverview; workspace: WorkspaceView | null }) {
  const [activeTab, setActiveTab] = useState<CockpitTabId>("overview");
  const activeLabel = data.tabs.find((tab) => tab.id === activeTab)?.label ?? "Übersicht";

  return (
    <aside className="flex h-full min-h-[720px] min-w-0 flex-col overflow-hidden rounded-[20px] border border-[#E5E7EB] bg-white shadow-[0_8px_24px_rgba(15,23,42,0.08)] lg:min-h-0">
      <CockpitTabs tabs={data.tabs} activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pb-4">
        {activeTab === "overview" ? (
          <>
            <CockpitStatusStrip items={data.statusStrip} />
            <div className="px-4 pt-4">
              <DecisionUnderstandingPanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <ManufacturerFitPanel workspace={workspace} />
            </div>
            <div className="grid grid-cols-1 gap-4 px-4 pt-4 xl:grid-cols-2">
              <ParameterDataCard rows={data.parameters.rows} warning={data.parameters.warning} />
              <CriticalDriversCard drivers={data.criticalDrivers} />
              <SolutionConsequenceCard solution={data.solution} />
              <CalculationsEvidenceCard metrics={data.calculations} />
            </div>
            <div className="mx-4 mt-4 rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-4 py-3 text-sm font-medium text-[#4B5563]">
              {data.footerNote}
            </div>
          </>
        ) : (
          <PlaceholderTab label={activeLabel} />
        )}
      </div>
    </aside>
  );
}
