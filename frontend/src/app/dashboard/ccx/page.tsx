'use client';
import Link from "next/link";
import { useEffect, useState } from "react";

type Job = {
  jobId: string;
  status: "queued" | "running" | "finished" | "error";
  lastUpdated?: string | null;
  files: { dat?: string; frd?: string; vtu?: string };
};
type JobsResp = { jobs: Job[] };

export default function Page() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await fetch("/api/ccx/jobs", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const { jobs }: JobsResp = await res.json();
        setJobs(jobs);
      } catch (e: any) {
        setErr(e?.message ?? "Fetch error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (err) return <div className="p-6 text-sm text-red-600">Fehler: {err}</div>;

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">CalculiX Jobs</h1>
      {loading ? (
        <div className="text-sm text-gray-500">lädt…</div>
      ) : (
        <ul className="divide-y divide-gray-200 rounded-xl border border-gray-200 bg-white">
          {jobs.length === 0 && (
            <li className="p-4 text-sm text-gray-500">Keine Jobs gefunden</li>
          )}
          {jobs.map((j) => (
            <li key={j.jobId} className="p-4 flex items-center justify-between">
              <div className="space-y-1">
                <div className="font-medium">{j.jobId}</div>
                <div className="text-xs text-gray-500">
                  Status: {j.status}
                  {j.lastUpdated ? ` · ${new Date(j.lastUpdated).toLocaleString()}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {j.files.dat && <a className="text-sm underline" href={j.files.dat}>.dat</a>}
                {j.files.frd && <a className="text-sm underline" href={j.files.frd}>.frd</a>}
                {j.files.vtu && <a className="text-sm underline" href={j.files.vtu}>.vtu</a>}
                <Link className="text-sm px-3 py-1 rounded-lg border" href={`/dashboard/ccx/${encodeURIComponent(j.jobId)}`}>Details</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
