"use client";

import React, { useMemo, useState } from "react";
import { useContextState } from "../context/ContextStateProvider";
import type { ContextParameterKey } from "@/types/context";

const PARAM_LABELS: Record<ContextParameterKey, string> = {
  medium: "Medium",
  temperature: "Temperatur",
  pressure: "Druck",
  sealingType: "Dichtungstyp",
};

type EditorState = {
  key: ContextParameterKey | null;
  value: string;
};

function ContextTag({
  label,
  value,
  onEdit,
}: {
  label: string;
  value: string;
  onEdit: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onEdit}
      className="group flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-left shadow-sm transition hover:-translate-y-[1px] hover:border-emerald-300 hover:shadow-[0_12px_30px_rgba(16,185,129,0.16)]"
    >
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</div>
        <div className="text-sm font-semibold text-slate-900">{value || "—"}</div>
      </div>
      <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700 transition group-hover:bg-emerald-100">
        edit
      </span>
    </button>
  );
}

export default function ContextSidebar() {
  const { contextState, updateContext, resetContext } = useContextState();
  const [editor, setEditor] = useState<EditorState>({ key: null, value: "" });

  const tags = useMemo(
    () => [
      { key: "medium" as const, value: contextState.medium },
      { key: "temperature" as const, value: contextState.temperature },
      { key: "pressure" as const, value: contextState.pressure },
      { key: "sealingType" as const, value: contextState.sealingType },
    ],
    [contextState],
  );

  const startEdit = (key: ContextParameterKey, current: string) => {
    setEditor({ key, value: current });
  };

  const saveEdit = () => {
    if (!editor.key) return;
    updateContext({ [editor.key]: editor.value.trim() || "—" } as Record<string, string>);
    setEditor({ key: null, value: "" });
  };

  const cancelEdit = () => setEditor({ key: null, value: "" });

  return (
    <aside className="sticky top-4 flex h-fit min-w-[280px] max-w-[360px] flex-col gap-3 rounded-2xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-4 shadow-[0_18px_44px_rgba(15,23,42,0.12)]">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-emerald-700">Kontext</div>
          <div className="text-lg font-bold text-slate-900">Dichtungstechnologie</div>
        </div>
        <button
          type="button"
          onClick={resetContext}
          className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-slate-600 shadow-inner transition hover:bg-slate-100"
        >
          Reset
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {tags.map((tag) => (
          <ContextTag
            key={tag.key}
            label={PARAM_LABELS[tag.key]}
            value={tag.value}
            onEdit={() => startEdit(tag.key, tag.value)}
          />
        ))}
      </div>

      {editor.key ? (
        <div className="rounded-xl border border-emerald-200 bg-white px-3 py-3 shadow-sm">
          <div className="text-xs font-semibold text-emerald-800">
            {PARAM_LABELS[editor.key]} bearbeiten
          </div>
          <input
            className="mt-2 w-full rounded-lg border border-emerald-200 px-3 py-2 text-sm text-slate-900 outline-none ring-2 ring-transparent transition focus:border-emerald-400 focus:ring-emerald-100"
            value={editor.value}
            onChange={(e) => setEditor((prev) => ({ ...prev, value: e.target.value }))}
            autoFocus
          />
          <div className="mt-3 flex justify-end gap-2 text-xs font-semibold">
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-full px-3 py-1 text-slate-500 transition hover:bg-slate-100"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={saveEdit}
              className="rounded-full bg-emerald-600 px-3 py-1 text-white shadow-sm transition hover:bg-emerald-700"
            >
              Speichern
            </button>
          </div>
        </div>
      ) : null}

      {contextState.attachments.length ? (
        <div className="mt-1 space-y-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Uploads</div>
          <ul className="space-y-1 text-xs text-slate-700">
            {contextState.attachments.map((file) => (
              <li key={file.name} className="flex items-center justify-between gap-2 rounded-lg bg-white px-2 py-1 shadow-sm">
                <span className="truncate font-semibold">{file.name}</span>
                <span className="text-[11px] text-slate-500">{Math.round(file.size / 1024)} KB</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  );
}
