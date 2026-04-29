import type { SealCockpitOverview } from "@/lib/engineering/sealCockpitViewModel";

export const sealCockpitOverview: SealCockpitOverview = {
  tabs: [
    { id: "overview", label: "Übersicht" },
    { id: "parameters", label: "Parameter" },
    { id: "medium", label: "Medium" },
    { id: "application", label: "Anwendung" },
    { id: "material", label: "Werkstoff" },
    { id: "calculation", label: "Berechnung" },
    { id: "briefing", label: "Briefing" },
  ],
  statusStrip: [
    { label: "Dichtungsfall", value: "Rotierende Welle · Rührwerk" },
    { label: "Datenreife", value: "61 % belastbar" },
    { label: "Lösungsraum", value: "PTFE-RWDR vorqualifiziert" },
    { label: "Kritische Lücken", value: "Medium · Temperatur · Rundlauf" },
    { label: "Berechnungsstatus", value: "3 von 5 Nachweisen belastbar" },
  ],
  parameters: {
    rows: [
      { label: "Medium", value: "Glykolhaltiges Prozessmedium" },
      { label: "Temperatur", value: "35-90 °C" },
      { label: "Druck", value: "2,5 bar" },
      { label: "Drehzahl", value: "1.450 rpm" },
      { label: "Wellendurchmesser", value: "40 mm" },
      { label: "Geometrie / Rundlauf", value: "offen" },
    ],
    warning: "Kritisch offen: Rundlauf, Einbauraum, Leckageklasse",
  },
  criticalDrivers: [
    { label: "Schmierfähigkeit", risk: "Mittel", consequence: "Wärmeentwicklung prüfen" },
    { label: "Abrasive Partikel", risk: "Gering", consequence: "Verschleiß derzeit unkritisch" },
    { label: "Korrosionsrisiko", risk: "Mittel", consequence: "Werkstofffreigabe relevant" },
    { label: "Temperaturdynamik", risk: "Hoch", consequence: "Werkstoffreserve beachten" },
    { label: "Wellenbewegung / Rundlauf", risk: "Offen", consequence: "Dichtungsbauart noch nicht final" },
  ],
  solution: {
    assessmentTitle: "Vorläufige Einschätzung",
    assessment:
      "PTFE-RWDR ist plausibel, da rotierende Welle, moderater Druck und kompakter Einbauraum zusammenpassen.",
    rows: [
      {
        label: "Warum passend",
        value: "chemisch robuste Option, gute Eignung für dynamische Abdichtung",
      },
      {
        label: "Was noch geprüft werden muss",
        value: "Mediumverträglichkeit im Detail, Rundlauf, Gegenlauffläche",
      },
      {
        label: "Herstellerfrage",
        value: "Ist PTFE/FKM bei Medium X, 90 °C und 2,5 bar dauerhaft freigegeben?",
      },
    ],
  },
  calculations: [
    {
      label: "Umfangsgeschwindigkeit",
      value: "3,0 m/s",
      limit: "Grenze 8,0 m/s",
      reserve: "Reserve 62 %",
      status: "plausibel",
    },
    {
      label: "PV-Wert",
      value: "0,75 MPa·m/s",
      limit: "Grenze 1,60",
      reserve: "Reserve 53 %",
      status: "plausibel",
    },
    {
      label: "Temperaturreserve",
      value: "12 °C",
      limit: "Werkstofffenster 100 °C",
      status: "kritisch beobachten",
    },
    {
      label: "Druckreserve",
      value: "2,5 / 6,0 bar",
      reserve: "Reserve 58 %",
      status: "plausibel",
    },
  ],
  footerNote:
    "SealAI strukturiert den Dichtungsfall, erklärt technische Konsequenzen und bereitet das Herstellerbriefing vor.",
};
