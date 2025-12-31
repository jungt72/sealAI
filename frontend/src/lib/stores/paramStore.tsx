"use client";

import React, { createContext, useCallback, useContext, useMemo, useReducer } from "react";
import type { SealParameters } from "@/lib/types/sealParameters";
import {
  applyParameterPatchAck,
  computeAppliedKeys,
  mergeServerParameters,
  reconcileDirtyWithServer,
  type ParameterMeta,
  type ParameterPatchAckPayload,
} from "@/lib/parameterSync";

type ParamEntry = {
  parameters: SealParameters;
  versions: Partial<Record<keyof SealParameters, number>>;
  updatedAt: Partial<Record<keyof SealParameters, number>>;
  dirty: Set<keyof SealParameters>;
  pending: Set<keyof SealParameters>;
  applied: Partial<Record<keyof SealParameters, number>>;
  lastServerEventId?: string | null;
};

type ParamStoreState = {
  byChatId: Record<string, ParamEntry>;
};

type InitPayload = {
  chatId: string;
  parameters?: SealParameters;
  versions?: Partial<Record<keyof SealParameters, number>>;
  updatedAt?: Partial<Record<keyof SealParameters, number>>;
};

type ReplacePayload = {
  chatId: string;
  parameters: SealParameters;
  versions: Partial<Record<keyof SealParameters, number>>;
  updatedAt: Partial<Record<keyof SealParameters, number>>;
};

type Action =
  | { type: "init"; payload: InitPayload }
  | { type: "replace"; payload: ReplacePayload }
  | { type: "apply_patch"; payload: { chatId: string; ack: ParameterPatchAckPayload } }
  | { type: "optimistic"; payload: { chatId: string; patch: Partial<SealParameters> } }
  | {
      type: "apply_local";
      payload: { chatId: string; patch: Partial<SealParameters>; markDirty?: boolean; clearDirty?: boolean };
    }
  | {
      type: "apply_delta";
      payload: { chatId: string; incoming: Partial<SealParameters>; meta?: ParameterMeta; eventId?: string | null };
    }
  | { type: "set_pending"; payload: { chatId: string; keys: Set<keyof SealParameters> } }
  | { type: "clear_pending"; payload: { chatId: string; keys: Set<keyof SealParameters> } }
  | { type: "prune_applied"; payload: { chatId: string; ttlMs: number } };

