// frontend/src/hooks/useCaseWorkspace.ts
// Hook to fetch the Case Workspace Projection after each turn completes.

import { useState, useEffect, useCallback, useRef } from "react";
import { confirmRfqPackage, generateRfqPdf, fetchCaseWorkspace, selectPartner as apiSelectPartner, initiateRfqHandover as apiInitiateHandover, type CaseWorkspaceProjection } from "@/lib/workspaceApi";

export function useCaseWorkspace(
  accessToken: string,
  chatId: string | null,
  isThinking: boolean,
) {
  const [workspace, setWorkspace] = useState<CaseWorkspaceProjection | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [isSelectingPartner, setIsSelectingPartner] = useState(false);
  const [isHandingOver, setIsHandingOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prevThinkingRef = useRef(isThinking);

  const refresh = useCallback(async () => {
    if (!accessToken || !chatId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchCaseWorkspace(accessToken, chatId);
      setWorkspace(data);
    } catch (err: any) {
      // 404 / empty state is expected for brand-new chats
      if (!err?.message?.includes(":404")) {
        setError(err?.message || "workspace_fetch_failed");
      }
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, chatId]);

  // Fetch when a turn completes (isThinking transitions true -> false)
  useEffect(() => {
    if (prevThinkingRef.current && !isThinking && chatId) {
      refresh();
    }
    prevThinkingRef.current = isThinking;
  }, [isThinking, chatId, refresh]);

  const confirmRfq = useCallback(async () => {
    if (!accessToken || !chatId) return;
    setIsConfirming(true);
    setError(null);
    try {
      const updated = await confirmRfqPackage(accessToken, chatId);
      setWorkspace(updated);
    } catch (err: any) {
      setError(err?.message || "rfq_confirm_failed");
    } finally {
      setIsConfirming(false);
    }
  }, [accessToken, chatId]);

  const generatePdf = useCallback(async () => {
    if (!accessToken || !chatId) return;
    setIsGeneratingPdf(true);
    setError(null);
    try {
      const updated = await generateRfqPdf(accessToken, chatId);
      setWorkspace(updated);
    } catch (err: any) {
      setError(err?.message || "generate_pdf_failed");
    } finally {
      setIsGeneratingPdf(false);
    }
  }, [accessToken, chatId]);

  const selectPartner = useCallback(async (partnerId: string) => {
    if (!accessToken || !chatId) return;
    setIsSelectingPartner(true);
    setError(null);
    try {
      const updated = await apiSelectPartner(accessToken, chatId, partnerId);
      setWorkspace(updated);
    } catch (err: any) {
      setError(err?.message || "partner_select_failed");
    } finally {
      setIsSelectingPartner(false);
    }
  }, [accessToken, chatId]);

  const initiateHandover = useCallback(async () => {
    if (!accessToken || !chatId) return;
    setIsHandingOver(true);
    setError(null);
    try {
      const updated = await apiInitiateHandover(accessToken, chatId);
      setWorkspace(updated);
    } catch (err: any) {
      setError(err?.message || "handover_failed");
    } finally {
      setIsHandingOver(false);
    }
  }, [accessToken, chatId]);

  const reset = useCallback(() => {
    setWorkspace(null);
    setError(null);
    setIsLoading(false);
    setIsConfirming(false);
    setIsGeneratingPdf(false);
    setIsSelectingPartner(false);
    setIsHandingOver(false);
  }, []);

  return { workspace, isLoading, isConfirming, isGeneratingPdf, isSelectingPartner, isHandingOver, error, refresh, confirmRfq, generatePdf, selectPartner, initiateHandover, reset };
}
