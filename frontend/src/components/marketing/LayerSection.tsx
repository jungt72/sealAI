"use client";

/**
 * sealingAI layer section — a native layer narrative (NOT a copy of any third
 * party). Left: a vertical step rail of the six layers. Right: a calm technical
 * preview of the active layer. Stacks to horizontal pills + preview on mobile.
 */

import { useState } from "react";
import { Check } from "lucide-react";

import { layerSection } from "@/lib/marketing/homeContent";

export function LayerSection() {
  const [active, setActive] = useState(0);
  const layers = layerSection.layers;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-10">
      {/* Rail — vertical on desktop, horizontally scrollable pills on mobile */}
      <ol className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1.5 lg:overflow-visible lg:pb-0">
        {layers.map((layer, index) => {
          const isActive = index === active;
          return (
            <li key={layer.name} className="shrink-0 lg:shrink">
              <button
                type="button"
                onClick={() => setActive(index)}
                aria-current={isActive ? "true" : undefined}
                className={`flex w-full items-center gap-3 rounded-full border px-4 py-2.5 text-left text-[13px] font-medium transition lg:rounded-[14px] ${
                  isActive
                    ? "border-seal-blue/25 bg-seal-light-blue text-seal-blue"
                    : "border-border bg-white text-muted-foreground hover:border-seal-blue/30"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                    isActive ? "bg-seal-blue text-white" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {index + 1}
                </span>
                <span className="whitespace-nowrap lg:whitespace-normal">{layer.name}</span>
              </button>
            </li>
          );
        })}
      </ol>

      {/* Preview card for the active layer */}
      <div className="rounded-xl border border-border bg-white p-6 sm:p-8">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Schicht {active + 1} / {layers.length}
        </span>
        <h3 className="mt-2 text-[22px] font-medium leading-tight text-foreground">{layers[active].name}</h3>
        <p className="mt-3 text-[14px] leading-7 text-muted-foreground">{layers[active].text}</p>
        <ul className="mt-6 grid gap-2 border-t border-border pt-5">
          {layers.map((layer, index) => (
            <li
              key={layer.name}
              className={`flex items-center gap-2 text-[12px] ${
                index <= active ? "text-foreground" : "text-muted-foreground/60"
              }`}
            >
              <span
                className={`flex h-4 w-4 items-center justify-center rounded-full ${
                  index <= active ? "bg-seal-blue text-white" : "bg-muted text-transparent"
                }`}
              >
                <Check size={10} aria-hidden />
              </span>
              {layer.name}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
