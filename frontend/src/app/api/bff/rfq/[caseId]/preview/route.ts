import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import {
  buildRfqPreviewBackendPath,
} from "@/lib/bff/workspace";

function friendlyPreviewMessage(status: number, message: string) {
  if (status === 404 || message.includes("rfq_preview_case_not_found") || message.includes("case not found")) {
    return "RFQ-Preview kann erst vorbereitet werden, wenn der Fall als Case-Revision im Backend gespeichert ist.";
  }
  return message;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildRfqPreviewBackendPath(caseId), request);
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `rfq_preview_fetch_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "rfq_preview_fetch_failed", message: friendlyPreviewMessage(response.status, message) } },
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
      { error: { code: "rfq_preview_fetch_failed", message: "RFQ preview could not be loaded." } },
      { status: 500 },
    );
  }
}

export async function POST(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildRfqPreviewBackendPath(caseId), request, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "create_preview",
        explicit_user_intent: true,
        dispatch_allowed: false,
        external_contact_allowed: false,
      }),
    });
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `rfq_preview_create_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "rfq_preview_create_failed", message: friendlyPreviewMessage(response.status, message) } },
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
      { error: { code: "rfq_preview_create_failed", message: "RFQ preview could not be created." } },
      { status: 500 },
    );
  }
}
