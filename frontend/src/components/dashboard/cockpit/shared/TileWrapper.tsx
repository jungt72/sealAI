"use client";

/**
 * TileWrapper — Consistent dark-card chrome for all cockpit tiles.
 * Each tile category has a coloured top-border accent:
 *   blue   → technical parameters
 *   teal   → medium intelligence
 *   amber  → capture status / checklist
 *   green  → recommendation / matching
 */

import type { ReactNode } from "react";

export type TileAccent = "blue" | "teal" | "amber" | "green" | "none";
export type BadgeVariant = "default" | "success" | "warning" | "error";

interface TileWrapperProps {
  title: string;
  icon?: ReactNode;
  badge?: string;
  badgeVariant?: BadgeVariant;
  accent?: TileAccent;
  isLoading?: boolean;
  isEmpty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}

const ACCENT_CLASSES: Record<TileAccent, string> = {
  blue:  "border-t-blue-500",
  teal:  "border-t-teal-500",
  amber: "border-t-amber-500",
  green: "border-t-green-500",
  none:  "border-t-transparent",
};

const BADGE_CLASSES: Record<BadgeVariant, string> = {
  default: "bg-slate-700 text-slate-200",
  success: "bg-green-900/60 text-green-300",
  warning: "bg-amber-900/60 text-amber-300",
  error:   "bg-red-900/60 text-red-300",
};

export default function TileWrapper({
  title,
  icon,
  badge,
  badgeVariant = "default",
  accent = "none",
  isLoading = false,
  isEmpty = false,
  emptyMessage = "Noch nicht erfasst",
  children,
}: TileWrapperProps) {
  return (
    <div
      className={`animate-fadeIn overflow-hidden rounded-[10px] border border-gray-800 border-t-2 bg-[#0f1117] ${ACCENT_CLASSES[accent]}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-3 py-[9px]">
        <div className="flex items-center gap-1.5">
          {icon && <span className="text-gray-400">{icon}</span>}
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-gray-400">
            {title}
          </span>
        </div>
        {badge && (
          <span
            className={`rounded-full px-[7px] py-[2px] text-[10px] font-medium ${BADGE_CLASSES[badgeVariant]}`}
          >
            {badge}
          </span>
        )}
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="space-y-2 p-3">
          <div className="h-3 w-3/4 animate-pulse rounded bg-gray-800" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-gray-800" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-gray-800" />
        </div>
      ) : isEmpty ? (
        <div className="px-3 py-[10px] text-[11px] text-gray-600 italic">
          {emptyMessage}
        </div>
      ) : (
        <div>{children}</div>
      )}
    </div>
  );
}
