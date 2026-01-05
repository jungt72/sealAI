"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { NavigationItem } from "@/lib/strapi";

type AerospaceNavProps = {
    items: NavigationItem[];
};

export default function AerospaceNav({ items }: AerospaceNavProps) {
    const [isScrolled, setIsScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 50);
        };

        window.addEventListener("scroll", handleScroll, { passive: true });
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    return (
        <header
            className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${isScrolled
                    ? "bg-white shadow-md"
                    : "bg-transparent"
                }`}
        >
            <nav className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="flex h-20 items-center justify-between">
                    {/* Logo */}
                    <Link
                        href="/"
                        className={`text-2xl font-bold tracking-tight transition-colors ${isScrolled ? "text-slate-900" : "text-white"
                            }`}
                    >
                        Aerospace Corp
                    </Link>

                    {/* Navigation Items */}
                    <ul className="hidden md:flex items-center gap-8">
                        {items.map((item) => (
                            <li key={item.id}>
                                <Link
                                    href={item.href}
                                    className={`text-sm font-medium transition-colors hover:opacity-70 ${isScrolled ? "text-slate-700" : "text-white"
                                        }`}
                                >
                                    {item.label}
                                </Link>
                            </li>
                        ))}
                    </ul>

                    {/* Mobile Menu Button */}
                    <button
                        type="button"
                        className={`md:hidden p-2 ${isScrolled ? "text-slate-900" : "text-white"
                            }`}
                        aria-label="Open menu"
                    >
                        <svg
                            className="h-6 w-6"
                            fill="none"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                </div>
            </nav>
        </header>
    );
}
