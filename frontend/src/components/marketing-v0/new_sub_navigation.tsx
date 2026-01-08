"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

const navItems = [
    { id: "overview", label: "Überblick" },
    { id: "funktionsweise", label: "Funktionsweise" },
    { id: "anwendungsfaelle", label: "Anwendungsfälle" },
    { id: "neutralitaet", label: "Neutralität" },
    { id: "hersteller", label: "Für Hersteller" },
];

export function SubNavigation() {
    const [activeTab, setActiveTab] = useState("overview");

    const scrollToSection = (id: string) => {
        const element = document.getElementById(id);
        if (element) {
            // Header (64px) + SubNav (approx 54px) = 118px offset
            const offset = 120;
            const bodyRect = document.body.getBoundingClientRect().top;
            const elementRect = element.getBoundingClientRect().top;
            const elementPosition = elementRect - bodyRect;
            const offsetPosition = elementPosition - offset;

            window.scrollTo({
                top: offsetPosition,
                behavior: "smooth",
            });
            setActiveTab(id);
        }
    };

    useEffect(() => {
        const observerOptions = {
            root: null,
            rootMargin: "-120px 0px -70% 0px",
            threshold: 0,
        };

        const observerCallback = (entries: IntersectionObserverEntry[]) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    setActiveTab(entry.target.id);
                }
            });
        };

        const observer = new IntersectionObserver(observerCallback, observerOptions);

        navItems.forEach((item) => {
            const element = document.getElementById(item.id);
            if (element) observer.observe(element);
        });

        return () => observer.disconnect();
    }, []);

    return (
        <div className="sticky top-[64px] z-30 bg-white border-b border-gray-200">
            <div className="max-w-[1600px] mx-auto px-6">
                <nav className="flex gap-10 overflow-x-auto no-scrollbar pl-[137px]" aria-label="Sekundäre Navigation">
                    {navItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => scrollToSection(item.id)}
                            className={cn(
                                "relative py-4 text-[13px] font-medium transition-all whitespace-nowrap",
                                activeTab === item.id
                                    ? "text-[#0078D4] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-[3px] after:bg-[#0078D4]"
                                    : "text-[#616161] hover:text-[#0078D4] after:absolute after:bottom-0 after:left-0 after:right-0 after:h-[3px] after:bg-[#0078D4] after:scale-x-0 hover:after:scale-x-100 after:transition-transform after:duration-300",
                            )}
                        >
                            {item.label}
                        </button>
                    ))}
                </nav>
            </div>
        </div>
    );
}
