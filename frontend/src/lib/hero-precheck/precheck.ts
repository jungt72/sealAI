/**
 * Deterministic hero precheck — NO LLM, NO material/manufacturer recommendation.
 *
 * This module is the single source of truth for the homepage hero teaser logic.
 * It only structures the input, computes the one deterministic value it can
 * (circumferential speed for rotary/RWDR cases) and reports a coarse readiness
 * status plus the open points that still block a real assessment. It never
 * decides a seal, a material, or a manufacturer — that is the product's job
 * behind the free login, not the homepage.
 */

export type SealType = "rwdr" | "o_ring" | "hydraulic_seal" | "ptfe_part" | "unknown";
export type Situation = "replacement" | "leakage" | "new_design" | "material_question";
export type GateStatus =
  | "initial"
  | "insufficient"
  | "preliminary"
  | "actionable"
  | "critical_unknowns";
export type DataQualityLabel = "Niedrig" | "Mittel" | "Gut";

export interface HeroPrecheckInput {
  sealType?: SealType;
  situation?: Situation;
  medium?: string;
  shaftDiameterMm?: number;
  rpm?: number;
}

export interface HeroPrecheckResult {
  status: GateStatus;
  /** German status label for display. */
  statusLabel: string;
  dataQualityLabel: DataQualityLabel;
  /** Only present for rotary/RWDR cases with shaft diameter AND rpm. */
  circumferentialSpeedMs?: number;
  /** Capped at 3 for the compact hero result. */
  missingPoints: string[];
  message: string;
}

/**
 * v = π · d · n / 60000  (d in mm, n in rpm → v in m/s)
 * Example: 45 mm, 1500 rpm → 3.53 m/s.
 */
export function calculateCircumferentialSpeedMs(shaftDiameterMm: number, rpm: number): number {
  return (Math.PI * shaftDiameterMm * rpm) / 60000;
}

function isPresentNumber(value: number | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

const STATUS_LABEL: Record<GateStatus, string> = {
  initial: "Bereit zum Vorcheck",
  insufficient: "Noch nicht bewertbar",
  critical_unknowns: "Kritische Angaben fehlen",
  preliminary: "Vorläufig bewertbar",
  actionable: "Vorläufig bewertbar",
};

const DATA_QUALITY: Record<GateStatus, DataQualityLabel> = {
  initial: "Niedrig",
  insufficient: "Niedrig",
  critical_unknowns: "Mittel",
  preliminary: "Mittel",
  actionable: "Gut",
};

const MESSAGE: Record<GateStatus, string> = {
  initial: "Wählen Sie Dichtungstyp und Situation, um den Vorcheck zu starten.",
  insufficient:
    "Für eine erste Einordnung fehlen noch grundlegende Angaben. Ergänzen Sie Medium und die wichtigsten Betriebsdaten.",
  critical_unknowns:
    "Für RWDR fehlen entscheidende Angaben. Ohne Wellendurchmesser und Drehzahl ist keine belastbare Vorprüfung möglich.",
  preliminary:
    "Für eine belastbare Bewertung fehlen noch wichtige Anwendungsdaten. sealingAI führt Sie Schritt für Schritt zur vollständigen Analyse.",
  actionable:
    "Für eine belastbare Bewertung fehlen noch wichtige Anwendungsdaten. sealingAI führt Sie Schritt für Schritt zur vollständigen Analyse.",
};

function buildMissingPoints(
  input: HeroPrecheckInput,
  hasMedium: boolean,
  isRwdr: boolean,
  hasShaft: boolean,
  hasRpm: boolean,
): string[] {
  const points: string[] = [];
  if (!hasMedium) points.push("Medium");
  if (isRwdr && !hasShaft) points.push("Wellendurchmesser");
  if (isRwdr && !hasRpm) points.push("Drehzahl");
  // Domain open points that are always relevant before a real assessment.
  points.push("Druckspitzen", "Wellenoberfläche", "Umgebung / Verschmutzung");
  return Array.from(new Set(points)).slice(0, 3);
}

/**
 * Coarse, deterministic readiness gate. Precedence is intentional:
 * initial → actionable → critical_unknowns → preliminary → insufficient.
 */
export function evaluatePrecheck(input: HeroPrecheckInput): HeroPrecheckResult {
  const hasMedium = Boolean(input.medium && input.medium.trim().length > 0);
  const hasShaft = isPresentNumber(input.shaftDiameterMm);
  const hasRpm = isPresentNumber(input.rpm);
  const isRwdr = input.sealType === "rwdr";

  const presentCount = [
    input.sealType !== undefined,
    input.situation !== undefined,
    hasMedium,
    hasShaft,
    hasRpm,
  ].filter(Boolean).length;

  let status: GateStatus;
  if (presentCount === 0) {
    status = "initial";
  } else if (isRwdr && hasMedium && hasShaft && hasRpm) {
    status = "actionable";
  } else if (isRwdr && (!hasShaft || !hasRpm)) {
    status = presentCount >= 2 ? "critical_unknowns" : "insufficient";
  } else if (hasMedium && (hasShaft || hasRpm)) {
    status = "preliminary";
  } else {
    status = "insufficient";
  }

  const canCompute = isRwdr && hasShaft && hasRpm;
  const circumferentialSpeedMs = canCompute
    ? Math.round(calculateCircumferentialSpeedMs(input.shaftDiameterMm!, input.rpm!) * 100) / 100
    : undefined;

  return {
    status,
    statusLabel: STATUS_LABEL[status],
    dataQualityLabel: DATA_QUALITY[status],
    circumferentialSpeedMs,
    missingPoints: status === "initial" ? [] : buildMissingPoints(input, hasMedium, isRwdr, hasShaft, hasRpm),
    message: MESSAGE[status],
  };
}

/** Formats a speed as German de-DE "3,53" (no unit). */
export function formatSpeedDe(value: number): string {
  return value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
