"use client";

import type { WorkspaceView } from "@/lib/contracts/workspace";

type Props = {
  workspace: WorkspaceView;
};

function ListSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </p>
      <div className="mt-2 flex flex-col gap-1.5">
        {items.map((item) => (
          <div
            key={item}
            className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-700"
          >
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function MediumContextPanel({ workspace }: Props) {
  const mediumContext = workspace.mediumContext;

  if (mediumContext.status !== "available" || !mediumContext.mediumLabel) {
    return null;
  }

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Medium-Kontext
          </p>
          <p className="mt-1 text-sm font-semibold text-slate-800">
            {mediumContext.mediumLabel}
          </p>
        </div>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
          {mediumContext.scope}
        </span>
      </div>

      {mediumContext.summary ? (
        <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
          {mediumContext.summary}
        </p>
      ) : null}

      <div className="space-y-3">
        <ListSection title="Typische Eigenschaften" items={mediumContext.properties} />
        <ListSection title="Typische Herausforderungen" items={mediumContext.challenges} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Einordnung
        </p>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-600">
          {mediumContext.disclaimer || "Allgemeiner Medium-Kontext, nicht als Freigabe."}
        </p>
      </div>
    </div>
  );
}
