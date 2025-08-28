'use client';
import React, { useEffect, useMemo, useState } from "react";

type CcxSummary = {
  jobId: string;
  jobName: string;
  version?: string;
  status: "queued" | "running" | "finished" | "error";
  runtimeSec?: number;
  converged?: boolean;
  iterations?: number;
  lastUpdated?: string; // ISO-8601
  files?: { dat?: string; frd?: string; vtu?: string };
  logTail?: string[]; // last N lines
};

function fmtSec(s?: number): string {
  if (s === undefined || s === null) return "–";
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}m ${r.toFixed(1)}s`;
}

function Pill({
  label,
  tone,
}: {
  label: string;
  tone: "ok" | "warn" | "err" | "muted";
}) {
  const map = {
    ok: "bg-green-100 text-green-700",
    warn: "bg-amber-100 text-amber-700",
    err: "bg-red-100 text-red-700",
    muted: "bg-gray-100 text-gray-600",
  } as const;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[tone]}`}>
      {label}
    </span>
  );
}

export default function CcxResultCard({ jobId }: { jobId: string }) {
  const [data, setData] = useState<CcxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setErr(null);
      const res = await fetch(
        `/api/ccx/jobs/${encodeURIComponent(jobId)}/summary`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = (await res.json()) as CcxSummary;
      setData(j);
    } catch (e: any) {
      setErr(e?.message ?? "Fetch error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const es = new EventSource(
      `/api/ccx/jobs/${encodeURIComponent(jobId)}/events`
    );
    es.onmessage = (ev) => {
      try {
        const patch = JSON.parse(ev.data) as Partial<CcxSummary>;
        setData((prev) => ({ ...(prev ?? ({} as CcxSummary)), ...patch }));
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      /* auto-retry by browser */
    };
    return () => es.close();
  }, [jobId]);

  const statusPill = useMemo(() => {
    if (!data) return <Pill label="lädt…" tone="muted" />;
    const map: Record<CcxSummary["status"], JSX.Element> = {
      queued: <Pill label="Wartend" tone="muted" />,
      running: <Pill label="Läuft" tone="warn" />,
      finished: (
        <Pill
          label={data.converged ? "Fertig · konvergiert" : "Fertig"}
          tone={data.converged ? "ok" : "muted"}
        />
      ),
      error: <Pill label="Fehler" tone="err" />,
    };
    return map[data.status];
  }, [data]);

  const files = data?.files ?? {};

  return (
    <div className="rounded-2xl border border-gray-200 p-4 shadow-sm bg-white">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm text-gray-500">CalculiX Ergebnis</h3>
          <div className="mt-0.5 text-lg font-semibold">
            {data?.jobName ?? jobId}
          </div>
        </div>
        {statusPill}
      </div>

      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Version</div>
          <div className="font-medium">{data?.version ?? "–"}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Laufzeit</div>
          <div className="font-medium">{fmtSec(data?.runtimeSec)}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Iterationen</div>
          <div className="font-medium">{data?.iterations ?? "–"}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Aktualisiert</div>
          <div className="font-medium">
            {data?.lastUpdated
              ? new Date(data.lastUpdated).toLocaleString()
              : "–"}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.dat
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.dat ?? "#"}
          onClick={(e) => {
            if (!files.dat) e.preventDefault();
          }}
        >
          {files.dat ? "Download .dat" : "kein .dat"}
        </a>
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.frd
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.frd ?? "#"}
          onClick={(e) => {
            if (!files.frd) e.preventDefault();
          }}
        >
          {files.frd ? "Download .frd" : "kein .frd"}
        </a>
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.vtu
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.vtu ?? "#"}
          onClick={(e) => {
            if (!files.vtu) e.preventDefault();
          }}
        >
          {files.vtu ? "Download .vtu" : "kein .vtu (Export nötig)"}
        </a>
      </div>

      <button
        onClick={() => setShowLog((v) => !v)}
        className="mt-4 text-xs text-gray-600 underline"
        type="button"
      >
        {showLog ? "Log ausblenden" : "Log einblenden"}
      </button>

      {showLog && (
        <pre className="mt-2 max-h-48 overflow-auto text-xs bg-black text-green-200 p-3 rounded-xl">
{(data?.logTail ??
  (loading ? ["lade…"] : err ? [err] : ["kein Log verfügbar"])
).join("\n")}
        </pre>
      )}
    </div>
  );
}
