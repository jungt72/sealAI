export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function POST(request: Request, context: any) {
  const conversationId: string | undefined = context?.params?.conversationId;
  if (!conversationId) {
    return new Response(JSON.stringify({ error: "Missing conversationId" }), {
      status: 400,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }

  const authHeader = request.headers.get("authorization");
  const token = authHeader?.split(" ")[1];
  if (!token) {
    return new Response(JSON.stringify({ error: "Unauthorized – token missing" }), {
      status: 401,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }

  const body = await request.text();

  const base =
    (process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://localhost:8000").replace(/\/$/, "");

  const backendUrl = `${base}/api/v1/langgraph/chat/${conversationId}/chat_stream`;

  const backendRes = await fetch(backendUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    body,
  });

  return new Response(backendRes.body, {
    status: backendRes.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform, no-store",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
