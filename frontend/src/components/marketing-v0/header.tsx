"use client";

import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/Button";

export function Header() {
    return (
        <header className="fixed top-0 left-0 right-0 bg-white border-b border-gray-200 z-50">
            <div className="max-w-[1600px] mx-auto px-6">
                <div className="relative flex items-center h-[64px]">
                    {/* Brand Area (Left) */}
                    <div className="flex items-center">
                        {/* Logo + Brand Name - Natural width + Right Padding */}
                        <Link href="/" className="flex items-center gap-4 pr-6 shrink-0">
                            <Image
                                src="/images/logo-sealai-schwebend-removebg-preview.png"
                                alt="sealAI Logo"
                                width={48}
                                height={48}
                                className="w-[48px] h-[48px] object-contain"
                                priority
                            />
                            <span className="text-[18px] font-semibold text-[#262626] tracking-tight whitespace-nowrap">sealAI</span>
                        </Link>

                        {/* Vertical Divider - Symmetric Spacing Anchor */}
                        <div className="h-6 w-[1.5px] bg-[#262626] opacity-30" aria-hidden="true" />

                        {/* Application Name - Left Padding matches Logo Link's Right Padding */}
                        <span className="text-[18px] font-semibold text-[#262626] pl-6 tracking-tight shrink-0">
                            Sealing Intelligence
                        </span>
                    </div>

                    {/* Centered Navigation */}
                    <nav className="absolute left-1/2 -translate-x-1/2 hidden xl:flex items-center gap-8" aria-label="Hauptnavigation">
                        <Link
                            href="#"
                            className="text-[13px] text-[#262626] hover:underline underline-offset-[22px] decoration-[2px] font-normal transition-all"
                        >
                            Lösung
                        </Link>
                        <Link
                            href="#"
                            className="text-[13px] text-[#262626] hover:underline underline-offset-[22px] decoration-[2px] font-normal transition-all"
                        >
                            Funktionsweise
                        </Link>
                        <Link
                            href="#"
                            className="text-[13px] text-[#262626] hover:underline underline-offset-[22px] decoration-[2px] font-normal transition-all"
                        >
                            Anwendungsfälle
                        </Link>
                        <Link
                            href="#"
                            className="text-[13px] text-[#262626] hover:underline underline-offset-[22px] decoration-[2px] font-normal transition-all"
                        >
                            Für Hersteller
                        </Link>
                        <Link
                            href="#"
                            className="text-[13px] text-[#262626] hover:underline underline-offset-[22px] decoration-[2px] font-normal transition-all"
                        >
                            Ressourcen
                        </Link>
                    </nav>

                    {/* Action Area (Right) */}
                    <div className="ml-auto flex items-center">
                        <Button
                            className="text-[13px] font-medium px-4 h-[30px] rounded-full shadow-sm transition-all flex items-center justify-center transform hover:scale-[1.02]"
                            style={{ backgroundColor: '#0071e3', color: 'white', border: 'none' }}
                        >
                            Loslegen
                        </Button>
                    </div>
                </div>
            </div>
        </header>
    );
}
