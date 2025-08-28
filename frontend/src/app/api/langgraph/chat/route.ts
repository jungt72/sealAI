import { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

export const dynamic = "force-dynamic";

/**
 * Allgemeiner SSE-Proxy auf /api/v1/langgraph/chat/stream.
 * Nutzt BACKEND_URL (Docker) oder NEXT_PUBLIC_BACKEND_URL als Fallback.
 */
export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  let accessToken: string | undefined = undefined;

  if (authHeader?.startsWith("Bearer ")) {
    accessToken = authHeader.replace("Bearer ", "");
  } else {
    const token = await getToken({ req });
    if (token && typeof token === "object") {
      accessToken = (token as any).accessToken || (token as any).access_token;
    }
  }

  if (!accessToken) {
    return new Response("Unauthorized", { status: 401 });
  }

  const json = await req.text();

  const base =
    (process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://localhost:8000").replace(/\/$/, "");

  const backendRes = await fetch(`${base}/api/v1/langgraph/chat/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: json,
  });

  return new Response(backendRes.body, {
    status: backendRes.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
