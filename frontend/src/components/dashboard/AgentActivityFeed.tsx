type AgentLog = {
  id: string;
  agent: string;
  status: "thinking" | "executing" | "complete" | "error";
  message: string;
  timestamp: string;
};

const MOCK_LOGS: AgentLog[] = [
  { id: "1", agent: "Orchestrator", status: "complete", message: "Plan: Verify Hydogen Compatibility", timestamp: "10:42:01" },
  { id: "2", agent: "MaterialAgent", status: "executing", message: "Querying VectorDB for 'NBR-90' specs...", timestamp: "10:42:02" },
  { id: "3", agent: "SafetyAgent", status: "thinking", message: "Analyzing pressure limits for ISO-1234 compliance...", timestamp: "10:42:03" },
];

export default function AgentActivityFeed() {
  return (
    <div className="h-full flex flex-col bg-slate-900/50 border-l border-slate-800 w-80 shrink-0">
      <div className="p-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Live Agent Feed
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {MOCK_LOGS.map((log) => (
          <div key={log.id} className="relative pl-4 border-l-2 border-slate-700">
             <div className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-slate-600 ring-4 ring-slate-900" />
             <div className="mb-1 flex items-center justify-between">
                <span className={`text-xs font-mono font-bold ${
                    log.agent === "SafetyAgent" ? "text-amber-400" : "text-sky-400"
                }`}>
                    {log.agent}
                </span>
                <span className="text-[10px] text-slate-500">{log.timestamp}</span>
             </div>
             <p className="text-xs text-slate-300 bg-slate-800/50 p-2 rounded border border-slate-700/50">
                {log.message}
             </p>
          </div>
        ))}
        {/* Animated Loading State at bottom */}
        <div className="relative pl-4 border-l-2 border-slate-700/50">
            <div className="h-8 rounded bg-slate-800/30 animate-pulse" />
        </div>
      </div>
    </div>
  );
}
