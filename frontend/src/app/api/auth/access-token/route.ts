import { NextRequest, NextResponse } from "next/server";
import { getRequestAuth } from "@/lib/server/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const auth = await getRequestAuth(req, { useRedis: true, requireAccessToken: true, logContext: "auth/access-token" });
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

  return NextResponse.json(
    { accessToken: auth.accessToken },
    {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
