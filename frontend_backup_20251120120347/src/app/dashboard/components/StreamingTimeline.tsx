"use client";

import React from "react";

export type TimelineStepStatus = "pending" | "active" | "done";
export type TimelineStepKind = "system" | "phase" | "agent";

export type TimelineStep = {
  id: string;
  label: string;
  kind: TimelineStepKind;
  status: TimelineStepStatus;
  description?: string;
  timestamp?: string;
};

type StreamingTimelineProps = {
  steps: TimelineStep[];
};

const statusColors: Record<
  TimelineStepStatus,
  { dot: string; card: string; border: string; text: string }
> = {
  pending: {
    dot: "bg-gray-300",
    card: "bg-white",
    border: "border-gray-200",
    text: "text-gray-400",
  },
  active: {
    dot: "bg-emerald-500",
    card: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-700",
  },
  done: {
    dot: "bg-emerald-600",
    card: "bg-white",
    border: "border-emerald-300",
    text: "text-emerald-700",
  },
};

const kindLabel: Record<TimelineStepKind, string> = {
  system: "System",
  phase: "Phase",
  agent: "Agent",
};

const formatTime = (iso?: string) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
};

export default function StreamingTimeline({ steps }: StreamingTimelineProps) {
  if (!steps || steps.length === 0) {
    return (
      <div className="flex h-full flex-col gap-3">
        <h2 className="text-sm font-semibold text-gray-700">
          LangGraph Ablauf
        </h2>
        <p className="text-xs text-gray-500">
          Die Timeline wird angezeigt, sobald du eine Sitzung startest.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-gray-700">
          LangGraph Ablauf
        </h2>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">
          Live
        </span>
      </div>

      <div className="flex-1 overflow-y-auto pr-1">
        <ol className="flex flex-col gap-3">
          {steps.map((step, index) => {
            const colors = statusColors[step.status];
            const timeLabel = formatTime(step.timestamp);
            const isLast = index === steps.length - 1;

            return (
              <li key={step.id} className="relative flex items-stretch gap-2">
                {/* Vertikale Linie + Statuspunkt */}
                <div className="flex flex-col items-center">
                  <div
                    className={`mt-1 h-2 w-2 rounded-full ${colors.dot}`}
                  />
                  {!isLast && (
                    <div className="mt-1 h-full w-px flex-1 bg-gray-200" />
                  )}
                </div>

                {/* Karte */}
                <div
                  className={`flex-1 rounded-xl border px-3 py-2 text-xs shadow-sm transition-colors ${colors.card} ${colors.border}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`font-semibold ${colors.text}`}>
                      {step.label}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide text-gray-400">
                      {kindLabel[step.kind]}
                    </span>
                  </div>

                  {step.description ? (
                    <p className="mt-1 text-[11px] text-gray-600">
                      {step.description}
                    </p>
                  ) : null}

                  <div className="mt-1 flex items-center justify-between text-[10px] text-gray-400">
                    <span>
                      Status:{" "}
                      {step.status === "pending"
                        ? "wartet"
                        : step.status === "active"
                        ? "läuft"
                        : "abgeschlossen"}
                    </span>
                    {timeLabel ? <span>{timeLabel}</span> : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
