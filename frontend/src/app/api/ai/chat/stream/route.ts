import { NextRequest } from "next/server";
export const runtime = "edge";
const BASE = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://backend:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.text();
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);

  const r = await fetch(`${BASE}/api/v1/langgraph/chat/stream2`, { method: "POST", headers, body });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform, no-store", Connection: "keep-alive", "X-Accel-Buffering": "no" }
  });
}
