import type { WorkspaceView } from "@/lib/contracts/workspace";
import type {
  CalculationEvidenceMetric,
  CriticalDriver,
  ParameterDataRow,
  SealCockpitOverview,
} from "@/lib/engineering/sealCockpitViewModel";
import { humanizeDisplayText } from "@/lib/engineering/displayLabels";
import { sealCockpitTabs } from "@/lib/engineering/sealCockpitViewModel";

const OPEN_VALUE = "Noch offen";
const MISSING_CALCULATION_VALUE = "Nicht berechenbar";

const EMPTY_PARAMETERS: ParameterDataRow[] = [
  { label: "Medium", value: OPEN_VALUE },
  { label: "Temperatur", value: OPEN_VALUE },
  { label: "Druck", value: OPEN_VALUE },
  { label: "Drehzahl", value: OPEN_VALUE },
  { label: "Wellendurchmesser", value: OPEN_VALUE },
  { label: "Geometrie / Rundlauf", value: OPEN_VALUE },
];

const CALCULATION_DEFINITIONS = [
  {
    label: "Umfangsgeschwindigkeit",
    outputKeys: ["v_surface_m_s"],
    requiredInputs: ["shaft_diameter_mm", "speed_rpm"],
    reason: "Wichtig für Wärmeentwicklung und dynamische Beanspruchung der Dichtkante.",
  },
  {
    label: "PV-Wert",
    outputKeys: ["pv_value_mpa_m_s"],
    requiredInputs: ["pressure_bar", "shaft_diameter_mm", "speed_rpm"],
    reason: "Wichtig, weil Druck und Gleitgeschwindigkeit gemeinsam die Belastung bestimmen.",
  },
  {
    label: "DN-Wert",
    outputKeys: ["dn_value"],
    requiredInputs: ["shaft_diameter_mm", "speed_rpm"],
    reason: "Wichtig zur Einordnung rotierender Dichtstellen gegen Herstellergrenzen.",
  },
  {
    label: "Temperaturfenster",
    outputKeys: ["temperature_window"],
    requiredInputs: ["temperature_c", "medium"],
    reason: "Wichtig, weil Medium und Temperatur die Werkstoffprüfung bestimmen.",
  },
  {
    label: "Druckfenster",
    outputKeys: ["pressure_window"],
    requiredInputs: ["pressure_bar", "sealing_type"],
    reason: "Wichtig, weil Druckrichtung und Bauart die Anfragebasis begrenzen.",
  },
] as const;

function hasDisplayValue(value: unknown): value is string | number {
  return value !== null && value !== undefined && value !== "";
}

function formatValue(value: string | number | null | undefined, unit?: string) {
  if (!hasDisplayValue(value)) {
    return OPEN_VALUE;
  }
  return unit ? `${value} ${unit}` : String(value);
}

function pathLabel(path: string | null | undefined) {
  switch (path) {
    case "rwdr":
      return "Rotierende Welle / RWDR";
    case "ms_pump":
      return "Gleitringdichtung / Pumpe";
    case "static":
      return "Statische Dichtung";
    case "labyrinth":
      return "Labyrinthdichtung";
    case "hyd_pneu":
      return "Hydraulik / Pneumatik";
    case "unclear_rotary":
      return "Rotierende Anwendung, noch einzuordnen";
    default:
      return "Noch nicht eingeordnet";
  }
}

function readableMissingInput(input: string) {
  switch (input) {
    case "medium":
      return "Medium";
    case "temperature_c":
      return "Temperatur";
    case "pressure_bar":
      return "Druck";
    case "speed_rpm":
      return "Drehzahl";
    case "shaft_diameter_mm":
      return "Wellendurchmesser";
    case "sealing_type":
      return "Dichtungsfall";
    default:
      return humanizeDisplayText(input);
  }
}

function buildParameterRows(workspace: WorkspaceView | null): ParameterDataRow[] {
  if (!workspace) {
    return EMPTY_PARAMETERS;
  }

  const parameters = workspace.parameters;
  const geometry = [parameters?.geometry_context, parameters?.tolerances, parameters?.counterface_surface]
    .filter(hasDisplayValue)
    .map(String)
    .join(" · ");

  return [
    { label: "Medium", value: formatValue(workspace.mediumClassification.canonicalLabel ?? parameters?.medium) },
    { label: "Temperatur", value: formatValue(parameters?.temperature_c, "°C") },
    { label: "Druck", value: formatValue(parameters?.pressure_bar, "bar") },
    { label: "Drehzahl", value: formatValue(parameters?.speed_rpm, "rpm") },
    { label: "Wellendurchmesser", value: formatValue(parameters?.shaft_diameter_mm, "mm") },
    { label: "Geometrie / Rundlauf", value: geometry || OPEN_VALUE },
  ];
}

