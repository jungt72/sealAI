"use client";

/**
 * CockpitHeader — Sticky header bar for the Engineering Cockpit panel.
 *
 * Shows:
 *  - "Cockpit" title with diamond icon
 *  - Case ID (first 8 chars), greyed out
 *  - Export stub button
 *
 * Must remain sticky at the top of the WorkspacePane scroll container.
 */

import { Download, Gem } from "lucide-react";
import { useCaseStore } from "@/lib/store/caseStore";

export default function CockpitHeader() {
  const caseId = useCaseStore((s) => s.caseId);
  const shortId = caseId ? caseId.slice(0, 8) : null;

  return (
    <>
      <div className="sticky top-0 z-20 flex items-center justify-between bg-[#f8fafc] px-4 py-[10px]">
        {/* Left: title + case id */}
        <div className="flex items-center gap-2">
          <Gem size={13} className="text-blue-500" />
          <span className="text-[12px] font-semibold tracking-wide text-[#1a2332]">
            Cockpit
          </span>
          {shortId && (
            <span className="font-mono text-[10px] text-slate-400">
              #{shortId}
            </span>
          )}
        </div>

        {/* Right: export button */}
        <button
          onClick={() => console.log("export", caseId)}
          title="Export"
          className="flex items-center gap-1.5 rounded-lg border border-[#e2e8f0] bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-500 transition-colors hover:border-blue-300 hover:text-blue-600 active:scale-95"
        >
          <Download size={11} />
          Export
        </button>
      </div>

      {/* Thin separator */}
      <div className="h-px bg-[#e8ecf1]" />
    </>
  );
}
