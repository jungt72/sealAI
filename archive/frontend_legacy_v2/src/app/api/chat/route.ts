import { NextRequest } from "next/server";

import { getBackendInternalBase } from "@/lib/backend-internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ChatV2Payload = {
  input: string;
  chat_id: string;
  client_msg_id?: string;
  metadata?: Record<string, unknown>;
  client_context?: Record<string, unknown>;
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function makeRequestId(): string {
  try {
    return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

export async function POST(req: NextRequest) {
  const request_id = makeRequestId();
  const started = Date.now();

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    console.info("[api/chat] invalid_json", { request_id });
    return new Response(JSON.stringify({ detail: "Invalid JSON", request_id }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!isPlainObject(body)) {
    console.info("[api/chat] invalid_body_type", { request_id });
    return new Response(JSON.stringify({ detail: "Body must be a JSON object", request_id }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const input = String(body.input ?? "").trim();
  const chat_id = String(body.chat_id ?? "").trim();

  const allowedKeys = new Set(["input", "chat_id", "client_msg_id", "metadata", "client_context"]);
  const unknownKeys = Object.keys(body).filter((key) => !allowedKeys.has(key));
  if (unknownKeys.length > 0) {
    console.info("[api/chat] forbidden_keys", { request_id, chat_id, unknownKeys });
    return new Response(
      JSON.stringify({
        detail: "Unknown keys in request body",
        request_id,
        unknown_keys: unknownKeys,
      }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  if (!input) {
    console.info("[api/chat] missing_input", { request_id, chat_id });
    return new Response(JSON.stringify({ detail: "input must not be empty", request_id }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (!chat_id) {
    console.info("[api/chat] missing_chat_id", { request_id });
    return new Response(JSON.stringify({ detail: "chat_id must not be empty", request_id }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const authHeader = req.headers.get("authorization") ?? "";
  const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  if (!bearerToken) {
    console.info("[api/chat] missing_auth", { request_id, chat_id });
    return new Response(JSON.stringify({ detail: "session_expired", request_id }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const payload: ChatV2Payload = { input, chat_id };
  const client_msg_id = typeof body.client_msg_id === "string" ? body.client_msg_id.trim() : "";
  if (client_msg_id) payload.client_msg_id = client_msg_id;
  const metadata = isPlainObject(body.metadata) ? body.metadata : undefined;
  if (metadata) payload.metadata = metadata;
  const client_context = isPlainObject(body.client_context) ? body.client_context : undefined;
  if (client_context) payload.client_context = client_context;
  if (metadata?.source === "param_apply") {
    const keys = Array.isArray(metadata.keys) ? metadata.keys.length : undefined;
    console.info("[api/chat] param_apply", { request_id, chat_id, keys });
  }

  const url = `${getBackendInternalBase()}/api/chat`;
  const lastEventId = req.headers.get("last-event-id") ?? "";

  let backendResp: Response;
  try {
    backendResp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: `Bearer ${bearerToken}`,
        "X-Request-Id": request_id,
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch (err: any) {
    console.info("[api/chat] backend_unreachable", {
      request_id,
      chat_id,
      ms: Date.now() - started,
      error: String(err?.message || err),
    });
    return new Response(JSON.stringify({ detail: `Backend unreachable: ${err?.message || err}` }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!backendResp.body) {
    console.info("[api/chat] backend_empty_body", {
      request_id,
      chat_id,
      status: backendResp.status,
      ms: Date.now() - started,
    });
    return new Response(JSON.stringify({ detail: "Empty response from backend", request_id }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  const headers = new Headers();
  headers.set("Content-Type", backendResp.headers.get("Content-Type") || "text/event-stream");
  headers.set("Cache-Control", "no-cache, no-transform");
  headers.set("Connection", "keep-alive");
  headers.set("X-Accel-Buffering", "no");
  headers.set("X-Request-Id", request_id);

  console.info("[api/chat] proxy", {
    request_id,
    chat_id,
    status: backendResp.status,
    ms: Date.now() - started,
  });

  return new Response(backendResp.body, {
    status: backendResp.status,
    headers,
  });
}