function buildOpenPointSummary(workspace: WorkspaceView | null) {
  if (!workspace) {
    return "Medium · Temperatur · Anwendung · Druck · Drehzahl";
  }

  const gaps = [
    ...workspace.completeness.missingCriticalParameters,
    ...workspace.completeness.coverageGaps,
    ...workspace.rfq.openPoints,
  ]
    .map(readableMissingInput)
    .filter((value, index, values) => value && values.indexOf(value) === index);

  return gaps.length > 0 ? gaps.slice(0, 5).join(" · ") : "Keine kritischen Lücken gemeldet";
}

function buildWarning(workspace: WorkspaceView | null) {
  const openPoints = buildOpenPointSummary(workspace);
  return openPoints === "Keine kritischen Lücken gemeldet" ? "Keine kritischen Lücken aus der Workspace-Projektion gemeldet" : `Kritisch offen: ${openPoints}`;
}

function buildCriticalDrivers(workspace: WorkspaceView | null): CriticalDriver[] {
  if (!workspace) {
    return [
      { label: "Medium", risk: "Offen", consequence: "Medienverträglichkeit kann noch nicht geprüft werden" },
      { label: "Temperatur", risk: "Offen", consequence: "Werkstofffenster ist noch nicht belastbar" },
      { label: "Anwendung", risk: "Offen", consequence: "Dichtungsfall und Herstellerprüfbedarf sind noch offen" },
      { label: "Druck", risk: "Offen", consequence: "Druckfenster kann noch nicht eingeordnet werden" },
      { label: "Drehzahl", risk: "Offen", consequence: "Dynamische Belastung ist noch nicht berechenbar" },
    ];
  }

  const fromGovernance = [
    ...workspace.governance.unknownsBlocking,
    ...workspace.governance.unknownsManufacturerValidation,
    ...workspace.governance.gateFailures,
  ];
  const fromMedium = workspace.mediumContext.challenges;
  const fromQuestions = workspace.manufacturerQuestions.mandatory;
  const drivers = [...fromGovernance, ...fromMedium, ...fromQuestions]
    .filter(Boolean)
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 5);

  if (drivers.length === 0) {
    return [{ label: "Herstellerprüfung", risk: "Offen", consequence: "Keine finalen Freigaben ableiten; Anfragebasis weiter qualifizieren" }];
  }

  return drivers.map((driver) => ({
    label: humanizeDisplayText(driver),
    risk: "Offen",
    consequence: "Für die Herstellerprüfung klären und mit Datenherkunft belegen",
  }));
}

function findConcreteCheck(workspace: WorkspaceView, outputKeys: readonly string[]) {
  return workspace.cockpit?.checks.find(
    (check) => outputKeys.includes(check.outputKey) && check.missingInputs.length === 0 && hasDisplayValue(check.value),
  );
}

function findConcreteDerivation(workspace: WorkspaceView, outputKey: string) {
  const derivation = workspace.technicalDerivations?.find((item) => item.status === "ok");
  if (!derivation) {
    return null;
  }

  switch (outputKey) {
    case "v_surface_m_s":
      return hasDisplayValue(derivation.vSurfaceMPerS) ? `${derivation.vSurfaceMPerS} m/s` : null;
    case "pv_value_mpa_m_s":
      return hasDisplayValue(derivation.pvValueMpaMPerS) ? `${derivation.pvValueMpaMPerS} MPa·m/s` : null;
    case "dn_value":
      return hasDisplayValue(derivation.dnValue) ? `${derivation.dnValue}` : null;
    default:
      return null;
  }
}

function missingInputsFor(workspace: WorkspaceView | null, requiredInputs: readonly string[]) {
  if (!workspace) {
    return requiredInputs.map(readableMissingInput);
  }

  return requiredInputs
    .filter((input) => !hasDisplayValue(workspace.parameters?.[input as keyof WorkspaceView["parameters"]]))
    .map(readableMissingInput);
}

