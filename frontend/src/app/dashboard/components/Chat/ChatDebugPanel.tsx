"use client";

import { useState } from "react";
import type { FlowMeta } from "@/types/chat";
import type { ChatMeta } from "@/types/chatMeta";

type Props = {
  flow: FlowMeta | null;
  meta: ChatMeta | null;
};

const StatRow = ({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) => (
  <div className="flex items-center justify-between text-[11px] text-gray-600">
    <span className="font-medium text-gray-500">{label}</span>
    <span>{value ?? "–"}</span>
  </div>
);

export default function ChatDebugPanel({ flow, meta }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-4 left-4 z-30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="rounded-full border border-gray-300 bg-white/90 px-3 py-1 text-[11px] font-medium text-gray-700 shadow-sm transition hover:border-gray-400 hover:text-gray-900"
      >
        {open ? "Debug schließen" : "Debug"}
      </button>
      {open ? (
        <div className="mt-2 w-64 rounded-2xl border border-gray-200 bg-white/95 p-3 shadow-lg backdrop-blur">
          <div className="text-[12px] font-semibold text-gray-700">
            LangGraph Debug
          </div>
          <div className="mt-2 space-y-1">
            <StatRow label="Phase" value={flow?.phase ?? "–"} />
            <StatRow
              label="Confidence"
              value={
                typeof flow?.confidence === "number"
                  ? `${Math.round(flow.confidence * 100)}%`
                  : meta?.routing?.confidence != null
                    ? `${Math.round((meta.routing.confidence ?? 0) * 100)}%`
                    : "–"
              }
            />
            <StatRow label="Review-Loops" value={flow?.reviewLoops ?? 0} />
            <StatRow
              label="Memory Refs"
              value={flow?.longTermMemoryRefs ?? "0"}
            />
          </div>
          {meta?.quality?.critique ? (
            <div className="mt-2 rounded-md bg-amber-50 p-2 text-[11px] text-amber-800">
              <div className="font-semibold">Critique</div>
              <p>{meta.quality.critique}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
