// src/components/Fog.tsx — bottom-only clouds, stronger & slower, no edge seam
"use client";
import React, { useEffect, useRef } from "react";

export default function Fog() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d", { alpha: true })!;
    let running = true;

    // Tunables (sichtbarer Nebel)
    const BLUR_PX = 22;          // etwas weniger Weichzeichnung -> mehr Struktur
    const PAD = BLUR_PX * 4;     // Offscreen-Puffer gegen Randartefakte
    const TILE = 256;            // Größe der Rausch-Kachel

    // Kleine wiederholbare Rauschkachel (gaussian-ish, leicht kontrastiert)
    const noiseTile = document.createElement("canvas");
    noiseTile.width = TILE; noiseTile.height = TILE;
    {
      const nctx = noiseTile.getContext("2d")!;
      const img = nctx.createImageData(TILE, TILE);
      const d = img.data;
      for (let i = 0; i < d.length; i += 4) {
        // Summe zweier Zufälle -> Glockenkurve; danach leicht kontrastverstärkt
        let v = (Math.random() + Math.random()) * 127; // 0..254
        // Simple contrast curve around mid gray
        const c = 1.18; // Kontrastfaktor
        v = (v - 127) * c + 127;
        v = Math.max(0, Math.min(255, v));
        d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255;
      }
      nctx.putImageData(img, 0, 0);
    }

    // Großes Offscreen-Canvas (mit Rand)
    const frame = document.createElement("canvas");
    const fctx = frame.getContext("2d")!;

    function resize() {
      const parent = canvas.parentElement!;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(parent.clientWidth * dpr);
      canvas.height = Math.floor(parent.clientHeight * dpr);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      frame.width = parent.clientWidth + PAD * 2;
      frame.height = parent.clientHeight + PAD * 2;
    }

    function draw(time: number) {
      if (!running) return;
      const t = time * 0.001;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;

      // Offscreen mit zwei driftenden Schichten füllen
      fctx.clearRect(0, 0, frame.width, frame.height);
      const pat = fctx.createPattern(noiseTile, "repeat")!;

      // Layer A (breit)
      fctx.save();
      fctx.globalAlpha = 0.95;
      fctx.setTransform(1, 0, 0, 1, (-((t * 6) % TILE)) - PAD, Math.sin(t * 0.10) * 10 - PAD);
      fctx.fillStyle = pat;
      fctx.fillRect(0, 0, frame.width + PAD * 2, frame.height + PAD * 2);
      fctx.restore();

      // Layer B (gegengesetzt, etwas schneller)
      fctx.save();
      fctx.globalAlpha = 0.75;
      fctx.setTransform(1, 0, 0, 1, (-((t * -9) % TILE)) - PAD, Math.cos(t * 0.08) * 12 - PAD);
      fctx.fillStyle = pat;
      fctx.fillRect(0, 0, frame.width + PAD * 2, frame.height + PAD * 2);
      fctx.restore();

      // Haupt-Render: weichzeichnen + kräftiger Alpha
      ctx.clearRect(0, 0, w, h);
      ctx.save();
      ctx.filter = `blur(${BLUR_PX}px)`;
      ctx.globalAlpha = 0.50; // vorher ~0.32
      ctx.drawImage(frame, -PAD, -PAD, frame.width, frame.height, 0, 0, w, h);
      ctx.restore();

      // Zweite Tiefen-Schicht (minimal skaliert) für volumen
      ctx.save();
      ctx.filter = `blur(${Math.round(BLUR_PX * 1.2)}px)`;
      ctx.globalAlpha = 0.25;
      ctx.drawImage(frame, -PAD - 12, -PAD - 8, frame.width + 24, frame.height + 16, 0, 0, w, h);
      ctx.restore();

      // Blaue Bodentönung etwas kräftiger
      const tint = ctx.createLinearGradient(0, h * 0.45, 0, h);
      tint.addColorStop(0.0, "rgba(0,0,0,0)");
      tint.addColorStop(1.0, "rgba(99,102,241,0.22)");
      ctx.fillStyle = tint;
      ctx.fillRect(0, 0, w, h);

      // Maske: weiter oben sichtbar machen
      const mask = ctx.createLinearGradient(0, 0, 0, h);
      mask.addColorStop(0.00, "rgba(0,0,0,0)");
      mask.addColorStop(0.45, "rgba(0,0,0,0.25)");
      mask.addColorStop(0.65, "rgba(0,0,0,0.75)");
      mask.addColorStop(1.00, "rgba(0,0,0,1)");
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = mask;
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";

      rafRef.current = requestAnimationFrame(draw);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas.parentElement!);
    rafRef.current = requestAnimationFrame(draw);

    return () => {
      running = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, []);

  // etwas höhere Nebelhöhe, damit er deutlicher sichtbar ist
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[48svh] md:h-[46svh] lg:h-[44svh]">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}
