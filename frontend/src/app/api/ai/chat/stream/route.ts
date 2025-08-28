// frontend/src/app/api/ai/chat/stream/route.ts
/**
 * Edge-Proxy, der Streaming-Requests an das FastAPI-Backend
 * (/api/v1/ai/chat/stream) durchleitet.
 */

import { NextRequest } from "next/server";

export const runtime = "edge";

const BASE =
  (process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    "http://localhost:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.text();

  // Auth-Header (z. B. “Bearer <JWT>”) einfach weiterreichen
  const headers = new Headers({
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  });
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);

  const backendResp = await fetch(`${BASE}/api/v1/ai/chat/stream`, {
    method: "POST",
    headers,
    body,
  });

  // Stream ungepuffert an den Client durchreichen
  return new Response(backendResp.body, {
    status: backendResp.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
