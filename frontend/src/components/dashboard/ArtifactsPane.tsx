"use client";

import React from "react";
import { CockpitData } from "@/hooks/useCockpitData";
import { createRfqJson, generateTechnicalSummary } from "@/lib/engineering/artifacts";
import { FileText, Download, Code, Printer, AlertTriangle } from "lucide-react";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";

interface ArtifactsPaneProps {
  data: CockpitData | null;
  caseId?: string;
}

export default function ArtifactsPane({ data, caseId }: ArtifactsPaneProps) {
  if (!data || !caseId) {
    return (
      <div className="flex h-full items-center justify-center p-12 text-center">
        <div className="max-w-md">
          <AlertTriangle size={48} className="mx-auto mb-4 text-amber-400" />
          <h2 className="text-xl font-bold text-seal-blue mb-2">Keine Daten vorhanden</h2>
          <p className="text-muted-foreground text-sm">
            Bitte starten Sie zuerst eine Analyse im Bereich &quot;Klärung&quot;, um Artefakte zu erzeugen.
          </p>
        </div>
      </div>
    );
  }

  const summary = generateTechnicalSummary(data);
  const rfqJson = createRfqJson(data, caseId);
  const isReady = data.view.readiness.isRfqReady;

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(rfqJson, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SealingAI-Anfrage-${caseId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full bg-slate-50/30 overflow-hidden">
      <div className="flex-1 overflow-y-auto p-8">
        <div className="mx-auto max-w-4xl">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10 pb-6 border-b border-border/50">
            <div>
              <h1 className="text-2xl font-bold text-seal-blue">Dokumente & Artefakte</h1>
              <p className="text-sm text-muted-foreground mt-1">Exportieren Sie Ihre technischen Qualifizierungsergebnisse.</p>
            </div>
            <div className="flex gap-3">
              <button 
                onClick={() => window.print()}
                disabled={!isReady}
                className="flex items-center gap-2 px-4 py-2 bg-white border border-border rounded-lg text-sm font-bold text-seal-blue hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <Printer size={16} /> PDF Drucken
              </button>
              <button 
                onClick={downloadJson}
                disabled={!isReady}
                className="flex items-center gap-2 px-4 py-2 bg-seal-blue text-white rounded-lg text-sm font-bold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <Download size={16} /> JSON Export
              </button>
            </div>
          </div>

          {!isReady && (
            <div className="mb-8 p-4 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3">
              <AlertTriangle className="text-amber-600 shrink-0 mt-0.5" size={18} />
              <div className="text-sm text-amber-800">
                <p className="font-bold">Anfrage noch nicht vollständig</p>
                <p className="opacity-80">Ein PDF-Export ist erst nach Abschluss der technischen Vorqualifizierung möglich. Bitte klären Sie die offenen Punkte.</p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-8">
            {/* TECHNICAL SUMMARY PREVIEW */}
            <div className="rounded-2xl border border-border bg-white shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-slate-50 flex items-center gap-2 text-seal-blue">
                <FileText size={18} />
                <span className="text-xs font-bold uppercase tracking-widest">Technische Zusammenfassung</span>
              </div>
              <div className="p-8 prose-print">
                <MarkdownRenderer>{summary}</MarkdownRenderer>
              </div>
            </div>

            {/* JSON PREVIEW */}
            <div className="rounded-2xl border border-border bg-white shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-slate-50 flex items-center gap-2 text-seal-blue">
                <Code size={18} />
                <span className="text-xs font-bold uppercase tracking-widest">Strukturierte Anfragebasis (JSON)</span>
              </div>
              <div className="p-6 bg-slate-900 overflow-x-auto">
                <pre className="text-[12px] text-emerald-400 font-mono leading-relaxed">
                  {JSON.stringify(rfqJson, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
