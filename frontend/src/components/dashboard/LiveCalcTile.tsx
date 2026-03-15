import { 
  AlertTriangle, 
  Gauge, 
  ShieldAlert, 
  Snowflake, 
  Activity, 
  Beaker, 
  ShieldCheck, 
  Settings2,
  CheckCircle2,
  AlertCircle 
} from "lucide-react";
import type { StructuredCasePanelModel } from "@/lib/caseStateProjection";

type LiveCalcStatus = "ok" | "warning" | "critical" | "insufficient_data";

export type LiveCalcTileData = {
  v_surface_m_s?: number | null;
  pv_value_mpa_m_s?: number | null;
  hrc_value?: number | null;
  hrc_warning?: boolean;
  runout_warning?: boolean;
  pv_warning?: boolean;
  friction_power_watts?: number | null;
  dry_running_risk?: boolean;
  clearance_gap_mm?: number | null;
  extrusion_risk?: boolean;
  requires_backup_ring?: boolean;
  compression_ratio_pct?: number | null;
  groove_fill_pct?: number | null;
  stretch_pct?: number | null;
  geometry_warning?: boolean;
  thermal_expansion_mm?: number | null;
  shrinkage_risk?: boolean;
  chem_warning?: boolean;
  chem_message?: string | null;
  status?: LiveCalcStatus;
  parameters?: Record<string, string | number | null | undefined>;
  // V8 Compliance & Resistance
  compliance?: {
    fda?: boolean;
    atex?: boolean;
    bam?: boolean;
  };
  resistance_status?: "ok" | "warning" | "critical" | "unknown";
};

type LiveCalcTileProps = {
  tile?: LiveCalcTileData | null;
  casePanel?: StructuredCasePanelModel | null;
  rfqReady?: boolean;
  rfqPdfBase64?: string | null;
  rfqHtmlReport?: string | null;
  rfqActionStatus?: string | null;
  onQualifiedAction?: (() => void | Promise<void>) | null;
  onSuggestedQuestionAction?: ((prompt: string) => void) | null;
};

const statusStyles: Record<LiveCalcStatus, string> = {
  ok: "bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30",
  warning: "bg-amber-500/15 text-amber-800 ring-1 ring-amber-500/35",
  critical: "bg-rose-500/15 text-rose-700 ring-1 ring-rose-500/35",
  insufficient_data: "bg-slate-500/15 text-slate-700 ring-1 ring-slate-400/40",
};

const statusLabels: Record<LiveCalcStatus, string> = {
  ok: "OK",
  warning: "Warnung",
  critical: "Kritisch",
  insufficient_data: "Keine Daten",
};

const LABEL_MAP: Record<string, string> = {
  medium: "Medium",
  pressure: "Druck (bar)",
  temperature: "Temperatur (°C)",
  speed: "Drehzahl (U/min)",
  diameter: "Wellen-Ø (mm)",
  pressure_max_bar: "Druck (bar)",
  pressure_bar: "Druck (bar)",
  temperature_max_c: "Temperatur (°C)",
  rpm: "Drehzahl (U/min)",
  speed_rpm: "Drehzahl (U/min)",
  shaft_d1_mm: "Wellen-Ø (mm)",
  shaft_diameter: "Wellen-Ø (mm)",
  housing_bore: "Gehäusebohrung (mm)",
  hrc_value: "Härte (HRC)",
  material: "Gegenlaufmaterial",
  seal_material: "Dichtungswerkstoff",
  cyclic_load: "Zyklische Last",
};

function formatValue(value: number | string | null | undefined, digits = 2): string {
  const numeric = typeof value === "string" ? Number(value) : value;
  if (numeric === null || numeric === undefined || Number.isNaN(numeric)) return "N/A";
  return Number(numeric).toFixed(digits);
}

function formatMetric(value: number | string | null | undefined, unit: string, digits = 2): string {
  const formatted = formatValue(value, digits);
  return formatted === "N/A" ? formatted : `${formatted} ${unit}`;
}

