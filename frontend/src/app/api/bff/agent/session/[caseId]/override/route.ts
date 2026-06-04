import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import { getAccessToken } from "@/lib/bff/auth-token";
import { BffError } from "@/lib/bff/http";
import { buildBackendUrl } from "@/lib/bff/backend";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  try {
    const token = await getAccessToken(request);
    const { caseId } = await context.params;
    const body = await request.json();

    const backendResponse = await fetch(
      buildBackendUrl(`/api/agent/session/${encodeURIComponent(caseId)}/override`),
      {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Request-Id": randomUUID(),
        },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );

    const payload = await backendResponse.json().catch(() => null);
    if (!backendResponse.ok) {
      return NextResponse.json(
        {
          error: {
            code: "parameter_override_failed",
            message:
              payload?.detail ||
              payload?.error?.message ||
              `parameter_override_failed:${backendResponse.status}`,
          },
        },
        { status: backendResponse.status || 500 },
      );
    }

    return NextResponse.json(payload, { status: 200 });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }

    return NextResponse.json(
      {
        error: {
          code: "parameter_override_failed",
          message: "Parameter override could not be processed.",
        },
      },
      { status: 500 },
    );
  }
}
