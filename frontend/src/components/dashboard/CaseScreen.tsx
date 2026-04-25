"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BookOpen,
  Calculator,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Columns,
  Database,
  FlaskConical,
  ListChecks,
  Search,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import ChatPane from "@/components/dashboard/ChatPane";
import { StatusBadge } from "@/components/dashboard/CockpitElements";
import { useCockpitData } from "@/hooks/useCockpitData";
import { useWorkspace } from "@/hooks/useWorkspace";
import {
  DEFAULT_PATH_RULES,
  PATH_RULES,
  type EngineeringPath,
  type EngineeringProperty,
} from "@/lib/engineering/cockpitModel";
import type { WorkspaceDeepDiveTab } from "@/lib/contracts/workspace";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { cn } from "@/lib/utils";

interface CaseScreenProps {
  caseId?: string;
  initialRequestType?: string;
}

type TimelineStep = {
  label: string;
  status: "done" | "active" | "pending";
};

type ContextItem = {
  label: string;
  value: string;
};

type ParameterStatus = "confirmed" | "inferred" | "missing" | "optional";

type ParameterTabId = "rotary" | "rwdr" | "hydraulic" | "static" | "other";

type ParameterFieldDescriptor = {
  key: string;
  label: string;
};

type ParameterFieldViewModel = {
  key: string;
  label: string;
  value: unknown;
  unit?: string;
  status: ParameterStatus;
};

type CalculationStatus = "current" | "stale" | "blocked";

type CalculationViewModel = {
  key: string;
  label: string;
  value: string;
  status: CalculationStatus;
  detail: string;
};

type OpenPointItem = {
  key: string;
  label: string;
  severity: "critical" | "attention" | "info";
};

type WorkspaceMode = "analysis" | "medium" | "material" | "seal_type";

type CompareColumn = {
  label: string;
  value: string;
};

type CompareTableRow = {
  criterion: string;
  values: string[];
};

type CompareCardData = {
  columns: CompareColumn[];
  rows: CompareTableRow[];
  conclusion: string | null;
  criteria: string[];
  sources: string[];
};

type DeepDiveCardData = {
  profileTitle: string | null;
  profileSummary: string | null;
  properties: string[];
  applicationsAndLimits: string[];
  notesAndSources: string[];
};

const WORKSPACE_MODE_OPTIONS: Array<{ id: WorkspaceMode; label: string }> = [
  { id: "analysis", label: "Analyse" },
  { id: "medium", label: "Medium" },
  { id: "material", label: "Werkstoff" },
  { id: "seal_type", label: "Dichtungstyp" },
];

const CORE_PARAMETER_FIELDS: ParameterFieldDescriptor[] = [
  { key: "medium", label: "Medium" },
  { key: "temperature_c", label: "Temperatur" },
  { key: "pressure_bar", label: "Druck" },
  { key: "motion_type", label: "Bewegung" },
  { key: "installation", label: "Anwendung / Maschine" },
  { key: "shaft_diameter_mm", label: "Referenz-Ø" },
  { key: "speed_rpm", label: "Drehzahl" },
];


const COCKPIT_PROPERTY_ALIASES: Record<string, string[]> = {
  medium: ["medium_name"],
  temperature_c: ["temperature_max"],
  pressure_bar: ["pressure_nominal"],
  shaft_diameter_mm: ["shaft_diameter"],
  geometry_context: ["seal_location"],
  installation: ["asset_type"],
  pressure_direction: ["primary_function"],
  contamination: ["particles_present", "top_risks"],
};

const PARAMETER_TABS: Array<{ id: ParameterTabId; label: string }> = [
  { id: "rotary", label: "Rotierend" },
  { id: "rwdr", label: "RWDR" },
  { id: "hydraulic", label: "Hydraulik" },
  { id: "static", label: "Flachdichtung" },
  { id: "other", label: "Sonstige" },
];

const TAB_FIELD_MAP: Record<ParameterTabId, ParameterFieldDescriptor[]> = {
  rotary: [
    { key: "shaft_diameter_mm", label: "Referenz-Ø" },
    { key: "speed_rpm", label: "Drehzahl" },
    { key: "runout_mm", label: "Rundlauf" },
    { key: "vibration_rms", label: "Vibration RMS" },
  ],
  rwdr: [
    { key: "shaft_material", label: "Wellenwerkstoff" },
    { key: "shaft_hardness", label: "Wellenhärte" },
    { key: "counterface_surface", label: "Gegenlaufoberflaeche" },
    { key: "tolerances", label: "Toleranzen" },
  ],
  hydraulic: [
    { key: "pressure_direction", label: "Druckrichtung" },
    { key: "geometry_context", label: "Bauraum" },
    { key: "allowable_leakage", label: "Zulaessige Leckage" },
    { key: "life_hours", label: "Lebensdauer" },
  ],
  static: [
    { key: "geometry_context", label: "Bauraum" },
    { key: "compliance", label: "Konformitaet" },
    { key: "allowable_leakage", label: "Zulaessige Leckage" },
    { key: "life_hours", label: "Lebensdauer" },
  ],
  other: [
    { key: "viscosity", label: "Viskositaet" },
    { key: "solids_percent", label: "Feststoffe" },
    { key: "ph", label: "pH-Wert" },
    { key: "dry_run_possible", label: "Trockenlauf moeglich" },
  ],
};

function humanize(value: string | null | undefined) {
  if (!value) return "Noch offen";
  return value.replace(/_/g, " ");
}

