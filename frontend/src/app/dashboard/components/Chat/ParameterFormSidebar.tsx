"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Check, X } from "lucide-react";
import type { SealParameters } from "@/lib/types/sealParameters";

interface ParameterFormSidebarProps {
  show: boolean;
  parameters: SealParameters;
  dirtyKeys: Set<keyof SealParameters>;
  appliedMap: Partial<Record<keyof SealParameters, number>>;
  onUpdate: (name: keyof SealParameters, value: string | number) => void;
  onSubmit: () => void;
  onClose: () => void;
}

interface FormField {
  name: keyof SealParameters;
  label: string;
  type?: "text" | "number";
  placeholder?: string;
  options?: { value: string; label: string }[];
}

interface FormSection {
  title: string;
  fields: FormField[];
}

const FORM_SECTIONS: FormSection[] = [
  {
    title: "Welle",
    fields: [
      { name: "shaft_diameter", label: "Wellen-Ø (d1)", type: "number", placeholder: "z.B. 50" },
      { name: "nominal_diameter", label: "Bohrungs-Ø (nominal)", type: "number", placeholder: "z.B. 65.0" },
      { name: "tolerance", label: "Toleranz (mm)", type: "number", placeholder: "z.B. 0.002" },
      { name: "hardness", label: "Härte", type: "text", placeholder: "z.B. 55 HRC" },
      { name: "surface", label: "Werkstoff", type: "text", placeholder: "z.B. 42CrMo4" },
      { name: "roughness_ra", label: "Ra (µm)", type: "number", placeholder: "0.2" },
      { name: "lead", label: "Drall", type: "text", placeholder: "z.B. frei" },
      { name: "lead_pitch", label: "Drall-Tiefe / Steigung", type: "text", placeholder: "z.B. 0.04 mm" },
      { name: "runout", label: "Rundlauf (mm)", type: "number", placeholder: "z.B. 0.03 mm" },
      { name: "eccentricity", label: "Exzentrizität", type: "text", placeholder: "z.B. 0.1 mm" },
    ],
  },
  {
    title: "Gehäuse",
    fields: [
      { name: "housing_diameter", label: "Gehäuse-Ø (D)", type: "number", placeholder: "z.B. 70" },
      { name: "bore_diameter", label: "Bohrungs-Ø (tats.)", type: "number", placeholder: "z.B. 65.0" },
      { name: "housing_tolerance", label: "Toleranz (mm)", type: "number", placeholder: "z.B. 0.03" },
      { name: "housing_surface", label: "Oberfläche", type: "text", placeholder: "z.B. Ra 1.6" },
      { name: "housing_material", label: "Material", type: "text", placeholder: "z.B. Stahl / Alu" },
      { name: "axial_plate_axial", label: "Axialer Platz (mm)", type: "number", placeholder: "z.B. 8" },
    ],
  },
  {
    title: "Betriebsbedingungen",
    fields: [
      { name: "pressure_bar", label: "Betriebsdruck (bar)", type: "number", placeholder: "z.B. 0.5" },
      { name: "pressure_min", label: "Min. Druck", type: "number", placeholder: "0" },
      { name: "pressure_max", label: "Max. Druck", type: "number", placeholder: "1.0" },
      { name: "temperature_C", label: "Betriebstemperatur (°C)", type: "number", placeholder: "80" },
      { name: "temp_min", label: "Min. Temp", type: "number", placeholder: "-15" },
      { name: "temp_max", label: "Max. Temp", type: "number", placeholder: "120" },
      { name: "medium", label: "Medium", type: "text", placeholder: "z.B. Öl / Luft" },
      { name: "speed_rpm", label: "Drehzahl (rpm)", type: "number", placeholder: "1500" },
      { name: "speed_linear", label: "Geschw. (m/s)", type: "number", placeholder: "z.B. 5" },
      { name: "dynamic_runout", label: "Wellenschlag (dyn)", type: "number", placeholder: "z.B. 0.05" },
      { name: "mounting_offset", label: "Montageversatz", type: "number", placeholder: "z.B. 0.1" },
    ],
  },
  {
    title: "Sonstiges",
    fields: [
      { name: "contamination", label: "Verschmutzung", type: "text", placeholder: "z.B. Staub / Schlamm" },
      { name: "lifespan", label: "Lebensdauer (h)", type: "text", placeholder: "z.B. 5000" },
      { name: "application_type", label: "Anwendungstyp", type: "text", placeholder: "z.B. Motor / Pumpe" },
      {
        name: "food_grade",
        label: "Konformität",
        options: [
          { value: "", label: "Standard" },
          { value: "fda", label: "FDA-konform" },
          { value: "ec1935", label: "EU 1935/2004" },
        ],
      },
    ],
  },
];

