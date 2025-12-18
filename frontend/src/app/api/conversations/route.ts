import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function stripApiSuffix(value: string): string {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed.replace(/\/api(?:\/v1)?$/i, "");
}

function resolveBackendBase(): string {
  // Wichtig: Server-side hat KEIN window.location – also MUSS eine Env existieren
  const raw =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_BASE ||
    process.env.BACKEND_URL ||
    process.env.API_BASE ||
    process.env.INTERNAL_BACKEND_URL ||
    "http://backend:8000"; // docker-compose service name fallback

  return stripApiSuffix(raw);
}

function pickToken(session: any): string | undefined {
  if (!session || typeof session !== "object") return undefined;

  const direct =
    session.accessToken ||
    session.access_token ||
    session.token ||
    session.idToken ||
    session.id_token;

  if (typeof direct === "string" && direct.length > 0) return direct;

  // manchmal steckt es in session.user
  const user = session.user;
  if (user && typeof user === "object") return pickToken(user);

  return undefined;
}

export async function GET() {
  let session: any = null;

  try {
    session = await getServerSession(authOptions);
  } catch (e: any) {
    // Das ist der klassische Fall "Failed to read session"
    return NextResponse.json(
      {
        detail: "Failed to read session",
        error: String(e?.message || e),
      },
      { status: 401 },
    );
  }

  if (!session) {
    return NextResponse.json(
      {
        detail: "Unauthorized",
        reason: "no_session",
      },
      { status: 401 },
    );
  }

  const sessionExpired = session.error === "RefreshAccessTokenError";
  if (sessionExpired) {
    return NextResponse.json(
      {
        detail: "Session expired",
        reason: "refresh_failed",
      },
      { status: 401 },
    );
  }

  const accessToken = pickToken(session);
  if (!accessToken) {
    return NextResponse.json(
      {
        detail: "Unauthorized",
        reason: "no_access_token_in_session",
      },
      { status: 401 },
    );
  }

  const backendBase = resolveBackendBase();
  const url = `${backendBase}/api/v1/chat/conversations`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
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
