"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Info, RotateCcw, Save } from "lucide-react";

import type { AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import { humanizeDisplayText } from "@/lib/engineering/displayLabels";
import { cn } from "@/lib/utils";

type ParameterKind = "text" | "number";
type BadgeTone = "default" | "info" | "warning" | "danger" | "success";

type ParameterField = {
  fieldName: string;
  label: string;
  unit?: string;
  kind: ParameterKind;
  placeholder: string;
  detail: string;
  why: string;
};

type ParameterMeta = {
  sourceType: string | null;
  validationStatus: string | null;
  origin: string | null;
  confidence: string | null;
  isConfirmed: boolean;
  isMandatory: boolean;
};

const PARAMETER_FIELDS: ParameterField[] = [
  {
    fieldName: "medium",
    label: "Medium",
    kind: "text",
    placeholder: "z. B. Ethanol, Salzwasser, Hydrauliköl",
    detail: "Das Medium beeinflusst Werkstoff, Korrosion, Schmierung und spätere Prüfpunkte.",
    why: "Ohne Medium kann SeaLAI nur grob einordnen, welche Richtung passen könnte.",
  },
  {
    fieldName: "temperature_c",
    label: "Temperatur",
    unit: "°C",
    kind: "number",
    placeholder: "z. B. 150",
    detail: "Die Temperatur entscheidet mit, welche Werkstoffe überhaupt in Frage kommen.",
    why: "Temperaturspitzen können wichtiger sein als die normale Betriebstemperatur.",
  },
  {
    fieldName: "pressure_bar",
    label: "Druck",
    unit: "bar",
    kind: "number",
    placeholder: "z. B. 10",
    detail: "Beim Druck ist wichtig, ob er wirklich direkt an der Dichtstelle anliegt.",
    why: "Bei Pumpen und rotierenden Wellen kann der Dichtstellendruck deutlich vom Systemdruck abweichen.",
  },
  {
    fieldName: "speed_rpm",
    label: "Drehzahl",
    unit: "rpm",
    kind: "number",
    placeholder: "z. B. 1450",
    detail: "Die Drehzahl hilft einzuschätzen, wie stark die Dichtkante beansprucht wird.",
    why: "Zusammen mit dem Wellendurchmesser entstehen daraus erste Rechenchecks.",
  },
  {
    fieldName: "shaft_diameter_mm",
    label: "Wellendurchmesser",
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 42",
    detail: "Der Wellendurchmesser ist wichtig für Einbauraum, Baugröße und Rechenchecks.",
    why: "Ohne Geometrie fehlen Herstellern oft entscheidende Angaben.",
  },
  {
    fieldName: "installation",
    label: "Anlage / Einbauort",
    kind: "text",
    placeholder: "z. B. Chemiepumpe, Getriebeausgang, Rührwerk",
    detail: "Die Anlage zeigt, in welchem Umfeld die Dichtung arbeiten muss.",
    why: "Eine Pumpe, ein Getriebe und ein Rührwerk benötigen unterschiedliche Prüfpunkte.",
  },
  {
    fieldName: "sealing_type",
    label: "Dichtungstyp-Richtung",
    kind: "text",
    placeholder: "z. B. RWDR, PTFE-RWDR, Gleitringdichtung",
    detail: "Diese Angabe ist nur eine Richtung oder vorhandene Vermutung.",
    why: "SeaLAI nutzt sie zur Einordnung, prüft aber weiter gegen Medium, Druck, Geometrie und Anwendung.",
  },
  {
    fieldName: "counterface_surface",
    label: "Gegenlauffläche",
    kind: "text",
    placeholder: "z. B. gehärtete Welle, Ra 0,2 µm, unbekannt",
    detail: "Oberfläche, Härte und Rundlauf beeinflussen Verschleiß, Leckage und Reibung.",
    why: "Gerade bei RWDR/PTFE-RWDR ist die Gegenlauffläche häufig ein Herstellerprüfpunkt.",
  },
];

const SOURCE_LABELS: Record<string, string> = {
  user_stated: "Nutzerangabe",
  uploaded_evidence: "Dokument / Upload",
  documented: "Dokument / Upload",
  rag_verified: "Wissensbasis",
  deterministic_calculation: "Berechnung",
  calculated: "Berechnung",
  llm_research_fallback: "KI-Hinweis",
  llm_synthesis: "KI-Hinweis",
  inferred: "abgeleitet",
  pattern_derived: "abgeleitet",
  system_derived: "aus den Angaben abgeleitet",
  missing: "Herkunft fehlt",
  unknown: "Herkunft unklar",
};

const VALIDATION_LABELS: Record<string, string> = {
  validated: "geprüft",
  documented: "dokumentiert",
  user_stated: "Nutzerangabe",
  candidate: "Kandidat",
  unvalidated: "noch nicht geprüft",
  conflicting: "widersprüchlich",
  conflict: "widersprüchlich",
  calculated: "berechnet",
  confirmed: "bestätigt",
  missing: "offen",
  unknown: "unklar",
};

const COCKPIT_FIELD_ALIASES: Record<string, string[]> = {
  medium: ["medium_name"],
  temperature_c: ["temperature_max", "temperature_min"],
  pressure_bar: ["pressure_nominal", "pressure_peak"],
  speed_rpm: ["rotational_speed"],
  shaft_diameter_mm: ["shaft_diameter"],
  installation: ["asset_type", "application", "asset_function"],
  sealing_type: ["seal_type", "current_seal_type", "requested_seal_type"],
  counterface_surface: ["surface_finish"],
};

const TYPE_SPECIFIC_FIELD_LABELS: Record<string, string> = {
  flange_standard: "Flansch / Norm",
  flange_size_or_dimensions: "Flanschgröße / Zeichnungsmaß",
  inner_outer_diameter: "Innen- und Außendurchmesser",
  hole_pattern: "Lochbild",
  gasket_material: "Dichtungsmaterial",
  thickness: "Dicke",
  bolt_load_or_torque: "Schraubenkraft / Drehmoment",
  surface_roughness: "Dichtflächen",
  certification_requirement: "Nachweise",
  rod_or_piston_diameter: "Stangen- oder Kolbendurchmesser",
  groove_dimensions: "Nut / Einbauraum",
  pressure_peaks: "Druckspitzen",
  hydraulic_fluid: "Hydraulikmedium",
  speed_or_stroke: "Hub / Geschwindigkeit",
  single_or_double_acting: "einfach- oder doppeltwirkend",
  contamination: "Verschmutzung",
  wiper_or_guide_required: "Abstreifer / Führung / Stützring",
  water_content: "Wasser / Kondensat",
  air_quality: "Druckluftqualität",
  lubrication: "Schmierung",
  friction_requirement: "Reibungsanforderung",
  pump_or_aggregate_type: "Pumpe / Aggregat",
  flush_or_barrier_fluid: "Spülung / Sperrmedium",
  solids_or_gas_content: "Feststoffe / Gas / Kristallisation",
  viscosity: "Viskosität / Aggregatzustand",
  atex_or_leakage_requirement: "ATEX / Leckageanforderung",
  inner_diameter: "Innendurchmesser",
  cross_section: "Schnurstärke",
  material: "Werkstoff",
  hardness: "Härte",
  static_or_dynamic: "statisch oder dynamisch",
  squeeze_or_stretch: "Verpressung / Dehnung",
  backup_ring_required: "Stützring",
  shaft_or_stem_diameter: "Wellen- oder Spindeldurchmesser",
  stuffing_box_dimensions: "Stopfbuchsraum",
  lubrication_or_flush: "Schmierung / Spülung",
};

type ParameterFormState = Record<string, string>;

function valueFor(workspace: WorkspaceView | null, fieldName: string): string {
  const value = workspace?.parameters?.[fieldName as keyof WorkspaceView["parameters"]];
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function normalizeCode(value: string | null | undefined): string {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function readableCode(value: string | null | undefined): string {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .trim();
}

function technicalFieldLabel(value: string | null | undefined): string {
  const code = normalizeCode(value);
  return TYPE_SPECIFIC_FIELD_LABELS[code] || humanizeDisplayText(value || "");
}

function sourceLabel(value: string | null | undefined): string {
  const code = normalizeCode(value);
  return SOURCE_LABELS[code] || readableCode(value) || SOURCE_LABELS.unknown;
}

function validationLabel(value: string | null | undefined): string {
  const code = normalizeCode(value);
  return VALIDATION_LABELS[code] || readableCode(value) || VALIDATION_LABELS.unknown;
}

function sourceTone(value: string | null | undefined): BadgeTone {
  const code = normalizeCode(value);
  if (code === "llm_research_fallback" || code === "llm_synthesis" || code === "unknown" || code === "missing") {
    return "warning";
  }
  if (code === "deterministic_calculation" || code === "calculated" || code === "rag_verified") {
    return "info";
  }
  if (code === "uploaded_evidence" || code === "documented" || code === "user_stated") {
    return "success";
  }
  return "default";
}

function validationTone(value: string | null | undefined): BadgeTone {
  const code = normalizeCode(value);
  if (code === "validated" || code === "confirmed" || code === "documented" || code === "calculated") {
    return "success";
  }
  if (code === "conflicting" || code === "conflict") {
    return "danger";
  }
  if (code === "candidate" || code === "unvalidated" || code === "unknown" || code === "missing") {
    return "warning";
  }
  return "default";
}

function badgeClass(tone: BadgeTone) {
  switch (tone) {
    case "success":
      return "border-[#B7E4C7] bg-[#EAF7EE] text-[#166534]";
    case "info":
      return "border-[#CFE0FF] bg-[#EFF6FF] text-[#0B57D0]";
    case "warning":
      return "border-[#F6D8A8] bg-[#FFF4E5] text-[#92400E]";
    case "danger":
      return "border-[#F7C8C8] bg-[#FDECEC] text-[#991B1B]";
    default:
      return "border-[#E5E7EB] bg-white text-[#4B5563]";
  }
}

function parameterMeta(workspace: WorkspaceView | null, fieldName: string): ParameterMeta {
  const aliases = new Set([fieldName, ...(COCKPIT_FIELD_ALIASES[fieldName] ?? [])]);
  const sections = Object.values(workspace?.cockpit?.sections ?? {});
  for (const section of sections) {
    const property = section.properties.find((item) => aliases.has(item.key));
    if (property) {
      return {
        sourceType: property.sourceType ?? property.origin ?? null,
        validationStatus: property.validationStatus ?? property.confidence ?? null,
        origin: property.origin ?? null,
        confidence: property.confidence ?? null,
        isConfirmed: property.isConfirmed,
        isMandatory: property.isMandatory,
      };
    }
  }
  if (fieldName === "medium" && workspace?.mediumContext) {
    return {
      sourceType: workspace.mediumContext.sourceType ?? null,
      validationStatus: workspace.mediumContext.validationStatus ?? null,
      origin: workspace.mediumCapture.primaryRawText ? "user_stated" : null,
      confidence: workspace.mediumContext.confidence ?? null,
      isConfirmed: workspace.mediumClassification.confidence === "high",
      isMandatory: workspace.completeness.missingCriticalParameters.includes("medium"),
    };
  }
  return {
    sourceType: valueFor(workspace, fieldName) ? "unknown" : "missing",
    validationStatus: valueFor(workspace, fieldName) ? "unknown" : "missing",
    origin: null,
    confidence: null,
    isConfirmed: false,
    isMandatory: workspace?.completeness.missingCriticalParameters.includes(fieldName) ?? false,
  };
}

function initialState(workspace: WorkspaceView | null): ParameterFormState {
  return Object.fromEntries(
    PARAMETER_FIELDS.map((field) => [field.fieldName, valueFor(workspace, field.fieldName)]),
  );
}

function parseValue(field: ParameterField, rawValue: string): string | number | null {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return null;
  }
  if (field.kind === "number") {
    const normalized = trimmed.replace(",", ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return trimmed;
}

function valuesMatch(field: ParameterField, currentValue: string, nextValue: string | number): boolean {
  const current = parseValue(field, currentValue);
  if (current === null) {
    return false;
  }
  if (field.kind === "number") {
    return typeof current === "number" && typeof nextValue === "number" && Math.abs(current - nextValue) < 0.000001;
  }
  return String(current).trim() === String(nextValue).trim();
}

function formatSummary(overrides: AgentOverrideItemRequest[]) {
  return overrides
    .map((override) => {
      const field = PARAMETER_FIELDS.find((item) => item.fieldName === override.field_name);
      const unit = override.unit ? ` ${override.unit}` : "";
      return `${field?.label ?? humanizeDisplayText(override.field_name)}: ${String(override.value)}${unit}`;
    })
    .join("; ");
}

function fieldStatus(workspace: WorkspaceView | null, field: ParameterField, rawValue: string) {
  const parsed = parseValue(field, rawValue);
  const currentValue = valueFor(workspace, field.fieldName);
  if (parsed !== null && !valuesMatch(field, currentValue, parsed)) {
    return "Status: wird als Nutzerangabe übernommen";
  }
  return currentValue ? "Status: bekannt" : "Status: offen";
}

function MetadataBadge({ label, tone = "default" }: { label: string; tone?: BadgeTone }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-1 text-[11px] font-semibold", badgeClass(tone))}>
      {label}
    </span>
  );
}

function ParameterFieldCard({
  field,
  workspace,
  formState,
  isSubmitting,
  onChange,
}: {
  field: ParameterField;
  workspace: WorkspaceView | null;
  formState: ParameterFormState;
  isSubmitting: boolean;
  onChange: (value: string) => void;
}) {
  const meta = parameterMeta(workspace, field.fieldName);
  const rawValue = formState[field.fieldName] ?? "";
  const isChanged = (() => {
    const parsed = parseValue(field, rawValue);
    return parsed !== null && !valuesMatch(field, valueFor(workspace, field.fieldName), parsed);
  })();
  const effectiveSource = isChanged ? "user_stated" : meta.sourceType;
  const effectiveValidation = isChanged ? "user_stated" : meta.validationStatus;

  return (
    <label className="block rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-[#111827]">{field.label}</div>
          <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{field.detail}</p>
        </div>
        {field.unit && (
          <span className="rounded-full border border-[#E5E7EB] bg-white px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[#6B7280]">
            {field.unit}
          </span>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          aria-label={field.label}
          inputMode={field.kind === "number" ? "decimal" : "text"}
          value={rawValue}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
          disabled={isSubmitting}
          className="min-h-10 w-full rounded-[12px] border border-[#D1D5DB] bg-white px-3 py-2 text-sm font-medium text-[#111827] outline-none transition-colors placeholder:text-[#9CA3AF] focus:border-[#0B57D0]"
        />
      </div>
      <div className="mt-2 grid gap-2 text-[12px] leading-relaxed text-[#6B7280]">
        <span>{field.why}</span>
        <span className="font-medium text-[#4B5563]">{fieldStatus(workspace, field, rawValue)}</span>
        <div className="flex flex-wrap gap-1.5">
          <MetadataBadge label={`Woher: ${sourceLabel(effectiveSource)}`} tone={sourceTone(effectiveSource)} />
          <MetadataBadge label={`Status: ${validationLabel(effectiveValidation)}`} tone={validationTone(effectiveValidation)} />
          {meta.isMandatory && <MetadataBadge label="Pflichtfeld" tone="warning" />}
          {meta.isConfirmed && !isChanged && <MetadataBadge label="bestätigt" tone="success" />}
        </div>
      </div>
    </label>
  );
}

function TypeSpecificParameterGuidance({ workspace }: { workspace: WorkspaceView | null }) {
  const sealProfile = workspace?.sealApplicationProfile;
  const questions = workspace?.decisionUnderstanding?.nextBestQuestions ?? [];
  const missingHints = sealProfile?.typeSpecificMissingHints ?? [];
  const visibleQuestions = questions
    .filter((question) => question.question)
    .sort((left, right) => left.priority - right.priority)
    .slice(0, 3);

  if (!workspace || (missingHints.length === 0 && visibleQuestions.length === 0)) {
    return (
      <section className="rounded-[18px] border border-[#E5E7EB] bg-[#FAFAFB] p-4">
        <h3 className="text-sm font-semibold text-[#111827]">Passende Zusatzangaben</h3>
        <p className="mt-1 text-sm leading-relaxed text-[#4B5563]">
          Sobald der Dichtungstyp klarer ist, zeigt SeaLAI hier die Angaben, die für genau diesen Fall wichtig sind.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-[18px] border border-[#D7E5FF] bg-[#F8FBFF] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#111827]">Passende Zusatzangaben</h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Der Parameter-Tab passt sich an den Dichtungstyp an. Hydraulik, Flachdichtung, O-Ring, RWDR und Gleitringdichtung brauchen unterschiedliche Angaben.
          </p>
        </div>
        {sealProfile?.sealType && (
          <MetadataBadge label={technicalFieldLabel(sealProfile.sealType)} tone={sealProfile.ambiguous ? "warning" : "info"} />
        )}
      </div>

      {missingHints.length > 0 && (
        <div className="mt-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Noch offen</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {missingHints.slice(0, 12).map((hint) => (
              <span key={hint} className="rounded-full border border-[#D1D5DB] bg-white px-2.5 py-1 text-[12px] font-semibold text-[#374151]">
                {technicalFieldLabel(hint)}
              </span>
            ))}
          </div>
        </div>
      )}

      {visibleQuestions.length > 0 && (
        <div className="mt-4 grid gap-2">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Nächste sinnvolle Fragen</div>
          {visibleQuestions.map((question) => (
            <div key={`${question.priority}-${question.focusKey}`} className="rounded-[14px] border border-[#E5E7EB] bg-white p-3">
              <div className="text-sm font-semibold leading-relaxed text-[#111827]">{question.question}</div>
              {question.reason && <div className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{question.reason}</div>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ParameterWorkspaceTab({
  workspace,
  isSubmitting = false,
  onSubmit,
}: {
  workspace: WorkspaceView | null;
  isSubmitting?: boolean;
  onSubmit: (overrides: AgentOverrideItemRequest[], summary: string) => Promise<void> | void;
}) {
  const [formState, setFormState] = useState<ParameterFormState>(() => initialState(workspace));
  const [error, setError] = useState<string | null>(null);

  const candidateOverrides = useMemo(
    () =>
      PARAMETER_FIELDS.flatMap((field) => {
        const value = parseValue(field, formState[field.fieldName] ?? "");
        if (value === null) {
          return [];
        }
        return [
          {
            field_name: field.fieldName,
            value,
            unit: field.unit ?? null,
          },
        ];
      }),
    [formState],
  );
  const overrides = useMemo(
    () =>
      candidateOverrides.filter((override) => {
        const field = PARAMETER_FIELDS.find((item) => item.fieldName === override.field_name);
        if (!field) {
          return false;
        }
        return !valuesMatch(field, valueFor(workspace, field.fieldName), override.value as string | number);
      }),
    [candidateOverrides, workspace],
  );
  const hasAnyEnteredValue = PARAMETER_FIELDS.some((field) => Boolean(formState[field.fieldName]?.trim()));

  const canSubmit = Boolean(workspace?.caseId) && hasAnyEnteredValue && !isSubmitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!workspace?.caseId) {
      setError("Bitte zuerst im Chat einen Dichtungsfall starten.");
      return;
    }
    if (!hasAnyEnteredValue) {
      setError("Bitte mindestens einen Parameter eintragen.");
      return;
    }

    const invalidNumber = PARAMETER_FIELDS.find((field) => {
      const raw = formState[field.fieldName]?.trim();
      return field.kind === "number" && raw && parseValue(field, raw) === null;
    });
    if (invalidNumber) {
      setError(`${invalidNumber.label} braucht einen numerischen Wert.`);
      return;
    }
    if (overrides.length === 0) {
      setError("Keine neuen oder geänderten Parameter erkannt.");
      return;
    }

    await onSubmit(overrides, formatSummary(overrides));
  };

  return (
    <form onSubmit={handleSubmit} className="mx-4 mt-4 space-y-4">
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-[#111827]">Angaben direkt eintragen</h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
              Trage Werte ein, die du sicher kennst. SeaLAI übernimmt nur neue oder geänderte Angaben, rechnet abhängige Hinweise neu und hält offene Punkte sichtbar.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-semibold text-[#0B57D0]">
            <Info size={14} />
            Hersteller muss später prüfen
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {PARAMETER_FIELDS.map((field) => (
            <ParameterFieldCard
              key={field.fieldName}
              field={field}
              workspace={workspace}
              formState={formState}
              isSubmitting={isSubmitting}
              onChange={(value) =>
                setFormState((current) => ({
                  ...current,
                  [field.fieldName]: value,
                }))
              }
            />
          ))}
        </div>

        <div className="mt-4">
          <TypeSpecificParameterGuidance workspace={workspace} />
        </div>

        {error && (
          <div className="mt-4 rounded-[12px] border border-[#F7C8C8] bg-[#FDECEC] px-3 py-2 text-sm font-semibold text-[#991B1B]">
            {error}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#F0F2F5] pt-4">
          <button
            type="button"
            onClick={() => {
              setFormState(initialState(workspace));
              setError(null);
            }}
            disabled={isSubmitting}
            className="inline-flex min-h-10 items-center gap-2 rounded-[12px] border border-[#D1D5DB] bg-white px-3 py-2 text-sm font-semibold text-[#4B5563] transition-colors hover:bg-[#F0F2F5] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RotateCcw size={16} />
            Zurücksetzen
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className={cn(
              "inline-flex min-h-10 items-center gap-2 rounded-[12px] px-4 py-2 text-sm font-semibold transition-colors",
              canSubmit
                ? "bg-[#0B57D0] text-white hover:bg-[#0847AD]"
                : "cursor-not-allowed bg-[#F0F2F5] text-[#9CA3AF]",
            )}
          >
            <Save size={16} />
            Als Nutzerangaben übernehmen
          </button>
        </div>
      </section>
    </form>
  );
}
