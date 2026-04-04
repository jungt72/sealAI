import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";

export async function POST(
  request: Request,
  context: { params: Promise<{ documentId: string }> },
) {
  try {
    const { documentId } = await context.params;
    const response = await fetchBackend(`/api/v1/rag/documents/${encodeURIComponent(documentId)}/reingest`, request, {
      method: "POST",
    });
    const body = await response.text();

    return new Response(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json; charset=utf-8",
      },
    });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      { error: { code: "rag_request_failed", message: "RAG reingest failed." } },
      { status: 500 },
    );
  }
}
