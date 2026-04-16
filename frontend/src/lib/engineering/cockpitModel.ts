export type DataOrigin = "user" | "inferred" | "medium_registry" | "missing";

export type EngineeringPath = 
  | "mechanical_seal_pump" 
  | "radial_shaft_seal" 
  | "static_seal" 
  | "labyrinth_non_contact" 
  | "unclear_rotary"
  | "standard";

export interface EngineeringProperty {
  key: string;
  label: string;
  value: any;
  unit?: string;
  origin: DataOrigin;
  isConfirmed: boolean;
  isMandatory: boolean;
  isHidden: boolean;
  riskFlags: string[];
}

export interface EngineeringSection {
  id: string;
  title: string;
  properties: EngineeringProperty[];
  completeness: number; // 0-1
}

export interface ReadinessState {
  isRfqReady: boolean;
  missingMandatoryKeys: string[];
  blockers: string[];
  status: "preliminary" | "review_needed" | "rfq_ready";
}

export interface EngineeringCockpitView {
  path: EngineeringPath;
  sections: Record<string, EngineeringSection>;
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
export const PATH_RULES: Record<EngineeringPath, { mandatory: string[], hidden: string[] }> = {
  mechanical_seal_pump: {
    mandatory: [
      "medium", "temperature_c", "pressure_bar", "shaft_diameter_mm", "speed_rpm", 
      "motion_type", "installation", "viscosity", "solids_percent", "runout_mm"
    ],
    hidden: []
  },
  radial_shaft_seal: {
    mandatory: [
      "medium", "temperature_c", "shaft_diameter_mm", "speed_rpm", "shaft_material", "shaft_hardness"
    ],
    hidden: ["pressure_max_bar"]
  },
  static_seal: {
    mandatory: [
      "medium", "temperature_c", "pressure_bar", "geometry_context"
    ],
    hidden: ["speed_rpm", "shaft_diameter_mm", "runout_mm"]
  },
  labyrinth_non_contact: {
    mandatory: ["shaft_diameter_mm", "speed_rpm", "medium"],
    hidden: ["pressure_bar"]
  },
  unclear_rotary: {
    mandatory: ["medium", "motion_type"],
    hidden: []
  },
  standard: {
    mandatory: ["medium", "temperature_c", "pressure_bar"],
    hidden: []
  }
};
