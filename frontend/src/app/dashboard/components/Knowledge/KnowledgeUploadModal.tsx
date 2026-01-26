"use client";

import { useState } from "react";
import { uploadRagDocument } from "@/lib/ragApi";
import { useAccessToken } from "@/lib/useAccessToken";

type UploadResult = { document_id: string; status: string };

type KnowledgeUploadModalProps = {
  open: boolean;
  onClose: () => void;
  onUploaded: (result: UploadResult) => void;
};

export default function KnowledgeUploadModal({
  open,
  onClose,
  onUploaded,
}: KnowledgeUploadModalProps) {
  const { token } = useAccessToken();
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [visibility, setVisibility] = useState<"private" | "public">("public");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const reset = () => {
    setFile(null);
    setCategory("");
    setTags("");
    setVisibility("public");
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const nextFile = event.dataTransfer.files?.[0];
    if (nextFile) {
      setFile(nextFile);
    }
  };

  const handleSubmit = async () => {
    if (!token) {
      setError("Bitte erneut anmelden.");
      return;
    }
    if (!file) {
      setError("Bitte eine Datei auswählen.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await uploadRagDocument(token, {
        file,
        category: category.trim() || undefined,
        tags: tags.trim() || undefined,
        visibility,
      });
      onUploaded(result);
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_20px_60px_rgba(15,23,42,0.25)]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-emerald-700">
              Knowledge Base
            </div>
            <div className="text-lg font-bold text-slate-900">Upload</div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200"
          >
            Schließen
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <div className="text-xs font-semibold text-slate-600">Datei</div>
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              className={`mt-2 rounded-lg border border-dashed px-3 py-3 text-xs text-slate-600 ${
                dragActive ? "border-emerald-400 bg-emerald-50" : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span>{file ? file.name : "Datei hier ablegen oder auswählen"}</span>
                <label className="cursor-pointer rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-200">
                  Datei wählen
                  <input
                    type="file"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                    className="hidden"
                  />
                </label>
              </div>
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-600">Kategorie</div>
            <input
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="z.B. norms, materials"
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700"
            />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-600">Tags (comma)</div>
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="iso, din, nitril"
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700"
            />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-600">Sichtbarkeit</div>
            <select
              value={visibility}
              onChange={(event) => setVisibility(event.target.value as "private" | "public")}
              className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
            >
              <option value="private">privat</option>
              <option value="public">öffentlich</option>
            </select>
          </div>
        </div>

        {error ? (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
            {error}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2 text-xs font-semibold">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-full px-3 py-1 text-slate-500 hover:bg-slate-100"
            disabled={busy}
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy}
            className="rounded-full bg-emerald-600 px-3 py-1 text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "Upload…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
