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

function resolveApiUrl(path: string): string {
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!apiBase || apiBase.startsWith("http://backend")) {
    return path;
  }
  return `${apiBase}${path}`;
}

async function authFetch<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(resolveApiUrl(path), {
    ...init,
    headers: {
      ...(init.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
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
  token: string,
  params: { limit?: number; status?: string } = {},
): Promise<{ items: RagDocumentItem[] }> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.status) search.set("status", params.status);
  const query = search.toString();
  return authFetch<{ items: RagDocumentItem[] }>(
    `/api/v1/rag/documents${query ? `?${query}` : ""}`,
    token,
  );
}

export async function healthCheckRagDocument(
  token: string,
  documentId: string,
): Promise<RagHealthCheck> {
  return authFetch<RagHealthCheck>(
    `/api/v1/rag/documents/${documentId}/health-check`,
    token,
  );
}

export async function reingestRagDocument(
  token: string,
  documentId: string,
): Promise<{ document_id: string; status: string }> {
  return authFetch<{ document_id: string; status: string }>(
    `/api/v1/rag/documents/${documentId}/reingest`,
    token,
    { method: "POST" },
  );
}

export async function deleteRagDocument(
  token: string,
  documentId: string,
): Promise<{ document_id: string; deleted: boolean }> {
  return authFetch<{ document_id: string; deleted: boolean }>(
    `/api/v1/rag/documents/${documentId}`,
    token,
    { method: "DELETE" },
  );
}

export async function uploadRagDocument(
  token: string,
  file: File,
  params: { category?: string; tags?: string; visibility?: "private" | "public" } = {},
): Promise<{ document_id: string; status: string }> {
  const formData = new FormData();
  formData.append("file", file);
  if (params.category) formData.append("category", params.category);
  if (params.tags) formData.append("tags", params.tags);
  if (params.visibility) formData.append("visibility", params.visibility);

  return authFetch<{ document_id: string; status: string }>(
    "/api/v1/rag/upload",
    token,
    {
      method: "POST",
      body: formData,
    },
  );
}
