"use client";

import React, { useState } from "react";
import ChatPane from "@/components/dashboard/ChatPane";
import ArtifactsPane from "@/components/dashboard/ArtifactsPane";
import RfqPane from "@/components/dashboard/RfqPane";
import { 
  CockpitTabs, 
  CockpitPanel, 
  CockpitCard, 
  CockpitTabType,
  ParameterRow,
  StatusBadge
} from "@/components/dashboard/CockpitElements";
import { 
  ClipboardCheck, 
  AlertCircle, 
  Info, 
  FileCheck,
  ShieldAlert,
  Search,
  ArrowRight,
  CheckCircle2,
  Send
} from "lucide-react";
import { useCockpitData } from "@/hooks/useCockpitData";

interface CaseScreenProps {
  caseId?: string;
  initialRequestType?: string;
}

export default function CaseScreen({ caseId, initialRequestType }: CaseScreenProps) {
  const [activeTab, setActiveTab] = useState<CockpitTabType>("clarification");
  const cockpit = useCockpitData();

  const isInitial = !cockpit || (!cockpit.view.readiness.isRfqReady && cockpit.coverage === 0);
  const displayRequestType = (cockpit?.view.requestType && cockpit.view.requestType !== "nicht bestimmt")
    ? cockpit.view.requestType 
    : initialRequestType;
  const mediumStatusTone = cockpit?.mediumStatus.tone;
  const mediumStatusUiVariant = mediumStatusTone === "neutral" ? "default" : mediumStatusTone;

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-white">
      {/* TABS HEADER */}
      <CockpitTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {/* CONTENT AREA */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden xl:flex-row">
        {/* MAIN AREA (DYNAMIC BASED ON TAB) */}
        <div className="relative min-h-0 min-w-0 flex-1">
          {activeTab === "clarification" && <ChatPane caseId={caseId} />}
          {activeTab === "documents" && <ArtifactsPane data={cockpit} caseId={caseId} />}
          {activeTab === "rfq" && <RfqPane data={cockpit} caseId={caseId} />}
          {activeTab !== "clarification" && activeTab !== "documents" && activeTab !== "rfq" && (
            <div className="flex h-full items-center justify-center p-12 text-muted-foreground italic bg-slate-50/30">
              Bereich &quot;{activeTab}&quot; ist in Vorbereitung (Phase 9).
            </div>
          )}
        </div>

        {/* COCKPIT PANEL (Right) */}
        <CockpitPanel>
          {/* 1. STATUS & REIFEGRAD */}
          <CockpitCard 
            title="Status & Reifegrad" 
            icon={ClipboardCheck}
          >
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center mb-1">
                <StatusBadge 
                  label={cockpit?.view.readiness.status || "Analyse startet..."} 
                  variant={cockpit?.view.readiness.isRfqReady ? "success" : "info"}
                />
                <span className="text-[12px] font-bold text-seal-blue">
                  {Math.round((cockpit?.coverage || 0) * 100)}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-seal-blue transition-all duration-500" 
                  style={{ width: `${(cockpit?.coverage || 0) * 100}%` }}
                />
              </div>
              <div className="mt-2 flex flex-col gap-1">
                <p className="text-[11px] opacity-70">
                  Anfragetyp: <span className="font-semibold text-foreground uppercase">{displayRequestType || "nicht bestimmt"}</span>
                </p>
                <p className="text-[11px] opacity-70">
                  Pfad: <span className="font-semibold text-foreground">{cockpit?.view.path || "Unklar"}</span>
                </p>
                <p className="text-[11px] opacity-70">
                  Release: <span className="font-semibold text-foreground uppercase">{cockpit?.releaseStatus || "Prüfung..."}</span>
                </p>
              </div>
            </div>
          </CockpitCard>

          {/* 2. HANDLUNGSBEDARF / OFFENE PUNKTE */}
          <CockpitCard 
            title="Handlungsbedarf" 
            icon={AlertCircle}
            status={cockpit?.view.readiness.missingMandatoryKeys.length ? "warning" : "default"}
          >
            {isInitial ? (
              <p className="text-[12px] italic opacity-60">
                Warte auf initiale Falldaten zur Ermittlung des Handlungsbedarfs...
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {cockpit?.view.readiness.missingMandatoryKeys.length ? (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-[10px] font-bold text-amber-700 uppercase">Fehlende Pflichtangaben:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {cockpit.view.readiness.missingMandatoryKeys.map(key => (
                        <span key={key} className="px-1.5 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-medium rounded border border-amber-200 uppercase">
                          {key.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-emerald-600 font-medium text-[12px]">
                    <ShieldAlert size={14} />
                    Keine blockierenden Pflichtfelder offen.
                  </div>
                )}

                {cockpit?.view.readiness.blockers && cockpit.view.readiness.blockers.length > 0 && (
                  <div className="flex flex-col gap-1.5 border-t border-border/50 pt-2">
                    <p className="text-[10px] font-bold text-rose-700 uppercase">Blocker / Konflikte:</p>
                    <ul className="space-y-1">
                      {cockpit.view.readiness.blockers.map((b, i) => (
                        <li key={i} className="text-[11px] text-rose-800 leading-tight">
                          • {b}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </CockpitCard>

          {/* 3. KRITISCHE PARAMETER */}
          <CockpitCard 
            title="Technische Parameter" 
            icon={Search}
          >
            {isInitial ? (
              <p className="text-[12px] italic opacity-60">
                Noch keine Parameter extrahiert.
              </p>
            ) : (
              <div className="flex flex-col gap-1">
                {cockpit?.view.sections.core_intake.properties.map(p => (
                  <ParameterRow 
                    key={p.key}
                    label={p.label}
                    value={p.value}
                    unit={p.unit}
                    isMandatory={p.isMandatory}
                  />
                ))}
              </div>
            )}
          </CockpitCard>

          {/* 4. MEDIUM & RISIKO */}
          <CockpitCard 
            title="Medium & Risiko" 
            icon={ShieldAlert}
            status={mediumStatusUiVariant}
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-bold uppercase opacity-50">Medium-Status:</span>
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-seal-blue">
                    {cockpit?.mediumStatus.label || cockpit?.mediumStatus.rawMention || "Nicht identifiziert"}
                  </span>
                  <StatusBadge 
                    label={cockpit?.mediumStatus.statusLabel || "unbekannt"} 
                    variant={mediumStatusUiVariant} 
                  />
                </div>
                {cockpit?.mediumStatus.status === "unavailable" && (
                  <p className="text-[11px] text-amber-700 font-medium mt-1">
                    ⚠️ Medium erforderlich für belastbare Bewertung
                  </p>
                )}
              </div>

              {cockpit?.view.mediumContext.riskFlags && cockpit.view.mediumContext.riskFlags.length > 0 && (
                <div className="flex flex-col gap-1.5 border-t border-border/50 pt-2">
                  <p className="text-[10px] font-bold text-rose-700 uppercase tracking-wider">Risikofaktoren:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {cockpit.view.mediumContext.riskFlags.map(f => (
                      <span key={f} className="text-[10px] font-medium text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-100">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CockpitCard>

          {/* 5. PTFE-RWDR FOKUS */}
          <CockpitCard 
            title="PTFE-RWDR Fokus" 
            icon={Search}
          >
            <div className="flex flex-col gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-bold text-seal-blue">Radialwellendichtring</span>
                  <StatusBadge label="SSoT" variant="info" />
                </div>
                <p className="mt-1.5 text-[11px] leading-tight text-muted-foreground">
                  Bewertung bleibt auf PTFE-RWDR und technische Vorqualifizierung begrenzt.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <span className="block font-bold text-slate-700">Kontaktfläche</span>
                  <span className="text-muted-foreground">Welle / Gegenlauf</span>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <span className="block font-bold text-slate-700">Primärrisiko</span>
                  <span className="text-muted-foreground">PV, Wärme, Verschleiß</span>
                </div>
              </div>
              <button 
                onClick={() => setActiveTab("rfq")}
                className="mt-1 flex w-full items-center justify-center gap-2 rounded-lg bg-seal-blue/5 py-2 text-[11px] font-bold text-seal-blue transition-colors hover:bg-seal-blue/10"
              >
                Anfrage konfigurieren <ArrowRight size={12} />
              </button>
            </div>
          </CockpitCard>

          {/* 6. ANFRAGE-STATUS */}
          <CockpitCard 
            title="Anfrage-Status" 
            icon={Send}
          >
            <div className="flex flex-col gap-3">
              <div className="flex justify-between items-center">
                <span className="text-[12px] opacity-70">Aktueller Stand:</span>
                <StatusBadge 
                  label={
                    cockpit?.view.readiness.isRfqReady 
                      ? (cockpit?.releaseStatus === "ready" ? "Versendet" : "Versandbereit") 
                      : "In Vorbereitung"
                  } 
                  variant={cockpit?.view.readiness.isRfqReady ? "success" : "default"} 
                />
              </div>
              
              {cockpit?.view.readiness.isRfqReady ? (
                <div className="p-2.5 bg-emerald-50 rounded-lg border border-emerald-100 flex items-start gap-2">
                  <CheckCircle2 size={14} className="text-emerald-600 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-emerald-800 leading-tight">
                    Alle technischen Hürden genommen. Die Anfrage kann an Hersteller übermittelt werden.
                  </p>
                </div>
              ) : (
                <div className="p-2.5 bg-slate-50 rounded-lg border border-border/50 flex items-start gap-2">
                  <Info size={14} className="text-muted-foreground mt-0.5 shrink-0" />
                  <p className="text-[11px] text-muted-foreground leading-tight">
                    Vervollständigen Sie die technischen Parameter, um den Versand freizuschalten.
                  </p>
                </div>
              )}
            </div>
          </CockpitCard>

          {/* 7. ARTEFAKTE */}
          <CockpitCard 
            title="Artefakte" 
            icon={FileCheck}
          >
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5 border-b border-border/50 pb-3">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] opacity-70">Zusammenfassung</span>
                  <StatusBadge label={isInitial ? "Warten" : "Bereit"} variant={isInitial ? "default" : "success"} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] opacity-70">Anfragebasis (JSON)</span>
                  <StatusBadge label={isInitial ? "Warten" : "Bereit"} variant={isInitial ? "default" : "success"} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] opacity-70">PDF Bericht</span>
                  <StatusBadge 
                    label={cockpit?.view.readiness.isRfqReady ? "Generierbar" : "Gesperrt"} 
                    variant={cockpit?.view.readiness.isRfqReady ? "info" : "default"} 
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2">
                <button 
                  onClick={() => setActiveTab("documents")}
                  className="w-full py-2 bg-slate-100 hover:bg-slate-200 text-seal-blue text-[11px] font-bold rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <Search size={12} /> Dokumente anzeigen
                </button>
              </div>
            </div>
          </CockpitCard>
        </CockpitPanel>
      </div>
    </div>
  );
}
