// frontend/src/components/HeroBackground.tsx

"use client";

import React from "react";

type HeroBackgroundProps = {
  imageUrl?: string | null;
};

/**
 * Hintergrund:
 * - Strapi-Bild als Cover (falls vorhanden)
 * - dunkle Overlays für Lesbarkeit
 */
export default function HeroBackground({ imageUrl }: HeroBackgroundProps) {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10">
      {/* Basishintergrund */}
      <div className="absolute inset-0 bg-slate-950" aria-hidden="true" />

      {/* Strapi-Hintergrundbild */}
      {imageUrl && (
        <div
          className="absolute inset-0 bg-cover bg-center opacity-70"
          style={{ backgroundImage: `url(${imageUrl})` }}
          aria-hidden="true"
        />
      )}

      {/* Overlay für Textlesbarkeit */}
      <div
        className="absolute inset-0 bg-gradient-to-b from-slate-950/70 via-slate-950/30 to-slate-950/90"
        aria-hidden="true"
      />
    </div>
  );
}
