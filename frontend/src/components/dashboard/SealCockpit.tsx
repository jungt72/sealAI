"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Beaker,
  Brain,
  Calculator,
  CheckCircle2,
  ClipboardList,
  Factory,
  FileText,
  HelpCircle,
  Layers,
  Search,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react";

import { DecisionUnderstandingPanel } from "@/components/dashboard/DecisionUnderstandingPanel";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { ParameterWorkspaceTab } from "@/components/dashboard/ParameterWorkspaceTab";
import RfqPane from "@/components/dashboard/RfqPane";
import type { AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import type { WorkspaceMaterialCandidate, WorkspaceView } from "@/lib/contracts/workspace";
import {
  type CalculationEvidenceMetric,
  type CockpitTabId,
  type CriticalDriver,
  type ParameterDataRow,
  type SealCockpitOverview,
} from "@/lib/engineering/sealCockpitViewModel";
import { humanizeDisplayText, uniqueDisplayItems } from "@/lib/engineering/displayLabels";
import { type MediumEvidenceItem, type MediumIntelligenceData, useWorkspaceStore } from "@/lib/store/workspaceStore";
import { cn } from "@/lib/utils";

type QuickParameterKind = "text" | "number";

type QuickParameterField = {
  fieldName: string;
  label: string;
  kind: QuickParameterKind;
  placeholder: string;
  unit?: string;
};

type QuickParameterProfile = {
  id: "rotary" | "hydraulic" | "static" | "oring";
  label: string;
  note: string;
  sealingTypeHint: string;
  fields: QuickParameterField[];
};

type QuickParameterFormState = Record<string, string>;

const QUICK_PARAMETER_PROFILES: QuickParameterProfile[] = [
  {
    id: "rotary",
    label: "Rotierend",
    note: "Für RWDR, Gleitringdichtung, Rührwerk, Pumpe oder Getriebeausgang.",
    sealingTypeHint: "rotierende Dichtstelle",
    fields: [
      { fieldName: "medium", label: "Medium", kind: "text", placeholder: "z. B. HLP 46, Wasser-Glykol" },
      { fieldName: "temperature_c", label: "Temperatur", kind: "number", unit: "°C", placeholder: "80" },
      { fieldName: "pressure_bar", label: "Druck", kind: "number", unit: "bar", placeholder: "10" },
      { fieldName: "shaft_diameter_mm", label: "Welle", kind: "number", unit: "mm", placeholder: "40" },
      { fieldName: "speed_rpm", label: "Drehzahl", kind: "number", unit: "rpm", placeholder: "1450" },
      { fieldName: "sealing_type", label: "Dichtungstyp", kind: "text", placeholder: "RWDR, Gleitringdichtung" },
      { fieldName: "counterface_surface", label: "Gegenlauf", kind: "text", placeholder: "gehärtet, Ra, eingelaufen" },
      { fieldName: "installation", label: "Einbauort", kind: "text", placeholder: "Pumpe, Getriebe, Rührwerk" },
    ],
  },
  {
    id: "hydraulic",
    label: "Hydraulik",
    note: "Für Stangen-, Kolben-, Abstreif- und Führungssysteme.",
    sealingTypeHint: "Hydraulikdichtung",
    fields: [
      { fieldName: "hydraulic_fluid", label: "Fluid", kind: "text", placeholder: "z. B. HLP 46, HFC, Bioöl" },
      { fieldName: "temperature_c", label: "Temperatur", kind: "number", unit: "°C", placeholder: "80" },
      { fieldName: "pressure_bar", label: "Arbeitsdruck", kind: "number", unit: "bar", placeholder: "160" },
      { fieldName: "pressure_peaks", label: "Druckspitzen", kind: "number", unit: "bar", placeholder: "250" },
      { fieldName: "rod_or_piston_diameter", label: "Stange/Kolben", kind: "number", unit: "mm", placeholder: "50" },
      { fieldName: "speed_or_stroke", label: "Hub/Geschwindigkeit", kind: "text", placeholder: "0,3 m/s, Hub 500 mm" },
      { fieldName: "groove_dimensions", label: "Nut/Bauraum", kind: "text", placeholder: "Nutmaß oder Zeichnung" },
      { fieldName: "contamination", label: "Verschmutzung", kind: "text", placeholder: "Staub, Späne, außenliegend" },
    ],
  },
  {
    id: "static",
    label: "Statisch",
    note: "Für Flachdichtung, Flansch, Gehäusedeckel oder statische Abdichtung.",
    sealingTypeHint: "statische Dichtung",
    fields: [
      { fieldName: "medium", label: "Medium", kind: "text", placeholder: "z. B. Dampf, Lauge, Öl" },
      { fieldName: "temperature_c", label: "Temperatur", kind: "number", unit: "°C", placeholder: "120" },
      { fieldName: "pressure_bar", label: "Druck", kind: "number", unit: "bar", placeholder: "16" },
      { fieldName: "flange_standard", label: "Flansch/Norm", kind: "text", placeholder: "EN 1092-1, ASME" },
      { fieldName: "flange_size_or_dimensions", label: "Größe/Maß", kind: "text", placeholder: "DN50 PN16, Zeichnung" },
      { fieldName: "gasket_material", label: "Material", kind: "text", placeholder: "PTFE, Graphit, Faser" },
      { fieldName: "thickness", label: "Dicke", kind: "number", unit: "mm", placeholder: "2" },
      { fieldName: "certification_requirement", label: "Nachweise", kind: "text", placeholder: "FDA, TA-Luft, Trinkwasser" },
    ],
  },
  {
    id: "oring",
    label: "O-Ring",
    note: "Für O-Ringe, Stützringe und einfache Nut-/Schnurstärkenklärung.",
    sealingTypeHint: "O-Ring",
    fields: [
      { fieldName: "medium", label: "Medium", kind: "text", placeholder: "z. B. Wasser, Öl, CIP" },
      { fieldName: "temperature_c", label: "Temperatur", kind: "number", unit: "°C", placeholder: "60" },
      { fieldName: "pressure_bar", label: "Druck", kind: "number", unit: "bar", placeholder: "10" },
      { fieldName: "inner_diameter", label: "Innen-Ø", kind: "number", unit: "mm", placeholder: "32" },
      { fieldName: "cross_section", label: "Schnurstärke", kind: "number", unit: "mm", placeholder: "3,53" },
      { fieldName: "material", label: "Werkstoff", kind: "text", placeholder: "NBR, FKM, EPDM" },
      { fieldName: "hardness", label: "Härte", kind: "text", placeholder: "70 Shore A" },
      { fieldName: "static_or_dynamic", label: "Bewegung", kind: "text", placeholder: "statisch, dynamisch" },
    ],
  },
];

const QUICK_NUMERIC_UNITS: Record<string, string> = Object.fromEntries(
  QUICK_PARAMETER_PROFILES.flatMap((profile) =>
    profile.fields
      .filter((field) => field.kind === "number" && field.unit)
      .map((field) => [field.fieldName, field.unit as string]),
  ),
);

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
    <div
      role="tablist"
      aria-label="SealingAI Cockpit"
      className="custom-scrollbar flex gap-2 overflow-x-auto bg-transparent px-4 pb-2 pt-4"
    >
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
              "h-10 shrink-0 rounded-full border px-4 text-sm font-semibold shadow-sm transition-colors",
              isActive
                ? "border-seal-blue bg-seal-blue text-white shadow-[0_8px_20px_rgba(4,30,73,0.18)]"
                : "border-[#D1D5DB] bg-white text-muted-foreground hover:bg-muted hover:text-seal-blue",
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
    <div className="grid grid-cols-1 gap-2 rounded-tl-[20px] px-4 pt-4 sm:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="min-h-[78px] rounded-[14px] border border-[#D1D5DB] bg-white px-3 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{item.label}</div>
          <div className="mt-2 text-sm font-semibold leading-snug text-foreground">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

function workspaceParameterValue(workspace: WorkspaceView | null, fieldName: string): string {
  const parameters = workspace?.parameters as Record<string, unknown> | undefined;
  const value = parameters?.[fieldName];
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

function quickInitialState(workspace: WorkspaceView | null): QuickParameterFormState {
  const fieldNames = new Set(
    QUICK_PARAMETER_PROFILES.flatMap((profile) => profile.fields.map((field) => field.fieldName)),
  );
  const state: QuickParameterFormState = {};
  fieldNames.forEach((fieldName) => {
    state[fieldName] = workspaceParameterValue(workspace, fieldName);
  });
  return state;
}

function quickProfileIdFromWorkspace(workspace: WorkspaceView | null): QuickParameterProfile["id"] {
  const path = String(
    workspace?.sealApplicationProfile?.sealType ||
      workspace?.sealApplicationProfile?.sealFamily ||
      workspace?.engineeringPath ||
      "",
  ).toLowerCase();
  if (path.includes("hyd")) return "hydraulic";
  if (path.includes("o-ring") || path.includes("oring")) return "oring";
  if (path.includes("flach") || path.includes("static")) return "static";
  return "rotary";
}

function parseQuickParameterValue(field: QuickParameterField, rawValue: string): string | number | null {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return null;
  }
  if (field.kind !== "number") {
    return trimmed;
  }
  const normalized = Number(trimmed.replace(",", "."));
  return Number.isFinite(normalized) ? normalized : null;
}

function formatQuickSummary(overrides: AgentOverrideItemRequest[], profile: QuickParameterProfile): string {
  return overrides
    .map((override) => {
      const field = profile.fields.find((item) => item.fieldName === override.field_name);
      const label = override.field_name === "sealing_type" ? "Dichtungstyp" : field?.label ?? override.field_name;
      const unit = override.unit ? ` ${override.unit}` : "";
      return `${label}: ${String(override.value)}${unit}`;
    })
    .join(", ");
}

function quickInputLabel(field: QuickParameterField): string {
  if (field.label === "Medium") {
    return "Schnelleingabe Medium";
  }
  return field.unit ? `${field.label} · ${field.unit}` : field.label;
}

function ParameterQuickEntry({
  workspace,
  isSubmitting,
  onSubmit,
}: {
  workspace: WorkspaceView | null;
  isSubmitting: boolean;
  onSubmit: (overrides: AgentOverrideItemRequest[], summary: string) => Promise<void> | void;
}) {
  const [activeProfileId, setActiveProfileId] = useState<QuickParameterProfile["id"]>(() =>
    quickProfileIdFromWorkspace(workspace),
  );
  const [formState, setFormState] = useState<QuickParameterFormState>(() => quickInitialState(workspace));
  const [isOpen, setIsOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const activeProfile = useMemo(
    () => QUICK_PARAMETER_PROFILES.find((profile) => profile.id === activeProfileId) ?? QUICK_PARAMETER_PROFILES[0],
    [activeProfileId],
  );

  const activeFields = activeProfile.fields;
  const filledCount = activeFields.filter((field) => formState[field.fieldName]?.trim()).length;
  const canSubmit = filledCount > 0 && !isSubmitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    const invalidNumber = activeFields.find((field) => {
      const raw = formState[field.fieldName] ?? "";
      return field.kind === "number" && raw.trim() && parseQuickParameterValue(field, raw) === null;
    });
    if (invalidNumber) {
      setError(`${invalidNumber.label} braucht einen numerischen Wert.`);
      return;
    }

    const overrides: AgentOverrideItemRequest[] = activeFields.flatMap((field) => {
      const value = parseQuickParameterValue(field, formState[field.fieldName] ?? "");
      if (value === null) {
        return [];
      }
      return [
        {
          field_name: field.fieldName,
          value,
          unit: field.unit ?? QUICK_NUMERIC_UNITS[field.fieldName] ?? null,
        },
      ];
    });

    if (
      overrides.length > 0 &&
      !overrides.some((override) => override.field_name === "sealing_type")
    ) {
      overrides.unshift({
        field_name: "sealing_type",
        value: activeProfile.sealingTypeHint,
        unit: null,
      });
    }

    if (overrides.length === 0) {
      setError("Bitte mindestens einen bekannten Parameter eintragen.");
      return;
    }

    await onSubmit(overrides, formatQuickSummary(overrides, activeProfile));
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-4 mt-4 rounded-[18px] border border-[#D1D5DB] bg-white p-4 shadow-[0_10px_28px_rgba(15,23,42,0.05)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-seal-blue">
            <ClipboardList size={14} />
            Direkteingabe
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">
            Bekannte Parameter in den State schreiben
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-[#4B5563]">
            Wähle zuerst die Anwendung. Danach erscheinen die passenden Felder für diesen Dichtungstyp.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setIsOpen((current) => !current)}
          className="shrink-0 rounded-full border border-[#D1D5DB] bg-white px-3 py-1.5 text-xs font-semibold text-seal-blue transition-colors hover:bg-muted"
        >
          {isOpen ? "Einklappen" : "Ausklappen"}
        </button>
      </div>

      {isOpen ? (
        <>
          <div
            role="tablist"
            aria-label="Parameterprofil"
            className="custom-scrollbar mt-4 flex gap-2 overflow-x-auto pb-1"
          >
            {QUICK_PARAMETER_PROFILES.map((profile) => {
              const isActive = profile.id === activeProfile.id;
              return (
                <button
                  key={profile.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => {
                    setActiveProfileId(profile.id);
                    setError(null);
                  }}
                  className={cn(
                    "h-9 shrink-0 rounded-full border px-3 text-xs font-semibold transition-colors",
                    isActive
                      ? "border-seal-blue bg-seal-blue text-white"
                      : "border-[#D1D5DB] bg-white text-muted-foreground hover:bg-muted hover:text-seal-blue",
                  )}
                >
                  {profile.label}
                </button>
              );
            })}
          </div>

          <div className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            {activeProfile.note}
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2 xl:grid-cols-2">
            {activeFields.map((field) => (
              <div key={field.fieldName} className="min-w-0">
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {field.label}
                  {field.unit ? <span className="normal-case tracking-normal text-muted-foreground"> · {field.unit}</span> : null}
                </span>
                <input
                  aria-label={quickInputLabel(field)}
                  type="text"
                  inputMode={field.kind === "number" ? "decimal" : "text"}
                  value={formState[field.fieldName] ?? ""}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      [field.fieldName]: event.target.value,
                    }))
                  }
                  placeholder={field.placeholder}
                  disabled={isSubmitting}
                  className="h-10 w-full rounded-[12px] border border-[#C9D1DC] bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-[#6B7280] focus:border-seal-blue focus:ring-3 focus:ring-seal-blue/10 disabled:cursor-not-allowed disabled:bg-slate-50"
                />
              </div>
            ))}
          </div>

          {error ? (
            <div className="mt-3 rounded-[12px] border border-[#F7C8C8] bg-[#FDECEC] px-3 py-2 text-sm font-semibold text-[#991B1B]">
              {error}
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => {
                setFormState(quickInitialState(workspace));
                setError(null);
              }}
              className="inline-flex min-h-10 items-center gap-2 rounded-full border border-[#D1D5DB] bg-white px-3 py-2 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RotateCcw size={15} />
              Zurücksetzen
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className={cn(
                "inline-flex min-h-10 items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold transition-colors",
                canSubmit
                  ? "bg-seal-blue text-white hover:opacity-90"
                  : "cursor-not-allowed bg-[#E5EAF2] text-[#6B7280]",
              )}
            >
              <Save size={15} />
              In State übernehmen
            </button>
          </div>
        </>
      ) : null}
    </form>
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
    <OverviewCard title="Angaben zum Fall" icon={ClipboardList}>
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
    <OverviewCard title="Was noch wichtig ist" icon={AlertTriangle}>
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
    <OverviewCard title="Einordnung" icon={CheckCircle2}>
      <div className="rounded-[14px] border border-[#D1D5DB] bg-[#EAF2FF] px-4 py-3">
        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#041E49]">{solution.assessmentTitle}</div>
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
      <div className="mt-3 inline-flex rounded-full border border-[#D1D5DB] bg-[#EFF6FF] px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[#041E49]">
        {metric.status}
      </div>
    </div>
  );
}

