import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRfqPreviewExportPdfBackendPath } from "@/lib/bff/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string; previewId: string }> },
) {
  try {
    const { previewId } = await context.params;
    const response = await fetchBackend(
      buildRfqPreviewExportPdfBackendPath(previewId),
      request,
      {
        method: "GET",
        headers: { Accept: "application/pdf" },
      },
    );
    const contentType = response.headers.get("Content-Type") || "";

    if (!response.ok || !contentType.includes("application/pdf")) {
      const body = await response.json().catch(() => null);
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        body?.error?.message ||
        `rfq_preview_export_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "rfq_preview_export_failed", message } },
        { status: response.status || 500 },
      );
    }

    const headers = new Headers();
    headers.set("Content-Type", "application/pdf");
    headers.set(
      "Content-Disposition",
      response.headers.get("Content-Disposition") ||
        `attachment; filename="sealai-rfq-${safeFileToken(previewId)}.pdf"`,
    );
    for (const header of [
      "X-SealAI-RFQ-Preview-ID",
      "X-SealAI-Dispatch-Allowed",
      "X-SealAI-External-Contact-Allowed",
      "X-SealAI-No-Final-Technical-Release",
    ]) {
      const value = response.headers.get(header);
      if (value) {
        headers.set(header, value);
      }
    }

    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers,
    });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      { error: { code: "rfq_preview_export_failed", message: "RFQ PDF export could not be generated." } },
      { status: 500 },
    );
  }
}

function safeFileToken(value: string): string {
  const token = value.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return token || "preview";
}
