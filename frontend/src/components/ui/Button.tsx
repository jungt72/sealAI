/**
 * Button — Universeller Button mit Varianten, Größen und Loading-State.
 * Nutzt Tailwind-Tokens aus der SealAI-Palette, kein ad-hoc Hex.
 */

import { forwardRef } from "react";
import { cn } from "@/lib/utils";

// ── Varianten & Größen ────────────────────────────────────────────────────────

const variantClasses = {
  /** Primäre Aktion — iOS-Blau */
  primary:
    "bg-seal-action text-white shadow-sm hover:bg-seal-action-hover active:scale-95 disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none",
  /** Sekundäre Aktion — weißer Rahmen */
  secondary:
    "border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 active:scale-95 disabled:opacity-50",
  /** Ghost — kein Hintergrund, subtiles Hover */
  ghost:
    "text-slate-600 hover:bg-white/60 hover:text-seal-rich active:scale-95 disabled:opacity-40",
  /** Danger — destruktive Aktion */
  danger:
    "bg-red-500 text-white shadow-sm hover:bg-red-600 active:scale-95 disabled:opacity-50",
} as const;

const sizeClasses = {
  sm: "h-8 rounded-lg px-3 text-xs font-medium gap-1.5",
  md: "h-10 rounded-xl px-4 text-sm font-medium gap-2",
  lg: "h-11 rounded-xl px-5 text-base font-medium gap-2",
} as const;

// ── Typen ─────────────────────────────────────────────────────────────────────

type ButtonVariant = keyof typeof variantClasses;
type ButtonSize = keyof typeof sizeClasses;

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Zeigt einen Spinner und deaktiviert den Button */
  loading?: boolean;
}

// ── Komponente ────────────────────────────────────────────────────────────────

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "secondary",
      size = "md",
      loading = false,
      disabled,
      className,
      children,
      ...rest
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(
          // Basis
          "inline-flex items-center justify-center transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-seal-action/50 disabled:cursor-not-allowed",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...rest}
      >
        {loading ? (
          <>
            <Spinner />
            {children}
          </>
        ) : (
          children
        )}
      </button>
    );
  },
);
Button.displayName = "Button";

export default Button;

// ── Interner Spinner ──────────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
