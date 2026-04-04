import type { WorkspaceView } from "@/lib/contracts/workspace";

async function ensureJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const fallback = `workspace_request_failed:${response.status}`;
    const body = await response.json().catch(() => ({}));
    const message =
      body?.error?.message ||
      body?.detail?.message ||
      body?.detail?.code ||
      fallback;
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function buildWorkspaceReadPath(caseId: string): string {
  return `/api/bff/workspace/${encodeURIComponent(caseId)}`;
}

export function buildWorkspaceBackendReadPath(caseId: string): string {
  return `/api/agent/workspace/${encodeURIComponent(caseId)}`;
}

export function buildRfqDocumentReadPath(caseId: string): string {
  return `/api/bff/rfq/${encodeURIComponent(caseId)}/document`;
}

export function buildRfqDocumentBackendReadPath(caseId: string): string {
  return `${buildWorkspaceBackendReadPath(caseId)}/rfq-document`;
}

export async function fetchWorkspace(caseId: string): Promise<WorkspaceView> {
  const response = await fetch(buildWorkspaceReadPath(caseId), {
    cache: "no-store",
  });
  return ensureJson<WorkspaceView>(response);
}
