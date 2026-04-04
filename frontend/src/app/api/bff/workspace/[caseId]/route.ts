import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";
import { buildWorkspaceBackendReadPath } from "@/lib/bff/workspace";
import { mapWorkspaceView } from "@/lib/mapping/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const response = await fetchBackend(buildWorkspaceBackendReadPath(caseId), request);
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `workspace_fetch_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "workspace_fetch_failed", message } },
        { status: response.status || 500 },
      );
    }

    return NextResponse.json(mapWorkspaceView(caseId, body));
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      { error: { code: "workspace_fetch_failed", message: "Workspace could not be loaded." } },
      { status: 500 },
    );
  }
}
