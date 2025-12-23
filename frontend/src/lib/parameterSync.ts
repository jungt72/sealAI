import type { SealParameters } from "@/lib/types/sealParameters";
import { normalizeNumericInput } from "@/lib/normalizeNumericInput";

const NUMERIC_PARAMETER_KEYS = new Set<keyof SealParameters>([
  "pressure_bar",
  "pressure",
  "temperature_C",
  "temperature_max",
  "temperature_min",
  "shaft_diameter",
  "housing_diameter",
  "speed_rpm",
  "d_shaft_nominal",
  "shaft_tolerance",
  "shaft_Ra",
  "shaft_Rz",
  "shaft_runout",
  "d_bore_nominal",
  "housing_tolerance",
  "housing_axial_space",
  "n_min",
  "n_max",
  "v_max",
  "p_min",
  "p_max",
  "T_medium_min",
  "T_medium_max",
  "T_ambient_min",
  "T_ambient_max",
  "nominal_diameter",
  "tolerance",
  "roughness_ra",
  "runout",
  "bore_diameter",
  "axial_plate_axial",
  "pressure_min",
  "pressure_max",
  "temp_min",
  "temp_max",
  "speed_linear",
  "dynamic_runout",
  "mounting_offset",
]);

export type ParameterSyncState = {
  values: SealParameters;
  dirty: Set<keyof SealParameters>;
  lastServerEventId?: string | null;
};

export function mergeServerParameters(
  current: SealParameters,
  incoming: SealParameters,
  dirty: Set<keyof SealParameters>,
): SealParameters {
  const merged: SealParameters = { ...current };
  for (const [key, value] of Object.entries(incoming || {})) {
    const typedKey = key as keyof SealParameters;
    if (dirty.has(typedKey)) continue;
    if (value === undefined) continue;
    merged[typedKey] = value as SealParameters[keyof SealParameters];
  }
  return merged;
}

export function buildDirtyPatch(
  values: SealParameters,
  dirty: Set<keyof SealParameters>,
): Partial<SealParameters> {
  const patch: Partial<SealParameters> = {};
  for (const key of dirty) {
    patch[key] = values[key];
  }
  return patch;
}

export function cleanParameterPatch(patch: Partial<SealParameters>): Partial<SealParameters> {
  const cleaned: Partial<SealParameters> = {};
  for (const [key, value] of Object.entries(patch || {})) {
    const typedKey = key as keyof SealParameters;
    if (value === undefined || value === null) continue;
    if (NUMERIC_PARAMETER_KEYS.has(typedKey)) {
      const normalized = normalizeNumericInput(value);
      if (normalized === undefined) continue;
      cleaned[typedKey] = normalized as SealParameters[keyof SealParameters];
      continue;
    }
    if (typeof value === "string" && !value.trim()) continue;
    cleaned[typedKey] = value as SealParameters[keyof SealParameters];
  }
  return cleaned;
}
