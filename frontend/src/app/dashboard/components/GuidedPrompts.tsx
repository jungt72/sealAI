"use client";

import React from "react";

export type GuidedPrompt = { label: string; prompt: string };

type GuidedPromptsProps = {
  prompts: GuidedPrompt[];
  onSelect: (prompt: string) => void;
};

export function GuidedPrompts({ prompts, onSelect }: GuidedPromptsProps) {
  if (!prompts.length) return null;

  return (
    <div className="mx-auto w-full max-w-3xl rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-[0_14px_44px_rgba(15,23,42,0.12)]">
      <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Vorschläge</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {prompts.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => onSelect(p.prompt)}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:-translate-y-[1px] hover:border-emerald-300 hover:text-emerald-700"
          >
            💡 {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default GuidedPrompts;
