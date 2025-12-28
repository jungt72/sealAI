"use client";

import type { SealParameters } from "@/lib/types/sealParameters";
import { dbg, isParamSyncDebug } from "@/lib/paramSyncDebug";

type ParamLabel = {
  label: string;
  unit?: string;
};

const PARAMETER_SUMMARY_LABELS: Partial<Record<keyof SealParameters, ParamLabel>> = {
  pressure_bar: { label: "Druck", unit: "bar" },
  temperature_C: { label: "Temperatur", unit: "°C" },
  speed_rpm: { label: "Drehzahl", unit: "rpm" },
  medium: { label: "Medium" },
  shaft_diameter: { label: "Wellen-Ø", unit: "mm" },
  nominal_diameter: { label: "Bohrungs-Ø", unit: "mm" },
  tolerance: { label: "Toleranz", unit: "mm" },
  hardness: { label: "Härte" },
  surface: { label: "Werkstoff" },
  roughness_ra: { label: "Ra", unit: "µm" },
  lead: { label: "Drall" },
  lead_pitch: { label: "Drall-Tiefe / Steigung" },
  runout: { label: "Rundlauf", unit: "mm" },
  eccentricity: { label: "Exzentrizität", unit: "mm" },
  housing_diameter: { label: "Gehäuse-Ø", unit: "mm" },
  bore_diameter: { label: "Bohrungs-Ø (tats.)", unit: "mm" },
  housing_tolerance: { label: "Gehäuse-Toleranz", unit: "mm" },
  housing_surface: { label: "Gehäuse-Oberfläche" },
  housing_material: { label: "Gehäuse-Material" },
  axial_plate_axial: { label: "Axialer Platz", unit: "mm" },
  pressure_min: { label: "Min. Druck", unit: "bar" },
  pressure_max: { label: "Max. Druck", unit: "bar" },
  temp_min: { label: "Min. Temp", unit: "°C" },
  temp_max: { label: "Max. Temp", unit: "°C" },
  speed_linear: { label: "Geschw.", unit: "m/s" },
  dynamic_runout: { label: "Wellenschlag (dyn)" },
  mounting_offset: { label: "Montageversatz", unit: "mm" },
  contamination: { label: "Verschmutzung" },
  lifespan: { label: "Lebensdauer (h)" },
  application_type: { label: "Anwendungstyp" },
  food_grade: { label: "Konformität" },
};

function formatParamValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  return String(value);
}

export function buildParameterApplySummary(patch: Partial<SealParameters>): string {
  const entries = Object.entries(patch)
    .map(([rawKey, rawValue]) => {
      const value = formatParamValue(rawValue);
      if (!value) return null;
      const key = rawKey as keyof SealParameters;
      const info = PARAMETER_SUMMARY_LABELS[key];
      const label = info?.label ?? rawKey;
      const unit = info?.unit ? ` ${info.unit}` : "";
      return `${label}=${value}${unit}`;
    })
    .filter((entry): entry is string => Boolean(entry));

  if (!entries.length) return "";
  return `Parameter übernommen: ${entries.join(", ")}`;
}

function pickConfirmedValues(
  keys: string[],
  confirmed: Partial<SealParameters> | null | undefined,
): Partial<SealParameters> {
  if (!confirmed) return {};
  const out: Partial<SealParameters> = {};
  for (const key of keys) {
    const typedKey = key as keyof SealParameters;
    if (confirmed[typedKey] === undefined) continue;
    out[typedKey] = confirmed[typedKey];
  }
  return out;
}

export async function applyParametersWithChatMessage(opts: {
  patch: Partial<SealParameters>;
  patchParameters: (patch: Partial<SealParameters>) => Promise<Partial<SealParameters> | null | void>;
  sendChatMessage: (content: string, metadata?: Record<string, unknown>) => void;
  metadata?: Record<string, unknown>;
}): Promise<{ summary: string }> {
  const patchKeys = Object.keys(opts.patch || {});
  if (!patchKeys.length) return { summary: "" };

  const confirmed = await opts.patchParameters(opts.patch);
  const summaryPatch = pickConfirmedValues(patchKeys, confirmed ?? undefined);
  if (isParamSyncDebug()) {
    const entries = Object.entries(summaryPatch).map(([key, value]) => ({
      key,
      value,
      type: typeof value,
    }));
    dbg("summary_source", {
      source: Object.keys(summaryPatch).length ? "confirmed_state" : "patch_raw",
      keys: patchKeys,
      summary_values: entries,
    });
  }
  const summary = buildParameterApplySummary(
    Object.keys(summaryPatch).length ? summaryPatch : {},
  );
  if (summary) {
    opts.sendChatMessage(summary, opts.metadata);
  }
  return { summary };
}
