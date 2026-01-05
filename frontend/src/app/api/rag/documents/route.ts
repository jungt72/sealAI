import { NextRequest } from "next/server";

import { getBackendInternalBase } from "@/lib/backend-internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const authHeader = req.headers.get("authorization") ?? "";
  const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  if (!bearerToken) {
    return new Response(JSON.stringify({ detail: "session_expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const backendBase = getBackendInternalBase();
  const url = `${backendBase}/api/v1/rag/documents${req.nextUrl.search}`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${bearerToken}`,
      },
      cache: "no-store",
    });

    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (err: any) {
    return new Response(
      JSON.stringify({
        detail: "Backend unreachable",
        error: String(err?.message || err),
        backend: url,
      }),
      {
        status: 502,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}
