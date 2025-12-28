import { NextRequest } from "next/server";
import { resolveLanggraphBackendBase } from "@/lib/langgraphBackendServer";

const makeRequestId = (): string => {
  try {
    return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
};

export async function GET(req: NextRequest) {
  const request_id = makeRequestId();
  const authHeader = req.headers.get("authorization") ?? "";
  if (!authHeader.startsWith("Bearer ")) {
    return new Response(JSON.stringify({ detail: "Missing Authorization: Bearer token", request_id }), {
      status: 401,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }

  const backendBase = resolveLanggraphBackendBase();
  const search = req.nextUrl.search || "";
  const url = `${backendBase}/api/v1/langgraph/state${search}`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: authHeader,
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
      JSON.stringify({ detail: `Backend unreachable: ${String(err?.message || err)}`, request_id }),
      { status: 502, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } },
    );
  }
}
