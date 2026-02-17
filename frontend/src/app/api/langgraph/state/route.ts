import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalBase } from "@/lib/backend-internal";

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
  const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  
  if (!bearerToken) {
    return NextResponse.json(
        { detail: "session_expired", request_id },
        { status: 401 }
    );
  }

  const backendBase = getBackendInternalBase();
  const base = backendBase.replace(/\/+$/, "");
  const search = req.nextUrl.search || "";
  const url = `${base}/api/v1/langgraph/state${search}`;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
      },
      cache: "no-store",
    });

    if (!res.ok) {
        const errorData = await res.text();
        return new Response(errorData, {
            status: res.status,
            headers: { 
                "Content-Type": res.headers.get("content-type") || "application/json",
                "Cache-Control": "no-store" 
            },
        });
    }

    const data = await res.text();
    return new Response(data, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { detail: `Backend unreachable: ${String(err?.message || err)}`, code: "backend_fetch_failed", request_id },
      { status: 502 }
    );
  }
}
