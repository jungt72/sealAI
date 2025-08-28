"use client";

import { useSession } from "next-auth/react";
import { useEffect, useRef, useState } from "react";
import ChatHistory from "./ChatHistory";
import ChatInput from "./ChatInput";
import type { Message } from "@/types/chat";
import { useChatWs } from "@/lib/useChatWs";

export default function ChatContainer() {
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated";

  // --- WebSocket Hook (verbindet automatisch, wenn Token vorhanden) ---
  const chatId = "default";
  const { connected, streaming, text, lastError, send } = useChatWs({ chatId });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);

  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, text, streaming]);

  // WebSocket-Delta in die letzte Assistant-Message mergen
  useEffect(() => {
    if (!streaming && !text) return;
    setMessages((prev) => {
      const next = [...prev];
      const lastIdx = next.length - 1;
      if (lastIdx >= 0 && next[lastIdx].role === "assistant") {
        next[lastIdx] = { ...next[lastIdx], content: text };
        return next;
        }
      return [...next, { role: "assistant", content: text }];
    });
  }, [text, streaming]);

  const firstName = session?.user?.name?.split(" ")[0];
  const sendingDisabled = !isAuthed || !connected; // senden nur mit Auth + WS-Connect
  const isInitial = messages.length === 0 && !hasStarted;

  const handleSend = (msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;
    setMessages((m) => [...m, { role: "user", content }]);
    setHasStarted(true);
    // Startet den WS-Request; Deltas kommen über `text` rein
    send(content);
    setInputValue("");
  };

  const handleStop = () => {
    // optional: WS-Abbruch implementieren (z.B. spezielles Control-Frame)
    // aktuell: noop
  };

  if (isInitial) {
    return (
      <div className="flex h-full w-full">
        <div className="m-auto w-full max-w-[768px] px-4">
          <div className="text-2xl md:text-3xl font-bold text-gray-800 text-center leading-tight select-none">
            Willkommen zurück{firstName ? `, ${firstName}` : ""}!
          </div>
          <div className="text-base md:text-lg text-gray-500 mb-3 text-center leading-snug font-medium select-none">
            Schön, dass du hier bist.
          </div>
          <div className="text-xs text-center mb-4">
            {isAuthed ? (
              connected ? (
                <span className="text-emerald-600">WebSocket verbunden</span>
              ) : (
                <span className="text-amber-600">Verbinde WebSocket…</span>
              )
            ) : (
              <span className="text-gray-500">Bitte anmelden</span>
            )}
          </div>

          <ChatInput
            value={inputValue}
            setValue={setInputValue}
            onSend={handleSend}
            onStop={handleStop}
            disabled={sendingDisabled}
            streaming={streaming}
            placeholder={
              isAuthed
                ? connected
                  ? "Was möchtest du wissen?"
                  : "Verbinde…"
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
    );
  }

  return (
    <div className="flex flex-col h-full w-full bg-transparent relative">
      <div className="flex-1 flex justify-center overflow-hidden">
        <div className="w-full max-w-[768px] mx-auto flex flex-col h-full">
          <div className="flex items-center justify-between px-1 pb-1 text-xs text-gray-500">
            <span>
              {connected ? "WS: verbunden" : "WS: verbinden…"}
              {streaming ? " · streamt…" : ""}
            </span>
            {lastError ? <span className="text-red-500">Fehler: {lastError}</span> : null}
          </div>

          <div className="flex-1 overflow-y-auto w-full pb-36" style={{ minHeight: 0 }}>
            <ChatHistory messages={messages} />
            <div ref={endRef} />
          </div>

          <div className="sticky bottom-0 left-0 right-0 z-20 flex justify-center bg-transparent pb-0 w-full">
            <div className="w-full max-w-[768px] pointer-events-auto">
              <ChatInput
                value={inputValue}
                setValue={setInputValue}
                onSend={handleSend}
                onStop={handleStop}
                disabled={sendingDisabled}
                streaming={streaming}
                placeholder={
                  isAuthed
                    ? connected
                      ? "Was möchtest du wissen?"
                      : "Verbinde…"
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
        </div>
      </div>
    </div>
  );
}
