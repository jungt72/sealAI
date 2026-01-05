import { NextRequest } from "next/server";

import { getBackendInternalBase } from "@/lib/backend-internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization") ?? "";
  const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  if (!bearerToken) {
    return new Response(JSON.stringify({ detail: "session_expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch (err: any) {
    return new Response(JSON.stringify({ detail: "invalid_multipart", error: String(err?.message || err) }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const backendBase = getBackendInternalBase();
  const url = `${backendBase}/api/v1/rag/upload`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
      },
      body: formData,
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
