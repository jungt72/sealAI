"use client";

import React, { useEffect, useMemo, useState } from "react";
import { isSidebarFormField } from "@/lib/sidebarParameterMap";

const applicationOptions = [
  "Getriebe",
  "Pumpe",
  "Motor",
  "Achse/Rad",
  "Allgemeine Maschine",
  "Sonstiges",
] as const;
const mediumOptions = [
  "Mineralöl",
  "Synthetisches Öl",
  "Fett",
  "Wasser / wässrige Lösung",
  "Emulsion",
  "Gas/Luft",
  "Sonstiges",
] as const;
const pressureOptions = [
  {
    value: "nahezu-drucklos",
    label: "nahezu drucklos (z. B. Ölbad, Tank, entlüftetes Getriebe)",
  },
  { value: "leicht-uber", label: "leicht überdruckt (bis ca. 0,5 bar)" },
  { value: "uberdruck", label: "Überdruck (0,5–2 bar)" },
  { value: "hochdruck", label: "Hochdruck (>2 bar)" },
] as const;
const dirtOptions = [
  "saubere Umgebung (Innenraum, Schaltschrank)",
  "leicht staubig (Werkstatt, Produktionshalle)",
  "stark staubig / Schmutz / Spritzwasser",
  "Schlamm / Hochdruckreinigung / Außen im Gelände",
] as const;
const lifetimeOptions = [
  "normale Lebensdauer der Maschine",
  "mehrere Jahre im Dauerbetrieb",
  "nur gelegentlicher Betrieb",
  "kurze Einsatzzeiten / Prüfstand",
] as const;
const specialRequirementOptions = [
  "lebensmitteltauglich",
  "beständig gegen aggressive Chemikalien",
  "sehr hohe Temperaturbeständigkeit",
  "keine besonderen Anforderungen",
] as const;
const shaftMaterialOptions = ["C-Stahl", "gehärteter Stahl", "Edelstahl", "sonstiges"] as const;
const hardnessOptions = ["< 45 HRC", "45–55 HRC", "> 55 HRC"] as const;
const orientationOptions = ["Welle horizontal", "Welle vertikal"] as const;
const oilLevelOptions = ["Dichtung über dem Ölspiegel", "Dichtung im Ölbad", "unsicher"] as const;
const rotationOptions = ["rechtsdrehend", "linksdrehend", "wechselnd / unbekannt"] as const;
const mediumSideOptions = [
  "auf der Innenseite der Dichtung",
  "auf der Außenseite der Dichtung",
] as const;

type OptionOrEmpty<T extends readonly string[]> = T[number] | "";

type RadialSealFormState = {
  applicationType: OptionOrEmpty<typeof applicationOptions>;
  applicationOther: string;
  mediumType: OptionOrEmpty<typeof mediumOptions>;
  mediumDetails: string;
  temperatureMin: string;
  temperatureMax: string;
  speedMaxRpm: string;
  pressureCategory: (typeof pressureOptions)[number]["value"] | "";
  maxPressure: string;
  dirtLevel: (typeof dirtOptions)[number] | "";
  lifetimeRequirement: (typeof lifetimeOptions)[number] | "";
  specialRequirements: (typeof specialRequirementOptions)[number][];
  shaftDiameter: string;
  housingDiameter: string;
  axialSpace: string;
  shaftMaterial: (typeof shaftMaterialOptions)[number] | "";
  shaftHardnessCategory: (typeof hardnessOptions)[number] | "";
  mountOrientation: (typeof orientationOptions)[number] | "";
  oilLevelRelativeToSeal: (typeof oilLevelOptions)[number] | "";
  rotationDirection: (typeof rotationOptions)[number] | "";
  mediumSide: (typeof mediumSideOptions)[number] | "";
  norms: string;
};

