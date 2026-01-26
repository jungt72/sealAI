"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import type { RagDocumentItem } from "@/lib/ragApi";
import { deleteRagDocument, listRagDocuments, retryRagDocument } from "@/lib/ragApi";
import { useAccessToken } from "@/lib/useAccessToken";
import KnowledgeUploadModal from "./KnowledgeUploadModal";

type ExpandedMap = Record<string, boolean>;

const statusStyles: Record<string, string> = {
  queued: "bg-amber-50 text-amber-700 border-amber-200",
  processing: "bg-blue-50 text-blue-700 border-blue-200",
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
};

const formatSize = (size?: number | null): string => {
  if (!size) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (value?: string | null): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

export default function KnowledgeDocumentsPanel({ canManage = false }: { canManage?: boolean }) {
  const { token } = useAccessToken();
  const [items, setItems] = useState<RagDocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedMap>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});

  const hasActiveJobs = useMemo(
    () => items.some((doc) => ["queued", "processing"].includes(String(doc.status || ""))),
    [items],
  );

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listRagDocuments(token, { limit: 20 });
      setItems(response.items || []);
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

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const markBusy = (id: string, value: boolean) => {
    setBusyIds((prev) => ({ ...prev, [id]: value }));
  };

  const handleRetry = async (doc: RagDocumentItem) => {
    if (!token || !doc.document_id) return;
    markBusy(doc.document_id, true);
    try {
      await retryRagDocument(token, doc.document_id);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry fehlgeschlagen.");
    } finally {
      markBusy(doc.document_id, false);
    }
  };

  const handleDelete = async (doc: RagDocumentItem) => {
    if (!token || !doc.document_id) return;
    const confirmed = window.confirm("Dokument wirklich löschen?");
    if (!confirmed) return;
    markBusy(doc.document_id, true);
    try {
      await deleteRagDocument(token, doc.document_id);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    } finally {
      markBusy(doc.document_id, false);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
            Knowledge Base
          </div>
          <div className="text-base font-bold text-slate-900">Uploads</div>
        </div>
        {canManage ? (
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
          >
            Upload
          </button>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="mt-3">
        {loading ? (
          <div className="text-xs text-slate-500">Lade Dokumente …</div>
        ) : null}
        {!loading && items.length === 0 ? (
          <div className="text-xs text-slate-500">Noch keine Uploads.</div>
        ) : null}
        {items.length > 0 ? (
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Datei</th>
                  <th className="px-3 py-2">Sichtbarkeit</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Versuche</th>
                  <th className="px-3 py-2">Zeit</th>
                  <th className="px-3 py-2">Fehlerzeit</th>
                  <th className="px-3 py-2 text-right">Aktion</th>
                </tr>
              </thead>
              <tbody>
                {items.map((doc) => {
                  const badgeClass =
                    statusStyles[String(doc.status || "")] || "bg-slate-50 text-slate-600 border-slate-200";
                  const isOpen = expanded[doc.document_id];
                  const busy = busyIds[doc.document_id];
                  return (
                    <Fragment key={doc.document_id}>
                      <tr key={doc.document_id} className="border-t border-slate-200">
                        <td className="px-3 py-2">
                          <div className="font-semibold text-slate-900">
                            {doc.filename || doc.document_id}
                          </div>
                          <div className="text-[11px] text-slate-500">{doc.category || "—"}</div>
                        </td>
                        <td className="px-3 py-2">{doc.visibility || "private"}</td>
                        <td className="px-3 py-2">
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${badgeClass}`}>
                            {doc.status || "unknown"}
                          </span>
                        </td>
                        <td className="px-3 py-2">{doc.attempt_count ?? "—"}</td>
                        <td className="px-3 py-2">{formatDate(doc.updated_at || doc.created_at)}</td>
                        <td className="px-3 py-2">{formatDate(doc.failed_at)}</td>
                        <td className="px-3 py-2 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => toggleExpanded(doc.document_id)}
                              className="rounded-full px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-100"
                            >
                              {isOpen ? "Weniger" : "Details"}
                            </button>
                            {canManage ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() => handleRetry(doc)}
                                  disabled={busy || doc.status !== "failed"}
                                  className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  Retry
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDelete(doc)}
                                  disabled={busy}
                                  className="rounded-full bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  Delete
                                </button>
                              </>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                      {isOpen ? (
                        <tr className="border-t border-slate-100 bg-slate-50/60">
                          <td colSpan={7} className="px-3 py-3 text-[11px] text-slate-600">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-white px-2 py-0.5">{formatSize(doc.size_bytes)}</span>
                              {doc.tags?.length
                                ? doc.tags.map((tag) => (
                                    <span key={tag} className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
                                      {tag}
                                    </span>
                                  ))
                                : null}
                            </div>
                            {doc.error ? (
                              <div className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2 py-2 text-rose-700">
                                {doc.error}
                              </div>
                            ) : null}
                            {doc.ingest_stats ? (
                              <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-white px-2 py-2 text-[11px] text-slate-600">
                                {JSON.stringify(doc.ingest_stats, null, 2)}
                              </pre>
                            ) : null}
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {canManage ? (
        <KnowledgeUploadModal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onUploaded={() => loadDocuments()}
        />
      ) : null}
    </section>
  );
}
