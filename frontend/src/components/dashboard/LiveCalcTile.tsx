import { AlertTriangle, Gauge, ShieldAlert, Snowflake } from "lucide-react";

type LiveCalcStatus = "ok" | "warning" | "critical" | "insufficient_data";

export type LiveCalcTileData = {
  v_surface_m_s?: number | null;
  pv_value_mpa_m_s?: number | null;
  hrc_value?: number | null;
  hrc_warning?: boolean;
  runout_warning?: boolean;
  pv_warning?: boolean;
  status?: LiveCalcStatus;
  extrusion_risk?: boolean;
  requires_backup_ring?: boolean;
  shrinkage_risk?: boolean;
  parameters?: Record<string, string | number | null | undefined>;
};

type LiveCalcTileProps = {
  tile?: LiveCalcTileData | null;
  rfqReady?: boolean;
  rfqPdfBase64?: string | null;
  rfqHtmlReport?: string | null;
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
  pressure_max_bar: "Druck (bar)",
  temperature_max_c: "Temperatur (°C)",
  rpm: "Drehzahl (U/min)",
  shaft_d1_mm: "Wellen-Ø (mm)",
  hrc_value: "Härte (HRC)",
  material: "Gegenlaufmaterial",
  seal_material: "Dichtungswerkstoff",
  cyclic_load: "Zyklische Last",
};

function formatValue(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return value.toFixed(digits);
}

function formatMetric(value: number | null | undefined, unit: string, digits = 2): string {
  const formatted = formatValue(value, digits);
  return formatted === "N/A" ? formatted : `${formatted} ${unit}`;
}

export default function LiveCalcTile(props: LiveCalcTileProps) {
  console.log("RENDERED LIVECALCTILE WITH PROPS:", props);
  const {
    tile,
    rfqReady = false,
    rfqPdfBase64 = null,
    rfqHtmlReport = null,
  } = props;
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

      <section className="mt-5 rounded-2xl border border-slate-200 bg-white/70 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Gauge className="h-4 w-4" />
          Kinematik
        </div>
        <dl className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <dt className="text-slate-600">Umfangsgeschwindigkeit</dt>
            <dd className="font-mono text-slate-900">{formatMetric(tile?.v_surface_m_s, "m/s")}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-slate-600">PV-Wert</dt>
            <dd className="font-mono text-slate-900">{formatMetric(tile?.pv_value_mpa_m_s, "MPa·m/s")}</dd>
          </div>
        </dl>
        {status === "insufficient_data" && (
          <p className="mt-3 text-xs text-slate-600">Warte auf Systemparameter...</p>
        )}
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
