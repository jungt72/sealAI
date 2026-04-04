"use client";

/**
 * CaptureStatusTile — Parameter completeness checklist.
 * Shows which parameters are confirmed vs. missing and a progress bar.
 * Data comes from the same sources as ParameterTablePanel (streamAssertions,
 * streamParamMap, canonicalParamMap) — no new props, pure store reads.
 */

import { useMemo } from "react";
import { CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import TileWrapper from "../shared/TileWrapper";

type ParamSpec = {
  key: string;
  label: string;
  critical: boolean;
};

type ParamQuality = "asserted" | "normalized" | "canonical" | "missing";

const PARAMS: ParamSpec[] = [
  { key: "medium",            label: "Medium",           critical: true },
  { key: "temperature_c",     label: "Temperatur",        critical: true },
  { key: "pressure_bar",      label: "Druck",             critical: true },
  { key: "shaft_diameter_mm", label: "Wellen-Ø",          critical: true },
  { key: "motion_type",       label: "Bewegungsart",      critical: false },
  { key: "speed_rpm",         label: "Drehzahl",          critical: false },
  { key: "installation",      label: "Einbausituation",   critical: false },
] as const;

type ParamEntry = { value: string | null; quality: ParamQuality };

function useParamValues(): Record<string, ParamEntry> {
  const streamAssertions = useWorkspaceStore((s) => s.streamAssertions);
  const streamWorkspace  = useWorkspaceStore((s) => s.streamWorkspace);
  const workspace        = useWorkspaceStore((s) => s.workspace);

  return useMemo(() => {
    const result: Record<string, ParamEntry> = {};

    // Build canonical map from workspace confirmedFactsSummary
    const canonicalMap: Record<string, string> = {};
    const confirmedFacts = workspace?.communication?.confirmedFactsSummary ?? [];
    for (const fact of confirmedFacts) {
      const [rawLabel, ...rest] = String(fact).split(":");
      const value = rest.join(":").trim();
      const label = rawLabel.trim().toLowerCase();
      if (!value) continue;
      if (label === "medium")              canonicalMap.medium           = value;
      if (label === "betriebsdruck")       canonicalMap.pressure_bar     = value;
      if (label === "betriebstemperatur")  canonicalMap.temperature_c    = value;
      if (label === "bewegungsart" || label === "motion type" || label === "motion_type")
        canonicalMap.motion_type = value;
      if (label === "wellendurchmesser" || label === "wellen-ø" || label === "shaft diameter" || label === "shaft") {
        const m = fact.match(/(\d+(?:[.,]\d+)?)\s*mm/i);
        if (m) canonicalMap["shaft_diameter_mm"] = m[1] + " mm";
      }
      if (label === "drehzahl" || label === "speed" || label === "rpm") {
        const m = fact.match(/(\d+(?:[.,]\d+)?)\s*(?:rpm|u\/min)/i);
        if (m) canonicalMap["speed_rpm"] = m[1] + " rpm";
      }
      if (label === "einbau" || label === "installation")
        canonicalMap["installation"] = value;
    }
    // Also pick up medium from classification / mediumContext
    if (!canonicalMap.medium) {
      const cl = workspace?.mediumClassification?.canonicalLabel?.trim();
      if (cl) canonicalMap.medium = cl;
    }
    if (!canonicalMap.medium) {
      const ml = workspace?.mediumContext?.mediumLabel?.trim();
      if (ml) canonicalMap.medium = ml;
    }

    // Build stream param map from legacy ui.parameter.parameters
    const streamParamMap: Record<string, string> = {};
    for (const p of streamWorkspace?.ui.parameter.parameters ?? []) {
      if (p.field_name && p.value != null && p.value !== "") {
        const k = String(p.field_name).toLowerCase().replace(/\s+/g, "_");
        streamParamMap[k] = String(p.value);
      }
    }

    for (const { key } of PARAMS) {
      const assertion = streamAssertions?.[key];
      if (assertion?.value) {
        result[key] = { value: assertion.value, quality: "asserted" };
      } else if (streamParamMap[key] !== undefined) {
        result[key] = { value: streamParamMap[key], quality: "normalized" };
      } else if (canonicalMap[key] !== undefined) {
        result[key] = { value: canonicalMap[key], quality: "canonical" };
      } else {
        result[key] = { value: null, quality: "missing" };
      }
    }
    return result;
  }, [streamAssertions, streamWorkspace, workspace]);
}

/** Quality indicator icon — ✅ asserted, 🔵 normalized/canonical, ⚠️ missing+critical */
function QualityIcon({ quality, critical }: { quality: ParamQuality; critical: boolean }) {
  if (quality === "asserted") {
    return <CheckCircle2 size={12} className="shrink-0 text-green-400" aria-label="Bestätigt" />;
  }
  if (quality === "normalized" || quality === "canonical") {
    return (
      <div
        className="h-3 w-3 shrink-0 rounded-full border border-blue-500 bg-blue-900/40"
        title="Erkannt (noch nicht bestätigt)"
      />
    );
  }
  // missing
  if (critical) {
    return <AlertCircle size={12} className="shrink-0 text-amber-400" aria-label="Erforderlich" />;
  }
  return <Clock size={12} className="shrink-0 text-gray-600" aria-label="Optional, noch offen" />;
}

export default function CaptureStatusTile() {
  const paramValues = useParamValues();

  const { filled, criticalMissingCount, total } = useMemo(() => {
    let filledCount = 0;
    let critMissing = 0;
    for (const p of PARAMS) {
      if (paramValues[p.key].value !== null) {
        filledCount++;
      } else if (p.critical) {
        critMissing++;
      }
    }
    return { filled: filledCount, criticalMissingCount: critMissing, total: PARAMS.length };
  }, [paramValues]);

  const pct = Math.round((filled / total) * 100);

  const barColor =
    filled <= 2 ? "bg-red-500" :
    filled <= 4 ? "bg-amber-400" :
    "bg-green-500";

  const badge = `${filled}/${total}`;
  const badgeVariant =
    filled <= 2 ? "error" :
    filled <= 4 ? "warning" :
    "success";

  const missingCritical = PARAMS.filter(
    (p) => p.critical && paramValues[p.key].value === null
  );

  if (filled === 0) {
    return null; // Don't render until at least one param is known
  }

  return (
    <TileWrapper
      title="Erfassungsstand"
      accent="amber"
      badge={badge}
      badgeVariant={badgeVariant}
    >
      {/* Progress bar */}
      <div className="px-3 pt-3 pb-1">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Parameter checklist */}
      <div className="divide-y divide-gray-800/50">
        {PARAMS.map((param) => {
          const { value, quality } = paramValues[param.key];
          const isFilled = value !== null;
          return (
            <div
              key={param.key}
              className="flex items-center justify-between px-3 py-[7px]"
            >
              <div className="flex items-center gap-2">
                <QualityIcon quality={quality} critical={param.critical} />
                <span
                  className={`text-[11px] ${
                    quality === "asserted"
                      ? "text-gray-200"
                      : quality === "normalized" || quality === "canonical"
                      ? "text-gray-400"
                      : param.critical
                      ? "text-gray-500"
                      : "text-gray-700"
                  }`}
                >
                  {param.label}
                  {param.critical && !isFilled && (
                    <span className="ml-1 text-[9px] text-amber-500">*</span>
                  )}
                </span>
              </div>
              {isFilled ? (
                <span
                  className={`max-w-[110px] truncate text-right font-mono text-[11px] ${
                    quality === "asserted" ? "text-white" : "text-gray-400"
                  }`}
                >
                  {value}
                </span>
              ) : (
                <span className="text-[11px] text-gray-700">—</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Missing critical footer */}
      {missingCritical.length > 0 && (
        <div className="border-t border-gray-800 px-3 py-2">
          <p className="mb-1 text-[10px] font-medium text-amber-500">
            Noch benötigt für Empfehlung:
          </p>
          <p className="text-[10px] text-gray-500">
            {missingCritical.map((p) => p.label).join(", ")}
          </p>
        </div>
      )}
    </TileWrapper>
  );
}
