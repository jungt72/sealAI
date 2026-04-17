"use client";

import React from "react";
import ChatComposer from "@/components/dashboard/ChatComposer";
import { cn } from "@/lib/utils";

interface ChatPaneProps {
  caseId?: string;
}

export default function ChatPane({ caseId }: ChatPaneProps) {
  // Mock für OnSend, in späteren Phasen an echte API-Logik gebunden
  const handleSend = (msg: string) => {
    console.log("Sende Nachricht für Fall:", caseId, msg);
  };

  return (
    <div className="flex flex-col h-full w-full bg-slate-50/30">
      {/* MESSAGES AREA */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="mx-auto max-w-3xl px-4 py-8">
          <div className="flex flex-col gap-6">
            {/* Erste Begrüßung / Status-Nachricht */}
            <div className="flex flex-col gap-2">
              <div className="text-sm font-semibold text-seal-blue uppercase tracking-widest opacity-70">
                SeaLAI Analyse-Workbench
              </div>
              <h1 className="text-2xl font-bold text-foreground">
                {caseId ? `Analyse-Fall: ${caseId}` : "Neue Dichtungsanalyse"}
              </h1>
              <p className="text-muted-foreground leading-relaxed max-w-2xl mt-2">
                Willkommen in der SeaLAI Workbench. Ich unterstütze Sie bei der technischen 
                Einordnung und Qualifizierung Ihres Dichtungsproblems.
              </p>
            </div>

            {/* Platzhalter für Chat-Nachrichten */}
            <div className="rounded-2xl bg-white border border-border p-6 shadow-sm">
              <p className="text-[15px] leading-relaxed">
                Ich habe Ihren Fall initial erfasst. Basierend auf Ihren Angaben befinden wir uns 
                aktuell in der Phase der **Bedarfs-Exploration**.
                <br /><br />
                Um die technische Eingrenzung vorzunehmen, benötigen wir Informationen zum 
                Einsatzbereich (z.B. Pumpe, Ventil, rotierend/statisch) und den primären 
                Betriebsbedingungen.
              </p>
            </div>
            
            {!caseId && (
              <div className="flex flex-col gap-4 border-t border-border pt-6">
                <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                  Vorschläge für den Einstieg:
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {[
                    "Ich plane ein neues Design für eine Chemiepumpe.",
                    "Es liegt ein vorzeitiger Ausfall einer Wellendichtung vor.",
                    "Ich benötige eine technische Validierung für einen Retrofit.",
                    "Ich möchte einen bestehenden Ersatzteil-Typ identifizieren."
                  ].map((s) => (
                    <button 
                      key={s}
                      onClick={() => handleSend(s)}
                      className="text-left p-4 rounded-xl border border-border bg-white hover:bg-slate-50 transition-colors text-sm font-medium text-foreground/80"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* COMPOSER AREA */}
      <div className="border-t border-border bg-white p-4">
        <div className="mx-auto max-w-3xl">
          <ChatComposer onSend={handleSend} />
          <div className="mt-3 text-center">
            <p className="text-[11px] text-muted-foreground opacity-60">
              SeaLAI liefert technische Vorqualifizierungen. Herstellerfreigabe bleibt die finale Instanz.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
