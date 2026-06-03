import { NextResponse } from "next/server";

import { BffError, applyBffCookieUpdates, fetchBackendWithAuth } from "@/lib/bff/http";
import { buildWorkspaceBackendReadPath } from "@/lib/bff/workspace";
import { mapWorkspaceView } from "@/lib/mapping/workspace";

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const { caseId } = await context.params;
    const { response, cookieUpdates } = await fetchBackendWithAuth(
      buildWorkspaceBackendReadPath(caseId),
      request,
    );
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        `workspace_fetch_failed:${response.status}`;
      const errorResponse = NextResponse.json(
        { error: { code: "workspace_fetch_failed", message } },
        { status: response.status || 500 },
      );
      applyBffCookieUpdates(errorResponse, cookieUpdates);
      return errorResponse;
    }

    const okResponse = NextResponse.json(mapWorkspaceView(caseId, body));
    applyBffCookieUpdates(okResponse, cookieUpdates);
    return okResponse;
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
