"use client";

import { useState } from "react";
import Image from "next/image";
import { ChevronDown } from "lucide-react";
import { sectionY, shell } from "@/lib/layout";
import { ProductTabSection } from "@/lib/types";

interface ProductTabsProps {
    tabs: ProductTabSection[];
}

export function ProductTabs({ tabs }: ProductTabsProps) {
    const [activeTab, setActiveTab] = useState(0);
    const [openAccordion, setOpenAccordion] = useState<number>(0);

    const toggleAccordion = (index: number) => {
        setOpenAccordion(openAccordion === index ? -1 : index);
    };

    if (!tabs || tabs.length === 0) {
        return null;
    }

    return (
        <section className={`${sectionY} bg-gray-50`}>
            <div className={shell}>
                <div className="mb-10">
                    <p className="text-sm text-gray-600 uppercase tracking-[0.16em] mb-3">Produkte</p>
                    <h2 className="h2-b2b text-gray-900 leading-tight text-balance">
                        Intuitiveres Arbeiten mit Copilot in Power Platform
                    </h2>
                </div>

                <div className="mb-10 border-b border-gray-200 overflow-x-auto">
                    <div className="flex gap-2 min-w-max">
                        {tabs.map((tab, index) => (
                            <button
                                key={tab.id || index}
                                onClick={() => {
                                    setActiveTab(index);
                                    setOpenAccordion(0);
                                }}
                                className={`px-6 py-2 text-sm font-medium whitespace-nowrap transition-colors relative ${activeTab === index ? "text-white bg-primary rounded-t" : "text-gray-700 hover:text-primary"
                                    }`}
                            >
                                {tab.title}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                    <div className="space-y-4">
                        {tabs[activeTab].accordionItems.map((item, index) => (
                            <div key={item.id || index} className={`${openAccordion === index ? "border-l-4 border-primary" : "border-l-4 border-transparent"}`}>
                                <button
                                    onClick={() => toggleAccordion(index)}
                                    className="w-full text-left p-6 bg-white hover:bg-gray-50 transition-colors flex justify-between items-start gap-4 rounded-xl"
                                >
                                    <div className="flex-1">
                                        <h3 className="text-lg font-semibold text-gray-900 mb-1">
                                            {item.title}
                                        </h3>
                                        {openAccordion === index && (
                                            <div className="mt-4">
                                                <p className="body-lg-b2b text-gray-600">{item.description}</p>
                                                {item.link && (
                                                    <a
                                                        href={item.link}
                                                        className="inline-block mt-4 text-primary font-medium hover:underline"
                                                    >
                                                        Weitere Informationen
                                                    </a>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                    <ChevronDown
                                        className={`w-5 h-5 text-gray-400 transition-transform flex-shrink-0 ${openAccordion === index ? "rotate-180" : ""}`}
                                    />
                                </button>
                            </div>
                        ))}
                    </div>

                    <div className="relative h-96 lg:h-auto rounded-2xl overflow-hidden shadow-xl">
                        {tabs[activeTab].image && (
                            <Image
                                src={tabs[activeTab].image.url}
                                alt={tabs[activeTab].image.alternativeText || tabs[activeTab].title}
                                fill
                                className="object-cover"
                            />
                        )}
                    </div>
                </div>
            </div>
        </section>
    );
}

