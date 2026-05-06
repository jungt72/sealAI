import { NextResponse } from "next/server";

import { BffError, fetchBackend } from "@/lib/bff/http";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const limit = url.searchParams.get("limit") || "30";
    const response = await fetchBackend(
      `/api/agent/cases?limit=${encodeURIComponent(limit)}`,
      request,
    );
    const body = await response.json().catch(() => null);

    if (!response.ok || !body) {
      const message =
        body?.detail?.message ||
        body?.detail?.code ||
        body?.detail ||
        `case_list_fetch_failed:${response.status}`;
      return NextResponse.json(
        { error: { code: "case_list_fetch_failed", message } },
        { status: response.status || 500 },
      );
    }

    return NextResponse.json(body, { status: 200 });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
        { status: error.status },
      );
    }
    return NextResponse.json(
      { error: { code: "case_list_fetch_failed", message: "Case history could not be loaded." } },
      { status: 500 },
    );
  }
}
