import type { ActionChip, PocketCockpitPatch } from "@/lib/contracts/agent";

/**
 * Frontend Pocket-Cockpit mapper (Blueprint §4.3, §11.3/.4).
 *
 * Mirrors the backend `app.agent.v92.pocket_cockpit` projection: it compresses
 * already-derived cockpit truth into the four mobile sections plus action-chip
 * affordances. It invents no engineering truth — it only re-shapes inputs that
 * the desktop cockpit already computed.
 */

export type PocketRecognizedInput = {
  label: string;
  value: string | number | null | undefined;
  status?: string;
};

export type PocketCriticalInput = {
  label: string;
  severity?: string;
};

export type PocketCockpitInput = {
  recognizedFacts?: PocketRecognizedInput[];
  criticalItems?: PocketCriticalInput[];
  nextQuestion?: { question?: string | null; field?: string | null } | null;
  isRfqReady?: boolean;
};

export const MAX_RECOGNIZED = 4;
export const MAX_CRITICAL = 3;

// Placeholder values the desktop view-model uses for "not yet known".
const PLACEHOLDER_VALUES = new Set(["", "—", "-", "noch offen", "unbekannt"]);

function isMeaningful(value: string | number | null | undefined): boolean {
  if (value === null || value === undefined) return false;
  return !PLACEHOLDER_VALUES.has(String(value).trim().toLowerCase());
}

export function buildPocketCockpitView(
  input: PocketCockpitInput,
): { patch: PocketCockpitPatch; chips: ActionChip[] } {
  const recognized = (input.recognizedFacts ?? [])
    .filter((fact) => fact.label && isMeaningful(fact.value))
    .slice(0, MAX_RECOGNIZED)
    .map((fact) => ({
      label: fact.label,
      value: String(fact.value),
      status: fact.status ?? "confirmed",
    }));

  const critical = (input.criticalItems ?? [])
    .filter((item) => Boolean(item.label))
    .slice(0, MAX_CRITICAL)
    .map((item) => ({ label: item.label, severity: item.severity ?? "high" }));

  const question = input.nextQuestion?.question?.trim() || "";
  const field = input.nextQuestion?.field ?? null;
  const nextStep = question
    ? { question, ...(field ? { field } : {}) }
    : null;

  // Coarse status until Patch 9 introduces the full readiness model.
  const rfqStatus = input.isRfqReady ? "MANUFACTURER_REVIEW_READY" : "DRAFT";

  const patch: PocketCockpitPatch = {
    recognized,
    critical,
    next_step: nextStep,
    rfq_status: rfqStatus,
    details_available: true,
    collapsed_by_default: true,
  };

  // Minimal default affordances for the active question. Selecting one only
  // emits an event (State-Gate handling is Patch 5).
  const chips: ActionChip[] = nextStep
    ? [
        { label: "Weiß ich nicht", value: "unknown", field },
        { label: "Foto senden", action: "upload_photo" },
      ]
    : [];

  return { patch, chips };
}

export type ResolvedPocketCockpit = {
  patch: PocketCockpitPatch;
  chips: ActionChip[];
  /** Where the rendered Pocket Cockpit came from. */
  source: "backend" | "client_derived";
};

/**
 * Prefer the backend-provided V1.6 Pocket Cockpit (Patch 6) when present,
 * otherwise fall back to the existing client-derived view.
 *
 * When the backend supplies `pocket_cockpit_patch` (mobile triage), it is
 * rendered verbatim — the client invents no engineering truth on top of it.
 * Legacy / non-mobile turns (no backend patch) keep the existing
 * `buildPocketCockpitView` behaviour unchanged.
 */
export function resolvePocketCockpitView(
  backend: { patch?: PocketCockpitPatch | null; chips?: ActionChip[] | null } | null,
  fallbackInput: PocketCockpitInput,
): ResolvedPocketCockpit {
  const backendPatch = backend?.patch ?? null;
  if (backendPatch) {
    return {
      patch: backendPatch,
      chips: Array.isArray(backend?.chips) ? backend.chips : [],
      source: "backend",
    };
  }
  const { patch, chips } = buildPocketCockpitView(fallbackInput);
  return { patch, chips, source: "client_derived" };
}
