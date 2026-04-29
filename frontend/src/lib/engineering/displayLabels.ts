const FIELD_LABELS: Record<string, string> = {
  application_requirement: "Anwendungsanforderung",
  atex: "ATEX-Relevanz",
  clarify_sealing_case_need: "Dichtungsfall klären",
  contamination: "Verunreinigung / Partikel",
  counterface_surface: "Gegenlauffläche",
  duty_profile: "Betriebsprofil",
  food_contact: "Lebensmittelkontakt",
  high: "hoch",
  installation: "Einbauort / Anlage",
  low: "niedrig",
  manufacturer_validation_required: "Herstellerprüfung erforderlich",
  mechanical_seal: "Gleitringdichtung",
  medium: "Medium",
  medium_name: "Medium",
  ms_pump: "Gleitringdichtung / Pumpe",
  new_rfq: "Anfragebasis vorbereiten",
  no_technical_case_detected: "technischer Fall noch nicht erkannt",
  precheck_only: "Vorprüfung",
  prequalification: "Vorqualifizierung",
  pressure: "Druck",
  pressure_bar: "Druck",
  pressure_direction: "Druckrichtung",
  pressure_location: "Druck an der Dichtstelle",
  pressure_nominal: "Betriebsdruck",
  pump: "Pumpe",
  rotary: "rotierend",
  rwdr: "RWDR",
  seal_chamber_pressure: "Dichtkammerdruck",
  seal_location: "Dichtstelle",
  seal_type: "Dichtungstyp",
  shaft_diameter: "Wellendurchmesser",
  shaft_diameter_mm: "Wellendurchmesser",
  shaft_sealing: "Wellenabdichtung",
  speed: "Drehzahl",
  speed_rpm: "Drehzahl",
  technical_clarification: "technische Klärung",
  technical_direction_plausible: "technische Richtung plausibel",
  temperature_c: "Temperatur",
  unknown_seal: "Dichtungstyp offen",
};

const RISK_LABELS: Record<string, string> = {
  abrasion_risk: "Abrasion",
  chemical_compatibility_risk: "chemische Verträglichkeit",
  corrosion_risk: "Korrosion",
  dry_run_risk: "Trockenlauf",
  installation_risk: "Einbau",
  pressure_risk: "Druck",
  speed_pv_risk: "Geschwindigkeit / PV",
  surface_risk: "Gegenlauffläche",
  temperature_risk: "Temperatur",
  unknowns_risk: "Unklare Angaben",
};

function isEmptyToken(raw: string) {
  return ["none", "null", "undefined", "nan"].includes(raw.toLowerCase());
}

function objectRiskLabel(value: Record<string, unknown>) {
  const riskName = humanizeDisplayText(value.risk_name ?? value.riskName ?? value.name);
  const label = humanizeDisplayText(value.label);
  const explanation = humanizeDisplayText(value.explanation_short ?? value.explanationShort);
  const missingInputs = value.missing_inputs ?? value.missingInputs;
  const missing = Array.isArray(missingInputs)
    ? missingInputs.map(humanizeDisplayText).filter(Boolean).join(" · ")
    : "";

  const parts = [riskName, label].filter(Boolean).join(": ");
  const detail = explanation || (missing ? `Offen: ${missing}` : "");
  return [parts, detail].filter(Boolean).join(" - ");
}

export function humanizeDisplayText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "object") {
    return objectRiskLabel(value as Record<string, unknown>);
  }

  const raw = String(value).trim();
  if (!raw || isEmptyToken(raw)) {
    return "";
  }

  let result = raw
    .replace(/\bSealType\./g, "")
    .replace(/\bCaseType\./g, "")
    .replace(/\b(\d+(?:[.,]\d+)?)\s*degC\b/g, "$1 °C")
    .replace(/\bmechanical face\b/gi, "Gleitringdichtungsprinzip")
    .replace(/\btechnical direction plausible\b/gi, "technische Richtung plausibel");

  for (const [code, label] of Object.entries({ ...RISK_LABELS, ...FIELD_LABELS })) {
    result = result.replace(new RegExp(`\\b${code}\\b`, "gi"), label);
  }

  return result.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

export function uniqueDisplayItems(items: Array<unknown>, limit = 6): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const item of items) {
    const value = humanizeDisplayText(item);
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    result.push(value);
    if (result.length >= limit) {
      break;
    }
  }

  return result;
}