function buildCalculations(workspace: WorkspaceView | null): CalculationEvidenceMetric[] {
  return CALCULATION_DEFINITIONS.map((definition) => {
    if (workspace) {
      const check = findConcreteCheck(workspace, definition.outputKeys);
      if (check) {
        return {
          label: check.label || definition.label,
          value: formatValue(check.value as string | number, check.unit ?? undefined),
          limit: check.notes[0],
          reserve: check.guardrails[0],
          status: check.status,
        };
      }

      for (const outputKey of definition.outputKeys) {
        const value = findConcreteDerivation(workspace, outputKey);
        if (value) {
          return {
            label: definition.label,
            value,
            limit: workspace.technicalDerivations?.[0]?.notes[0],
            status: "backend-berechnet",
          };
        }
      }
    }

    const missingInputs = missingInputsFor(workspace, definition.requiredInputs);
    return {
      label: definition.label,
      value: MISSING_CALCULATION_VALUE,
      limit: `Fehlende Eingaben: ${missingInputs.join(" · ")}`,
      reserve: definition.reason,
      status: "offen",
    };
  });
}

function countLoadBearingCalculations(calculations: CalculationEvidenceMetric[]) {
  return calculations.filter((calculation) => calculation.value !== MISSING_CALCULATION_VALUE).length;
}

function coveragePercent(workspace: WorkspaceView | null) {
  if (!workspace) {
    return 0;
  }
  return workspace.completeness.coveragePercent || Math.round(workspace.completeness.coverageScore * 100) || 0;
}

function buildSolution(workspace: WorkspaceView | null): SealCockpitOverview["solution"] {
  if (!workspace) {
    return {
      assessmentTitle: "Anfragebasis noch offen",
      assessment: "Der Dichtungsfall ist noch nicht eingeordnet. SeaLAI kann erst mit belastbaren Eingaben eine Herstellerprüfungsbasis vorbereiten.",
      rows: [
        { label: "Lösungsraum", value: OPEN_VALUE },
        { label: "Was noch geprüft werden muss", value: "Medium, Temperatur, Anwendung, Druck und Drehzahl" },
        { label: "Nächster Schritt", value: "Erste Betriebsdaten erfassen und als Case-Felder qualifizieren" },
      ],
    };
  }

  const direction =
    workspace.deepDiveTabs.find((tab) => tab.derivedDirection)?.derivedDirection ||
    workspace.communication?.supportingReason ||
    "Noch keine belastbare technische Richtung aus der Workspace-Projektion";

  return {
    assessmentTitle: "Vorläufige Einordnung",
    assessment: humanizeDisplayText(direction),
    rows: [
      { label: "Lösungsraum", value: workspace.engineeringPath ? pathLabel(workspace.engineeringPath) : OPEN_VALUE },
      { label: "Was noch geprüft werden muss", value: buildOpenPointSummary(workspace) },
      {
        label: "Herstellerfrage",
        value: workspace.manufacturerQuestions.mandatory[0] ?? workspace.communication?.primaryQuestion ?? "Herstellerprüfbedarf noch nicht konkretisiert",
      },
    ],
  };
}

export function buildSealCockpitViewModel(workspace: WorkspaceView | null): SealCockpitOverview {
  const calculations = buildCalculations(workspace);
  const calculationCount = countLoadBearingCalculations(calculations);
  const openPointSummary = buildOpenPointSummary(workspace);
  const solution = buildSolution(workspace);

  return {
    tabs: sealCockpitTabs,
    statusStrip: [
      { label: "Dichtungsfall", value: workspace ? pathLabel(workspace.engineeringPath) : "Noch nicht eingeordnet" },
      { label: "Datenreife", value: `${coveragePercent(workspace)} % belastbar` },
      { label: "Lösungsraum", value: workspace ? solution.rows[0]?.value ?? OPEN_VALUE : OPEN_VALUE },
      { label: "Kritische Lücken", value: openPointSummary },
      { label: "Berechnungsstatus", value: `${calculationCount} von ${CALCULATION_DEFINITIONS.length} Nachweisen belastbar` },
    ],
    parameters: {
      rows: buildParameterRows(workspace),
      warning: buildWarning(workspace),
    },
    criticalDrivers: buildCriticalDrivers(workspace),
    solution,
    calculations,
    footerNote:
      "SeaLAI erklärt den aktuellen Arbeitsstand, macht offene Punkte sichtbar und bereitet eine Anfragebasis für Herstellerprüfung vor.",
  };
}
