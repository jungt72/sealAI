const FIELD_LABELS: Record<string, string> = {
  application_requirement: "Anwendungsanforderung",
  atex: "ATEX-Relevanz",
  atex_relevance: "ATEX-Relevanz",
  clarify_sealing_case_need: "Dichtungsfall klären",
  contamination: "Verunreinigung / Partikel",
  counterface_surface: "Gegenlauffläche",
  dynamic: "dynamisch",
  duty_profile: "Betriebsprofil",
  food_contact: "Lebensmittelkontakt",
  geometry: "Geometrie",
  high: "hoch",
  housing_bore: "Gehäusebohrung",
  housing_bore_mm: "Gehäusebohrung",
  installation: "Einbauort / Anlage",
  installation_direction: "Einbaurichtung",
  low: "niedrig",
  manufacturer_validation_required: "Hersteller muss prüfen",
  mechanical_face: "Gleitringdichtungsprinzip",
  mechanical_seal: "Gleitringdichtung",
  medium: "Medium",
  medium_name: "Medium",
  ms_pump: "Gleitringdichtung / Pumpe",
  new_rfq: "Anfragebasis vorbereiten",
  no_technical_case_detected: "technischer Fall noch nicht erkannt",
  normal: "normal",
  precheck_only: "Vorprüfung",
  prequalification: "Vorqualifizierung",
  pressure: "Druck",
  pressure_bar: "Druck",
  pressure_direction: "Druckrichtung",
  pressure_interpretation: "Druckangabe",
  pressure_location: "Druck an der Dichtstelle",
  pressure_nominal: "Betriebsdruck",
  pump: "Pumpe",
  radial_shaft_seal: "Radialwellendichtring",
  readiness: "Anfrage-Reife",
  rfq_preparable_with_open_points: "RFQ mit offenen Punkten vorbereitbar",
  rotary: "rotierend",
  rotary_shaft: "rotierende Welle",
  rwdr: "RWDR",
  seal_chamber_pressure: "Dichtkammerdruck",
  seal_location: "Dichtstelle",
  seal_type: "Dichtungstyp",
  shaft_diameter: "Wellendurchmesser",
  shaft_diameter_mm: "Wellendurchmesser",
  shaft_sealing: "Wellenabdichtung",
  shaft_surface: "Gegenlauffläche",
  speed: "Drehzahl",
  speed_rpm: "Drehzahl",
  static: "statisch",
  static_or_dynamic: "statisch oder dynamisch",
  technical_clarification: "Fall klären",
  technical_direction_plausible: "Richtung ist plausibel",
  temperature: "Temperatur",
  temperature_c: "Temperatur",
  unknown: "unklar",
  unknown_seal: "Dichtungstyp offen",
  width: "Einbaubreite",
  width_mm: "Einbaubreite",
};

const RISK_LABELS: Record<string, string> = {
  abrasion_risk: "Abrasion",
  "abrasion risk": "Abrasion",
  chemical_compatibility_risk: "chemische Verträglichkeit",
  corrosion_risk: "Korrosion",
  "corrosion risk": "Korrosion",
  dry_run_risk: "Trockenlauf",
  installation_risk: "Einbau",
  pressure_risk: "Druck",
  "pressure risk": "Druck",
  speed_pv_risk: "Geschwindigkeit / PV",
  "speed pv risk": "Geschwindigkeit / PV",
  surface_risk: "Gegenlauffläche",
  temperature_risk: "Temperatur",
  "temperature risk": "Temperatur",
  unknowns_risk: "Unklare Angaben",
  "unknowns risk": "Unklare Angaben",
};

