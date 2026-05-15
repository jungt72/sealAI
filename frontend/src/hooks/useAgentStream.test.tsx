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
    vi.spyOn(globalThis, "fetch").mockImplementation(
      async () =>
        new Response(JSON.stringify({ messages: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
  });

  it("streams text chunks live and finalizes with state_update.reply once", async () => {
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Preview " }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "text" }) });
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
      expect.objectContaining({ role: "user", content: "Hallo" }),
      expect.objectContaining({ role: "assistant", content: "Finale Antwort" }),
    ]);
  });

  it("surfaces live graph progress until text chunks arrive", async () => {
    const hold = deferred<void>();
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "progress",
          data: { event_type: "challenge_ready" },
        }),
      });
      await hold.promise;
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Live " }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Antwort" }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "state_update", caseId: "case-1", reply: "Live Antwort" }) });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream());

    let sendPromise: Promise<void> | undefined;
    await act(async () => {
      sendPromise = result.current.sendMessage("Bitte analysieren");
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.streamingStatusText).toBe("SealingAI bewertet technische Risiken...");
    });

    await act(async () => {
      hold.resolve();
      await sendPromise;
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.streamingStatusText).toBe("");
    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Bitte analysieren" }),
      expect.objectContaining({ role: "assistant", content: "Live Antwort" }),
    ]);
  });

  it("normalizes German visible text while token chunks are still streaming", async () => {
    const hold = deferred<void>();
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Druckunterschied ue" }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "ber der Dichtung" }) });
      await hold.promise;
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "state_update",
          caseId: "case-1",
          answer_markdown: "Druckunterschied ueber der Dichtung",
        }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream());

    let sendPromise: Promise<void> | undefined;
    await act(async () => {
      sendPromise = result.current.sendMessage("Bitte prüfen");
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.streamingText).toBe("Druckunterschied über der Dichtung");
    });

    await act(async () => {
      hold.resolve();
      await sendPromise;
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Bitte prüfen" }),
      expect.objectContaining({
        role: "assistant",
        content: "Druckunterschied über der Dichtung",
      }),
    ]);
  });

  it("resets live preview when backend repairs a governed stream", async () => {
    const hold = deferred<void>();
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "Slotfrage" }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_reset" }) });
      handlers.onmessage?.({ data: JSON.stringify({ type: "text_chunk", text: "EPDM Warnpunkt. " }) });
      await hold.promise;
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "state_update",
          caseId: "case-1",
          answer_markdown: "EPDM Warnpunkt. Wichtigste Rückfrage?",
        }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream());

    let sendPromise: Promise<void> | undefined;
    await act(async () => {
      sendPromise = result.current.sendMessage("Bitte einordnen");
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.streamingText).toBe("EPDM Warnpunkt. ");
    });

    await act(async () => {
      hold.resolve();
      await sendPromise;
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Bitte einordnen" }),
      expect.objectContaining({
        role: "assistant",
        content: "EPDM Warnpunkt. Wichtigste Rückfrage?",
      }),
    ]);
  });

  it("renders no-case fast responses without binding a case or cockpit workspace", async () => {
    const onCaseBound = vi.fn();
    const onNoCaseTurn = vi.fn();
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "state_update",
          noCaseCreated: true,
          reply: "Hallo! Schoen, dass du da bist.",
          responseClass: "conversational_answer",
        }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream({ onCaseBound, onNoCaseTurn }));

    await act(async () => {
      await result.current.sendMessage("Hallo");
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.activeCaseId).toBeNull();
    expect(result.current.streamWorkspace).toBeNull();
    expect(onCaseBound).not.toHaveBeenCalled();
    expect(onNoCaseTurn).toHaveBeenCalledTimes(1);
    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Hallo" }),
      expect.objectContaining({ role: "assistant", content: "Hallo! Schön, dass du da bist." }),
    ]);
  });

  it("maps expired-token stream errors to a user-facing session message", async () => {
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(
        new Response(JSON.stringify({ error: { message: "{\"detail\":\"token_expired\"}" } }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });

    const { result } = renderHook(() => useAgentStream());

    await act(async () => {
      await result.current.sendMessage("Was ist NBR?");
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.error).toBe("Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
    expect(result.current.error).not.toContain("token_expired");
    expect(result.current.error).not.toContain("{");
  });

  it("prefers state_update.answer_markdown over reply for the final assistant message", async () => {
    const answerTrace = {
      reply_source: "knowledge_service",
      answer_markdown_source: "knowledge_composer",
      final_visible_source: "answer_markdown",
      composer_attempted: true,
      composer_succeeded: true,
      hcl_attempted: false,
      hcl_succeeded: false,
      fallback_reason: null,
    };
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "state_update",
          caseId: "case-1",
          reply: "deterministic fallback",
          answer_markdown: "real assistant answer",
          runMeta: {
            answer_trace: answerTrace,
          },
        }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream());

    await act(async () => {
      await result.current.sendMessage("Vergleiche FKM und EPDM");
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Vergleiche FKM und EPDM" }),
      expect.objectContaining({
        role: "assistant",
        content: "real assistant answer",
        answerSource: "answer_markdown",
        answerTrace,
      }),
    ]);
  });

  it("preserves answer_trace while keeping reply rendering unchanged", async () => {
    const answerTrace = {
      reply_source: "fast_responder",
      answer_markdown_source: "fast_responder",
      final_visible_source: "answer_markdown",
      composer_attempted: false,
      composer_succeeded: false,
      hcl_attempted: false,
      hcl_succeeded: false,
      fallback_reason: null,
    };
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({
        data: JSON.stringify({
          type: "state_update",
          noCaseCreated: true,
          reply: "Hallo! Schoen, dass du da bist.",
          runMeta: { answer_trace: answerTrace },
        }),
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

    expect(result.current.messages).toEqual([
      expect.objectContaining({ role: "user", content: "Hallo" }),
      expect.objectContaining({
        role: "assistant",
        content: "Hallo! Schön, dass du da bist.",
        answerSource: "reply",
        answerTrace: {
          ...answerTrace,
          final_visible_source: "reply",
        },
      }),
    ]);
  });

  it("binds the active case from state_update even when case_bound is missing", async () => {
    const onCaseBound = vi.fn();
    mockFetchEventSource.mockImplementation(async (_url: string, handlers: Record<string, Function>) => {
      await handlers.onopen?.(new Response(null, { status: 200 }));
      handlers.onmessage?.({
        data: JSON.stringify({ type: "state_update", caseId: "case-from-state", reply: "Antwort" }),
      });
      handlers.onmessage?.({ data: "[DONE]" });
      handlers.onclose?.();
    });

    const { result } = renderHook(() => useAgentStream({ onCaseBound }));

    await act(async () => {
      await result.current.sendMessage("Salzwasser 80 Grad");
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.activeCaseId).toBe("case-from-state");
    expect(onCaseBound).toHaveBeenCalledWith("case-from-state");
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
      expect.objectContaining({ role: "user", content: "Neue Nachricht" }),
      expect.objectContaining({ role: "assistant", content: "Aktuelle Antwort" }),
    ]);
  });

  it("restores chat history from the live agent endpoint list response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify([
          { role: "user", content: "Bitte analysiere eine Pumpendichtung." },
          { role: "assistant", content: "Welche Druckdifferenz liegt an der Dichtstelle an?" },
        ]),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const { result } = renderHook(() => useAgentStream({ initialCaseId: "case-1" }));

    await waitFor(() => {
      expect(result.current.messages).toEqual([
        { role: "user", content: "Bitte analysiere eine Pumpendichtung." },
        { role: "assistant", content: "Welche Druckdifferenz liegt an der Dichtstelle an?" },
      ]);
    });

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/bff/agent/chat/history/case-1");
  });
});
