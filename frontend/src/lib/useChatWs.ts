"use client";

import * as React from "react";
import ChatWsClient from "./ws";
import { useAccessToken, fetchFreshAccessToken } from "./useAccessToken";

export type UseChatWsArgs = { chatId: string; endpoint?: string };

type UseChatWsState = {
  connected: boolean;
  streaming: boolean;
  threadId?: string;
  agent?: string;
  text: string;            // transient Streaming-Puffer (wird nach DONE geleert)
  lastError?: string;
};

export function useChatWs({ chatId, endpoint }: UseChatWsArgs) {
  const { token } = useAccessToken();
  const [state, setState] = React.useState<UseChatWsState>({
    connected: false,
    streaming: false,
    text: "",
  });

  const clientRef = React.useRef<ChatWsClient>();
  // Nur wenn wir aktiv send() aufrufen, darf ein "starting" den Stream starten.
  const awaitingSendRef = React.useRef(false);

  // bei jedem Connect frischen Token holen (Fallback: letzter bekannter)
  const getToken = React.useCallback(async () => {
    const fresh = await fetchFreshAccessToken();
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

      // "starting" nur akzeptieren, wenn wir selbst gesendet haben.
      onStreamStart: ({ threadId, agent }: { threadId: string; agent?: string }) => {
        if (!mounted) return;
        if (!awaitingSendRef.current) return; // späte/duplizierte Events ignorieren
        setState((s) => ({
          ...s,
          streaming: true,
          threadId,
          agent,
          text: "", // neuer Stream -> Puffer leeren
        }));
      },

      onStreamDelta: ({ delta }: { delta: string }) =>
        mounted &&
        setState((s) => ({
          ...s,
          text: (s.text ?? "") + String(delta),
        })),

      onStreamDone: () => {
        if (!mounted) return;
        awaitingSendRef.current = false;
        // Wichtig gegen Doppelanzeige:
        // Der Stream-Text ist nur transient. Nach DONE wird er geleert,
        // damit anschließend NUR die persistierte Final-Nachricht angezeigt wird.
        setState((s) => ({ ...s, streaming: false, text: "" }));
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
      if (!input?.trim()) return;
      awaitingSendRef.current = true;
      clientRef.current?.request(input, chatId, extra);
    },
    [chatId],
  );

  const cancel = React.useCallback(() => {
    clientRef.current?.cancel(state.threadId);
    awaitingSendRef.current = false;
    setState((s) => ({ ...s, streaming: false, text: "" }));
  }, [state.threadId]);

  return { ...state, send, cancel };
}
