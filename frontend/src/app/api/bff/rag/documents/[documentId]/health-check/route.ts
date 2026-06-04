import { NextResponse } from "next/server";

import { ragPassthroughResponse } from "@/lib/bff/ragResponse";
import { BffError, fetchBackend } from "@/lib/bff/http";

export async function GET(
  request: Request,
  context: { params: Promise<{ documentId: string }> },
) {
  try {
    const { documentId } = await context.params;
    const response = await fetchBackend(`/api/v1/rag/documents/${encodeURIComponent(documentId)}/health-check`, request);
    const body = await response.text();

    return ragPassthroughResponse(response, body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      { error: { code: "rag_request_failed", message: "RAG health check failed." } },
      { status: 500 },
    );
  }
}
