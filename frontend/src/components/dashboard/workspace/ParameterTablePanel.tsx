"use client";

/**
 * ParameterTablePanel — 2-Spalten-Raster für technische Parameter.
 * Zeigt immer alle Felder (N.N. als Platzhalter).
 *
 * Priorität absteigend:
 *  1. localOverrides    — User tippt direkt in das Feld
 *  2. streamAssertions  — Assertions aus dem letzten Governed-Turn (persistiert im Store)
 *  3. streamParams      — Legacy ui.parameter.parameters (Non-Governed-Pfad)
 *
 * Loop-Invariante: EMPTY_STREAM_PARAMS ist eine Modul-Konstante (stabile
 * Referenz), damit useSyncExternalStore nicht bei jedem Call ein neues []
 * zurückgibt → kein Object.is-Loop (Error #185).
 */

import { useCallback, useMemo, useState } from "react";

import { useCaseStore } from "@/lib/store/caseStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { patchAgentOverrides } from "@/lib/bff/parameterOverride";

type StreamParam = { field_name?: string; value?: unknown; unit?: string | null };

const EMPTY_STREAM_PARAMS: StreamParam[] = [];

type DefaultParam = {
  key: string;
  label: string;
  unit: string;
  value: string;
};

const DEFAULT_PARAMS: DefaultParam[] = [
  { key: "medium",            label: "Medium",         unit: "",    value: "N.N." },
  { key: "temperature_c",     label: "Temperatur",     unit: "°C",  value: "N.N." },
  { key: "pressure_bar",      label: "Druck",          unit: "bar", value: "N.N." },
  { key: "shaft_diameter_mm", label: "Wellen-Ø",       unit: "mm",  value: "N.N." },
  { key: "speed_rpm",         label: "Drehzahl",       unit: "rpm", value: "N.N." },
  { key: "installation",      label: "Einbausituation",unit: "",    value: "N.N." },
];

