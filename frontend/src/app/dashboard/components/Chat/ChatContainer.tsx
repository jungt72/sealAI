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
import { fetchV2StateParameters, patchV2Parameters } from "@/lib/v2ParameterPatch";
import { applyParametersWithChatMessage } from "@/lib/parameterApplyChat";
import {
  buildDirtyPatch,
  cleanParameterPatch,
  mergeServerParameters,
  reconcileDirtyWithServer,
  type ParameterSyncState,
} from "@/lib/parameterSync";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import ParameterFormSidebar from "./ParameterFormSidebar";
import type { SealParameters } from "@/lib/types/sealParameters";

type ChatContainerProps = {
  chatId?: string | null;
};

function coerceValue(v: string): string | number {
  const t = v.trim();
  if (!t) return "";
  const n = Number(t.replace(",", "."));
  if (Number.isFinite(n) && String(n) !== "NaN") return n;
  return t;
}

// Unterstützt: "/param key=value key2=value2"
function parseParamCommand(input: string): Partial<SealParameters> | null {
  const trimmed = input.trim();
  if (!trimmed.toLowerCase().startsWith("/param ")) return null;
  const rest = trimmed.slice(7).trim();
  if (!rest) return {};
  const out: Record<string, any> = {};
  for (const part of rest.split(/\s+/g)) {
    const idx = part.indexOf("=");
    if (idx <= 0) continue;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (!k) continue;
    out[k] = coerceValue(v);
  }
  return out as Partial<SealParameters>;
}

