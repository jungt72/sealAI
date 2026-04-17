"use client";

import React, { useState } from "react";
import { CockpitData } from "@/hooks/useCockpitData";
import { generateTechnicalSummary } from "@/lib/engineering/artifacts";
import { 
  Send, 
  CheckCircle2, 
  AlertTriangle, 
  Building2, 
  ShieldCheck, 
  ArrowRight,
  Info
} from "lucide-react";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { StatusBadge } from "./CockpitElements";
import { cn } from "@/lib/utils";
import { buildRfqPayload } from "@/lib/engineering/rfq";
import { submitRfq } from "@/lib/bff/workspace";

interface RfqPaneProps {
  data: CockpitData | null;
  caseId?: string;
}

// Mocked manufacturer data as per objective 2
const MOCK_MANUFACTURERS = [
  {
    id: "m1",
    name: "EagleBurgmann",
    capability: "Mechanical Seals / Pumps",
    score: 0.95,
    notes: "Marktführer für GLRD, hervorragend für Standard- und Spezialpumpen.",
    fitReason: "Hohe Deckung mit dem Engineering-Pfad 'mechanical_seal_pump'."
  },
  {
    id: "m2",
    name: "John Crane",
    capability: "Sealing Solutions",
    score: 0.92,
    notes: "Starkes Portfolio für petrochemische Anwendungen und hohe Drücke.",
    fitReason: "Gelistete Beständigkeiten passen zum identifizierten Medium."
  },
  {
    id: "m3",
    name: "Flowserve",
    capability: "Pump Systems & Seals",
    score: 0.88,
    notes: "Integrierte Systemlösungen, gut für komplexe Retrofit-Projekte.",
    fitReason: "Spezialisierung auf Retrofit passt zum gewählten Anfragetyp."
  }
];

