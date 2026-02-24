import Link from "next/link";
import { ArrowRight, ShieldCheck, Zap, Activity } from "lucide-react";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      {/* Hero Section */}
      <section className="relative flex flex-1 flex-col justify-center items-center overflow-hidden px-6 pt-16 text-center">
        
        {/* Abstract Background Elements */}
        <div className="absolute top-0 left-1/2 -ml-[40rem] shadow-[0_0_1000px_100px_rgba(14,165,233,0.15)] rounded-full w-[80rem] h-[80rem] bg-indigo-500/10 blur-3xl -z-10" />
        
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/50 px-3 py-1 text-xs font-medium text-slate-400 backdrop-blur">
          <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          System Operational • v3.1 Platinum
        </div>

        <h1 className="max-w-4xl text-5xl font-extrabold tracking-tight text-white lg:text-7xl">
          Industrial AI <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-cyan-300">Orchestration</span>
        </h1>
        
        <p className="mt-6 max-w-2xl text-lg text-slate-400">
          Autonomous multi-agent supervision for high-pressure sealing environments. 
          Monitor reasoning streams, verify material compatibility, and ensure ISO compliance in real-time.
        </p>

        <div className="mt-10 flex flex-col gap-4 sm:flex-row">
          <Link 
            href="/dashboard"
            className="inline-flex h-12 items-center justify-center rounded-md bg-gradient-to-r from-sky-600 to-cyan-600 px-8 text-sm font-medium text-white shadow-lg transition-all hover:brightness-110 hover:shadow-cyan-500/25"
          >
            Enter Supervisor Dashboard
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
          <button disabled className="inline-flex h-12 items-center justify-center rounded-md border border-slate-800 bg-slate-950 px-8 text-sm font-medium text-slate-500 cursor-not-allowed">
            View Documentation
          </button>
        </div>

        {/* Feature Grid Mockup */}
        <div className="mt-24 grid w-full max-w-5xl grid-cols-1 gap-8 md:grid-cols-3 text-left">
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 backdrop-blur transition hover:border-slate-700">
            <Zap className="h-8 w-8 text-sky-400 mb-4" />
            <h3 className="font-semibold text-white">Real-Time Reasoning</h3>
            <p className="mt-2 text-sm text-slate-400">Observe agent thought processes as they execute standard operating procedures.</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 backdrop-blur transition hover:border-slate-700">
            <ShieldCheck className="h-8 w-8 text-emerald-400 mb-4" />
            <h3 className="font-semibold text-white">Safety Guardrails</h3>
            <p className="mt-2 text-sm text-slate-400">Automated verification of hydrogen compatibility and pressure limits.</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 backdrop-blur transition hover:border-slate-700">
            <Activity className="h-8 w-8 text-amber-400 mb-4" />
            <h3 className="font-semibold text-white">Live Telemetry</h3>
            <p className="mt-2 text-sm text-slate-400">Connect to industrial sensors via MCP protocol for live data ingestion.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
