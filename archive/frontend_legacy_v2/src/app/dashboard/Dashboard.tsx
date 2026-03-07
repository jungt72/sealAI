"use client";

import React from "react";
import Chat from "./components/Chat/ChatContainer";
import AgentActivityFeed, { ReasoningEntry } from "./components/AgentActivityFeed";

export default function Dashboard() {
  // Initial "Platinum" system status to ensure the feed is visible and confirmatory
  const initialEntries: ReasoningEntry[] = [
    {
      id: 'sys-init',
      kind: 'system',
      title: 'Platinum Supervisor Active',
      text: 'Monitoring Agent Activity Stream...',
      timestamp: new Date().toISOString(),
    }
  ];

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Main Chat Area */}
      <div className="flex-1 min-w-0 h-full relative">
        <Chat />
      </div>

      {/* Supervisor Side Panel (Right) */}
      <div className="hidden xl:flex w-[350px] shrink-0 border-l border-slate-100 bg-white/50 overflow-y-auto flex-col h-full">
        <div className="p-4 border-b border-slate-100 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
          <h2 className="text-sm font-semibold text-slate-800">Agent Supervisor</h2>
          <p className="text-xs text-slate-500">Live Reasoning & Activity</p>
        </div>
        <div className="p-2">
          <AgentActivityFeed entries={initialEntries} />
        </div>
      </div>
    </div>
  );
}
