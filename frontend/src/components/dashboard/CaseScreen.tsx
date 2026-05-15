"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Gauge,
  ListChecks,
  PanelRightClose,
  PanelRightOpen,
  Search,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import ChatPane from "@/components/dashboard/ChatPane";
import { StatusBadge } from "@/components/dashboard/CockpitElements";
import { SealCockpit } from "@/components/dashboard/SealCockpit";
import { useCockpitData } from "@/hooks/useCockpitData";
import { patchAgentOverrides, type AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import { fetchWorkspace } from "@/lib/bff/workspace";
import { useChatStore } from "@/lib/store/chatStore";
import {
  DEFAULT_PATH_RULES,
  PATH_RULES,
  type EngineeringPath,
  type EngineeringProperty,
} from "@/lib/engineering/cockpitModel";
import { buildSealCockpitViewModel } from "@/lib/engineering/buildSealCockpitViewModel";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { cn } from "@/lib/utils";

interface CaseScreenProps {
  caseId?: string;
  initialGoal?: string;
  initialRequestType?: string;
}

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

type WorkspaceMode = "case_analysis" | "knowledge_compare" | "knowledge_deep_dive";

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
  { id: "case_analysis", label: "Anfragebasis" },
  { id: "knowledge_compare", label: "Vergleich" },
  { id: "knowledge_deep_dive", label: "Deep Dive" },
];

const DEFAULT_WORKSPACE_WIDTH = 560;
const DEFAULT_WORKSPACE_RATIO = 0.5;
const MIN_WORKSPACE_RATIO = 0.4;
const MAX_WORKSPACE_RATIO = 0.6;
const MIN_CHAT_WIDTH = 430;
const MIN_WORKSPACE_WIDTH = 360;
const RESIZER_WIDTH = 36;

function getWorkspaceWidthBounds(containerWidth: number) {
  const availableForWorkspace = Math.max(
    MIN_WORKSPACE_WIDTH,
    containerWidth - MIN_CHAT_WIDTH - RESIZER_WIDTH,
  );
  const minimum = Math.min(
    availableForWorkspace,
    Math.max(MIN_WORKSPACE_WIDTH, containerWidth * MIN_WORKSPACE_RATIO),
  );
  const maximum = Math.max(
    minimum,
    Math.min(availableForWorkspace, containerWidth * MAX_WORKSPACE_RATIO),
  );

  return { minimum, maximum };
}

function clampWorkspaceWidth(containerWidth: number, width: number) {
  const { minimum, maximum } = getWorkspaceWidthBounds(containerWidth);
  return Math.min(maximum, Math.max(minimum, width));
}

const CORE_PARAMETER_FIELDS: ParameterFieldDescriptor[] = [
  { key: "medium", label: "Medium" },
  { key: "temperature_c", label: "Temperatur" },
  { key: "pressure_bar", label: "Druck" },
  { key: "motion_type", label: "Bewegung" },
  { key: "installation", label: "Anwendung / Maschine" },
  { key: "shaft_diameter_mm", label: "Referenz-Ø" },
  { key: "speed_rpm", label: "Drehzahl" },
];

const PARAMETER_INTAKE_FIELDS: Array<
  ParameterFieldDescriptor & {
    placeholder: string;
    width?: "half" | "full";
  }
> = [
  { key: "medium", label: "Medium", placeholder: "z. B. Hydrauliköl HLP 46", width: "full" },
  { key: "temperature_c", label: "Temperatur", placeholder: "z. B. 80", width: "half" },
  { key: "pressure_bar", label: "Druck", placeholder: "z. B. 12", width: "half" },
  { key: "motion_type", label: "Bewegung", placeholder: "rotierend, statisch, Hub", width: "half" },
  { key: "sealing_type", label: "Dichtungstyp", placeholder: "RWDR, O-Ring, Flachdichtung", width: "half" },
  { key: "shaft_diameter_mm", label: "Referenz-Ø", placeholder: "z. B. 35", width: "half" },
  { key: "speed_rpm", label: "Drehzahl", placeholder: "z. B. 1500", width: "half" },
  { key: "installation", label: "Anwendung", placeholder: "Pumpe, Getriebe, Ventil ...", width: "full" },
  { key: "geometry_context", label: "Bauraum / Geometrie", placeholder: "Nut, Welle, Einbauraum, Altteil", width: "full" },
  { key: "failure_mode", label: "Ziel / Fehlerbild", placeholder: "Neuauslegung, Leckage, Ersatz, Optimierung", width: "full" },
];

