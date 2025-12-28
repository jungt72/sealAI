"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { Menu, Search } from "lucide-react";
import { NavbarData } from "@/lib/types";

interface NavbarProps {
    data: NavbarData;
}

export function Navbar({ data }: NavbarProps) {
    const [isVisible, setIsVisible] = useState(true);
    const [lastScrollY, setLastScrollY] = useState(0);

    useEffect(() => {
        const handleScroll = () => {
            const currentScrollY = window.scrollY;

            if (currentScrollY > 100) {
                setIsVisible(false);
            } else {
                setIsVisible(true);
            }

            setLastScrollY(currentScrollY);
        };

        window.addEventListener("scroll", handleScroll, { passive: true });
        return () => window.removeEventListener("scroll", handleScroll);
    }, [lastScrollY]);

    return (
        <header
            className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 bg-gradient-to-b from-black/50 to-transparent ${isVisible ? "translate-y-0" : "-translate-y-full"
                }`}
        >
            <div className="w-full max-w-[1600px] mx-auto h-20 flex items-center px-5">
                {/* Menu Button - Left */}
                <button
                    className="h-full flex items-center gap-3 pr-8 border-r-2 border-white/40 text-white hover:text-white/80 transition-colors"
                    onClick={() => { /* Toggle menu logic if needed, or just scroll to footer/open drawer */ }}
                >
                    <span className="text-sm font-medium tracking-wide uppercase hidden md:inline-block">Menu</span>
                    <Menu className="w-5 h-5" />
                </button>

                {/* Logo - Left Center */}
                <Link href="/" className="h-full flex items-center px-8">
                    {data.logo?.url && (
                        <Image
                            src={data.logo.url}
                            alt={data.logo.alternativeText || "Logo"}
                            width={45}
                            height={45}
                            className="w-[45px] h-[45px]"
                        />
                    )}
                    <span className="ml-3 text-2xl font-bold tracking-wider text-white">{data.brand_name}</span>
                </Link>

                {/* Spacer */}
                <div className="flex-grow" />

                {/* Nav Links - Right */}
                <nav className="hidden md:flex h-full items-center gap-1">
                    {data.items.map((item, index) => (
                        <Link
                            key={index}
                            href={item.href}
                            className="h-full flex items-center px-5 text-sm font-medium text-white hover:text-white/80 transition-colors"
                            target={item.isExternal ? "_blank" : undefined}
                            rel={item.isExternal ? "noopener noreferrer" : undefined}
                        >
                            {item.label}
                        </Link>
                    ))}
                    {/* Contact Link (formerly button) */}
                    <Link
                        href="/contact"
                        className="h-full flex items-center px-5 text-sm font-medium text-white hover:text-white/80 transition-colors"
                    >
                        Kontakt
                    </Link>
                </nav>

                {/* Search - Far Right */}
                {data.show_search && (
                    <button className="h-full flex items-center gap-3 pl-8 text-white hover:text-white/80 transition-colors ml-4">
                        <span className="text-sm font-medium tracking-wide uppercase hidden md:inline-block">Search</span>
                        <Search className="w-5 h-5" />
                    </button>
                )}

                {/* Login Button */}
                <Link
                    href="/auth/signin"
                    className="h-full flex items-center gap-3 pl-8 border-l-2 border-white/40 text-white hover:text-white/80 transition-colors ml-4"
                >
                    <span className="text-sm font-medium tracking-wide uppercase">Login</span>
                </Link>
            </div>
        </header>
    );
}
