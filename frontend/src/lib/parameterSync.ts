import type { SealParameters } from "@/lib/types/sealParameters";
import { normalizeNumericInput } from "@/lib/normalizeNumericInput";
import { emit } from "@/lib/telemetry";
import { dbg, isParamSyncDebug } from "@/lib/paramSyncDebug";

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
  pending: Set<keyof SealParameters>;
  applied?: Partial<Record<keyof SealParameters, number>>;
  lastServerEventId?: string | null;
};

function normalizeParamValue(
  key: keyof SealParameters,
  value: SealParameters[keyof SealParameters] | undefined,
): SealParameters[keyof SealParameters] | undefined {
  if (value === undefined || value === null) return value;
  if (NUMERIC_PARAMETER_KEYS.has(key)) {
    const normalized = normalizeNumericInput(value);
    return normalized === undefined ? value : (normalized as SealParameters[keyof SealParameters]);
  }
  if (typeof value === "string") return value.trim() as SealParameters[keyof SealParameters];
  return value;
}

export function areParamValuesEquivalent(
  key: keyof SealParameters,
  left: SealParameters[keyof SealParameters] | undefined,
  right: SealParameters[keyof SealParameters] | undefined,
): boolean {
  const normalizedLeft = normalizeParamValue(key, left);
  const normalizedRight = normalizeParamValue(key, right);
  if (normalizedLeft === undefined || normalizedRight === undefined) return false;
  return Object.is(normalizedLeft, normalizedRight);
}

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

export function reconcileDirtyWithServer(
  current: SealParameters,
  incoming: SealParameters,
  dirty: Set<keyof SealParameters>,
  pending?: Set<keyof SealParameters>,
): Set<keyof SealParameters> {
  const nextDirty = new Set(dirty);
  for (const [key, value] of Object.entries(incoming || {})) {
    const typedKey = key as keyof SealParameters;
    if (!nextDirty.has(typedKey)) continue;
    if (value === undefined) continue;
    const equivalent = areParamValuesEquivalent(
      typedKey,
      current[typedKey],
      value as SealParameters[keyof SealParameters],
    );
    if (equivalent) {
      nextDirty.delete(typedKey);
      continue;
    }
    if (pending?.has(typedKey)) {
      nextDirty.delete(typedKey);
      if (isParamSyncDebug()) {
        const left = current[typedKey];
        const right = value as SealParameters[keyof SealParameters];
        dbg("reconcile_accept_pending", {
          key: typedKey,
          client_value: left,
          client_type: typeof left,
          server_value: right,
          server_type: typeof right,
        });
      }
      continue;
    }
    if (isParamSyncDebug()) {
      const left = current[typedKey];
      const right = value as SealParameters[keyof SealParameters];
      dbg("reconcile_mismatch", {
        key: typedKey,
        client_value: left,
        client_type: typeof left,
        server_value: right,
        server_type: typeof right,
      });
    }
  }
  return nextDirty;
}

export function computeAppliedKeys(
  current: SealParameters,
  incoming: SealParameters,
  dirty: Set<keyof SealParameters>,
): Set<keyof SealParameters> {
  const applied = new Set<keyof SealParameters>();
  for (const [key, value] of Object.entries(incoming || {})) {
    const typedKey = key as keyof SealParameters;
    if (!dirty.has(typedKey)) continue;
    if (value === undefined) continue;
    if (areParamValuesEquivalent(typedKey, current[typedKey], value as SealParameters[keyof SealParameters])) {
      applied.add(typedKey);
    }
  }
  return applied;
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

export function emitParamPatchTelemetry(fields: number, ms: number, ok: boolean): void {
  emit({ type: "param_patch", fields, ms, ok });
}
