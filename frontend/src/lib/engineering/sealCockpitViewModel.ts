export type CockpitTabId =
  | "overview"
  | "parameters"
  | "rfq"
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
  compatibilityStatus?: string;
  evidenceStatus?: string;
  evidenceRefs?: Array<{
    refId?: string;
    cardId?: string;
    sourceTitle?: string;
    sourceType?: string;
    claimLevel?: string;
    material?: string;
    medium?: string;
    excerptShort?: string;
    limitations?: string[];
  }>;
  evidenceSummary?: string;
  evidenceLimitations?: string[];
  missingFields?: string[];
  ambiguousFields?: string[];
  finalApprovalClaimAllowed?: boolean;
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
  { id: "rfq", label: "Anfragebasis" },
  { id: "medium", label: "Medium" },
  { id: "application", label: "Anwendung" },
  { id: "material", label: "Werkstoff" },
  { id: "calculation", label: "Berechnung" },
  { id: "briefing", label: "Briefing" },
];