const ParamStoreContext = createContext<{
  state: ParamStoreState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

const EMPTY_ENTRY: ParamEntry = {
  parameters: {},
  versions: {},
  updatedAt: {},
  dirty: new Set(),
  pending: new Set(),
  applied: {},
  lastServerEventId: null,
};

export function reduceParamStore(state: ParamStoreState, action: Action): ParamStoreState {
  switch (action.type) {
    case "init": {
      const { chatId, parameters, versions, updatedAt } = action.payload;
      const existing = state.byChatId[chatId];
      if (existing) return state;
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            parameters: parameters ?? {},
            versions: versions ?? {},
            updatedAt: updatedAt ?? {},
            dirty: new Set(),
            pending: new Set(),
            applied: {},
            lastServerEventId: null,
          },
        },
      };
    }
    case "replace": {
      const { chatId, parameters, versions, updatedAt } = action.payload;
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            parameters,
            versions,
            updatedAt,
            dirty: new Set(),
            pending: new Set(),
            applied: {},
            lastServerEventId: null,
          },
        },
      };
    }
    case "optimistic": {
      const { chatId, patch } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            parameters: { ...existing.parameters, ...patch },
          },
        },
      };
    }
    case "apply_local": {
      const { chatId, patch, markDirty, clearDirty } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const nextDirty = new Set(existing.dirty);
      const nextPending = new Set(existing.pending);
      const nextApplied = { ...existing.applied };
      const keys = Object.keys(patch) as (keyof SealParameters)[];
      if (markDirty) {
        for (const key of keys) {
          nextDirty.add(key);
          nextPending.delete(key);
          delete nextApplied[key];
        }
      }
      if (clearDirty) {
        for (const key of keys) {
          nextDirty.delete(key);
          nextPending.delete(key);
          delete nextApplied[key];
        }
      }
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            parameters: { ...existing.parameters, ...patch },
            dirty: nextDirty,
            pending: nextPending,
            applied: nextApplied,
          },
        },
      };
    }
    case "apply_delta": {
      const { chatId, incoming, meta, eventId } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const currentValues = existing.parameters ?? {};
      const nextDirty = reconcileDirtyWithServer(currentValues, incoming, existing.dirty, existing.pending);
      const nextPending = new Set(existing.pending);
      const forceOverwriteKeys = new Set<keyof SealParameters>();
      if (meta) {
        for (const [key, entry] of Object.entries(meta)) {
          const typedKey = key as keyof SealParameters;
          if (entry?.force_overwrite) {
            forceOverwriteKeys.add(typedKey);
            nextDirty.delete(typedKey);
            nextPending.delete(typedKey);
          }
        }
      }
      const merged = mergeServerParameters(currentValues, incoming, nextDirty, meta);
      const appliedKeys = computeAppliedKeys(currentValues, incoming, existing.dirty);
      const nextApplied: Partial<Record<keyof SealParameters, number>> = {
        ...existing.applied,
      };
      for (const key of Array.from(nextPending)) {
        if (!nextDirty.has(key)) nextPending.delete(key);
      }
      const appliedAt = Date.now();
      for (const key of appliedKeys) {
        if (forceOverwriteKeys.has(key)) continue;
        nextApplied[key] = appliedAt;
        nextPending.delete(key);
      }
      for (const key of nextDirty) {
        delete nextApplied[key];
      }
      for (const key of forceOverwriteKeys) {
        delete nextApplied[key];
      }
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            parameters: merged,
            dirty: nextDirty,
            pending: nextPending,
            applied: nextApplied,
            lastServerEventId: eventId ?? existing.lastServerEventId ?? null,
          },
        },
      };
    }
    case "apply_patch": {
      const { chatId, ack } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const result = applyParameterPatchAck(existing.parameters, existing.versions, ack);
      const nextUpdatedAt = { ...existing.updatedAt };
      const nextDirty = new Set(existing.dirty);
      const nextPending = new Set(existing.pending);
      const nextApplied = { ...existing.applied };
      for (const [key, version] of Object.entries(ack.versions || {})) {
        const typedKey = key as keyof SealParameters;
        if (typeof version !== "number") continue;
        const localVersion = existing.versions?.[typedKey] ?? 0;
        if (version <= localVersion) continue;
        const ts = ack.updated_at?.[key];
        if (typeof ts === "number") nextUpdatedAt[typedKey] = ts;
      }
      const appliedAt = Date.now();
      for (const key of result.applied) {
        nextDirty.delete(key);
        nextPending.delete(key);
        nextApplied[key] = appliedAt;
      }
      for (const rejected of ack.rejected_fields || []) {
        if (!rejected?.field) continue;
        nextPending.delete(rejected.field as keyof SealParameters);
      }
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            parameters: result.values,
            versions: result.versions,
            updatedAt: nextUpdatedAt,
            dirty: nextDirty,
            pending: nextPending,
            applied: nextApplied,
          },
        },
      };
    }
    case "set_pending": {
      const { chatId, keys } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const nextPending = new Set(existing.pending);
      for (const key of keys) nextPending.add(key);
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            pending: nextPending,
          },
        },
      };
    }
    case "clear_pending": {
      const { chatId, keys } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const nextPending = new Set(existing.pending);
      for (const key of keys) nextPending.delete(key);
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            pending: nextPending,
          },
        },
      };
    }
    case "prune_applied": {
      const { chatId, ttlMs } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const nowTs = Date.now();
      const currentApplied = existing.applied ?? {};
      const nextApplied: Partial<Record<keyof SealParameters, number>> = {};
      for (const [key, ts] of Object.entries(currentApplied)) {
        if (!ts) continue;
        if (nowTs - ts < ttlMs) {
          nextApplied[key as keyof SealParameters] = ts;
        }
      }
      if (Object.keys(nextApplied).length === Object.keys(currentApplied).length) {
        return state;
      }
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            ...existing,
            applied: nextApplied,
          },
        },
      };
    }
    default:
      return state;
  }
}

