"use client";

import React from "react";
import type { UiAction } from "@/types/ui";

function prettyKey(k: string) {
  if (k === "umfangsgeschwindigkeit_m_s") return "v (m/s)";
  if (k === "surface_speed_m_s") return "v (m/s)";
  if (k === "omega_rad_s") return "ω (rad/s)";
  if (k === "p_bar") return "p (bar)";
  if (k === "p_pa") return "p (Pa)";
  if (k === "p_mpa") return "p (MPa)";
  if (k === "pv_bar_ms") return "PV (bar·m/s)";
  if (k === "pv_mpa_ms") return "PV (MPa·m/s)";
  if (k === "friction_force_n") return "Reibkraft (N)";
  if (k === "friction_power_w") return "Reibleistung (W)";
  return k.replaceAll("_", " ");
}

export default function CalcCard() {
  const [calc, setCalc] = React.useState<Record<string, number | string>>({});
  const [warnings, setWarnings] = React.useState<string[]>([]);

  React.useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as UiAction | any;
      if (!detail) return;
      const action = (detail.ui_action || "").toString();
      if (action !== "calc_snapshot") return;

      const d = (detail.derived || {}) as any;
      const c = (d.calculated || {}) as Record<string, number | string>;
      setCalc(c);
      setWarnings(Array.isArray(d.warnings) ? d.warnings : []);
    };
    window.addEventListener("sealai:ui_action", handler as EventListener);
    return () => window.removeEventListener("sealai:ui_action", handler as EventListener);
  }, []);

  const entries = Object.entries(calc)
    .filter(([k, v]) => v !== null && v !== undefined && k !== "")
    .sort(([a], [b]) => a.localeCompare(b));

  if (entries.length === 0 && warnings.length === 0) return null;

  return (
    <div className="rounded-2xl border p-4 shadow-sm bg-white/60 dark:bg-zinc-900/60">
      <div className="mb-2 text-sm font-semibold opacity-80">Berechnungen</div>

      <div className="grid grid-cols-1 gap-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-sm">
            <span className="opacity-70">{prettyKey(k)}</span>
            <span className="font-mono tabular-nums">
              {typeof v === "number"
                ? (Math.abs(v) < 1e-3 ? v.toExponential(3) : Number(v).toPrecision(6))
                : String(v)}
            </span>
          </div>
        ))}
      </div>

      {warnings.length > 0 && (
        <div className="mt-3 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="text-xs text-amber-700 dark:text-amber-300">
              • {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
