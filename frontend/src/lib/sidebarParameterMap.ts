import type { SealParameters } from "@/lib/types/sealParameters";

const SIDEBAR_FORM_PARAMETER_MAP: Record<string, string> = {
  medium: "mediumType",
  medium_type: "mediumType",
  medium_details: "mediumDetails",
  temperature_min: "temperatureMin",
  temperature_max: "temperatureMax",
  speed_rpm: "speedMaxRpm",
  pressure_bar: "maxPressure",
  pressure_max: "maxPressure",
  pressure_min: "maxPressure",
  shaft_diameter: "shaftDiameter",
  housing_diameter: "housingDiameter",
  housing_axial_space: "axialSpace",
  shaft_material: "shaftMaterial",
  shaft_hardness: "shaftHardnessCategory",
};

const SIDEBAR_FORM_FIELD_SET = new Set(Object.values(SIDEBAR_FORM_PARAMETER_MAP));

const stringifyParameterValue = (value: unknown): string | undefined => {
  if (value == null) return undefined;
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : undefined;
  }
  return typeof value === "number" ? String(value) : String(value).trim();
};

export const buildSidebarFormPrefill = (params: SealParameters): Record<string, string> => {
  const prefill: Record<string, string> = {};
  for (const [paramKey, fieldName] of Object.entries(SIDEBAR_FORM_PARAMETER_MAP)) {
    const rawValue = params[paramKey as keyof SealParameters];
    const value = stringifyParameterValue(rawValue);
    if (!value) continue;
    prefill[fieldName] = value;
  }
  return prefill;
};

export const isSidebarFormField = (field: string): field is string =>
  SIDEBAR_FORM_FIELD_SET.has(field);

export const SIDEBAR_FORM_FIELDS = SIDEBAR_FORM_FIELD_SET;
