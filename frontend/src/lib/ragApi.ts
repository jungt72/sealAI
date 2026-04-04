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

export type RagHealthCheck = {
  document_id: string;
  tenant_id: string;
  status: string;
  collection: string;
  filesystem: {
    path: string;
    exists: boolean;
  };
  qdrant: {
    points: number;
    error?: string | null;
  };
  is_consistent: boolean;
  issues: string[];
};

async function bffFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`rag_request_failed:${res.status}:${body || ""}`);
  }
  if (res.status === 204) {
    return {} as T;
  }
  return (await res.json()) as T;
}

export async function listRagDocuments(
  params: { limit?: number; status?: string } = {},
): Promise<{ items: RagDocumentItem[] }> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.status) search.set("status", params.status);
  const query = search.toString();
  return bffFetch<{ items: RagDocumentItem[] }>(
    `/api/bff/rag/documents${query ? `?${query}` : ""}`,
  );
}

export async function healthCheckRagDocument(
  documentId: string,
): Promise<RagHealthCheck> {
  return bffFetch<RagHealthCheck>(`/api/bff/rag/documents/${documentId}/health-check`);
}

export async function reingestRagDocument(
  documentId: string,
): Promise<{ document_id: string; status: string }> {
  return bffFetch<{ document_id: string; status: string }>(
    `/api/bff/rag/documents/${documentId}/reingest`,
    { method: "POST" },
  );
}

export async function deleteRagDocument(
  documentId: string,
): Promise<{ document_id: string; deleted: boolean }> {
  return bffFetch<{ document_id: string; deleted: boolean }>(
    `/api/bff/rag/documents/${documentId}`,
    { method: "DELETE" },
  );
}

export async function uploadRagDocument(
  file: File,
  params: { category?: string; tags?: string; visibility?: "private" | "public" } = {},
): Promise<{ document_id: string; status: string }> {
  const formData = new FormData();
  formData.append("file", file);
  if (params.category) formData.append("category", params.category);
  if (params.tags) formData.append("tags", params.tags);
  if (params.visibility) formData.append("visibility", params.visibility);

  return bffFetch<{ document_id: string; status: string }>(
    "/api/bff/rag/documents",
    {
      method: "POST",
      body: formData,
    },
  );
}
