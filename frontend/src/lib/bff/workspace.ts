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

export function buildRfqPreviewReadPath(caseId: string): string {
  return `/api/bff/rfq/${encodeURIComponent(caseId)}/preview`;
}

export function buildRfqPreviewBackendPath(caseId: string): string {
  return `/api/v1/rfq/preview?case_id=${encodeURIComponent(caseId)}`;
}

export function buildRfqPreviewConsentReadPath(caseId: string, previewId: string): string {
  return `/api/bff/rfq/${encodeURIComponent(caseId)}/preview/${encodeURIComponent(previewId)}/consent`;
}

export function buildRfqPreviewConsentBackendPath(previewId: string): string {
  return `/api/v1/rfq/preview/${encodeURIComponent(previewId)}/consent`;
}

export function buildRfqPreviewExportReadPath(caseId: string, previewId: string): string {
  return `/api/bff/rfq/${encodeURIComponent(caseId)}/preview/${encodeURIComponent(previewId)}/export`;
}

export function buildRfqPreviewExportPdfBackendPath(previewId: string): string {
  return `/api/v1/rfq/preview/${encodeURIComponent(previewId)}/export.pdf`;
}

export function buildRwdrAnalyzeReadPath(): string {
  return "/api/bff/rfq/rwdr/analyze";
}

export function buildRwdrAnalyzeBackendPath(): string {
  return "/api/v1/rfq/rwdr/analyze";
}

export function buildRwdrBriefReadPath(): string {
  return "/api/bff/rfq/rwdr/brief";
}

export function buildRwdrBriefBackendPath(): string {
  return "/api/v1/rfq/rwdr/brief";
}

export function buildRwdrCaseReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}`;
}

export function buildRwdrCaseBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}`;
}

export function buildRwdrConfirmationsReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/confirmations`;
}

export function buildRwdrConfirmationsBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/confirmations`;
}

export function buildRwdrCaseBriefReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/brief`;
}

export function buildRwdrCaseBriefBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/brief`;
}

export function buildRwdrCaseExportReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/export`;
}

export function buildRwdrCaseExportBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/export.md`;
}

export function buildRwdrCasePdfReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/export.pdf`;
}

export function buildRwdrCasePdfBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/export.pdf`;
}

export function buildRwdrCaseSnapshotsReadPath(caseId: string): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/snapshots`;
}

export function buildRwdrCaseSnapshotsBackendPath(caseId: string): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/snapshots`;
}

export function buildRwdrCaseDiffReadPath(caseId: string, fromRevision: number, toRevision: number): string {
  return `/api/bff/rfq/rwdr/cases/${encodeURIComponent(caseId)}/diff/${encodeURIComponent(String(fromRevision))}/${encodeURIComponent(String(toRevision))}`;
}

export function buildRwdrCaseDiffBackendPath(caseId: string, fromRevision: number, toRevision: number): string {
  return `/api/v1/rfq/rwdr/cases/${encodeURIComponent(caseId)}/diff/${encodeURIComponent(String(fromRevision))}/${encodeURIComponent(String(toRevision))}`;
}

export async function fetchWorkspace(caseId: string): Promise<WorkspaceView> {
  const response = await fetch(buildWorkspaceReadPath(caseId), {
    cache: "no-store",
  });
  return ensureJson<WorkspaceView>(response);
}

export async function submitRfq(caseId: string, payload: unknown): Promise<never> {
  void caseId;
  void payload;
  throw new Error(
    "Legacy RFQ document submission is disabled. Use the governed RFQ preview/export flow; consent required before export.",
  );
}
