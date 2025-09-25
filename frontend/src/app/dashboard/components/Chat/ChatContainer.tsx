'use client';

import { useSession } from "next-auth/react";
import { useAccessToken } from "@/lib/useAccessToken";
import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import ChatHistory from "./ChatHistory";
import Thinking from "./Thinking";
import ChatInput from "./ChatInput";
import type { Message } from "@/types/chat";
import { useChatWs } from "@/lib/useChatWs";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatContainer() {
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated";

  const chatId = "default";
  const token = useAccessToken();
  const { connected, streaming, text, lastError, send, cancel } =
    useChatWs({ chatId, token });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);

  // === Scroll "anchor-then-hold" ===
  const scrollRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const prevStreamingRef = useRef(streaming);
  const [autoAnchor, setAutoAnchor] = useState(false);
  const targetTopRef = useRef<number | null>(null);

  const cancelAutoAnchor = useCallback(() => {
    targetTopRef.current = null;
    setAutoAnchor(false);
  }, []);

  const onScroll = useCallback(() => {
    if (!autoAnchor || targetTopRef.current == null) return;
    const cont = scrollRef.current;
    if (!cont) return;
    if (Math.abs(cont.scrollTop - targetTopRef.current) > 150) cancelAutoAnchor();
  }, [autoAnchor, cancelAutoAnchor]);

  const onWheel = cancelAutoAnchor;
  const onTouchStart = cancelAutoAnchor;

  // Beim Streamstart Anker ins obere Drittel
  useEffect(() => {
    const was = prevStreamingRef.current;
    prevStreamingRef.current = streaming;
    if (!was && streaming) {
      requestAnimationFrame(() => {
        const cont = scrollRef.current;
        const anchor = anchorRef.current;
        if (!cont || !anchor) return;
        const desiredTop = Math.max(0, anchor.offsetTop - Math.round(cont.clientHeight / 3));
        targetTopRef.current = desiredTop;
        setAutoAnchor(true);
        cont.scrollTo({ top: desiredTop, behavior: "smooth" });
      });
    }
  }, [streaming]);

  // Während des Streams dezent nachführen
  useEffect(() => {
    if (!streaming || !autoAnchor) return;
    const cont = scrollRef.current;
    const t = targetTopRef.current;
    if (!cont || t == null) return;
    if (Math.abs(cont.scrollTop - t) > 40) cont.scrollTo({ top: t, behavior: "auto" });
  }, [text, streaming, autoAnchor]);

  // Nach Streamende lösen
  useEffect(() => {
    if (!streaming) {
      targetTopRef.current = null;
      setAutoAnchor(false);
    }
  }, [streaming]);

  // ==== WICHTIG: Live-Text in History mergen – nur wenn text !== '' ====
  useEffect(() => {
    if (text === "") return; // verhindert, dass am Ende/leeren Start etwas überschrieben wird
    setMessages((prev) => {
      const lastIdx = prev.length - 1;
      if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
        const copy = [...prev];
        copy[lastIdx] = { ...copy[lastIdx], content: text };
        return copy;
      }
      return [...prev, { role: "assistant", content: text }];
    });
  }, [text]); // absichtlich NUR von text abhängig

  // History während Streaming ohne die live-assistant-Zeile
  const historyMessages = useMemo(() => {
    if (!streaming || messages.length === 0) return messages;
    const last = messages[messages.length - 1];
    return last.role === "assistant" ? messages.slice(0, -1) : messages;
  }, [messages, streaming]);

  const firstName = (session?.user?.name || "").split(" ")[0] || "";
  const sendingDisabled = !isAuthed || !connected;
  const isInitial = messages.length === 0 && !hasStarted;

  const handleSend = useCallback((msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;
    setMessages((m) => [...m, { role: "user", content }]);
    setHasStarted(true);
    send(content);
    setInputValue("");
  }, [sendingDisabled, send]);

  const hasFirstToken = text.trim().length > 0;

  return (
    <div className="flex flex-col h-full w-full bg-transparent relative">
      {isInitial ? (
        <div className="flex min-h-[80vh] w-full items-center justify-center">
          <div className="w-full max-w-[768px] px-4">
            <div className="text-2xl md:text-3xl font-bold text-gray-800 text-center leading-tight select-none">
              Willkommen zurück{firstName ? `, ${firstName}` : ""}!
            </div>
            <div className="text-base md:text-lg text-gray-500 mb-3 text-center leading-snug font-medium select-none">
              Schön, dass du hier bist.
            </div>
            <div className="text-xs text-center mb-4">
              {isAuthed ? (
                connected ? <span className="text-emerald-600">WebSocket verbunden</span>
                          : <span className="text-amber-600">Verbinde WebSocket…</span>
              ) : <span className="text-gray-500">Bitte anmelden</span>}
            </div>

            <ChatInput
              value={inputValue}
              setValue={setInputValue}
              onSend={handleSend}
              onStop={() => cancel()}
              disabled={sendingDisabled}
              streaming={streaming}
              placeholder={
                isAuthed
                  ? (connected ? "Was möchtest du wissen?" : "Verbinde…")
                  : "Bitte anmelden, um zu schreiben"
              }
            />

            {!isAuthed && (
              <div className="mt-2 text-xs text-gray-500 text-center">
                Du musst angemeldet sein, um Nachrichten zu senden.
              </div>
            )}
            {lastError && (
              <div className="mt-2 text-xs text-red-500 text-center select-none">
                Fehler: {lastError}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Scroll-Container */}
          <div
            ref={scrollRef}
            onScroll={onScroll}
            onWheel={onWheel}
            onTouchStart={onTouchStart}
            className="flex-1 overflow-y-auto w-full pb-36"
            style={{ minHeight: 0 }}
          >
            <ChatHistory messages={historyMessages} />

            {/* Anker vor der Live-Bubble */}
            <div ref={anchorRef} aria-hidden />

            {/* Live-Stream-Bubble */}
            {streaming && (
              <div className="w-full max-w-[768px] mx-auto px-4 py-2">
                <div className="inline-flex items-start gap-2">
                  {!hasFirstToken ? <Thinking /> : null}
                  <div className="max-w-[680px] chat-markdown cm-assistant">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {text || (hasFirstToken ? "" : " ")}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Eingabe */}
          <div className="sticky bottom-0 left-0 right-0 z-20 flex justify-center bg-transparent pb-0 w-full">
            <div className="w-full max-w-[768px] pointer-events-auto">
              <ChatInput
                value={inputValue}
                setValue={setInputValue}
                onSend={handleSend}
                onStop={() => cancel()}
                disabled={sendingDisabled}
                streaming={streaming}
                placeholder={
                  isAuthed
                    ? (connected ? "Was möchtest du wissen?" : "Verbinde…")
                    : "Bitte anmelden, um zu schreiben"
                }
              />
              {!isAuthed && (
                <div className="mt-2 text-xs text-gray-500">
                  Du musst angemeldet sein, um Nachrichten zu senden.
                </div>
              )}
              {lastError && (
                <div className="mt-2 text-xs text-red-500 select-none">
                  Fehler: {lastError}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
