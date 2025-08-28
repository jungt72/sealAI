// src/components/Starfield.tsx — subtiler Sternenhimmel (twinkle)
"use client";
import React, { useEffect, useRef } from "react";

type Star = { x: number; y: number; r: number; phase: number; speed: number };

export default function Starfield({ density = 240 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const stars: Star[] = [];
    let running = true;

    function resize() {
      const parent = c.parentElement!;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      c.width = Math.floor(parent.clientWidth * dpr);
      c.height = Math.floor(parent.clientHeight * dpr);
      c.style.width = "100%";
      c.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      stars.length = 0;
      const count = Math.floor((parent.clientWidth * parent.clientHeight) / 18000);
      for (let i = 0; i < Math.min(density, Math.max(80, count)); i++) {
        stars.push({
          x: Math.random() * parent.clientWidth,
          y: Math.random() * parent.clientHeight,
          r: Math.random() * 1.2 + 0.2,
          phase: Math.random() * Math.PI * 2,
          speed: 0.6 + Math.random() * 0.6,
        });
      }
    }

    function draw(t: number) {
      if (!running) return;
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.fillStyle = "#fff";
      for (const s of stars) {
        const a = 0.08 + Math.abs(Math.sin(s.phase + t * 0.001 * s.speed)) * 0.18;
        ctx.globalAlpha = a;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf.current = requestAnimationFrame(draw);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(c.parentElement!);
    raf.current = requestAnimationFrame(draw);

    return () => { running = false; if (raf.current) cancelAnimationFrame(raf.current); ro.disconnect(); };
  }, [density]);

  return <canvas ref={ref} className="absolute inset-0 w-full h-full" aria-hidden />;
}
