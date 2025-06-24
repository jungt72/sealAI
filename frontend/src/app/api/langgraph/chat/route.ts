import { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  let accessToken: string | undefined = undefined;

  if (authHeader && authHeader.startsWith("Bearer ")) {
    accessToken = authHeader.replace("Bearer ", "");
  }

  if (!accessToken) {
    const token = await getToken({ req });
    if (token && typeof token === "object") {
      accessToken = (token as any).accessToken || (token as any).access_token;
    }
  }

  if (!accessToken) {
    return new Response("Unauthorized", { status: 401 });
  }

  const json = await req.json();
  const body = JSON.stringify(json);

  const backendRes = await fetch(`${process.env.BACKEND_URL}/api/v1/langgraph/chat/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body,
  });

  return new Response(backendRes.body, {
    status: backendRes.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
