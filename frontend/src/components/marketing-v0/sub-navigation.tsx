"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

const navItems = [
  { id: "overview", label: "Übersicht" },
  { id: "products", label: "Produkte" },
  { id: "news", label: "Ausgewählte Neuigkeiten" },
  { id: "next-steps", label: "Nächste Schritte" },
];

export function SubNavigation() {
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <div className="sticky top-[60px] z-30 bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 md:px-6 lg:px-8">
        <nav className="flex gap-8" aria-label="Sekundäre Navigation">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "relative py-4 text-sm font-medium transition-colors hover:text-gray-900",
                activeTab === item.id
                  ? "text-gray-900 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-blue-600"
                  : "text-gray-600",
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
