"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { products } from "@/data/marketing-v0/products";
import type { Product } from "@/types/marketing-v0/products";

function getTabFromLocation(defaultTab: string) {
    if (typeof window === "undefined") return defaultTab;
    const params = new URLSearchParams(window.location.search);
    return params.get("tab") || defaultTab;
}

// ... (imports remain the same)

function ProductTabButton({
    product,
    isActive,
    onClick,
}: {
    product: Product;
    isActive: boolean;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            aria-pressed={isActive}
            aria-label={`${product.name} ${isActive ? "ausgewählt" : ""}`}
            className={`rounded-full px-5 py-2.5 text-[15px] font-semibold transition-colors duration-200 ${isActive
                ? "bg-[#004E8C] text-white shadow-sm"
                : "bg-[#E1DFDD] text-[#323130] hover:bg-[#C8C6C4]"
                }`}
        >
            {product.name}
        </button>
    );
}

function AccordionItem({
    feature,
    index,
    isOpen,
    onToggle,
    totalItems,
}: {
    feature: { title: string; description: string; link: string };
    index: number;
    isOpen: boolean;
    onToggle: () => void;
    totalItems: number;
}) {
    return (
        <div className={`transition-all duration-300 ${isOpen ? "border-l-[4px] border-[#A4262C] bg-white pl-6 py-4 shadow-sm" : "border-l-[4px] border-transparent pl-6 py-4 hover:bg-gray-50"}`}>
            <button
                id={`accordion-header-${index}`}
                onClick={onToggle}
                aria-expanded={isOpen}
                aria-controls={`accordion-content-${index}`}
                className="w-full text-left bg-transparent focus:outline-none group"
            >
                <div className="flex justify-between items-start">
                    <h3 className={`text-lg leading-tight transition-colors ${isOpen ? "font-bold text-[#242424]" : "font-semibold text-[#323130] group-hover:text-black"}`}>
                        {feature.title}
                    </h3>
                    {isOpen ? (
                        <ChevronUp className="h-5 w-5 text-[#605E5C] flex-shrink-0 mt-0.5" aria-hidden="true" />
                    ) : (
                        <ChevronDown className="h-5 w-5 text-[#605E5C] flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
                    )}
                </div>
            </button>

            {isOpen && (
                <div id={`accordion-content-${index}`} className="mt-3 animate-in slide-in-from-top-1 duration-200">
                    <p className="text-[#323130] leading-relaxed mb-3 text-[15px]">{feature.description}</p>
                    <a
                        href="#"
                        className="text-[#0067B8] font-semibold text-[15px] hover:underline inline-flex items-center gap-1 focus:outline-none decoration-1 hover:decoration-2 underline-offset-2"
                    >
                        {feature.link}
                    </a>
                </div>
            )}
            {/* Divider only if not last item and current item is not open (optional, Microsoft often just uses spacing) - keeping it clean for now by removing explicit dividers inside the item, relying on spacing/border */}
        </div>
    );
}

export function ProductTabs() {
    // ... (logic remains the same)
    const router = useRouter();
    const pathname = usePathname();

    const DEFAULT_TAB = "parameters";
    const [activeTab, setActiveTab] = useState<string>(DEFAULT_TAB);

    const [openAccordion, setOpenAccordion] = useState(0);

    // Initial tab from URL (client only)
    useEffect(() => {
        // Mock implementation for example, real one needs standard hook usage
        if (typeof window !== "undefined") {
            const params = new URLSearchParams(window.location.search);
            const tab = params.get("tab") || DEFAULT_TAB;
            setActiveTab(tab);
            setOpenAccordion(0);
        }
    }, []);

    const activeProduct = useMemo(() => products.find((p) => p.id === activeTab), [activeTab]);

    const handleTabChange = useCallback(
        (productId: string) => {
            setActiveTab(productId);
            setOpenAccordion(0);

            if (typeof window !== "undefined") {
                const params = new URLSearchParams(window.location.search);
                params.set("tab", productId);
                router.push(`${pathname}?${params.toString()}`, { scroll: false });
            }
        },
        [router, pathname],
    );

    const handleAccordionToggle = useCallback((index: number) => {
        setOpenAccordion((prev) => (prev === index ? -1 : index));
    }, []);

    // ... (Keyboard navigation remains)

    if (!activeProduct) return null;

    return (
        <section id="funktionsweise" className="py-20 px-6 bg-white" aria-labelledby="products-heading">
            <div id="anwendungsfaelle" className="max-w-[1600px] mx-auto px-6">
                <div className="ml-[137px]">
                    <div className="mb-10">
                        <p className="text-xs font-semibold text-gray-500 mb-2 tracking-widest uppercase">PRODUKTE</p>
                        <h2 id="products-heading" className="text-3xl md:text-4xl lg:text-[2.5rem] font-semibold text-[#242424] leading-tight">
                            Intuitiveres Arbeiten mit sealAI – Sealing Intelligence
                        </h2>
                    </div>

                    <div className="flex flex-wrap gap-3 mb-14" role="tablist" aria-label="Produktauswahl">
                        {products.map((product) => (
                            <ProductTabButton
                                key={product.id}
                                product={product}
                                isActive={activeTab === product.id}
                                onClick={() => handleTabChange(product.id)}
                            />
                        ))}
                    </div>

                    <div className="grid lg:grid-cols-2 gap-8 lg:gap-16 items-start">
                        <div className="space-y-2" role="tabpanel" aria-label={activeProduct.name}>
                            {activeProduct.features.map((feature, index) => (
                                <AccordionItem
                                    key={index}
                                    feature={feature}
                                    index={index}
                                    isOpen={openAccordion === index}
                                    onToggle={() => handleAccordionToggle(index)}
                                    totalItems={activeProduct.features.length}
                                />
                            ))}
                        </div>

                        <div className="relative rounded-xl overflow-hidden bg-gradient-to-br from-[#E6F2EA] to-[#D3E9D9] p-8 lg:p-14 shadow-sm border border-[#D1E6D5]">
                            <Image
                                src={activeProduct.image || "/placeholder.svg"}
                                alt={`${activeProduct.name} Interface Preview`}
                                width={800}
                                height={600}
                                className="w-full h-auto rounded-md shadow-lg bg-white"
                                priority={activeTab === DEFAULT_TAB}
                                quality={95}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