function titleCase(value: string | null | undefined) {
  const normalized = humanize(value);
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function compactValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "Noch offen";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

function hasValue(value: unknown) {
  return !(value === null || value === undefined || value === "");
}

function buildPropertyLookup(cockpit: ReturnType<typeof useCockpitData>) {
  const lookup = new Map<string, EngineeringProperty>();
  if (!cockpit) {
    return lookup;
  }

  Object.values(cockpit.view.sections).forEach((section) => {
    section.properties.forEach((property) => {
      if (!lookup.has(property.key)) {
        lookup.set(property.key, property);
      }
    });
  });

  Object.entries(COCKPIT_PROPERTY_ALIASES).forEach(([canonicalKey, aliases]) => {
    if (lookup.has(canonicalKey)) {
      return;
    }
    const aliasedProperty = aliases.map((alias) => lookup.get(alias)).find(Boolean);
    if (aliasedProperty) {
      lookup.set(canonicalKey, {
        ...aliasedProperty,
        key: canonicalKey,
      });
    }
  });

  return lookup;
}

function fieldLabel(descriptor: ParameterFieldDescriptor, property?: EngineeringProperty) {
  return property?.label || descriptor.label;
}

function deriveRequiredKeys(path: EngineeringPath | null, propertyLookup: Map<string, EngineeringProperty>) {
  const required = new Set<string>((path ? PATH_RULES[path] : DEFAULT_PATH_RULES).mandatory);
  propertyLookup.forEach((property) => {
    if (property.isMandatory) {
      required.add(property.key);
    }
  });
  return required;
}

function deriveParameterStatus({
  property,
  value,
  required,
}: {
  property?: EngineeringProperty;
  value: unknown;
  required: boolean;
}): ParameterStatus {
  if (!hasValue(value)) {
    return required ? "missing" : "optional";
  }

  if (
    property?.isConfirmed ||
    property?.confidence === "confirmed" ||
    property?.confidence === "user_override"
  ) {
    return "confirmed";
  }

  return "inferred";
}

function statusVariant(status: ParameterStatus): "default" | "warning" | "error" | "success" | "info" {
  switch (status) {
    case "confirmed":
      return "success";
    case "inferred":
      return "info";
    case "missing":
      return "error";
    case "optional":
      return "default";
  }
}

function getInitialParameterTab(path: EngineeringPath | null): ParameterTabId {
  switch (path) {
    case "rwdr":
      return "rwdr";
    case "hyd_pneu":
      return "hydraulic";
    case "static":
      return "static";
    case "ms_pump":
    case "labyrinth":
    case "unclear_rotary":
      return "rotary";
    default:
      return "other";
  }
}

function createFieldViewModels({
  descriptors,
  cockpit,
  propertyLookup,
  requiredKeys,
}: {
  descriptors: ParameterFieldDescriptor[];
  cockpit: ReturnType<typeof useCockpitData>;
  propertyLookup: Map<string, EngineeringProperty>;
  requiredKeys: Set<string>;
}) {
  return descriptors.map((descriptor) => {
    const property = propertyLookup.get(descriptor.key);
    const value = property?.value ?? cockpit?.parameters?.[descriptor.key] ?? null;
    return {
      key: descriptor.key,
      label: fieldLabel(descriptor, property),
      value,
      unit: property?.unit,
      status: deriveParameterStatus({
        property,
        value,
        required: requiredKeys.has(descriptor.key),
      }),
    } satisfies ParameterFieldViewModel;
  });
}

function ParameterFieldRow({ field }: { field: ParameterFieldViewModel }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-sm font-medium text-[#111827]">{field.label}</div>
        <div className="mt-1 text-sm text-[#4B5563]">
          {compactValue(field.value)}
          {field.unit && hasValue(field.value) ? ` ${field.unit}` : ""}
        </div>
      </div>
      <StatusBadge label={field.status} variant={statusVariant(field.status)} />
    </div>
  );
}

function statusToneClass(severity: OpenPointItem["severity"]) {
  switch (severity) {
    case "critical":
      return "border-[#FDECEC] bg-[#FDECEC] text-[#991B1B]";
    case "attention":
      return "border-[#FFF4E5] bg-[#FFF4E5] text-[#9A3412]";
    case "info":
      return "border-[#E5E7EB] bg-white text-[#4B5563]";
  }
}

function calculationStatusVariant(status: CalculationStatus): "default" | "warning" | "error" | "success" | "info" {
  switch (status) {
    case "current":
      return "success";
    case "stale":
      return "warning";
    case "blocked":
      return "default";
  }
}

function buildCalculationItems({
  cockpit,
  workspace,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
}) {
  const stale = Boolean(workspace?.summary?.derivedArtifactsStale);
  const fromChecks: CalculationViewModel[] =
    cockpit?.view.checks.map((check) => {
      const hasCheckValue = check.value !== null && check.value !== undefined && check.value !== "";
      const status: CalculationStatus = stale ? "stale" : hasCheckValue ? "current" : "blocked";
      const detail = stale
        ? workspace?.summary?.staleReason || "Kennwert muss nach upstream Aenderung neu bestaetigt werden."
        : check.missingInputs.length > 0
          ? `Fehlende Inputs: ${check.missingInputs.join(", ")}`
          : humanize(check.status);

      return {
        key: check.calcId,
        label: check.label,
        value: hasCheckValue ? `${check.value}${check.unit ? ` ${check.unit}` : ""}` : "Nicht verfuegbar",
        status,
        detail,
      } satisfies CalculationViewModel;
    }) ?? [];

  if (fromChecks.length > 0) {
    return fromChecks;
  }

  return (
    workspace?.technicalDerivations?.flatMap((item) => {
      const candidates: Array<{ key: string; label: string; value: number | null }> = [
        { key: `${item.calcType}-v`, label: "Umlaufgeschwindigkeit", value: item.vSurfaceMPerS },
        { key: `${item.calcType}-pv`, label: "PV-Wert", value: item.pvValueMpaMPerS },
        { key: `${item.calcType}-dn`, label: "DN-Wert", value: item.dnValue },
      ];

      return candidates.map((candidate) => {
        const status: CalculationStatus = stale ? "stale" : candidate.value !== null ? "current" : "blocked";
        return {
          key: candidate.key,
          label: candidate.label,
          value: candidate.value !== null ? String(candidate.value) : "Nicht verfuegbar",
          status,
          detail: stale
            ? workspace?.summary?.staleReason || "Kennwert muss neu bestaetigt werden."
            : item.status ? humanize(item.status) : "Aus technischer Ableitung",
        } satisfies CalculationViewModel;
      });
    }) ?? []
  );
}

function buildOpenPoints({
  cockpit,
  workspace,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
}) {
  const items = new Map<string, OpenPointItem>();

  (cockpit?.view.readiness.missingMandatoryKeys ?? []).forEach((key) => {
    items.set(`missing-${key}`, {
      key: `missing-${key}`,
      label: humanize(key),
      severity: "critical",
    });
  });

  (cockpit?.view.readiness.blockers ?? []).forEach((blocker) => {
    items.set(`blocker-${blocker}`, {
      key: `blocker-${blocker}`,
      label: humanize(blocker),
      severity: "attention",
    });
  });

  (workspace?.communication?.openPointsSummary ?? []).forEach((item) => {
    items.set(`summary-${item}`, {
      key: `summary-${item}`,
      label: item,
      severity: "info",
    });
  });

  (workspace?.mediumContext?.followupPoints ?? []).forEach((item) => {
    items.set(`medium-${item}`, {
      key: `medium-${item}`,
      label: item,
      severity: "info",
    });
  });

  return Array.from(items.values());
}

function dedupeTextItems(items: Array<string | null | undefined>) {
  const seen = new Set<string>();
  const result: string[] = [];

  items.forEach((item) => {
    const normalized = typeof item === "string" ? item.trim() : "";
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    result.push(normalized);
  });

  return result;
}

function deriveDefaultWorkspaceMode({
  workspace: _workspace,
  activeResponseClass: _activeResponseClass,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  activeResponseClass: string | null;
}): WorkspaceMode {
  return "analysis";
}

function buildCompareCardData({
  workspace,
  cockpit,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  cockpit: ReturnType<typeof useCockpitData>;
}): CompareCardData | null {
  const items = workspace?.matching.items.slice(0, 3) ?? [];
  if (items.length === 0) {
    return null;
  }

  const columns = items.map((item) => ({
    label: item.material,
    value: `${humanize(item.cluster)} / ${humanize(item.specificity)}`,
  }));

  const rows: CompareTableRow[] = [
    {
      criterion: "Fit basis",
      values: items.map((item) => item.fitBasis || "Noch offen"),
    },
    {
      criterion: "Specificity",
      values: items.map((item) => humanize(item.specificity)),
    },
    {
      criterion: "Validation",
      values: items.map((item) => (item.requiresValidation ? "Manufacturer validation" : "No extra validation flagged")),
    },
    {
      criterion: "Grounded facts",
      values: items.map((item) => `${item.groundedFacts.length}`),
    },
  ];

  return {
    columns,
    rows,
    conclusion:
      items[0]?.fitBasis ||
      workspace?.governance.notes[0] ||
      cockpit?.mediumStatus.summary ||
      null,
    criteria: dedupeTextItems([
      workspace?.specificity.materialSpecificityRequired,
      ...(workspace?.mediumContext.properties?.slice(0, 2) ?? []),
      ...(workspace?.manufacturerQuestions.mandatory?.slice(0, 2) ?? []),
    ]),
    sources: dedupeTextItems(
      items.flatMap((item) =>
        item.groundedFacts.map((fact) => `${fact.source}: ${fact.name}`),
      ),
    ).slice(0, 5),
  };
}

function buildDeepDiveCardData({
  workspace,
  cockpit,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  cockpit: ReturnType<typeof useCockpitData>;
}): DeepDiveCardData | null {
  const profileTitle =
    workspace?.mediumClassification.canonicalLabel ||
    cockpit?.mediumStatus.label ||
    workspace?.matching.items[0]?.material ||
    null;

  const profileSummary =
    workspace?.mediumContext.summary ||
    cockpit?.mediumStatus.summary ||
    workspace?.matching.items[0]?.fitBasis ||
    null;

  const properties = dedupeTextItems([
    ...workspace?.mediumContext.properties ?? [],
    ...cockpit?.view.mediumContext.properties ?? [],
  ]).slice(0, 6);

  const applicationsAndLimits = dedupeTextItems([
    workspace?.parameters?.installation ? `Anwendung: ${workspace.parameters.installation}` : null,
    workspace?.engineeringPath ? `Pfad: ${humanize(workspace.engineeringPath)}` : null,
    ...(workspace?.mediumContext.challenges?.slice(0, 3) ?? []),
    ...(workspace?.governance.unknownsBlocking?.slice(0, 2) ?? []),
  ]).slice(0, 6);

  const notesAndSources = dedupeTextItems([
    workspace?.mediumContext.sourceType ? `Source type: ${workspace.mediumContext.sourceType}` : null,
    workspace?.mediumContext.disclaimer,
    ...(workspace?.evidence.sourceBackedFindings?.slice(0, 2) ?? []),
    ...(workspace?.evidence.deterministicFindings?.slice(0, 2) ?? []),
  ]).slice(0, 6);

  if (!profileTitle && !profileSummary && properties.length === 0 && applicationsAndLimits.length === 0 && notesAndSources.length === 0) {
    return null;
  }

  return {
    profileTitle,
    profileSummary,
    properties,
    applicationsAndLimits,
    notesAndSources,
  };
}

function WorkspaceStateMessage({
  title,
  tone = "neutral",
}: {
  title: string;
  tone?: "neutral" | "warning";
}) {
  return (
    <div
      className={cn(
        "rounded-[12px] border px-3 py-3 text-sm",
        tone === "warning"
          ? "border-[#FFF4E5] bg-[#FFF4E5] text-[#9A3412]"
          : "border-dashed border-[#D1D5DB] bg-white text-[#6B7280]",
      )}
    >
      {title}
    </div>
  );
}

function ParameterApplicationCard({
  cockpit,
  workspaceHasAuthoritativeCockpit,
  displayRequestType,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspaceHasAuthoritativeCockpit: boolean;
  displayRequestType: string;
}) {
  const propertyLookup = useMemo(() => buildPropertyLookup(cockpit), [cockpit]);
  const path = cockpit?.view.path ?? null;
  const requiredKeys = useMemo(() => deriveRequiredKeys(path, propertyLookup), [path, propertyLookup]);
  const [tabOverride, setTabOverride] = useState<ParameterTabId | null>(null);
  const initialTab = getInitialParameterTab(path);
  const activeTab = tabOverride ?? initialTab;

  const applicationProperty =
    propertyLookup.get("installation") ??
    propertyLookup.get("geometry_context");
  const applicationValue =
    applicationProperty?.value ??
    cockpit?.parameters?.installation ??
    cockpit?.parameters?.geometry_context ??
    null;
  const pathStatusLabel = path
    ? workspaceHasAuthoritativeCockpit && path !== "unclear_rotary"
      ? "confirmed"
      : "proposed"
    : "offen";

  const coreFields = useMemo(
    () =>
      createFieldViewModels({
        descriptors: CORE_PARAMETER_FIELDS,
        cockpit,
        propertyLookup,
        requiredKeys,
      }),
    [cockpit, propertyLookup, requiredKeys],
  );

  const pathSpecificFields = useMemo(
    () =>
      createFieldViewModels({
        descriptors: TAB_FIELD_MAP[activeTab],
        cockpit,
        propertyLookup,
        requiredKeys,
      }),
    [activeTab, cockpit, propertyLookup, requiredKeys],
  );

  const tabOrder = PARAMETER_TABS.map((tab) => tab.id);

  const onTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, currentTab: ParameterTabId) => {
    const currentIndex = tabOrder.indexOf(currentTab);
    let nextTab: ParameterTabId | null = null;

    if (event.key === "ArrowRight") {
      nextTab = tabOrder[(currentIndex + 1) % tabOrder.length];
    } else if (event.key === "ArrowLeft") {
      nextTab = tabOrder[(currentIndex - 1 + tabOrder.length) % tabOrder.length];
    } else if (event.key === "Home") {
      nextTab = tabOrder[0];
    } else if (event.key === "End") {
      nextTab = tabOrder[tabOrder.length - 1];
    }

    if (!nextTab) {
      return;
    }

    event.preventDefault();
    setTabOverride(nextTab);
    document.getElementById(`parameter-tab-${nextTab}`)?.focus();
  };

  return (
    <WorkspaceCard title="Parameter & Application" eyebrow="Slot 1" icon={CircleDot}>
      <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">
              Aktiver technischer Pfad
            </div>
            <div className="mt-1 text-lg font-semibold tracking-tight text-[#111827]">
              {titleCase(path)}
            </div>
            <div className="mt-2 text-sm text-[#4B5563]">
              {hasValue(applicationValue)
                ? compactValue(applicationValue)
                : "Anwendung oder Maschine noch nicht belastbar erkannt"}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge label={pathStatusLabel} variant={pathStatusLabel === "confirmed" ? "success" : "warning"} />
            <StatusBadge label={titleCase(displayRequestType)} variant="default" />
          </div>
        </div>
      </div>

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
          Kernparameter
        </div>
        <div className="grid gap-2">
          {coreFields.map((field) => (
            <ParameterFieldRow key={field.key} field={field} />
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
            Pfadspezifische Zusatzparameter
          </div>
          <div className="text-xs text-[#6B7280]">Tab-Wechsel ist reine UI-Navigation</div>
        </div>

        <div
          role="tablist"
          aria-label="Path-spezifische Parameter"
          className="custom-scrollbar flex gap-2 overflow-x-auto pb-2"
        >
          {PARAMETER_TABS.map((tab) => {
            const isActive = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                id={`parameter-tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`parameter-panel-${tab.id}`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => setTabOverride(tab.id)}
                onKeyDown={(event) => onTabKeyDown(event, tab.id)}
                className={cn(
                  "rounded-[14px] border px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "border-[#0B57D0] bg-[#0B57D0] text-white"
                    : "border-[#E5E7EB] bg-[#FAFAFB] text-[#4B5563] hover:bg-[#F0F2F5] hover:text-[#111827]",
                )}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div
          id={`parameter-panel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`parameter-tab-${activeTab}`}
          className="mt-2 space-y-2 rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-[#111827]">
              {PARAMETER_TABS.find((tab) => tab.id === activeTab)?.label}
            </div>
            <StatusBadge
              label={activeTab === initialTab ? "active path" : "ui view"}
              variant={activeTab === initialTab ? "info" : "default"}
            />
          </div>

          {pathSpecificFields.some((field) => hasValue(field.value) || field.status === "missing") ? (
            pathSpecificFields.map((field) => <ParameterFieldRow key={field.key} field={field} />)
          ) : (
            <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-white px-3 py-3 text-sm text-[#6B7280]">
              Fuer diesen Tab liegen aktuell keine belastbaren Zusatzparameter vor.
            </div>
          )}
        </div>
      </div>
    </WorkspaceCard>
  );
}

function MediumIntelligenceCard({
  cockpit,
  workspace,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
}) {
  const mediumState = cockpit?.mediumStatus;
  const followupPoints = workspace?.mediumContext?.followupPoints?.slice(0, 3) ?? [];
  const hasMedium =
    Boolean(mediumState?.label) ||
    Boolean(mediumState?.rawMention) ||
    mediumState?.status !== "unavailable";

  return (
    <WorkspaceCard title="Medium Intelligence" eyebrow="Slot 2" icon={Activity}>
      {!cockpit ? (
        <WorkspaceStateMessage title="Warte auf Medium-Projektion aus dem Workspace." />
      ) : !hasMedium ? (
        <WorkspaceStateMessage title="Noch kein belastbarer Medium-Kontext vorhanden. Fuer die weitere Einordnung wird zuerst das Medium benoetigt." />
      ) : (
        <>
          <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                  Erkanntes Medium
                </div>
                <div className="mt-1 text-base font-semibold text-[#111827]">
                  {mediumState?.label || mediumState?.rawMention || "Noch offen"}
                </div>
              </div>
              <StatusBadge
                label={mediumState?.statusLabel || "offen"}
                variant={
                  mediumState?.tone === "success"
                    ? "success"
                    : mediumState?.tone === "warning"
                      ? "warning"
                      : "default"
                }
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {mediumState?.confidence && (
                <StatusBadge label={`Confidence ${mediumState.confidence}`} variant="info" />
              )}
              {mediumState?.family && <StatusBadge label={mediumState.family} variant="default" />}
            </div>
          </div>

          <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
              Einordnung
            </div>
            <p className="mt-2 text-sm text-[#4B5563]">
              {workspace?.mediumContext?.summary || mediumState?.summary || "Kein Medium-Summary verfuegbar."}
            </p>
          </div>

          {(cockpit.view.mediumContext.properties.length > 0 || cockpit.view.mediumContext.riskFlags.length > 0) && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                  Relevante Eigenschaften
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {cockpit.view.mediumContext.properties.slice(0, 4).map((property) => (
                    <span
                      key={property}
                      className="rounded-full border border-[#E5E7EB] bg-[#EFF6FF] px-2.5 py-1 text-xs font-medium text-[#2563EB]"
                    >
                      {property}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                  Medium-Hinweise
                </div>
                <div className="mt-2 space-y-2">
                  {cockpit.view.mediumContext.riskFlags.slice(0, 3).map((item) => (
                    <div
                      key={item}
                      className="rounded-[10px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm text-[#9A3412]"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
              Offene Medium-Fragen
            </div>
            {followupPoints.length > 0 || mediumState?.nextStepHint ? (
              <div className="mt-2 space-y-2">
                {followupPoints.map((item) => (
                  <div key={item} className="rounded-[10px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-sm text-[#4B5563]">
                    {item}
                  </div>
                ))}
                {followupPoints.length === 0 && mediumState?.nextStepHint && (
                  <div className="rounded-[10px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-sm text-[#4B5563]">
                    {mediumState.nextStepHint}
                  </div>
                )}
              </div>
            ) : (
              <WorkspaceStateMessage title="Aktuell keine separaten Medium-Rueckfragen projiziert." />
            )}
          </div>
        </>
      )}
    </WorkspaceCard>
  );
}

function CalculationsCard({
  cockpit,
  workspace,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
}) {
  const items = buildCalculationItems({ cockpit, workspace }).slice(0, 4);
  const stale = Boolean(workspace?.summary?.derivedArtifactsStale);

  return (
    <WorkspaceCard title="Calculations" eyebrow="Slot 3" icon={Calculator}>
      {!cockpit ? (
        <WorkspaceStateMessage title="Warte auf Berechnungsprojektion aus dem Workspace." />
      ) : items.length === 0 ? (
        <WorkspaceStateMessage title="Noch keine backend-seitig projizierten Kennwerte verfuegbar." />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <StatusBadge label={stale ? "stale" : "current view"} variant={stale ? "warning" : "info"} />
            {workspace?.summary?.staleReason && <StatusBadge label="input changed" variant="default" />}
          </div>

          <div className="grid gap-3">
            {items.map((item) => (
              <div key={item.key} className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-[#111827]">{item.label}</div>
                    <div className="mt-1 text-lg font-semibold text-[#111827]">{item.value}</div>
                  </div>
                  <StatusBadge label={item.status} variant={calculationStatusVariant(item.status)} />
                </div>
                <div className="mt-2 text-sm text-[#4B5563]">{item.detail}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </WorkspaceCard>
  );
}

function OpenPointsCard({
  cockpit,
  workspace,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
}) {
  const openPoints = buildOpenPoints({ cockpit, workspace }).slice(0, 6);
  const nextStep =
    workspace?.communication?.primaryQuestion ||
    cockpit?.mediumStatus.nextStepHint ||
    (cockpit?.view.readiness.isRfqReady
      ? "Technische Klaerung ist ausreichend weit fuer den naechsten Freigabeschritt."
      : "Als Naechstes die priorisierten fehlenden Angaben vervollstaendigen.");

  return (
    <WorkspaceCard title="Open Points / Next Step" eyebrow="Slot 4" icon={AlertCircle}>
      {!cockpit ? (
        <WorkspaceStateMessage title="Warte auf Open-Points-Projektion aus dem Workspace." />
      ) : openPoints.length === 0 ? (
        <WorkspaceStateMessage
          title="Aktuell keine priorisierten offenen Punkte projiziert."
          tone={cockpit.view.readiness.isRfqReady ? "neutral" : "warning"}
        />
      ) : (
        <div className="space-y-2">
          {openPoints.map((item) => (
            <div
              key={item.key}
              className={cn("flex items-center gap-2 rounded-[12px] border px-3 py-2 text-sm", statusToneClass(item.severity))}
            >
              <AlertCircle size={15} />
              {item.label}
            </div>
          ))}
        </div>
      )}

      <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
          <ArrowRight size={14} />
          Naechster sinnvoller Schritt
        </div>
        <p className="mt-2 text-sm text-[#111827]">{nextStep}</p>
      </div>
    </WorkspaceCard>
  );
}

function KnowledgeCompareMode({
  workspace,
  cockpit,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  cockpit: ReturnType<typeof useCockpitData>;
}) {
  const data = buildCompareCardData({ workspace, cockpit });

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <WorkspaceCard title="Vergleich NBR vs PTFE" eyebrow="1" icon={Columns} className="lg:col-span-1">
        {!data ? (
          <WorkspaceStateMessage title="Noch kein backend-projizierter Vergleich vorhanden. Dieser Modus bleibt bis zu einer produktiven Compare-Projektion ein UI-Fallback." />
        ) : (
          <div className="overflow-hidden rounded-[14px] border border-[#E5E7EB]">
            <div className="grid grid-cols-[minmax(120px,0.82fr)_repeat(3,minmax(0,1fr))] bg-[#FAFAFB] text-xs font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
              <div className="border-r border-[#E5E7EB] px-3 py-2">Kriterium</div>
              {data.columns.map((column) => (
                <div key={column.label} className="border-r border-[#E5E7EB] px-3 py-2 last:border-r-0">
                  <div className="text-[#111827]">{column.label}</div>
                  <div className="mt-1 normal-case tracking-normal text-[#6B7280]">{column.value}</div>
                </div>
              ))}
            </div>
            {data.rows.map((row) => (
              <div
                key={row.criterion}
                className="grid grid-cols-[minmax(120px,0.82fr)_repeat(3,minmax(0,1fr))] border-t border-[#E5E7EB] text-sm text-[#4B5563]"
              >
                <div className="border-r border-[#E5E7EB] bg-white px-3 py-2 font-medium text-[#111827]">
                  {row.criterion}
                </div>
                {row.values.map((value, index) => (
                  <div key={`${row.criterion}-${index}`} className="border-r border-[#E5E7EB] bg-white px-3 py-2 last:border-r-0">
                    {value}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Kurzfazit" eyebrow="2" icon={BookOpen} className="lg:col-span-1">
        <div className="space-y-3">
          {(data?.conclusion
            ? data.conclusion
                .split(/(?<=[.!?])\s+/)
                .filter(Boolean)
                .slice(0, 5)
            : [
                "PTFE ueberzeugt durch chemische Bestaendigkeit und hohe Temperaturfestigkeit.",
                "NBR bleibt wirtschaftlich interessant, wenn Dynamik und Kosten priorisiert werden.",
                "Die Auswahl haengt von Medium, Temperatur und Reibungsniveau ab.",
              ]
          ).map((item) => (
            <div key={item} className="flex gap-3 rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3 text-sm text-[#4B5563]">
              <CircleDot className="mt-0.5 shrink-0 text-[#16A34A]" size={16} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </WorkspaceCard>

      <WorkspaceCard title="Wichtige Auswahlkriterien" eyebrow="3" icon={ListChecks} className="lg:col-span-1">
        {data?.criteria.length ? (
          <div className="space-y-2">
            {data.criteria.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                {humanize(item)}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine produktiv projizierten Entscheidungskriterien fuer einen Vergleich vorhanden." />
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Quellen & Datenbasis" eyebrow="4" icon={Database} className="lg:col-span-1">
        {data?.sources.length ? (
          <div className="space-y-2">
            {data.sources.map((item) => (
              <div key={item} className="flex items-center justify-between gap-3 rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                <span>{item}</span>
                <StatusBadge label="Datenblatt" variant="info" />
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Keine expliziten Quellen fuer einen Vergleich projiziert. Der UI-Modus zeigt daher nur den strukturellen Rahmen." />
        )}
      </WorkspaceCard>
    </div>
  );
}

function KnowledgeDeepDiveMode({
  workspace,
  cockpit,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  cockpit: ReturnType<typeof useCockpitData>;
}) {
  const data = buildDeepDiveCardData({ workspace, cockpit });

  return (
    <div className="grid gap-4">
      <WorkspaceCard title="Material Profile" eyebrow="Mode: Deep Dive" icon={FlaskConical}>
        {!data ? (
          <WorkspaceStateMessage title="Noch kein produktiv projiziertes Deep-Dive-Profil vorhanden. Dieser Modus bleibt bis zu einer staerkeren Projektion ein UI-Fallback." />
        ) : (
          <div className="rounded-[14px] border border-[#E5E7EB] bg-white px-3 py-3">
            <div className="text-base font-semibold text-[#111827]">{data.profileTitle || "Deep dive topic offen"}</div>
            <p className="mt-2 text-sm text-[#4B5563]">
              {data.profileSummary || "Noch keine vertiefende Zusammenfassung projiziert."}
            </p>
          </div>
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Properties" eyebrow="Mode: Deep Dive" icon={ListChecks}>
        {data?.properties.length ? (
          <div className="flex flex-wrap gap-2">
            {data.properties.map((item) => (
              <span
                key={item}
                className="rounded-full border border-[#E5E7EB] bg-[#EFF6FF] px-2.5 py-1 text-xs font-medium text-[#2563EB]"
              >
                {item}
              </span>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine vertieften Eigenschaften projiziert." />
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Typical Applications & Limits" eyebrow="Mode: Deep Dive" icon={Activity}>
        {data?.applicationsAndLimits.length ? (
          <div className="space-y-2">
            {data.applicationsAndLimits.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                {item}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine Anwendungen oder Grenzen aus der Projektion verfuegbar." />
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Deep Notes / Sources" eyebrow="Mode: Deep Dive" icon={Database}>
        {data?.notesAndSources.length ? (
          <div className="space-y-2">
            {data.notesAndSources.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                {item}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine vertieften Hinweise oder Quellen projiziert." />
        )}
      </WorkspaceCard>
    </div>
  );
}


function DeepDiveTabMode({
  mode,
  workspace,
  cockpit,
}: {
  mode: Exclude<WorkspaceMode, "analysis">;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  cockpit: ReturnType<typeof useCockpitData>;
}) {
  const tab = workspace?.deepDiveTabs?.find((item) => item.tabId === mode) ?? buildFallbackDeepDiveTab(mode, cockpit, workspace);

  return (
    <div className="grid grid-cols-2 items-start gap-4">
      <WorkspaceCard title="Was wurde erkannt?" eyebrow={tab.label} icon={Search}>
        {tab.detected.length ? (
          <div className="space-y-2">
            {tab.detected.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#111827]">
                {item}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine fallbezogene Projektion fuer diesen Tab vorhanden." />
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Warum relevant?" eyebrow={tab.status} icon={BookOpen}>
        <p className="text-sm leading-relaxed text-[#4B5563]">
          {tab.relevance || "SeaLAI fuehrt diesen Tab nur fallbezogen: Erkenntnis, Risiko, Ableitung und Rueckfuehrung zur Analyse."}
        </p>
        {tab.derivedDirection && (
          <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-3 text-sm text-[#111827]">
            {tab.derivedDirection}
          </div>
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Chancen & Risiken" eyebrow="Fallbezug" icon={AlertCircle}>
        <div className="grid gap-3">
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">Chancen</div>
            <div className="space-y-2">
              {(tab.opportunities.length ? tab.opportunities : ["Noch keine spezifischen Chancen projiziert."]).map((item) => (
                <div key={item} className="rounded-[12px] border border-[#BBF7D0] bg-[#F0FDF4] px-3 py-2 text-sm text-[#166534]">
                  {item}
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">Risiken</div>
            <div className="space-y-2">
              {(tab.risks.length ? tab.risks : ["Keine separaten Risiken fuer diesen Tab projiziert."]).map((item) => (
                <div key={item} className="rounded-[12px] border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-sm text-[#92400E]">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </WorkspaceCard>

      <WorkspaceCard title="Fehlt noch / Rueckfuehrung" eyebrow="Zurueck zur Analyse" icon={ArrowRight}>
        {tab.missing.length ? (
          <div className="space-y-2">
            {tab.missing.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                {humanize(item)}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Keine tab-spezifischen offenen Punkte projiziert." />
        )}
        <div className="rounded-[14px] border border-[#D7E5FF] bg-[#EFF6FF] px-3 py-3 text-sm font-medium text-[#0B57D0]">
          {tab.nextAction || tab.returnToAnalysis || "Zurueck zur Analyse"}
        </div>
      </WorkspaceCard>

      {tab.cards.slice(0, 2).map((card) => (
        <WorkspaceCard key={`${tab.tabId}-${card.title}`} title={card.title} eyebrow="Projection" icon={Database}>
          <p className="text-sm leading-relaxed text-[#4B5563]">{card.body}</p>
          {card.items.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {card.items.map((item) => (
                <span key={item} className="rounded-full border border-[#E5E7EB] bg-[#FAFAFB] px-2.5 py-1 text-xs font-medium text-[#4B5563]">
                  {item}
                </span>
              ))}
            </div>
          )}
        </WorkspaceCard>
      ))}
    </div>
  );
}

function buildFallbackDeepDiveTab(
  mode: Exclude<WorkspaceMode, "analysis">,
  cockpit: ReturnType<typeof useCockpitData>,
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null,
): WorkspaceDeepDiveTab {
  const label = WORKSPACE_MODE_OPTIONS.find((item) => item.id === mode)?.label || "Deep Dive";
  const missing = cockpit?.view.readiness.missingRequiredFields || cockpit?.view.readiness.missingMandatoryKeys || [];
  const medium = cockpit?.mediumStatus.label || workspace?.mediumContext.mediumLabel || "Medium noch offen";
  return {
    tabId: mode,
    label,
    status: "fallback",
    detected: mode === "medium" ? [medium] : [],
    relevance: "Dieser Tab ist bereits als v0.4-Arbeitsflaeche vorhanden; die Backend-Projektion wird fallbezogen erweitert, sobald mehr Daten im Case liegen.",
    opportunities: [],
    risks: (cockpit?.view.riskEvaluations || []).map((risk) => risk.explanationShort || risk.riskName).filter(Boolean).slice(0, 3),
    derivedDirection: "Noch keine vollstaendige Deep-Dive-Projektion fuer diesen Tab.",
    missing,
    nextAction: cockpit?.view.readiness.recommendedNextQuestion || workspace?.communication?.primaryQuestion || null,
    returnToAnalysis: "Zurueck zur Analyse",
    cards: [],
  };
}

function WorkspaceModeContent({
  mode,
  cockpit,
  workspace,
  displayRequestType,
}: {
  mode: WorkspaceMode;
  cockpit: ReturnType<typeof useCockpitData>;
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  displayRequestType: string;
}) {
  if (mode !== "analysis") {
    return <DeepDiveTabMode mode={mode} workspace={workspace} cockpit={cockpit} />;
  }

  return (
    <div className="grid grid-cols-2 items-start gap-4">
      <ParameterApplicationCard
        key={cockpit?.view.path ?? "no-path"}
        cockpit={cockpit}
        workspaceHasAuthoritativeCockpit={Boolean(workspace?.cockpit)}
        displayRequestType={displayRequestType}
      />
      <MediumIntelligenceCard cockpit={cockpit} workspace={workspace} />
      <CalculationsCard cockpit={cockpit} workspace={workspace} />
      <OpenPointsCard cockpit={cockpit} workspace={workspace} />
    </div>
  );
}

function deriveTimelineSteps(cockpit: ReturnType<typeof useCockpitData>): TimelineStep[] {
  const coverage = cockpit?.coverage ?? 0;
  const missingMandatory = cockpit?.view.readiness.missingMandatoryKeys.length ?? 0;
  const rfqReady = cockpit?.view.readiness.isRfqReady ?? false;

  let activeIndex = 0;
  if (rfqReady) {
    activeIndex = 4;
  } else if (coverage >= 0.75) {
    activeIndex = 3;
  } else if (coverage >= 0.45 || missingMandatory > 0) {
    activeIndex = 2;
  } else if (coverage > 0.1 || cockpit?.view.path) {
    activeIndex = 1;
  }

  return [
    "Frage verstehen",
    "Vergleich aufbauen",
    "Unterschiede bewerten",
    "Empfehlung ableiten",
  ].map((label, index) => ({
    label,
    status: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending",
  }));
}

function deriveContextItems({
  cockpit,
  caseId,
}: {
  cockpit: ReturnType<typeof useCockpitData>;
  caseId?: string;
}): ContextItem[] {
  const sectionProperties = cockpit?.view.sections.application_function.properties ?? [];
  const application =
    sectionProperties.find((property) => property.key === "installation")?.value ??
    sectionProperties.find((property) => property.key === "geometry_context")?.value;

  return [
    { label: "Case ID", value: caseId ?? "Noch nicht gebunden" },
    { label: "Active Path", value: titleCase(cockpit?.view.path) },
    { label: "Application", value: compactValue(application) },
    {
      label: "Medium",
      value: cockpit?.mediumStatus.label || cockpit?.mediumStatus.rawMention || "Noch offen",
    },
    {
      label: "Phase",
      value: titleCase(
        cockpit?.view.routingMetadata?.phase || cockpit?.view.readiness.status || "analysis",
      ),
    },
    { label: "Completeness", value: `${Math.round((cockpit?.coverage ?? 0) * 100)}%` },
  ];
}

function WorkspaceTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <div className="border-b border-[#E7ECF3] bg-white px-5 py-4 sm:px-7">
      <div className="custom-scrollbar flex items-center gap-3 overflow-x-auto pb-1">
        {steps.map((step, index) => {
          const isDone = step.status === "done";
          const isActive = step.status === "active";

          return (
            <div key={step.label} className="flex min-w-fit flex-1 items-center gap-3">
              <div className="flex items-center gap-2.5">
                <div
                  className={cn(
                    "flex h-7 min-w-7 items-center justify-center rounded-full border text-[11px] font-semibold transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
                    isActive && "border-[#0B5BD3] bg-[#0B5BD3] text-white shadow-[0_4px_18px_rgba(15,23,42,0.06)]",
                    isDone && "border-[#16A34A] bg-[#16A34A] text-white",
                    !isDone && !isActive && "border-[#D1D5DB] bg-[#F9FAFB] text-[#6B7280]",
                  )}
                >
                  {index + 1}
                </div>
                <div className="min-w-0">
                  <div className={cn("whitespace-nowrap text-sm font-medium", isActive ? "text-[#0B5BD3]" : "text-[#6B7280]")}>
                    {step.label}
                  </div>
                </div>
              </div>
              {index < steps.length - 1 && <div className="h-px min-w-[56px] flex-1 bg-[#D1D5DB]" aria-hidden="true" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WorkspaceCard({
  title,
  eyebrow,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  eyebrow: string;
  icon: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
        className,
      )}
    >
      <div className="mb-4 flex items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">
            {eyebrow}
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">{title}</h2>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-[14px] bg-[#FAFAFB] text-[#4B5563]">
          <Icon size={17} />
        </div>
      </div>
      <div className="space-y-3 text-sm text-[#4B5563]">{children}</div>
    </section>
  );
}

function UtilityRail({
  isOpen,
  onToggle,
  caseId,
  pathLabel,
  mediumLabel,
}: {
  isOpen: boolean;
  onToggle: () => void;
  caseId?: string;
  pathLabel: string;
  mediumLabel: string;
}) {
  const sections = [
    {
      title: "Verlauf",
      items: [caseId ? `Fall ${caseId}` : "Neue Analyse", "Aktive Klaerung", "Letzter Systemturn live"],
      icon: Activity,
    },
    {
      title: "Notizen",
      items: ["Annahmen sichtbar halten", "Keine Frontend-Berechnungen", "Backend-Projektion bevorzugen"],
      icon: Search,
    },
    {
      title: "Sprungmarken",
      items: [pathLabel, mediumLabel, "Offene Punkte"],
      icon: ArrowRight,
    },
  ];

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col rounded-[18px] border border-[#E5E7EB] bg-white shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
        isOpen ? "w-[240px]" : "w-[64px]",
      )}
    >
      <div className={cn("flex items-center border-b border-[#F0F2F5] p-2", isOpen ? "justify-between" : "justify-center")}>
        {isOpen && (
          <div className="min-w-0 px-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">Utility Rail</div>
            <div className="truncate text-sm font-medium text-[#111827]">Kontext ohne Chat-Duplikat</div>
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          aria-controls="workspace-utility-rail"
          aria-label={isOpen ? "Utility Rail einklappen" : "Utility Rail aufklappen"}
          className="flex h-10 w-10 items-center justify-center rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] text-[#4B5563] transition-colors hover:bg-[#F0F2F5] hover:text-[#111827]"
        >
          {isOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
        </button>
      </div>

      <div id="workspace-utility-rail" className="custom-scrollbar flex-1 overflow-y-auto p-2">
        {isOpen ? (
          <div className="space-y-3">
            {sections.map((section) => (
              <div key={section.title} className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                  <section.icon size={14} />
                  {section.title}
                </div>
                <div className="space-y-2">
                  {section.items.map((item) => (
                    <div key={item} className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2 text-xs text-[#4B5563]">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center gap-3 pt-3">
            {[Activity, Search, AlertCircle].map((Icon, index) => (
              <div
                key={index}
                className="flex h-10 w-10 items-center justify-center rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] text-[#4B5563]"
              >
                <Icon size={16} />
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

export default function CaseScreen({ caseId, initialRequestType }: CaseScreenProps) {
  const [resolvedCaseId, setResolvedCaseId] = useState<string | null>(caseId ?? null);
  const workspaceResult = useWorkspace(resolvedCaseId);
  const cockpit = useCockpitData();
  const workspace = useWorkspaceStore((state) => state.workspace);
  const activeResponseClass = useWorkspaceStore((state) => state.activeResponseClass);
  const setWorkspace = useWorkspaceStore((state) => state.setWorkspace);
  const setWorkspaceLoading = useWorkspaceStore((state) => state.setWorkspaceLoading);
  const timelineSteps = useMemo(() => deriveTimelineSteps(cockpit), [cockpit]);
  const contextItems = useMemo(() => deriveContextItems({ cockpit, caseId: resolvedCaseId ?? undefined }), [resolvedCaseId, cockpit]);
  const [modeOverride, setModeOverride] = useState<WorkspaceMode | null>(null);
  const [isUtilityRailOpen, setIsUtilityRailOpen] = useState(false);

  useEffect(() => {
    setResolvedCaseId(caseId ?? null);
  }, [caseId]);

  useEffect(() => {
    setWorkspace(workspaceResult.workspace);
  }, [setWorkspace, workspaceResult.workspace]);

  useEffect(() => {
    setWorkspaceLoading(workspaceResult.isLoading);
  }, [setWorkspaceLoading, workspaceResult.isLoading]);

  const displayRequestType =
    (cockpit?.view.requestType && cockpit.view.requestType !== "nicht bestimmt"
      ? cockpit.view.requestType
      : initialRequestType) || "laufende Analyse";
  const defaultWorkspaceMode = deriveDefaultWorkspaceMode({ workspace, activeResponseClass });
  const workspaceMode = modeOverride ?? defaultWorkspaceMode;

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#F7F9FC]">
      <WorkspaceTimeline steps={timelineSteps} />

      <div className="min-h-0 flex-1 p-4 sm:p-5">
        <div className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <section className="min-h-0 overflow-hidden rounded-[24px] border border-[#E7ECF3] bg-white shadow-[0_6px_22px_rgba(15,23,42,0.05)] lg:min-w-0">
            <ChatPane
              caseId={resolvedCaseId ?? undefined}
              onCaseBound={setResolvedCaseId}
              onTurnComplete={() => void workspaceResult.refresh()}
            />
          </section>

          <section className="min-h-0 overflow-hidden rounded-[24px] border border-[#E7ECF3] bg-[#FBFCFE] shadow-[0_6px_22px_rgba(15,23,42,0.05)] lg:min-w-0">
            <div className="custom-scrollbar flex h-full min-h-0 flex-col overflow-y-auto p-4">
              <div className="mb-4 flex items-start justify-between gap-3 rounded-[18px] border border-[#E7ECF3] bg-white px-4 py-4">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">
                    Vergleichsarbeitsstand
                  </div>
                  <h1 className="mt-1 text-lg font-semibold tracking-tight text-[#111827]">
                    PTFE-RWDR Entscheidungsraum
                  </h1>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div className="flex rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-1">
                    {WORKSPACE_MODE_OPTIONS.map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={workspaceMode === option.id}
                        onClick={() => setModeOverride(option.id)}
                        className={cn(
                          "rounded-[10px] px-3 py-1.5 text-xs font-semibold transition-colors",
                          workspaceMode === option.id
                            ? "bg-[#0B57D0] text-white"
                            : "text-[#4B5563] hover:bg-white hover:text-[#111827]",
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  <StatusBadge
                    label={workspaceMode === "analysis" ? titleCase(cockpit?.view.readiness.status || "analysis") : WORKSPACE_MODE_OPTIONS.find((option) => option.id === workspaceMode)?.label || "Deep Dive"}
                    variant={cockpit?.view.readiness.isRfqReady ? "success" : "info"}
                  />
                </div>
              </div>

              <div className="mb-4 grid grid-cols-2 gap-2">
                {contextItems.slice(0, 4).map((item) => (
                  <div key={item.label} className="rounded-[14px] border border-[#E7ECF3] bg-white px-3 py-2.5">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                      {item.label}
                    </div>
                    <div className="mt-1 text-sm font-medium text-[#111827]">{item.value}</div>
                  </div>
                ))}
              </div>

              <div className="relative min-h-0 flex-1">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={workspaceMode}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="h-full"
                  >
                    <WorkspaceModeContent
                      mode={workspaceMode}
                      cockpit={cockpit}
                      workspace={workspace}
                      displayRequestType={displayRequestType}
                    />
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </section>

          <UtilityRail
            isOpen={isUtilityRailOpen}
            onToggle={() => setIsUtilityRailOpen((isOpen) => !isOpen)}
            caseId={resolvedCaseId ?? undefined}
            pathLabel={titleCase(cockpit?.view.path || workspace?.engineeringPath || "rwdr")}
            mediumLabel={cockpit?.mediumStatus.label || workspace?.mediumClassification?.canonicalLabel || "Medium offen"}
          />
        </div>
      </div>
    </div>
  );
}
