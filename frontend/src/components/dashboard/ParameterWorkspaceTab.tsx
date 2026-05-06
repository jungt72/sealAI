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
    placeholder: "z. B. RWDR, Gleitringdichtung, O-Ring",
    detail: "Diese Angabe ist nur eine Richtung oder vorhandene Vermutung.",
    why: "SealingAI nutzt sie zur Einordnung, prüft aber weiter gegen Medium, Druck, Geometrie und Anwendung.",
  },
  {
    fieldName: "counterface_surface",
    label: "Gegenlauffläche",
    kind: "text",
    placeholder: "z. B. gehärtete Welle, Ra 0,2 µm, unbekannt",
    detail: "Oberfläche, Härte und Rundlauf beeinflussen Verschleiß, Leckage und Reibung.",
    why: "Gerade bei dynamischen Dichtstellen ist die Gegenlauffläche häufig ein Herstellerprüfpunkt.",
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
  rod_or_piston_diameter: ["rod_diameter", "piston_diameter", "shaft_diameter"],
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

const TYPE_SPECIFIC_FIELD_DETAILS: Record<string, Partial<ParameterField>> = {
  flange_standard: {
    placeholder: "z. B. EN 1092-1, ASME B16.5, Zeichnung",
    detail: "Norm oder Flanschfamilie grenzt die Geometrie der Flachdichtung ein.",
    why: "Ohne Anschlussnorm bleibt die Dichtung nur grob beschreibbar.",
  },
  flange_size_or_dimensions: {
    placeholder: "z. B. DN50 PN16, NPS 2 Class 150",
    detail: "Flanschgröße oder Zeichnungsmaß macht die Anfrage eindeutig.",
    why: "Hersteller brauchen diese Angabe, um Abmessungen und Bauform einzugrenzen.",
  },
  inner_outer_diameter: {
    placeholder: "z. B. 54 x 92 mm",
    detail: "Innen- und Außendurchmesser beschreiben die reale Dichtungsgeometrie.",
    why: "Diese Maße verhindern Verwechslungen bei Flach- und Profildichtungen.",
  },
  hole_pattern: {
    placeholder: "z. B. 4 x Ø18 auf TK 125",
    detail: "Das Lochbild ist bei Flanschdichtungen oft ein entscheidendes Zeichnungsmerkmal.",
    why: "Material allein reicht bei gelochten Dichtungen nicht aus.",
  },
  gasket_material: {
    placeholder: "z. B. PTFE, Graphit, Faserstoff",
    detail: "Das aktuelle oder gewünschte Material ist ein Prüfpunkt, kein Ergebnisversprechen.",
    why: "Material muss gegen Medium, Temperatur, Druck und Nachweise geprüft werden.",
  },
  thickness: {
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 2",
    detail: "Die Dicke beeinflusst Verpressung und Austauschbarkeit.",
    why: "Gerade bei Ersatzfällen ist die vorhandene Dicke oft wichtig.",
  },
  bolt_load_or_torque: {
    placeholder: "z. B. 80 Nm, unbekannt, Montage nach Betreiberstandard",
    detail: "Montagekraft oder Drehmoment beeinflusst die Dichtpressung.",
    why: "Flachdichtungen können ohne Montagekontext nicht sauber eingeordnet werden.",
  },
  surface_roughness: {
    placeholder: "z. B. Ra 3,2, glatte Dichtfläche, unbekannt",
    detail: "Die Dichtflächen bestimmen mit, ob die Dichtung sinnvoll arbeiten kann.",
    why: "Oberfläche und Beschädigungen sind häufige Leckageursachen.",
  },
  certification_requirement: {
    placeholder: "z. B. FDA, ATEX, TA-Luft, Trinkwasser",
    detail: "Nachweise werden als Prüfpunkte erfasst, nicht als SeaLAI-Zusage.",
    why: "Regulierte Anforderungen gehören sichtbar in die Herstellerklärung.",
  },
  rod_or_piston_diameter: {
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 40",
    detail: "Stangen- oder Kolbendurchmesser ist der Geometrieanker für Zylinderdichtungen.",
    why: "Hydraulik- und Pneumatikprofile hängen stark vom Durchmesser ab.",
  },
  groove_dimensions: {
    placeholder: "z. B. Nut 40 x 48 x 6 oder Zeichnung vorhanden",
    detail: "Nut und Einbauraum entscheiden, welche Profile überhaupt prüfbar sind.",
    why: "Ohne Nutdaten bleibt die Anfrage für Hydraulik, Pneumatik und O-Ring zu offen.",
  },
  pressure_peaks: {
    unit: "bar",
    kind: "number",
    placeholder: "z. B. 250",
    detail: "Druckspitzen können kritischer sein als der normale Betriebsdruck.",
    why: "Sie beeinflussen Extrusionsrisiko und Stützringbedarf.",
  },
  hydraulic_fluid: {
    placeholder: "z. B. HLP 46, HFC, biologisches Öl",
    detail: "Das Hydraulikmedium beeinflusst Werkstoff, Quellung und Verschleiß.",
    why: "Hydraulikdichtungen brauchen die Fluidangabe getrennt vom Druck.",
  },
  speed_or_stroke: {
    placeholder: "z. B. 0,3 m/s, Hub 500 mm, langsam taktend",
    detail: "Hub und Geschwindigkeit beschreiben die dynamische Beanspruchung.",
    why: "Lineare Dichtungen werden anders bewertet als rotierende Wellen.",
  },
  single_or_double_acting: {
    placeholder: "z. B. doppeltwirkend, einfachwirkend, unklar",
    detail: "Die Wirkweise bestimmt Druckrichtung und Dichtungsanordnung.",
    why: "Sie ist für Zylinderdichtungen oft früher wichtig als Materialdetails.",
  },
  wiper_or_guide_required: {
    placeholder: "z. B. Abstreifer vorhanden, Führung verschlissen",
    detail: "Abstreifer, Führung und Stützringe gehören bei Zylindern oft zum Problem.",
    why: "Leckage oder Ausfall entsteht nicht immer an der Hauptdichtung allein.",
  },
  water_content: {
    placeholder: "z. B. Kondensat, Wasser im Öl, stark verschmutzt",
    detail: "Wasser und Schmutz verschieben das Risiko in Richtung Verschleiß und Korrosion.",
    why: "Diese Angaben helfen, den Fall nicht zu simpel zu behandeln.",
  },
  air_quality: {
    placeholder: "z. B. trocken, geölt, Kondensat, Partikel",
    detail: "Druckluftqualität prägt Reibung und Lebensdauer bei Pneumatik.",
    why: "Pneumatik ist nicht einfach Hydraulik mit niedrigerem Druck.",
  },
  lubrication: {
    placeholder: "z. B. trockenlaufend, geölte Luft, Fett",
    detail: "Schmierung beeinflusst Reibung, Losbrechkraft und Verschleiß.",
    why: "Bei Pneumatikdichtungen ist diese Angabe besonders wichtig.",
  },
  friction_requirement: {
    placeholder: "z. B. geringe Losbrechkraft, schnelle Bewegung",
    detail: "Reibungsanforderungen beeinflussen Profil- und Werkstoffrichtung.",
    why: "Dichtheit allein beschreibt Pneumatikfälle oft nicht ausreichend.",
  },
  pump_or_aggregate_type: {
    placeholder: "z. B. Kreiselpumpe, Rührwerk, Seitenkanalpumpe",
    detail: "Das Aggregat bestimmt, welche Gleitringdichtungsdaten relevant werden.",
    why: "Eine Gleitringdichtung wird nicht ohne Pumpen-/Aggregatkontext bewertet.",
  },
  flush_or_barrier_fluid: {
    placeholder: "z. B. keine Spülung, Plan 11, Sperrflüssigkeit",
    detail: "Spülung oder Barriere beeinflusst Aufbau und Prüfbarkeit der Gleitringdichtung.",
    why: "Bei Pumpenfällen ist das oft ein zentraler Herstellerpunkt.",
  },
  solids_or_gas_content: {
    placeholder: "z. B. Feststoffe, Gasanteil, kristallisierend",
    detail: "Feststoffe, Gas und Kristallisation sind frühe Risikotreiber.",
    why: "Sie können die Dichtungsrichtung stärker verändern als ein einzelner Druckwert.",
  },
  viscosity: {
    placeholder: "z. B. niedrigviskos, 120 mPa·s, gasförmig",
    detail: "Viskosität und Medienzustand helfen, den Betriebsfall einzuordnen.",
    why: "Gleitringdichtungen reagieren stark auf Mediumzustand und Schmierung.",
  },
  atex_or_leakage_requirement: {
    placeholder: "z. B. ATEX Zone 1, minimale Leckage, unklar",
    detail: "ATEX- und Leckageanforderungen werden als Prüfpunkte dokumentiert.",
    why: "SeaLAI markiert sie, gibt aber keine Konformität frei.",
  },
  inner_diameter: {
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 40",
    detail: "Der Innendurchmesser ist eine Grundangabe für O-/X-Ringe.",
    why: "Ohne ID und Schnurstärke ist der Ring nicht eindeutig.",
  },
  cross_section: {
    unit: "mm",
    kind: "number",
    placeholder: "z. B. 3,53",
    detail: "Die Schnurstärke bestimmt Verpressung und Nutraum.",
    why: "Sie ist für O-Ring-Fälle genauso wichtig wie der Innendurchmesser.",
  },
  material: {
    placeholder: "z. B. FKM 75, EPDM, NBR, PTFE",
    detail: "Werkstoffangaben bleiben Prüfpunkte und werden nicht automatisch als passend bewertet.",
    why: "Der Werkstoff muss zum Medium und Temperaturfenster passen.",
  },
  hardness: {
    placeholder: "z. B. 75 Shore A",
    detail: "Härte beeinflusst Montage, Verpressung und Extrusionsverhalten.",
    why: "Elastomerdichtungen brauchen oft Härte und Material zusammen.",
  },
  static_or_dynamic: {
    placeholder: "z. B. statisch, dynamisch, oszillierend",
    detail: "Bewegung verändert Nut, Verpressung und Reibungsbewertung.",
    why: "Ein statischer O-Ring ist ein anderer Fall als ein dynamischer.",
  },
  squeeze_or_stretch: {
    placeholder: "z. B. 18 % Verpressung, Dehnung unbekannt",
    detail: "Verpressung und Dehnung zeigen, ob Geometrie und Nut plausibel sind.",
    why: "Diese Werte sind für O-Ring-Prüfung deutlich aussagekräftiger als nur das Material.",
  },
  backup_ring_required: {
    placeholder: "z. B. vorhanden, wegen 120 bar prüfen",
    detail: "Stützringe können bei Druck und Spalt ein Extrusionsschutz sein.",
    why: "SeaLAI soll diesen Punkt sichtbar machen, nicht still übergehen.",
  },
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

const BASE_FIELD_NAMES = new Set(PARAMETER_FIELDS.map((field) => field.fieldName));

function parameterFieldForHint(hint: string): ParameterField | null {
  const code = normalizeCode(hint);
  if (!code || BASE_FIELD_NAMES.has(code)) {
    return null;
  }
  const details = TYPE_SPECIFIC_FIELD_DETAILS[code];
  if (!details) {
    return null;
  }
  return {
    fieldName: code,
    label: technicalFieldLabel(code),
    unit: details.unit,
    kind: details.kind ?? "text",
    placeholder: details.placeholder ?? "Angabe eintragen",
    detail: details.detail ?? "Diese Angabe hilft, den Fall genauer einzuordnen.",
    why: details.why ?? "SealingAI übernimmt die Angabe als Nutzerangabe und hält Herstellerprüfung sichtbar.",
  };
}

function typeSpecificParameterFields(workspace: WorkspaceView | null): ParameterField[] {
  const hints = workspace?.sealApplicationProfile?.typeSpecificMissingHints ?? [];
  const seen = new Set<string>();
  return hints
    .flatMap((hint) => {
      const field = parameterFieldForHint(hint);
      if (!field || seen.has(field.fieldName)) {
        return [];
      }
      seen.add(field.fieldName);
      return [field];
    })
    .slice(0, 8);
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

function initialState(workspace: WorkspaceView | null, fields: ParameterField[] = PARAMETER_FIELDS): ParameterFormState {
  return Object.fromEntries(
    fields.map((field) => [field.fieldName, valueFor(workspace, field.fieldName)]),
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

function formatSummary(overrides: AgentOverrideItemRequest[], fields: ParameterField[]) {
  return overrides
    .map((override) => {
      const field = fields.find((item) => item.fieldName === override.field_name);
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
            Der Parameter-Tab passt sich an den Dichtungstyp an. Hydraulik, Flachdichtung, O-Ring, RWDR und Gleitringdichtung brauchen unterschiedliche Angaben. Was SealingAI direkt verarbeiten kann, erscheint unten als Eingabefeld.
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
  const typeSpecificFields = useMemo(() => typeSpecificParameterFields(workspace), [workspace]);
  const editableFields = useMemo(() => {
    const seen = new Set<string>();
    return [...PARAMETER_FIELDS, ...typeSpecificFields].filter((field) => {
      if (seen.has(field.fieldName)) {
        return false;
      }
      seen.add(field.fieldName);
      return true;
    });
  }, [typeSpecificFields]);
  const [formState, setFormState] = useState<ParameterFormState>(() => initialState(workspace, editableFields));
  const [error, setError] = useState<string | null>(null);

  const candidateOverrides = useMemo(
    () =>
      editableFields.flatMap((field) => {
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
    [editableFields, formState],
  );
  const overrides = useMemo(
    () =>
      candidateOverrides.filter((override) => {
        const field = editableFields.find((item) => item.fieldName === override.field_name);
        if (!field) {
          return false;
        }
        return !valuesMatch(field, valueFor(workspace, field.fieldName), override.value as string | number);
      }),
    [candidateOverrides, editableFields, workspace],
  );
  const hasAnyEnteredValue = editableFields.some((field) => Boolean(formState[field.fieldName]?.trim()));

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

    const invalidNumber = editableFields.find((field) => {
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

    await onSubmit(overrides, formatSummary(overrides, editableFields));
  };

  return (
    <form onSubmit={handleSubmit} className="mx-4 mt-4 space-y-4">
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-[#111827]">Angaben direkt eintragen</h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
              Trage Werte ein, die du sicher kennst. SealingAI übernimmt neue oder geänderte Angaben, rechnet abhängige Hinweise neu und hält offene Punkte sichtbar.
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

        {typeSpecificFields.length > 0 && (
          <section className="mt-4 rounded-[18px] border border-[#D7E5FF] bg-[#F8FBFF] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-[#111827]">Zusatzangaben für diesen Dichtungstyp</h3>
                <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
                  Diese Felder kommen aus dem aktuellen Dichtungstyp-Profil. Trage nur ein, was du wirklich weißt.
                </p>
              </div>
              <MetadataBadge label={`${typeSpecificFields.length} Felder`} tone="info" />
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
              {typeSpecificFields.map((field) => (
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
          </section>
        )}

        {error && (
          <div className="mt-4 rounded-[12px] border border-[#F7C8C8] bg-[#FDECEC] px-3 py-2 text-sm font-semibold text-[#991B1B]">
            {error}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#F0F2F5] pt-4">
          <button
            type="button"
            onClick={() => {
              setFormState(initialState(workspace, editableFields));
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
