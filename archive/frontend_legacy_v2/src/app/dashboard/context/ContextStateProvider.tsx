"use client";

import React, { createContext, useContext, useMemo, useState } from "react";
import type { ContextState, UploadedTechnicalFile } from "@/types/context";
import { DEFAULT_CONTEXT_STATE } from "@/types/context";

type ContextStateContextValue = {
  contextState: ContextState;
  updateContext: (patch: Partial<ContextState>) => void;
  resetContext: () => void;
  addAttachments: (files: UploadedTechnicalFile[]) => void;
};

const ContextStateContext = createContext<ContextStateContextValue | null>(null);

export function ContextStateProvider({
  children,
  initialState,
}: {
  children: React.ReactNode;
  initialState?: Partial<ContextState>;
}) {
  const [contextState, setContextState] = useState<ContextState>({
    ...DEFAULT_CONTEXT_STATE,
    ...initialState,
    attachments: initialState?.attachments ?? DEFAULT_CONTEXT_STATE.attachments,
  });

  const updateContext = (patch: Partial<ContextState>) => {
    setContextState((prev) => ({
      ...prev,
      ...patch,
      attachments: patch.attachments ?? prev.attachments,
    }));
  };

  const resetContext = () => setContextState(DEFAULT_CONTEXT_STATE);

  const addAttachments = (files: UploadedTechnicalFile[]) => {
    if (!files.length) return;
    setContextState((prev) => ({
      ...prev,
      attachments: [...prev.attachments, ...files],
    }));
  };

  const value = useMemo(
    () => ({ contextState, updateContext, resetContext, addAttachments }),
    [contextState],
  );

  return <ContextStateContext.Provider value={value}>{children}</ContextStateContext.Provider>;
}

export function useContextState(): ContextStateContextValue {
  const ctx = useContext(ContextStateContext);
  if (!ctx) {
    throw new Error("useContextState must be used within ContextStateProvider");
  }
  return ctx;
}