export default function ChatContainer({ chatId: chatIdProp }: ChatContainerProps) {
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated";

  const preferredChatId = (chatIdProp ?? "").trim() || null;
  const storedChatId = useChatThreadId(preferredChatId);
  const chatId = preferredChatId ?? storedChatId;
  const token = useAccessToken();
  const {
    connected,
    streaming,
    text,
    lastError,
    confirmCheckpoint,
    send,
    cancel,
    lastEventId,
    lastDoneEvent,
  } = useChatSseV2({ chatId, token });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const [confirmActionBusy, setConfirmActionBusy] = useState(false);
  const [confirmActionError, setConfirmActionError] = useState<string | null>(null);

  // ===== Voll-Parameter-State (für 1:1 Sync) =====
  const [paramState, setParamState] = useState<ParameterSyncState>({
    values: {},
    dirty: new Set(),
  });
  const parameters = paramState.values;
  const [showParamDrawer, setShowParamDrawer] = useState(false);
  const [paramToast, setParamToast] = useState<string | null>(null);
  const prevStreamForStateRef = useRef(false);
  const paramQueueRef = useRef<Promise<void>>(Promise.resolve());
  const stateAbortRef = useRef<AbortController | null>(null);
  const patchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paramSyncTokenRef = useRef(0);
  const chatIdRef = useRef<string | null>(chatId);
  const lastSseEventIdRef = useRef<string | null>(null);
  const autoPatchOnChange = process.env.NEXT_PUBLIC_AUTO_PATCH_PARAMS === "1";
  const paramSyncDebug = process.env.NEXT_PUBLIC_PARAM_SYNC_DEBUG === "1";

  useEffect(() => {
    paramSyncTokenRef.current += 1;
    chatIdRef.current = chatId;
    setMessages([]);
    setHasStarted(false);
    setParamState({ values: {}, dirty: new Set() });
    setShowParamDrawer(false);
    setParamToast(null);
    paramQueueRef.current = Promise.resolve();
    stateAbortRef.current?.abort();
    stateAbortRef.current = null;
    lastSseEventIdRef.current = null;
    if (patchDebounceRef.current) {
      clearTimeout(patchDebounceRef.current);
      patchDebounceRef.current = null;
    }
  }, [chatId]);

  useEffect(() => {
    return () => {
      stateAbortRef.current?.abort();
      if (patchDebounceRef.current) {
        clearTimeout(patchDebounceRef.current);
        patchDebounceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    lastSseEventIdRef.current = lastEventId ?? null;
  }, [lastEventId]);

  // ===== Öffnen per UI-Event (wie früher) =====
  const applyLocalParameters = useCallback(
    (patch: Partial<SealParameters>, opts?: { markDirty?: boolean; clearDirty?: boolean }) => {
      if (!patch || typeof patch !== "object") return;
      const { markDirty = false, clearDirty = false } = opts || {};
      setParamState((prev) => {
        const nextValues = { ...prev.values, ...patch };
        const nextDirty = new Set(prev.dirty);
        const keys = Object.keys(patch) as (keyof SealParameters)[];
        if (markDirty) {
          for (const key of keys) nextDirty.add(key);
        }
        if (clearDirty) {
          for (const key of keys) nextDirty.delete(key);
        }
        return { values: nextValues, dirty: nextDirty };
      });
    },
    [],
  );

  const applyServerParameters = useCallback((next: SealParameters, eventId?: string | null) => {
    setParamState((prev) => {
      const merged = mergeServerParameters(prev.values, next, prev.dirty);
      const nextDirty = reconcileDirtyWithServer(prev.values, next, prev.dirty);
      if (paramSyncDebug) {
        const incomingKeys = Object.keys(next || {});
        console.log("[param-sync] store_apply", {
          chat_id: chatId,
          incoming_keys: incomingKeys.slice(0, 8),
          incoming_keys_count: incomingKeys.length,
          incoming_pressure_bar: (next as SealParameters).pressure_bar,
          merged_pressure_bar: merged.pressure_bar,
          dirty_keys: Array.from(nextDirty).slice(0, 8),
        });
      }
      return {
        values: merged,
        dirty: nextDirty,
        lastServerEventId: eventId ?? prev.lastServerEventId ?? null,
      };
    });
  }, [chatId, paramSyncDebug]);

  useEffect(() => {
    const onUi = (ev: Event) => {
      const ua: any = (ev as CustomEvent<any>).detail ?? (ev as any);
      const action = ua?.ui_action ?? ua?.action ?? ua?.event;
      if (action === "open_form") setShowParamDrawer(true);

      // optional: prefill/params mergen
      const pre = ua?.prefill ?? ua?.params;
      if (pre && typeof pre === "object") {
        applyLocalParameters(pre, { markDirty: false });
      }
    };
    window.addEventListener("sealai:ui", onUi as EventListener);
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    window.addEventListener("sealai:form:patch", onUi as EventListener);
    return () => {
      window.removeEventListener("sealai:ui", onUi as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
      window.removeEventListener("sealai:form:patch", onUi as EventListener);
    };
  }, [applyLocalParameters]);

  const enqueueParamTask = useCallback(<T,>(task: (tokenId: number) => Promise<T>) => {
    const tokenId = paramSyncTokenRef.current;
    const next = paramQueueRef.current.catch(() => undefined).then(() => task(tokenId));
    paramQueueRef.current = next.then(() => undefined, () => undefined);
    return next;
  }, []);

  const shouldAbortParamTask = useCallback((tokenId: number, expectedChatId: string | null) => {
    if (tokenId !== paramSyncTokenRef.current) return true;
    if (!expectedChatId || chatIdRef.current !== expectedChatId) return true;
    return false;
  }, []);

  const runRefresh = useCallback(async (opts: {
    expectedChatId: string;
    token: string;
    patchedKeysCount: number;
    tokenId: number;
    expectedEventId?: string | null;
  }) => {
    const { expectedChatId, token, patchedKeysCount, tokenId, expectedEventId } = opts;
    if (shouldAbortParamTask(tokenId, expectedChatId)) return;
    stateAbortRef.current?.abort();
    const controller = new AbortController();
    stateAbortRef.current = controller;
    try {
      const next = await fetchV2StateParameters({
        chatId: expectedChatId,
        token,
        signal: controller.signal,
      });
      if (shouldAbortParamTask(tokenId, expectedChatId)) return;
      applyServerParameters(next as SealParameters, expectedEventId ?? null);
      if (paramSyncDebug) {
        const refreshedKeysCount = Object.keys(next || {}).length;
        console.log({
          chat_id: expectedChatId,
          patched_keys_count: patchedKeysCount,
          refreshed_keys_count: refreshedKeysCount,
        });
      }
    } finally {
      if (stateAbortRef.current === controller) {
        stateAbortRef.current = null;
      }
    }
  }, [applyServerParameters, paramSyncDebug, shouldAbortParamTask]);

  const refreshParameters = useCallback(async (opts?: { expectedEventId?: string | null }) => {
    if (!chatId || !token) return;
    return enqueueParamTask(async (tokenId) => {
      await runRefresh({
        expectedChatId: chatId,
        token,
        patchedKeysCount: 0,
        tokenId,
        expectedEventId: opts?.expectedEventId ?? null,
      });
    });
  }, [chatId, token, enqueueParamTask, runRefresh]);

  // ===== Backend Patch (übernimmt "Parameter übernehmen") =====
  const patchAllParameters = useCallback(async (patch: Partial<SealParameters>) => {
    if (!chatId || !token) return;
    const cleaned = cleanParameterPatch(patch);
    if (!Object.keys(cleaned).length) return;

    try {
      const patchedKeysCount = Object.keys(cleaned).length;
      await enqueueParamTask(async (tokenId) => {
        if (shouldAbortParamTask(tokenId, chatId)) return;
        await patchV2Parameters({
          chatId,
          token,
          parameters: cleaned,
        });
        await runRefresh({ expectedChatId: chatId, token, patchedKeysCount, tokenId });
      });
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      throw e;
    }
  }, [chatId, token, enqueueParamTask, runRefresh, shouldAbortParamTask]);

  const schedulePatchOnChange = useCallback((next: SealParameters) => {
    if (!autoPatchOnChange) return;
    if (patchDebounceRef.current) clearTimeout(patchDebounceRef.current);
    patchDebounceRef.current = setTimeout(() => {
      patchAllParameters(next).catch((err) => {
        if (err?.name === "AbortError") return;
        console.warn("[param-sync] debounced_patch_failed", err);
      });
    }, 350);
  }, [autoPatchOnChange, patchAllParameters]);

  const onParamUpdate = useCallback((name: keyof SealParameters, value: string | number) => {
    if (paramSyncDebug) {
      const normalized = cleanParameterPatch({ [name]: value });
      const normalizedValue =
        Object.prototype.hasOwnProperty.call(normalized, name) ? normalized[name] : undefined;
      console.log("[param-sync] input_change", {
        chat_id: chatId,
        field: name,
        raw_value: value,
        normalized_value: normalizedValue,
      });
    }
    setParamState((prev) => {
      const nextValues = { ...prev.values, [name]: value };
      const nextDirty = new Set(prev.dirty);
      nextDirty.add(name);
      schedulePatchOnChange(nextValues);
      return { values: nextValues, dirty: nextDirty };
    });
  }, [chatId, paramSyncDebug, schedulePatchOnChange]);

  const onParamSubmit = useCallback(async () => {
    try {
      const cleaned = cleanParameterPatch(buildDirtyPatch(paramState.values, paramState.dirty));
      if (paramSyncDebug) {
        console.log("[param-sync] applyParameters clicked", {
          chat_id: chatId,
          dirty_keys: Array.from(paramState.dirty),
          payload_keys: Object.keys(cleaned),
        });
      }
      if (!Object.keys(cleaned).length) {
        setParamToast("Keine Änderungen");
        window.setTimeout(() => setParamToast(null), 1200);
        return;
      }
      const metadata = {
        source: "param_apply",
        kind: "parameter_summary",
        keys: Object.keys(cleaned),
      };

      const canSendChatMessage = isAuthed && connected && Boolean(chatId);
      const { summary } = await applyParametersWithChatMessage({
        patch: cleaned,
        patchParameters: patchAllParameters,
        sendChatMessage: (content, meta) => {
          if (!canSendChatMessage) return;
          setMessages((m) => [...m, { role: "user", content }]);
          setHasStarted(true);
          send(content, meta);
          setConfirmActionError(null);
        },
        metadata,
      });

      if (paramSyncDebug) {
        console.log("[param-sync] applyParameters patched", {
          chat_id: chatId,
          patched_keys: Object.keys(cleaned),
        });
        if (summary && canSendChatMessage) {
          console.log("[param-sync] sending chat message due to parameter apply", {
            chat_id: chatId,
            endpoint: "/api/chat",
            preview: summary.slice(0, 140),
          });
        }
      }
      setParamState((prev) => {
        const nextDirty = new Set(prev.dirty);
        for (const key of Object.keys(cleaned) as (keyof SealParameters)[]) {
          nextDirty.delete(key);
        }
        return { values: prev.values, dirty: nextDirty };
      });
      setParamToast("Parameter aktualisiert");
      window.setTimeout(() => setParamToast(null), 1500);
    } catch (e: any) {
      setParamToast(`Update fehlgeschlagen: ${String(e?.message || e)}`);
      window.setTimeout(() => setParamToast(null), 2500);
    }
  }, [chatId, paramState, paramSyncDebug, patchAllParameters, send, isAuthed, connected]);

  useEffect(() => {
    if (!chatId || !token) return;
    refreshParameters({ expectedEventId: lastEventId ?? null }).catch((err) => {
      if (err?.name === "AbortError") return;
      console.warn("[param-sync] initial_state_fetch_failed", err);
    });
  }, [chatId, token, lastEventId, refreshParameters]);

  useEffect(() => {
    const wasStreaming = prevStreamForStateRef.current;
    if (wasStreaming && !streaming) {
      refreshParameters({ expectedEventId: lastEventId ?? null }).catch((err) => {
        if (err?.name === "AbortError") return;
        console.warn("[param-sync] post_stream_state_fetch_failed", err);
      });
    }
    prevStreamForStateRef.current = streaming;
  }, [streaming, lastEventId, refreshParameters]);

  useEffect(() => {
    if (!lastDoneEvent || !chatId) return;
    const doneChatId = String(lastDoneEvent.data?.chat_id || "");
    if (!doneChatId || doneChatId !== chatId) return;
    refreshParameters({ expectedEventId: lastDoneEvent.id ?? null }).catch((err) => {
      if (err?.name === "AbortError") return;
      console.warn("[param-sync] done_event_state_fetch_failed", err);
    });
  }, [lastDoneEvent, chatId, refreshParameters]);

  // ===== Scroll "anchor-then-hold" =====
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

  useEffect(() => {
    if (!streaming || !autoAnchor) return;
    const cont = scrollRef.current;
    const t = targetTopRef.current;
    if (!cont || t == null) return;
    if (Math.abs(cont.scrollTop - t) > 40) cont.scrollTo({ top: t, behavior: "auto" });
  }, [text, streaming, autoAnchor]);

  useEffect(() => {
    if (!streaming) {
      targetTopRef.current = null;
      setAutoAnchor(false);
    }
  }, [streaming]);

  // ===== Live-Text in History mergen =====
  useEffect(() => {
    if (text === "") return;
    setMessages((prev) => {
      const lastIdx = prev.length - 1;
      if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
        const copy = [...prev];
        copy[lastIdx] = { ...copy[lastIdx], content: text };
        return copy;
      }
      return [...prev, { role: "assistant", content: text }];
    });
  }, [text]);

  const historyMessages = useMemo(() => {
    if (!streaming || messages.length === 0) return messages;
    const last = messages[messages.length - 1];
    return last.role === "assistant" ? messages.slice(0, -1) : messages;
  }, [messages, streaming]);

  const firstName = (session?.user?.name || "").split(" ")[0] || "";
  const hasThread = Boolean(chatId);
  const sendingDisabled = !isAuthed || !connected || !hasThread;
  const isInitial = messages.length === 0 && !hasStarted;

  const handleSend = useCallback(async (msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;

    // 1) Parameter direkt im Chat setzen: "/param pressure_bar=5 temperature_C=50 ..."
    const parsed = parseParamCommand(content);
    if (parsed) {
      applyLocalParameters(parsed, { clearDirty: true });

      // sofort patchen, damit Backend + UI synchron bleiben
      try {
        await patchAllParameters(parsed);
        setParamToast("Parameter aktualisiert");
        window.setTimeout(() => setParamToast(null), 1200);
      } catch (e: any) {
        setParamToast(`Update fehlgeschlagen: ${String(e?.message || e)}`);
        window.setTimeout(() => setParamToast(null), 2500);
      }

      // optional: Chat-Log Eintrag
      setMessages((m) => [...m, { role: "user", content: `Parameter gesetzt: ${Object.keys(parsed).join(", ")}` }]);
      setHasStarted(true);
      setInputValue("");
      setConfirmActionError(null);
      return;
    }

    // normaler Chat
    setMessages((m) => [...m, { role: "user", content }]);
    setHasStarted(true);
    send(content);
    setInputValue("");
    setConfirmActionError(null);
  }, [sendingDisabled, send, patchAllParameters, applyLocalParameters]);

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
    setShowParamDrawer(true);
    window.dispatchEvent(
      new CustomEvent("sealai:ui", {
        detail: { ui_action: "open_form", action: "open_form", missing: missingCoreFields, source: "confirm_checkpoint" },
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
      {/* Toggle Button rechts (wie “aufschiebbare” Sidebar) */}
      <button
        type="button"
        onClick={() => setShowParamDrawer(true)}
        className="absolute top-3 right-3 z-30 rounded-md bg-white/90 hover:bg-white border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-sm"
        title="Technische Parameter"
        aria-label="Technische Parameter"
      >
        Parameter
      </button>

      {/* Toast */}
      {paramToast ? (
        <div className="absolute top-14 right-3 z-30 rounded-md bg-indigo-600 text-white text-xs font-semibold px-3 py-2 shadow">
          {paramToast}
        </div>
      ) : null}

      {/* Drawer Overlay rechts */}
      <div
        className={[
          "fixed inset-0 z-40",
          showParamDrawer ? "pointer-events-auto" : "pointer-events-none",
        ].join(" ")}
        aria-hidden={!showParamDrawer}
      >
        <div
          className={[
            "absolute inset-0 bg-slate-900/30 transition-opacity duration-300 ease-out",
            showParamDrawer ? "opacity-100" : "opacity-0",
          ].join(" ")}
          onClick={() => setShowParamDrawer(false)}
        />
        <div
          className={[
            "absolute right-0 top-0 h-full",
            "transform transition-transform duration-300 ease-out will-change-transform",
            showParamDrawer ? "translate-x-0" : "translate-x-full",
          ].join(" ")}
        >
          <ParameterFormSidebar
            show={showParamDrawer}
            parameters={parameters}
            onUpdate={onParamUpdate}
            onSubmit={onParamSubmit}
            onClose={() => setShowParamDrawer(false)}
          />
        </div>
      </div>

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
                      Fehlt (Kernfelder): <span className="font-semibold">{missingCoreFields.join(", ")}</span>
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

            <div ref={anchorRef} aria-hidden />

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
