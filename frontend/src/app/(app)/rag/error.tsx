"use client";

/**
 * Error Boundary für das RAG/Knowledge-Base-Segment.
 * Fängt unerwartete Render-Fehler ab und bietet einen Reset-Button an.
 */

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function RagError({ error, reset }: Props) {
  useEffect(() => {
    console.error("[RagError]", error);
  }, [error]);

  return (
    <div className="flex h-full w-full items-center justify-center bg-seal-bg p-8">
      <div className="flex max-w-md flex-col items-center gap-6 rounded-[30px] border border-slate-200 bg-white/95 p-10 text-center shadow-[0_22px_60px_rgba(15,23,42,0.08)]">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-red-100 bg-red-50">
          <AlertTriangle className="h-7 w-7 text-red-500" />
        </div>
        <div>
          <h2 className="mb-2 text-lg font-semibold text-slate-900">Knowledge Base nicht verfügbar</h2>
          <p className="text-sm leading-relaxed text-slate-500">
            Die Wissensdatenbank konnte nicht geladen werden.
            {error.digest ? (
              <span className="mt-1 block font-mono text-xs text-slate-400">
                Fehler-ID: {error.digest}
              </span>
            ) : null}
          </p>
        </div>
        <button
          onClick={reset}
          className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 active:scale-95"
        >
          Erneut versuchen
        </button>
      </div>
    </div>
  );
}
