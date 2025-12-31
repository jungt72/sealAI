import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { POST } from "../src/app/api/chat/route";

vi.mock("../src/lib/langgraphApi", () => ({
  backendLangGraphChatEndpoint: () => "http://backend.test/api/v1/langgraph/chat/v2",
}));

const makeRequest = (body: Record<string, unknown>) =>
  new NextRequest("http://localhost/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer token-123",
    },
    body: JSON.stringify(body),
  });

describe("api/chat route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("allows client_context and forwards it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("event: message\ndata: ok\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client_context = {
      param_snapshot: { versions: { pressure_bar: 2, medium: 1 } },
    };

    const req = makeRequest({
      input: "hallo",
      chat_id: "chat-123",
      client_msg_id: "msg-1",
      client_context,
    });

    const resp = await POST(req);

    expect(resp.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe(
      JSON.stringify({
        input: "hallo",
        chat_id: "chat-123",
        client_msg_id: "msg-1",
        client_context,
      }),
    );
  });

  it("rejects unknown keys", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const req = makeRequest({
      input: "hallo",
      chat_id: "chat-456",
      bogus_key: 1,
    });

    const resp = await POST(req);
    const data = await resp.json();

    expect(resp.status).toBe(400);
    expect(data.unknown_keys).toContain("bogus_key");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