export function CalculationsEvidenceCard({ metrics }: { metrics: CalculationEvidenceMetric[] }) {
  return (
    <OverviewCard title="Rechencheck" icon={Calculator}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {metrics.map((metric) => (
          <CalculationMetric key={metric.label} metric={metric} />
        ))}
      </div>
    </OverviewCard>
  );
}

function normalizeText(value: unknown): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (Array.isArray(value)) {
    const joined = value.map(normalizeText).filter(Boolean).join(" · ");
    return joined || null;
  }
  return humanizeDisplayText(String(value));
}

function compactItems(items: Array<unknown>, limit = 6) {
  return uniqueDisplayItems(items.map(normalizeText), limit);
}

function WorkspaceTabShell({
  title,
  icon: Icon,
  intro,
  children,
}: {
  title: string;
  icon: typeof ClipboardList;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-4 mt-4 rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <Icon size={17} />
            {title}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">{intro}</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[#D1D5DB] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-semibold text-[#041E49]">
          <ShieldCheck size={14} />
          Nur zur Ansicht
        </div>
      </div>
      {children}
    </section>
  );
}

function InfoTile({
  title,
  value,
  note,
  tone = "neutral",
}: {
  title: string;
  value: string | null;
  note?: string | null;
  tone?: "neutral" | "info" | "warning";
}) {
  const toneClass =
    tone === "warning"
      ? "border-[#FDE2B8] bg-[#FFF4E5]"
      : tone === "info"
        ? "border-[#D1D5DB] bg-[#EFF6FF]"
        : "border-[#E5E7EB] bg-[#FAFAFB]";
  return (
    <div className={cn("rounded-[14px] border p-3", toneClass)}>
      <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      <div className="mt-2 text-sm font-semibold leading-relaxed text-[#111827]">{value || "Noch offen"}</div>
      {note ? <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{note}</p> : null}
    </div>
  );
}

