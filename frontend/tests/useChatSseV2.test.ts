import React, { forwardRef, useImperativeHandle } from "react";
import { act, create } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildChatRequestPayload, type SseStatus, useChatSseV2 } from "../src/lib/useChatSseV2";
import { fetchWithAuth } from "@/lib/fetchWithAuth";

vi.mock("@/lib/fetchWithAuth", () => ({
  fetchWithAuth: vi.fn(),
}));

type HookHandle = ReturnType<typeof useChatSseV2>;

const HookHarness = forwardRef<
  HookHandle,
  { chatId?: string | null; token?: string | null; onRetrievalMeta?: (payload: any) => void }
>(({ chatId, token, onRetrievalMeta }, ref) => {
    const state = useChatSseV2({
      chatId,
      token,
      onToken: () => undefined,
      onDone: () => undefined,
      onStart: () => undefined,
      onRetrievalMeta,
    });

    useImperativeHandle(ref, () => state, [state]);
    return null;
  });
HookHarness.displayName = "HookHarness";

const createSseResponse = (frames: string[]) => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
};

const createOpenSseResponse = () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode("event: token\n"));
      controller.enqueue(encoder.encode("data: {\"text\":\"hi\"}\n\n"));
    },
    pull() {
      return new Promise(() => undefined);
    },
  });
  return new Response(stream, { status: 200 });
};

const expectStatus = (status: HookHandle["status"], expected: SseStatus) => {
  expect(status).toBe(expected);
};

const flush = async () => {
  await Promise.resolve();
};

describe("useChatSseV2 payload", () => {
  it("includes client_context param snapshot", () => {
    const payload = buildChatRequestPayload({
      input: "Hi",
      chatId: "chat-1",
      clientMsgId: "msg-1",
      metadata: { source: "test" },
      clientContext: {
        param_snapshot: {
          parameters: { pressure_bar: 5 },
          versions: { pressure_bar: 2 },
          updated_at: { pressure_bar: 100 },
        },
      },
    });

    expect(payload).toEqual({
      input: "Hi",
      chat_id: "chat-1",
      client_msg_id: "msg-1",
      metadata: { source: "test" },
      client_context: {
        param_snapshot: {
          parameters: { pressure_bar: 5 },
          versions: { pressure_bar: 2 },
          updated_at: { pressure_bar: 100 },
        },
      },
    });
  });
});

describe("useChatSseV2 reconnect fsm", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("marks reconnecting on network error and schedules retry", async () => {
    const fetchMock = vi.mocked(fetchWithAuth);
    fetchMock.mockImplementation(() => {
      throw new Error("network");
    });
    const ref = React.createRef<HookHandle>();

    act(() => {
      create(React.createElement(HookHarness, { ref, chatId: "chat-1", token: "token" }));
    });

    await act(async () => {
      ref.current?.send("Hallo");
      await flush();
    });

    expectStatus(ref.current?.status, "reconnecting");
    expect(vi.getTimerCount()).toBeGreaterThan(0);
  });

  it("resets backoff and sets connected on successful open", async () => {
    const fetchMock = vi.mocked(fetchWithAuth);
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    fetchMock
      .mockImplementationOnce(() => {
        throw new Error("network");
      })
      .mockResolvedValueOnce(
        createSseResponse(["event: done\n", "data: {}\n\n"]),
      );

    const ref = React.createRef<HookHandle>();
    act(() => {
      create(React.createElement(HookHarness, { ref, chatId: "chat-1", token: "token" }));
    });

    await act(async () => {
      ref.current?.send("Hallo");
      await flush();
    });

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await flush();
    });

    expectStatus(ref.current?.status, "connected");
    expect(ref.current?.retryAttempt).toBe(0);
    vi.restoreAllMocks();
  });

  it("manual reconnect starts a new stream and aborts the old one", async () => {
    const fetchMock = vi.mocked(fetchWithAuth);
    const signals: AbortSignal[] = [];
    fetchMock.mockImplementation((_url, _token, init) => {
      if (init?.signal) signals.push(init.signal);
      return Promise.resolve(createOpenSseResponse());
    });

    const ref = React.createRef<HookHandle>();
    act(() => {
      create(React.createElement(HookHarness, { ref, chatId: "chat-1", token: "token" }));
    });

    await act(async () => {
      ref.current?.send("Hallo");
      await flush();
    });

    await act(async () => {
      ref.current?.reconnect();
      await flush();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(signals[0]?.aborted).toBe(true);
  });

  it("auth failure goes offline without scheduling retries", async () => {
    const fetchMock = vi.mocked(fetchWithAuth);
    fetchMock.mockResolvedValue(new Response("auth_required", { status: 401 }));
    const ref = React.createRef<HookHandle>();

    act(() => {
      create(React.createElement(HookHarness, { ref, chatId: "chat-1", token: "token" }));
    });

    await act(async () => {
      ref.current?.send("Hallo");
      await flush();
    });

    expectStatus(ref.current?.status, "offline");
    expect(ref.current?.lastError).toBe("auth_required");
    expect(vi.getTimerCount()).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("captures retrieval sources from SSE events", async () => {
    const fetchMock = vi.mocked(fetchWithAuth);
    const retrievalSpy = vi.fn();
    fetchMock.mockResolvedValue(
      createSseResponse([
        "event: retrieval.results\n",
        "data: {\"sources\":[{\"document_id\":\"doc-1\",\"filename\":\"specs.pdf\",\"score\":0.92}]}\n\n",
        "event: done\n",
        "data: {}\n\n",
      ]),
    );
    const ref = React.createRef<HookHandle>();

    act(() => {
      create(
        React.createElement(HookHarness, {
          ref,
          chatId: "chat-1",
          token: "token",
          onRetrievalMeta: retrievalSpy,
        }),
      );
    });

    await act(async () => {
      ref.current?.send("Hallo");
      await flush();
    });

    expect(retrievalSpy).toHaveBeenCalled();
    const payload = retrievalSpy.mock.calls[0][0];
    expect(payload.sources?.[0]?.document_id).toBe("doc-1");
    expect(payload.sources?.[0]?.filename).toBe("specs.pdf");
  });
});
