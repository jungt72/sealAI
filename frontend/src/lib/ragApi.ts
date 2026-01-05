import { fetchWithAuth } from "@/lib/fetchWithAuth";
import { backendBaseUrl } from "@/lib/langgraphApi";

export type RagDocumentItem = {
  document_id: string;
  filename?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  category?: string | null;
  tags?: string[] | null;
  visibility?: string | null;
  status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  ingest_stats?: Record<string, unknown> | null;
  error?: string | null;
};

type ListParams = {
  limit?: number;
  status?: string;
  category?: string;
  visibility?: string;
};

const buildQuery = (params: ListParams = {}): string => {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.status) search.set("status", params.status);
  if (params.category) search.set("category", params.category);
  if (params.visibility) search.set("visibility", params.visibility);
  const query = search.toString();
  return query ? `?${query}` : "";
};

export async function listRagDocuments(
  token: string,
  params: ListParams = {},
): Promise<{ items: RagDocumentItem[] }> {
  const res = await fetchWithAuth(`/api/rag/documents${buildQuery(params)}`, token);
  if (!res.ok) {
    throw new Error(`rag_list_failed:${res.status}`);
  }
  return (await res.json()) as { items: RagDocumentItem[] };
}

export async function uploadRagDocument(
  token: string,
  payload: {
    file: File;
    category?: string;
    tags?: string;
    visibility?: "private" | "public";
  },
): Promise<{ document_id: string; status: string }> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.category) formData.append("category", payload.category);
  if (payload.tags) formData.append("tags", payload.tags);
  if (payload.visibility) formData.append("visibility", payload.visibility);
  const res = await fetchWithAuth("/api/rag/upload", token, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`rag_upload_failed:${res.status}`);
  }
  return (await res.json()) as { document_id: string; status: string };
}

export async function getRagDocument(
  token: string,
  documentId: string,
): Promise<RagDocumentItem> {
  const res = await fetchWithAuth(`${backendBaseUrl()}/api/v1/rag/documents/${documentId}`, token);
  if (!res.ok) {
    throw new Error(`rag_document_failed:${res.status}`);
  }
  return (await res.json()) as RagDocumentItem;
}
