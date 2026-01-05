import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalBase } from "@/lib/backend-internal";
import { getRequestAuth } from "@/lib/server/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const auth = await getRequestAuth(req, { useRedis: true, requireAccessToken: true, logContext: "auth/conversations" });
  if (auth.reason) {
    return NextResponse.json(
      {
        detail: "session_expired",
        reason: auth.reason,
        ...(auth.debug ? { debug: auth.debug } : {}),
      },
      { status: 401 },
    );
  }

  const backendBase = getBackendInternalBase();
  const url = `${backendBase}/api/v1/chat/conversations`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${auth.accessToken}`,
      },
      cache: "no-store",
    });

    const text = await res.text();
    const contentType = res.headers.get("content-type") || "application/json";

    if (!res.ok) {
      const MAX_BODY_LENGTH = 8 * 1024;
      const truncated =
        text.length > MAX_BODY_LENGTH ? `${text.slice(0, MAX_BODY_LENGTH)}... (truncated)` : text;
      const safeBody = contentType.toLowerCase().includes("text/html") ? undefined : truncated;
      const payload: Record<string, unknown> = {
        detail: "Backend request failed",
        status: res.status,
        backend: url,
      };
      if (safeBody && safeBody.length > 0) {
        payload.body = safeBody;
      }

      return new NextResponse(JSON.stringify(payload), {
        status: res.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new NextResponse(text, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  } catch (e: any) {
    return NextResponse.json(
      {
        detail: "Backend unreachable",
        error: String(e?.message || e),
        backend: url,
      },
      { status: 502 },
    );
  }
}
