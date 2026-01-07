'use client';

import { signIn, useSession } from "next-auth/react";
import { usePathname } from "next/navigation";
import { fetchFreshAccessToken, useAccessToken } from "@/lib/useAccessToken";
import { fetchWithAuth } from "@/lib/fetchWithAuth";
import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import ChatHistory from "./ChatHistory";
import ChatInput from "./ChatInput";
import type { Message } from "@/types/chat";
import { useChatSseV2 } from "@/lib/useChatSseV2";
import { useChatThreadId } from "@/lib/useChatThreadId";
import { fetchV2StateParameters, patchV2Parameters } from "@/lib/v2ParameterPatch";
import { applyParametersWithChatMessage } from "@/lib/parameterApplyChat";
import QualityMetaPanel from "@/app/dashboard/components/QualityMetaPanel";
import {
  buildDirtyPatch,
  cleanParameterPatch,
  emitParamPatchTelemetry,
  areParamValuesEquivalent,
  type ParameterMeta,
  type ParameterPatchAckPayload,
} from "@/lib/parameterSync";
import { useParamStore } from "@/lib/stores/paramStore";
import { toRelativeCallbackUrl } from "@/lib/utils";

import ParameterFormSidebar from "./ParameterFormSidebar";
import type { SealParameters } from "@/lib/types/sealParameters";
import type { ChatMeta } from "@/types/chatMeta";
import StreamingMessage, { type StreamingMessageHandle } from "./StreamingMessage";
import { isParamSyncDebug } from "@/lib/paramSyncDebug";

type ChatContainerProps = {
  chatId?: string | null;
};

type LanggraphState = Record<string, unknown> & {
  parameters?: Record<string, unknown>;
  parameter_meta?: Record<string, unknown>;
};

const THREAD_STORAGE_PREFIX = "sealai:thread:";

export const clearAllThreadStorage = (): number => {
  if (typeof window === "undefined") return 0;
  const keys: string[] = [];
  for (let i = 0; i < sessionStorage.length; i += 1) {
    const key = sessionStorage.key(i);
    if (key && key.startsWith(THREAD_STORAGE_PREFIX)) keys.push(key);
  }
  for (const key of keys) {
    sessionStorage.removeItem(key);
  }
  return keys.length;
};

export const normalizeIncomingParameters = (raw: Record<string, unknown>): Partial<SealParameters> => {
  const normalized: Record<string, unknown> = { ...raw };
  if ("pressure" in normalized) {
    if (normalized.pressure !== undefined && normalized.pressure !== null) {
      normalized.pressure_bar = normalized.pressure;
    }
    delete normalized.pressure;
  }
  return normalized as Partial<SealParameters>;
};

const normalizeIncomingParameterMeta = (raw: Record<string, unknown>): ParameterMeta => {
  const normalized: Record<string, unknown> = { ...raw };
  if ("pressure" in normalized) {
    normalized.pressure_bar = normalized.pressure;
    delete normalized.pressure;
  }
  return normalized as ParameterMeta;
};

const normalizeIncomingParameterVersions = (
  raw: unknown,
): Partial<Record<keyof SealParameters, number>> => {
  if (!raw || typeof raw !== "object") return {};
  const out: Partial<Record<keyof SealParameters, number>> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    out[key as keyof SealParameters] = value;
  }
  return out;
};

const normalizeIncomingParameterUpdatedAt = (
  raw: unknown,
): Partial<Record<keyof SealParameters, number>> => {
  if (!raw || typeof raw !== "object") return {};
  const out: Partial<Record<keyof SealParameters, number>> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    out[key as keyof SealParameters] = value;
  }
  return out;
};