export function getParamSnapshot(state: ParamStoreState, chatId?: string | null) {
  if (!chatId) return null;
  const entry = state.byChatId[chatId] ?? EMPTY_ENTRY;
  return {
    parameters: { ...entry.parameters },
    versions: { ...entry.versions },
    updated_at: { ...entry.updatedAt },
  };
}

export function ParamStoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reduceParamStore, { byChatId: {} });
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <ParamStoreContext.Provider value={value}>{children}</ParamStoreContext.Provider>;
}

export function useParamStore(chatId?: string | null) {
  const ctx = useContext(ParamStoreContext);
  if (!ctx) {
    throw new Error("useParamStore must be used within ParamStoreProvider");
  }

  const entry = chatId ? ctx.state.byChatId[chatId] ?? EMPTY_ENTRY : EMPTY_ENTRY;

  const initChat = useCallback(
    (payload: InitPayload) => ctx.dispatch({ type: "init", payload }),
    [ctx],
  );

  const replaceFromServer = useCallback(
    (payload: ReplacePayload) => ctx.dispatch({ type: "replace", payload }),
    [ctx],
  );

  const setLocalOptimistic = useCallback(
    (chatIdValue: string, patch: Partial<SealParameters>) =>
      ctx.dispatch({ type: "optimistic", payload: { chatId: chatIdValue, patch } }),
    [ctx],
  );

  const applyLocalEdit = useCallback(
    (chatIdValue: string, patch: Partial<SealParameters>, opts?: { markDirty?: boolean; clearDirty?: boolean }) =>
      ctx.dispatch({
        type: "apply_local",
        payload: { chatId: chatIdValue, patch, markDirty: opts?.markDirty, clearDirty: opts?.clearDirty },
      }),
    [ctx],
  );

  const applyRemoteDeltaFromSse = useCallback(
    (
      chatIdValue: string,
      incoming: Partial<SealParameters>,
      meta?: ParameterMeta,
      eventId?: string | null,
    ) =>
      ctx.dispatch({
        type: "apply_delta",
        payload: { chatId: chatIdValue, incoming, meta, eventId },
      }),
    [ctx],
  );

  const applyPatchAck = useCallback(
    (chatIdValue: string, ack: ParameterPatchAckPayload) =>
      ctx.dispatch({ type: "apply_patch", payload: { chatId: chatIdValue, ack } }),
    [ctx],
  );

  const markPending = useCallback(
    (chatIdValue: string, keys: Set<keyof SealParameters>) =>
      ctx.dispatch({ type: "set_pending", payload: { chatId: chatIdValue, keys } }),
    [ctx],
  );

  const clearPending = useCallback(
    (chatIdValue: string, keys: Set<keyof SealParameters>) =>
      ctx.dispatch({ type: "clear_pending", payload: { chatId: chatIdValue, keys } }),
    [ctx],
  );

  const pruneApplied = useCallback(
    (chatIdValue: string, ttlMs: number) =>
      ctx.dispatch({ type: "prune_applied", payload: { chatId: chatIdValue, ttlMs } }),
    [ctx],
  );

  return {
    parameters: entry.parameters,
    versions: entry.versions,
    updatedAt: entry.updatedAt,
    dirty: entry.dirty,
    pending: entry.pending,
    applied: entry.applied,
    lastServerEventId: entry.lastServerEventId ?? null,
    getSnapshot: (chatIdValue?: string | null) => getParamSnapshot(ctx.state, chatIdValue ?? chatId),
    initChat,
    replaceFromServer,
    setLocalOptimistic,
    applyLocalEdit,
    applyRemoteDeltaFromSse,
    applyPatchAck,
    markPending,
    clearPending,
    pruneApplied,
  };
}
