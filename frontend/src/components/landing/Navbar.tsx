"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Button from "@/components/ui/Button";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled
          ? "border-b border-white/[0.06] bg-seal-command/90 backdrop-blur-xl"
          : "bg-transparent"
      }`}
    >
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <span className="font-syne text-lg font-bold tracking-tight text-white">
          Seal<span className="text-seal-action">AI</span>
        </span>

        <div className="hidden items-center gap-8 sm:flex">
          <a
            href="#features"
            className="text-sm text-slate-400 transition hover:text-white"
          >
            Features
          </a>
          <span className="cursor-not-allowed text-sm text-slate-600">
            Dokumentation
          </span>
          <Link href="/dashboard/new">
            <Button variant="primary" size="sm">
              Dashboard öffnen
            </Button>
          </Link>
        </div>
      </nav>
    </header>
  );
}
