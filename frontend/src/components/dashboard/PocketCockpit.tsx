"use client";

import React from "react";
import { AlertTriangle, Camera, CircleDot, Loader2 } from "lucide-react";

import type { ActionChip, PocketCockpitPatch } from "@/lib/contracts/agent";
import { cn } from "@/lib/utils";

/**
 * Mobile Pocket Cockpit (Blueprint §3.3, §4.3, §11.3/.4, §29.3).
 *
 * Renders only the four compressed sections — Erkannt / Kritisch / Nächster
 * Schritt / RFQ-Status — plus action chips and a No-empty-spinner progress
 * state (§4.6). Purely presentational: it renders backend-projected truth and
 * emits chip-selection events (no state mutation here — that is Patch 5).
 */

export type PocketCockpitProps = {
  patch: PocketCockpitPatch | null;
  actionChips?: ActionChip[];
  isLoading?: boolean;
  progressText?: string;
  onActionChip?: (chip: ActionChip) => void;
  className?: string;
};

function hasContent(patch: PocketCockpitPatch | null): boolean {
  if (!patch) return false;
  return Boolean(
    (patch.recognized && patch.recognized.length) ||
      (patch.critical && patch.critical.length) ||
      patch.next_step,
  );
}

const SEVERITY_TONE: Record<string, string> = {
  high: "text-red-600",
  medium: "text-amber-600",
  low: "text-slate-500",
  review: "text-seal-blue",
};

export function PocketCockpit({
  patch,
  actionChips = [],
  isLoading = false,
  progressText,
  onActionChip,
  className,
}: PocketCockpitProps) {
  // No-empty-spinner rule (§4.6): while a longer tier runs and nothing useful is
  // available yet, always show an immediate, readable progress line.
  if (isLoading && !hasContent(patch)) {
    return (
      <section
        data-testid="pocket-cockpit"
        aria-label="Pocket Cockpit"
        className={cn(
          "rounded-2xl border border-[#C7D2E2] bg-white p-4 text-sm text-seal-blue shadow-sm",
          className,
        )}
      >
        <div data-testid="pocket-progress" className="flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          <span>{progressText?.trim() || "Ich grenze deinen Fall gerade ein …"}</span>
        </div>
      </section>
    );
  }

  if (!patch) {
    return null;
  }

  const recognized = patch.recognized ?? [];
  const critical = patch.critical ?? [];
  const nextStep = patch.next_step ?? null;
  const nextQuestion =
    (nextStep && (nextStep.question as string | undefined)) || undefined;
  const nextAction = (nextStep && (nextStep.action as string | undefined)) || undefined;

  return (
    <section
      data-testid="pocket-cockpit"
      aria-label="Pocket Cockpit"
      className={cn(
        "rounded-2xl border border-[#C7D2E2] bg-white p-4 text-sm shadow-sm",
        className,
      )}
    >
      {isLoading ? (
        <div
          data-testid="pocket-progress"
          className="mb-3 flex items-center gap-2 text-xs font-medium text-seal-blue"
        >
          <Loader2 size={13} className="animate-spin" aria-hidden="true" />
          <span>{progressText?.trim() || "Aktualisiere …"}</span>
        </div>
      ) : null}

      {recognized.length > 0 ? (
        <div data-testid="pocket-recognized" className="mb-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Erkannt
          </p>
          <ul className="space-y-1">
            {recognized.map((item, index) => (
              <li
                key={`${item.label}-${index}`}
                className="flex items-center justify-between gap-3"
              >
                <span className="text-slate-600">{String(item.label ?? "")}</span>
                <span className="font-medium text-slate-950">{String(item.value ?? "")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {critical.length > 0 ? (
        <div data-testid="pocket-critical" className="mb-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Kritisch
          </p>
          <ul className="space-y-1">
            {critical.map((item, index) => {
              const severity = String(item.severity ?? "high");
              return (
                <li key={`${item.label}-${index}`} className="flex items-center gap-2">
                  <AlertTriangle
                    size={14}
                    className={cn(SEVERITY_TONE[severity] ?? "text-red-600")}
                    aria-hidden="true"
                  />
                  <span className="text-slate-800">{String(item.label ?? "")}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {nextStep ? (
        <div data-testid="pocket-next-step" className="mb-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Nächster Schritt
          </p>
          <p className="flex items-start gap-2 text-slate-950">
            <CircleDot size={14} className="mt-0.5 text-seal-blue" aria-hidden="true" />
            <span>{nextQuestion ?? nextAction ?? "—"}</span>
          </p>
        </div>
      ) : null}

      {actionChips.length > 0 ? (
        <div data-testid="pocket-action-chips" className="mb-3 flex flex-wrap gap-2">
          {actionChips.map((chip, index) => (
            <button
              key={`${chip.label}-${index}`}
              type="button"
              data-testid="pocket-action-chip"
              onClick={() => onActionChip?.(chip)}
              className="inline-flex items-center gap-1 rounded-full border border-[#C7D2E2] bg-[#F6F9FD] px-3 py-1.5 text-xs font-medium text-seal-blue transition-colors hover:bg-[#E8F0FA]"
            >
              {chip.action === "upload_photo" ? (
                <Camera size={13} aria-hidden="true" />
              ) : null}
              {chip.label}
            </button>
          ))}
        </div>
      ) : null}

      <div
        data-testid="pocket-rfq-status"
        className="flex items-center justify-between border-t border-slate-100 pt-2 text-xs"
      >
        <span className="text-slate-500">RFQ</span>
        <span className="font-semibold text-seal-blue">{patch.rfq_status ?? "DRAFT"}</span>
      </div>
    </section>
  );
}

export default PocketCockpit;
