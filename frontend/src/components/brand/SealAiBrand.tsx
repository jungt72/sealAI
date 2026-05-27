"use client";

import React from "react";

import { cn } from "@/lib/utils";

export type SealAiIconProps = Omit<React.SVGProps<SVGSVGElement>, "ref"> & {
  size?: number;
  strokeWidth?: number;
};

export type SealAiIconComponent = React.ComponentType<SealAiIconProps>;

function IconSvg({
  size = 24,
  strokeWidth = 1.9,
  children,
  className,
  ...props
}: SealAiIconProps & { children: React.ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

function SealRing({ muted = false }: { muted?: boolean }) {
  return (
    <>
      <circle cx="12" cy="12" r="9" opacity={muted ? 0.18 : 0.34} strokeDasharray="12 5" />
      <circle cx="12" cy="12" r="7.25" opacity={muted ? 0.12 : 0.2} strokeDasharray="4 7" />
    </>
  );
}

export function SealAiSymbol({
  size = 24,
  strokeWidth = 1.85,
  className,
  ...props
}: SealAiIconProps) {
  return (
    <IconSvg size={size} strokeWidth={strokeWidth} className={cn("text-seal-blue", className)} {...props}>
      <path d="M12 2.9 19.7 7.35v9.3L12 21.1l-7.7-4.45v-9.3L12 2.9Z" />
      <path d="M8.15 8.8 12 6.55l3.85 2.25" />
      <path d="M15.85 8.8v3.05L8.15 16.2" />
      <path d="M8.15 16.2 12 18.45l3.85-2.25" />
      <path d="M8.15 8.8v3.05l7.7 4.35" />
    </IconSvg>
  );
}

export function SealAiLogoMark({
  size = 38,
  className,
  decorative = false,
}: {
  size?: number;
  className?: string;
  decorative?: boolean;
}) {
  return (
    <span
      className={cn("inline-grid shrink-0 place-items-center text-seal-blue", className)}
      style={{ width: size, height: size }}
      aria-hidden={decorative ? "true" : undefined}
    >
      <svg
        role={decorative ? undefined : "img"}
        aria-label={decorative ? undefined : "sealingAI Logo"}
        viewBox="0 0 64 64"
        width={size}
        height={size}
        className="h-full w-full overflow-visible drop-shadow-[0_4px_9px_rgba(0,42,91,0.13)]"
      >
        <defs>
          <linearGradient id="sealai-mark-blue" x1="10" x2="54" y1="8" y2="8" gradientUnits="userSpaceOnUse">
            <stop stopColor="#0B3B82" />
            <stop offset="0.48" stopColor="#002A5B" />
            <stop offset="1" stopColor="#001F45" />
          </linearGradient>
          <linearGradient id="sealai-mark-white" x1="18" x2="46" y1="18" y2="54" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FFFFFF" />
            <stop offset="1" stopColor="#F7F9FC" />
          </linearGradient>
          <filter id="sealai-mark-soft-shadow" x="-16" y="-10" width="96" height="92" colorInterpolationFilters="sRGB">
            <feDropShadow dx="0" dy="2.5" stdDeviation="2.2" floodColor="#001F45" floodOpacity="0.2" />
          </filter>
        </defs>
        <g filter="url(#sealai-mark-soft-shadow)">
          <rect x="8" y="7.5" width="48" height="11" rx="5.5" fill="url(#sealai-mark-blue)" />
          <rect x="28" y="21" width="16" height="16" rx="4.4" fill="url(#sealai-mark-white)" stroke="#E6EBF2" strokeWidth="0.65" />
          <rect x="18" y="31" width="16" height="16" rx="4.4" fill="url(#sealai-mark-white)" stroke="#E6EBF2" strokeWidth="0.65" />
          <rect x="36" y="42" width="16" height="16" rx="4.4" fill="url(#sealai-mark-white)" stroke="#E6EBF2" strokeWidth="0.65" />
          <rect x="18" y="51" width="16" height="16" rx="4.4" fill="url(#sealai-mark-white)" stroke="#E6EBF2" strokeWidth="0.65" />
          <path
            d="M33.9 36.2c2.7-.15 5.2-1.3 7.4-3.5M33.9 45.7c2.4.25 4.5 1.4 6.2 3.25M33.9 45.7c-2.7-.2-5.2-1.4-7.3-3.5M33.9 36.2c-2.45-.25-4.55-1.35-6.25-3.2"
            stroke="#DCE3EC"
            strokeWidth="1.1"
            strokeLinecap="round"
            fill="none"
            opacity="0.7"
          />
        </g>
      </svg>
    </span>
  );
}

export function SealAiCornerMark({
  size = 34,
  className,
  decorative = false,
}: {
  size?: number;
  className?: string;
  decorative?: boolean;
}) {
  return (
    <span
      className={cn("inline-grid shrink-0 place-items-center text-seal-blue", className)}
      style={{ width: size, height: size }}
      aria-hidden={decorative ? "true" : undefined}
    >
      <svg
        role={decorative ? undefined : "img"}
        aria-label={decorative ? undefined : "sealingAI Logo"}
        data-testid="sealai-circular-s-logo"
        viewBox="0 0 64 64"
        width={size}
        height={size}
        className="h-full w-full overflow-visible drop-shadow-[0_2px_5px_rgba(0,42,91,0.14)]"
        fill="none"
      >
        <defs>
          <linearGradient id="sealai-circular-s-blue" x1="16" x2="49" y1="10" y2="56" gradientUnits="userSpaceOnUse">
            <stop stopColor="#004986" />
            <stop offset="0.5" stopColor="#002F68" />
            <stop offset="1" stopColor="#002653" />
          </linearGradient>
        </defs>
        <path
          d="M30 7.4a24.6 24.6 0 0 0 0 49.2"
          stroke="url(#sealai-circular-s-blue)"
          strokeWidth="5.6"
          strokeLinecap="butt"
        />
        <path
          d="M34 7.4a24.6 24.6 0 0 1 0 49.2"
          stroke="url(#sealai-circular-s-blue)"
          strokeWidth="5.6"
          strokeLinecap="butt"
        />
        <path
          d="M46 26.4H35.6c-5.4 0-9.5 3.85-9.5 9.25"
          stroke="url(#sealai-circular-s-blue)"
          strokeWidth="7.1"
          strokeLinecap="butt"
          strokeLinejoin="round"
        />
        <path
          d="M18.1 40.2h10.35c5.5 0 9.45-3.9 9.45-9.35"
          stroke="url(#sealai-circular-s-blue)"
          strokeWidth="7.1"
          strokeLinecap="butt"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function SealAiWordmark({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      aria-label={compact ? "sealingAI" : "sealingAI Intelligence"}
      data-testid="sealai-brand-wordmark"
      className={cn("flex min-w-0 items-center gap-2.5", className)}
    >
      <SealAiLogoMark size={compact ? 32 : 38} decorative />
      <div className="min-w-0">
        <div className="flex items-baseline gap-1 text-[22px] font-semibold leading-none tracking-[0] text-seal-blue">
          <span>sealing</span>
          <span className="text-[#1A73E8]">AI</span>
        </div>
        {!compact ? (
          <div className="mt-1 text-[10px] font-semibold uppercase leading-none tracking-[0.18em] text-[#5F6368]">
            Intelligence
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function CommunicationIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M6.25 8.2h11.5a2.2 2.2 0 0 1 2.2 2.2v4.1a2.2 2.2 0 0 1-2.2 2.2H11.2l-4.55 3.15v-3.15h-.4a2.2 2.2 0 0 1-2.2-2.2v-4.1a2.2 2.2 0 0 1 2.2-2.2Z" />
      <path d="M8.3 12.25h7.4" opacity="0.55" />
    </IconSvg>
  );
}

export function DemandAnalysisIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <SealRing />
      <circle cx="12" cy="12" r="3.25" />
      <circle cx="12" cy="12" r="1.15" fill="currentColor" stroke="none" />
    </IconSvg>
  );
}

export function CaseStateIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <SealRing />
      <path d="m8.2 12.2 2.45 2.45 5.25-5.35" />
    </IconSvg>
  );
}

export function ParameterIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M7 4.7v14.6" />
      <path d="M12 4.7v14.6" />
      <path d="M17 4.7v14.6" />
      <circle cx="7" cy="9" r="1.55" />
      <circle cx="12" cy="15.3" r="1.55" />
      <circle cx="17" cy="11.4" r="1.55" />
    </IconSvg>
  );
}

