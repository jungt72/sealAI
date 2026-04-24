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
  Info
} from "lucide-react";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { StatusBadge } from "./CockpitElements";
import { cn } from "@/lib/utils";

interface RfqPaneProps {
  data: CockpitData | null;
  caseId?: string;
}

export default function RfqPane({ data, caseId }: RfqPaneProps) {
  const [isSending, setIsSending] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!data || !caseId) return null;

  const isReady = data.view.readiness.isRfqReady;
  const summary = generateTechnicalSummary(data);
  const backendMatchingAvailable = false;

  const handleSend = async () => {
    if (!isReady || !backendMatchingAvailable) return;
    
    setIsSending(true);
    setError(null);
    try {
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
            Ihre technische Anfrage wurde über den backend-bestätigten Anfrageprozess übermittelt.
          </p>
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
                disabled={!isReady || !backendMatchingAvailable || isSending}
                className={cn(
                  "flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg",
                  isReady && backendMatchingAvailable
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

            {/* RIGHT: MANUFACTURER MATCHING */}
            <div className="lg:col-span-5 flex flex-col gap-6">
              <div className="flex flex-col gap-4">
                <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                  <Building2 size={14} /> Backend-Matching ausstehend
                </h3>
                
                <div className="rounded-2xl border border-dashed border-border bg-white p-5">
                  <div className="flex items-start gap-3">
                    <Info className="text-muted-foreground shrink-0 mt-0.5" size={18} />
                    <div>
                      <p className="text-sm font-semibold text-seal-blue">
                        Noch keine backend-bestätigte Herstellerliste
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        Hersteller-Matching wird erst angezeigt, wenn der Backend-Prozess
                        eine strukturierte, neutral geprüfte Auswahl liefert.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