function ItemList({
  title,
  items,
  empty = "Noch keine Angaben vorhanden",
}: {
  title: string;
  items: Array<unknown>;
  empty?: string;
}) {
  const visibleItems = compactItems(items, 7);
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      {visibleItems.length ? (
        <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
          {visibleItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">{empty}</p>
      )}
    </div>
  );
}

function plausibilityTone(plausibility: string) {
  switch (plausibility) {
    case "high":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "blocked":
      return "border-red-200 bg-red-50 text-red-800";
    case "medium":
      return "border-[#D1D5DB] bg-[#EFF6FF] text-[#041E49]";
    default:
      return "border-amber-200 bg-amber-50 text-amber-800";
  }
}

function findingTone(severity: string) {
  switch (severity) {
    case "blocking":
      return "border-red-200 bg-red-50 text-red-800";
    case "watch":
      return "border-amber-200 bg-amber-50 text-amber-800";
    default:
      return "border-[#D1D5DB] bg-[#EFF6FF] text-[#041E49]";
  }
}

function findingLabel(severity: string) {
  switch (severity) {
    case "blocking":
      return "blockierend";
    case "watch":
      return "prüfen";
    default:
      return "Hinweis";
  }
}

function findingKindLabel(kind: string) {
  switch (kind) {
    case "missing_information":
      return "offene Angabe";
    case "contradiction":
      return "Gegenindikator";
    case "medium_challenge":
      return "Medium";
    case "application_challenge":
      return "Anwendung";
    case "derived_signal":
      return "abgeleitet";
    case "claim_guard":
      return "Grenze";
    default:
      return humanizeDisplayText(kind);
  }
}

function actionModeLabel(mode: string) {
  switch (mode) {
    case "CHALLENGE_KNOWN_INPUTS":
      return "bekannte Angaben challengen";
    case "ASK_NEXT_BEST_QUESTION":
      return "nächste Frage";
    case "RUN_SCENARIO_MATRIX":
      return "Szenario-Matrix";
    case "RUN_COUNTERINDICATOR_CHALLENGE":
      return "Gegencheck";
    case "RUN_SURFACE_SPEED_CHALLENGE":
      return "Gegenfläche";
    case "RUN_SUPPORT_SYSTEM_CHALLENGE":
      return "Schmierung/Flush";
    case "RUN_PRESSURE_DIRECTION_CHALLENGE":
      return "Druckrichtung";
    case "RUN_RISK_COMPLETENESS":
      return "Risikoprüfung";
    case "RUN_MEDIUM_CHALLENGE":
      return "Mediumtiefe";
    case "RUN_DERIVED_CALCULATIONS":
      return "Rechencheck";
    default:
      return humanizeDisplayText(mode);
  }
}

function fieldLabel(field: string) {
  switch (field) {
    case "medium":
      return "Medium";
    case "medium_qualifiers":
      return "Mediumdetails";
    case "temperature_c":
      return "Temperatur";
    case "pressure_bar":
      return "Druck";
    case "pressure_direction":
      return "Druckrichtung";
    case "sealing_type":
      return "Dichtungstyp";
    case "shaft_diameter_mm":
      return "Welle";
    case "speed_rpm":
      return "Drehzahl";
    case "counterface_surface":
      return "Gegenfläche";
    case "lubrication_context":
      return "Schmierung/Flush";
    default:
      return humanizeDisplayText(field);
  }
}