export default function ParameterTablePanel() {
  const streamAssertions = useWorkspaceStore((s) => s.streamAssertions);
  const streamParameters = useWorkspaceStore(
    (s) => s.streamWorkspace?.ui.parameter.parameters ?? EMPTY_STREAM_PARAMS,
  );
  const workspace = useWorkspaceStore((s) => s.workspace);
  const setStreamAssertions = useWorkspaceStore((s) => s.setStreamAssertions);
  const refreshWorkspace = useWorkspaceStore((s) => s.refreshWorkspace);
  const turnCount = useWorkspaceStore((s) => s.workspace?.summary.turnCount ?? 0);
  const caseId = useCaseStore((s) => s.caseId);

  const [localOverrides, setLocalOverrides] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const coerceOverrideValue = useCallback((key: string, value: string): string | number => {
    if (["temperature_c", "pressure_bar", "shaft_diameter_mm", "speed_rpm"].includes(key)) {
      const normalized = Number(value.replace(",", "."));
      if (!Number.isFinite(normalized)) {
        throw new Error("Bitte geben Sie fuer numerische Parameter eine gueltige Zahl ein.");
      }
      return normalized;
    }
    return value;
  }, []);

  // Fallback: legacy ui.parameter.parameters (non-governed path)
  const streamParamMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of streamParameters) {
      if (p.field_name && p.value !== undefined && p.value !== null && p.value !== "") {
        const key = String(p.field_name).toLowerCase().replace(/\s+/g, "_");
        map[key] = String(p.value);
      }
    }
    return map;
  }, [streamParameters]);

  const canonicalParamMap = useMemo(() => {
    const map: Record<string, string> = {};
    const confirmedFacts = workspace?.communication?.confirmedFactsSummary ?? [];

    for (const fact of confirmedFacts) {
      const [label, ...rest] = String(fact).split(":");
      const value = rest.join(":").trim();
      const normalizedLabel = label.trim().toLowerCase();
      if (!value) {
        continue;
      }
      if (normalizedLabel === "medium") {
        map.medium = value;
      } else if (normalizedLabel === "betriebsdruck") {
        map.pressure_bar = value;
      } else if (normalizedLabel === "betriebstemperatur") {
        map.temperature_c = value;
      } else if (
        normalizedLabel === "wellendurchmesser" ||
        normalizedLabel === "wellen-ø" ||
        normalizedLabel === "shaft diameter" ||
        normalizedLabel === "shaft"
      ) {
        const m = fact.match(/(\d+(?:[.,]\d+)?)\s*mm/i);
        if (m) map["shaft_diameter_mm"] = m[1] + " mm";
      } else if (
        normalizedLabel === "drehzahl" ||
        normalizedLabel === "speed" ||
        normalizedLabel === "rpm"
      ) {
        const m = fact.match(/(\d+(?:[.,]\d+)?)\s*(?:rpm|u\/min)/i);
        if (m) map["speed_rpm"] = m[1] + " rpm";
      } else if (
        normalizedLabel === "einbau" ||
        normalizedLabel === "installation"
      ) {
        map["installation"] = value;
      }
    }

    if (!map.medium) {
      const classifiedMedium = workspace?.mediumClassification?.canonicalLabel?.trim();
      if (classifiedMedium) {
        map.medium = classifiedMedium;
      }
    }

    if (!map.medium) {
      const mediumLabel = workspace?.mediumContext?.mediumLabel?.trim();
      if (mediumLabel) {
        map.medium = mediumLabel;
      }
    }

    return map;
  }, [workspace]);

  const getEffectiveValue = useCallback(
    (param: DefaultParam): string => {
      // 1. User-typed override
      if (localOverrides[param.key] !== undefined) {
        return localOverrides[param.key];
      }
      // 2. Assertions from last governed turn (persists after stream ends)
      const assertion = streamAssertions?.[param.key];
      if (assertion?.value) {
        return assertion.value;
      }
      // 3. Legacy ui.parameter.parameters (non-governed path)
      const streamVal = streamParamMap[param.key];
      if (streamVal !== undefined) {
        return streamVal;
      }
      const canonicalVal = canonicalParamMap[param.key];
      if (canonicalVal !== undefined) {
        return canonicalVal;
      }
      return param.value;
    },
    [canonicalParamMap, streamAssertions, localOverrides, streamParamMap],
  );

  const handleChange = useCallback((key: string, value: string) => {
    setLocalOverrides((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleBlur = useCallback(
    async (param: DefaultParam, value: string) => {
      const trimmed = value.trim();
      if (!trimmed || trimmed === "N.N.") return;
      const assertionValue = streamAssertions?.[param.key]?.value ?? param.value;
      if (trimmed === assertionValue) return;
      if (!caseId) {
        setSaveError("Parameterkorrektur ist erst moeglich, sobald ein Case aktiv ist.");
        return;
      }

      setSaveError(null);
      setSavingKey(param.key);

      try {
        const overrideValue = coerceOverrideValue(param.key, trimmed);
        await patchAgentOverrides(caseId, {
          overrides: [
            {
              field_name: param.key,
              value: overrideValue,
              unit: param.unit || undefined,
            },
          ],
          turn_index: turnCount,
        });
        setStreamAssertions({
          ...(streamAssertions ?? {}),
          [param.key]: {
            value: String(overrideValue),
            confidence: "user_override",
          },
        });
        refreshWorkspace();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Parameterkorrektur konnte nicht gespeichert werden.";
        setSaveError(message);
      } finally {
        setSavingKey((current) => (current === param.key ? null : current));
      }
    },
    [
      caseId,
      coerceOverrideValue,
      refreshWorkspace,
      setStreamAssertions,
      streamAssertions,
      turnCount,
    ],
  );

  return (
    <div>
      {saveError ? (
        <div className="border-b border-[#f0f2f6] px-[10px] py-[7px] text-[11px] text-[#b91c1c]">
          {saveError}
        </div>
      ) : null}
      <div className="grid grid-cols-2">
      {DEFAULT_PARAMS.map((param, index) => {
        const isLastPair = index >= DEFAULT_PARAMS.length - 2;
        const isRightCol = index % 2 === 1;
        const displayValue = getEffectiveValue(param);
        const isFilled = displayValue !== "N.N." && displayValue !== "";

        return (
          <div
            key={param.key}
            className={`px-[10px] py-[7px] ${!isLastPair ? "border-b border-[#f0f2f6]" : ""} ${!isRightCol ? "border-r border-[#f0f2f6]" : ""}`}
          >
            <div className="text-[10.5px] text-[#94a3b8]">
              {param.label}
              {param.unit && (
                <span className="ml-0.5 text-[9.5px]">{param.unit}</span>
              )}
            </div>
            <input
              type="text"
              value={displayValue}
              onChange={(e) => handleChange(param.key, e.target.value)}
              onBlur={(e) => {
                void handleBlur(param, e.target.value);
              }}
              disabled={savingKey === param.key}
              className="mt-0.5 w-full rounded-[5px] border border-[#e2e8f0] bg-[#f8fafc] px-[6px] py-[3px] text-right font-mono text-[12px] focus:border-blue-500 focus:bg-white focus:outline-none"
              style={{
                color: isFilled ? "#1a2332" : "#cbd5e1",
                fontWeight: isFilled ? 500 : 400,
              }}
            />
          </div>
        );
      })}
      </div>
    </div>
  );
}
