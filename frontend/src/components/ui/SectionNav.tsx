"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { shell } from "@/lib/layout";
import { Link } from "@/lib/types";

interface SectionNavProps {
    sections: Link[];
}

export function SectionNav({ sections }: SectionNavProps) {
    const [activeSection, setActiveSection] = useState<string>("");

    useEffect(() => {
        const handleScroll = () => {
            const scrollPosition = window.scrollY + 200;

            for (const section of sections) {
                // Extract ID from href (e.g., "#products" -> "products")
                const sectionId = section.href.replace('#', '');
                const element = document.getElementById(sectionId);
                if (element) {
                    const { offsetTop, offsetHeight } = element;
                    if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
                        setActiveSection(sectionId);
                        break;
                    }
                }
            }
        };

        window.addEventListener("scroll", handleScroll);
        handleScroll();
        return () => window.removeEventListener("scroll", handleScroll);
    }, [sections]);

    const scrollToSection = (href: string) => {
        const sectionId = href.replace('#', '');
        const element = document.getElementById(sectionId);
        if (element) {
            const offset = 80;
            const elementPosition = element.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - offset;

            window.scrollTo({
                top: offsetPosition,
                behavior: "smooth",
            });
        }
    };

    return (
        <nav className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-gray-200 shadow-sm">
            <div className={shell}>
                <div className="flex items-center gap-2 overflow-x-auto">
                    {sections.map((section, index) => {
                        const sectionId = section.href.replace('#', '');
                        return (
                            <button
                                key={section.id}
                                onClick={() => scrollToSection(section.href)}
                                className={`
                  relative px-6 py-4 text-sm font-medium whitespace-nowrap transition-colors cursor-pointer flex items-center gap-2
                  ${activeSection === sectionId ? "text-primary" : "text-gray-600 hover:text-primary"}
                `}
                            >
                                {index === 0 && (
                                    <Image
                                        src="/logo_blue_v2.png"
                                        alt="SealAI"
                                        width={24}
                                        height={24}
                                        className="w-6 h-6"
                                    />
                                )}
                                {section.label}
                                {activeSection === sectionId && (
                                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>
        </nav>
    );
}

