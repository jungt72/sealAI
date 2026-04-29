export type CockpitTabId =
  | "overview"
  | "parameters"
  | "medium"
  | "application"
  | "material"
  | "calculation"
  | "briefing";

export type CockpitTab = {
  id: CockpitTabId;
  label: string;
};

export type StatusStripItem = {
  label: string;
  value: string;
};

export type ParameterDataRow = {
  label: string;
  value: string;
};

export type CriticalDriver = {
  label: string;
  risk: "Gering" | "Mittel" | "Hoch" | "Offen";
  consequence: string;
};

export type SolutionConsequence = {
  assessmentTitle: string;
  assessment: string;
  rows: Array<{
    label: string;
    value: string;
  }>;
};

export type CalculationEvidenceMetric = {
  label: string;
  value: string;
  limit?: string;
  reserve?: string;
  status: string;
};

export type SealCockpitOverview = {
  tabs: CockpitTab[];
  statusStrip: StatusStripItem[];
  parameters: {
    rows: ParameterDataRow[];
    warning: string;
  };
  criticalDrivers: CriticalDriver[];
  solution: SolutionConsequence;
  calculations: CalculationEvidenceMetric[];
  footerNote: string;
};

export const sealCockpitTabs: CockpitTab[] = [
  { id: "overview", label: "Übersicht" },
  { id: "parameters", label: "Parameter" },
  { id: "medium", label: "Medium" },
  { id: "application", label: "Anwendung" },
  { id: "material", label: "Werkstoff" },
  { id: "calculation", label: "Berechnung" },
  { id: "briefing", label: "Briefing" },
];