const extractParametersFromDelta = (delta: Record<string, unknown>): Partial<SealParameters> | null => {
  if (!delta || typeof delta !== "object") return null;
  const direct =
    delta.parameters && typeof delta.parameters === "object"
      ? (delta.parameters as Record<string, unknown>)
      : null;
  if (direct) return normalizeIncomingParameters(direct);
  const nestedState =
    delta.state && typeof delta.state === "object" ? (delta.state as Record<string, unknown>) : null;
  if (nestedState && nestedState.parameters && typeof nestedState.parameters === "object") {
    return normalizeIncomingParameters(nestedState.parameters as Record<string, unknown>);
  }
  return null;
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

function parseParamEdits(input: string): Partial<SealParameters> | null {
  if (!input) return null;
  const out: Record<string, any> = {};
  for (const rawLine of input.split(/\n|,/g)) {
    const line = rawLine.trim();
    if (!line) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (!key) continue;
    out[key] = coerceValue(value);
  }
  return out as Partial<SealParameters>;
}

const normalizeStatePayload = (body: any): LanggraphState | null => {
  if (!body || typeof body !== "object") return null;
  const state = body.state && typeof body.state === "object" ? { ...(body.state as Record<string, unknown>) } : {};
  const parameters =
    body.parameters && typeof body.parameters === "object"
      ? (body.parameters as Record<string, unknown>)
      : undefined;
  const normalized: LanggraphState = { ...state };
  if (parameters) normalized.parameters = parameters;
  return Object.keys(normalized).length ? normalized : null;
};

const mergeState = (prev: LanggraphState | null, delta: LanggraphState | null): LanggraphState | null => {
  if (!delta || typeof delta !== "object") return prev;
  if (!prev || typeof prev !== "object") return { ...(delta as LanggraphState) };
  const prevParams = prev.parameters && typeof prev.parameters === "object" ? prev.parameters : {};
  const nextParams = delta.parameters && typeof delta.parameters === "object" ? delta.parameters : null;
  return {
    ...prev,
    ...delta,
    ...(nextParams ? { parameters: { ...prevParams, ...nextParams } } : {}),
  };
};

export default function ChatContainer({ chatId: chatIdProp }: ChatContainerProps) {
  const { data: session, status: authStatus } = useSession();
  const pathname = usePathname();
  const isAuthed = authStatus === "authenticated";
  const tokenExpiresAt = (session as any)?.expires_at ?? null;

  const urlConversationId = useMemo(() => {
    const segments = (pathname ?? "").split("/").filter(Boolean);
    if (segments[0] !== "chat") return null;
    return segments[1] ?? null;
  }, [pathname]);
  const preferredChatId = (urlConversationId ?? chatIdProp ?? "").trim() || null;
  const storedChatId = useChatThreadId(preferredChatId);
  const chatId = preferredChatId ?? storedChatId;
  const { token, error: tokenError } = useAccessToken();
  const {
    parameters,
    versions: parameterVersions,
    updatedAt: parameterUpdatedAt,
    initChat: initParamChat,
    replaceFromServer: replaceParamFromServer,
    applyPatchAck: applyParamPatchAck,
    applyLocalEdit, // ✅ FIX: needed below
    applyServerParams,
    getSnapshot: getParamSnapshot,
  } = useParamStore(chatId);

  const streamingRef = useRef<StreamingMessageHandle | null>(null);
  const [chatMeta, setChatMeta] = useState<ChatMeta | null>(null);
  const clearRagSources = useCallback(() => {
    setChatMeta((prev) => {
      if (!prev) return null;
      const next = { ...prev };
      delete next.ragSources;
      return Object.keys(next).length ? next : null;
    });
  }, []);
  const handleStreamToken = useCallback((chunk: string) => {
    streamingRef.current?.append(chunk);
  }, []);
  const handleStreamStart = useCallback(
    (isRetry: boolean) => {
      if (!isRetry) streamingRef.current?.reset();
      if (!isRetry) clearRagSources();
    },
    [clearRagSources],
  );
  const handleStreamDone = useCallback((finalText: string) => {
    if (finalText && finalText.trim()) {
      setMessages((m) => [...m, { role: "assistant", content: finalText }]);
      window.dispatchEvent(
        new CustomEvent("sealai:conversations:invalidate", {
          detail: { reason: "message_committed" },
        }),
      );
    }
    streamingRef.current?.reset();
  }, []);

  const [authExpired, setAuthExpired] = useState(false);
  const applyServerParametersRef = useRef<((next: SealParameters, eventId?: string | null, meta?: ParameterMeta) => void) | null>(null);
  const prevUrlConversationIdRef = useRef<string | null>(urlConversationId ?? null);

  useEffect(() => {
    if (tokenError === "expired") {
      setAuthExpired(true);
      return;
    }
    if (tokenError === "missing") {
      if (authStatus !== "authenticated") {
        setAuthExpired(false);
        return;
      }
      void fetchFreshAccessToken().then((fresh) => {
        if (fresh.status === 401 || fresh.error === "expired") {
          setAuthExpired(true);
          return;
        }
        if (fresh.token) {
          setAuthExpired(false);
        }
      });
      return;
    }
    setAuthExpired(false);
  }, [tokenError, authStatus]);

  useEffect(() => {
    if (!authExpired) return;
    window.dispatchEvent(
      new CustomEvent("sealai:conversations:invalidate", {
        detail: { reason: "auth_expired" },
      }),
    );
  }, [authExpired]);

  const refreshTokenForSse = useCallback(async () => {
    const fresh = await fetchFreshAccessToken();
    if (fresh.status === 401 || fresh.error === "expired") {
      setAuthExpired(true);
      return null;
    }
    if (fresh.token) {
      setAuthExpired(false);
      return fresh.token;
    }
    return null;
  }, []);

  const resyncStateFromServer = (reason: string) => {
    const expectedChatId = chatId;
    const expectedToken = token;
    if (!expectedChatId || !expectedToken) return;
    currentStateAbortRef.current?.abort();
    const controller = new AbortController();
    currentStateAbortRef.current = controller;
    fetchWithAuth(`/api/langgraph/state?thread_id=${encodeURIComponent(expectedChatId)}`, expectedToken, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json().catch(() => null);
      })
      .then((body) => {
        if (!body || controller.signal.aborted) return;
        if (chatIdRef.current !== expectedChatId) return;
        const normalized = normalizeStatePayload(body);
        updateCurrentState(normalized);
        syncCurrentStateParameters(normalized);
        const state = body.state && typeof body.state === "object" ? body.state : {};
        const versions = normalizeIncomingParameterVersions(
          (state as Record<string, unknown>).parameter_versions,
        );
        const updatedAt = normalizeIncomingParameterUpdatedAt(
          (state as Record<string, unknown>).parameter_updated_at,
        );
        const params =
          normalized?.parameters && typeof normalized.parameters === "object"
            ? normalizeIncomingParameters(normalized.parameters as Record<string, unknown>)
            : {};
        replaceParamFromServer({
          chatId: expectedChatId,
          parameters: params as SealParameters,
          versions,
          updatedAt,
        });
      })
      .catch((err) => {
        console.warn("[param-sync] resync_failed", { reason, err });
      })
      .finally(() => {
        if (currentStateAbortRef.current === controller) {
          currentStateAbortRef.current = null;
        }
      });
  };

  const {
    status: sseStatus,
    streaming,
    lastError,
    confirmCheckpoint,
    send,
    cancel,
    lastEventId,
    lastDoneEvent,
    reconnect,
  } = useChatSseV2({
    chatId,
    token,
    tokenExpiresAt,
    refreshAccessToken: refreshTokenForSse,
    getClientContext: () => {
      const snapshot = getParamSnapshot(chatId);
      if (!snapshot) return null;
      return { param_snapshot: snapshot };
    },
    onToken: handleStreamToken,
    onStart: handleStreamStart,
    onDone: handleStreamDone,
    onAuthExpired: () => {
      void fetchFreshAccessToken().then((fresh) => {
        if (fresh.status === 401 || fresh.error === "expired") {
          setAuthExpired(true);
          return;
        }
        if (fresh.token) {
          setAuthExpired(false);
        }
      });
    },
    onStateDelta: (delta, meta, payload) => {
      if (chatIdRef.current && chatIdRef.current !== chatId) return;
      const nextState = mergeState(currentStateRef.current, delta);
      updateCurrentState(nextState);
      syncCurrentStateParameters(nextState, meta?.id ?? null);
      const params = extractParametersFromDelta(delta);
      const rawMeta =
        payload?.parameter_meta && typeof payload.parameter_meta === "object"
          ? (payload.parameter_meta as Record<string, unknown>)
          : payload?.delta && typeof payload.delta === "object" && (payload.delta as any).parameter_meta
            ? ((payload.delta as any).parameter_meta as Record<string, unknown>)
            : delta?.parameter_meta && typeof delta.parameter_meta === "object"
              ? (delta.parameter_meta as Record<string, unknown>)
              : null;
      const metaPayload = rawMeta ? normalizeIncomingParameterMeta(rawMeta) : undefined;
      if (metaPayload) {
        lastParamMetaRef.current = {
          eventId: meta?.id ?? null,
          meta: metaPayload,
        };
      }
      if (params && Object.keys(params).length) {
        if (paramSyncDebug) {
          console.log("[param-sync] sse_state_update", {
            chat_id: chatId,
            event: meta?.event,
            event_id: meta?.id ?? null,
            keys: Object.keys(params),
          });
        }
        lastParamEventIdRef.current = meta?.id ?? null;
      }
    },
    onRetrievalMeta: ({ sources, skipped }) => {
      if (chatIdRef.current && chatIdRef.current !== chatId) return;
      if (skipped || !sources.length) {
        clearRagSources();
        return;
      }
      setChatMeta((prev) => ({ ...(prev ?? {}), ragSources: sources }));
    },
    onEvent: (evt) => {
      if (!evt?.event || !evt.data || typeof evt.data !== "object") return;
      if (chatIdRef.current && chatIdRef.current !== chatId) return;
      if (evt.event === "parameter_patch_ack") {
        const payload = evt.data as ParameterPatchAckPayload;
        if (chatId) {
          applyParamPatchAck(chatId, payload);
        }
        if ((payload.rejected_fields || []).length) {
          resyncStateFromServer("rejected_fields");
        }
      }
      if (evt.event === "resync_required") {
        resyncStateFromServer("resync_required");
      }
      if (evt.event === "slow_client") {
        console.warn("[sse] slow_client", { chat_id: chatId });
      }
    },
  });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const [confirmActionBusy, setConfirmActionBusy] = useState(false);
  const [confirmActionError, setConfirmActionError] = useState<string | null>(null);
  const [dismissedCheckpointId, setDismissedCheckpointId] = useState<string | null>(null);
  const [showConfirmEdit, setShowConfirmEdit] = useState(false);
  const [confirmEditInstructions, setConfirmEditInstructions] = useState("");
  const [confirmEditParams, setConfirmEditParams] = useState("");
  const snapshotMaxVersion = useMemo(() => {
    const versions = Object.values(parameterVersions || {});
    if (!versions.length) return 0;
    return Math.max(0, ...versions.filter((value) => Number.isFinite(value)));
  }, [parameterVersions]);
  const snapshotMaxUpdatedAt = useMemo(() => {
    const updated = Object.values(parameterUpdatedAt || {});
    if (!updated.length) return null;
    const maxValue = Math.max(...updated.filter((value) => Number.isFinite(value)));
    return Number.isFinite(maxValue) && maxValue > 0 ? maxValue : null;
  }, [parameterUpdatedAt]);
  const snapshotLabel = useMemo(() => {
    if (!snapshotMaxVersion) return null;
    if (!snapshotMaxUpdatedAt) return `Parameter-Stand: v${snapshotMaxVersion}`;
    const ts = new Date(snapshotMaxUpdatedAt * 1000);
    return `Parameter-Stand: v${snapshotMaxVersion} · ${ts.toLocaleString()}`;
  }, [snapshotMaxUpdatedAt, snapshotMaxVersion]);

  useEffect(() => {
    if (!confirmCheckpoint?.checkpoint_id) return;
    setDismissedCheckpointId((prev) =>
      prev && prev !== confirmCheckpoint.checkpoint_id ? null : prev,
    );
  }, [confirmCheckpoint?.checkpoint_id]);

  const paramsRef = useRef<SealParameters>({});
  const versionsRef = useRef<Partial<Record<keyof SealParameters, number>>>({});
  const [showParamDrawer, setShowParamDrawer] = useState(false);
  const [userClosedDrawer, setUserClosedDrawer] = useState(false);
  const [paramToast, setParamToast] = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<LanggraphState | null>(null);
  const currentStateRef = useRef<LanggraphState | null>(null);
  const updateCurrentState = useCallback(
    (next: LanggraphState | null) => {
      currentStateRef.current = next;
      setCurrentState(next);
    },
    [setCurrentState],
  );
  const syncCurrentStateParameters = useCallback((next: LanggraphState | null, eventId?: string | null) => {
    const raw = next?.parameters;
    if (!raw || typeof raw !== "object") return;
    const normalized = normalizeIncomingParameters(raw as Record<string, unknown>);
    if (!Object.keys(normalized).length) return;
    applyServerParametersRef.current?.(normalized as SealParameters, eventId ?? null);
  }, []);
  const prevStreamForStateRef = useRef(false);
  const paramQueueRef = useRef<Promise<void>>(Promise.resolve());
  const stateAbortRef = useRef<AbortController | null>(null);
  const currentStateAbortRef = useRef<AbortController | null>(null);
  const numericPatchTimersRef = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});
  const paramSyncTokenRef = useRef(0);
  const chatIdRef = useRef<string | null>(chatId);
  const lastSseEventIdRef = useRef<string | null>(null);
  const lastParamEventIdRef = useRef<string | null>(null);
  const prevParamValuesRef = useRef<SealParameters>({});
  const paramSyncDebug = isParamSyncDebug();
  const lastParamMetaRef = useRef<{ eventId: string | null; meta: ParameterMeta } | null>(null);

  useEffect(() => {
    paramsRef.current = parameters ?? {};
  }, [parameters]);

  useEffect(() => {
    versionsRef.current = parameterVersions ?? {};
  }, [parameterVersions]);

  useEffect(() => {
    const prevUrlId = prevUrlConversationIdRef.current;
    if (prevUrlId === urlConversationId) return;
    if (prevUrlId) {
      const removedCount = clearAllThreadStorage();
      if (paramSyncDebug) {
        console.log("[param-sync] hard_reset", {
          prev_url_conversation_id: prevUrlId,
          next_url_conversation_id: urlConversationId ?? null,
          removed_thread_keys: removedCount,
        });
      }
      cancel();
      stateAbortRef.current?.abort();
      stateAbortRef.current = null;
      currentStateAbortRef.current?.abort();
      currentStateAbortRef.current = null;
      updateCurrentState(null);
      lastSseEventIdRef.current = null;
      lastParamEventIdRef.current = null;
      lastParamMetaRef.current = null;
      chatIdRef.current = urlConversationId ?? null;
      paramQueueRef.current = Promise.resolve();
    }
    prevUrlConversationIdRef.current = urlConversationId ?? null;
    setChatMeta(null);
  }, [cancel, paramSyncDebug, urlConversationId]);

  useEffect(() => {
    paramSyncTokenRef.current += 1;
    chatIdRef.current = chatId;
    setMessages([]);
    setHasStarted(false);
    setShowParamDrawer(false);
    setUserClosedDrawer(false);
    setParamToast(null);
    updateCurrentState(null);
    setDismissedCheckpointId(null);
    setShowConfirmEdit(false);
    setConfirmEditInstructions("");
    setConfirmEditParams("");
    setConfirmActionError(null);
    setChatMeta(null);
    paramQueueRef.current = Promise.resolve();
    cancel();
    stateAbortRef.current?.abort();
    stateAbortRef.current = null;
    currentStateAbortRef.current?.abort();
    currentStateAbortRef.current = null;
    lastSseEventIdRef.current = null;
    lastParamEventIdRef.current = null;
    lastParamMetaRef.current = null;
  }, [chatId, cancel]);

  useEffect(() => {
    if (!chatId) return;
    initParamChat({ chatId });
  }, [chatId, initParamChat]);

  useEffect(() => {
    return () => {
      stateAbortRef.current?.abort();
      currentStateAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    lastSseEventIdRef.current = lastEventId ?? null;
  }, [lastEventId]);

  useEffect(() => {
    if (!paramSyncDebug) {
      prevParamValuesRef.current = parameters;
      return;
    }
    const prev = prevParamValuesRef.current;
    const next = parameters;
    const keys = new Set([...Object.keys(prev || {}), ...Object.keys(next || {})]);
    const changedKeys: string[] = [];
    for (const key of keys) {
      const typedKey = key as keyof SealParameters;
      if (!areParamValuesEquivalent(typedKey, prev?.[typedKey], next?.[typedKey])) {
        changedKeys.push(key);
      }
    }
    if (changedKeys.length) {
      console.log("[param-sync] values_changed", {
        chat_id: chatId,
        keys: changedKeys,
      });
    }
    prevParamValuesRef.current = next;
  }, [chatId, parameters, paramSyncDebug]);

  const refreshCurrentState = useCallback(async () => {
    if (!chatId || !token) return;
    const expectedChatId = chatId;
    currentStateAbortRef.current?.abort();
    const controller = new AbortController();
    currentStateAbortRef.current = controller;
    try {
      const res = await fetchWithAuth(`/api/langgraph/state?thread_id=${encodeURIComponent(chatId)}`, token, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        throw new Error(msg || `HTTP ${res.status}`);
      }
      const body = await res.json().catch(() => null);
      const normalized = normalizeStatePayload(body);
      if (!normalized) return;
      if (controller.signal.aborted) return;
      if (chatIdRef.current !== expectedChatId) return;
      const merged = mergeState(currentStateRef.current, normalized);
      updateCurrentState(merged);
      syncCurrentStateParameters(merged);
      const state = body.state && typeof body.state === "object" ? body.state : {};
      if (normalized.parameters && typeof normalized.parameters === "object") {
        const normalizedParams = normalizeIncomingParameters(normalized.parameters as Record<string, unknown>);
        const versions = normalizeIncomingParameterVersions(
          (state as Record<string, unknown>).parameter_versions,
        );
        const updatedAt = normalizeIncomingParameterUpdatedAt(
          (state as Record<string, unknown>).parameter_updated_at,
        );
        replaceParamFromServer({
          chatId: expectedChatId,
          parameters: normalizedParams as SealParameters,
          versions,
          updatedAt,
        });
      }
    } finally {
      if (currentStateAbortRef.current === controller) {
        currentStateAbortRef.current = null;
      }
    }
  }, [chatId, token, replaceParamFromServer, syncCurrentStateParameters, updateCurrentState]);

  // ===== Öffnen per UI-Event (wie früher) =====
  const applyLocalParameters = useCallback(
    (patch: Partial<SealParameters>, opts?: { markDirty?: boolean; clearDirty?: boolean }) => {
      if (!patch || typeof patch !== "object") return;
      if (chatId) {
        applyLocalEdit(chatId, patch, opts);
      }
    },
    [chatId, applyLocalEdit],
  );

  const applyServerParameters = useCallback(
    (next: SealParameters, eventId?: string | null) => {
      if (!chatId) return;
      applyServerParams(chatId, next, eventId ?? null);
    },
    [chatId, applyServerParams],
  );

  useEffect(() => {
    applyServerParametersRef.current = applyServerParameters;
  }, [applyServerParameters]);

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
  }): Promise<SealParameters | null> => {
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
      if (paramSyncDebug) {
        const serverPressure = (next as SealParameters).pressure_bar;
        const serverAlias = (next as SealParameters as any).pressure;
        console.log("[param-wire] refresh_payload", {
          chat_id: expectedChatId,
          pressure_bar: serverPressure,
          pressure_bar_type: typeof serverPressure,
          pressure_alias: serverAlias,
          pressure_alias_type: typeof serverAlias,
        });
      }
      applyServerParameters(next as SealParameters, expectedEventId ?? null);
      if (paramSyncDebug) {
        const refreshedKeysCount = Object.keys(next || {}).length;
        console.log({
          chat_id: expectedChatId,
          patched_keys_count: patchedKeysCount,
          refreshed_keys_count: refreshedKeysCount,
        });
      }
      return next as SealParameters;
    } finally {
      if (stateAbortRef.current === controller) {
        stateAbortRef.current = null;
      }
    }
  }, [applyServerParameters, paramSyncDebug, shouldAbortParamTask]);

  const sendParameterPatch = useCallback(
    async (patch: Partial<SealParameters>) => {
      if (!chatId || !token) return null;
      const cleaned = cleanParameterPatch(patch);
      if (!Object.keys(cleaned).length) return null;
      try {
        await enqueueParamTask(async (tokenId) => {
          if (shouldAbortParamTask(tokenId, chatId)) return null;
          const baseVersions: Record<string, number> = {};
          for (const key of Object.keys(cleaned)) {
            const typedKey = key as keyof SealParameters;
            const localVersion = versionsRef.current?.[typedKey];
            baseVersions[key] = typeof localVersion === "number" ? localVersion : 0;
          }
          await patchV2Parameters({
            chatId,
            token,
            parameters: cleaned,
            baseVersions,
          });
          return null;
        });
      } catch (err: any) {
        if (err?.name === "AbortError") return null;
        const message = typeof err?.message === "string" ? err.message : String(err);
        setParamToast(`Parameter update fehlgeschlagen: ${message}`);
        window.setTimeout(() => setParamToast(null), 2500);
      }
      return null;
    },
    [chatId, token, enqueueParamTask, shouldAbortParamTask, setParamToast],
  );

  const scheduleNumericPatch = useCallback(
    (name: keyof SealParameters, value: string | number) => {
      const key = String(name);
      if (numericPatchTimersRef.current[key]) {
        clearTimeout(numericPatchTimersRef.current[key]!);
      }
      numericPatchTimersRef.current[key] = setTimeout(() => {
        numericPatchTimersRef.current[key] = null;
        void sendParameterPatch({ [name]: value });
      }, 300);
    },
    [sendParameterPatch],
  );

  useEffect(() => {
    return () => {
      for (const timer of Object.values(numericPatchTimersRef.current)) {
        if (timer) clearTimeout(timer);
      }
    };
  }, []);

  const handleParameterFieldChange = useCallback(
    (
      name: keyof SealParameters,
      value: string | number,
      opts: { hasOptions: boolean; type?: string },
    ) => {
      if (paramSyncDebug) {
        const normalized = cleanParameterPatch({ [name]: value });
        const normalizedValue =
          Object.prototype.hasOwnProperty.call(normalized, name) ? (normalized as any)[name] : undefined;
        console.log("[param-sync] input_change", {
          chat_id: chatId,
          field: name,
          raw_value: value,
          normalized_value: normalizedValue,
        });
        if (name === "pressure_bar") {
          console.log("[param-wire] input_change", {
            chat_id: chatId,
            field: name,
            value,
            value_type: typeof value,
          });
        }
      }
      if (opts.hasOptions) {
        void sendParameterPatch({ [name]: value });
        return;
      }
      if (opts.type === "number") {
        scheduleNumericPatch(name, value);
        return;
      }
      void sendParameterPatch({ [name]: value });
    },
    [chatId, paramSyncDebug, scheduleNumericPatch, sendParameterPatch],
  );

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
    if (!chatId || !token) return null;
    const cleaned = cleanParameterPatch(patch);
    if (!Object.keys(cleaned).length) return null;
    const patchedKeysCount = Object.keys(cleaned).length;
    if (paramSyncDebug) {
      console.log("[param-sync] patch_request", {
        chat_id: chatId,
        thread_id: chatId,
        keys: Object.keys(cleaned),
      });
    }
    return enqueueParamTask(async (tokenId) => {
      if (shouldAbortParamTask(tokenId, chatId)) return null;
      const patchStart = performance.now();
      let ok = false;
      try {
        const baseVersions: Record<string, number> = {};
        for (const key of Object.keys(cleaned)) {
          const typedKey = key as keyof SealParameters;
          const localVersion = versionsRef.current?.[typedKey];
          baseVersions[key] = typeof localVersion === "number" ? localVersion : 0;
        }
        await patchV2Parameters({
          chatId,
          token,
          parameters: cleaned,
          baseVersions,
        });
        ok = true;
      } finally {
        emitParamPatchTelemetry(patchedKeysCount, performance.now() - patchStart, ok);
      }
      const refreshed = await runRefresh({
        expectedChatId: chatId,
        token,
        patchedKeysCount,
        tokenId,
      });
      return refreshed;
    });
  }, [chatId, token, enqueueParamTask, runRefresh, shouldAbortParamTask, paramSyncDebug]);

  const onParamSubmit = useCallback(async () => {
    try {
      const cleaned = cleanParameterPatch(paramsRef.current ?? {});
      if (paramSyncDebug) {
        console.log("[param-sync] applyParameters clicked", {
          chat_id: chatId,
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

      const canSendChatMessage = isAuthed && Boolean(chatId) && sseStatus !== "offline";
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
      setParamToast("Parameter gesendet");
      window.setTimeout(() => setParamToast(null), 1500);
    } catch (e: any) {
      setParamToast(`Update fehlgeschlagen: ${String(e?.message || e)}`);
      window.setTimeout(() => setParamToast(null), 2500);
    }
  }, [chatId, paramSyncDebug, patchAllParameters, send, isAuthed, sseStatus]);

  useEffect(() => {
    if (!chatId || !token) return;
    refreshParameters({ expectedEventId: lastEventId ?? null }).catch((err) => {
      if (err?.name === "AbortError") return;
      console.warn("[param-sync] initial_state_fetch_failed", err);
    });
  }, [chatId, token, lastEventId, refreshParameters]);

  useEffect(() => {
    if (!chatId || !token) return;
    refreshCurrentState().catch((err) => {
      if (err?.name === "AbortError") return;
      console.warn("[state] initial_fetch_failed", err);
    });
  }, [chatId, token, refreshCurrentState]);

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
    const doneChatId = String((lastDoneEvent as any).data?.chat_id || "");
    if (!doneChatId || doneChatId !== chatId) return;
    refreshParameters({ expectedEventId: (lastDoneEvent as any).id ?? null }).catch((err) => {
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

  const syncAutoAnchor = useCallback(() => {
    if (!streaming || !autoAnchor) return;
    const cont = scrollRef.current;
    const t = targetTopRef.current;
    if (!cont || t == null) return;
    if (Math.abs(cont.scrollTop - t) > 40) cont.scrollTo({ top: t, behavior: "auto" });
  }, [streaming, autoAnchor]);

  useEffect(() => {
    if (!streaming) {
      targetTopRef.current = null;
      setAutoAnchor(false);
    }
  }, [streaming]);

  const firstName = (session?.user?.name || "").split(" ")[0] || "";
  const hasThread = Boolean(chatId);
  const sendingDisabled = !isAuthed || authExpired || !hasThread;
  const isInitial = messages.length === 0 && !hasStarted;
  const [showReconnectLost, setShowReconnectLost] = useState(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (sseStatus === "reconnecting") {
      setShowReconnectLost(false);
      reconnectTimerRef.current = setTimeout(() => {
        setShowReconnectLost(true);
      }, 10000);
    } else {
      setShowReconnectLost(false);
    }
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [sseStatus]);

  const showConnectionLost = sseStatus === "offline" || (sseStatus === "reconnecting" && showReconnectLost);
  const statusLabel = useMemo(() => {
    if (authExpired) return "Bitte neu anmelden";
    if (!isAuthed) return "Bitte anmelden";
    if (!hasThread) return "Initialisiere Sitzung…";
    if (showConnectionLost) return "Verbindung verloren";
    if (streaming) return "Streaming…";
    if (sseStatus === "connecting") return "Verbinde…";
    if (sseStatus === "reconnecting") return "Verbinde…";
    return "Bereit";
  }, [authExpired, hasThread, isAuthed, showConnectionLost, sseStatus, streaming]);

  const handleReauth = useCallback(() => {
    const callbackUrl = toRelativeCallbackUrl(window.location.href);
    signIn("keycloak", { callbackUrl });
  }, []);

  const handleSend = useCallback(async (msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;
    clearRagSources();

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
  }, [sendingDisabled, clearRagSources, send, patchAllParameters, applyLocalParameters]);

  const activeCheckpoint = useMemo(() => {
    if (!confirmCheckpoint) return null;
    if (dismissedCheckpointId && (confirmCheckpoint as any).checkpoint_id === dismissedCheckpointId) return null;
    return confirmCheckpoint;
  }, [confirmCheckpoint, dismissedCheckpointId]);

  useEffect(() => {
    if (activeCheckpoint) {
      if (!userClosedDrawer) setShowParamDrawer(true);
    } else {
      setUserClosedDrawer(false);
    }
  }, [activeCheckpoint, userClosedDrawer]);

  const missingCoreFields = useMemo(() => {
    const knownCore = ["medium", "temperature_C", "pressure_bar", "speed_rpm", "shaft_diameter"];
    const raw =
      (activeCheckpoint as any)?.preview?.coverage_gaps ??
      [];
    const list = Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : [];
    const filtered = list.filter((k) => knownCore.includes(k));
    return Array.from(new Set(filtered));
  }, [activeCheckpoint]);

  const openMissingParameterForm = useCallback(() => {
    setShowParamDrawer(true);
    window.dispatchEvent(
      new CustomEvent("sealai:ui", {
        detail: { ui_action: "open_form", action: "open_form", missing: missingCoreFields, source: "confirm_checkpoint" },
      }),
    );
  }, [missingCoreFields]);

  const submitConfirmDecision = useCallback(
    async (decision: "approve" | "reject" | "edit", edits?: { parameters?: Partial<SealParameters>; instructions?: string }) => {
      if (!chatId) return;
      if (!token) return;
      if (!activeCheckpoint) return;
      if (confirmActionBusy) return;
      setConfirmActionBusy(true);
      setConfirmActionError(null);
      try {
        const res = await fetchWithAuth("/api/langgraph/confirm/go", token, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            chat_id: chatId,
            checkpoint_id: (activeCheckpoint as any).checkpoint_id,
            decision,
            ...(edits ? { edits } : {}),
          }),
        });
        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          throw new Error(msg || `HTTP ${res.status}`);
        }
        const payload = await res.json().catch(() => null);
        setConfirmActionBusy(false);
        setDismissedCheckpointId((activeCheckpoint as any).checkpoint_id);
        if (payload?.final_text && typeof payload.final_text === "string") {
          setMessages((m) => [...m, { role: "assistant", content: payload.final_text }]);
        }
      } catch (e: any) {
        setConfirmActionBusy(false);
        setConfirmActionError(String(e?.message || e));
      }
    },
    [activeCheckpoint, chatId, confirmActionBusy, token],
  );

  const approveConfirmGo = useCallback(async () => {
    await submitConfirmDecision("approve");
  }, [submitConfirmDecision]);

  const rejectConfirmGo = useCallback(async () => {
    await submitConfirmDecision("reject");
  }, [submitConfirmDecision]);

  const confirmEditGo = useCallback(async () => {
    const instructions = confirmEditInstructions.trim();
    const parsedParams = parseParamEdits(confirmEditParams);
    const patch = parsedParams && Object.keys(parsedParams).length ? parsedParams : null;
    if (patch) {
      applyLocalParameters(patch, { clearDirty: true });
      try {
        await patchAllParameters(patch);
      } catch (e: any) {
        setConfirmActionError(`Parameter-Update fehlgeschlagen: ${String(e?.message || e)}`);
        return;
      }
    }
    await submitConfirmDecision("edit", {
      parameters: patch ?? undefined,
      instructions: instructions || undefined,
    });
    setShowConfirmEdit(false);
    setConfirmEditInstructions("");
    setConfirmEditParams("");
  }, [confirmEditInstructions, confirmEditParams, applyLocalParameters, patchAllParameters, submitConfirmDecision]);

  return (
    <div className="flex flex-col h-full w-full bg-transparent relative">
      {paramSyncDebug ? (
        <div className="absolute left-3 top-3 z-40 rounded-md border border-slate-200 bg-white/90 px-2 py-1 text-[11px] text-slate-700 shadow-sm">
          <div>url_conversation_id: {urlConversationId ?? "null"}</div>
          <div>chat_id: {chatId ?? "null"}</div>
          <div>paramState.pressure_bar: {String((parameters as any).pressure_bar ?? "null")}</div>
          <div>currentState.pressure_bar: {String(((currentState?.parameters as any) ?? {})?.pressure_bar ?? "null")}</div>
        </div>
      ) : null}

      {/* Toggle Button rechts (wie “aufschiebbare” Sidebar) */}
      <button
        type="button"
        onClick={() => {
          setUserClosedDrawer(false);
          setShowParamDrawer(true);
        }}
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
          onClick={() => {
            setShowParamDrawer(false);
            setUserClosedDrawer(true);
          }}
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
            currentState={currentState}
            onFieldChange={handleParameterFieldChange}
            onSubmit={onParamSubmit}
            onClose={() => {
              setShowParamDrawer(false);
              setUserClosedDrawer(true);
            }}
            activeCheckpoint={activeCheckpoint}
            confirmBusy={confirmActionBusy}
            confirmError={confirmActionError}
            onApprove={approveConfirmGo}
            onReject={rejectConfirmGo}
            onEdit={() => setShowConfirmEdit(true)}
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
              <span
                className={
                  showConnectionLost
                    ? "text-red-600"
                    : streaming
                      ? "text-emerald-600"
                      : "text-amber-600"
                }
              >
                {statusLabel}
              </span>
              {showConnectionLost && lastError ? (
                <span className="block mt-1 text-[11px] text-red-500">Fehler: {lastError}</span>
              ) : null}
            </div>

            <ChatInput
              value={inputValue}
              setValue={setInputValue}
              onSend={handleSend}
              onStop={() => cancel()}
              disabled={sendingDisabled}
              streaming={streaming}
              placeholder={
                authExpired
                  ? "Bitte neu anmelden"
                  : isAuthed
                  ? !hasThread
                    ? "Initialisiere Sitzung…"
                    : sseStatus === "connecting" || sseStatus === "reconnecting"
                      ? "Verbinde…"
                      : "Was möchtest du wissen?"
                  : "Bitte anmelden, um zu schreiben"
              }
            />

            {snapshotLabel ? (
              <div className="mt-1 text-[11px] text-gray-500 text-center">
                {snapshotLabel}
              </div>
            ) : null}
            {!isAuthed && (
              <div className="mt-2 text-xs text-gray-500 text-center">
                Du musst angemeldet sein, um Nachrichten zu senden.
              </div>
            )}
            {authExpired ? (
              <div className="mt-2 text-xs text-red-500 text-center select-none">
                Bitte neu anmelden.
                <button
                  type="button"
                  onClick={handleReauth}
                  className="ml-2 text-xs font-semibold text-sky-600 hover:text-sky-700 underline underline-offset-2"
                >
                  Neu anmelden
                </button>
              </div>
            ) : showConnectionLost ? (
              <div className="mt-2 text-xs text-red-500 text-center select-none">
                Fehler: {lastError || "Verbindung verloren."}
                <button
                  type="button"
                  onClick={reconnect}
                  className="ml-2 text-xs font-semibold text-sky-600 hover:text-sky-700 underline underline-offset-2"
                >
                  Erneut versuchen
                </button>
              </div>
            ) : null}
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
            {activeCheckpoint ? (
              <div className="w-full max-w-[768px] mx-auto px-4 pt-3">
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                  <div className="font-semibold">Freigabe erforderlich</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide">
                      Aktion: {(activeCheckpoint as any).action}
                    </span>
                    <span className="text-xs">
                      Risiko: {(activeCheckpoint as any).risk === "high" ? "hoch" : (activeCheckpoint as any).risk === "low" ? "niedrig" : "mittel"}
                    </span>
                  </div>

                  {missingCoreFields.length > 0 ? (
                    <div className="mt-1 text-xs">
                      Fehlt (Kernfelder): <span className="font-semibold">{missingCoreFields.join(", ")}</span>
                    </div>
                  ) : null}

                  {(activeCheckpoint as any).preview?.text ? (
                    <div className="mt-2 whitespace-pre-wrap text-xs text-amber-900">
                      {(activeCheckpoint as any).preview.text}
                    </div>
                  ) : null}

                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!token || streaming || confirmActionBusy}
                      onClick={approveConfirmGo}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {confirmActionBusy ? "Freigabe läuft…" : "Freigeben"}
                    </button>

                    <button
                      type="button"
                      disabled={streaming || confirmActionBusy}
                      onClick={rejectConfirmGo}
                      className="rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-amber-950 ring-1 ring-amber-300 disabled:opacity-50"
                    >
                      Ablehnen
                    </button>

                    <button
                      type="button"
                      disabled={streaming || confirmActionBusy}
                      onClick={() => setShowConfirmEdit(true)}
                      className="rounded-md bg-amber-800 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Bearbeiten
                    </button>

                    {confirmActionError ? (
                      <span className="text-xs text-red-700">Freigabe fehlgeschlagen: {confirmActionError}</span>
                    ) : null}
                  </div>

                  {missingCoreFields.length > 0 ? (
                    <div className="mt-2">
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
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {showConfirmEdit && activeCheckpoint ? (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
                <div className="w-full max-w-[520px] rounded-lg bg-white p-4 shadow-lg">
                  <div className="text-sm font-semibold text-slate-800">Checkpoint bearbeiten</div>
                  <div className="mt-2 text-xs text-slate-500">
                    Optional: Parameter anpassen oder eine kurze Anweisung hinterlassen.
                  </div>
                  <label className="mt-3 block text-xs font-semibold text-slate-600">
                    Anweisung
                  </label>
                  <textarea
                    value={confirmEditInstructions}
                    onChange={(e) => setConfirmEditInstructions(e.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-800"
                    rows={3}
                    placeholder="Kurze Anweisung (optional)"
                  />
                  <label className="mt-3 block text-xs font-semibold text-slate-600">
                    Parameter-Edits (key=value, eine pro Zeile)
                  </label>
                  <textarea
                    value={confirmEditParams}
                    onChange={(e) => setConfirmEditParams(e.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-800"
                    rows={4}
                    placeholder={"pressure_bar=6\ntemperature_C=80"}
                  />
                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setShowConfirmEdit(false)}
                      className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600"
                    >
                      Abbrechen
                    </button>
                    <button
                      type="button"
                      onClick={confirmEditGo}
                      disabled={confirmActionBusy}
                      className="rounded-md bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Speichern &amp; Fortsetzen
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            <QualityMetaPanel meta={chatMeta} />

            <ChatHistory messages={messages} />

            <div ref={anchorRef} aria-hidden />

            {streaming && (
              <div className="w-full max-w-[768px] mx-auto px-4 py-2">
                <StreamingMessage ref={streamingRef} onFrame={syncAutoAnchor} />
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
                  authExpired
                    ? "Bitte neu anmelden"
                    : isAuthed
                    ? !hasThread
                      ? "Initialisiere Sitzung…"
                      : sseStatus === "connecting" || sseStatus === "reconnecting"
                        ? "Verbinde…"
                        : "Was möchtest du wissen?"
                    : "Bitte anmelden, um zu schreiben"
                }
              />
              {!isAuthed && (
                <div className="mt-2 text-xs text-gray-500">
                  Du musst angemeldet sein, um Nachrichten zu senden.
                </div>
              )}
              <div className="mt-2 text-xs text-gray-500">
                Status: <span className={showConnectionLost ? "text-red-600" : "text-gray-600"}>{statusLabel}</span>
              </div>
              {snapshotLabel ? (
                <div className="mt-1 text-[11px] text-gray-500">
                  {snapshotLabel}
                </div>
              ) : null}
              {authExpired ? (
                <div className="mt-1 text-xs text-red-500 select-none">
                  Bitte neu anmelden.
                  <button
                    type="button"
                    onClick={handleReauth}
                    className="ml-2 text-xs font-semibold text-sky-600 hover:text-sky-700 underline underline-offset-2"
                  >
                    Neu anmelden
                  </button>
                </div>
              ) : showConnectionLost ? (
                <div className="mt-1 text-xs text-red-500 select-none">
                  Fehler: {lastError || "Verbindung verloren."}
                  <button
                    type="button"
                    onClick={reconnect}
                    className="ml-2 text-xs font-semibold text-sky-600 hover:text-sky-700 underline underline-offset-2"
                  >
                    Erneut versuchen
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
