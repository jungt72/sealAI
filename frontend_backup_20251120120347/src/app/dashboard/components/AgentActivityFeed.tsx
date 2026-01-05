"use client";

import React from "react";

export type ReasoningEntry = {
  id: string;
  kind: "phase" | "agent" | "rag" | "system" | "error";
  title: string;
  text?: string;
  meta?: Record<string, unknown>;
  timestamp: string;
};

type AgentActivityFeedProps = {
  entries: ReasoningEntry[];
};

/**
 * Zeigt immer nur den/die übergebenen Eintrag/Einträge an.
 * In Kombination mit ChatContainer wird hier nur der letzte Eintrag
 * übergeben – dadurch wirkt es wie ein einzelnes „Grok-Reasoning“-Fenster,
 * das sich bei jedem Agentenschritt aktualisiert.
 */
export default function AgentActivityFeed({ entries }: AgentActivityFeedProps) {
  if (!entries.length) return null;

  return (
    <div className="mx-auto mt-2 w-full max-w-[768px] px-4">
      <div className="rounded-2xl border border-gray-200 bg-white/80 px-4 py-3 text-xs text-gray-700 shadow-sm backdrop-blur">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-semibold text-gray-800">Agenten-Aktivität</span>
          <span className="text-[10px] uppercase tracking-wide text-gray-400">
            Live Reasoning
          </span>
        </div>
        <div className="space-y-1.5">
          {entries.map((entry) => (
            <div key={entry.id} className="flex gap-2">
              <span className="mt-[2px] text-[10px] text-gray-400">
                {new Date(entry.timestamp).toLocaleTimeString("de-DE", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <div>
                <div className="font-medium text-gray-800">{entry.title}</div>
                {entry.text ? (
                  <div className="text-[11px] text-gray-600">{entry.text}</div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