export default function RfqPane({ data, caseId }: RfqPaneProps) {
  const [selectedManufacturers, setSelectedManufacturers] = useState<string[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!data || !caseId) return null;

  const isReady = data.view.readiness.isRfqReady;
  const summary = generateTechnicalSummary(data);

  const toggleManufacturer = (id: string) => {
    setSelectedManufacturers(prev => 
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    );
  };

  const handleSend = async () => {
    if (!isReady || selectedManufacturers.length === 0) return;
    
    setIsSending(true);
    setError(null);
    try {
      const payload = buildRfqPayload(data, caseId, selectedManufacturers);
      await submitRfq(caseId, payload);
      setIsSent(true);
    } catch (err) {
      console.error("RFQ Submit Error:", err);
      setError("Anfrage konnte nicht gesendet werden.");
    } finally {
      setIsSending(false);
    }
  };

  if (isSent) {
    return (
      <div className="flex h-full items-center justify-center p-12 bg-slate-50/30">
        <div className="max-w-md w-full bg-white rounded-3xl border border-emerald-100 p-10 text-center shadow-xl shadow-emerald-500/5">
          <div className="mx-auto w-20 h-20 bg-emerald-50 rounded-full flex items-center justify-center mb-6">
            <CheckCircle2 size={40} className="text-emerald-500" />
          </div>
          <h2 className="text-2xl font-bold text-seal-blue mb-2">Anfrage erfolgreich versendet</h2>
          <p className="text-muted-foreground mb-8">
            Ihre technische Anfrage wurde an {selectedManufacturers.length} Hersteller übermittelt. Sie erhalten Rückmeldungen direkt in Ihrem Dashboard.
          </p>
          <div className="flex flex-col gap-3">
            <div className="p-4 bg-slate-50 rounded-xl text-left border border-border/50">
              <p className="text-[10px] font-bold uppercase text-muted-foreground mb-2 tracking-widest">Empfänger:</p>
              <div className="flex flex-wrap gap-2">
                {selectedManufacturers.map(id => {
                  const m = MOCK_MANUFACTURERS.find(x => x.id === id);
                  return (
                    <span key={id} className="px-2 py-1 bg-white border border-border rounded text-[11px] font-medium">
                      {m?.name}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-50/30 overflow-hidden">
      <div className="flex-1 overflow-y-auto p-8">
        <div className="mx-auto max-w-5xl">
          {/* HEADER */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10 pb-6 border-b border-border/50">
            <div>
              <h1 className="text-2xl font-bold text-seal-blue">Anfrage-Prozess (RFQ)</h1>
              <p className="text-sm text-muted-foreground mt-1">Finalisieren und versenden Sie Ihre technische Anfrage an qualifizierte Hersteller.</p>
            </div>
            <div className="flex items-center gap-4">
               {error && (
                 <div className="text-[11px] text-rose-600 font-medium bg-rose-50 px-3 py-1.5 rounded-lg border border-rose-100">
                   {error}
                 </div>
               )}
               {!isReady && (
                 <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-xs font-medium">
                   <AlertTriangle size={14} /> Anfrage blockiert
                 </div>
               )}
               <button 
                onClick={handleSend}
                disabled={!isReady || selectedManufacturers.length === 0 || isSending}
                className={cn(
                  "flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg",
                  isReady && selectedManufacturers.length > 0
                    ? "bg-seal-blue text-white hover:opacity-90 active:scale-95 shadow-seal-blue/20"
                    : "bg-slate-200 text-muted-foreground cursor-not-allowed shadow-none"
                )}
              >
                {isSending ? "Wird gesendet..." : "An Hersteller senden"}
                {!isSending && <Send size={16} />}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* LEFT: SUMMARY & DATA */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              <div className="rounded-2xl border border-border bg-white shadow-sm overflow-hidden">
                <div className="px-6 py-3 border-b border-border bg-slate-50 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-seal-blue">
                    <ShieldCheck size={18} />
                    <span className="text-xs font-bold uppercase tracking-widest">Technische Validierung</span>
                  </div>
                  <StatusBadge 
                    label={data.view.readiness.status} 
                    variant={isReady ? "success" : "warning"} 
                  />
                </div>
                <div className="p-6 prose-print max-h-[500px] overflow-y-auto custom-scrollbar bg-slate-50/30">
                  <MarkdownRenderer>{summary}</MarkdownRenderer>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-blue-50 border border-blue-100 flex items-start gap-3">
                <Info className="text-blue-600 shrink-0 mt-0.5" size={18} />
                <div className="text-sm text-blue-800">
                  <p className="font-bold">Hersteller-Prüfvorbehalt</p>
                  <p className="opacity-80">Finale technische Prüfung erfolgt durch den Hersteller. SealingAI dient als qualifizierte Entscheidungsgrundlage.</p>
                </div>
              </div>
            </div>

            {/* RIGHT: MANUFACTURER SELECTION */}
            <div className="lg:col-span-5 flex flex-col gap-6">
              <div className="flex flex-col gap-4">
                <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                  <Building2 size={14} /> Passende Hersteller auswählen
                </h3>
                
                <div className="flex flex-col gap-3">
                  {MOCK_MANUFACTURERS.map((m) => {
                    const isSelected = selectedManufacturers.includes(m.id);
                    return (
                      <div 
                        key={m.id}
                        onClick={() => toggleManufacturer(m.id)}
                        className={cn(
                          "group relative p-4 rounded-2xl border transition-all cursor-pointer",
                          isSelected 
                            ? "bg-white border-seal-blue ring-1 ring-seal-blue shadow-md" 
                            : "bg-white border-border hover:border-seal-blue/40"
                        )}
                      >
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <h4 className="font-bold text-seal-blue">{m.name}</h4>
                            <p className="text-[11px] text-muted-foreground">{m.capability}</p>
                          </div>
                          <div className={cn(
                            "h-5 w-5 rounded-full border flex items-center justify-center transition-colors",
                            isSelected ? "bg-seal-blue border-seal-blue" : "border-border bg-slate-50"
                          )}>
                            {isSelected && <div className="h-2 w-2 bg-white rounded-full" />}
                          </div>
                        </div>
                        
                        <p className="text-[12px] text-foreground/80 leading-relaxed mb-3">
                          {m.notes}
                        </p>
                        
                        <div className="flex flex-col gap-1 border-t border-border/50 pt-2">
                          <p className="text-[10px] font-bold text-emerald-700 uppercase flex items-center gap-1">
                            <CheckCircle2 size={10} /> Warum dieser Match?
                          </p>
                          <p className="text-[10px] text-muted-foreground italic">
                            {m.fitReason}
                          </p>
                        </div>

                        <div className="absolute top-4 right-12">
                           <span className="text-[10px] font-bold text-seal-blue bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100">
                             {Math.round(m.score * 100)}% Fit
                           </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {selectedManufacturers.length === 0 && (
                  <p className="text-[11px] text-center text-muted-foreground italic mt-2">
                    Bitte wählen Sie mindestens einen Hersteller für die Anfrage aus.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
