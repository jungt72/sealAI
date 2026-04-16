"use client";

import React from "react";
// Hier könnten weitere Imports stehen (MarkdownRenderer, etc.)

interface ChatPaneProps {
  caseId?: string;
}

export default function ChatPane({ caseId }: ChatPaneProps) {
  return (
    <div className="flex flex-col h-full w-full">
      {/* Hier nutzt du die caseId, um z.B. den Chat-Verlauf zu laden.
         Wenn caseId undefined ist (bei /new), wird ein leerer Chat gezeigt.
      */}
      <div className="flex-1 overflow-y-auto p-4">
        {caseId ? `Chat für Fall: ${caseId}` : "Neuer Fall wird erstellt..."}
      </div>
      {/* Deine bestehende Chat-Eingabe-Logik */}
    </div>
  );
}
