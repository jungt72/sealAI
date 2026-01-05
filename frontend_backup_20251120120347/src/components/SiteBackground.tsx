// src/components/SiteBackground.tsx
// Globaler Seitenhintergrund: sehr dunkles Blau + dezenter Starfield, fixiert
"use client";

import React from "react";
import Starfield from "./Starfield";

export default function SiteBackground() {
  return (
    <>
      {/* Tiefschwarz als Fallback */}
      <div className="pointer-events-none fixed inset-0 z-[-3] bg-black" />

      {/* Dunkelblauer Verlauf wie im Hero */}
      <div
        className="pointer-events-none fixed inset-0 z-[-2]
                   bg-gradient-to-b from-[#040815] via-[#0A1328] to-[#0B1020]"
        aria-hidden
      />

      {/* Dezenter Sternenhimmel über gesamte Seite */}
      <div className="pointer-events-none fixed inset-0 z-[-1] opacity-35">
        <Starfield />
      </div>
    </>
  );
}
