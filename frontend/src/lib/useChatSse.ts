"use client";

import * as React from "react";
import { useSession } from "next-auth/react";

type State = {
  streaming: boolean;
  text: string;
  error: string | null;
};

export function useChatSse(endpoint: string = "/api/langgraph/chat") {
  const { status } = useSession();
  const [state, setState] = React.useState<State>({ streaming: false, text: "", error: null });
  const controllerRef = React.useRef<AbortController | null>(null);

  const send = React.useCallback(async (input: string, bodyExtra?: Record<string, unknown>) => {
    if (status !== "authenticated") {
      setState((s) => ({ ...s, error: "unauthenticated" }));
      return;
    }
    const trimmed = input.trim();
    if (!trimmed) return;

    controllerRef.current?.abort();
    controllerRef.current = new AbortController();

    setState({ streaming: true, text: "", error: null });

    const resp = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ input: trimmed, stream: true, ...(bodyExtra || {}) }),
      signal: controllerRef.current.signal,
    }).catch((e) => {
      setState({ streaming: false, text: "", error: String(e?.message || "network_error") });
      return null as any;
    });

    if (!resp || !resp.ok || !resp.body) {
      if (resp) setState({ streaming: false, text: "", error: `http_${resp.status}` });
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(6));
            if (typeof payload?.delta === "string" && payload.delta.length) {
              setState((s) => ({ ...s, text: s.text + payload.delta }));
            } else if (payload?.final?.text) {
              setState((s) => ({ ...s, text: payload.final.text }));
            } else if (payload?.error) {
              setState((s) => ({ ...s, error: String(payload.error) }));
            }
          } catch {
            // ignore malformed frames
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setState((s) => ({ ...s, error: String(e?.message || "stream_error") }));
      }
    } finally {
      try { await reader.cancel(); } catch {}
      setState((s) => ({ ...s, streaming: false }));
    }
  }, [status, endpoint]);

  const cancel = React.useCallback(() => {
    controllerRef.current?.abort();
    setState((s) => ({ ...s, streaming: false }));
  }, []);

  const reset = React.useCallback(() => {
    controllerRef.current?.abort();
    setState({ streaming: false, text: "", error: null });
  }, []);

  return { ...state, send, cancel, reset };
}
