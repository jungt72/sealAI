import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRfqPreviewConsentBackendPath } from "@/lib/bff/workspace";

export async function POST(
  request: Request,
  context: { params: Promise<{ caseId: string; previewId: string }> },
) {
  try {
    const { previewId } = await context.params;
    const response = await fetchBackend(buildRfqPreviewConsentBackendPath(previewId), request, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: await request.text(),
    });
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `rfq_preview_consent_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "rfq_preview_consent_failed", message } },
        { status: response.status || 500 },
      );
    }

    return NextResponse.json(body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      { error: { code: "rfq_preview_consent_failed", message: "RFQ preview consent could not be saved." } },
      { status: 500 },
    );
  }
}
