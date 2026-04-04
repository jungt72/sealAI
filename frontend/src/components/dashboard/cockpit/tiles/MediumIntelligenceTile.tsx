"use client";

/**
 * MediumIntelligenceTile — Rich medium knowledge card.
 *
 * Shows:
 *  - Medium label + family (from workspace or streamAssertions)
 *  - Physical properties (pH, viscosity, temp range) from LLM enrichment
 *  - Material compatibility matrix (green / red)
 *  - Special challenges & sealing considerations
 *
 * LLM enrichment fetches /api/bff/medium-intelligence once per unique medium
 * label. Falls back to existing workspace.mediumContext data if BFF call fails
 * or is still loading.
 */

import { useEffect, useMemo } from "react";
import { FlaskConical, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { useWorkspaceStore, type MediumIntelligenceData } from "@/lib/store/workspaceStore";
import TileWrapper from "../shared/TileWrapper";

// ── Data helpers ────────────────────────────────────────────────────────────

function useCurrentMediumLabel(): string | null {
  const workspace        = useWorkspaceStore((s) => s.workspace);
  const streamAssertions = useWorkspaceStore((s) => s.streamAssertions);

  return useMemo(() => {
    // Prefer canonical label from classification
    const classified = workspace?.mediumClassification?.canonicalLabel?.trim();
    if (classified) return classified;

    // Fall back to mediumContext label
    const contextLabel = workspace?.mediumContext?.mediumLabel?.trim();
    if (contextLabel) return contextLabel;

    // Fall back to stream assertion
    const assertion = streamAssertions?.["medium"]?.value?.trim();
    if (assertion) return assertion;

    return null;
  }, [workspace, streamAssertions]);
}

async function fetchMediumIntelligence(
  mediumLabel: string
): Promise<MediumIntelligenceData> {
  const res = await fetch("/api/bff/medium-intelligence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ medium: mediumLabel }),
  });
  if (!res.ok) {
    throw new Error(`Medium intelligence fetch failed: ${res.status}`);
  }
  return res.json() as Promise<MediumIntelligenceData>;
}

// ── Rendering helpers ───────────────────────────────────────────────────────

function AggressivenessLabel({ level }: { level: string }) {
  const map: Record<string, { label: string; color: string }> = {
    low:       { label: "Niedrig",   color: "text-green-400" },
    medium:    { label: "Mittel",    color: "text-amber-400" },
    high:      { label: "Hoch",      color: "text-orange-400" },
    very_high: { label: "Sehr hoch", color: "text-red-400" },
  };
  const { label, color } = map[level] ?? { label: level, color: "text-gray-400" };
  return <span className={`font-medium ${color}`}>{label}</span>;
}

