"use client";

import * as React from "react";
import ChatWsClient from "./ws";
import { useAccessToken, fetchFreshAccessToken } from "./useAccessToken";

export type UseChatWsArgs = { chatId?: string; endpoint?: string };

type UseChatWsState = {
  connected: boolean;
  streaming: boolean;
  threadId?: string;
  agent?: string;
  text: string;             // transient Stream-Puffer (wird nach DONE geleert)
  lastError?: string;
  lastUiAction?: any;       // zuletzt empfangenes UI-Event
};

export function useChatWs({ chatId = "default", endpoint }: UseChatWsArgs = {}) {
  const { token } = useAccessToken();
  const [state, setState] = React.useState<UseChatWsState>({
    connected: false,
    streaming: false,
    text: "",
  });

  const clientRef = React.useRef<ChatWsClient>();
  const awaitingSendRef = React.useRef(false);

  const getToken = React.useCallback(async () => {
    const fresh = await fetchFreshAccessToken().catch(() => undefined);
    return fresh ?? token;
  }, [token]);

  React.useEffect(() => {
    let mounted = true;
    if (!token) return;

    const client = new ChatWsClient({
      url: endpoint ?? "/api/v1/ai/ws",
      getToken,
      onOpen: () => mounted && setState((s) => ({ ...s, connected: true })),
      onClose: () =>
        mounted && setState((s) => ({ ...s, connected: false, streaming: false })),
      onError: (ev: Event) =>
        mounted &&
        setState((s) => ({
          ...s,
          lastError: String((ev as any)?.message ?? "WebSocket error"),
        })),
      onStreamStart: ({ threadId, agent }) => {
        if (!mounted || !awaitingSendRef.current) return;
        setState((s) => ({
          ...s,
          streaming: true,
          threadId,
          agent,
          text: "",
        }));
      },
      onStreamDelta: ({ delta }) =>
        mounted &&
        setState((s) => ({
          ...s,
          text: (s.text ?? "") + String(delta),
        })),
      onStreamDone: () => {
        if (!mounted) return;
        awaitingSendRef.current = false;
        setState((s) => ({ ...s, streaming: false, text: "" }));
      },
      onUiAction: (ua) => {
        if (!mounted) return;
        setState((s) => ({ ...s, lastUiAction: ua }));
        // globales Event, damit Shell den linken Drawer öffnen kann
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: ua }));
      },
    });

    clientRef.current = client;
    client.connect().catch((e: any) => {
      if (!mounted) return;
      setState((s) => ({ ...s, lastError: String(e?.message ?? e) }));
    });

    return () => {
      mounted = false;
      client.close();
      clientRef.current = undefined;
    };
  }, [token, endpoint, getToken]);

  const send = React.useCallback(
    (input: string, extra?: Record<string, unknown>) => {
      const trimmed = input?.trim();
      if (!trimmed) return;
      awaitingSendRef.current = true;
      clientRef.current?.request(trimmed, chatId, extra);
    },
    [chatId],
  );

  const cancel = React.useCallback(() => {
    clientRef.current?.cancel(state.threadId);
    awaitingSendRef.current = false;
    setState((s) => ({ ...s, streaming: false, text: "" }));
  }, [state.threadId]);

  const reset = React.useCallback(() => {
    awaitingSendRef.current = false;
    setState({ connected: !!state.connected, streaming: false, text: "" });
  }, [state.connected]);

  return { ...state, send, cancel, reset };
}
