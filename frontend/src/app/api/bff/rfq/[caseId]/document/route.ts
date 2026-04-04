import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRfqDocumentBackendReadPath } from "@/lib/bff/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildRfqDocumentBackendReadPath(caseId), request);
    const html = await response.text();

    if (!response.ok) {
      return NextResponse.json(
        {
          error: {
            code: "rfq_document_unavailable",
            message: html || `rfq_document_unavailable:${response.status}`,
          },
        },
        { status: response.status || 500 },
      );
    }

    return new NextResponse(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
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
      { error: { code: "rfq_document_unavailable", message: "RFQ document could not be loaded." } },
      { status: 500 },
    );
  }
}
