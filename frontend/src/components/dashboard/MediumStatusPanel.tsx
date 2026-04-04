"use client";

import type { MediumStatusViewModel } from "@/lib/mediumStatusView";

type Props = {
  view: MediumStatusViewModel;
};

function toneClasses(tone: MediumStatusViewModel["tone"]): string {
  switch (tone) {
    case "success":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-600";
  }
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  if (!value) {
    return null;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-[11px] text-slate-700">{value}</p>
    </div>
  );
}

export default function MediumStatusPanel({ view }: Props) {
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-sm font-semibold text-slate-800">
          {view.label || view.statusLabel}
        </p>
        <span
          className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${toneClasses(view.tone)}`}
        >
          {view.statusLabel}
        </span>
      </div>

      <p className="text-[11px] leading-relaxed text-slate-600">{view.summary}</p>

      <div className="grid gap-2">
        <InfoRow label="Familie" value={view.family} />
        <InfoRow label="Einordnungssicherheit" value={view.confidence} />
        <InfoRow
          label="Genannte Bezeichnung"
          value={view.status !== "recognized" ? view.rawMention : null}
        />
      </div>
    </div>
  );
}
