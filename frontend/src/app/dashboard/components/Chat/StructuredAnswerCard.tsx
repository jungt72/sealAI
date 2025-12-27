"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type StructuredAnswerSource = { label: string; url: string };
export type StructuredActionButton = { label: string; prompt: string };

export type StructuredAnswerPayload = {
  type: "structured_answer";
  result: string;
  justification?: string;
  confidence_score?: number;
  sources?: StructuredAnswerSource[];
  action_buttons?: StructuredActionButton[];
  details_markdown?: string;
};

type StructuredAnswerCardProps = {
  data: StructuredAnswerPayload;
  onAction?: (prompt: string) => void;
};

const SectionTitle = ({ children }: { children: React.ReactNode }) => (
  <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">{children}</div>
);

export function StructuredAnswerCard({ data, onAction }: StructuredAnswerCardProps) {
  const confidencePct =
    typeof data.confidence_score === "number"
      ? Math.round(Math.max(0, Math.min(1, data.confidence_score)) * 100)
      : null;

  return (
    <article className="w-full max-w-[720px] rounded-2xl border border-slate-200 bg-gradient-to-b from-white to-slate-50/40 shadow-[0_18px_60px_rgba(30,41,59,0.12)]">
      <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4">
        <div className="mt-1 h-8 w-8 rounded-full bg-emerald-50 text-emerald-700 flex items-center justify-center text-lg font-semibold shadow-inner">
          ⬢
        </div>
        <div className="flex-1 space-y-1">
          <SectionTitle>Result</SectionTitle>
          <div className="text-xl font-bold text-slate-900 leading-tight">{data.result}</div>
          {data.justification ? (
            <p className="text-sm text-slate-600 leading-relaxed">{data.justification}</p>
          ) : null}
        </div>
        {confidencePct !== null ? (
          <div className="flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 border border-amber-100 shadow-sm">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            {confidencePct}% Vertrauen
          </div>
        ) : null}
      </div>

      {data.details_markdown ? (
        <div className="px-5 py-4">
          <SectionTitle>Details</SectionTitle>
          <div className="prose prose-sm max-w-none text-slate-800 prose-headings:text-slate-900 prose-strong:text-slate-900 prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.details_markdown}</ReactMarkdown>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 border-t border-slate-100 px-5 py-4 sm:grid-cols-2">
        <div className="space-y-2">
          <SectionTitle>Sources</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {data.sources && data.sources.length
              ? data.sources.map((source) => (
                  <a
                    key={`${source.label}-${source.url}`}
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:-translate-y-[1px] hover:border-emerald-300 hover:text-emerald-700"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    {source.label}
                  </a>
                ))
              : (
                <span className="text-xs text-slate-400">Keine Quellen hinterlegt</span>
              )}
          </div>
        </div>

        <div className="space-y-2">
          <SectionTitle>Actions</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {data.action_buttons && data.action_buttons.length
              ? data.action_buttons.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => onAction?.(action.prompt)}
                    className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white shadow-[0_12px_30px_rgba(15,23,42,0.35)] transition hover:-translate-y-[1px] hover:bg-slate-800 disabled:opacity-50"
                  >
                    ⚙️ {action.label}
                  </button>
                ))
              : (
                <span className="text-xs text-slate-400">Keine Aktionen verfügbar</span>
              )}
          </div>
        </div>
      </div>
    </article>
  );
}

export default StructuredAnswerCard;
