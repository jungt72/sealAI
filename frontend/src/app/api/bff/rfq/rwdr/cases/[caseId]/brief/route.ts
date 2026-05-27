import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRwdrCaseBriefBackendPath } from "@/lib/bff/workspace";

export async function POST(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildRwdrCaseBriefBackendPath(caseId), request, { method: "POST" });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body) {
      return NextResponse.json(
        { error: { code: "rwdr_brief_failed", message: body?.detail?.message || body?.detail?.code || `rwdr_brief_failed:${response.status}` } },
        { status: response.status || 500 },
      );
    }
    return NextResponse.json(body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json({ error: { code: "auth_error", message: error.message } }, { status: error.status });
    }
    return NextResponse.json({ error: { code: "rwdr_brief_failed", message: "Technical RWDR RFQ Brief could not be created." } }, { status: 500 });
  }
}
