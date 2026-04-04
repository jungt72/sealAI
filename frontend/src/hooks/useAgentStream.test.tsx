import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAgentStream } from "./useAgentStream";

const mockFetchEventSource = vi.fn();

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: (...args: unknown[]) => mockFetchEventSource(...args),
}));

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useAgentStream", () => {
  beforeEach(() => {
    mockFetchEventSource.mockReset();
    vi.restoreAllMocks();
  });

  it("uses only state_update.reply as visible text and finalizes the assistant turn once", async () => {
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Preview text" }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "case_bound", caseId: "case-1" }) });
      handlers.onmessage?.({
        data: JSON.stringify({ type: "state_update", caseId: "case-1", reply: "Finale Antwort" }),
      });
      handlers.onmessage?.({
        data: JSON.stringify({ type: "state_update", caseId: "case-1", reply: "Finale Antwort" }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream());

    await act(async () => {
      await result.current.sendMessage("Hallo");
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.activeCaseId).toBe("case-1");
    expect(result.current.streamingText).toBe("");
    expect(result.current.messages).toEqual([
      { role: "user", content: "Hallo" },
      { role: "assistant", content: "Finale Antwort" },
    ]);
  });

  it("does not let a late history restore overwrite the live turn state", async () => {
    const historyRequest = deferred<{
      ok: boolean;
      json: () => Promise<{ messages: Array<{ role: string; content: string }> }>;
    }>();

    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => historyRequest.promise as Promise<Response>,
    );
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({ data: JSON.stringify({ type: "case_bound", caseId: "case-1" }) });
      handlers.onmessage?.({
        data: JSON.stringify({ type: "state_update", caseId: "case-1", reply: "Aktuelle Antwort" }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream({ initialCaseId: "case-1" }));

    await act(async () => {
      await result.current.sendMessage("Neue Nachricht");
    });

    await act(async () => {
      historyRequest.resolve({
        ok: true,
        json: async () => ({
          messages: [{ role: "assistant", content: "Alte Antwort" }],
        }),
      });
      await historyRequest.promise;
      await Promise.resolve();
    });

    expect(result.current.messages).toEqual([
      { role: "user", content: "Neue Nachricht" },
      { role: "assistant", content: "Aktuelle Antwort" },
    ]);
  });
});