function ConfidenceBadge({ level }: { level: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    high:   { label: "HOCH",   cls: "bg-green-900/40 text-green-300" },
    medium: { label: "MITTEL", cls: "bg-amber-900/40 text-amber-300" },
    low:    { label: "NIEDRIG",cls: "bg-gray-800 text-gray-400" },
  };
  const { label, cls } = map[level] ?? { label: level.toUpperCase(), cls: "bg-gray-800 text-gray-400" };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

function IncompatibleMaterial({ entry }: { entry: string | { material: string; reason: string } }) {
  if (typeof entry === "string") {
    return <span>{entry}</span>;
  }
  return (
    <span>
      {entry.material}
      {entry.reason && (
        <span className="ml-1 text-[10px] text-gray-600">({entry.reason})</span>
      )}
    </span>
  );
}

// ── Fallback view using workspace.mediumContext ──────────────────────────────

function MediumContextFallback({ mediumLabel }: { mediumLabel: string }) {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const ctx = workspace?.mediumContext;
  const cls = workspace?.mediumClassification;

  const properties = ctx?.properties ?? [];
  const challenges = ctx?.challenges ?? [];
  const summary    = ctx?.summary ?? cls?.family ?? null;

  return (
    <div className="space-y-0">
      {/* Medium name + family */}
      <div className="border-b border-gray-800 px-3 py-2">
        <p className="text-sm font-medium text-white">{mediumLabel}</p>
        {summary && (
          <p className="mt-0.5 text-[11px] text-gray-400">{summary}</p>
        )}
      </div>

      {properties.length > 0 && (
        <div className="border-b border-gray-800 px-3 py-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Eigenschaften
          </p>
          <ul className="space-y-0.5">
            {properties.map((p, i) => (
              <li key={i} className="text-[11px] text-gray-300">
                • {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {challenges.length > 0 && (
        <div className="px-3 py-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Herausforderungen
          </p>
          <ul className="space-y-0.5">
            {challenges.map((c, i) => (
              <li key={i} className="flex items-start gap-1 text-[11px] text-amber-400">
                <AlertTriangle size={10} className="mt-0.5 shrink-0" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Full enriched view ───────────────────────────────────────────────────────

function MediumEnrichedView({
  mediumLabel,
  data,
}: {
  mediumLabel: string;
  data: MediumIntelligenceData;
}) {
  const pHNote = [
    data.pH.min !== null && data.pH.max !== null
      ? `pH ${data.pH.min}–${data.pH.max}`
      : null,
    data.pH.note || null,
  ]
    .filter(Boolean)
    .join(" – ");

  const viscNote = data.viscosityMpas.at20c !== null
    ? `~${data.viscosityMpas.at20c} mPas (20°C)`
    : null;

  const tempRange = `${data.temperatureRange.minC}°C bis ${data.temperatureRange.maxC}°C`;

  return (
    <div>
      {/* Header: name + family */}
      <div className="border-b border-gray-800 px-3 py-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-white">{data.canonicalName}</p>
            <p className="mt-0.5 text-[11px] text-gray-400">
              {data.family}
              {data.subFamily ? ` / ${data.subFamily}` : ""}
            </p>
          </div>
          <ConfidenceBadge level={data.confidenceLevel} />
        </div>
      </div>

      {/* Physical properties */}
      <div className="border-b border-gray-800 px-3 py-2">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Physikalische Eigenschaften
        </p>
        <div className="space-y-1">
          {pHNote && (
            <div className="flex justify-between text-[11px]">
              <span className="text-gray-500">pH</span>
              <span className="text-gray-200">{pHNote}</span>
            </div>
          )}
          {viscNote && (
            <div className="flex justify-between text-[11px]">
              <span className="text-gray-500">Viskosität</span>
              <span className="text-gray-200">{viscNote}</span>
            </div>
          )}
          <div className="flex justify-between text-[11px]">
            <span className="text-gray-500">Temp-Range</span>
            <span className="text-gray-200">{tempRange}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-gray-500">Korrosivität</span>
            <AggressivenessLabel level={data.corrosiveness} />
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-gray-500">Chem. Agressivität</span>
            <AggressivenessLabel level={data.chemicalAggressiveness} />
          </div>
        </div>
      </div>

      {/* Material compatibility */}
      {(data.compatibleMaterials.length > 0 || data.incompatibleMaterials.length > 0) && (
        <div className="border-b border-gray-800 px-3 py-2">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Materialverträglichkeit
          </p>
          {data.compatibleMaterials.length > 0 && (
            <div className="mb-1 flex flex-wrap gap-1">
              {data.compatibleMaterials.map((m) => (
                <span
                  key={m}
                  className="flex items-center gap-0.5 rounded bg-green-900/30 px-1.5 py-0.5 text-[10px] text-green-300"
                >
                  <CheckCircle2 size={8} />
                  {m}
                </span>
              ))}
            </div>
          )}
          {data.incompatibleMaterials.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {data.incompatibleMaterials.map((m, i) => (
                <span
                  key={i}
                  className="flex items-center gap-0.5 rounded bg-red-900/30 px-1.5 py-0.5 text-[10px] text-red-300"
                >
                  <XCircle size={8} />
                  <IncompatibleMaterial entry={m} />
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Warnings */}
      {data.warningFlags.length > 0 && (
        <div className="border-b border-gray-800 px-3 py-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-amber-600">
            ⚠ Besondere Hinweise
          </p>
          <ul className="space-y-0.5">
            {data.warningFlags.map((w, i) => (
              <li key={i} className="text-[11px] text-amber-400">
                • {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Sealing considerations */}
      {data.sealingConsiderations.length > 0 && (
        <div className="border-b border-gray-800 px-3 py-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Dichtungshinweise
          </p>
          <ul className="space-y-0.5">
            {data.sealingConsiderations.map((s, i) => (
              <li key={i} className="text-[11px] text-gray-300">
                • {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Preliminary recommendation */}
      {data.compatibleMaterials.length > 0 && (
        <div className="px-3 py-2">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-green-600">
            ↗ Vorläufige Empfehlung
          </p>
          <p className="mb-1 text-[10px] text-gray-500">
            Bevorzugte Dichtungswerkstoffe für dieses Medium:
          </p>
          <div className="flex flex-wrap gap-1">
            {data.compatibleMaterials.slice(0, 4).map((m) => (
              <span
                key={m}
                className="rounded border border-green-800/50 bg-green-900/20 px-2 py-0.5 text-[10px] font-medium text-green-300"
              >
                {m}
              </span>
            ))}
          </div>
          <p className="mt-1.5 text-[9.5px] italic text-gray-700">
            Orientierend — ohne vollständige Betriebsparameter nicht verbindlich.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Main tile ────────────────────────────────────────────────────────────────

export default function MediumIntelligenceTile() {
  const mediumLabel            = useCurrentMediumLabel();
  const intelligence           = useWorkspaceStore((s) => s.mediumIntelligence);
  const loading                = useWorkspaceStore((s) => s.mediumIntelligenceLoading);
  const intelligenceFor        = useWorkspaceStore((s) => s.mediumIntelligenceFor);
  const setIntelligence        = useWorkspaceStore((s) => s.setMediumIntelligence);
  const setLoading             = useWorkspaceStore((s) => s.setMediumIntelligenceLoading);
  const setIntelligenceFor     = useWorkspaceStore((s) => s.setMediumIntelligenceFor);
  const workspaceCtxAvailable  = useWorkspaceStore(
    (s) => s.workspace?.mediumContext?.status === "available"
  );

  // Fetch enriched data when a new medium is identified
  useEffect(() => {
    if (!mediumLabel) return;
    if (mediumLabel === intelligenceFor) return;

    let cancelled = false;
    setLoading(true);
    setIntelligenceFor(mediumLabel);

    fetchMediumIntelligence(mediumLabel)
      .then((data) => {
        if (!cancelled) {
          setIntelligence(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIntelligence(null);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [mediumLabel, intelligenceFor, setIntelligence, setLoading, setIntelligenceFor]);

  // Don't render if no medium identified at all
  if (!mediumLabel && !workspaceCtxAvailable) {
    return null;
  }
  if (!mediumLabel) {
    return null;
  }

  const confidenceBadge =
    intelligence?.confidenceLevel === "high" ? "●HIGH" :
    intelligence?.confidenceLevel === "medium" ? "●MED" :
    null;

  return (
    <TileWrapper
      title="Medium-Intelligenz"
      icon={<FlaskConical size={12} />}
      accent="teal"
      badge={confidenceBadge ?? undefined}
      badgeVariant={
        intelligence?.confidenceLevel === "high" ? "success" :
        intelligence?.confidenceLevel === "medium" ? "warning" :
        "default"
      }
      isLoading={loading}
    >
      {intelligence ? (
        <MediumEnrichedView mediumLabel={mediumLabel} data={intelligence} />
      ) : (
        <MediumContextFallback mediumLabel={mediumLabel} />
      )}
    </TileWrapper>
  );
}
