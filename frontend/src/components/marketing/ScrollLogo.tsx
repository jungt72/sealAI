"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

export function ScrollLogo({ tone = "dark" }: { tone?: "dark" | "light" }) {
  const [compact, setCompact] = useState(false);
  const compactColor = tone === "light" ? "text-white" : "text-[#002A5B]";
  const compactBar = tone === "light" ? "bg-white" : "bg-[#002A5B]";

  useEffect(() => {
    const update = () => setCompact(window.scrollY > 72);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  if (tone === "light") {
    return (
      <Link
        href="/"
        aria-label="sealingAI Startseite"
        className="absolute left-1/2 flex h-9 -translate-x-1/2 items-center justify-center"
      >
        <span className="text-[15px] font-semibold tracking-[0.34em] text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.28)] sm:text-[16px]">
          sealingAI
        </span>
      </Link>
    );
  }

  return (
    <Link
      href="/"
      aria-label="sealingAI Startseite"
      className="absolute left-1/2 flex h-9 w-[136px] -translate-x-1/2 items-center justify-center overflow-hidden"
    >
      <Image
        src="/images/logo/sealing-wordmark-new.png"
        alt="sealingAI"
        width={1500}
        height={300}
        priority
        sizes="136px"
        className={`h-auto w-[118px] object-contain transition-all duration-500 ease-out sm:w-[136px] ${
          compact ? "scale-75 opacity-0 blur-[2px]" : "scale-100 opacity-100 blur-0"
        }`}
      />
      <span
        aria-hidden="true"
        className={`absolute inset-0 flex items-center justify-center gap-1.5 text-[19px] font-black leading-none tracking-[0.08em] ${compactColor} transition-all duration-500 ease-out ${
          compact ? "scale-100 opacity-100 blur-0" : "scale-125 opacity-0 blur-[2px]"
        }`}
      >
        <span>S</span>
        <span className={`block h-5 w-[5px] skew-x-[18deg] ${compactBar}`} />
      </span>
    </Link>
  );
}
