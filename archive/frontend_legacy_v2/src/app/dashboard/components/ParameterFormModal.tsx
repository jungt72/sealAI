"use client";

import React, { useEffect, useState } from "react";
import type { ContextState } from "@/types/context";

type ParameterFormModalProps = {
  open: boolean;
  onClose: () => void;
  contextState: ContextState;
  onSave: (next: Partial<ContextState>) => void;
};

export function ParameterFormModal({ open, onClose, contextState, onSave }: ParameterFormModalProps) {
  const [medium, setMedium] = useState(contextState.medium);
  const [temperature, setTemperature] = useState(contextState.temperature);
  const [pressure, setPressure] = useState(contextState.pressure);
  const [sealingType, setSealingType] = useState(contextState.sealingType);

  useEffect(() => {
    if (open) {
      setMedium(contextState.medium);
      setTemperature(contextState.temperature);
      setPressure(contextState.pressure);
      setSealingType(contextState.sealingType);
    }
  }, [open, contextState]);

  if (!open) return null;

  const handleSave = () => {
    onSave({ medium, temperature, pressure, sealingType });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 px-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="border-b border-slate-100 px-6 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-emerald-700">Parameter</div>
          <h3 className="text-xl font-bold text-slate-900">Technische Eingabe</h3>
          <p className="mt-1 text-sm text-slate-600">
            Trage die kritischen Dichtungsparameter ein – sie werden live in den Kontext übernommen.
          </p>
        </div>

        <div className="space-y-4 px-6 py-4">
          <LabeledInput label="Medium" value={medium} onChange={setMedium} placeholder="z.B. HLP 46 / Wasser / Gas" />
          <LabeledInput label="Temperatur" value={temperature} onChange={setTemperature} placeholder="z.B. 180°C" />
          <LabeledInput label="Druck" value={pressure} onChange={setPressure} placeholder="z.B. 120 bar" />
          <LabeledInput label="Dichtungstyp" value={sealingType} onChange={setSealingType} placeholder="z.B. Radialwellendichtung" />
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-md transition hover:bg-emerald-700"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (val: string) => void;
}) {
  return (
    <label className="block space-y-1">
      <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</div>
      <input
        className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 shadow-inner outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
