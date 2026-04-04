import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(
      `/api/agent/chat/history/${encodeURIComponent(caseId)}`,
      request,
    );
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `history_fetch_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "history_fetch_failed", message } },
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
      { error: { code: "history_fetch_failed", message: "Chat history could not be loaded." } },
      { status: 500 },
    );
  }
}