function MiniList({
  label,
  items,
  limit = 3,
}: {
  label: string;
  items: string[];
  limit?: number;
}) {
  const visibleItems = compactItems(items, limit);
  if (!visibleItems.length) {
    return null;
  }
  return (
    <div className="mt-2">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{label}</div>
      <ul className="mt-1 space-y-1 text-[12px] leading-relaxed text-[#374151]">
        {visibleItems.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ChallengeChipRow({
  fields,
  actionMode,
  evidenceRefs,
}: {
  fields: string[];
  actionMode: string;
  evidenceRefs: string[];
}) {
  const chips = [
    ...compactItems(fields.map(fieldLabel), 4),
    actionMode ? actionModeLabel(actionMode) : null,
    ...compactItems(evidenceRefs, 2),
  ].filter(Boolean) as string[];

  if (!chips.length) {
    return null;
  }

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full border border-[#E5E7EB] bg-white px-2 py-0.5 text-[11px] font-semibold text-[#4B5563]"
        >
          {chip}
        </span>
      ))}
    </div>
  );
}

export function ChallengeIntelligencePanel({ workspace }: { workspace: WorkspaceView | null }) {
  const challenge = workspace?.challengeIntelligence;
  const findings = challenge?.findings ?? [];
  const hypotheses = challenge?.hypotheses ?? [];
  const question = challenge?.nextBestQuestion ?? null;
  const hasContent = Boolean(
    challenge &&
      challenge.status !== "not_run" &&
      (findings.length || hypotheses.length || question),
  );

  if (!hasContent || !challenge) {
    return null;
  }

  const blockingCount = findings.filter((finding) => finding.severity === "blocking").length;
  const counterindicatorCount =
    findings.filter((finding) => finding.kind === "contradiction").length +
    hypotheses.filter((hypothesis) => hypothesis.counterindicators.length > 0).length;

  return (
    <section className="rounded-[18px] border border-[#D1D5DB] bg-[#FFFFFF] p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#E5E7EB] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <Brain size={17} />
            Challenger
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Befunde, Prüfhypothesen und nächste beste Rückfrage aus dem V9-Kern.
          </p>
        </div>
        <span className="inline-flex rounded-full border border-[#D1D5DB] bg-white/80 px-3 py-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-[#041E49]">
          {challenge.schemaVersion}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {[
          ["Blocker", String(blockingCount)],
          ["Gegenchecks", String(counterindicatorCount)],
          ["Aktionen", String(challenge.actionModesRun.length)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{label}</div>
            <div className="mt-1 text-lg font-semibold text-[#111827]">{value}</div>
          </div>
        ))}
      </div>

      {question ? (
        <div className="mt-4 rounded-[14px] border border-[#D1D5DB] bg-white p-3">
          <div className="flex items-start gap-2">
            <HelpCircle className="mt-0.5 shrink-0 text-[#041E49]" size={17} />
            <div>
              <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#041E49]">
                Nächste beste Frage
              </div>
              <p className="mt-1 text-sm font-semibold leading-relaxed text-[#111827]">{question.question}</p>
              {question.reason ? (
                <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{question.reason}</p>
              ) : null}
              <ChallengeChipRow
                fields={[question.focusKey]}
                actionMode="ASK_NEXT_BEST_QUESTION"
                evidenceRefs={question.closesFindings}
              />
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-[14px] border border-[#E5E7EB] bg-white p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Kritische Befunde</div>
          {findings.length ? (
            <div className="mt-2 space-y-2">
              {findings.slice(0, 6).map((finding) => (
                <div key={finding.findingId} className="rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">
                        {findingKindLabel(finding.kind)}
                      </div>
                      <div className="mt-1 text-sm font-semibold leading-snug text-[#111827]">{finding.title}</div>
                    </div>
                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold", findingTone(finding.severity))}>
                      {findingLabel(finding.severity)}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{finding.summary}</p>
                  {finding.rfqRelevance ? (
                    <p className="mt-2 rounded-[10px] border border-[#E5E7EB] bg-white px-2.5 py-2 text-[12px] leading-relaxed text-[#374151]">
                      RFQ: {humanizeDisplayText(finding.rfqRelevance)}
                    </p>
                  ) : null}
                  <ChallengeChipRow
                    fields={finding.relatedFields}
                    actionMode={finding.actionMode}
                    evidenceRefs={finding.evidenceRefIds}
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">Noch kein Challenger-Befund verfügbar.</p>
          )}
        </div>

        <div className="rounded-[14px] border border-[#E5E7EB] bg-white p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Prüfhypothesen</div>
          {hypotheses.length ? (
            <div className="mt-2 space-y-2">
              {hypotheses.slice(0, 4).map((hypothesis) => (
                <div key={hypothesis.hypothesisId} className="rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold leading-snug text-[#111827]">{hypothesis.label}</div>
                    <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold", plausibilityTone(hypothesis.plausibilityClass))}>
                      {plausibilityLabel(hypothesis.plausibilityClass)}
                    </span>
                  </div>
                  {hypothesis.counterindicators.length ? (
                    <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">
                      Gegenindikator: {humanizeDisplayText(hypothesis.counterindicators[0])}
                    </p>
                  ) : hypothesis.basis.length ? (
                    <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">
                      Basis: {humanizeDisplayText(hypothesis.basis[0])}
                    </p>
                  ) : null}
                  <MiniList label="Blocker" items={hypothesis.blockingUnknowns} />
                  <MiniList label="Prüfen" items={hypothesis.requiredChecks} />
                  {hypothesis.rfqRelevance ? (
                    <p className="mt-2 rounded-[10px] border border-[#E5E7EB] bg-white px-2.5 py-2 text-[12px] leading-relaxed text-[#374151]">
                      RFQ: {humanizeDisplayText(hypothesis.rfqRelevance)}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">Noch keine Prüfhypothesen ableitbar.</p>
          )}
        </div>
      </div>

      {challenge.actionModesRun.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {compactItems(challenge.actionModesRun.map(actionModeLabel), 8).map((mode) => (
            <span
              key={mode}
              className="rounded-full border border-[#E5E7EB] bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-[#041E49]"
            >
              {mode}
            </span>
          ))}
        </div>
      ) : null}

      <p className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-white/70 px-3 py-2 text-[12px] leading-relaxed text-[#4B5563]">
        {normalizeText(challenge.boundaryNotice) ||
          "Prüfhypothesen sind keine Freigabe und keine finale Auslegung."}
      </p>
    </section>
  );
}

function plausibilityLabel(plausibility: string) {
  switch (plausibility) {
    case "high":
      return "hoch";
    case "medium":
      return "mittel";
    case "low":
      return "niedrig";
    default:
      return normalizeText(plausibility) || "offen";
  }
}

function MaterialHypothesisSummary({ candidate }: { candidate: WorkspaceMaterialCandidate }) {
  return (
    <div className="mt-3 rounded-[14px] border border-[#D1D5DB] bg-white p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#041E49]">
            Prüfhypothese
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">
            {normalizeText(candidate.allowedClaim) || "Vorläufiger Prüfrahmen aus bekannten Parametern."}
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-3 py-1 text-[12px] font-bold uppercase tracking-[0.08em]",
            plausibilityTone(candidate.plausibility),
          )}
        >
          {plausibilityLabel(candidate.plausibility)}
        </span>
      </div>
      <p className="mt-3 text-[12px] leading-relaxed text-[#4B5563]">
        {normalizeText(candidate.rfqRelevance) ||
          "Nur als Kontext für die spätere Herstellerprüfung sichtbar, nicht als Vorgabe."}
      </p>
    </div>
  );
}

function designStatusLabel(status: string) {
  switch (status) {
    case "minimal_dataset_missing":
      return "Mindestdaten fehlen";
    case "preselection_ready_with_open_points":
      return "Vorprüfung mit offenen Punkten";
    case "design_review_ready_not_released":
      return "Prüfdatensatz vollständig";
    default:
      return "Noch kein Design-Datensatz";
  }
}

function screeningStatusLabel(status: string) {
  switch (status) {
    case "screening_ok":
      return "im Vorcheck unauffällig";
    case "warning":
      return "prüfen";
    case "low_review":
      return "zu niedrig prüfen";
    default:
      return humanizeDisplayText(status);
  }
}

export function DesignIntakePanel({ workspace }: { workspace: WorkspaceView | null }) {
  const intake = workspace?.designIntake;
  const hasContent = Boolean(
    intake &&
      intake.status !== "no_design_dataset" &&
      (intake.knownFields.length ||
        intake.missingFields.length ||
        intake.screeningChecks.length ||
        intake.escalationTriggers.length),
  );
  if (!hasContent || !intake) {
    return null;
  }

  const missingByKey = new Map(intake.missingFields.map((field) => [field.key, field]));
  const nextFields = intake.nextRequiredFields
    .map((key) => missingByKey.get(key)?.label || humanizeDisplayText(key))
    .filter(Boolean);
  const criticalMissing = intake.missingFields.filter((field) => field.criticality === "critical");
  const visibleKnown = intake.knownFields.slice(0, 4);
  const visibleMissing = criticalMissing.length ? criticalMissing.slice(0, 5) : intake.missingFields.slice(0, 5);

  return (
    <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <ClipboardList size={17} />
            Neuauslegung
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Mindestdaten, Vorchecks und Eskalationspunkte aus dem Backend. Nur als Anfragebasis für spätere Prüfung.
          </p>
        </div>
        <span className="inline-flex rounded-full border border-[#D1D5DB] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-[#041E49]">
          {designStatusLabel(intake.status)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Schon vorhanden</div>
          {visibleKnown.length ? (
            <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
              {visibleKnown.map((field) => (
                <li key={field.key}>
                  {field.label}: {normalizeText(field.value) || "angegeben"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Noch keine belastbare Angabe im Design-Datensatz.</p>
          )}
        </div>

        <div className="rounded-[14px] border border-[#FFF4E5] bg-[#FFF8ED] p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#9A3412]">Als Nächstes klären</div>
          {nextFields.length || visibleMissing.length ? (
            <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
              {(nextFields.length ? nextFields : visibleMissing.map((field) => field.label)).map((label) => (
                <li key={label}>{label}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Keine Pflichtlücke gemeldet.</p>
          )}
        </div>
      </div>

      {intake.screeningChecks.length || intake.escalationTriggers.length ? (
        <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
          <ItemList
            title="Vorchecks"
            empty="Noch keine Vorchecks möglich"
            items={intake.screeningChecks.map((check) => {
              const value = check.value !== null ? `${check.value}${check.unit ? ` ${check.unit}` : ""}` : null;
              return `${check.label}: ${value ? `${value} · ` : ""}${screeningStatusLabel(check.status)}`;
            })}
          />
          <ItemList
            title="Eskalationspunkte"
            empty="Keine Eskalationspunkte gemeldet"
            items={intake.escalationTriggers.map((trigger) => `${trigger.label}: ${trigger.reason}`)}
          />
        </div>
      ) : null}

      <p className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-[12px] leading-relaxed text-[#4B5563]">
        {normalizeText(intake.boundaryNotice) ||
          "Read-only Vorqualifikation; die technische Auslegung bleibt später zu prüfen."}
      </p>
    </section>
  );
}

function sourceStatusLine(workspace: WorkspaceView | null) {
  if (!workspace) {
    return "Herkunft noch offen";
  }
  const source = normalizeText(workspace.mediumContext.sourceType) || "Herkunft unklar";
  const status = workspace.mediumContext.notForReleaseDecisions
    ? "noch nicht geprüft"
    : normalizeText(workspace.mediumContext.validationStatus) || "Status unklar";
  return `${source} · ${status}`;
}

function v91OverallLabel(status: string | undefined): string {
  switch (status) {
    case "rfq_basis":
      return "Anfragebasis";
    case "review_needed":
      return "Prüfung nötig";
    case "screening":
      return "Screening";
    case "intake":
      return "Intake";
    default:
      return "Noch offen";
  }
}

export function V91IntelligencePanel({ workspace }: { workspace: WorkspaceView | null }) {
  const v91 = workspace?.v91Workspace;
  const intelligence = v91?.intelligenceState;
  if (!v91 || !intelligence) {
    return null;
  }

  const slices = [
    intelligence.medium,
    intelligence.material,
    intelligence.challenge,
    intelligence.document,
    intelligence.rfq,
  ];
  const nextAction =
    v91.tabState.find((tab) => tab.nextAction)?.nextAction ||
    workspace?.communication?.primaryQuestion ||
    null;

  return (
    <section className="rounded-[18px] border border-[#D1D5DB] bg-[#FFFFFF] p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#E5E7EB] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <ShieldCheck size={17} />
            Sealing Intelligence
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Backend-owned V9.1 Workspace-Projektion aus Medium, Werkstoff, Challenge, Dokumenten und Anfragebasis.
          </p>
        </div>
        <span className="inline-flex rounded-full border border-[#D1D5DB] bg-white/80 px-3 py-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-[#041E49]">
          {v91OverallLabel(intelligence.overallStatus)}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 xl:grid-cols-5">
        {slices.map((slice) => (
          <div key={slice.sliceId} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2.5">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">
              {humanizeDisplayText(slice.sliceId)}
            </div>
            <div className="mt-1 text-sm font-semibold leading-snug text-[#111827]">
              {humanizeDisplayText(slice.status)}
            </div>
            <p className="mt-1 line-clamp-3 text-[12px] leading-relaxed text-[#4B5563]">
              {slice.summary || "Noch keine Projektion."}
            </p>
            {slice.blockers.length ? (
              <div className="mt-2 rounded-full border border-[#FED7AA] bg-[#FFF7ED] px-2 py-1 text-[11px] font-bold text-[#9A3412]">
                {slice.blockers.length} offen
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {nextAction ? (
        <div className="mt-3 rounded-[14px] border border-[#D1D5DB] bg-white px-3 py-2 text-sm leading-relaxed text-[#374151]">
          <span className="font-semibold text-[#111827]">Nächster sinnvoller Schritt:</span>{" "}
          {humanizeDisplayText(nextAction)}
        </div>
      ) : null}
    </section>
  );
}

function researchStatusLabel(attempt: MediumIntelligenceData["research_status"]["rag"] | undefined, label: string) {
  if (!attempt) {
    return `${label}: noch nicht geprüft`;
  }
  if (!attempt.attempted) {
    if (attempt.status === "not_requested") {
      return `${label}: nur auf Wunsch`;
    }
    return `${label}: ${attempt.note || "nicht gestartet"}`;
  }
  if (attempt.status === "ok") {
    return `${label}: ${attempt.hit_count} Treffer${attempt.tier ? ` · ${attempt.tier}` : ""}`;
  }
  if (attempt.status === "no_hits") {
    return `${label}: keine Treffer`;
  }
  return `${label}: ${attempt.note || "nicht verfügbar"}`;
}

function evidenceStatusLabel(item: MediumEvidenceItem) {
  const source =
    item.source_type === "rag"
      ? "RAG"
      : item.source_type === "web"
        ? "Web"
        : "System";
  const status =
    item.validation_status === "documented"
      ? "dokumentiert"
      : item.validation_status === "web_retrieved"
        ? "live abgerufen"
        : item.validation_status === "system_derived"
          ? "systemseitig abgeleitet"
          : "nicht verfügbar";
  return `${source} · ${status}`;
}

function mediumAnswerSourceLabel(data: MediumIntelligenceData) {
  if (data.answer_markdown_source === "medium_composer" && data.composer?.succeeded) {
    return "LLM formuliert · quellengebunden";
  }
  if (data.answer_markdown_source === "composer_fallback") {
    return "Fallback · geprüfte Sektionen";
  }
  return "Deterministisch · geprüfte Sektionen";
}

function MediumDeepDive({
  data,
  loading,
  error,
  webResearchLoading,
  webResearchError,
  onRunWebResearch,
}: {
  data: MediumIntelligenceData | null;
  loading: boolean;
  error: string | null;
  webResearchLoading: boolean;
  webResearchError: string | null;
  onRunWebResearch: () => void;
}) {
  if (loading) {
    return (
      <section className="mt-4 rounded-[16px] border border-[#D1D5DB] bg-[#FFFFFF] p-4">
        <h3 className="text-sm font-semibold text-[#111827]">Medium-Deep-Dive</h3>
        <p className="mt-2 text-sm leading-relaxed text-[#4B5563]">
          SeaLAI prüft gerade den kuratierten Medium-Kontext und interne Wissensquellen.
        </p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="mt-4 rounded-[16px] border border-[#FDE2B8] bg-[#FFF4E5] p-4">
        <h3 className="text-sm font-semibold text-[#111827]">Medium-Deep-Dive</h3>
        <p className="mt-2 text-sm leading-relaxed text-[#9A3412]">{error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="mt-4 rounded-[16px] border border-[#E5E7EB] bg-[#FAFAFB] p-4">
        <h3 className="text-sm font-semibold text-[#111827]">Medium-Deep-Dive</h3>
        <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">
          Sobald ein Medium erkannt wurde, zeigt SeaLAI hier einen quellenmarkierten Deep-Dive.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-4 space-y-4 rounded-[16px] border border-[#E5E7EB] bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-[#111827]">Medium-Deep-Dive</h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Quellenmarkierte Orientierung zu {normalizeText(data.resolved_medium ?? data.medium) || "diesem Medium"}.
            Keine Werkstofffreigabe, keine Compliance-Aussage.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[12px] font-semibold">
          <span className="rounded-full border border-[#D1D5DB] bg-[#EFF6FF] px-3 py-1 text-[#041E49]">
            {researchStatusLabel(data.research_status.rag, "RAG")}
          </span>
          <span className="rounded-full border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-1 text-[#4B5563]">
            {researchStatusLabel(data.research_status.web, "Web")}
          </span>
          <button
            type="button"
            onClick={onRunWebResearch}
            disabled={webResearchLoading}
            className="inline-flex items-center gap-2 rounded-full border border-[#D1D5DB] bg-white px-3 py-1 text-[#041E49] shadow-sm transition-colors hover:bg-[#EFF6FF] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Search size={13} />
            {webResearchLoading
              ? "Websearch läuft"
              : data.research_status.web.status === "ok"
                ? "Websearch erneut starten"
                : "Websearch starten"}
          </button>
        </div>
      </div>

      {webResearchError ? (
        <div className="rounded-[12px] border border-[#FDE2B8] bg-[#FFF4E5] px-3 py-2 text-sm leading-relaxed text-[#9A3412]">
          {webResearchError}
        </div>
      ) : null}

      {data.answer_markdown ? (
        <div className="rounded-[14px] border border-[#D1D5DB] bg-[#FFFFFF] p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#041E49]">
              LLM-Deep-Dive
            </div>
            <span className="rounded-full border border-[#D1D5DB] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#041E49]">
              {mediumAnswerSourceLabel(data)}
            </span>
          </div>
          <div className="text-sm leading-relaxed text-[#111827]">
            <MarkdownRenderer variant="chat">{data.answer_markdown}</MarkdownRenderer>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {data.sections.map((section) => (
          <div key={section.id} className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
            <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{section.title}</div>
            <p className="mt-2 text-sm leading-relaxed text-[#111827]">{normalizeText(section.content)}</p>
            {section.bullets.length ? (
              <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#4B5563]">
                {section.bullets.slice(0, 8).map((bullet) => (
                  <li key={bullet}>{normalizeText(bullet)}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </div>

      <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Quellen & Nachweise</div>
        {data.evidence.length ? (
          <div className="mt-3 space-y-3">
            {data.evidence.map((item) => (
              <div key={item.id} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-[#111827]">{normalizeText(item.title)}</div>
                  <span className="rounded-full border border-[#E5E7EB] bg-[#FAFAFB] px-2.5 py-1 text-[11px] font-semibold text-[#4B5563]">
                    {evidenceStatusLabel(item)}
                  </span>
                </div>
                {item.source_name ? <p className="mt-1 text-[12px] text-[#6B7280]">{normalizeText(item.source_name)}</p> : null}
                <p className="mt-2 text-sm leading-relaxed text-[#4B5563]">{normalizeText(item.excerpt)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">
            Keine belastbare Quelle gefunden. SeaLAI zeigt dann keine erfundenen Medienaussagen.
          </p>
        )}
      </div>

      <div className="rounded-[14px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm leading-relaxed text-[#9A3412]">
        {data.limitations.map((limitation) => (
          <p key={limitation}>{normalizeText(limitation)}</p>
        ))}
      </div>
    </section>
  );
}

function MediumTab({ workspace }: { workspace: WorkspaceView | null }) {
  const mediumIntelligence = useWorkspaceStore((state) => state.mediumIntelligence);
  const mediumIntelligenceLoading = useWorkspaceStore((state) => state.mediumIntelligenceLoading);
  const mediumIntelligenceFor = useWorkspaceStore((state) => state.mediumIntelligenceFor);
  const setMediumIntelligence = useWorkspaceStore((state) => state.setMediumIntelligence);
  const setMediumIntelligenceLoading = useWorkspaceStore((state) => state.setMediumIntelligenceLoading);
  const setMediumIntelligenceFor = useWorkspaceStore((state) => state.setMediumIntelligenceFor);
  const setMediumIntelligenceResult = useWorkspaceStore((state) => state.setMediumIntelligenceResult);
  const [mediumIntelligenceError, setMediumIntelligenceError] = useState<string | null>(null);
  const [webResearchLoading, setWebResearchLoading] = useState(false);
  const [webResearchError, setWebResearchError] = useState<string | null>(null);
  const mediumLabel = normalizeText(
    workspace?.mediumContext.mediumLabel ??
      workspace?.parameters?.medium ??
      workspace?.mediumClassification.canonicalLabel,
  );

  useEffect(() => {
    if (!mediumLabel) {
      setMediumIntelligence(null);
      setMediumIntelligenceFor(null);
      return;
    }
    if (mediumIntelligenceFor === mediumLabel) {
      return;
    }

    const controller = new AbortController();
    setMediumIntelligenceLoading(true);

    fetch("/api/bff/medium-intelligence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ medium: mediumLabel, include_web_research: false }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Medium-Deep-Dive konnte nicht geladen werden.");
        }
        return (await response.json()) as MediumIntelligenceData;
      })
      .then((payload) => {
        setMediumIntelligenceError(null);
        setWebResearchError(null);
        setMediumIntelligenceResult(mediumLabel, payload);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setMediumIntelligence(null);
        setMediumIntelligenceFor(null);
        setMediumIntelligenceError(
          error instanceof Error ? error.message : "Medium-Deep-Dive konnte nicht geladen werden.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setMediumIntelligenceLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [
    mediumLabel,
    mediumIntelligenceFor,
    setMediumIntelligence,
    setMediumIntelligenceFor,
    setMediumIntelligenceLoading,
    setMediumIntelligenceResult,
  ]);

  const handleRunWebResearch = () => {
    if (!mediumLabel || webResearchLoading) {
      return;
    }
    setWebResearchLoading(true);
    setWebResearchError(null);

    fetch("/api/bff/medium-intelligence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ medium: mediumLabel, include_web_research: true }),
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Websearch konnte nicht geladen werden.");
        }
        return (await response.json()) as MediumIntelligenceData;
      })
      .then((payload) => {
        setMediumIntelligenceError(null);
        setWebResearchError(null);
        setMediumIntelligenceResult(mediumLabel, payload);
      })
      .catch((error: unknown) => {
        setWebResearchError(error instanceof Error ? error.message : "Websearch konnte nicht geladen werden.");
      })
      .finally(() => {
        setWebResearchLoading(false);
      });
  };

  return (
    <WorkspaceTabShell
      title="Medium"
      icon={Beaker}
      intro="Hier siehst du, welches Medium erkannt wurde, welche Risiken daran hängen und woher die Info kommt."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Erkanntes Medium" value={normalizeText(workspace?.mediumContext.mediumLabel ?? workspace?.parameters?.medium)} tone="info" />
        <InfoTile title="Woher kommt die Info?" value={sourceStatusLine(workspace)} tone={workspace?.mediumContext.notForReleaseDecisions ? "warning" : "neutral"} />
        <InfoTile title="Medienfamilie" value={normalizeText(workspace?.mediumClassification.family)} />
        <InfoTile title="Klassifizierung" value={normalizeText(workspace?.mediumClassification.status)} note={normalizeText(workspace?.mediumContext.disclaimer)} />
        <ItemList title="Eigenschaften" items={workspace?.mediumContext.properties ?? []} />
        <ItemList title="Risiken / Prüfpunkte" items={workspace?.mediumContext.challenges ?? []} />
        <ItemList title="Offen" items={[...(workspace?.mediumContext.followupPoints ?? []), ...(workspace?.completeness.coverageGaps ?? [])]} />
        <ItemList title="Nächste Frage" items={[workspace?.mediumClassification.followupQuestion, workspace?.communication?.primaryQuestion]} />
      </div>
      <MediumDeepDive
        data={mediumIntelligenceFor === mediumLabel ? mediumIntelligence : null}
        loading={mediumIntelligenceLoading}
        error={mediumLabel ? mediumIntelligenceError : null}
        webResearchLoading={webResearchLoading}
        webResearchError={webResearchError}
        onRunWebResearch={handleRunWebResearch}
      />
    </WorkspaceTabShell>
  );
}

function ApplicationTab({ workspace }: { workspace: WorkspaceView | null }) {
  const profile = workspace?.sealApplicationProfile;
  return (
    <WorkspaceTabShell
      title="Anwendung"
      icon={Factory}
      intro="Anlage, Einbauort und Bewegung helfen, den Fall richtig einzuordnen, bevor eine Anfrage vorbereitet wird."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Anlage / Einbauort" value={normalizeText(workspace?.parameters?.installation)} tone="info" />
        <InfoTile title="Dichtstelle / Geometrie" value={normalizeText(workspace?.parameters?.geometry_context)} />
        <InfoTile title="Bewegung" value={normalizeText(profile?.motionType ?? workspace?.parameters?.motion_type)} />
        <InfoTile title="Anwendungsdomäne" value={normalizeText(profile?.applicationDomain)} />
        <ItemList title="Bekannt" items={workspace?.decisionUnderstanding?.currentStateAnalysis.knownFields ?? workspace?.communication?.confirmedFactsSummary ?? []} />
        <ItemList title="Offen" items={workspace?.decisionUnderstanding?.currentStateAnalysis.missingFields ?? workspace?.completeness.missingCriticalParameters ?? []} />
        <ItemList title="Warum das wichtig ist" items={workspace?.decisionUnderstanding?.technicalMeaning ?? []} />
        <ItemList title="Was der Hersteller prüfen muss" items={workspace?.decisionUnderstanding?.manufacturerReviewNeeds ?? workspace?.manufacturerQuestions.mandatory ?? []} />
      </div>
    </WorkspaceTabShell>
  );
}

function MaterialTab({ workspace }: { workspace: WorkspaceView | null }) {
  const intelligence = workspace?.materialIntelligence;
  const input = intelligence?.inputSummary;
  const candidates = intelligence?.candidateMaterials ?? [];
  const alternatives = intelligence?.alternatives ?? [];
  const hasCandidates = candidates.length > 0;

  return (
    <WorkspaceTabShell
      title="Werkstoff"
      icon={Layers}
      intro="SealingAI entwickelt hier ein Werkstofffenster aus dem aktuellen Fallzustand. Die Entscheidung bleibt bis zur Herstellerprüfung offen."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Medium" value={normalizeText(input?.medium ?? workspace?.parameters?.medium)} tone="info" />
        <InfoTile title="Medienfamilie" value={normalizeText(input?.mediumFamily)} />
        <InfoTile title="Temperatur" value={input?.temperatureC != null ? `${input.temperatureC} °C` : null} />
        <InfoTile title="Druck" value={input?.pressureBar != null ? `${input.pressureBar} bar` : null} />
        <InfoTile title="Dichtprinzip" value={normalizeText(input?.sealType ?? workspace?.sealApplicationProfile?.sealType)} />
        <InfoTile title="Bekannter Werkstoff" value={normalizeText(input?.knownMaterial)} />
      </div>

      <div className="mt-4 rounded-[14px] border border-[#D1D5DB] bg-[#EFF6FF] p-3">
        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#041E49]">
          Werkstofffenster
        </div>
        <p className="mt-2 text-sm leading-relaxed text-[#1F3B63]">
          Kandidaten werden nur als Prüfrahmen gezeigt. SeaLAI setzt daraus keine Materialentscheidung,
          keinen Anfrage-Status und keine Auslegung.
        </p>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 2xl:grid-cols-2">
        {hasCandidates ? (
          candidates.map((candidate) => (
            <div key={candidate.materialKey || candidate.label} className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-base font-semibold text-[#111827]">{candidate.label}</h3>
                  <p className="mt-1 text-sm text-[#6B7280]">{candidate.family}</p>
                </div>
                <span className="rounded-full border border-[#D1D5DB] bg-white px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[#041E49]">
                  {normalizeText(candidate.statusLabel)}
                </span>
              </div>
              <MaterialHypothesisSummary candidate={candidate} />
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                <ItemList title="Stützende Signale" items={candidate.scoreDrivers} />
                <ItemList title="Prüfpunkte" items={candidate.scoreCautions} />
                <ItemList title="Warum im Fenster" items={candidate.whyConsidered} />
                <ItemList title="Grenzen" items={candidate.limits} />
                <ItemList title="Datenlücken" items={candidate.blockingUnknowns} empty="Keine weiteren Pflichtdaten aus diesem Fenster" />
                <ItemList title="Gegenindikatoren" items={candidate.counterindicators} />
                <ItemList title="Noch zu prüfen" items={candidate.requiredChecks} />
              </div>
            </div>
          ))
        ) : (
          <ItemList title="Werkstofffenster" items={[]} empty="Sobald Medium, Temperatur, Druck und Dichtprinzip vorliegen, zeigt SeaLAI hier Kandidaten und Alternativen." />
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <ItemList
          title="Alternativen"
          items={alternatives.map((item) => `${item.fromMaterial} ↔ ${item.toMaterial}: ${item.comparison}`)}
          empty="Noch keine Alternative belastbar einzugrenzen"
        />
        <ItemList
          title="Was noch fehlt"
          items={intelligence?.missingFieldHints ?? workspace?.completeness.coverageGaps ?? []}
        />
        <ItemList title="Anfragebasis" items={intelligence?.rfqRelevanceNotes ?? []} />
        <ItemList
          title="Quellenrahmen"
          items={(intelligence?.evidence ?? []).map((item) => `${item.title}: ${item.excerpt}`)}
          empty="Noch keine kuratierte Werkstoffgrundlage im Fall sichtbar"
        />
      </div>
    </WorkspaceTabShell>
  );
}

function CalculationTab({
  data,
  workspace,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
}) {
  return (
    <WorkspaceTabShell
      title="Berechnung"
      icon={Calculator}
      intro="SeaLAI zeigt einfache Rechenchecks nur dann, wenn genug Angaben vorhanden sind. Fehlende Eingaben bleiben sichtbar."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {data.calculations.map((metric) => (
          <InfoTile key={metric.label} title={metric.label} value={metric.value} note={compactItems([metric.limit, metric.reserve]).join(" · ")} tone={metric.value === "Noch nicht möglich" ? "warning" : "info"} />
        ))}
        <ItemList title="Hinweise aus dem System" items={workspace?.technicalDerivations?.flatMap((item) => item.notes) ?? []} />
        <ItemList title="Berechnete Hinweise" items={workspace?.evidence.deterministicFindings ?? []} />
      </div>
    </WorkspaceTabShell>
  );
}


function RfqQualificationTab({
  data,
  workspace,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
}) {
  return (
    <WorkspaceTabShell
      title="Anfragebasis"
      icon={FileText}
      intro="RFQ-Readiness, offene Punkte und Vorschau für die spätere Herstellerprüfung. Hier wird nichts automatisch versendet."
    >
      <div className="mt-4">
        <RfqPane data={data} caseId={workspace?.caseId} workspace={workspace} />
      </div>
    </WorkspaceTabShell>
  );
}

function BriefingTab({
  data,
  workspace,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
}) {
  const decision = workspace?.decisionUnderstanding;
  return (
    <WorkspaceTabShell
      title="Briefing"
      icon={FileText}
      intro="Kurze Zusammenfassung für interne Klärung und eine spätere Anfragevorschau. Hier wird nichts versendet."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Fallzusammenfassung" value={normalizeText(decision?.caseSummary) || data.solution.assessment} tone="info" />
        <InfoTile title="Anfrage-Status" value={normalizeText(workspace?.rfq.status)} note={normalizeText(workspace?.rfq.releaseStatus)} />
        <ItemList title="Bekannt" items={decision?.understoodNow ?? workspace?.communication?.confirmedFactsSummary ?? []} />
        <ItemList title="Offen" items={[...(workspace?.rfq.openPoints ?? []), ...(workspace?.completeness.missingCriticalParameters ?? [])]} />
        <ItemList title="Was zu prüfen ist" items={decision?.manufacturerReviewNeeds ?? workspace?.manufacturerQuestions.mandatory ?? []} />
        <ItemList title="Nächste sinnvolle Frage" items={[decision?.nextBestQuestion, workspace?.communication?.primaryQuestion]} />
        <ItemList title="Grenzen" items={[...(workspace?.governance.requiredDisclaimers ?? []), "Der Hersteller muss die Auslegung später prüfen."]} />
        <ItemList title="Blocker" items={[...(workspace?.rfq.blockers ?? []), ...(workspace?.matching.blockingReasons ?? [])]} empty="Keine Blocker gemeldet" />
      </div>
      <div className="mt-4">
        <RfqPane data={data} caseId={workspace?.caseId} workspace={workspace} />
      </div>
    </WorkspaceTabShell>
  );
}

export function SealCockpit({
  data,
  workspace,
  isParameterSubmitting = false,
  onParameterSubmit,
  preferredTab,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
  isParameterSubmitting?: boolean;
  onParameterSubmit?: (overrides: AgentOverrideItemRequest[], summary: string) => Promise<void> | void;
  preferredTab?: CockpitTabId | null;
}) {
  const [activeTab, setActiveTab] = useState<CockpitTabId>(preferredTab ?? "overview");

  return (
    <aside className="flex min-h-0 min-w-0 flex-col overflow-visible rounded-[20px] border border-transparent bg-transparent">
      <ParameterQuickEntry
        key={[
          workspace?.caseId ?? "new-case",
          workspace?.engineeringPath ?? "no-path",
          workspace?.sealApplicationProfile?.sealFamily ?? "no-family",
          workspace?.sealApplicationProfile?.sealType ?? "no-type",
        ].join(":")}
        workspace={workspace}
        isSubmitting={isParameterSubmitting}
        onSubmit={onParameterSubmit ?? (async () => {})}
      />
      <CockpitTabs tabs={data.tabs} activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="min-h-0 overflow-visible pb-4">
        {activeTab === "overview" ? (
          <>
            <CockpitStatusStrip items={data.statusStrip} />
            <div className="px-4 pt-4">
              <V91IntelligencePanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <DecisionUnderstandingPanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <ChallengeIntelligencePanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <DesignIntakePanel workspace={workspace} />
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
        ) : activeTab === "parameters" ? (
          <ParameterWorkspaceTab
            key={workspace?.caseId ?? "new-parameter-case"}
            workspace={workspace}
            isSubmitting={isParameterSubmitting}
            onSubmit={onParameterSubmit ?? (async () => {})}
          />
        ) : activeTab === "rfq" ? (
          <RfqQualificationTab data={data} workspace={workspace} />
        ) : activeTab === "medium" ? (
          <MediumTab workspace={workspace} />
        ) : activeTab === "application" ? (
          <ApplicationTab workspace={workspace} />
        ) : activeTab === "material" ? (
          <MaterialTab workspace={workspace} />
        ) : activeTab === "calculation" ? (
          <CalculationTab data={data} workspace={workspace} />
        ) : (
          <BriefingTab data={data} workspace={workspace} />
        )}
      </div>
    </aside>
  );
}
