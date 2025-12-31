"use client";

import React, { createContext, useCallback, useContext, useMemo, useReducer } from "react";
import type { SealParameters } from "@/lib/types/sealParameters";
import { applyParameterPatchAck, type ParameterPatchAckPayload } from "@/lib/parameterSync";

type ParamEntry = {
  parameters: SealParameters;
  versions: Partial<Record<keyof SealParameters, number>>;
  updatedAt: Partial<Record<keyof SealParameters, number>>;
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
  | { type: "optimistic"; payload: { chatId: string; patch: Partial<SealParameters> } };

const ParamStoreContext = createContext<{
  state: ParamStoreState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

const EMPTY_ENTRY: ParamEntry = {
  parameters: {},
  versions: {},
  updatedAt: {},
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
    case "apply_patch": {
      const { chatId, ack } = action.payload;
      const existing = state.byChatId[chatId] ?? EMPTY_ENTRY;
      const result = applyParameterPatchAck(existing.parameters, existing.versions, ack);
      const nextUpdatedAt = { ...existing.updatedAt };
      for (const [key, version] of Object.entries(ack.versions || {})) {
        const typedKey = key as keyof SealParameters;
        if (typeof version !== "number") continue;
        const localVersion = existing.versions?.[typedKey] ?? 0;
        if (version <= localVersion) continue;
        const ts = ack.updated_at?.[key];
        if (typeof ts === "number") nextUpdatedAt[typedKey] = ts;
      }
      return {
        byChatId: {
          ...state.byChatId,
          [chatId]: {
            parameters: result.values,
            versions: result.versions,
            updatedAt: nextUpdatedAt,
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

  const applyPatchAck = useCallback(
    (chatIdValue: string, ack: ParameterPatchAckPayload) =>
      ctx.dispatch({ type: "apply_patch", payload: { chatId: chatIdValue, ack } }),
    [ctx],
  );

  return {
    parameters: entry.parameters,
    versions: entry.versions,
    updatedAt: entry.updatedAt,
    getSnapshot: (chatIdValue?: string | null) => getParamSnapshot(ctx.state, chatIdValue ?? chatId),
    initChat,
    replaceFromServer,
    setLocalOptimistic,
    applyPatchAck,
  };
}
