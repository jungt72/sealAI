import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRwdrAnalyzeBackendPath } from "@/lib/bff/workspace";

async function readJson(request: Request): Promise<Record<string, unknown>> {
  const body = await request.json().catch(() => null);
  return body && typeof body === "object" && !Array.isArray(body) ? body as Record<string, unknown> : {};
}

export async function POST(request: Request) {
  try {
    const callerBody = await readJson(request);
    const response = await fetchBackend(buildRwdrAnalyzeBackendPath(), request, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_inquiry: callerBody.raw_inquiry || "" }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body) {
      return NextResponse.json(
        { error: { code: "rwdr_analyze_failed", message: body?.detail?.message || body?.detail?.code || `rwdr_analyze_failed:${response.status}` } },
        { status: response.status || 500 },
      );
    }
    return NextResponse.json(body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json({ error: { code: "auth_error", message: error.message } }, { status: error.status });
    }
    return NextResponse.json({ error: { code: "rwdr_analyze_failed", message: "RWDR inquiry could not be analyzed." } }, { status: 500 });
  }
}