const GERMAN_ASCII_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bGegenlaufflaechen\b/g, "Gegenlaufflächen"],
  [/\bGegenlaufflaeche\b/g, "Gegenlauffläche"],
  [/\bgegenlaufflaechen\b/g, "Gegenlaufflächen"],
  [/\bgegenlaufflaeche\b/g, "Gegenlauffläche"],
  [/\bOberflaechen\b/g, "Oberflächen"],
  [/\bOberflaeche\b/g, "Oberfläche"],
  [/\boberflaechen\b/g, "Oberflächen"],
  [/\boberflaeche\b/g, "Oberfläche"],
  [/\bDichtflaechen\b/g, "Dichtflächen"],
  [/\bDichtflaeche\b/g, "Dichtfläche"],
  [/\bHaerte\b/g, "Härte"],
  [/\bhaerte\b/g, "Härte"],
  [/\bHuelse\b/g, "Hülse"],
  [/\bhuelse\b/g, "Hülse"],
  [/\bVerschleiss\b/g, "Verschleiß"],
  [/\bverschleiss\b/g, "Verschleiß"],
  [/\bWaermeeintrag\b/g, "Wärmeeintrag"],
  [/\bWaerme\b/g, "Wärme"],
  [/\bwaerme\b/g, "Wärme"],
  [/\bRuehrwerk(e|en)?\b/g, "Rührwerk$1"],
  [/\bruehrwerk(e|en)?\b/g, "Rührwerk$1"],
  [/\bBehaelter\b/g, "Behälter"],
  [/\bbehaelter\b/g, "Behälter"],
  [/\bExzentrizitaet\b/g, "Exzentrizität"],
  [/\bexzentrizitaet\b/g, "Exzentrizität"],
  [/\bEntzuendung\b/g, "Entzündung"],
  [/\bIdentitaet\b/g, "Identität"],
  [/\bOel\b/g, "Öl"],
  [/\boel\b/g, "Öl"],
  [/\bFuer\b/g, "Für"],
  [/\bfuer\b/g, "für"],
  [/\bUeber\b/g, "Über"],
  [/\bueber\b/g, "über"],
  [/\bDafuer\b/g, "Dafür"],
  [/\bdafuer\b/g, "dafür"],
  [/Pruef/g, "Prüf"],
  [/pruef/g, "prüf"],
  [/Klaer/g, "Klär"],
  [/klaer/g, "klär"],
  [/Bestaet/g, "Bestät"],
  [/bestaet/g, "bestät"],
  [/Unbestaet/g, "Unbestät"],
  [/unbestaet/g, "unbestät"],
  [/\bNaechst/g, "Nächst"],
  [/\bnaechst/g, "nächst"],
  [/\blaesst\b/g, "lässt"],
  [/\bLaesst\b/g, "Lässt"],
  [/\bhaengt\b/g, "hängt"],
  [/\bHaengt\b/g, "Hängt"],
  [/\bwaere\b/g, "wäre"],
  [/\bWaere\b/g, "Wäre"],
  [/\bfrueh\b/g, "früh"],
  [/\bFrueh\b/g, "Früh"],
  [/\bgehoert\b/g, "gehört"],
  [/\bGehoert\b/g, "Gehört"],
  [/\bmuessen\b/g, "müssen"],
  [/\bMuessen\b/g, "Müssen"],
  [/\bzulaessig/g, "zulässig"],
  [/\bZulaessig/g, "Zulässig"],
  [/\bqualitaet\b/g, "qualität"],
  [/\bQualitaet\b/g, "Qualität"],
  [/\bLoesung/g, "Lösung"],
  [/\bloesung/g, "lösung"],
];

export function normalizeGermanVisibleText(value: string): string {
  return GERMAN_ASCII_REPLACEMENTS.reduce(
    (current, [pattern, replacement]) => current.replace(pattern, replacement),
    value,
  );
}

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
  if ((raw.includes("risk name") || raw.includes("risk_name")) && raw.includes("explanation")) {
    return humanizeRiskString(raw);
  }

  let result = normalizeGermanVisibleText(raw)
    .replace(/\bSealType\./g, "")
    .replace(/\bCaseType\./g, "")
    .replace(/\b(\d+(?:[.,]\d+)?)\s*degC\b/g, "$1 °C")
    .replace(/\bmechanical face\b/gi, "Gleitringdichtungsprinzip")
    .replace(/\bradial shaft seal\b/gi, "Radialwellendichtring")
    .replace(/\brotary shaft\b/gi, "rotierende Welle")
    .replace(/\bstatic or dynamic\b/gi, "statisch oder dynamisch")
    .replace(/\bshaft surface\b/gi, "Gegenlauffläche")
    .replace(/\binstallation direction\b/gi, "Einbaurichtung")
    .replace(/\bpressure interpretation\b/gi, "Druckangabe")
    .replace(/\brfq preparable with open points\b/gi, "RFQ mit offenen Punkten vorbereitbar")
    .replace(/\btechnical direction plausible\b/gi, "Richtung ist plausibel")
    .replace(/\bkeine finale technische freigabe\b/gi, "keine Auslegungsfreigabe")
    .replace(/\bfinale technische freigabe\b/gi, "Auslegungsfreigabe");

  for (const [code, label] of Object.entries({ ...RISK_LABELS, ...FIELD_LABELS })) {
    result = result.replace(new RegExp(`\\b${code}\\b`, "gi"), label);
  }

  return result.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

function firstQuotedField(raw: string, field: string) {
  const single = new RegExp(`'${field}'\\s*:\\s*'([^']*)'`).exec(raw);
  if (single?.[1]) {
    return single[1];
  }
  const double = new RegExp(`"${field}"\\s*:\\s*"([^"]*)"`).exec(raw);
  return double?.[1] || "";
}

function firstListField(raw: string, field: string) {
  const single = new RegExp(`'${field}'\\s*:\\s*\\[([^\\]]*)\\]`).exec(raw);
  const double = new RegExp(`"${field}"\\s*:\\s*\\[([^\\]]*)\\]`).exec(raw);
  const content = single?.[1] || double?.[1] || "";
  return content
    .split(",")
    .map((item) => item.replace(/['"]/g, "").trim())
    .filter(Boolean);
}

function humanizeRiskString(raw: string) {
  const riskName = humanizeDisplayText(firstQuotedField(raw, "risk name") || firstQuotedField(raw, "risk_name"));
  const label = humanizeDisplayText(firstQuotedField(raw, "label"));
  const explanation = humanizeDisplayText(firstQuotedField(raw, "explanation short") || firstQuotedField(raw, "explanation_short"));
  const missing = [
    ...firstListField(raw, "missing inputs"),
    ...firstListField(raw, "missing_inputs"),
  ].map(humanizeDisplayText).filter(Boolean);

  const headline = [riskName, label].filter(Boolean).join(": ");
  const detail = explanation || (missing.length ? `Offen: ${missing.join(" · ")}` : "");
  return [headline, detail].filter(Boolean).join(" - ");
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
