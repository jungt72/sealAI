'use client';

import { useSession } from "next-auth/react";
import { useAccessToken } from "@/lib/useAccessToken";
import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import ChatHistory from "./ChatHistory";
import Thinking from "./Thinking";
import ChatInput from "./ChatInput";
import type { Message } from "@/types/chat";
import { useChatSseV2 } from "@/lib/useChatSseV2";
import { useChatThreadId } from "@/lib/useChatThreadId";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatContainer() {
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated";

  const chatId = useChatThreadId();
  const token = useAccessToken();
  const { connected, streaming, text, lastError, confirmCheckpoint, send, cancel } =
    useChatSseV2({ chatId, token });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const [confirmActionBusy, setConfirmActionBusy] = useState(false);
  const [confirmActionError, setConfirmActionError] = useState<string | null>(null);

  useEffect(() => {
    setMessages([]);
    setHasStarted(false);
  }, [chatId]);

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
  const hasThread = Boolean(chatId);
  const sendingDisabled = !isAuthed || !connected || !hasThread;
  const isInitial = messages.length === 0 && !hasStarted;

  const handleSend = useCallback((msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;
    setMessages((m) => [...m, { role: "user", content }]);
    setHasStarted(true);
    send(content);
    setInputValue("");
    setConfirmActionError(null);
  }, [sendingDisabled, send]);

  const hasFirstToken = text.trim().length > 0;

  const missingCoreFields = useMemo(() => {
    const knownCore = ["medium", "temperature_C", "pressure_bar", "speed_rpm", "shaft_diameter"];
    const raw =
      (confirmCheckpoint as any)?.missing_core ??
      (confirmCheckpoint as any)?.missingCore ??
      (confirmCheckpoint as any)?.coverage_gaps ??
      [];
    const list = Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : [];
    const filtered = list.filter((k) => knownCore.includes(k));
    return Array.from(new Set(filtered));
  }, [confirmCheckpoint]);

  const openMissingParameterForm = useCallback(() => {
    const mapping: Record<string, string> = {
      medium: "medium",
      temperature_C: "temp_max_c",
      pressure_bar: "druck_bar",
      speed_rpm: "drehzahl_u_min",
      shaft_diameter: "wellen_mm",
    };
    const missingFormKeys = missingCoreFields
      .map((k) => mapping[k])
      .filter((v): v is string => typeof v === "string" && v.length > 0);
    window.dispatchEvent(
      new CustomEvent("sealai:ui", {
        detail: {
          ui_action: "open_form",
          action: "open_form",
          missing: missingFormKeys,
          source: "confirm_checkpoint",
        },
      }),
    );
  }, [missingCoreFields]);

  const approveConfirmGo = useCallback(async () => {
    if (!chatId) return;
    if (!token) return;
    if (confirmActionBusy) return;
    setConfirmActionBusy(true);
    setConfirmActionError(null);
    try {
      const res = await fetch("/api/v1/langgraph/confirm/go", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ chat_id: chatId, go: true }),
      });
      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        throw new Error(msg || `HTTP ${res.status}`);
      }
      setConfirmActionBusy(false);
      handleSend("Freigabe erteilt. Bitte Empfehlung ausarbeiten.");
    } catch (e: any) {
      setConfirmActionBusy(false);
      setConfirmActionError(String(e?.message || e));
    }
  }, [chatId, token, confirmActionBusy, handleSend]);

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
                !hasThread ? (
                  <span className="text-amber-600">Initialisiere Sitzung…</span>
                ) : connected ? (
                  <span className="text-emerald-600">Streaming bereit</span>
                ) : (
                  <span className="text-amber-600">Initialisiere Streaming…</span>
                )
              ) : (
                <span className="text-gray-500">Bitte anmelden</span>
              )}
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
                  ? !hasThread
                    ? "Initialisiere Sitzung…"
                    : connected
                      ? "Was möchtest du wissen?"
                      : "Initialisiere…"
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
            {confirmCheckpoint ? (
              <div className="w-full max-w-[768px] mx-auto px-4 pt-3">
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                  <div className="font-semibold">Abnahme-Checkpoint</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide">
                      Status: {confirmCheckpoint.recommendation_go ? "GO" : "NO-GO"}
                    </span>
                    {!confirmCheckpoint.recommendation_go ? (
                      <span className="text-xs">Freigabe erforderlich (bitte fehlende Kernangaben ergänzen).</span>
                    ) : (
                      <span className="text-xs">Bitte kurz bestätigen, dann kann die Empfehlung weiter ausgearbeitet werden.</span>
                    )}
                  </div>
                  {!confirmCheckpoint.recommendation_go && missingCoreFields.length > 0 ? (
                    <div className="mt-1 text-xs">
                      Fehlt (Kernfelder):{" "}
                      <span className="font-semibold">{missingCoreFields.join(", ")}</span>
                    </div>
                  ) : null}
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!token || streaming || confirmActionBusy}
                      onClick={approveConfirmGo}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {confirmActionBusy ? "Freigabe läuft…" : "Freigeben (GO)"}
                    </button>
                    <button
                      type="button"
                      disabled={streaming || confirmActionBusy}
                      onClick={() => {
                        setInputValue("Ich reiche Daten nach: ");
                        openMissingParameterForm();
                      }}
                      className="rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-amber-950 ring-1 ring-amber-300 disabled:opacity-50"
                    >
                      Daten nachreichen
                    </button>
                    {confirmActionError ? (
                      <span className="text-xs text-red-700">Freigabe fehlgeschlagen: {confirmActionError}</span>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

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
                  ? !hasThread
                    ? "Initialisiere Sitzung…"
                    : connected
                      ? "Was möchtest du wissen?"
                      : "Initialisiere…"
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
