"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useSession } from "next-auth/react";
import {
  deleteRagDocument,
  healthCheckRagDocument,
  listRagDocuments,
  reingestRagDocument,
  syncPaperless,
  uploadRagDocument,
  type RagDocumentItem,
  type RagHealthCheck,
} from "@/lib/ragApi";

type HealthMap = Record<string, RagHealthCheck | undefined>;
type BusyMap = Record<string, boolean>;
type ToastVariant = "info" | "success" | "error";

type ToastState = {
  message: string;
  variant: ToastVariant;
  storagePermissionHint?: boolean;
};

function normalizeStatus(raw?: string | null): "processing" | "indexed" | "error" | "unknown" {
  const value = String(raw || "").toLowerCase();
  if (value === "queued" || value === "processing") return "processing";
  if (value === "done" || value === "indexed") return "indexed";
  if (value === "failed" || value === "error") return "error";
  return "unknown";
}

function formatBytes(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function extractChunkCount(doc: RagDocumentItem, health?: RagHealthCheck): string {
  const stats = doc.ingest_stats;
  if (stats && typeof stats === "object") {
    const chunks = (stats as Record<string, unknown>).chunks;
    if (typeof chunks === "number") {
      return String(chunks);
    }
  }
  if (typeof health?.qdrant?.points === "number") {
    return String(health.qdrant.points);
  }
  return "-";
}

const statusClass: Record<string, string> = {
  processing: "text-amber-300 bg-amber-500/10 border-amber-300/25",
  indexed: "text-emerald-300 bg-emerald-500/10 border-emerald-300/25",
  error: "text-rose-300 bg-rose-500/10 border-rose-300/25",
  unknown: "text-slate-300 bg-slate-500/10 border-slate-300/25",
};

const dotClass: Record<string, string> = {
  processing: "bg-amber-300 animate-pulse",
  indexed: "bg-emerald-300",
  error: "bg-rose-300",
  unknown: "bg-slate-300",
};

export default function RagDocumentGrid() {
  const { data: session } = useSession();
  const token = (session as { accessToken?: string } | null)?.accessToken;

  const [documents, setDocuments] = useState<RagDocumentItem[]>([]);
  const [healthById, setHealthById] = useState<HealthMap>({});
  const [busyById, setBusyById] = useState<BusyMap>({});
  const [uploading, setUploading] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const toastTimeoutRef = useRef<number | null>(null);

  const withBusy = (documentId: string, next: boolean) => {
    setBusyById((prev) => ({ ...prev, [documentId]: next }));
  };

  const showToast = useCallback(
    (
      message: string,
      variant: ToastVariant,
      durationMs = 3500,
      options: { storagePermissionHint?: boolean } = {},
    ) => {
      if (toastTimeoutRef.current) {
        window.clearTimeout(toastTimeoutRef.current);
        toastTimeoutRef.current = null;
      }
      setToast({ message, variant, storagePermissionHint: options.storagePermissionHint });
      if (durationMs > 0) {
        toastTimeoutRef.current = window.setTimeout(() => {
          setToast(null);
          toastTimeoutRef.current = null;
        }, durationMs);
      }
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        window.clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const list = await listRagDocuments(token, { limit: 100 });
      const docs = list.items || [];
      setDocuments(docs);

      const checks = await Promise.all(
        docs.map(async (doc) => {
          try {
            const health = await healthCheckRagDocument(token, doc.document_id);
            return [doc.document_id, health] as const;
          } catch {
            return [doc.document_id, undefined] as const;
          }
        }),
      );

      const nextMap: HealthMap = {};
      for (const [id, health] of checks) {
        nextMap[id] = health;
      }
      setHealthById(nextMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RAG-Dokumente konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasActiveItems = useMemo(
    () => documents.some((doc) => normalizeStatus(doc.status) === "processing"),
    [documents],
  );

  useEffect(() => {
    if (!hasActiveItems) return;
    const id = window.setInterval(() => {
      refresh();
    }, 3000);
    return () => window.clearInterval(id);
  }, [hasActiveItems, refresh]);

  const handleSyncPaperless = async () => {
    if (!token) return;
    setSyncing(true);
    setError(null);
    showToast("Syncing Paperless...", "info", 0);
    try {
      const result = await syncPaperless(token);
      if (result.error) {
        throw new Error(result.error);
      }
      showToast(
        `Sync successful! Scanned: ${result.scanned}, Queued: ${result.queued}, Skipped: ${result.skipped}`,
        "success",
        6000,
      );
      await refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Paperless-Sync fehlgeschlagen.";
      setError(msg);
      showToast(msg, "error", 6000);
    } finally {
      setSyncing(false);
    }
  };

  const handleReingest = async (documentId: string) => {
    if (!token) return;
    withBusy(documentId, true);
    setError(null);
    try {
      await reingestRagDocument(token, documentId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-Ingest fehlgeschlagen.");
    } finally {
      withBusy(documentId, false);
    }
  };

  const handleDelete = async (documentId: string, filename?: string | null) => {
    if (!token) return;
    const display = filename || documentId;
    if (!window.confirm(`Dokument wirklich löschen?\n${display}`)) return;

    withBusy(documentId, true);
    setError(null);
    try {
      await deleteRagDocument(token, documentId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    } finally {
      withBusy(documentId, false);
    }
  };

  const handleUploadFiles = useCallback(
    async (incomingFiles: FileList | File[]) => {
      if (!token) return;
      const files = Array.from(incomingFiles || []);
      if (files.length === 0) return;

      setUploading(true);
      setError(null);
      showToast("Uploading...", "info", 0);
      try {
        let uploaded = 0;
        for (const file of files) {
          await uploadRagDocument(token, file);
          uploaded += 1;
        }
        if (uploaded > 0) {
          await refresh();
          showToast("Upload successful! Processing started.", "success", 4500);
        }
      } catch (err) {
        const rawMessage = err instanceof Error ? err.message : "Upload fehlgeschlagen.";
        const lowerMessage = rawMessage.toLowerCase();
        const status500 = lowerMessage.includes("rag_request_failed:500:");
        const isStoragePermissionError =
          (status500 && lowerMessage.includes("storage permission denied")) ||
          (lowerMessage.includes("storage") && lowerMessage.includes("permission denied"));
        const uploadErrorMessage = isStoragePermissionError
          ? "Server Storage Error: Please check VPS permissions."
          : rawMessage;
        setError(uploadErrorMessage);
        showToast(uploadErrorMessage, "error", 6000, {
          storagePermissionHint: isStoragePermissionError,
        });
      } finally {
        setUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [refresh, token],
  );

  const handleInputChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    await handleUploadFiles(files);
  };

  const handleDrop = async (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
    if (uploading) return;
    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) return;
    await handleUploadFiles(files);
  };

  if (!token) {
    return (
      <section className="rounded-3xl border border-white/10 bg-white/5 p-6 text-sm text-slate-300 backdrop-blur">
        Anmeldung erforderlich, um das RAG-Dokumenten-Dashboard zu laden.
      </section>
    );
  }

  return (
    <section>
      {toast ? (
        <div className="fixed right-4 top-4 z-50">
          <div
            className={`max-w-sm rounded-xl border px-4 py-3 text-sm font-semibold shadow-lg backdrop-blur transition-all duration-300 ${
              toast.variant === "success"
                ? "border-emerald-300/40 bg-emerald-600/90 text-white"
                : toast.variant === "error"
                  ? "border-rose-300/40 bg-rose-600/90 text-white"
                  : "border-slate-200/40 bg-slate-700/90 text-white"
            }`}
          >
            <div>{toast.message}</div>
            {toast.storagePermissionHint ? (
              <details className="mt-2 text-xs font-medium text-white/95">
                <summary className="inline-flex cursor-pointer items-center rounded-full border border-white/35 px-2 py-1 hover:bg-white/10">
                  Info
                </summary>
                <p className="mt-2 leading-relaxed text-white/90">
                  Der Server kann nicht in `/app/data/uploads` schreiben. Bitte VPS-Verzeichnisrechte
                  und Ownership prufen (z. B. `chmod/chown`).
                </p>
              </details>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-200/80">RAG Management</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-white">Document Grid</h1>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleSyncPaperless}
            className="rounded-full border border-sky-300/40 bg-sky-600/20 px-4 py-2 text-xs font-semibold text-sky-100 transition hover:bg-sky-600/30 disabled:cursor-wait disabled:opacity-50"
            disabled={syncing}
          >
            {syncing ? "Syncing..." : "Sync Paperless"}
          </button>
          <button
            type="button"
            onClick={refresh}
            className="rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs font-semibold text-white transition hover:bg-white/20"
            disabled={loading}
          >
            {loading ? "Aktualisieren..." : "Refresh"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mb-4 rounded-2xl border border-rose-300/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      <div className="mb-6">
        <input
          ref={fileInputRef}
          type="file"
          className="sr-only"
          id="rag-upload-input"
          onChange={handleInputChange}
          multiple
          disabled={uploading}
          accept=".pdf,.txt,.md,.docx"
        />
        <label
          htmlFor="rag-upload-input"
          onDragOver={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!uploading) setIsDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setIsDragActive(false);
          }}
          onDrop={handleDrop}
          className={`group flex cursor-pointer items-center justify-between gap-4 rounded-2xl border px-4 py-3 backdrop-blur-xl transition ${
            uploading
              ? "cursor-wait border-slate-400/30 bg-slate-500/10"
              : isDragActive
                ? "border-sky-300/60 bg-sky-400/10"
                : "border-white/15 bg-white/5 hover:border-white/30 hover:bg-white/10"
          }`}
        >
          <div>
            <p className="text-sm font-semibold text-white">Upload Documents</p>
            <p className="text-xs text-slate-300">Drop files here or click to browse</p>
          </div>
          <span className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-100">
            {uploading ? "Uploading..." : "Choose Files"}
          </span>
        </label>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {documents.map((doc) => {
          const health = healthById[doc.document_id];
          const normalized = normalizeStatus(doc.status);
          const busy = Boolean(busyById[doc.document_id]);
          const syncIssue = health ? !health.is_consistent : false;

          return (
            <article
              key={doc.document_id}
              className="group relative overflow-hidden rounded-[28px] border border-white/15 bg-[linear-gradient(160deg,rgba(255,255,255,0.14)_0%,rgba(255,255,255,0.04)_45%,rgba(2,6,23,0.28)_100%)] p-5 shadow-[0_20px_80px_rgba(8,15,35,0.42)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-[0_22px_90px_rgba(8,15,35,0.52)]"
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-white">{doc.filename || doc.document_id}</p>
                  <p className="mt-1 truncate text-xs text-slate-300">{doc.document_id}</p>
                </div>
                <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-medium ${statusClass[normalized]}`}>
                  <span className={`h-2.5 w-2.5 rounded-full ${dotClass[normalized]}`} />
                  {normalized}
                </span>
              </div>

              <dl className="space-y-2 text-xs text-slate-200/90">
                <div className="flex justify-between gap-4">
                  <dt>Size</dt>
                  <dd>{formatBytes(doc.size_bytes)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>Date</dt>
                  <dd className="text-right">{formatDate(doc.updated_at || doc.created_at)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>Chunks</dt>
                  <dd>{extractChunkCount(doc, health)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt>Qdrant</dt>
                  <dd>{typeof health?.qdrant?.points === "number" ? health.qdrant.points : "-"}</dd>
                </div>
              </dl>

              {syncIssue ? (
                <div className="mt-4 rounded-xl border border-amber-300/35 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
                  Sync-Warnung: {health?.issues.join(", ")}
                </div>
              ) : null}

              {doc.error ? (
                <div className="mt-4 rounded-xl border border-rose-300/35 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-100">
                  {doc.error}
                </div>
              ) : null}

              <div className="mt-5 flex gap-2">
                <button
                  type="button"
                  onClick={() => handleReingest(doc.document_id)}
                  disabled={busy}
                  className="flex-1 rounded-full border border-sky-300/35 bg-sky-500/10 px-3 py-2 text-xs font-semibold text-sky-100 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Re-Ingest
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(doc.document_id, doc.filename)}
                  disabled={busy}
                  className="flex-1 rounded-full border border-rose-300/35 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Delete
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {!loading && documents.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-white/15 bg-white/5 px-5 py-6 text-sm text-slate-300 backdrop-blur">
          Keine Dokumente gefunden.
        </div>
      ) : null}
    </section>
  );
}
