"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RagDocumentItem } from "@/lib/ragApi";
import { listRagDocuments } from "@/lib/ragApi";
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

export default function KnowledgeDocumentsPanel() {
  const { token } = useAccessToken();
  const [items, setItems] = useState<RagDocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedMap>({});
  const [modalOpen, setModalOpen] = useState(false);

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

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
            Knowledge Base
          </div>
          <div className="text-base font-bold text-slate-900">Uploads</div>
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
        >
          Upload
        </button>
      </div>

      {error ? (
        <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="mt-3 space-y-2">
        {loading ? (
          <div className="text-xs text-slate-500">Lade Dokumente …</div>
        ) : null}
        {!loading && items.length === 0 ? (
          <div className="text-xs text-slate-500">Noch keine Uploads.</div>
        ) : null}
        {items.map((doc) => {
          const badgeClass = statusStyles[String(doc.status || "")] || "bg-slate-50 text-slate-600 border-slate-200";
          const isOpen = expanded[doc.document_id];
          return (
            <div key={doc.document_id} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              <button
                type="button"
                onClick={() => toggleExpanded(doc.document_id)}
                className="flex w-full items-center justify-between text-left"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900">
                    {doc.filename || doc.document_id}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                    <span>{doc.category || "—"}</span>
                    <span>•</span>
                    <span>{formatDate(doc.updated_at || doc.created_at)}</span>
                  </div>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${badgeClass}`}>
                  {doc.status || "unknown"}
                </span>
              </button>

              {isOpen ? (
                <div className="mt-3 space-y-2 text-xs text-slate-600">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">{doc.visibility || "private"}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">{formatSize(doc.size_bytes)}</span>
                  </div>
                  {doc.tags?.length ? (
                    <div className="flex flex-wrap gap-2">
                      {doc.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {doc.ingest_stats ? (
                    <pre className="whitespace-pre-wrap rounded-lg bg-white px-2 py-2 text-[11px] text-slate-600">
                      {JSON.stringify(doc.ingest_stats, null, 2)}
                    </pre>
                  ) : null}
                  {doc.error ? (
                    <div className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-2 text-[11px] text-rose-700">
                      {doc.error}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <KnowledgeUploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onUploaded={() => loadDocuments()}
      />
    </section>
  );
}