export default function ParameterFormSidebar({
  show,
  parameters,
  dirtyKeys,
  appliedMap,
  onUpdate,
  onSubmit,
  onClose,
}: ParameterFormSidebarProps) {
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const paramSyncDebug = process.env.NEXT_PUBLIC_PARAM_SYNC_DEBUG === "1";
  const dirtyCount = dirtyKeys.size;

  useEffect(() => {
    if (!show || !paramSyncDebug) return;
    const keys = Object.keys(parameters || {});
    const pressureValue = parameters?.pressure_bar;
    const displayPressure =
      pressureValue !== undefined && pressureValue !== null ? String(pressureValue) : "";
    console.log("[param-sync] sidebar_render", {
      keys: keys.slice(0, 8),
      keys_count: keys.length,
      pressure_bar: displayPressure,
    });
  }, [parameters, paramSyncDebug, show]);

  if (!show) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  const toggleSection = (title: string) => {
    const next = new Set(collapsedSections);
    if (next.has(title)) next.delete(title);
    else next.add(title);
    setCollapsedSections(next);
  };

  const handleFieldChange = (name: keyof SealParameters, rawValue: string) => {
    onUpdate(name, rawValue);
  };

  return (
    <div className="parameter-form-sidebar">
      <div className="sidebar-header">
        <h3>Technische Parameter</h3>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-2 hover:bg-white/10 transition"
          aria-label="Schließen"
          title="Schließen"
        >
          <X className="w-4 h-4 text-white/70" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="sidebar-form">
        {FORM_SECTIONS.map((section) => {
          const isCollapsed = collapsedSections.has(section.title);
          return (
            <div
              className="form-section bg-[#1E1E2D] rounded-lg border border-white/10 overflow-hidden"
              key={section.title}
            >
              <button
                type="button"
                onClick={() => toggleSection(section.title)}
                className="w-full flex items-center justify-between p-3 bg-white/5 hover:bg-white/10 transition-colors text-left"
              >
                <span className="text-sm font-semibold text-white/90 uppercase tracking-wider">
                  {section.title}
                </span>
                {isCollapsed ? (
                  <ChevronDown className="w-4 h-4 text-white/60" />
                ) : (
                  <ChevronUp className="w-4 h-4 text-white/60" />
                )}
              </button>

              {!isCollapsed && (
                <div className="p-3 grid grid-cols-2 gap-3 animate-in slide-in-from-top-2 duration-200">
                  {section.fields.map((field) => {
                    const inputId = `param-${String(field.name)}`;
                    const fieldValue = parameters[field.name];
                    const displayValue =
                      fieldValue !== undefined && fieldValue !== null ? String(fieldValue) : "";
                    const isDirty = dirtyKeys.has(field.name);
                    const isApplied = Boolean(appliedMap?.[field.name]) && !isDirty;

                    return (
                      <div className="form-group flex flex-col gap-1.5" key={inputId}>
                        <label
                          htmlFor={inputId}
                          className="text-xs text-white/70 font-medium truncate flex items-center gap-1.5"
                          title={field.label}
                        >
                          <span className="truncate">{field.label}</span>
                          {isDirty ? (
                            <span
                              className="inline-block h-2 w-2 rounded-full bg-amber-400"
                              title="Änderung noch nicht übernommen"
                              aria-label="Änderung noch nicht übernommen"
                            />
                          ) : isApplied ? (
                            <Check
                              className="h-3 w-3 text-emerald-400"
                              title="Übernommen"
                              aria-label="Übernommen"
                            />
                          ) : null}
                        </label>

                        {field.options && field.options.length ? (
                          <select
                            id={inputId}
                            value={displayValue as string}
                            onChange={(e) => onUpdate(field.name, e.target.value)}
                            className="h-9 w-full rounded bg-white/5 border border-white/10 px-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all placeholder:text-white/20"
                          >
                            <option value="" className="bg-[#1E1E2D]">
                              Bitte wählen...
                            </option>
                            {field.options.map((option) => (
                              <option
                                key={option.value}
                                value={option.value}
                                className="bg-[#1E1E2D]"
                              >
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            id={inputId}
                            type="text"
                            inputMode={field.type === "number" ? "decimal" : "text"}
                            value={displayValue}
                            onChange={(e) => handleFieldChange(field.name, e.target.value)}
                            placeholder={field.placeholder}
                            className="h-9 w-full rounded bg-white/5 border border-white/10 px-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all placeholder:text-white/20"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        <div className="pt-2 sticky bottom-0 bg-[#14141e] pb-0 -mx-2 px-2 z-10">
          <button
            type="submit"
            disabled={dirtyCount === 0}
            className={[
              "w-full flex items-center justify-center gap-2 font-medium py-3 rounded-lg shadow-lg transition-all active:scale-[0.98]",
              dirtyCount === 0
                ? "bg-indigo-500/40 text-white/60 cursor-not-allowed shadow-none"
                : "bg-indigo-600 hover:bg-indigo-700 text-white hover:shadow-indigo-500/25",
            ].join(" ")}
            title={dirtyCount === 0 ? "Keine Änderungen" : "Parameter übernehmen"}
          >
            <Check className="w-4 h-4" />
            Parameter übernehmen
          </button>
        </div>
      </form>

      <style jsx>{`
        .parameter-form-sidebar {
          width: 500px;
          height: 100%;
          background: #14141e;
          border-left: 1px solid rgba(255, 255, 255, 0.08);
          padding: 1.5rem;
          overflow-y: auto;
          flex-shrink: 0;
          display: flex;
          flex-direction: column;
        }

        .sidebar-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
          padding-bottom: 1rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          flex-shrink: 0;
        }

        .sidebar-header h3 {
          color: #fff;
          font-size: 1.125rem;
          font-weight: 600;
          margin: 0;
        }

        .sidebar-form {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          padding-bottom: 2rem;
        }

        .parameter-form-sidebar::-webkit-scrollbar {
          width: 6px;
        }
        .parameter-form-sidebar::-webkit-scrollbar-track {
          background: transparent;
        }
        .parameter-form-sidebar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
        }
        .parameter-form-sidebar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
        }
      `}</style>
    </div>
  );
}