export default function LiveCalcTile(props: LiveCalcTileProps) {
  console.log("RENDERED LIVECALCTILE WITH PROPS:", props);
  const {
    tile: rawTile,
    casePanel = null,
    rfqReady = false,
    rfqPdfBase64 = null,
    rfqHtmlReport = null,
    rfqActionStatus = null,
    onQualifiedAction = null,
    onSuggestedQuestionAction = null,
  } = props;
  const tile =
    rawTile && typeof (rawTile as any).working_profile?.live_calc_tile === "object"
      ? ((rawTile as any).working_profile.live_calc_tile as LiveCalcTileData)
      : rawTile && typeof (rawTile as any).live_calc_tile === "object"
      ? ((rawTile as any).live_calc_tile as LiveCalcTileData)
      : rawTile;
  const status: LiveCalcStatus = tile?.status ?? "insufficient_data";
  const capturedParams = new Map<string, string | number>();
  Object.entries(tile?.parameters ?? {}).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (typeof value === "string" && value.trim().length === 0) return;

    const translatedLabel = LABEL_MAP[key];
    if (!translatedLabel) return;

    // Deduplicate aliases by using the translated label as the canonical key.
    capturedParams.set(translatedLabel, value);
  });

  const handleDownloadRfq = () => {
    if (rfqPdfBase64 && typeof window !== "undefined") {
      try {
        const binary = window.atob(rfqPdfBase64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: "application/pdf" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "sealai-rfq.pdf";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        return;
      } catch (error) {
        console.error("Failed to download RFQ PDF:", error);
      }
    }

    if (rfqHtmlReport && typeof window !== "undefined") {
      const popup = window.open("", "_blank", "noopener,noreferrer");
      if (popup) {
        popup.document.open();
        popup.document.write(rfqHtmlReport);
        popup.document.close();
        return;
      }
      const blob = new Blob([rfqHtmlReport], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sealai-rfq.html";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }
  };

  if (casePanel?.isStructured) {
    const actionGate = casePanel.actionGate;
    const actionAllowed = Boolean(actionGate?.allowed);
    return (
      <aside className="h-full rounded-3xl border border-slate-200/70 bg-[linear-gradient(145deg,#f7fbff_0%,#eef6ff_55%,#f8fbff_100%)] p-5 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Case State Projection</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">{casePanel.title}</h2>
            <p className="mt-1 text-xs text-slate-500">{casePanel.subtitle}</p>
          </div>
          <span className="rounded-full px-3 py-1 text-xs font-semibold bg-blue-500/10 text-blue-700 ring-1 ring-blue-500/20">
            Structured
          </span>
        </div>

        <StructuredPanelSection title="Technical Direction" items={casePanel.technicalDirection} />
        <StructuredPanelSection title="Validity & Constraints" items={casePanel.validityEnvelope} />
        <StructuredPanelSection title="Current Case Summary" items={casePanel.caseSummary} />
        <StructuredPanelSection title="Failure Analysis" items={casePanel.failureAnalysis} />
        <StructuredPanelSection title="Next Best Inputs" items={casePanel.nextBestInputs} />
        <StructuredPanelSection
          title="Suggested Next Questions"
          items={casePanel.suggestedNextQuestions}
          actionable
          onAction={onSuggestedQuestionAction}
        />
        <StructuredPanelSection title="Known Parameters" items={casePanel.knownParameters} />
        <StructuredPanelSection title="Derived Values" items={casePanel.derivedValues} />
        <StructuredPanelSection title="Engineering Signals" items={casePanel.engineeringSignals} />
        <StructuredPanelSection title="Qualification Status" items={casePanel.qualificationStatus} />

        {actionGate && (
          <div className="mt-5 space-y-2">
            <button
              type="button"
              onClick={() => {
                if (onQualifiedAction) {
                  void onQualifiedAction();
                  return;
                }
                handleDownloadRfq();
              }}
              disabled={!actionAllowed}
              className={`w-full rounded-xl border px-4 py-2.5 text-sm font-semibold shadow-sm transition active:scale-[0.99] ${
                actionAllowed
                  ? "border-[#0b5fff] bg-[#0b5fff] text-white hover:bg-[#0a4ed0]"
                  : "cursor-not-allowed border-slate-300 bg-slate-100 text-slate-500"
              }`}
            >
              Download Technical RFQ
            </button>
            {!actionAllowed && actionGate.blockReasons.length > 0 && (
              <p className="text-xs text-slate-600">
                Blocked: {actionGate.blockReasons.join(", ")}
              </p>
            )}
            {rfqActionStatus && (
              <p className="text-xs text-slate-600">{rfqActionStatus}</p>
            )}
            {casePanel.lastQualifiedAction && casePanel.lastQualifiedAction.lastStatus !== "none" && (
              <p className="text-xs text-slate-600">
                Last RFQ Action: {casePanel.lastQualifiedAction.lastStatus}
                {casePanel.lastQualifiedAction.blockReasons.length > 0
                  ? ` · ${casePanel.lastQualifiedAction.blockReasons.join(", ")}`
                  : ""}
              </p>
            )}
            {casePanel.qualifiedActionHistory.length > 1 && (
              <div className="rounded-xl border border-slate-200 bg-white/60 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Recent Action History
                </p>
                <div className="mt-2 space-y-1.5">
                  {casePanel.qualifiedActionHistory.slice(0, 5).map((entry, index) => (
                    <p key={`${entry.timestamp}-${index}`} className="text-xs text-slate-600">
                      {entry.lastStatus}
                      {entry.blockReasons.length > 0 ? ` · ${entry.blockReasons.join(", ")}` : ""}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!actionGate && rfqReady && (
          <button
            type="button"
            onClick={handleDownloadRfq}
            className="mt-5 w-full rounded-xl border border-[#0b5fff] bg-[#0b5fff] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0a4ed0] active:scale-[0.99]"
          >
            Download Technical RFQ
          </button>
        )}
      </aside>
    );
  }

  return (
    <aside className="h-full rounded-3xl border border-slate-200/70 bg-[linear-gradient(145deg,#f7fbff_0%,#eef6ff_55%,#f8fbff_100%)] p-5 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Sealing Intelligence Dashboard</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">Live-Physik-Engine</h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${statusStyles[status]}`}>
          {statusLabels[status]}
        </span>
      </div>

      {/* SECTION 1: Tribologie & Kinematik */}
      <section className="mt-4 rounded-2xl border border-slate-200 bg-white/70 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Activity className="h-4 w-4 text-blue-500" />
          Tribologie & Kinematik
        </div>
        <dl className="space-y-2.5 text-sm">
          {[
            { label: "Umfangsgeschwindigkeit", value: tile?.v_surface_m_s, unit: "m/s" },
            { label: "PV-Wert", value: tile?.pv_value_mpa_m_s, unit: "MPa·m/s" },
            { label: "Reibleistung", value: tile?.friction_power_watts, unit: "W" },
            { label: "Klarspalt", value: tile?.clearance_gap_mm, unit: "mm" },
          ].map(item => item.value != null && (
            <div key={item.label} className="flex items-center justify-between gap-4 border-b border-slate-100 pb-1.5 last:border-0 last:pb-0">
              <dt className="text-slate-500 text-xs">{item.label}</dt>
              <dd className="font-mono text-slate-900 font-medium">{formatMetric(item.value, item.unit)}</dd>
            </div>
          ))}
        </dl>
        {status === "insufficient_data" && (
          <p className="mt-3 text-xs text-slate-600">Warte auf Systemparameter...</p>
        )}
      </section>

      {/* SECTION 2: DIN 3770 Geometrie (M2) */}
      {(tile?.compression_ratio_pct != null || tile?.groove_fill_pct != null) && (
        <section className="mt-4 rounded-2xl border border-slate-200 bg-white/70 p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Settings2 className="h-4 w-4 text-slate-500" />
            Geometrie (DIN 3770)
            {tile?.geometry_warning && <AlertCircle className="h-4 w-4 text-amber-500 animate-pulse" />}
          </div>
          <dl className="space-y-2.5 text-sm">
            {[
              { label: "Verpressung", value: tile?.compression_ratio_pct, unit: "%" },
              { label: "Nutfüllung", value: tile?.groove_fill_pct, unit: "%" },
              { label: "Dehnung", value: tile?.stretch_pct, unit: "%" },
            ].map(item => item.value != null && (
              <div key={item.label} className="flex items-center justify-between gap-4">
                <dt className="text-slate-500 text-xs">{item.label}</dt>
                <dd className="font-mono text-slate-900 font-medium">{formatMetric(item.value, item.unit, 1)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* SECTION 3: Beständigkeit & Compliance (M6/M8) */}
      <section className="mt-4 rounded-2xl border border-slate-200 bg-white/70 p-4">
        <div className="mb-3 flex items-center justify-between text-sm font-semibold text-slate-700">
          <div className="flex items-center gap-2">
            <Beaker className="h-4 w-4 text-indigo-500" />
            Chem. Beständigkeit
          </div>
          {tile?.chem_warning === false && tile?.chem_message && (
             <span className="flex items-center gap-1 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border text-emerald-600 border-emerald-200 bg-emerald-50">
               <CheckCircle2 className="h-3 w-3" /> Beständig
             </span>
          )}
          {tile?.chem_warning && (
             <span className="flex items-center gap-1 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border text-rose-600 border-rose-200 bg-rose-50">
               <AlertTriangle className="h-3 w-3" /> Warnung
             </span>
          )}
        </div>
        
        {tile?.chem_message && (
          <p className={`text-[11px] leading-relaxed mb-2 ${tile.chem_warning ? 'text-rose-700 font-medium' : 'text-slate-600'}`}>
            {tile.chem_message}
          </p>
        )}

        {/* Compliance Badges */}
        <div className="flex flex-wrap gap-1.5 mt-2">
          {tile?.compliance?.fda && (
            <span className="flex items-center gap-1 text-[10px] font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full border border-slate-200">
              <ShieldCheck className="h-3 w-3 text-emerald-500" /> FDA
            </span>
          )}
          {tile?.compliance?.atex && (
            <span className="flex items-center gap-1 text-[10px] font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full border border-slate-200">
              <ShieldCheck className="h-3 w-3 text-amber-500" /> ATEX
            </span>
          )}
          {tile?.compliance?.bam && (
            <span className="flex items-center gap-1 text-[10px] font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full border border-slate-200">
              <ShieldCheck className="h-3 w-3 text-blue-500" /> BAM
            </span>
          )}
        </div>
      </section>

      <section className="mt-5 space-y-3">
        {(tile?.hrc_warning ?? false) && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle className="h-4 w-4" />
              Risiko: Wellenhärte
            </div>
            <p className="mt-1 text-xs">Wellenhärte unter 58 HRC. Härten der Welle oder Gleitringdichtung prüfen.</p>
          </div>
        )}

        {((tile?.extrusion_risk ?? false) || (tile?.requires_backup_ring ?? false)) && (
          <div className="rounded-xl border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-900">
            <div className="flex items-center gap-2 font-semibold">
              <ShieldAlert className="h-4 w-4" />
              Kritisch: Extrusion
            </div>
            <p className="mt-1 text-xs">Hohes Extrusionsrisiko durch Druck. Stützring (Back-up Ring) zwingend erforderlich.</p>
          </div>
        )}

        {(tile?.shrinkage_risk ?? false) && (
          <div className="rounded-xl border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900">
            <div className="flex items-center gap-2 font-semibold">
              <Snowflake className="h-4 w-4" />
              Cryogenic Warning
            </div>
            <p className="mt-1 text-xs">Cryogenic range detected. Spring-energized sealing is recommended.</p>
          </div>
        )}
      </section>

      {capturedParams.size > 0 && (
        <section className="mt-5 rounded-2xl border border-slate-200 bg-white/70 p-4">
          <div className="mb-3 text-sm font-semibold text-slate-700">Erfasste Parameter</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            {Array.from(capturedParams.entries()).map(([label, value]) => (
              <div key={label} className="flex flex-col">
                <span className="text-xs text-slate-500">{label}</span>
                <span className="font-medium text-slate-800">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {rfqReady && (
        <button
          type="button"
          onClick={handleDownloadRfq}
          className="mt-5 w-full rounded-xl border border-[#0b5fff] bg-[#0b5fff] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0a4ed0] active:scale-[0.99]"
        >
          Download Technical RFQ
        </button>
      )}
    </aside>
  );
}

function StructuredPanelSection({
  title,
  items,
  actionable = false,
  onAction = null,
}: {
  title: string;
  items: Array<{ key: string; label: string; value: string; detail?: string | null; severity?: "low" | "medium" | "high" }>;
  actionable?: boolean;
  onAction?: ((prompt: string) => void) | null;
}) {
  return (
    <section className="mt-4 rounded-2xl border border-slate-200 bg-white/70 p-4">
      <div className="mb-3 text-sm font-semibold text-slate-700">{title}</div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500">Noch keine strukturierten Daten.</p>
      ) : (
        <dl className="space-y-2.5 text-sm">
          {items.map(item => (
            <div key={item.key} className="border-b border-slate-100 pb-2 last:border-0 last:pb-0">
              {actionable && onAction && item.key.startsWith("suggested_question_") && item.detail ? (
                <button
                  type="button"
                  onClick={() => onAction(item.detail ?? item.value)}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-left transition hover:border-[#0b5fff]/35 hover:bg-[#0b5fff]/5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <dt className="text-xs text-slate-500">{item.label}</dt>
                      <div className="mt-1 text-sm font-medium text-slate-900">{item.detail}</div>
                    </div>
                    <dd className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
                      {item.value}
                    </dd>
                  </div>
                </button>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-xs text-slate-500">{item.label}</dt>
                    <dd className="text-right font-medium text-slate-900">{item.value}</dd>
                  </div>
                  {item.detail && (
                    <div className={`mt-1 text-[11px] ${
                      item.severity === "high"
                        ? "text-rose-700"
                        : item.severity === "medium"
                        ? "text-amber-700"
                        : "text-slate-500"
                    }`}>
                      {item.detail}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
