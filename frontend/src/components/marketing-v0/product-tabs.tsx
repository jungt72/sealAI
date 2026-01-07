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
    <Button
      variant={isActive ? "default" : "secondary"}
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={`${product.name} ${isActive ? "ausgewählt" : ""}`}
      className={`rounded-full px-6 py-2 h-auto text-sm font-medium transition-all ${
        isActive
          ? "bg-blue-700 text-white hover:bg-blue-800"
          : "bg-blue-100 text-blue-900 hover:bg-blue-200"
      }`}
    >
      {product.name}
    </Button>
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
    <div className={`border-l-4 -ml-1 transition-all ${isOpen ? "border-red-600" : "border-transparent"}`}>
      <button
        id={`accordion-header-${index}`}
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={`accordion-content-${index}`}
        className="w-full text-left px-6 py-5 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset"
      >
        <div className="flex justify-between items-start gap-4">
          <h3 className="text-lg font-semibold text-gray-900 leading-tight pr-4">{feature.title}</h3>
          {isOpen ? (
            <ChevronUp className="h-5 w-5 text-gray-500 flex-shrink-0 mt-1" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-5 w-5 text-gray-500 flex-shrink-0 mt-1" aria-hidden="true" />
          )}
        </div>
      </button>

      {isOpen && (
        <div id={`accordion-content-${index}`} className="px-6 pb-6 animate-in slide-in-from-top-2 duration-200">
          <p className="text-gray-700 leading-relaxed mb-4">{feature.description}</p>
          <a
            href="#"
            className="text-blue-700 font-medium hover:underline inline-flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
          >
            {feature.link}
          </a>
        </div>
      )}

      {index < totalItems - 1 && <div className="border-b border-gray-200 ml-6" />}
    </div>
  );
}

export function ProductTabs() {
  const router = useRouter();
  const pathname = usePathname();

  const DEFAULT_TAB = "automate";
  const [activeTab, setActiveTab] = useState<string>(DEFAULT_TAB);
  const [openAccordion, setOpenAccordion] = useState(0);

  // Initial tab from URL (client only)
  useEffect(() => {
    const tab = getTabFromLocation(DEFAULT_TAB);
    setActiveTab(tab);
    setOpenAccordion(0);
  }, []);

  const activeProduct = useMemo(() => products.find((p) => p.id === activeTab), [activeTab]);

  const handleTabChange = useCallback(
    (productId: string) => {
      setActiveTab(productId);
      setOpenAccordion(0);

      // update URL query without full reload
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        params.set("tab", productId);
        router.push(`${pathname}?${params.toString()}`, { scroll: false });
      } else {
        router.push(pathname, { scroll: false });
      }
    },
    [router, pathname],
  );

  const handleAccordionToggle = useCallback((index: number) => {
    setOpenAccordion((prev) => (prev === index ? -1 : index));
  }, []);

  // Keyboard navigation left/right through tabs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;

      const currentIndex = products.findIndex((p) => p.id === activeTab);
      if (currentIndex < 0) return;

      let newIndex: number;
      if (e.key === "ArrowLeft") newIndex = currentIndex > 0 ? currentIndex - 1 : products.length - 1;
      else newIndex = currentIndex < products.length - 1 ? currentIndex + 1 : 0;

      const next = products[newIndex];
      if (next) handleTabChange(next.id);
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [activeTab, handleTabChange]);

  if (!activeProduct) return null;

  return (
    <section className="py-16 px-4 md:px-6 lg:px-8 bg-gray-50" aria-labelledby="products-heading">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <p className="text-xs font-semibold text-gray-600 mb-3 tracking-widest uppercase">Produkte</p>
          <h2 id="products-heading" className="text-3xl md:text-4xl lg:text-5xl font-semibold mb-8 text-gray-900">
            Intuitiveres Arbeiten mit sealAI - sealing intelligence
          </h2>
        </div>

        <div className="flex flex-wrap gap-3 mb-12" role="tablist" aria-label="Produktauswahl">
          {products.map((product) => (
            <ProductTabButton
              key={product.id}
              product={product}
              isActive={activeTab === product.id}
              onClick={() => handleTabChange(product.id)}
            />
          ))}
        </div>

        <div className="grid lg:grid-cols-2 gap-8 lg:gap-12 items-start">
          <div className="space-y-0 border-l-4 border-gray-200" role="tabpanel" aria-label={activeProduct.name}>
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

          <div className="relative rounded-3xl overflow-hidden bg-gradient-to-br from-teal-100 to-teal-200 p-8 lg:p-12">
            <Image
              src={activeProduct.image || "/placeholder.svg"}
              alt={`${activeProduct.name} Screenshot - zeigt die Benutzeroberfläche und Hauptfunktionen`}
              width={800}
              height={600}
              className="w-full h-auto rounded-lg shadow-2xl"
              priority={activeTab === DEFAULT_TAB}
              loading={activeTab === DEFAULT_TAB ? "eager" : "lazy"}
              quality={90}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
