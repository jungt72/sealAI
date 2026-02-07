"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  getRagDocument,
  listRagDocuments,
  uploadRagDocument,
  type RagDocumentItem,
} from "@/lib/ragApi";

type Props = {
  token: string;
};

type TabKey = "documents" | "upload";

const fmtBytes = (n?: number | null) => {
  if (!n || n <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const digits = i === 0 ? 0 : i === 1 ? 1 : 2;
  return `${v.toFixed(digits)} ${units[i]}`;
};

const fmtDate = (s?: string | null) => {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
};

export default function RagAdminClient({ token }: Props) {
  const [tab, setTab] = useState<TabKey>("documents");

  // list
  const [items, setItems] = useState<RagDocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // filters
  const [limit, setLimit] = useState<number>(50);
  const [status, setStatus] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [visibility, setVisibility] = useState<string>("");

  // details
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsErr, setDetailsErr] = useState<string | null>(null);
  const [details, setDetails] = useState<RagDocumentItem | null>(null);

  // upload
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCategory, setUploadCategory] = useState<string>("");
  const [uploadTags, setUploadTags] = useState<string>("");
  const [uploadVisibility, setUploadVisibility] = useState<"private" | "public">(
    "private",
  );
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  const queryParams = useMemo(
    () => ({
      limit,
      status: status || undefined,
      category: category || undefined,
      visibility: visibility || undefined,
    }),
    [limit, status, category, visibility],
  );

  const refresh = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const res = await listRagDocuments(token, queryParams);
      setItems(res.items || []);
    } catch (e: any) {
      setErr(e?.message || "rag_list_failed");
    } finally {
      setLoading(false);
    }
  }, [token, queryParams]);

  const loadDetails = useCallback(
    async (documentId: string) => {
      setDetailsErr(null);
      setDetailsLoading(true);
      setDetails(null);
      try {
        const doc = await getRagDocument(token, documentId);
        setDetails(doc);
      } catch (e: any) {
        setDetailsErr(e?.message || "rag_document_failed");
      } finally {
        setDetailsLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    loadDetails(selectedId);
  }, [selectedId, loadDetails]);

  const onUpload = useCallback(async () => {
    if (!uploadFile) {
      setUploadMsg("Bitte Datei wählen.");
      return;
    }
    setUploadMsg(null);
    setUploading(true);
    try {
      const res = await uploadRagDocument(token, {
        file: uploadFile,
        category: uploadCategory || undefined,
        tags: uploadTags || undefined,
        visibility: uploadVisibility,
      });
      setUploadMsg(`Upload OK: ${res.document_id} (${res.status})`);
      setUploadFile(null);
      // nach Upload: zurück zu Documents + Refresh
      setTab("documents");
      await refresh();
    } catch (e: any) {
      setUploadMsg(e?.message || "rag_upload_failed");
    } finally {
      setUploading(false);
    }
  }, [
    token,
    uploadFile,
    uploadCategory,
    uploadTags,
    uploadVisibility,
    refresh,
  ]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">RAG Admin</h1>
          <p className="text-sm text-zinc-400">
            Hidden Admin-only Dashboard (Documents / Upload)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            className={`px-3 py-1.5 rounded-md text-sm border ${
              tab === "documents"
                ? "border-zinc-200/40 bg-zinc-200/10"
                : "border-zinc-200/20 hover:bg-zinc-200/5"
            }`}
            onClick={() => setTab("documents")}
            type="button"
          >
            Documents
          </button>
          <button
            className={`px-3 py-1.5 rounded-md text-sm border ${
              tab === "upload"
                ? "border-zinc-200/40 bg-zinc-200/10"
                : "border-zinc-200/20 hover:bg-zinc-200/5"
            }`}
            onClick={() => setTab("upload")}
            type="button"
          >
            Upload
          </button>
        </div>
      </div>

      {tab === "documents" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Limit</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-24"
                type="number"
                min={1}
                max={500}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 50)}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Status</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-40"
                placeholder="e.g. ready/failed/..."
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Category</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-40"
                placeholder="e.g. norms"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Visibility</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-40"
                placeholder="public/private"
                value={visibility}
                onChange={(e) => setVisibility(e.target.value)}
              />
            </div>

            <button
              className="px-3 py-2 rounded-md text-sm border border-zinc-200/20 hover:bg-zinc-200/5"
              onClick={() => refresh()}
              disabled={loading}
              type="button"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>

            {err && (
              <div className="text-sm text-red-300">
                {err}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <div className="border border-zinc-200/15 rounded-lg overflow-hidden">
                <div className="px-3 py-2 text-xs text-zinc-400 border-b border-zinc-200/10">
                  {items.length} items
                </div>

                <div className="overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-zinc-400">
                      <tr className="border-b border-zinc-200/10">
                        <th className="text-left px-3 py-2">Filename</th>
                        <th className="text-left px-3 py-2">Status</th>
                        <th className="text-left px-3 py-2">Visibility</th>
                        <th className="text-left px-3 py-2">Size</th>
                        <th className="text-left px-3 py-2">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it) => {
                        const isSel = selectedId === it.document_id;
                        return (
                          <tr
                            key={it.document_id}
                            className={`border-b border-zinc-200/5 hover:bg-zinc-200/5 cursor-pointer ${
                              isSel ? "bg-zinc-200/10" : ""
                            }`}
                            onClick={() => setSelectedId(it.document_id)}
                          >
                            <td className="px-3 py-2">
                              <div className="font-medium">
                                {it.filename || it.document_id}
                              </div>
                              <div className="text-xs text-zinc-500">
                                {it.document_id}
                              </div>
                            </td>
                            <td className="px-3 py-2">{it.status || "—"}</td>
                            <td className="px-3 py-2">
                              {it.visibility || "—"}
                            </td>
                            <td className="px-3 py-2">
                              {fmtBytes(it.size_bytes)}
                            </td>
                            <td className="px-3 py-2">
                              {fmtDate(it.updated_at)}
                            </td>
                          </tr>
                        );
                      })}

                      {items.length === 0 && !loading && (
                        <tr>
                          <td
                            className="px-3 py-6 text-zinc-500 text-center"
                            colSpan={5}
                          >
                            No documents found.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <p className="text-xs text-zinc-500 mt-2">
                Hinweis: Delete/Retry sind nicht verfügbar, da in{" "}
                <code className="text-zinc-300">ragApi.ts</code> keine Exporte
                dafür existieren.
              </p>
            </div>

            <div className="lg:col-span-1">
              <div className="border border-zinc-200/15 rounded-lg p-3 space-y-2">
                <div className="text-sm font-semibold">Details</div>

                {!selectedId && (
                  <div className="text-sm text-zinc-500">
                    Wähle ein Dokument aus der Liste.
                  </div>
                )}

                {selectedId && (
                  <>
                    {detailsLoading && (
                      <div className="text-sm text-zinc-500">
                        Loading…
                      </div>
                    )}
                    {detailsErr && (
                      <div className="text-sm text-red-300">
                        {detailsErr}
                      </div>
                    )}

                    {details && (
                      <div className="text-sm space-y-2">
                        <div>
                          <div className="text-xs text-zinc-400">ID</div>
                          <div className="break-all">{details.document_id}</div>
                        </div>

                        <div>
                          <div className="text-xs text-zinc-400">Filename</div>
                          <div>{details.filename || "—"}</div>
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <div className="text-xs text-zinc-400">Status</div>
                            <div>{details.status || "—"}</div>
                          </div>
                          <div>
                            <div className="text-xs text-zinc-400">Visibility</div>
                            <div>{details.visibility || "—"}</div>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <div className="text-xs text-zinc-400">Category</div>
                            <div>{details.category || "—"}</div>
                          </div>
                          <div>
                            <div className="text-xs text-zinc-400">Size</div>
                            <div>{fmtBytes(details.size_bytes)}</div>
                          </div>
                        </div>

                        <div>
                          <div className="text-xs text-zinc-400">Created</div>
                          <div>{fmtDate(details.created_at)}</div>
                        </div>

                        <div>
                          <div className="text-xs text-zinc-400">Updated</div>
                          <div>{fmtDate(details.updated_at)}</div>
                        </div>

                        {details.error && (
                          <div>
                            <div className="text-xs text-zinc-400">Error</div>
                            <div className="text-red-300 whitespace-pre-wrap">
                              {details.error}
                            </div>
                          </div>
                        )}

                        {details.ingest_stats && (
                          <div>
                            <div className="text-xs text-zinc-400">Ingest stats</div>
                            <pre className="text-xs bg-black/20 border border-zinc-200/10 rounded-md p-2 overflow-auto">
                              {JSON.stringify(details.ingest_stats, null, 2)}
                            </pre>
                          </div>
                        )}

                        <button
                          className="px-3 py-2 rounded-md text-sm border border-zinc-200/20 hover:bg-zinc-200/5"
                          onClick={() => loadDetails(details.document_id)}
                          type="button"
                        >
                          Reload details
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "upload" && (
        <div className="border border-zinc-200/15 rounded-lg p-4 space-y-4 max-w-2xl">
          <div className="text-sm font-semibold">Upload</div>

          <div className="space-y-2">
            <label className="block text-xs text-zinc-400">File</label>
            <input
              className="block w-full text-sm"
              type="file"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Category (optional)</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-full"
                value={uploadCategory}
                onChange={(e) => setUploadCategory(e.target.value)}
                placeholder="e.g. norms"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Tags (optional)</label>
              <input
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-full"
                value={uploadTags}
                onChange={(e) => setUploadTags(e.target.value)}
                placeholder="comma,separated,tags"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs text-zinc-400">Visibility</label>
              <select
                className="px-2 py-1 rounded-md bg-black/20 border border-zinc-200/20 text-sm w-full"
                value={uploadVisibility}
                onChange={(e) =>
                  setUploadVisibility(e.target.value as "private" | "public")
                }
              >
                <option value="private">private</option>
                <option value="public">public</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              className="px-3 py-2 rounded-md text-sm border border-zinc-200/20 hover:bg-zinc-200/5 disabled:opacity-60"
              onClick={() => onUpload()}
              disabled={uploading}
              type="button"
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
            {uploadMsg && (
              <div className="text-sm text-zinc-300">{uploadMsg}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
