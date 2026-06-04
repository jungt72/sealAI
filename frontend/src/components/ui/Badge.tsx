/**
 * Badge — Status-Kennzeichnung mit semantischen Varianten.
 * Passend zu den bestehenden Status-Anzeigen im Dashboard
 * (Dokument-Status, Governance-Klassen, RFQ-Status).
 */

import { cn } from "@/lib/utils";

// ── Varianten ─────────────────────────────────────────────────────────────────

const variantClasses = {
  /** Neutral / Standard */
  default: "bg-slate-100 text-slate-600 border-slate-200",
  /** Erfolgreich / Aktiv */
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  /** Warnung / In Bearbeitung */
  warning: "bg-amber-50 text-amber-700 border-amber-200",
  /** Fehler / Blockiert */
  error: "bg-red-50 text-red-600 border-red-200",
  /** Informativ / Pending */
  info: "bg-sky-50 text-sky-700 border-sky-200",
} as const;

type BadgeVariant = keyof typeof variantClasses;

// ── Typen ─────────────────────────────────────────────────────────────────────

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

// ── Komponente ────────────────────────────────────────────────────────────────

export default function Badge({
  variant = "default",
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.06em]",
        variantClasses[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
