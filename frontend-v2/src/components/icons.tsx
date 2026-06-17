import type { ReactNode } from "react";

/** Inline SVG icon set for the pilot-ui rail + pill — stroke-based, 20px grid, currentColor.
 * Deliberately no icon dependency: six small glyphs do not justify a package. */

type IconProps = { size?: number };

function Svg({ size = 20, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** Brandmark: an O-ring — the product, reduced to its glyph. Drawn thicker, no cap rounding. */
export function RingIcon({ size = 26 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="6.4" stroke="currentColor" strokeWidth="3.2" />
    </svg>
  );
}

/** Sidebar toggle: a panel with a left column — the standard collapse/expand glyph. */
export function PanelLeftIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="4" width="14" height="12" rx="2" />
      <path d="M8 4v12" />
    </Svg>
  );
}

/** Compose / new question (pencil). */
export function ComposeIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M13.7 4.2l2.1 2.1L7 15.1l-3 .9.9-3 8.8-8.8z" />
    </Svg>
  );
}

export function SearchIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="9" cy="9" r="5.2" />
      <path d="M13 13l4 4" />
    </Svg>
  );
}

/** History (clock). */
export function HistoryIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="10" cy="10" r="6.6" />
      <path d="M10 6.4V10l2.4 1.8" />
    </Svg>
  );
}

export function SettingsIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="10" cy="10" r="2.4" />
      <path d="M10 3.2v2M10 14.8v2M3.2 10h2M14.8 10h2M5.2 5.2l1.4 1.4M13.4 13.4l1.4 1.4M14.8 5.2l-1.4 1.4M6.6 13.4l-1.4 1.4" />
    </Svg>
  );
}

export function PlusIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M10 4.5v11M4.5 10h11" />
    </Svg>
  );
}

export function MicIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="7.6" y="3.2" width="4.8" height="8" rx="2.4" />
      <path d="M5 9.6a5 5 0 0 0 10 0M10 14.6v2.2" />
    </Svg>
  );
}

/** Send (arrow up — the pill's primary action). */
export function SendIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M10 15.5v-11M5.5 9 10 4.5 14.5 9" />
    </Svg>
  );
}

/** Attachment (paperclip) — the composer attach affordance. */
export function PaperclipIcon({ size = 20 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

export function PersonIcon(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="10" cy="7" r="3" />
      <path d="M4.4 16.4c.9-2.9 3-4.3 5.6-4.3s4.7 1.4 5.6 4.3" />
    </Svg>
  );
}
