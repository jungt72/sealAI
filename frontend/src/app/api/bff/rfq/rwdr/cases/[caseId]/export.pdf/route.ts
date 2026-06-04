import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRwdrCasePdfBackendPath } from "@/lib/bff/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildRwdrCasePdfBackendPath(caseId), request);
    const body = await response.arrayBuffer().catch(() => null);
    if (!response.ok || !body) {
      return NextResponse.json(
        { error: { code: "rwdr_pdf_export_failed", message: `rwdr_pdf_export_failed:${response.status}` } },
        { status: response.status || 500 },
      );
    }
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/pdf",
        "Content-Disposition": response.headers.get("content-disposition") || `attachment; filename="sealai-rwdr-${caseId}.pdf"`,
        "X-SealAI-Dispatch-Allowed": "false",
        "X-SealAI-External-Contact-Allowed": "false",
      },
    });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json({ error: { code: "auth_error", message: error.message } }, { status: error.status });
    }
    return NextResponse.json({ error: { code: "rwdr_pdf_export_failed", message: "RWDR PDF export could not be created." } }, { status: 500 });
  }
}