export function MediumIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <SealRing muted />
      <path d="M12 4.7s5 5.35 5 9.05a5 5 0 0 1-10 0c0-3.7 5-9.05 5-9.05Z" />
    </IconSvg>
  );
}

export function MaterialIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="m4.6 8.2 7.4-3.55 7.4 3.55-7.4 3.55-7.4-3.55Z" />
      <path d="m4.6 12.1 7.4 3.55 7.4-3.55" />
      <path d="m4.6 15.95 7.4 3.55 7.4-3.55" />
    </IconSvg>
  );
}

export function ApplicationIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M4.6 19.25V9.7l4.35 2.15V8.7l4.25 2.1V6.9l6.2 3.05v9.3H4.6Z" />
      <path d="M8.25 16.2h2" />
      <path d="M13 16.2h2" />
      <circle cx="17.15" cy="16.25" r="1.25" />
    </IconSvg>
  );
}

export function RiskIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M12 4.4 21 19H3L12 4.4Z" />
      <path d="M12 9.15v4.65" />
      <path d="M12 16.8h.01" />
    </IconSvg>
  );
}

export function EvidenceRagIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M7 3.9h6.8L18 8.1v11.7H7V3.9Z" />
      <path d="M13.65 4.15V8.2h4.05" />
      <path d="m9.25 14.3 1.75 1.75 3.8-3.9" />
    </IconSvg>
  );
}

