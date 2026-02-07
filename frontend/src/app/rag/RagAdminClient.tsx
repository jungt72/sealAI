"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RagDocumentItem } from "@/lib/ragApi";
import { deleteRagDocument, listRagDocuments, retryRagDocument, uploadRagDocument } from "@/lib/ragApi";

type RagAdminClientProps = {
  token: string;
};

type TabKey = "documents" | "upload";

const formatDate = (value?: string | null): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatSize = (value?: number | null): string => {
  if (typeof value !== "number") return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

export default function RagAdminClient({ token }: RagAdminClientProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("documents");
  const [items, setItems] = useState<RagDocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCategory, setUploadCategory] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadVisibility, setUploadVisibility] = useState<"private" | "public">("public");

  const hasActiveJobs = useMemo(
    () => items.some((doc) => ["queued", "processing"].includes(String(doc.status ?? ""))),
    [items],
  );

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listRagDocuments(token, { limit: 50 });
      const nextItems = Array.isArray(response?.items) ? response.items : [];
      setItems(nextItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Laden fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!hasActiveJobs) return;
    const id = window.setInterval(() => {
      loadDocuments();
    }, 3000);
    return () => window.clearInterval(id);
  }, [hasActiveJobs, loadDocuments]);

  const markBusy = (docId: string, value: boolean) => {
    setBusyIds((prev) => ({ ...prev, [docId]: value }));
  };

  const handleRetry = async (doc: RagDocumentItem) => {
    const docId = doc?.document_id;
    if (!docId) return;
    markBusy(docId, true);
    setError(null);
    try {
      await retryRagDocument(token, docId);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry fehlgeschlagen.");
    } finally {
      markBusy(docId, false);
    }
  };

  const handleDelete = async (doc: RagDocumentItem) => {
    const docId = doc?.document_id;
    if (!docId) return;
    const confirmed = window.confirm("Dokument wirklich löschen?");
    if (!confirmed) return;
    markBusy(docId, true);
    setError(null);
    try {
      await deleteRagDocument(token, docId);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    } finally {
      markBusy(docId, false);
    }
  };

  const resetUpload = () => {
    setUploadFile(null);
    setUploadCategory("");
    setUploadTags("");
    setUploadVisibility("public");
    setUploadError(null);
  };

  const handleUpload = async () => {
    if (!uploadFile) {
      setUploadError("Bitte eine Datei auswählen.");
      return;
    }
    setUploadBusy(true);
    setUploadError(null);
    try {
      await uploadRagDocument(token, {
        file: uploadFile,
        category: uploadCategory.trim() || undefined,
        tags: uploadTags.trim() || undefined,
        visibility: uploadVisibility,
      });
      resetUpload();
      setActiveTab("documents");
      await loadDocuments();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setUploadBusy(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">RAG Admin</div>
          <h1 className="text-2xl font-semibold text-slate-900">Knowledge Documents</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("documents")}
            className={`rounded-full px-4 py-1 text-xs font-semibold ${
              activeTab === "documents" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
            }`}
          >
            Documents
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("upload")}
            className={`rounded-full px-4 py-1 text-xs font-semibold ${
              activeTab === "upload" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
            }`}
          >
            Upload
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      {activeTab === "documents" ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold text-slate-700">Documents</div>
            <button
              type="button"
              onClick={() => loadDocuments()}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200"
            >
              Refresh
            </button>
          </div>

          <div className="mt-3">
            {loading ? <div className="text-xs text-slate-500">Lade Dokumente …</div> : null}
            {!loading && items.length === 0 ? (
              <div className="text-xs text-slate-500">Keine Dokumente gefunden.</div>
            ) : null}
            {items.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Datei</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Größe</th>
                      <th className="px-3 py-2">Updated</th>
                      <th className="px-3 py-2 text-right">Aktion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((doc, index) => {
                      const docId = doc.document_id || `doc-${index}`;
                      const busy = doc.document_id ? busyIds[doc.document_id] : false;
                      const label = doc.filename || doc.document_id || "Unbekannt";
                      return (
                        <tr key={docId} className="border-t border-slate-200">
                          <td className="px-3 py-2">
                            <div className="font-semibold text-slate-900">{label}</div>
                            <div className="text-[11px] text-slate-500">
                              {doc.category || "—"} · {doc.visibility || "—"}
                            </div>
                          </td>
                          <td className="px-3 py-2">{doc.status || "—"}</td>
                          <td className="px-3 py-2">{formatSize(doc.size_bytes)}</td>
                          <td className="px-3 py-2">{formatDate(doc.updated_at || doc.created_at)}</td>
                          <td className="px-3 py-2 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => handleRetry(doc)}
                                disabled={busy || !doc.document_id}
                                className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Retry
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDelete(doc)}
                                disabled={busy || !doc.document_id}
                                className="rounded-full bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {activeTab === "upload" ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-700">Upload</div>
            <button
              type="button"
              onClick={resetUpload}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200"
            >
              Reset
            </button>
          </div>

          <div className="mt-4 grid gap-3 text-sm text-slate-700">
            <label className="grid gap-2">
              <span className="text-xs font-semibold text-slate-500">Datei</span>
              <input
                type="file"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
              <div className="text-xs text-slate-500">{uploadFile?.name || "Keine Datei gewählt."}</div>
            </label>

            <label className="grid gap-2">
              <span className="text-xs font-semibold text-slate-500">Kategorie</span>
              <input
                value={uploadCategory}
                onChange={(event) => setUploadCategory(event.target.value)}
                placeholder="z.B. norms, materials"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>

            <label className="grid gap-2">
              <span className="text-xs font-semibold text-slate-500">Tags (comma)</span>
              <input
                value={uploadTags}
                onChange={(event) => setUploadTags(event.target.value)}
                placeholder="iso, din, nitril"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </label>

            <label className="grid gap-2">
              <span className="text-xs font-semibold text-slate-500">Sichtbarkeit</span>
              <select
                value={uploadVisibility}
                onChange={(event) => setUploadVisibility(event.target.value as "private" | "public")}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <option value="private">privat</option>
                <option value="public">öffentlich</option>
              </select>
            </label>
          </div>

          {uploadError ? (
            <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
              {uploadError}
            </div>
          ) : null}

          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={handleUpload}
              disabled={uploadBusy}
              className="rounded-full bg-emerald-600 px-4 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {uploadBusy ? "Upload…" : "Upload"}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("documents")}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-200"
            >
              Zurück
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
