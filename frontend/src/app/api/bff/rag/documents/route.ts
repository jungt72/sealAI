import { NextResponse } from "next/server";

import { ragPassthroughResponse } from "@/lib/bff/ragResponse";
import { BffError, fetchBackend } from "@/lib/bff/http";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const search = url.searchParams.toString();
    const response = await fetchBackend(`/api/v1/rag/documents${search ? `?${search}` : ""}`, request);
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
      { error: { code: "rag_request_failed", message: "RAG documents could not be loaded." } },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const response = await fetchBackend("/api/v1/rag/upload", request, {
      method: "POST",
      body: formData,
    });
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
      { error: { code: "rag_request_failed", message: "RAG document upload failed." } },
      { status: 500 },
    );
  }
}