const initialState: RadialSealFormState = {
  applicationType: "",
  applicationOther: "",
  mediumType: "",
  mediumDetails: "",
  temperatureMin: "",
  temperatureMax: "",
  speedMaxRpm: "",
  pressureCategory: "",
  maxPressure: "",
  dirtLevel: "",
  lifetimeRequirement: "",
  specialRequirements: ["keine besonderen Anforderungen"],
  shaftDiameter: "",
  housingDiameter: "",
  axialSpace: "",
  shaftMaterial: "",
  shaftHardnessCategory: "",
  mountOrientation: "",
  oilLevelRelativeToSeal: "",
  rotationDirection: "",
  mediumSide: "",
  norms: "",
};

const PreliminaryRecommendation = () => (
  <div className="rounded-2xl border border-gray-200 bg-white/60 p-4 shadow-sm">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
      Vorläufige Empfehlung
    </p>
    <p className="mt-1 text-sm font-semibold text-gray-800">
      Basierend auf den eingegebenen Basisdaten
    </p>
    <p className="mt-2 text-[11px] text-gray-500">
      Nach Klick auf „Auslegung anfragen“ könnten hier Vorschläge für Elastomer
      & Profil folgen.
    </p>
  </div>
);

export default function SidebarForm() {
  const [form, setForm] = useState<RadialSealFormState>(initialState);
  const [showTechnical, setShowTechnical] = useState(false);
const [submitAttempted, setSubmitAttempted] = useState(false);

  useEffect(() => {
    const handleFormPatch = (event: Event) => {
      const detail = (event as CustomEvent)?.detail;
      const params = detail?.params;
      if (!params || typeof params !== "object") return;
      setForm((prev) => {
        let changed = false;
        const next = { ...prev };
        for (const [key, value] of Object.entries(params)) {
          if (!isSidebarFormField(key)) continue;
          const fieldKey = key as keyof RadialSealFormState;
          const formatted = value == null ? "" : String(value);
          const existing = String(((next as any)[fieldKey] ?? ""));
          if (existing === formatted) continue;
          (next as any)[fieldKey] = formatted;
          changed = true;
        }
        return changed ? next : prev;
      });
    };

    window.addEventListener("sealai:form:patch", handleFormPatch as EventListener);
    return () => {
      window.removeEventListener("sealai:form:patch", handleFormPatch as EventListener);
    };
  }, []);

  const isHighPressure = form.pressureCategory === "hochdruck";
  const isSpecialRequirementSelected = form.specialRequirements.length > 0;
  const isStage1Complete =
    form.applicationType &&
    (form.applicationType !== "Sonstiges" || form.applicationOther.trim() !== "") &&
    form.mediumType &&
    form.temperatureMin.trim() !== "" &&
    form.temperatureMax.trim() !== "" &&
    form.speedMaxRpm.trim() !== "" &&
    form.pressureCategory &&
    (!isHighPressure || form.maxPressure.trim() !== "") &&
    form.dirtLevel &&
    form.lifetimeRequirement &&
    isSpecialRequirementSelected;

  const helperTextProps = "text-[11px] text-gray-500";

  const toggleSpecialRequirement = (value: RadialSealFormState["specialRequirements"][number]) => {
    setForm((prev) => {
      if (value === "keine besonderen Anforderungen") {
        return { ...prev, specialRequirements: ["keine besonderen Anforderungen"] };
      }
      const withoutNone = prev.specialRequirements.filter(
        (entry) => entry !== "keine besonderen Anforderungen"
      );
      const hasValue = withoutNone.includes(value);
      const updated = hasValue
        ? withoutNone.filter((entry) => entry !== value)
        : [...withoutNone, value];
      return {
        ...prev,
        specialRequirements:
          updated.length > 0 ? updated : ["keine besonderen Anforderungen"],
      };
    });
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleReset = () => {
    setForm(initialState);
    setShowTechnical(false);
    setSubmitAttempted(false);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitAttempted(true);
    if (!isStage1Complete) return;
    // Mock submission path; später an Backend anbinden.
  };

  const summary = useMemo(() => {
    if (!isStage1Complete) {
      return "Basisdaten vervollständigen, um eine Empfehlung vorzubereiten.";
    }
    return `Anwendung: ${form.applicationType}${
      form.applicationType === "Sonstiges" ? ` (${form.applicationOther})` : ""
    } · Medium: ${form.mediumType} · Temperatur ${form.temperatureMin}–${form.temperatureMax} °C`;
  }, [
    isStage1Complete,
    form.applicationType,
    form.applicationOther,
    form.mediumType,
    form.temperatureMin,
    form.temperatureMax,
  ]);

  return (
    <form
      className="flex flex-col gap-4 text-sm text-gray-800"
      onSubmit={handleSubmit}
      noValidate
    >
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-gray-900">1. Schnelle Auslegung</h2>
        <p className="text-xs text-gray-500">
          Nur die wichtigsten Eckdaten für ein Material- und Profilvorschlag.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="flex items-center justify-between text-sm font-medium text-gray-700">
              <span>Anwendungstyp *</span>
            </label>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {applicationOptions.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setForm((prev) => ({ ...prev, applicationType: option }))}
                  className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                    form.applicationType === option
                      ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                      : "border-gray-200 bg-white text-gray-600 hover:border-emerald-400"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
            {form.applicationType === "Sonstiges" && (
              <input
                type="text"
                name="applicationOther"
                value={form.applicationOther}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="Bitte Anwendung beschreiben"
              />
            )}
          </div>

          <div className="space-y-2">
            <label className="flex items-center justify-between text-sm font-medium text-gray-700">
              <span>Medium *</span>
            </label>
            <select
              name="mediumType"
              value={form.mediumType}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="" disabled>
                Auswahl treffen
              </option>
              {mediumOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <input
              type="text"
              name="mediumDetails"
              value={form.mediumDetails}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              placeholder="z. B. ISO VG 220 oder ergänzende Informationen"
            />
            <p className={helperTextProps}>
              Dieser Wert ist wichtig für die Auswahl des Dichtungsmaterials (Elastomer).
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-sm text-gray-700">
              <span>Min. Temperatur [°C] *</span>
              <input
                type="number"
                name="temperatureMin"
                value={form.temperatureMin}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>Max. Temperatur [°C] *</span>
              <input
                type="number"
                name="temperatureMax"
                value={form.temperatureMax}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
          </div>
          <p className={helperTextProps}>
            Bitte typische Einsatztemperaturen angeben, keine extrem kurzen Spitzen.
          </p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">
              Maximale Drehzahl [U/min] *
            </label>
            <input
              type="number"
              name="speedMaxRpm"
              value={form.speedMaxRpm}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <p className={helperTextProps}>
              Wenn du den genauen Wert nicht kennst, gib eine grobe Schätzung an (z. B. 1500,
              3000 oder 6000 U/min).
            </p>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700">Druckniveau *</p>
            <div className="space-y-2">
              {pressureOptions.map((option) => (
                <label key={option.value} className="flex items-center gap-2 text-sm text-gray-600">
                  <input
                    type="radio"
                    name="pressureCategory"
                    value={option.value}
                    checked={form.pressureCategory === option.value}
                    onChange={handleChange}
                    className="h-4 w-4 rounded-full border-gray-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            {isHighPressure && (
              <label className="space-y-1 text-sm text-gray-700">
                <span>Maximaler Druck [bar] *</span>
                <input
                  type="number"
                  name="maxPressure"
                  value={form.maxPressure}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </label>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700">Verschmutzungsgrad Umgebung (Luftseite) *</p>
            <select
              name="dirtLevel"
              value={form.dirtLevel}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="" disabled>
                Auswahl treffen
              </option>
              {dirtOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700">Lebensdaueranforderung *</p>
            <select
              name="lifetimeRequirement"
              value={form.lifetimeRequirement}
              onChange={handleChange}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="" disabled>
                Auswahl treffen
              </option>
              {lifetimeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-2xl border border-dashed border-gray-200/60 bg-white/60 p-4">
        <label className="text-sm font-medium text-gray-700 flex items-center justify-between">
          <span>Besondere Materialanforderungen *</span>
        </label>
        <p className={helperTextProps}>
          Mehrfachauswahl möglich – wähle „keine besonderen Anforderungen“, wenn nichts zutrifft.
        </p>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {specialRequirementOptions.map((option) => (
            <label
              key={option}
              className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition hover:border-emerald-400"
            >
              <input
                type="checkbox"
                checked={form.specialRequirements.includes(option)}
                onChange={() => toggleSpecialRequirement(option)}
                className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
              />
              {option}
            </label>
          ))}
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-2 rounded-2xl border border-gray-200 bg-white/70 p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Status</p>
          <p className="text-sm font-medium text-gray-800">{summary}</p>
          <p className="text-[11px] text-gray-500">
            Sobald alle Pflichtfelder ausgefüllt sind, kannst du weiter zu den technischen Details
            oder direkt eine Auslegung anfragen.
          </p>
        </div>
        <PreliminaryRecommendation />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setShowTechnical((prev) => !prev)}
          className="rounded-full border border-emerald-500 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100"
        >
          {showTechnical ? "Technische Details ausblenden" : "Technische Details einblenden (optional)"}
        </button>
        <button
          type="submit"
          disabled={!isStage1Complete}
          className={`rounded-full bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition ${
            isStage1Complete ? "hover:bg-emerald-700" : "opacity-60 cursor-not-allowed"
          }`}
        >
          Auslegung anfragen
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          Zurücksetzen
        </button>
      </div>

      {submitAttempted && !isStage1Complete && (
        <p className="text-[11px] text-red-500 mt-1">
          Bitte alle Pflichtfelder der Schnellen Auslegung ausfüllen (mit * gekennzeichnet), bevor du die Auslegung anfragst.
        </p>
      )}

      {showTechnical && (
        <section className="space-y-4 rounded-2xl border border-gray-200 bg-white/60 p-4">
          <header>
            <h3 className="text-sm font-semibold text-gray-900">2. Technische Details (optional)</h3>
            <p className="text-[11px] text-gray-500">Diese Angaben präzisieren die Auslegung, sind aber optional.</p>
          </header>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="space-y-1 text-sm text-gray-700">
              <span>Wellen-Ø d₁ [mm]</span>
              <input
                type="number"
                name="shaftDiameter"
                value={form.shaftDiameter}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>Gehäusebohrung D [mm]</span>
              <input
                type="number"
                name="housingDiameter"
                value={form.housingDiameter}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>axialer Bauraum für Dichtung [mm]</span>
              <input
                type="number"
                name="axialSpace"
                value={form.axialSpace}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1 text-sm text-gray-700">
              <span>Wellenwerkstoff</span>
              <select
                name="shaftMaterial"
                value={form.shaftMaterial}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {shaftMaterialOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>Härteklasse</span>
              <select
                name="shaftHardnessCategory"
                value={form.shaftHardnessCategory}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {hardnessOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="space-y-1 text-sm text-gray-700">
              <span>Einbaulage</span>
              <select
                name="mountOrientation"
                value={form.mountOrientation}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {orientationOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>Ölstand relativ zur Dichtung</span>
              <select
                name="oilLevelRelativeToSeal"
                value={form.oilLevelRelativeToSeal}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {oilLevelOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>Drehrichtung der Welle</span>
              <select
                name="rotationDirection"
                value={form.rotationDirection}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {rotationOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1 text-sm text-gray-700">
              <span>Wo liegt das Medium?</span>
              <select
                name="mediumSide"
                value={form.mediumSide}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">Auswahl treffen</option>
                {mediumSideOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm text-gray-700">
              <span>OEM-/Normvorgaben</span>
              <input
                type="text"
                name="norms"
                value={form.norms}
                onChange={handleChange}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="z. B. Automotive, Bahn, FDA …"
              />
            </label>
          </div>
        </section>
      )}
    </form>
  );
}
