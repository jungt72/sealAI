import { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
export const dynamic = "force-dynamic";

const BASE = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://backend:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  let accessToken: string | undefined;
  if (authHeader?.startsWith("Bearer ")) accessToken = authHeader.slice(7);
  else {
    const token = await getToken({ req });
    if (token && typeof token === "object") accessToken = (token as any).accessToken || (token as any).access_token;
  }
  if (!accessToken) return new Response("Unauthorized", { status: 401, headers: { "Cache-Control": "no-store" } });

  const body = await req.text();
  const r = await fetch(`${BASE}/api/v1/langgraph/chat/stream`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json", Accept: "text/event-stream" },
    body
  });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform, no-store", Connection: "keep-alive", "X-Accel-Buffering": "no" }
  });
}
