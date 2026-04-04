"use client";

/**
 * Error Boundary für das Dashboard-Segment.
 * Fängt unerwartete Render-Fehler ab und bietet einen Reset-Button an.
 */

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function DashboardError({ error, reset }: Props) {
  useEffect(() => {
    console.error("[DashboardError]", error);

    // Stale client JS after PM2 restart — Server Action IDs no longer match.
    // Hard reload fetches the new JS bundle and resolves the mismatch.
    // 2.5s delay so the error.message is visible for diagnosis before reload.
    const isStaleAction =
      error.message?.includes("Failed to find Server Action") ||
      error.message?.includes("Server Action");
    if (isStaleAction) {
      const timer = setTimeout(() => window.location.reload(), 2500);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return (
    <div className="flex h-full w-full items-center justify-center bg-seal-bg p-8">
      <div className="flex max-w-md flex-col items-center gap-6 rounded-[30px] border border-slate-200 bg-white/95 p-10 text-center shadow-[0_22px_60px_rgba(15,23,42,0.08)]">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-red-100 bg-red-50">
          <AlertTriangle className="h-7 w-7 text-red-500" />
        </div>
        <div>
          <h2 className="mb-2 text-lg font-semibold text-slate-900">Etwas ist schiefgelaufen</h2>
          <p className="text-sm leading-relaxed text-slate-500">
            Das Dashboard konnte nicht geladen werden.
            {error.message ? (
              <span className="mt-2 block font-mono text-xs text-red-600 break-all">
                {error.message}
              </span>
            ) : null}
            {error.stack ? (
              <span className="mt-1 block font-mono text-xs text-slate-400 break-all">
                {error.stack.split("\n")[1]}
              </span>
            ) : null}
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
