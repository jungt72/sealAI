"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Info, RotateCcw, Save } from "lucide-react";

import type { AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import { humanizeDisplayText } from "@/lib/engineering/displayLabels";
import { cn } from "@/lib/utils";

type ParameterKind = "text" | "number";

type ParameterField = {
  fieldName: string;
  label: string;
  unit?: string;
  kind: ParameterKind;
  placeholder: string;
  detail: string;
  why: string;
};

const PARAMETER_FIELDS: ParameterField[] = [
  {
    fieldName: "medium",
    label: "Medium",
    kind: "text",
    placeholder: "z. B. Ethanol, Salzwasser, Hydrauliköl",
    detail: "Das Medium bestimmt Werkstofffenster, Quellung, Korrosion, Schmierung und offene Herstellerprüfpunkte.",
    why: "Ohne Medium bleibt jede Werkstoff- oder Dichtungstyp-Richtung nur eine Vorqualifikation.",
  },
  {
    fieldName: "temperature_c",
    label: "Temperatur",
    unit: "°C",
    kind: "number",
    placeholder: "z. B. 150",
    detail: "Die Temperatur grenzt Werkstoffe, Medienzustand und thermische Belastung ein.",
    why: "Temperaturspitzen können wichtiger sein als die normale Betriebstemperatur.",
  },
  {
    fieldName: "pressure_bar",
    label: "Druck",
    unit: "bar",
    kind: "number",
    placeholder: "z. B. 10",
    detail: "Der Druck ist nur belastbar, wenn klar ist, ob er direkt an der Dichtstelle anliegt.",
    why: "Bei Pumpen und rotierenden Wellen kann der Dichtstellendruck deutlich vom Systemdruck abweichen.",
  },
  {
    fieldName: "speed_rpm",
    label: "Drehzahl",
    unit: "rpm",
    kind: "number",
    placeholder: "z. B. 1450",
    detail: "Die Drehzahl wird für Umfangsgeschwindigkeit, dynamische Belastung und Berechnungsfähigkeit benötigt.",
    why: "Zusammen mit dem Wellendurchmesser wird daraus eine erste rechnerische Belastungsbasis.",
  },
  {
    fieldName: "shaft_diameter_mm",
    label: "Wellendurchmesser",
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 42",
    detail: "Der Wellendurchmesser ist ein Kernwert für Einbauraum, Dichtungsauswahl und Berechnungen.",
    why: "Ohne Geometrie bleibt eine Anfrage oft nicht herstellerprüfbar genug.",
  },
  {
    fieldName: "installation",
    label: "Anlage / Einbauort",
    kind: "text",
    placeholder: "z. B. Chemiepumpe, Getriebeausgang, Rührwerk",
    detail: "Der Anlagenkontext verhindert vorschnelle Produktlogik und führt die richtige Dichtungsfamilie.",
    why: "Eine Pumpe, ein Getriebe und ein Rührwerk benötigen unterschiedliche Prüfpunkte.",
  },
  {
    fieldName: "sealing_type",
    label: "Dichtungstyp-Richtung",
    kind: "text",
    placeholder: "z. B. RWDR, PTFE-RWDR, Gleitringdichtung",
    detail: "Diese Angabe ist eine Richtung oder vorhandene Vermutung, keine finale technische Freigabe.",
    why: "SeaLAI nutzt sie zur Einordnung, prüft aber weiter gegen Medium, Druck, Geometrie und Anwendung.",
  },
  {
    fieldName: "counterface_surface",
    label: "Gegenlauffläche",
    kind: "text",
    placeholder: "z. B. gehärtete Welle, Ra 0,2 µm, unbekannt",
    detail: "Oberfläche, Härte und Rundlauf beeinflussen Verschleiß, Leckage und Reibung stark.",
    why: "Gerade bei RWDR/PTFE-RWDR ist die Gegenlauffläche häufig ein Herstellerprüfpunkt.",
  },
];

type ParameterFormState = Record<string, string>;

function valueFor(workspace: WorkspaceView | null, fieldName: string): string {
  const value = workspace?.parameters?.[fieldName as keyof WorkspaceView["parameters"]];
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
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
            <h2 className="text-base font-semibold tracking-tight text-[#111827]">Parameter im Fall bearbeiten</h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
              Trage bekannte Werte direkt ein. SeaLAI übernimmt nur neue oder geänderte Angaben in den governed Case-State, berechnet abhängige Hinweise neu und markiert weiter offene Punkte.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-semibold text-[#0B57D0]">
            <Info size={14} />
            Herstellerprüfung bleibt erforderlich
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {PARAMETER_FIELDS.map((field) => (
            <label
              key={field.fieldName}
              className="block rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3"
            >
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
                  value={formState[field.fieldName] ?? ""}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      [field.fieldName]: event.target.value,
                    }))
                  }
                  placeholder={field.placeholder}
                  disabled={isSubmitting}
                  className="min-h-10 w-full rounded-[12px] border border-[#D1D5DB] bg-white px-3 py-2 text-sm font-medium text-[#111827] outline-none transition-colors placeholder:text-[#9CA3AF] focus:border-[#0B57D0]"
                />
              </div>
              <div className="mt-2 grid gap-1 text-[12px] leading-relaxed text-[#6B7280]">
                <span>{field.why}</span>
                <span className="font-medium text-[#4B5563]">{fieldStatus(workspace, field, formState[field.fieldName] ?? "")}</span>
              </div>
            </label>
          ))}
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
