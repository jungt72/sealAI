import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildRwdrCaseDiffBackendPath } from "@/lib/bff/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string; fromRevision: string; toRevision: string }> },
) {
  try {
    const { caseId, fromRevision, toRevision } = await context.params;
    const from = Number.parseInt(fromRevision, 10);
    const to = Number.parseInt(toRevision, 10);
    const response = await fetchBackend(buildRwdrCaseDiffBackendPath(caseId, from, to), request);
    const body = await response.json().catch(() => null);
    if (!response.ok || !body) {
      return NextResponse.json(
        { error: { code: "rwdr_diff_failed", message: body?.detail?.message || body?.detail?.code || `rwdr_diff_failed:${response.status}` } },
        { status: response.status || 500 },
      );
    }
    return NextResponse.json(body);
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json({ error: { code: "auth_error", message: error.message } }, { status: error.status });
    }
    return NextResponse.json({ error: { code: "rwdr_diff_failed", message: "RWDR revisions could not be compared." } }, { status: 500 });
  }
}
