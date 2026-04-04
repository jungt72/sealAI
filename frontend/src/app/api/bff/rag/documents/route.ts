import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";

function passthroughResponse(response: Response, body: BodyInit | null) {
  return new Response(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json; charset=utf-8",
    },
  });
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const search = url.searchParams.toString();
    const response = await fetchBackend(`/api/v1/rag/documents${search ? `?${search}` : ""}`, request);
    const body = await response.text();
    return passthroughResponse(response, body);
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
    return passthroughResponse(response, body);
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
