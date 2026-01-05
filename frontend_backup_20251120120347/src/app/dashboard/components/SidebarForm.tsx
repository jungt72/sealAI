"use client";

import React, { useState } from "react";

type RadialSealFormState = {
  application: string;
  medium: string;
  temperatureMin: string;
  temperatureMax: string;
  speedRpm: string;
  pressureInner: string;
  pressureOuter: string;
  shaftDiameter: string;
  housingDiameter: string;
  notes: string;
};

const initialState: RadialSealFormState = {
  application: "",
  medium: "",
  temperatureMin: "",
  temperatureMax: "",
  speedRpm: "",
  pressureInner: "",
  pressureOuter: "",
  shaftDiameter: "",
  housingDiameter: "",
  notes: "",
};

export default function SidebarForm() {
  const [form, setForm] = useState<RadialSealFormState>(initialState);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleReset = () => {
    setForm(initialState);
  };

  const handleUseInChat = () => {
    // Aktuell nur Copy-Hilfe für dich.
    // Später kannst du hier einen Callback zum Chat einbauen.
    const prompt = [
      "Ich suche eine Radialwellendichtung aus PTFE auf Basis folgender Daten:",
      form.application && `• Anwendung: ${form.application}`,
      form.medium && `• Medium: ${form.medium}`,
      (form.temperatureMin || form.temperatureMax) &&
        `• Temperatur: ${form.temperatureMin || "?"} … ${
          form.temperatureMax || "?"
        } °C`,
      form.speedRpm && `• Drehzahl: ${form.speedRpm} rpm`,
      (form.pressureInner || form.pressureOuter) &&
        `• Drücke: innen ${form.pressureInner || "?"} bar, außen ${
          form.pressureOuter || "?"
        } bar`,
      (form.shaftDiameter || form.housingDiameter) &&
        `• Geometrie: Welle ${form.shaftDiameter || "?"} mm, Gehäuse ${
          form.housingDiameter || "?"
        } mm`,
      form.notes && `• Hinweise: ${form.notes}`,
      "",
      "Welches Dichtungsmaterial (PTFE-Variante) und welches Profil empfiehlst du und warum?",
    ]
      .filter(Boolean)
      .join("\n");

    void navigator.clipboard?.writeText(prompt);
    // Kleine visuelle Bestätigung könntest du später ergänzen.
    // Für jetzt reicht Copy to Clipboard.
    // eslint-disable-next-line no-console
    console.log("Prompt in Zwischenablage:", prompt);
  };

  return (
    <form
      className="flex flex-col gap-3 text-xs text-gray-800"
      onSubmit={(e) => e.preventDefault()}
    >
      <div>
        <h2 className="text-sm font-semibold text-gray-800">
          Parameter für PTFE-Radialwellendichtung
        </h2>
        <p className="mt-1 text-[11px] text-gray-500">
          Fülle einige Eckdaten aus – du kannst sie später per Klick in den
          Chat übernehmen.
        </p>
      </div>

      <div className="space-y-2">
        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-gray-600">
            Anwendung / Maschine
          </span>
          <input
            type="text"
            name="application"
            value={form.application}
            onChange={handleChange}
            className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="z. B. Pumpenwelle, Getriebeabtrieb …"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-gray-600">
            Medium (Öl / Gas / andere)
          </span>
          <input
            type="text"
            name="medium"
            value={form.medium}
            onChange={handleChange}
            className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="z. B. Mineralöl ISO VG 68"
          />
        </label>

        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Tmin [°C]
            </span>
            <input
              type="number"
              name="temperatureMin"
              value={form.temperatureMin}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Tmax [°C]
            </span>
            <input
              type="number"
              name="temperatureMax"
              value={form.temperatureMax}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-gray-600">
            Drehzahl [rpm]
          </span>
          <input
            type="number"
            name="speedRpm"
            value={form.speedRpm}
            onChange={handleChange}
            className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </label>

        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Innendruck [bar]
            </span>
            <input
              type="number"
              name="pressureInner"
              value={form.pressureInner}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Außendruck [bar]
            </span>
            <input
              type="number"
              name="pressureOuter"
              value={form.pressureOuter}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Wellen-Ø [mm]
            </span>
            <input
              type="number"
              name="shaftDiameter"
              value={form.shaftDiameter}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-gray-600">
              Gehäuse-Ø [mm]
            </span>
            <input
              type="number"
              name="housingDiameter"
              value={form.housingDiameter}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-gray-600">
            Hinweise / Besonderheiten
          </span>
          <textarea
            name="notes"
            value={form.notes}
            onChange={handleChange}
            rows={3}
            className="w-full rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            placeholder="z. B. Schmutz, Vibration, begrenzter Einbauraum, FDA, ATEX …"
          />
        </label>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleUseInChat}
          className="rounded-full bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-white shadow-sm hover:bg-emerald-700"
        >
          Parameter als Chat-Frage kopieren
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-[11px] font-medium text-gray-600 hover:bg-gray-50"
        >
          Zurücksetzen
        </button>
      </div>

      <p className="mt-1 text-[10px] text-gray-400">
        Tipp: Nach dem Kopieren einfach im mittigen Chat-Feld einfügen – der
        Berater erkennt dann, dass du auf einen PTFE-Radialwellendichtring
        abzielst.
      </p>
    </form>
  );
}
