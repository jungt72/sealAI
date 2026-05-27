import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRwdrConfirmationsBackendPath } from "@/lib/bff/workspace";

async function readJson(request: Request): Promise<Record<string, unknown>> {
  const body = await request.json().catch(() => null);
  return body && typeof body === "object" && !Array.isArray(body) ? body as Record<string, unknown> : {};
}

export async function POST(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const callerBody = await readJson(request);
    const response = await fetchBackend(buildRwdrConfirmationsBackendPath(caseId), request, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions: Array.isArray(callerBody.decisions) ? callerBody.decisions : [] }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body) {
      return NextResponse.json(
        { error: { code: "rwdr_confirmation_failed", message: body?.detail?.message || body?.detail?.code || `rwdr_confirmation_failed:${response.status}` } },
        { status: response.status || 500 },
      );
    }
    return NextResponse.json(body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json({ error: { code: "auth_error", message: error.message } }, { status: error.status });
    }
    return NextResponse.json({ error: { code: "rwdr_confirmation_failed", message: "RWDR confirmation could not be stored." } }, { status: 500 });
  }
}