export function ManufacturerMatchingIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <circle cx="12" cy="5.8" r="2" />
      <circle cx="6.3" cy="17.35" r="2" />
      <circle cx="17.7" cy="17.35" r="2" />
      <path d="M11.15 7.65 7.15 15.55" />
      <path d="m12.85 7.65 4 7.9" />
      <path d="M8.35 17.35h7.3" />
    </IconSvg>
  );
}

export function RfqPreviewIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M6.6 3.9h7.2L18 8.1v11.8H6.6V3.9Z" />
      <path d="M13.65 4.15V8.2h4.05" />
      <path d="M9.2 12.25h5.6" />
      <path d="M9.2 15.45h3.8" />
      <circle cx="16.75" cy="18.1" r="1.4" />
    </IconSvg>
  );
}

export function RevisionFreezeIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M12 4.1v15.8" />
      <path d="m7.15 6.8 9.7 10.4" />
      <path d="m16.85 6.8-9.7 10.4" />
      <path d="m9.25 4.95 2.75 2 2.75-2" />
      <path d="m9.25 19.05 2.75-2 2.75 2" />
    </IconSvg>
  );
}

export function ConsentIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M12 3.8 18.4 6.4v5.05c0 4.2-2.45 6.95-6.4 8.75-3.95-1.8-6.4-4.55-6.4-8.75V6.4L12 3.8Z" />
      <path d="m8.9 12.2 2.05 2.05 4.1-4.45" />
    </IconSvg>
  );
}

export function TenantPrivacyIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <rect x="5.5" y="10.4" width="13" height="9.15" rx="2" />
      <path d="M8.2 10.4V8.1a3.8 3.8 0 0 1 7.6 0v2.3" />
      <path d="M12 14.05v2.15" />
    </IconSvg>
  );
}

export function UncertaintyIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <SealRing />
      <path d="M9.55 9.35a2.7 2.7 0 1 1 3.25 2.65c-.75.2-.95.55-.95 1.25v.45" />
      <path d="M12 17.25h.01" />
    </IconSvg>
  );
}

export function DecisionMatrixIcon(props: SealAiIconProps) {
  return (
    <IconSvg {...props}>
      <path d="M6.1 7.1h4.4" />
      <path d="M13.5 7.1h4.4" />
      <path d="M6.1 12h4.4" />
      <path d="M13.5 12h4.4" />
      <path d="M6.1 16.9h4.4" />
      <path d="M13.5 16.9h4.4" />
      <circle cx="4.1" cy="7.1" r=".55" fill="currentColor" stroke="none" />
      <circle cx="11.5" cy="12" r=".55" fill="currentColor" stroke="none" />
      <circle cx="19.9" cy="16.9" r=".55" fill="currentColor" stroke="none" />
    </IconSvg>
  );
}

export function SealAiFramedIcon({
  icon: Icon,
  size = 44,
  iconSize = 21,
  className,
}: {
  icon: SealAiIconComponent;
  size?: number;
  iconSize?: number;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "relative inline-grid shrink-0 place-items-center rounded-full text-seal-blue",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 44 44" fill="none" aria-hidden="true">
        <circle cx="22" cy="22" r="18.5" stroke="currentColor" strokeWidth="1.75" strokeDasharray="14 6" opacity="0.86" />
        <circle cx="22" cy="22" r="15" stroke="currentColor" strokeWidth="1.45" strokeDasharray="4 7" opacity="0.24" />
      </svg>
      <Icon size={iconSize} strokeWidth={1.9} />
    </span>
  );
}