const NUMERIC_INTAKE_FIELDS = new Set([
  "temperature_c",
  "pressure_bar",
  "shaft_diameter_mm",
  "speed_rpm",
]);

const INTAKE_FIELD_UNITS: Record<string, string> = {
  temperature_c: "°C",
  pressure_bar: "bar",
  shaft_diameter_mm: "mm",
  speed_rpm: "rpm",
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
    { key: "allowable_leakage", label: "Zulässige Leckage" },
    { key: "life_hours", label: "Lebensdauer" },
  ],
  static: [
    { key: "geometry_context", label: "Bauraum" },
    { key: "compliance", label: "Konformität" },
    { key: "allowable_leakage", label: "Zulässige Leckage" },
    { key: "life_hours", label: "Lebensdauer" },
  ],
  other: [
    { key: "viscosity", label: "Viskosität" },
    { key: "solids_percent", label: "Feststoffe" },
    { key: "ph", label: "pH-Wert" },
    { key: "dry_run_possible", label: "Trockenlauf möglich" },
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

function normalizeIntakeOverrideValue(key: string, value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  if (!NUMERIC_INTAKE_FIELDS.has(key)) {
    return trimmed;
  }

  const normalizedNumber = Number(trimmed.replace(",", "."));
  return Number.isFinite(normalizedNumber) ? normalizedNumber : trimmed;
}

function buildIntakeOverrideItems(
  items: Array<{ key: string; value: string }>,
): AgentOverrideItemRequest[] {
  const overrides: AgentOverrideItemRequest[] = [];

  items.forEach((item) => {
    const value = normalizeIntakeOverrideValue(item.key, item.value);
    if (value === null) {
      return;
    }

    overrides.push({
      field_name: item.key,
      value,
      unit: INTAKE_FIELD_UNITS[item.key] ?? null,
    });
  });

  return overrides;
}

function ParameterIntakePanel({ cockpit }: { cockpit: ReturnType<typeof useCockpitData> }) {
  const userParameterOverrides = useWorkspaceStore((s) => s.userParameterOverrides) ?? {};
  const setUserParameterOverride = useWorkspaceStore((s) => s.setUserParameterOverride);
  const resetUserParameterOverrides = useWorkspaceStore((s) => s.resetUserParameterOverrides);
  const workspaceCaseId = useWorkspaceStore((s) => s.workspace?.caseId ?? null);
  const setWorkspace = useWorkspaceStore((s) => s.setWorkspace);
  const activeCaseId = useChatStore((s) => s.activeCaseId);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const parameters = cockpit?.parameters ?? {};
  const canonicalCaseId = workspaceCaseId || activeCaseId;

  const values = PARAMETER_INTAKE_FIELDS.reduce<Record<string, string>>((acc, field) => {
    const value = userParameterOverrides[field.key] ?? parameters[field.key];
    acc[field.key] = value === null || value === undefined ? "" : String(value);
    return acc;
  }, {});

  const filledItems = PARAMETER_INTAKE_FIELDS
    .map((field) => ({
      key: field.key,
      label: field.label,
      value: values[field.key]?.trim(),
    }))
    .filter((item) => item.value);

  const filledCount = filledItems.length;
  const canAnalyze = filledCount > 0 && !isStreaming;
  const canPersist = Boolean(canonicalCaseId) && filledCount > 0 && saveState !== "saving";

  const persistOverrides = async () => {
    if (!canonicalCaseId || filledItems.length === 0) {
      return false;
    }

    setSaveState("saving");
    setSaveMessage(null);

    try {
      const overrides = buildIntakeOverrideItems(
        filledItems.map((item) => ({ key: item.key, value: item.value || "" })),
      );
      if (overrides.length === 0) {
        setSaveState("idle");
        return false;
      }

      const result = await patchAgentOverrides(canonicalCaseId, { overrides });
      const nextWorkspace = await fetchWorkspace(canonicalCaseId).catch(() => null);
      if (nextWorkspace) {
        setWorkspace(nextWorkspace);
      }
      setSaveState("saved");
      setSaveMessage(`${result.applied_fields.length} Parameter in der Fallakte gespeichert.`);
      return true;
    } catch (error) {
      setSaveState("error");
      setSaveMessage(error instanceof Error ? error.message : "Parameter konnten nicht gespeichert werden.");
      return false;
    }
  };

  const handleAnalyze = async () => {
    if (!canAnalyze) return;
    if (canonicalCaseId) {
      const persisted = await persistOverrides();
      if (!persisted) {
        return;
      }
    }

    const facts = filledItems.map((item) => `- ${item.label}: ${item.value}`).join("\n");
    void sendMessage(
      [
        "Analysiere diese direkt eingegebenen Dichtungsparameter als vorbereiteten technischen Fall.",
        canonicalCaseId
          ? "Die Angaben wurden vorher als User-Overrides in die Fallakte geschrieben."
          : "Es ist noch kein Fall gebunden; nutze diese Angaben als Startdatensatz und überführe sie in den neuen Fallzustand.",
        "",
        facts,
        "",
        "Bitte stelle keine stumpfe Parameterabfrage. Challenge den Dichtungsfall: benenne kritische Punkte, abgeleitete Signale, vorsichtige Prüfhypothesen, Gegenindikatoren, fehlende Blocker und die nächste beste Rückfrage. Keine Prozentwerte, keine finale Freigabe, keine Materialentscheidung.",
      ].join("\n"),
    );
  };

  return (
    <div className="rounded-[18px] border border-[#D1D5DB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-seal-blue">
            <Gauge size={14} />
            Parameter
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">
            Schnelleingabe für vorbereitete Fälle
          </h2>
        </div>
        <span className="rounded-full border border-[#D1D5DB] bg-muted px-2.5 py-1 text-xs font-semibold text-seal-blue">
          {filledCount}/{PARAMETER_INTAKE_FIELDS.length}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {PARAMETER_INTAKE_FIELDS.map((field) => (
          <label
            key={field.key}
            className={cn("block", field.width === "full" && "sm:col-span-2")}
          >
            <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {field.label}
            </span>
            <input
              value={values[field.key]}
              onChange={(event) => setUserParameterOverride(field.key, event.target.value)}
              placeholder={field.placeholder}
              className="h-10 w-full rounded-[12px] border border-[#C9D1DC] bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-[#6B7280] focus:border-seal-blue focus:ring-3 focus:ring-seal-blue/10"
            />
          </label>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => {
            resetUserParameterOverrides();
            setSaveState("idle");
            setSaveMessage(null);
          }}
          className="rounded-full border border-[#D1D5DB] bg-white px-3 py-2 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          Eingaben leeren
        </button>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={() => void persistOverrides()}
            disabled={!canPersist}
            className="rounded-full border border-[#D1D5DB] bg-white px-3 py-2 text-xs font-semibold text-seal-blue transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
          >
            {saveState === "saving" ? "Speichere..." : "In Fallakte speichern"}
          </button>
          <button
            type="button"
            onClick={() => void handleAnalyze()}
            disabled={!canAnalyze || saveState === "saving"}
            className="inline-flex items-center gap-2 rounded-full bg-seal-blue px-4 py-2 text-xs font-semibold text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
          >
            {canonicalCaseId ? "Speichern & analysieren" : "Mit sealingAI analysieren"}
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      <div className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-xs text-muted-foreground">
        {saveMessage ||
          (canonicalCaseId
            ? "Eingaben werden als User-Overrides mit Fallbezug gespeichert."
            : "Nach dem ersten Chat-Turn bindet sealingAI einen Fall; danach werden die Werte dauerhaft in die Fallakte geschrieben.")}
      </div>
    </div>
  );
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
  workspace,
  activeResponseClass,
}: {
  workspace: ReturnType<typeof useWorkspaceStore.getState>["workspace"] | null;
  activeResponseClass: string | null;
}): WorkspaceMode {
  if (
    activeResponseClass === "candidate_shortlist" &&
    (workspace?.matching.items.length ?? 0) > 1
  ) {
    return "knowledge_compare";
  }

  if (
    !workspace?.caseId &&
    (workspace?.mediumContext.summary || workspace?.mediumClassification.canonicalLabel)
  ) {
    return "knowledge_deep_dive";
  }

  return "case_analysis";
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
                    ? "border-[#041E49] bg-[#041E49] text-white"
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
      ? "Technische Klärung ist ausreichend weit für den nächsten Freigabeschritt."
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
    <div className="grid gap-4 xl:grid-cols-2">
      <WorkspaceCard title="Vergleich NBR vs PTFE" eyebrow="1" icon={Columns} className="xl:col-span-1">
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

      <WorkspaceCard title="Kurzfazit" eyebrow="2" icon={BookOpen} className="xl:col-span-1">
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

      <WorkspaceCard title="Wichtige Auswahlkriterien" eyebrow="3" icon={ListChecks} className="xl:col-span-1">
        {data?.criteria.length ? (
          <div className="space-y-2">
            {data.criteria.map((item) => (
              <div key={item} className="rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
                {humanize(item)}
              </div>
            ))}
          </div>
        ) : (
          <WorkspaceStateMessage title="Noch keine produktiv projizierten Entscheidungskriterien für einen Vergleich vorhanden." />
        )}
      </WorkspaceCard>

      <WorkspaceCard title="Quellen & Datenbasis" eyebrow="4" icon={Database} className="xl:col-span-1">
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
          <WorkspaceStateMessage title="Keine expliziten Quellen für einen Vergleich projiziert. Der UI-Modus zeigt daher nur den strukturellen Rahmen." />
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
  if (mode === "knowledge_compare") {
    return <KnowledgeCompareMode workspace={workspace} cockpit={cockpit} />;
  }

  if (mode === "knowledge_deep_dive") {
    return <KnowledgeDeepDiveMode workspace={workspace} cockpit={cockpit} />;
  }

  return (
    <div className="grid gap-4">
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
      items: [caseId ? `Fall ${caseId}` : "Neue Analyse", "Aktive Klärung", "Letzter Systemturn live"],
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

export default function CaseScreen({ caseId, initialGoal, initialRequestType }: CaseScreenProps) {
  const cockpit = useCockpitData();
  const workspace = useWorkspaceStore((state) => state.workspace);
  const activeResponseClass = useWorkspaceStore((state) => state.activeResponseClass);
  const setWorkspace = useWorkspaceStore((state) => state.setWorkspace);
  const setWorkspaceLoading = useWorkspaceStore((state) => state.setWorkspaceLoading);
  const cockpitViewModel = useMemo(() => buildSealCockpitViewModel(workspace), [workspace]);
  const [isParameterSubmitting, setIsParameterSubmitting] = useState(false);
  const [isWorkspaceOpen, setIsWorkspaceOpen] = useState(true);
  const [workspaceWidth, setWorkspaceWidth] = useState(DEFAULT_WORKSPACE_WIDTH);
  const [isResizingWorkspace, setIsResizingWorkspace] = useState(false);
  const layoutRef = useRef<HTMLDivElement>(null);
  const hasUserResizedWorkspaceRef = useRef(false);
  const activeCaseId = useChatStore((state) => state.activeCaseId);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const canonicalCaseId = workspace?.caseId || activeCaseId || caseId || null;

  useEffect(() => {
    if (!caseId) {
      return;
    }

    let isCurrent = true;
    setWorkspaceLoading(true);
    fetchWorkspace(caseId)
      .then((nextWorkspace) => {
        if (isCurrent) {
          setWorkspace(nextWorkspace);
        }
      })
      .catch(() => {
        if (isCurrent) {
          setWorkspace(null);
        }
      })
      .finally(() => {
        if (isCurrent) {
          setWorkspaceLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [caseId, setWorkspace, setWorkspaceLoading]);

  useEffect(() => {
    if (!isWorkspaceOpen) {
      return;
    }

    const layoutElement = layoutRef.current;
    if (!layoutElement || typeof ResizeObserver === "undefined") {
      return;
    }

    const syncWorkspaceWidth = () => {
      const bounds = layoutElement.getBoundingClientRect();
      if (bounds.width <= 0) {
        return;
      }

      setWorkspaceWidth((currentWidth) => {
        const preferredWidth = hasUserResizedWorkspaceRef.current
          ? currentWidth
          : bounds.width * DEFAULT_WORKSPACE_RATIO;
        return clampWorkspaceWidth(bounds.width, preferredWidth);
      });
    };

    syncWorkspaceWidth();
    const observer = new ResizeObserver(syncWorkspaceWidth);
    observer.observe(layoutElement);

    return () => observer.disconnect();
  }, [isWorkspaceOpen]);

  useEffect(() => {
    if (!isResizingWorkspace) {
      return;
    }

    const updateWorkspaceWidth = (clientX: number) => {
      const bounds = layoutRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }
      const nextWidth = bounds.right - clientX - RESIZER_WIDTH / 2;
      setWorkspaceWidth(clampWorkspaceWidth(bounds.width, nextWidth));
    };
    const handlePointerMove = (event: PointerEvent) => {
      updateWorkspaceWidth(event.clientX);
    };
    const handleMouseMove = (event: MouseEvent) => {
      updateWorkspaceWidth(event.clientX);
    };

    const stopResizing = () => {
      setIsResizingWorkspace(false);
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("pointerup", stopResizing, { once: true });
    window.addEventListener("mouseup", stopResizing, { once: true });

    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("pointerup", stopResizing);
      window.removeEventListener("mouseup", stopResizing);
    };
  }, [isResizingWorkspace]);

  const handleWorkspaceRefresh = useCallback(
    async (nextCaseId?: string) => {
      const refreshCaseId = nextCaseId || canonicalCaseId;
      if (!refreshCaseId) {
        return;
      }
      const nextWorkspace = await fetchWorkspace(refreshCaseId).catch(() => null);
      if (nextWorkspace) {
        setWorkspace(nextWorkspace);
      }
    },
    [canonicalCaseId, setWorkspace],
  );

  const handleParameterSubmit = useCallback(
    async (overrides: AgentOverrideItemRequest[], summary: string) => {
      if (overrides.length === 0) {
        return;
      }
      if (!canonicalCaseId) {
        const facts = overrides
          .map((override) => `- ${override.field_name}: ${override.value}${override.unit ? ` ${override.unit}` : ""}`)
          .join("\n");
        void sendMessage(
          [
            "Analysiere diese direkt eingegebenen Dichtungsparameter als vorbereiteten technischen Fall.",
            summary ? `Zusammenfassung: ${summary}` : null,
            "",
            facts,
            "",
            "Bitte stelle keine stumpfe Parameterabfrage. Challenge den Dichtungsfall: benenne kritische Punkte, abgeleitete Signale, vorsichtige Prüfhypothesen, Gegenindikatoren, fehlende Blocker und die nächste beste Rückfrage. Keine Prozentwerte, keine finale Freigabe, keine Materialentscheidung.",
          ]
            .filter(Boolean)
            .join("\n"),
        );
        return;
      }
      setIsParameterSubmitting(true);
      try {
        await patchAgentOverrides(canonicalCaseId, { overrides });
        await handleWorkspaceRefresh(canonicalCaseId);
      } finally {
        setIsParameterSubmitting(false);
      }
    },
    [canonicalCaseId, handleWorkspaceRefresh, sendMessage],
  );
  const handleCaseBound = useCallback(
    (nextCaseId: string) => {
      void handleWorkspaceRefresh(nextCaseId);
    },
    [handleWorkspaceRefresh],
  );
  const handleTurnComplete = useCallback(
    (nextCaseId: string) => {
      void handleWorkspaceRefresh(nextCaseId);
    },
    [handleWorkspaceRefresh],
  );

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-y-auto bg-white lg:overflow-hidden">
      <div className="relative min-h-0 flex-1 px-4 py-4 sm:px-5">
        {!isWorkspaceOpen ? (
          <button
            type="button"
            aria-label="Arbeitsbereich einblenden"
            title="Arbeitsbereich einblenden"
            onClick={() => setIsWorkspaceOpen(true)}
            className="absolute right-5 top-5 z-30 inline-flex h-10 items-center gap-2 rounded-full border border-border bg-white px-3 text-xs font-semibold text-seal-blue shadow-[0_12px_30px_rgba(15,23,42,0.10)] transition-colors hover:bg-muted"
          >
            <PanelRightOpen size={15} />
            Arbeitsbereich
          </button>
        ) : null}

        <div
          ref={layoutRef}
          style={{ "--workspace-width": `${workspaceWidth}px` } as React.CSSProperties}
          className={cn(
            "flex min-h-[640px] flex-col lg:h-full lg:min-h-0 lg:flex-row",
            isResizingWorkspace && "select-none",
          )}
        >
          <section className="min-h-[460px] flex-1 overflow-hidden lg:min-h-0 lg:min-w-[430px]">
            <ChatPane
              caseId={caseId}
              initialGoal={initialGoal}
              onCaseBound={handleCaseBound}
              onTurnComplete={handleTurnComplete}
            />
          </section>

          {isWorkspaceOpen ? (
            <>
              <button
                type="button"
                aria-label="Arbeitsbereichbreite anpassen"
                title="Arbeitsbereichbreite anpassen"
                onPointerDown={(event) => {
                  event.preventDefault();
                  hasUserResizedWorkspaceRef.current = true;
                  setIsResizingWorkspace(true);
                }}
                onMouseDown={(event) => {
                  event.preventDefault();
                  hasUserResizedWorkspaceRef.current = true;
                  setIsResizingWorkspace(true);
                }}
                className={cn(
                  "relative hidden w-9 shrink-0 cursor-col-resize touch-none items-center justify-center outline-none lg:flex",
                  "before:absolute before:inset-y-8 before:left-1/2 before:w-7 before:-translate-x-1/2 before:rounded-full before:bg-gradient-to-r before:from-transparent before:via-[#EFF4FA] before:to-transparent before:opacity-0 before:transition-opacity hover:before:opacity-100",
                )}
              >
                <span
                  className={cn(
                    "sticky top-[50vh] flex h-12 w-10 -translate-y-1/2 items-center justify-center gap-0.5 rounded-full border border-[#C7D2E2] bg-white text-seal-blue shadow-[0_14px_35px_rgba(4,30,73,0.20)] transition-all duration-150",
                    "hover:border-seal-blue hover:shadow-[0_18px_42px_rgba(4,30,73,0.26)]",
                    isResizingWorkspace && "border-seal-blue bg-[#F8FAFF] shadow-[0_18px_45px_rgba(4,30,73,0.30)]",
                  )}
                >
                  <ChevronLeft size={14} strokeWidth={2.4} />
                  <ChevronRight size={14} strokeWidth={2.4} />
                </span>
              </button>
              <aside className="relative min-h-0 w-full overflow-visible lg:w-[var(--workspace-width)] lg:shrink-0 lg:overflow-hidden">
                <button
                  type="button"
                  aria-label="Arbeitsbereich einklappen"
                  title="Arbeitsbereich einklappen"
                  onClick={() => setIsWorkspaceOpen(false)}
                  className="absolute right-4 top-4 z-20 inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-white text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-seal-blue"
                >
                  <PanelRightClose size={16} />
                </button>
                <div className="custom-scrollbar min-h-0 pr-12 lg:h-full lg:overflow-y-auto">
                  <SealCockpit
                    data={cockpitViewModel}
                    workspace={workspace}
                    isParameterSubmitting={isParameterSubmitting}
                    onParameterSubmit={handleParameterSubmit}
                    preferredTab={canonicalCaseId ? null : "parameters"}
                  />
                </div>
              </aside>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
