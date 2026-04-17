export type DataOrigin = string | null;

export type EngineeringPath = 
  | "ms_pump"
  | "rwdr"
  | "static"
  | "labyrinth"
  | "hyd_pneu"
  | "unclear_rotary";

export type EngineeringSectionId =
  | "core_intake"
  | "failure_drivers"
  | "geometry_fit"
  | "rfq_liability";

export interface EngineeringProperty {
  key: string;
  label: string;
  value: any;
  unit?: string;
  origin: DataOrigin;
  confidence?: string | null;
  isConfirmed: boolean;
  isMandatory: boolean;
}

export interface EngineeringSectionCompletion {
  mandatoryPresent: number;
  mandatoryTotal: number;
  percent: number;
}

export interface EngineeringSection {
  id: EngineeringSectionId;
  title: string;
  properties: EngineeringProperty[];
  completion: EngineeringSectionCompletion;
}

export interface EngineeringCheckResult {
  calcId: string;
  label: string;
  formulaVersion: string;
  requiredInputs: string[];
  missingInputs: string[];
  validPaths: EngineeringPath[];
  outputKey: string;
  unit?: string | null;
  status: string;
  value: unknown;
  fallbackBehavior: string;
  guardrails: string[];
  notes: string[];
}

export interface ReadinessState {
  isRfqReady: boolean;
  missingMandatoryKeys: string[];
  blockers: string[];
  status: "preliminary" | "review_needed" | "rfq_ready";
  releaseStatus?: string;
  coverageScore?: number;
}

export interface RoutingMetadata {
  phase?: string | null;
  lastNode?: string | null;
  routing?: Record<string, unknown>;
}

export interface EngineeringCockpitView {
  path: EngineeringPath | null;
  requestType: string;
  routingMetadata?: RoutingMetadata;
  sections: Record<EngineeringSectionId, EngineeringSection>;
  checks: EngineeringCheckResult[];
  readiness: ReadinessState;
  mediumContext: {
    canonicalName: string | null;
    isConfirmed: boolean;
    properties: string[];
    riskFlags: string[];
  };
}

/**
 * Technical Path Requirements
 * Defines which fields are mandatory/hidden for each path.
 */
export const DEFAULT_PATH_RULES = {
  mandatory: ["medium", "temperature_c", "pressure_bar"],
  hidden: [],
};

export const PATH_RULES: Record<EngineeringPath, { mandatory: string[], hidden: string[] }> = {
  ms_pump: {
    mandatory: [
      "medium", "temperature_c", "pressure_bar", "shaft_diameter_mm", "speed_rpm", 
      "motion_type", "installation", "viscosity", "solids_percent", "runout_mm"
    ],
    hidden: []
  },
  rwdr: {
    mandatory: [
      "medium", "temperature_c", "shaft_diameter_mm", "speed_rpm", "shaft_material", "shaft_hardness"
    ],
    hidden: ["pressure_max_bar"]
  },
  static: {
    mandatory: [
      "medium", "temperature_c", "pressure_bar", "geometry_context"
    ],
    hidden: ["speed_rpm", "shaft_diameter_mm", "runout_mm"]
  },
  labyrinth: {
    mandatory: ["shaft_diameter_mm", "speed_rpm", "medium"],
    hidden: ["pressure_bar"]
  },
  hyd_pneu: {
    mandatory: ["medium", "temperature_c", "pressure_bar", "geometry_context"],
    hidden: []
  },
  unclear_rotary: {
    mandatory: ["medium", "motion_type"],
    hidden: []
  }
};
